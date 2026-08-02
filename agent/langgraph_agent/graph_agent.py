"""
Exercise — LangGraph Agent (§16)
==================================

Build a customer support router using LangGraph's StateGraph — comparing
it with the hand-coded SupervisorAgent from §9 to see what the framework
buys you.

Run from the project root:
    python -m langgraph_agent.graph_agent

Learning goals:
    - Define typed state that flows through every graph node (TypedDict)
    - Write nodes as plain Python functions that return partial state updates
    - Route between nodes with conditional edge functions
    - Attach MemorySaver for persistent multi-turn memory in one line
    - Stream node updates as they fire with .stream(stream_mode="updates")
    - Compare LangGraph vs hand-coded orchestration (§9 SupervisorAgent)

Key insight: LangGraph is not magic — it is typed control-flow plumbing.
The intelligence lives in your node functions (LLM prompts). The graph handles
routing, state merging, and checkpointing.

New dependency: langgraph>=0.2.0  (pip install langgraph)
"""

from __future__ import annotations

import json
import operator
import re
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from shared.config import SETTINGS, get_llm

DIVIDER = "─" * 65
THICK = "═" * 65

# ─────────────────────────────────────────────────────────────────────────────
# Module-level LangChain chat model — set in main() before any graph.invoke() call.
#
# Teaching point: LangGraph nodes are plain functions with signature
# (state: SupportState) -> dict. They cannot accept extra constructor args.
# The standard pattern for injecting dependencies is a module-level variable
# or a closure. We use a module-level variable for maximum clarity.
# ─────────────────────────────────────────────────────────────────────────────

_llm: BaseChatModel | None = None


# ─────────────────────────────────────────────────────────────────────────────
# ── TYPED STATE SCHEMA
# SupportState flows through every node. LangGraph merges the returned dict
# into the existing state — it does not replace the whole state.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Define SupportState as a TypedDict.
# messages   — append-only via operator.add reducer (Annotated[list[str], operator.add])
# intent     — plain overwrite: "billing" | "technical" | "general" | ""
# response   — plain overwrite: the specialist's draft response
# qa_passed  — plain overwrite: whether QA approved the response
# turn_count — plain overwrite: incremented by classify_intent each turn


class SupportState(TypedDict):
    """
    Typed state that flows through every node in the graph.

    The `Annotated[list[str], operator.add]` reducer on `messages` means
    LangGraph APPENDS to the list rather than replacing it. All other fields
    use the default (plain overwrite) reducer.

    Teaching point: state is just a TypedDict. Reducers are how you control
    whether a field accumulates (append) or overwrites (last-write-wins).
    """
    messages:   Annotated[list[str], operator.add]
    intent:     str
    response:   str
    qa_passed:  bool
    turn_count: int


# ─────────────────────────────────────────────────────────────────────────────
# LLM HELPER
# ─────────────────────────────────────────────────────────────────────────────

def llm(system: str, messages: list[dict], max_tokens: int = 512, temperature: float = 0.3) -> str:
    """Single LLM call using the module-level _llm model."""
    assert _llm is not None, "_llm must be set before calling llm()"
    lc_msgs: list = [SystemMessage(content=system)] if system else []
    for m in messages:
        if m["role"] == "user":
            lc_msgs.append(HumanMessage(content=m["content"]))
        else:
            lc_msgs.append(AIMessage(content=m["content"]))
    return _llm.invoke(lc_msgs).content.strip()


def parse_json(raw: str, fallback: dict) -> dict:
    cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip("` \n")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# ── NODES
# Each node receives the full SupportState and returns a PARTIAL dict.
# LangGraph merges the returned dict into the state using each field's reducer.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement the five nodes.
# Each node returns only the keys it modifies — not the full state.
# classify_intent: LLM classifies the last user message → sets intent, turn_count
# handle_billing / handle_technical / handle_general: specialist LLM → sets response
# qa_check: LLM QA review → sets qa_passed, appends response to messages


CLASSIFY_SYSTEM = """\
Classify the user's support query into exactly one category:
  billing    — payment, invoice, charge, subscription, refund
  technical  — API, error, bug, integration, rate limit, feature
  general    — anything else (info requests, feedback, account)

Return ONLY JSON: {"intent": "billing" | "technical" | "general", "reasoning": "one sentence"}"""

BILLING_SYSTEM = """\
You are a billing specialist for AcmeCorp. Answer the customer's billing query
concisely and helpfully. Always acknowledge the issue and give a concrete next step.
Maximum 3 sentences."""

TECHNICAL_SYSTEM = """\
You are a technical support specialist for AcmeCorp. Answer the customer's technical
query with specific details (error codes, limits, workarounds). Maximum 3 sentences."""

GENERAL_SYSTEM = """\
You are a general support agent for AcmeCorp. Answer the customer's query helpfully
and direct them to the right resource if needed. Maximum 2 sentences."""

QA_SYSTEM = """\
You are a QA reviewer. Evaluate whether the support response is helpful and on-topic.
Return ONLY JSON:
{"passed": true | false, "reason": "one sentence", "improved": "<response if not passed, else empty string>"}
Pass if: response directly addresses the query, is polite, and gives concrete information."""


def classify_intent(state: SupportState) -> dict:
    """
    Node 1: classify the last user message as billing / technical / general.

    Returns only intent and turn_count — not the full state.
    Teaching point: returning a partial dict is idiomatic LangGraph.
    """
    last_message = state["messages"][-1] if state["messages"] else ""
    raw = llm(CLASSIFY_SYSTEM, [{"role": "user", "content": last_message}], max_tokens=128)
    parsed = parse_json(raw, {"intent": "general", "reasoning": ""})
    intent = parsed.get("intent", "general")
    if intent not in ("billing", "technical", "general"):
        intent = "general"
    return {"intent": intent, "turn_count": state["turn_count"] + 1}


def route_to_specialist(state: SupportState) -> str:
    """
    Conditional edge function — NOT a node.
    Returns the name of the next node based on state["intent"].

    Teaching point: conditional edges are plain Python functions returning a
    string that must match one of the keys in the routing dict passed to
    add_conditional_edges(). This is where control-flow logic lives in LangGraph.
    """
    intent = state.get("intent", "general")
    return {
        "billing":   "handle_billing",
        "technical": "handle_technical",
        "general":   "handle_general",
    }.get(intent, "handle_general")


def handle_billing(state: SupportState) -> dict:
    """Node 2a: billing specialist handler."""
    query = state["messages"][-1] if state["messages"] else ""
    response = llm(BILLING_SYSTEM, [{"role": "user", "content": query}])
    return {"response": response}


def handle_technical(state: SupportState) -> dict:
    """Node 2b: technical specialist handler."""
    query = state["messages"][-1] if state["messages"] else ""
    response = llm(TECHNICAL_SYSTEM, [{"role": "user", "content": query}])
    return {"response": response}


def handle_general(state: SupportState) -> dict:
    """Node 2c: general support handler."""
    query = state["messages"][-1] if state["messages"] else ""
    response = llm(GENERAL_SYSTEM, [{"role": "user", "content": query}])
    return {"response": response}


def qa_check(state: SupportState) -> dict:
    """
    Node 3: QA review of the specialist's response.

    Teaching point: QA as a graph node (not post-processing outside the graph)
    means it is checkpointed, visible in the graph topology, and can be
    interrupted by a HITL gate just like any other node.
    """
    query = state["messages"][-1] if state["messages"] else ""
    prompt = f"Query: {query}\n\nResponse to evaluate: {state.get('response', '')}"
    raw = llm(QA_SYSTEM, [{"role": "user", "content": prompt}], max_tokens=256)
    parsed = parse_json(raw, {"passed": True, "reason": "", "improved": ""})
    passed = bool(parsed.get("passed", True))
    improved = parsed.get("improved", "")
    final_response = improved if (not passed and improved) else state.get("response", "")
    return {
        "qa_passed": passed,
        "response": final_response,
        "messages": [final_response],   # operator.add appends to messages list
    }


# ─────────────────────────────────────────────────────────────────────────────
# ── BUILD THE GRAPH
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement build_graph.
# Register nodes, add edges, add conditional edge from classify_intent,
# compile with optional checkpointer.
# Topology:
#   START → classify_intent →(conditional)→ [handle_billing | handle_technical | handle_general]
#                                              ↓
#                                           qa_check → END


def build_graph(checkpointer: MemorySaver | None = None):
    """
    Construct and compile the customer support StateGraph.

    Teaching point: graph.compile() is where the checkpointer is attached.
    Checkpointers are NOT part of graph definition — they are runtime config.
    This keeps topology separate from persistence concerns.
    """
    graph = StateGraph(SupportState)

    # Register nodes
    graph.add_node("classify_intent",  classify_intent)
    graph.add_node("handle_billing",   handle_billing)
    graph.add_node("handle_technical", handle_technical)
    graph.add_node("handle_general",   handle_general)
    graph.add_node("qa_check",         qa_check)

    # Edges
    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        route_to_specialist,
        {
            "handle_billing":   "handle_billing",
            "handle_technical": "handle_technical",
            "handle_general":   "handle_general",
        },
    )
    graph.add_edge("handle_billing",   "qa_check")
    graph.add_edge("handle_technical", "qa_check")
    graph.add_edge("handle_general",   "qa_check")
    graph.add_edge("qa_check",         END)

    return graph.compile(checkpointer=checkpointer)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

DEMO_QUERIES = [
    "Why was I charged twice for my Pro subscription this month?",
    "The API keeps returning 429 errors. What is the rate limit for Pro tier?",
]


def main() -> None:
    global _llm
    print(THICK)
    print("LangGraph Agent Exercise")
    print(f"Model: {SETTINGS.model}")
    print(THICK)

    _llm = get_llm(temperature=0.3)

    # ── Print graph topology ──────────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("Graph Topology")
    print(DIVIDER)
    print("Nodes:")
    print("  classify_intent   — LLM: classify query as billing/technical/general")
    print("  handle_billing    — LLM: billing specialist response")
    print("  handle_technical  — LLM: technical specialist response")
    print("  handle_general    — LLM: general support response")
    print("  qa_check          — LLM: QA review before returning response")
    print("\nEdges:")
    print("  START → classify_intent")
    print("  classify_intent →(conditional)→ [handle_billing | handle_technical | handle_general]")
    print("  [specialist] → qa_check → END")

    # ── Demo 1: .invoke()  (turn 1) ───────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("Demo 1: .invoke()  (billing query)")
    print(DIVIDER)

    memory = MemorySaver()
    app = build_graph(checkpointer=memory)
    thread_config = {"configurable": {"thread_id": "demo-thread-1"}}

    query1 = DEMO_QUERIES[0]
    print(f"User: \"{query1}\"\n")

    initial_state: SupportState = {
        "messages":   [query1],
        "intent":     "",
        "response":   "",
        "qa_passed":  False,
        "turn_count": 0,
    }
    result1 = app.invoke(initial_state, config=thread_config)

    print(f"  → classify_intent:  intent={result1['intent']}")
    print(f"  → specialist:       drafting response...")
    print(f"  → qa_check:         qa_passed={result1['qa_passed']}")
    print(f"\nResponse: \"{result1['response'][:200]}\"")
    print(f"\nState after turn 1:")
    print(f"  intent: {result1['intent']}  |  qa_passed: {result1['qa_passed']}"
          f"  |  turn_count: {result1['turn_count']}")
    print(f"  messages: {len(result1['messages'])} entries  (user + agent)")

    # ── Demo 2: .stream(stream_mode="updates")  (turn 2) ─────────────────────
    print(f"\n{DIVIDER}")
    print('Demo 2: .stream(stream_mode="updates")  (technical query)')
    print(DIVIDER)
    print("Streaming shows each node's state delta as it fires.\n")

    query2 = DEMO_QUERIES[1]
    print(f"User: \"{query2}\"\n")

    state2: SupportState = {
        "messages":   [query2],
        "intent":     "",
        "response":   "",
        "qa_passed":  False,
        "turn_count": result1["turn_count"],
    }
    for chunk in app.stream(state2, config=thread_config, stream_mode="updates"):
        for node_name, delta in chunk.items():
            # Print only the interesting keys in the delta
            keys_shown = {k: v for k, v in delta.items()
                          if k not in ("messages",) or len(delta) == 1}
            preview = json.dumps(keys_shown)[:100]
            print(f"  stream chunk → {node_name:<18} {preview}")

    final2 = app.get_state(thread_config).values
    print(f"\nResponse: \"{final2.get('response', '')[:200]}\"")

    # ── Demo 3: Checkpoint history ────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("Checkpointing — same thread_id remembers state across invocations")
    print(DIVIDER)
    history = list(app.get_state_history(thread_config))
    print(f"  State snapshots for thread 'demo-thread-1':  {len(history)} checkpoint(s)")
    for i, snap in enumerate(reversed(history[:4])):
        vals = snap.values
        tc = vals.get("turn_count", 0)
        intent = vals.get("intent", "")
        n_msgs = len(vals.get("messages", []))
        print(f"  checkpoint {i}:  intent='{intent}'  turn_count={tc}  messages={n_msgs}")
    print("\n  Teaching point: MemorySaver stores a snapshot after every node.")
    print("  Use get_state_history() to replay, diff, or fork from any checkpoint.")

    # ── Comparison table ──────────────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("Comparison: LangGraph vs hand-coded SupervisorAgent (§9)")
    print(DIVIDER)
    rows = [
        ("Routing logic",    "~50 lines in _route() + _run_llm_driven()", "route_to_specialist() — 6 lines"),
        ("Checkpointing",    "Build yourself (see hitl/human_in_the_loop.py)", "MemorySaver() — 1 line"),
        ("State schema",     "Implicit dict — any key at any time",       "SupportState TypedDict — validated"),
        ("Graph topology",   "Visible only by reading the code",           "build_graph() — readable as data"),
        ("Streaming",        "Must implement manually",                    ".stream(stream_mode='updates')"),
    ]
    print(f"  {'Aspect':<22}  {'SupervisorAgent (§9)':<44}  {'LangGraph'}")
    print(f"  {'─'*22}  {'─'*44}  {'─'*34}")
    for aspect, sup, lg in rows:
        print(f"  {aspect:<22}  {sup:<44}  {lg}")
    print("\n  Same capability — LangGraph removes the plumbing boilerplate.")
    print("  The intelligence still lives in the node prompt functions.")

    print(f"\n{THICK}")
    print("Key takeaway: LangGraph is typed control-flow plumbing.")
    print("Nodes = your LLM prompts. Edges = your routing logic.")
    print("Checkpointing and streaming come for free once the graph is compiled.")
    print(THICK)


if __name__ == "__main__":
    main()
