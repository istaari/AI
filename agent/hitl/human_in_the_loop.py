"""
Exercise — Human-in-the-Loop Patterns (§13)
============================================

Build a document drafting agent that demonstrates every HITL pattern from §13:
approval gates, confidence thresholds, correction loops, async state
checkpointing, and graceful degradation.

Run from the project root:
    python -m hitl.human_in_the_loop

Learning goals:
    - Gate irreversible actions behind explicit human approval (§13.1)
    - Use a confidence threshold to decide when to escalate vs. auto-proceed (§13.2)
    - Let humans annotate and correct — agent re-invokes from the correction (§13.3)
    - Checkpoint state so async approval doesn't block the thread (§13.4)
    - Degrade gracefully when the human is unavailable or rejects (§13.5)

Key insight: HITL is risk control, not weakness. The gate lives in control flow,
not in a prompt instruction the model could override.
"""

import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from shared.config import SETTINGS
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from shared.config import get_llm

DIVIDER = "─" * 65
THICK = "═" * 65

# Set to True to skip input() calls and simulate automatic timeout / rejection
DEMO_SIMULATE_TIMEOUT = False


# ─────────────────────────────────────────────────────────────────────────────
# ── §13.4  STATE CHECKPOINT
# Checkpointing allows the agent to suspend and resume without recomputing
# prior steps — essential for async approval workflows.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Define the Checkpoint dataclass and CheckpointStore.
# Checkpoint fields: id, step_index, completed_steps, pending_action, context,
#                    status ("pending"|"approved"|"rejected"), created_at.
# CheckpointStore: in-memory dict simulating a durable store.


@dataclass
class Checkpoint:
    """Serialisable snapshot of agent state at a pause point."""
    id: str
    step_index: int
    completed_steps: list[dict]
    pending_action: dict             # {"action": name, "args": dict, "risk": str}
    context: str                     # draft or output so far
    status: str                      # "pending" | "approved" | "rejected"
    created_at: str


class CheckpointStore:
    """
    In-memory dict simulating a durable state store (Redis / Postgres in prod).
    The store is what makes async HITL practical — the agent process can exit
    after saving, and a completely different process can resume it later.
    """

    def __init__(self) -> None:
        self._store: dict[str, Checkpoint] = {}

    def save(self, cp: Checkpoint) -> str:
        self._store[cp.id] = cp
        return cp.id

    def load(self, cp_id: str) -> Checkpoint:
        return self._store[cp_id]

    def update_decision(self, cp_id: str, decision: str) -> None:
        """decision: "approved" | "rejected" """
        self._store[cp_id].status = decision

    def pending(self) -> list[Checkpoint]:
        return [cp for cp in self._store.values() if cp.status == "pending"]


# ─────────────────────────────────────────────────────────────────────────────
# ── §13.2  CONFIDENCE THRESHOLD
# A secondary score decides whether to auto-approve a low-risk action or
# escalate to a human. Self-reported LLM scores are poorly calibrated —
# use a separate classifier in production.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement score_confidence.
# Ask the LLM to rate the draft quality 0-10.
# Normalise to 0.0-1.0 and return.
# Include a docstring warning that self-reported scores are a teaching proxy,
# not a production-ready confidence signal.


CONFIDENCE_SYSTEM = """Rate the quality of the given draft for its stated task.
Score 0-10 where:
  10 = perfectly addresses the task, well-structured, no issues
   0 = completely off-topic or incoherent
Return ONLY JSON: {"score": N, "reason": "one sentence"}"""


def score_confidence(draft: str, task: str) -> float:
    """
    Ask the LLM to self-score its draft quality 0-10; normalise to 0.0-1.0.

    WARNING: LLM self-reported confidence is poorly calibrated — models tend
    to overestimate quality. In production, use a separate fine-tuned
    classifier trained on human-annotated examples. Here it serves as a
    pedagogical proxy to demonstrate the threshold pattern.
    """
    raw = get_llm(temperature=0.1, max_tokens=128).invoke([
        SystemMessage(content=CONFIDENCE_SYSTEM),
        HumanMessage(content=f"Task: {task}\n\nDraft:\n{draft}"),
    ]).content.strip()
    cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip("` \n")
    try:
        parsed = json.loads(cleaned)
        score = float(parsed.get("score", 7))
        return min(1.0, max(0.0, score / 10.0))
    except (json.JSONDecodeError, ValueError):
        return 0.7  # neutral fallback


# ─────────────────────────────────────────────────────────────────────────────
# ── §13.1  APPROVAL GATE
# Hard control-flow pause before irreversible actions.
# The gate is in code, not in a prompt — the model cannot override it.
# ─────────────────────────────────────────────────────────────────────────────

HIGH_RISK_ACTIONS = {"publish", "delete", "send_email", "deploy"}


def requires_approval(action: str) -> bool:
    """Return True if the action is irreversible and needs a human gate."""
    return action in HIGH_RISK_ACTIONS


# TODO: Implement request_approval.
# 1. Save a checkpoint (simulates async: agent state is durable before we pause)
# 2. Print a clear approval banner
# 3. Prompt the human: y / n / edit
# 4. Update checkpoint status
# 5. Return (approved: bool, correction_text: str)


def request_approval(
    action: str,
    args: dict,
    context: str,
    store: CheckpointStore,
    step_index: int = 0,
    timeout_seconds: int = 30,
) -> tuple[bool, str]:
    """
    Synchronous approval gate using input().

    Returns (approved, correction_text).
    correction_text is non-empty only when the human typed 'edit'.

    §13.4: the checkpoint is saved BEFORE input() — simulating that in an async
    system the agent could exit here and a worker could resume later after the
    human responds via a UI notification.
    """
    cp = Checkpoint(
        id=secrets.token_hex(4),
        step_index=step_index,
        completed_steps=[],
        pending_action={"action": action, "args": args, "risk": "HIGH"},
        context=context[:200],
        status="pending",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    cp_id = store.save(cp)
    print(f"\n  [checkpoint saved: {cp_id}]  (in async HITL the agent would exit here)")

    print(f"\n  ╔{'═' * 58}╗")
    print(f"  ║  {'APPROVAL REQUIRED':<56}║")
    print(f"  ║  {'Action: ' + action:<56}║")
    preview = context[:50].replace('\n', ' ')
    print(f"  ║  {'Document: \"' + preview + '\"':<56}║")
    print(f"  ║  {'This action is IRREVERSIBLE.':<56}║")
    print(f"  ╚{'═' * 58}╝")

    if DEMO_SIMULATE_TIMEOUT:
        print(f"  [simulated] No response within {timeout_seconds}s → treating as timeout")
        store.update_decision(cp_id, "rejected")
        return False, ""

    try:
        response = input("  Approve? [y / n / edit]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        response = "n"
        print()

    if response == "y":
        store.update_decision(cp_id, "approved")
        return True, ""
    elif response.startswith("edit"):
        try:
            correction = input("  Enter correction: ").strip()
        except (KeyboardInterrupt, EOFError):
            correction = ""
        store.update_decision(cp_id, "rejected")
        return False, correction
    else:
        store.update_decision(cp_id, "rejected")
        return False, ""


# ─────────────────────────────────────────────────────────────────────────────
# ── §13.3  CORRECTION LOOP
# Human annotates the draft. The correction is injected into context —
# the agent re-invokes from the correction point, not from the start.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement apply_correction.
# Inject the human correction into the draft via an LLM revision call.
# Append it as a note — do NOT overwrite the draft entirely. The model sees
# the original + "Human correction: ..." and produces a revision.


CORRECTION_SYSTEM = """You are an editor. Given a draft document and a human
correction note, revise the draft to incorporate the correction.
Keep all content that is not addressed by the correction.
Return ONLY the revised document text — no JSON, no preamble."""


def apply_correction(draft: str, correction: str) -> str:
    """
    Revise the draft to incorporate the human correction.

    §13.3: the correction is appended to context (not used to overwrite).
    The model sees original + correction and produces a targeted revision.
    This preserves the draft's existing quality while applying the human's note.
    """
    prompt = f"Original draft:\n{draft}\n\nHuman correction: {correction}"
    return get_llm(temperature=0.2, max_tokens=600).invoke([
        SystemMessage(content=CORRECTION_SYSTEM),
        HumanMessage(content=prompt),
    ]).content.strip()


# ─────────────────────────────────────────────────────────────────────────────
# ── §13.5  GRACEFUL DEGRADATION
# When a human is unavailable or rejects, fall back safely.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement degrade_gracefully.
# Map each irreversible action to a safe fallback that does less harm:
#   "publish"    → save as draft
#   "delete"     → archive instead
#   "send_email" → queue for review
#   default      → skip


def degrade_gracefully(action: str, reason: str) -> dict:
    """
    Return a safe fallback result when a human gate fails or times out.
    The fallback does the LEAST harmful reversible alternative.
    """
    fallbacks = {
        "publish":    {"status": "saved_as_draft",      "message": f"Document saved as draft (not published). Reason: {reason}"},
        "delete":     {"status": "archived",             "message": f"Item archived instead of deleted. Reason: {reason}"},
        "send_email": {"status": "queued_for_review",   "message": f"Email queued for human review. Reason: {reason}"},
        "deploy":     {"status": "staged_for_review",   "message": f"Deployment staged but not applied. Reason: {reason}"},
    }
    return fallbacks.get(action, {"status": "skipped", "message": reason})


# ─────────────────────────────────────────────────────────────────────────────
# LLM HELPER
# ─────────────────────────────────────────────────────────────────────────────

def llm(system: str, messages: list[dict],
        max_tokens: int = 600, temperature: float = 0.3) -> str:
    """Single LLM call. messages = [{role, content}, ...]"""
    chat = get_llm(temperature=temperature, max_tokens=max_tokens)
    lc_msgs: list = [SystemMessage(content=system)] if system else []
    for m in messages:
        if m["role"] == "user":
            lc_msgs.append(HumanMessage(content=m["content"]))
        else:
            lc_msgs.append(AIMessage(content=m["content"]))
    return chat.invoke(lc_msgs).content.strip()


def parse_json(raw: str, fallback: dict) -> dict:
    cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip("` \n")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# ── DOCUMENT DRAFTING AGENT
# Orchestrates all 5 HITL patterns in a single workflow.
# ─────────────────────────────────────────────────────────────────────────────

DRAFTER_SYSTEM = """You are a document drafting assistant. Write a well-structured
short document (150-200 words) on the given topic.
Return ONLY JSON: {"draft": "...", "title": "..."}"""

EDITOR_SYSTEM = """You are an editor making minor improvements.
Given a draft, apply only low-risk edits: fix typos, improve readability,
improve sentence flow. Do NOT change facts or add new content.
Return ONLY JSON: {"edited_draft": "...", "changes_made": ["change 1", "change 2"]}"""


class DocumentDraftingAgent:
    """
    A document drafting agent that demonstrates all five §13 HITL patterns:

    Phase 1: Draft      (LLM generates initial document)
    Phase 2: Edit       (confidence threshold → auto-approve or gate)
    Phase 3: Publish    (always gated — irreversible action)
               ├─ Approved               → publish
               ├─ Edit requested         → correction loop → re-gate
               └─ Rejected / timeout     → graceful degradation
    """

    AUTO_APPROVE_THRESHOLD = 0.75

    def __init__(self, store: CheckpointStore):
        self.store = store

    def draft(self, topic: str) -> tuple[str, str]:
        """Phase 1: Generate the initial draft. Returns (title, draft_text)."""
        raw = llm(DRAFTER_SYSTEM, [{"role": "user", "content": f"Topic: {topic}"}])
        parsed = parse_json(raw, {"draft": raw, "title": "Draft"})
        return parsed.get("title", "Draft"), parsed.get("draft", raw)

    def edit(self, draft: str, task: str) -> tuple[str, float, list[str]]:
        """
        Phase 2: Apply low-risk editorial improvements.
        Returns (edited_draft, confidence_score, changes_made).
        The confidence score determines whether Phase 3 needs escalation.
        """
        raw = llm(EDITOR_SYSTEM, [{"role": "user", "content": f"Draft:\n{draft}"}])
        parsed = parse_json(raw, {"edited_draft": draft, "changes_made": []})
        edited = parsed.get("edited_draft", draft)
        changes = parsed.get("changes_made", [])
        confidence = score_confidence(edited, task)
        return edited, confidence, changes

    def publish(self, title: str, draft: str, step_index: int) -> dict:
        """
        Phase 3: Attempt to publish — always requires human approval.
        Handles: approve / correct+re-gate / reject+degrade.
        """
        MAX_CORRECTION_ROUNDS = 2
        current_draft = draft

        for attempt in range(1, MAX_CORRECTION_ROUNDS + 2):
            approved, correction = request_approval(
                action="publish",
                args={"title": title},
                context=current_draft,
                store=self.store,
                step_index=step_index,
            )

            if approved:
                return {"status": "published", "title": title,
                        "message": "Document published successfully."}

            if correction:
                # ── §13.3  Correction loop ────────────────────────────────
                print(f"\n  §13.3  Correction loop (attempt {attempt})")
                print(f"  Correction: \"{correction}\"")
                print("  Revising from correction point (not from scratch)...")
                current_draft = apply_correction(current_draft, correction)
                preview = current_draft[:80].replace('\n', ' ')
                print(f"  Revised preview: \"{preview}...\"")
                if attempt < MAX_CORRECTION_ROUNDS + 1:
                    print("  Re-presenting for approval...\n")
                    continue

            # No correction or exhausted rounds → degrade
            break

        # ── §13.5  Graceful degradation ───────────────────────────────────
        reason = "rejected by human" if not DEMO_SIMULATE_TIMEOUT else "timeout (no response)"
        return degrade_gracefully("publish", reason)

    def run(self, topic: str) -> None:
        """Full HITL workflow with decision pathway printed at each step."""
        print(f"\n{DIVIDER}")
        print(f"Topic: \"{topic}\"")
        print(DIVIDER)

        # Phase 1: Draft
        print(f"\n── Phase 1: Generate Initial Draft ────────────────────────────")
        title, draft = self.draft(topic)
        preview = draft[:80].replace('\n', ' ')
        print(f"  Title:  \"{title}\"")
        print(f"  Draft preview: \"{preview}...\"")

        # Phase 2: Edit with confidence threshold
        print(f"\n── §13.2  Confidence Threshold  →  Phase 2: Edit ───────────────")
        print("  Scoring confidence...")
        edited_draft, confidence, changes = self.edit(draft, topic)
        print(f"  Confidence score: {confidence:.2f}  (threshold: {self.AUTO_APPROVE_THRESHOLD})")

        if confidence >= self.AUTO_APPROVE_THRESHOLD:
            print(f"  Score ≥ threshold → auto-approve low-risk edit")
        else:
            print(f"  Score < threshold → escalating edit for human review")

        if changes:
            print(f"  Changes applied: {changes[:2]}")

        # Phase 3: Publish (always gated)
        print(f"\n── §13.1  Approval Gate  →  Phase 3: Publish ──────────────────")
        result = self.publish(title, edited_draft, step_index=3)

        print(f"\n── Result ──────────────────────────────────────────────────────")
        print(f"  Status:  {result['status']}")
        print(f"  Message: {result['message']}")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

DEMO_TOPICS = [
    "The benefits of remote work for engineering teams",
    "Why code reviews matter in software development",
]


def main() -> None:
    print(THICK)
    print("Human-in-the-Loop Exercise (§13)")
    print(f"Model: {SETTINGS.model}")
    if DEMO_SIMULATE_TIMEOUT:
        print("Mode: DEMO_SIMULATE_TIMEOUT=True  (auto-rejects without input())")
    print(THICK)

    print(f"\n{'Patterns demonstrated':}")
    print("  §13.1 Approval gate         — hard pause before irreversible actions")
    print("  §13.2 Confidence threshold  — auto-approve if score ≥ 0.75, else escalate")
    print("  §13.3 Correction loop       — human edits → agent revises → re-gate")
    print("  §13.4 State checkpointing   — checkpoint saved before every input() call")
    print("  §13.5 Graceful degradation  — safe fallback when rejected/timeout")

    print(f"\nAvailable demo topics:")
    for i, t in enumerate(DEMO_TOPICS, 1):
        print(f"  {i}. {t}")
    print()

    if DEMO_SIMULATE_TIMEOUT:
        topic = DEMO_TOPICS[0]
        print(f"Using topic 1 (timeout simulation mode): \"{topic}\"")
    else:
        choice = input("Enter a topic (or press Enter for topic 1, '2' for topic 2): ").strip()
        if choice == "2":
            topic = DEMO_TOPICS[1]
        elif choice and not choice.isdigit():
            topic = choice    # user entered a custom topic
        else:
            topic = DEMO_TOPICS[0]

    store = CheckpointStore()
    agent = DocumentDraftingAgent(store)
    agent.run(topic)

    # Show checkpoint audit trail
    pending = store.pending()
    all_checkpoints = list(store._store.values())
    if all_checkpoints:
        print(f"\n{DIVIDER}")
        print(f"§13.4  Checkpoint Audit Trail  ({len(all_checkpoints)} checkpoint(s))")
        print(DIVIDER)
        for cp in all_checkpoints:
            print(f"  [{cp.id}] step={cp.step_index}  action={cp.pending_action['action']}"
                  f"  status={cp.status}  created={cp.created_at[:19]}")
        if pending:
            print(f"\n  {len(pending)} checkpoint(s) still pending — an async worker could resume these.")

    print(f"\n{THICK}")
    print("Key takeaway: the gate lives in control flow, not in a prompt.")
    print("The model cannot override an approval gate — it is a code-level pause.")
    print(THICK)


if __name__ == "__main__":
    main()
