"""
Exercise — Agent Communication Patterns (§7)
=============================================

Build the core communication primitives that make multi-agent systems reliable:
typed message schemas, idempotency, dead-letter queues, backpressure, correlation
IDs, and async vs. sync patterns.

Run from the project root:
    python -m agent_comms.communication

Learning goals:
    - Define typed, validated message contracts with correlation IDs (§7.3, §7.7)
    - Detect and discard duplicate messages with an idempotency store (§7.4)
    - Route unprocessable messages to a Dead Letter Queue after retries (§7.5)
    - Signal backpressure with a bounded channel (§7.6)
    - Contrast sync (caller blocks) with async (caller fires and continues) (§7.8)

Key insight: these primitives are framework-independent. Whether you use Kafka,
Redis, or Python queues, the same contracts apply.

Note: this module deliberately avoids asyncio. Threading shows the structural
contrast between sync and async without framework complexity.
"""

from __future__ import annotations

import json
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from google import genai
from google.genai import types
from shared.config import SETTINGS

DIVIDER = "─" * 65
THICK = "═" * 65
SENTINEL = None   # placed in a queue to signal worker shutdown


# ─────────────────────────────────────────────────────────────────────────────
# ── §7.3  MESSAGE SCHEMA
# Every inter-agent message carries a type, payload, unique ID, and a
# correlation ID that threads through every derived message.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Define the Message dataclass.
# Fields: type (discriminator), payload (data), id (unique per message),
# correlation_id (threads through all derived messages), timestamp, attempt (retry count).
# Add a derive() method that creates a new Message with the same correlation_id.


@dataclass
class Message:
    """
    Typed, validated inter-agent message.

    Teaching points:
    §7.3 — 'type' is the discriminator; 'payload' carries typed fields.
    §7.7 — 'correlation_id' is set once on entry and copied to every derived message.
    §7.4 — 'id' is unique per message and used for idempotency checks.
    """
    type: str                                           # message type discriminator
    payload: dict                                       # typed data payload
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    attempt: int = 1                                    # incremented on retry

    def derive(self, new_type: str, new_payload: dict) -> "Message":
        """
        Create a derived message preserving the correlation_id.

        §7.7 teaching point: every downstream message in a pipeline MUST
        preserve the original correlation_id. This is how you reconstruct
        the full request path from logs.
        """
        return Message(
            type=new_type,
            payload=new_payload,
            correlation_id=self.correlation_id,
        )

    def retry(self) -> "Message":
        """Return a copy of this message with attempt incremented."""
        return Message(
            type=self.type,
            payload=self.payload,
            id=self.id,                      # same ID — idempotency store will catch duplicates
            correlation_id=self.correlation_id,
            attempt=self.attempt + 1,
        )


def validate_message(msg: Message, required_fields: list[str]) -> list[str]:
    """
    Validate that the message payload contains all required fields.
    Returns a list of missing field names (empty list = valid).

    §7.3: validate at the boundary — reject malformed messages before
    they propagate errors into downstream stages.
    """
    return [f for f in required_fields if f not in msg.payload]


# ─────────────────────────────────────────────────────────────────────────────
# ── §7.4  IDEMPOTENCY STORE
# Track processed message IDs so duplicates are discarded, not re-executed.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement IdempotencyStore.
# mark_seen(msg_id): record that this ID has been processed.
# is_seen(msg_id): return True if this ID was already processed.


class IdempotencyStore:
    """
    Thread-safe store of processed message IDs.

    Teaching point (§7.4): every message handler checks is_seen() before
    doing work. If seen, it's a no-op — not an error, not a retry.
    This is what makes message delivery "at-least-once safe."

    In production: store IDs in Redis with a TTL so they don't grow forever.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    def mark_seen(self, msg_id: str) -> None:
        with self._lock:
            self._seen.add(msg_id)

    def is_seen(self, msg_id: str) -> bool:
        with self._lock:
            return msg_id in self._seen

    def count(self) -> int:
        return len(self._seen)


# ─────────────────────────────────────────────────────────────────────────────
# ── §7.5  DEAD LETTER QUEUE
# Messages that fail after all retries are moved here instead of being dropped.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement DeadLetterQueue.
# add(msg, reason): record the message and the failure reason.
# list(): return all dead-lettered messages.
# size(): return the count.


class DeadLetterQueue:
    """
    Holds messages that could not be processed after all retries.

    Teaching point (§7.5): a DLQ prevents silent message loss. A human or
    a repair agent inspects DLQ entries, fixes the root cause, and replays.
    Without a DLQ, failed messages vanish and you discover the problem from
    customer complaints — not from your own monitoring.
    """

    def __init__(self) -> None:
        self._entries: list[dict] = []
        self._lock = threading.Lock()

    def add(self, msg: Message, reason: str) -> None:
        with self._lock:
            self._entries.append({
                "msg_id": msg.id,
                "correlation_id": msg.correlation_id,
                "type": msg.type,
                "reason": reason,
                "attempt": msg.attempt,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload_preview": str(msg.payload)[:80],
            })

    def list(self) -> list[dict]:
        with self._lock:
            return list(self._entries)

    def size(self) -> int:
        with self._lock:
            return len(self._entries)


# ─────────────────────────────────────────────────────────────────────────────
# ── §7.6  BACKPRESSURE — BOUNDED CHANNEL
# When the consumer is slower than the producer, the channel fills up and
# signals the producer to pause. This makes bottlenecks visible.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement BoundedChannel.
# Wrap queue.Queue(maxsize=N).
# send(msg): return False (backpressure) if full; True if sent.
# receive(timeout): return next Message or None on timeout.


class BoundedChannel:
    """
    A bounded message queue that signals backpressure when full.

    Teaching point (§7.6): when send() returns False, the producer knows
    to pause or shed load — rather than buffering unboundedly until OOM.
    A bounded channel makes the slowest component visible to producers.
    """

    def __init__(self, maxsize: int = 10, name: str = "channel") -> None:
        self._q: queue.Queue = queue.Queue(maxsize=maxsize)
        self.name = name
        self.maxsize = maxsize
        self.backpressure_count = 0

    def send(self, msg: Message) -> bool:
        """
        Attempt to send a message. Returns False (backpressure) if full.
        Never blocks — the caller must handle the False case.
        """
        try:
            self._q.put_nowait(msg)
            return True
        except queue.Full:
            self.backpressure_count += 1
            return False

    def receive(self, timeout: float = 1.0) -> Optional[Message]:
        """Receive the next message, or return None on timeout."""
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def is_full(self) -> bool:
        return self._q.full()

    def size(self) -> int:
        return self._q.qsize()


# ─────────────────────────────────────────────────────────────────────────────
# ── §7.7  CORRELATION ID LOGGING
# Every log line carries the correlation ID so you can filter and reconstruct
# the full path of a single request.
# ─────────────────────────────────────────────────────────────────────────────

def log_with_correlation(correlation_id: str, stage: str, message: str) -> None:
    """
    Print a structured log line with correlation ID.

    §7.7: filtering all logs for a single correlation_id reconstructs the
    complete execution path across every agent and stage. This is the primary
    debugging tool in multi-agent systems.
    """
    print(f"  [corr={correlation_id}]  {stage:<22}  {message}")


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:8]


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE STAGE FUNCTIONS  (used in both sync and async modes)
# ─────────────────────────────────────────────────────────────────────────────

MAX_RETRIES = 2

REQUIRED_ORDER_FIELDS = ["order_id", "customer_id", "amount"]


def _process_validate(msg: Message, idempotency: IdempotencyStore, dlq: DeadLetterQueue) -> Optional[Message]:
    """Validate an order_received message. Returns validated message or None."""
    cid = msg.correlation_id

    # §7.4  Idempotency check
    if idempotency.is_seen(msg.id):
        log_with_correlation(cid, "validate", f"[DUPLICATE] msg_id={msg.id} — discarded")
        return None
    idempotency.mark_seen(msg.id)

    # §7.3  Schema validation
    missing = validate_message(msg, REQUIRED_ORDER_FIELDS)
    if missing:
        for attempt in range(1, MAX_RETRIES + 1):
            log_with_correlation(cid, "validate", f"[RETRY {attempt}/{MAX_RETRIES}] missing fields: {missing}")
            time.sleep(0.01)   # brief wait before retry
        dlq.add(msg, f"Missing required fields after {MAX_RETRIES} retries: {missing}")
        log_with_correlation(cid, "validate", f"[DLQ] msg moved to dead letter queue")
        return None

    log_with_correlation(cid, "validate", f"order_id={msg.payload['order_id']} ✓ valid")
    return msg.derive("order_validated", msg.payload)


def _process_fulfill(msg: Message) -> Optional[Message]:
    """Simulate order fulfillment."""
    cid = msg.correlation_id
    order_id = msg.payload.get("order_id", "?")
    log_with_correlation(cid, "fulfill", f"order_id={order_id} — allocating inventory")
    time.sleep(0.005)    # simulate work
    return msg.derive("order_fulfilled", {**msg.payload, "warehouse": "WH-01"})


def _process_notify(msg: Message) -> Optional[Message]:
    """Simulate customer notification."""
    cid = msg.correlation_id
    customer_id = msg.payload.get("customer_id", "?")
    log_with_correlation(cid, "notify", f"customer_id={customer_id} — sending confirmation email")
    return msg.derive("notification_sent", {**msg.payload, "channel": "email"})


# ─────────────────────────────────────────────────────────────────────────────
# ── §7.8  SYNC PIPELINE
# All stages run sequentially in-thread. The caller blocks until the entire
# pipeline completes.
# ─────────────────────────────────────────────────────────────────────────────

def run_sync_pipeline(orders: list[dict]) -> list[dict]:
    """
    Run all orders through the pipeline synchronously.

    §7.8 teaching point: sync means the caller blocks on every stage.
    Simple to reason about, but slow — total latency = sum of all stage latencies.
    """
    idempotency = IdempotencyStore()
    dlq = DeadLetterQueue()
    results: list[dict] = []

    for order in orders:
        msg = Message(
            type="order_received",
            payload=order,
            correlation_id=new_correlation_id(),
        )
        validated = _process_validate(msg, idempotency, dlq)
        if validated is None:
            continue
        fulfilled = _process_fulfill(validated)
        if fulfilled is None:
            continue
        notified = _process_notify(fulfilled)
        if notified:
            results.append(notified.payload)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# ── §7.8  ASYNC PIPELINE (threads + bounded channels)
# The caller fires messages into the first channel and gets back immediately.
# Worker threads process stages concurrently. Results land asynchronously.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement stage worker functions and run_async_pipeline.
# Each stage reads from channel_in, does work, writes to channel_out.
# run_async_pipeline returns immediately with correlation_ids;
# workers run in background threads.


def _worker_validate(
    ch_in: BoundedChannel,
    ch_out: BoundedChannel,
    dlq: DeadLetterQueue,
    idempotency: IdempotencyStore,
) -> None:
    """Thread worker for the validate stage."""
    while True:
        msg = ch_in.receive(timeout=2.0)
        if msg is SENTINEL:
            ch_out.send(SENTINEL)
            break
        if msg is None:
            continue
        result = _process_validate(msg, idempotency, dlq)
        if result:
            sent = ch_out.send(result)
            if not sent:
                # §7.6 Backpressure: downstream queue is full
                log_with_correlation(result.correlation_id, "validate",
                                     "[BACKPRESSURE] fulfill channel full — retrying")
                time.sleep(0.05)
                ch_out.send(result)


def _worker_fulfill(ch_in: BoundedChannel, ch_out: BoundedChannel) -> None:
    """Thread worker for the fulfill stage."""
    while True:
        msg = ch_in.receive(timeout=2.0)
        if msg is SENTINEL:
            ch_out.send(SENTINEL)
            break
        if msg is None:
            continue
        result = _process_fulfill(msg)
        if result:
            ch_out.send(result)


def _worker_notify(ch_in: BoundedChannel, results: list) -> None:
    """Thread worker for the notify stage (terminal — writes to results list)."""
    while True:
        msg = ch_in.receive(timeout=2.0)
        if msg is SENTINEL:
            break
        if msg is None:
            continue
        result = _process_notify(msg)
        if result:
            results.append(result.payload)


def run_async_pipeline(orders: list[dict], channel_size: int = 3) -> tuple[list[str], list[dict]]:
    """
    Run orders through the pipeline asynchronously via worker threads.

    Returns immediately with (correlation_ids, results_container).
    results_container is populated by workers as they complete.

    §7.8 teaching point: async means the caller is not blocked by any stage.
    Total latency ≈ slowest single-stage latency, not the sum.
    """
    idempotency = IdempotencyStore()
    dlq = DeadLetterQueue()
    results: list[dict] = []

    # §7.6: bounded channels create natural backpressure between stages
    ch_validate = BoundedChannel(maxsize=channel_size, name="validate_in")
    ch_fulfill  = BoundedChannel(maxsize=channel_size, name="fulfill_in")
    ch_notify   = BoundedChannel(maxsize=channel_size, name="notify_in")

    workers = [
        threading.Thread(target=_worker_validate, args=(ch_validate, ch_fulfill, dlq, idempotency), daemon=True),
        threading.Thread(target=_worker_fulfill,  args=(ch_fulfill, ch_notify), daemon=True),
        threading.Thread(target=_worker_notify,   args=(ch_notify, results), daemon=True),
    ]
    for w in workers:
        w.start()

    correlation_ids: list[str] = []
    for order in orders:
        cid = new_correlation_id()
        msg = Message(type="order_received", payload=order, correlation_id=cid)
        correlation_ids.append(cid)
        sent = ch_validate.send(msg)
        if not sent:
            log_with_correlation(cid, "producer", "[BACKPRESSURE] validate channel full — producer pausing")
            time.sleep(0.1)
            ch_validate.send(msg)

    # Signal shutdown
    ch_validate.send(SENTINEL)
    for w in workers:
        w.join(timeout=5.0)

    return correlation_ids, results


# ─────────────────────────────────────────────────────────────────────────────
# LLM HELPER  (used for a brief AI-powered summary in the demo)
# ─────────────────────────────────────────────────────────────────────────────

def llm(client: genai.Client, system: str, messages: list[dict]) -> str:
    contents = [
        types.Content(role=m["role"], parts=[types.Part(text=m["content"])])
        for m in messages
    ]
    resp = client.models.generate_content(
        model=SETTINGS.model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.2,
            max_output_tokens=256,
        ),
    )
    return resp.text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

DEMO_ORDERS = [
    {"order_id": "ORD-001", "customer_id": "CUST-42", "amount": 29.99, "product": "Pro subscription"},
    {"order_id": "ORD-001", "customer_id": "CUST-42", "amount": 29.99, "product": "Pro subscription"},  # duplicate
    {"customer_id": "CUST-99", "amount": 9.99},         # malformed — missing order_id and product
    {"order_id": "ORD-002", "customer_id": "CUST-77", "amount": 12.50, "product": "Express shipping"},
]


def main() -> None:
    print(THICK)
    print("Agent Communication Patterns Exercise (§7)")
    print(f"Model: {SETTINGS.model}")
    print(THICK)
    print("\nPrimitives demonstrated:")
    print("  §7.3  Message schema     — typed payload + discriminator type")
    print("  §7.4  Idempotency        — duplicate detection via message ID")
    print("  §7.5  Dead letter queue  — unprocessable messages preserved for recovery")
    print("  §7.6  Backpressure       — bounded channels signal full consumers")
    print("  §7.7  Correlation IDs    — threaded through every derived message")
    print("  §7.8  Sync vs. async     — sync blocks caller; async returns immediately")

    # ── §7.3  Show message schema ─────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§7.3  Message Schema + §7.7  Correlation IDs")
    print(DIVIDER)
    sample = Message(type="order_received",
                     payload={"order_id": "ORD-001", "customer_id": "CUST-42", "amount": 29.99})
    print(f"  Message(type='{sample.type}', id='{sample.id}', corr='{sample.correlation_id}')")
    derived = sample.derive("order_validated", sample.payload)
    print(f"  Derived message:  type='{derived.type}', id='{derived.id}', corr='{derived.correlation_id}'")
    print(f"  → correlation_id preserved: {sample.correlation_id == derived.correlation_id}")

    # ── §7.8  Sync pipeline ───────────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§7.8  Sync Pipeline  (caller blocks until all stages complete)")
    print(DIVIDER)
    print("Processing 4 orders synchronously...\n")
    t0 = time.monotonic()
    sync_results = run_sync_pipeline(DEMO_ORDERS)
    sync_dur = (time.monotonic() - t0) * 1000
    print(f"\n  Sync pipeline complete: {len(sync_results)} order(s) fulfilled  ({sync_dur:.0f}ms)")
    print("  Caller was BLOCKED for the full duration.\n")

    # Recreate DLQ and idempotency for the async demo
    print(f"\n{DIVIDER}")
    print("§7.8  Async Pipeline  (caller returns immediately, workers continue)")
    print(DIVIDER)
    print("Firing 4 orders into async pipeline...\n")
    t1 = time.monotonic()
    corr_ids, async_results = run_async_pipeline(DEMO_ORDERS, channel_size=2)
    async_dur = (time.monotonic() - t1) * 1000
    print(f"\n  Async pipeline complete: {len(async_results)} order(s) fulfilled  ({async_dur:.0f}ms)")
    print(f"  Correlation IDs returned to caller: {corr_ids}")
    print("  Caller received IDs immediately and could do other work while workers ran.")

    # ── Show DLQ contents ─────────────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§7.5  Dead Letter Queue  (messages that could not be processed)")
    print(DIVIDER)
    # Re-run sync to show DLQ explicitly
    dlq = DeadLetterQueue()
    idempotency = IdempotencyStore()
    for order in DEMO_ORDERS:
        msg = Message(type="order_received", payload=order, correlation_id=new_correlation_id())
        _process_validate(msg, idempotency, dlq)

    print(f"  DLQ size: {dlq.size()} message(s)")
    for entry in dlq.list():
        print(f"  [DLQ] corr={entry['correlation_id']}  reason='{entry['reason']}'")
    print("\n  Teaching point: without the DLQ this message would be silently lost.")
    print("  A repair agent or human can inspect, fix, and replay from the DLQ.")

    print(f"\n{THICK}")
    print("Key takeaway: these primitives are framework-independent.")
    print("Message schema + correlation ID + idempotency + DLQ + backpressure")
    print("are the building blocks of any reliable multi-agent communication layer.")
    print(THICK)


if __name__ == "__main__":
    main()
