"""
Exercise — Multi-Agent Orchestration Architecture (§9)
=======================================================

Build a Supervisor-pattern multi-agent system from scratch using only the
Gemini SDK and Python's stdlib. No frameworks, no external orchestrators.

Run from the project root:
    python -m multi_agent.orchestrator

Learning goals:
    - Define typed agent contracts (input schema, output schema, failure modes) (§9.2)
    - Implement a Supervisor that routes tasks to specialist agents (§9.4)
    - Compare deterministic routing (fixed order) vs LLM-driven routing (§9.1)
    - Compress handoff state instead of passing full transcripts (§9.5)
    - Handle failure propagation gracefully (abort/degrade/retry) (§9.6)
    - Fan out tasks in parallel with ThreadPoolExecutor (§9.3)

Key insight: state machines are boring but auditable. LLM-driven routing is
flexible but fragile. Production systems use both.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from shared.config import SETTINGS
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from shared.config import get_llm

DIVIDER = "─" * 65
THICK = "═" * 65


# ─────────────────────────────────────────────────────────────────────────────
# ── §9.2  AGENT CONTRACTS
# Each agent declares what it accepts (AgentInput) and what it returns
# (AgentOutput). This is the same discipline as microservice API contracts.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Define AgentInput and AgentOutput dataclasses.
# AgentInput:  task (what to do) + context (compressed state from prior agents)
# AgentOutput: agent_name, result, facts (key bullets), status, error


@dataclass
class AgentInput:
    """Typed input contract for every agent."""
    task: str
    context: dict = field(default_factory=dict)   # compressed handoff state


@dataclass
class AgentOutput:
    """Typed output contract for every agent."""
    agent_name: str
    result: str                          # the main content produced
    facts: list[str] = field(default_factory=list)   # extracted key facts
    status: str = "success"              # "success" | "failure" | "degraded"
    error: Optional[str] = None          # populated only on failure


# ─────────────────────────────────────────────────────────────────────────────
# LLM HELPER
# ─────────────────────────────────────────────────────────────────────────────

def llm(system: str, messages: list[dict], max_tokens: int = 1024, temperature: float = 0.3) -> str:
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
    """Strip markdown fences and parse JSON; return fallback on failure."""
    cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip("` \n")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# ── SPECIALIST AGENTS
# Each agent does one thing well (Unix philosophy).
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement the four specialist agents.
# Each agent:
#   1. Has a SYSTEM prompt that defines its role
#   2. Accepts AgentInput and returns AgentOutput
#   3. Uses the context dict (compressed handoff) to build on prior work


class BaseAgent:
    """Shared structure for all specialist agents."""

    SYSTEM = ""   # override in subclasses

    def __init__(self, name: str):
        self.name = name

    def run(self, inp: AgentInput) -> AgentOutput:
        raise NotImplementedError


class ResearchAgent(BaseAgent):
    """Finds and summarises relevant facts about a topic."""

    SYSTEM = """You are a research agent. Given a topic and task, produce 4-5
factual bullet points with concrete details (numbers, dates, specifics).
Return ONLY JSON:
{"facts": ["bullet 1", "bullet 2", ...], "summary": "one-sentence overview"}"""

    def run(self, inp: AgentInput) -> AgentOutput:
        prompt = f"Task: {inp.task}\nTopic context: {json.dumps(inp.context)}"
        raw = llm(self.SYSTEM, [{"role": "user", "content": prompt}])
        parsed = parse_json(raw, {"facts": [], "summary": raw})
        facts = parsed.get("facts", [])
        summary = parsed.get("summary", "")
        return AgentOutput(
            agent_name=self.name,
            result=summary,
            facts=facts,
            status="success",
        )


class WriterAgent(BaseAgent):
    """Takes research facts and writes a polished short document."""

    SYSTEM = """You are a writer agent. Given research facts and a task, write a
well-structured short document (150-200 words). Use the provided facts —
do not invent new ones.
Return ONLY JSON:
{"draft": "full document text here", "title": "document title", "word_count": N}"""

    def run(self, inp: AgentInput) -> AgentOutput:
        facts = inp.context.get("facts", [])
        facts_str = "\n".join(f"- {f}" for f in facts) if facts else "No prior research available."
        prompt = f"Task: {inp.task}\n\nResearch facts:\n{facts_str}"
        raw = llm(self.SYSTEM, [{"role": "user", "content": prompt}])
        parsed = parse_json(raw, {"draft": raw, "title": "Draft", "word_count": 0})
        draft = parsed.get("draft", raw)
        title = parsed.get("title", "Draft")
        word_count = parsed.get("word_count", len(draft.split()))
        return AgentOutput(
            agent_name=self.name,
            result=draft,
            facts=[f"title: {title}", f"word_count: {word_count}"],
            status="success",
        )


class FactCheckerAgent(BaseAgent):
    """Reviews a draft against the research facts; flags unsupported claims."""

    SYSTEM = """You are a fact-checker. Given a draft and research facts, identify
any claim in the draft NOT directly supported by the provided facts.
Return ONLY JSON:
{"verdict": "PASS" or "FAIL", "issues": ["issue 1", ...], "revised_draft": "corrected draft or original if PASS"}"""

    def run(self, inp: AgentInput) -> AgentOutput:
        draft = inp.context.get("draft", inp.task)
        facts = inp.context.get("facts", [])
        facts_str = "\n".join(f"- {f}" for f in facts) if facts else "No research facts provided."
        prompt = f"Draft to check:\n{draft}\n\nReference facts:\n{facts_str}"
        raw = llm(self.SYSTEM, [{"role": "user", "content": prompt}])
        parsed = parse_json(raw, {"verdict": "PASS", "issues": [], "revised_draft": draft})
        verdict = parsed.get("verdict", "PASS")
        issues = parsed.get("issues", [])
        revised = parsed.get("revised_draft", draft)
        return AgentOutput(
            agent_name=self.name,
            result=revised,
            facts=[f"verdict: {verdict}", f"issues_found: {len(issues)}"] + issues,
            status="success",
        )


class ReviewerAgent(BaseAgent):
    """Final quality review: completeness, clarity, and actionability."""

    SYSTEM = """You are a quality reviewer. Score the draft on:
- completeness (0-10): does it fully address the original task?
- clarity (0-10): is it easy to read and understand?
Return ONLY JSON:
{"completeness": N, "clarity": N, "verdict": "PASS" or "NEEDS_WORK",
 "notes": "brief feedback", "final_draft": "polished final version"}"""

    def run(self, inp: AgentInput) -> AgentOutput:
        draft = inp.context.get("draft", inp.context.get("result", inp.task))
        prompt = f"Original task: {inp.task}\n\nDraft to review:\n{draft}"
        raw = llm(self.SYSTEM, [{"role": "user", "content": prompt}])
        parsed = parse_json(raw, {
            "completeness": 7, "clarity": 7,
            "verdict": "PASS", "notes": "", "final_draft": draft,
        })
        final = parsed.get("final_draft", draft)
        completeness = parsed.get("completeness", 0)
        clarity = parsed.get("clarity", 0)
        verdict = parsed.get("verdict", "PASS")
        notes = parsed.get("notes", "")
        return AgentOutput(
            agent_name=self.name,
            result=final,
            facts=[
                f"completeness: {completeness}/10",
                f"clarity: {clarity}/10",
                f"verdict: {verdict}",
                f"notes: {notes}",
            ],
            status="success",
        )


# ─────────────────────────────────────────────────────────────────────────────
# ── §9.5  CONTEXT COMPRESSION / HANDOFF STATE
# Only forward the essential state — not the full transcript.
# This is the 90-token-vs-1800-token lesson.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement compress_handoff.
# Extract only: completed_by, all facts combined, status_chain, and latest draft.
# The result is what the NEXT agent receives as context — not the full history.


def compress_handoff(outputs: list[AgentOutput]) -> dict:
    """
    Compress a list of agent outputs into a minimal handoff state.
    Only facts + statuses are forwarded — NOT the full text of prior outputs.

    Teaching point: passing full output chains grows O(n) in tokens and
    hits context limits. The compressed handoff stays roughly constant size.
    """
    all_facts: list[str] = []
    status_chain: list[str] = []
    latest_draft: str = ""

    for out in outputs:
        all_facts.extend(out.facts)
        status_chain.append(f"{out.agent_name}:{out.status}")
        # Carry the most recent substantial result as the "draft"
        if out.result and len(out.result) > 50:
            latest_draft = out.result

    return {
        "completed_by": [o.agent_name for o in outputs],
        "facts":        all_facts,
        "status_chain": status_chain,
        "draft":        latest_draft,
    }


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 characters."""
    return len(text) // 4


# ─────────────────────────────────────────────────────────────────────────────
# ── §9.3  PARALLEL FAN-OUT DEMO
# Show how independent sub-tasks can run concurrently with ThreadPoolExecutor.
# ─────────────────────────────────────────────────────────────────────────────

def demo_parallel_fanout(goal: str) -> None:
    """
    Demonstrate §9.3: fan out two independent research subtasks in parallel,
    then collect results. Uses only stdlib concurrent.futures.
    """
    print(f"\n{DIVIDER}")
    print("§9.3  Parallel Fan-out  (two research agents running concurrently)")
    print(DIVIDER)

    subtasks = [
        f"Research current market size and growth rate for: {goal}",
        f"Research key players and competitive landscape for: {goal}",
    ]

    researcher_a = ResearchAgent("researcher_A")
    researcher_b = ResearchAgent("researcher_B")
    agents_tasks = [
        (researcher_a, AgentInput(task=subtasks[0])),
        (researcher_b, AgentInput(task=subtasks[1])),
    ]

    results: list[AgentOutput] = []
    print(f"Dispatching {len(agents_tasks)} agents in parallel...")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(agent.run, inp): agent.name for agent, inp in agents_tasks}
        for future in as_completed(futures):
            out = future.result()
            results.append(out)
            print(f"  [{out.agent_name}] completed — {len(out.facts)} fact(s)")

    all_facts = [f for out in results for f in out.facts]
    print(f"Parallel results merged: {len(all_facts)} facts from {len(results)} agents")


# ─────────────────────────────────────────────────────────────────────────────
# ── §9.1 & §9.4  SUPERVISOR AGENT
# Coordinator that routes tasks and assembles the final result.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement SupervisorAgent.
# The supervisor must:
#   1. Route each step to the right specialist (via LLM or fixed order)
#   2. Compress and pass handoff state between agents
#   3. Handle failures with retry + graceful degradation (§9.6)


AGENT_DESCRIPTIONS = {
    "researcher":    "Finds and summarises key facts about a topic. Use first.",
    "writer":        "Writes a polished draft from research facts. Use after researcher.",
    "fact_checker":  "Verifies the draft against research facts. Use after writer.",
    "reviewer":      "Final quality review of the draft. Use last.",
}

ROUTER_SYSTEM = """You are a routing supervisor. Given a goal, the current step,
and what agents have already completed, decide which agent to run next.

Available agents:
{agent_descriptions}

Already completed: {completed}
Current step number: {step}

Return ONLY JSON:
{{"next_agent": "<agent_name>", "reasoning": "one sentence"}}

Stop routing (return {{"next_agent": "DONE", "reasoning": "..."}}) when:
- All 4 agents have run, OR
- The goal is fully achieved"""


class SupervisorAgent:
    """
    Coordinator that routes tasks to specialist agents and assembles results.
    Supports both deterministic (fixed order) and LLM-driven routing.
    """

    AGENT_CLASSES = {
        "researcher":   ResearchAgent,
        "writer":       WriterAgent,
        "fact_checker": FactCheckerAgent,
        "reviewer":     ReviewerAgent,
    }

    def __init__(self):
        self.agents = {
            name: cls(name)
            for name, cls in self.AGENT_CLASSES.items()
        }

    # ── §9.6  Failure propagation ─────────────────────────────────────────────

    def _execute_with_fallback(
        self, agent: BaseAgent, inp: AgentInput, retries: int = 1
    ) -> AgentOutput:
        """
        Try to run an agent. On failure:
        - Retry up to `retries` times
        - After exhausting retries, return a degraded output so the pipeline continues
        """
        for attempt in range(retries + 1):
            try:
                return agent.run(inp)
            except Exception as e:
                if attempt < retries:
                    print(f"  [supervisor] {agent.name} failed (attempt {attempt+1}), retrying...")
                else:
                    print(f"  [supervisor] {agent.name} failed after {retries+1} attempt(s) → degraded")
                    return AgentOutput(
                        agent_name=agent.name,
                        result="",
                        facts=[f"DEGRADED: {str(e)[:80]}"],
                        status="degraded",
                        error=str(e),
                    )
        # unreachable but satisfies type checker
        return AgentOutput(agent_name=agent.name, result="", status="degraded")

    # ── §9.1  LLM-driven routing ──────────────────────────────────────────────

    def _route(self, goal: str, step: int, completed: list[str]) -> str:
        """Ask the LLM which agent should run next."""
        descriptions = "\n".join(
            f"  - {name}: {desc}" for name, desc in AGENT_DESCRIPTIONS.items()
        )
        system = ROUTER_SYSTEM.format(
            agent_descriptions=descriptions,
            completed=", ".join(completed) if completed else "none",
            step=step,
        )
        raw = llm(system, [{"role": "user", "content": f"Goal: {goal}"}], max_tokens=256)
        parsed = parse_json(raw, {"next_agent": "DONE", "reasoning": "parse error"})
        return parsed.get("next_agent", "DONE"), parsed.get("reasoning", "")

    # ── §9.1  Deterministic routing ───────────────────────────────────────────

    def _run_deterministic(self, goal: str) -> str:
        """Fixed sequence: researcher → writer → fact_checker → reviewer."""
        print(f"\n  Routing: DETERMINISTIC  (fixed order)")
        sequence = ["researcher", "writer", "fact_checker", "reviewer"]
        outputs: list[AgentOutput] = []

        for i, name in enumerate(sequence, 1):
            agent = self.agents[name]
            ctx = compress_handoff(outputs)
            inp = AgentInput(task=goal, context=ctx)
            print(f"  [step {i}/4] Running: {name}")
            out = self._execute_with_fallback(agent, inp)
            outputs.append(out)
            summary = out.facts[0] if out.facts else out.result[:60]
            print(f"           → status: {out.status} | {summary}")

        return outputs[-1].result

    # ── §9.1  LLM-driven routing ──────────────────────────────────────────────

    def _run_llm_driven(self, goal: str) -> str:
        """The supervisor LLM decides which agent to run at each step."""
        print(f"\n  Routing: LLM-DRIVEN  (supervisor decides)")
        outputs: list[AgentOutput] = []
        completed: list[str] = []

        for step in range(1, 6):   # safety limit
            next_agent, reasoning = self._route(goal, step, completed)
            if next_agent == "DONE" or next_agent not in self.agents:
                print(f"  [supervisor] Step {step}: DONE  ({reasoning})")
                break

            print(f"  [supervisor] Step {step}: route → {next_agent}  ({reasoning})")
            agent = self.agents[next_agent]
            ctx = compress_handoff(outputs)
            inp = AgentInput(task=goal, context=ctx)
            out = self._execute_with_fallback(agent, inp)
            outputs.append(out)
            completed.append(next_agent)
            summary = out.facts[0] if out.facts else out.result[:60]
            print(f"  [{next_agent}] status: {out.status} | {summary}")

        return outputs[-1].result if outputs else "No output produced."

    def run(self, goal: str, routing: str = "deterministic") -> str:
        """
        Run the full multi-agent pipeline.
        routing: "deterministic" (fixed order) or "llm" (supervisor decides)
        """
        if routing == "llm":
            return self._run_llm_driven(goal)
        return self._run_deterministic(goal)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

DEMO_GOAL = "Write a short market overview of electric vehicle (EV) charging infrastructure."


def main() -> None:
    print(THICK)
    print("Multi-Agent Orchestration Exercise (§9)")
    print(f"Model: {SETTINGS.model}")
    print(THICK)

    # ── §9.2  Show agent contracts ────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§9.2  Agent Contracts  (typed input/output + failure modes)")
    print(DIVIDER)
    print("Registered agents:")
    for name, desc in AGENT_DESCRIPTIONS.items():
        print(f"  {name:<14} : {desc}")
    print("\nContract types:")
    print("  Input:  AgentInput(task: str, context: dict)")
    print("  Output: AgentOutput(agent_name, result, facts, status, error)")
    print("  Status: 'success' | 'failure' | 'degraded'")

    supervisor = SupervisorAgent()

    # ── §9.1  Deterministic routing ───────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print(f"§9.1  Deterministic Routing  →  Goal: \"{DEMO_GOAL}\"")
    print(DIVIDER)
    det_result = supervisor.run(DEMO_GOAL, routing="deterministic")

    # ── §9.5  Handoff compression demo ────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§9.5  Handoff Context Compression")
    print(DIVIDER)
    # Simulate two outputs to show the compression effect
    mock_outputs = [
        AgentOutput("researcher", det_result[:300], ["fact A", "fact B", "fact C"], "success"),
        AgentOutput("writer", det_result, ["title: EV Market Overview", "word_count: 175"], "success"),
    ]
    compressed = compress_handoff(mock_outputs)
    full_size = _estimate_tokens(det_result * 2)
    compressed_size = _estimate_tokens(json.dumps(compressed))
    print(f"Full transcript (2 agents):  ~{full_size} tokens")
    print(f"Compressed handoff state:    ~{compressed_size} tokens")
    print(f"Reduction:                   ~{100 - int(100 * compressed_size / max(full_size, 1))}%")
    print(f"Compressed state: {json.dumps(compressed, indent=2)[:200]}...")

    # ── §9.1  LLM-driven routing ──────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print(f"§9.1  LLM-Driven Routing  (same goal, supervisor decides order)")
    print(DIVIDER)
    llm_result = supervisor.run(DEMO_GOAL, routing="llm")

    # ── §9.3  Parallel fan-out ────────────────────────────────────────────────
    demo_parallel_fanout(DEMO_GOAL)

    # ── §9.6  Failure propagation demo ───────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§9.6  Failure Propagation  (retry → degraded → pipeline continues)")
    print(DIVIDER)

    class BrokenResearcher(ResearchAgent):
        """Researcher that always fails — to demo failure handling."""
        def run(self, inp: AgentInput) -> AgentOutput:
            raise RuntimeError("Simulated API timeout")

    broken = BrokenResearcher("researcher")
    out = supervisor._execute_with_fallback(broken, AgentInput(task="test"), retries=1)
    print(f"  Final status: {out.status}  |  error: {out.error}")
    print(f"  Pipeline receives degraded output and continues (no crash).")

    # ── Final answer ──────────────────────────────────────────────────────────
    print(f"\n{THICK}")
    print("FINAL OUTPUT  (LLM-driven routing)")
    print(THICK)
    print(llm_result[:600] + ("..." if len(llm_result) > 600 else ""))


if __name__ == "__main__":
    main()
