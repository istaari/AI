"""
Exercise — Agent Evaluation (§11)
==================================

Learn how to evaluate agent quality systematically: record execution traces,
score outputs with LLM-as-Judge, measure step-level quality, run behavioral
checks, build a regression suite, and track latency and cost.

Run from the project root:
    python -m agent_eval.evaluator

Learning goals:
    - Record every intermediate step in a Trace for debugging (§11.2)
    - Use LLM-as-Judge to score outputs with a rubric (§11.3)
    - Score each step independently to pinpoint failures (§11.4)
    - Assert behavioral invariants that exact-output checks cannot catch (§11.5)
    - Run a regression suite to catch quality regressions (§11.6)
    - Measure per-call and end-to-end latency and cost (§11.7)

Key insight: agent outputs are non-deterministic. Evals measure quality across
the distribution of valid answers — not a single exact expected string.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from google import genai
from google.genai import types
from shared.config import SETTINGS

DIVIDER = "─" * 65
THICK = "═" * 65

# Cost constants — gemini-2.0-flash ($ per 1M tokens)
COST_PER_M_INPUT = 0.30
COST_PER_M_OUTPUT = 1.20
CHARS_PER_TOKEN = 4   # rough estimate: 1 token ≈ 4 characters


# ─────────────────────────────────────────────────────────────────────────────
# ── §11.2  TRACE DATA STRUCTURES
# A Trace records every intermediate step: LLM calls, tool calls, planning.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Define TraceEntry, Trace, and Tracer.
# TraceEntry = one recorded step with timing and token counts.
# Trace      = ordered list of TraceEntry objects for a single agent run.
# Tracer     = context manager that agents call to log each step.


@dataclass
class TraceEntry:
    """One recorded step in an agent execution."""
    step: str                           # "plan" | "tool_call" | "llm_call" | "answer"
    input: str                          # stringified input
    output: str                         # stringified output
    tool: Optional[str] = None          # tool name if step == "tool_call"
    tokens_in: int = 0
    tokens_out: int = 0
    duration_ms: float = 0.0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class Trace:
    """Ordered record of all steps for a single agent goal."""
    goal: str
    entries: list[TraceEntry] = field(default_factory=list)
    total_duration_ms: float = 0.0
    start_ts: str = ""

    def add(self, entry: TraceEntry) -> None:
        """Append one step to the trace."""
        self.entries.append(entry)

    def total_tokens(self) -> tuple[int, int]:
        """Return (total_input_tokens, total_output_tokens) across all LLM entries."""
        tok_in = sum(e.tokens_in for e in self.entries)
        tok_out = sum(e.tokens_out for e in self.entries)
        return tok_in, tok_out

    def cost_estimate(self) -> float:
        """Compute estimated dollar cost from token counts."""
        tok_in, tok_out = self.total_tokens()
        return (tok_in * COST_PER_M_INPUT + tok_out * COST_PER_M_OUTPUT) / 1_000_000

    def tool_calls(self) -> list[str]:
        """Return list of tool names called (preserves order, may contain duplicates)."""
        return [e.tool for e in self.entries if e.step == "tool_call" and e.tool]

    def to_dict(self) -> dict:
        """Serialise to a JSON-safe dict."""
        return {
            "goal": self.goal,
            "total_duration_ms": self.total_duration_ms,
            "start_ts": self.start_ts,
            "entries": [
                {
                    "step": e.step,
                    "tool": e.tool,
                    "tokens_in": e.tokens_in,
                    "tokens_out": e.tokens_out,
                    "duration_ms": e.duration_ms,
                    "input_preview": e.input[:80],
                    "output_preview": e.output[:80],
                }
                for e in self.entries
            ],
        }


class Tracer:
    """
    Context manager that records intermediate steps into a Trace.

    Usage:
        tracer = Tracer(goal="Find cheapest laptop")
        with tracer:
            answer = run_traced_agent(client, goal, tracer)
        trace = tracer.trace

    Teaching point (§11.2): the trace is the only reliable way to debug
    an agent. Every step is recorded — not just the final answer.
    """

    def __init__(self, goal: str) -> None:
        self.trace = Trace(goal=goal)
        self._start: float = 0.0
        self._step_start: float = 0.0

    def __enter__(self) -> "Tracer":
        self._start = time.monotonic()
        self.trace.start_ts = datetime.now(timezone.utc).isoformat()
        return self

    def __exit__(self, *args: object) -> None:
        self.trace.total_duration_ms = (time.monotonic() - self._start) * 1000

    def log_llm(
        self,
        step: str,
        prompt: str,
        response: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        """Record one LLM call."""
        self.trace.add(TraceEntry(
            step=step,
            input=prompt[:200],
            output=response[:200],
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
        ))

    def log_tool(self, tool_name: str, args: dict, result: str, duration_ms: float = 0.0) -> None:
        """Record one tool call."""
        self.trace.add(TraceEntry(
            step="tool_call",
            input=json.dumps(args)[:200],
            output=result[:200],
            tool=tool_name,
            duration_ms=duration_ms,
        ))

    def log_step(self, step: str, input_text: str, output_text: str) -> None:
        """Record a generic named step."""
        self.trace.add(TraceEntry(
            step=step,
            input=input_text[:200],
            output=output_text[:200],
        ))


# ─────────────────────────────────────────────────────────────────────────────
# ── §11.2  TRACE REPLAYER
# Printing a trace step-by-step shows exactly where the agent went wrong.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement replay_trace.
# For each TraceEntry, print: step index, step type, tool name if applicable,
# timing, tokens, and previews of input/output.


def replay_trace(trace: Trace) -> None:
    """
    Print a trace step-by-step with visual formatting.

    Teaching point: replaying the trace is how you find the exact step
    where the agent went wrong — bad plan, wrong tool call, hallucination.
    """
    tok_in, tok_out = trace.total_tokens()
    print(f"\n  §11.2  Trace Replay  ({len(trace.entries)} steps recorded)")
    print(f"  Goal: \"{trace.goal}\"")
    print()
    for i, e in enumerate(trace.entries, 1):
        label = f"{e.step:<14}"
        if e.tool:
            label += f"  {e.tool:<20}"
        tok_info = f"{e.tokens_in} tok in, {e.tokens_out} tok out" if (e.tokens_in or e.tokens_out) else "0 tokens"
        print(f"  [step {i}/{len(trace.entries)}] {label}  ({e.duration_ms:.0f}ms, {tok_info})")
        print(f"    IN:  {e.input[:90]}{'...' if len(e.input) > 90 else ''}")
        print(f"    OUT: {e.output[:90]}{'...' if len(e.output) > 90 else ''}")
    print()
    print(f"  Total: {len(trace.entries)} steps  |  {tok_in + tok_out} tokens  |  {trace.total_duration_ms:.0f}ms")


# ─────────────────────────────────────────────────────────────────────────────
# LLM HELPER
# ─────────────────────────────────────────────────────────────────────────────

def llm(client: genai.Client, system: str, messages: list[dict],
        max_tokens: int = 512) -> tuple[str, int, int, float]:
    """
    Single LLM call. Returns (text, tokens_in, tokens_out, duration_ms).
    Token counts estimated from character length (CHARS_PER_TOKEN).
    """
    t0 = time.monotonic()
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
            max_output_tokens=max_tokens,
        ),
    )
    duration_ms = (time.monotonic() - t0) * 1000
    text = resp.text.strip()
    # Estimate tokens from prompt chars + output chars
    prompt_chars = sum(len(m["content"]) for m in messages) + len(system)
    tok_in = prompt_chars // CHARS_PER_TOKEN
    tok_out = len(text) // CHARS_PER_TOKEN
    return text, tok_in, tok_out, duration_ms


def parse_json(raw: str, fallback: dict) -> dict:
    cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip("` \n")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT AGENT  (local copy of §3 tools — keeps this module self-contained)
# ─────────────────────────────────────────────────────────────────────────────

PRODUCT_DB = {
    "laptop-pro":  {"name": "Laptop Pro",  "price": 1200, "stock": 5,  "rating": 4.7},
    "laptop-air":  {"name": "Laptop Air",  "price": 850,  "stock": 12, "rating": 4.5},
    "tablet-x":    {"name": "Tablet X",    "price": 499,  "stock": 0,  "rating": 4.2},
    "keyboard-k1": {"name": "Keyboard K1", "price": 79,   "stock": 30, "rating": 4.8},
}


def _search_products(query: str) -> list[dict]:
    q = query.lower()
    return [p for p in PRODUCT_DB.values() if q in p["name"].lower()]


def _get_product_details(product_id: str) -> dict:
    return PRODUCT_DB.get(product_id, {"error": f"Product '{product_id}' not found."})


def _calculate(expression: str) -> str:
    if not re.fullmatch(r"[\d\s\+\-\*\/\.\(\)]+", expression):
        return f"Error: unsafe expression"
    try:
        return str(eval(expression, {"__builtins__": {}}))  # noqa: S307
    except Exception as e:
        return f"Error: {e}"


def _check_stock(product_id: str) -> dict:
    p = PRODUCT_DB.get(product_id)
    if p is None:
        return {"error": f"Unknown product '{product_id}'"}
    return {"product": p["name"], "in_stock": p["stock"] > 0, "quantity": p["stock"]}


TOOLS = {
    "search_products":    {"fn": _search_products,    "desc": "Search products by keyword. Input: {query: string}"},
    "get_product_details":{"fn": _get_product_details,"desc": "Get full product details. Input: {product_id: string}"},
    "calculate":          {"fn": _calculate,          "desc": "Evaluate arithmetic. Input: {expression: string}"},
    "check_stock":        {"fn": _check_stock,        "desc": "Check stock availability. Input: {product_id: string}"},
}

TOOL_DESCS = "\n".join(f"  - {n}: {v['desc']}" for n, v in TOOLS.items())

REACT_SYSTEM = f"""You are a product search agent. Complete tasks using tools.
Respond ONLY with JSON in one of two forms:
  {{"thought": "...", "action": "<tool>", "args": {{...}}}}
  {{"thought": "...", "answer": "..."}}
Tools:\n{TOOL_DESCS}"""

PLAN_SYSTEM = f"""Break the goal into 3-4 ordered sub-tasks.
Return ONLY a JSON array of strings. Tools:\n{TOOL_DESCS}"""


def run_traced_agent(
    client: genai.Client, goal: str, tracer: Tracer
) -> str:
    """
    Run a ReAct product-search agent while recording every step in the tracer.
    This is a thin instrumented wrapper around the §3 react_agent pattern.
    """
    # Planning step
    plan_prompt = goal
    raw, tok_in, tok_out, dur = llm(client, PLAN_SYSTEM, [{"role": "user", "content": plan_prompt}])
    cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip("` \n")
    try:
        steps = json.loads(cleaned) if cleaned.startswith("[") else [goal]
    except json.JSONDecodeError:
        steps = [goal]
    tracer.log_llm("plan", plan_prompt, str(steps), tok_in, tok_out, dur)

    history: list[dict] = [{"role": "user", "content": goal}]
    final_answer = "No answer produced."

    for _ in range(8):
        raw, tok_in, tok_out, dur = llm(client, REACT_SYSTEM, history)
        history.append({"role": "model", "content": raw})
        cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip("` \n")
        parsed = parse_json(cleaned, {})

        if "action" in parsed:
            tool_name = parsed["action"]
            args = parsed.get("args", {})
            if tool_name in TOOLS:
                t0 = time.monotonic()
                result = TOOLS[tool_name]["fn"](**args)
                tool_dur = (time.monotonic() - t0) * 1000
                obs = json.dumps(result)
                tracer.log_tool(tool_name, args, obs, tool_dur)
                history.append({"role": "user", "content": f"Observation: {obs}"})
            else:
                history.append({"role": "user", "content": f"Observation: unknown tool {tool_name}"})
        elif "answer" in parsed:
            final_answer = parsed["answer"]
            tracer.log_llm("answer", goal, final_answer, tok_in, tok_out, dur)
            break

    return final_answer


# ─────────────────────────────────────────────────────────────────────────────
# ── §11.3  LLM-AS-JUDGE
# A model grades another model's output using a rubric.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement judge().
# Send question + answer to the LLM with JUDGE_SYSTEM rubric.
# Parse score and criteria_scores from the response.
# Return JudgeResult with passed = (score >= threshold).


@dataclass
class JudgeResult:
    score: int               # 1–5 overall
    reasoning: str
    passed: bool             # score >= threshold
    criteria_scores: dict[str, int] = field(default_factory=dict)


JUDGE_SYSTEM = """\
You are an impartial evaluator. Score the agent's answer against this rubric.
Return ONLY JSON:
{
  "score": <1-5>,
  "reasoning": "<one sentence>",
  "criteria_scores": {"correctness": <1-5>, "completeness": <1-5>, "grounding": <1-5>}
}

Rubric:
- correctness  (1-5): Is the answer factually correct given the tools available?
- completeness (1-5): Does the answer fully address the question?
- grounding    (1-5): Is every claim supported by a tool observation, not invented?

Overall score = floor(average of the three criteria).
5 = correct, complete, fully grounded.
3 = partially correct or missing one criterion.
1 = wrong product, hallucinated data, or completely off-topic."""


def judge(
    client: genai.Client,
    question: str,
    agent_answer: str,
    trace: Optional[Trace] = None,
    threshold: int = 3,
) -> JudgeResult:
    """
    LLM-as-Judge: score the agent's answer on correctness, completeness, grounding.

    Teaching point (§11.3): in production use a stronger model (e.g., gemini-2.5-pro)
    to grade outputs from a faster one (e.g., gemini-2.0-flash). The judge inherits
    model biases — validate against a human-labeled gold set before trusting it.
    """
    tool_trace = ""
    if trace:
        calls = trace.tool_calls()
        tool_trace = f"\nTools called: {', '.join(calls)}" if calls else ""

    prompt = f"Question: {question}\nAgent answer: {agent_answer}{tool_trace}"
    raw, _, _, _ = llm(client, JUDGE_SYSTEM, [{"role": "user", "content": prompt}], max_tokens=256)
    parsed = parse_json(raw, {"score": 3, "reasoning": "parse error", "criteria_scores": {}})

    score = int(parsed.get("score", 3))
    criteria = parsed.get("criteria_scores", {})
    return JudgeResult(
        score=score,
        reasoning=parsed.get("reasoning", ""),
        passed=score >= threshold,
        criteria_scores=criteria,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ── §11.4  TASK DECOMPOSITION METRICS
# Score each step independently to pinpoint exactly where failure occurred.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement score_decomposition.
# For tool_call entries: deterministic check (was it in expected_tools?).
# For llm_call / answer entries: use judge() for that step alone.


@dataclass
class StepScore:
    step_index: int
    description: str
    score: int      # 1–5
    passed: bool


@dataclass
class DecompositionResult:
    step_scores: list[StepScore]
    aggregate_score: float
    steps_passed: int
    steps_total: int


def score_decomposition(
    client: genai.Client,
    goal: str,
    trace: Trace,
    expected_tools: list[str],
) -> DecompositionResult:
    """
    Score each traced step independently.

    Teaching point (§11.4): end-to-end score hides where failure occurred.
    Step-level decomposition pinpoints the exact broken step:
    bad plan → wrong tool called → tool result misread → hallucination.
    """
    scores: list[StepScore] = []
    tool_calls_seen: list[str] = []

    for i, entry in enumerate(trace.entries):
        if entry.step == "tool_call":
            tool_calls_seen.append(entry.tool or "")
            # Deterministic check: was this tool expected? Did it return non-empty output?
            in_expected = entry.tool in expected_tools
            has_output = bool(entry.output and "error" not in entry.output.lower())
            s = 5 if (in_expected and has_output) else (3 if has_output else 1)
            scores.append(StepScore(
                step_index=i,
                description=f"tool={entry.tool}",
                score=s,
                passed=s >= 3,
            ))
        elif entry.step in ("answer", "llm_call"):
            # LLM judgment for synthesis steps
            result = judge(client, goal, entry.output, threshold=3)
            scores.append(StepScore(
                step_index=i,
                description=entry.step,
                score=result.score,
                passed=result.passed,
            ))

    passed = sum(1 for s in scores if s.passed)
    agg = sum(s.score for s in scores) / max(len(scores), 1)
    return DecompositionResult(
        step_scores=scores,
        aggregate_score=round(agg, 2),
        steps_passed=passed,
        steps_total=len(scores),
    )


# ─────────────────────────────────────────────────────────────────────────────
# ── §11.5  BEHAVIORAL TESTING
# Assert behavioral invariants — what the agent DID, not what it said.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement run_behavioral_test.
# Check must_call_tools: verify each appears in trace.tool_calls().
# Check must_not_contain: verify none appear in the answer.
# Both checks are deterministic — no LLM needed.


@dataclass
class BehavioralTest:
    name: str
    goal: str
    invariants: list[str]              # human-readable description of each invariant
    must_call_tools: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    max_total_tokens: int = 10_000


@dataclass
class BehavioralResult:
    test_name: str
    passed: bool
    violations: list[str]


def run_behavioral_test(
    client: genai.Client,
    test: BehavioralTest,
    trace: Trace,
    answer: str,
) -> BehavioralResult:
    """
    Assert behavioral invariants against a completed trace + answer.

    Teaching point (§11.5): behavioral tests catch judgment failures that
    exact-output assertions cannot — e.g., "agent assumed stock without
    calling check_stock first."
    """
    violations: list[str] = []
    tools_called = set(trace.tool_calls())

    for tool in test.must_call_tools:
        if tool not in tools_called:
            violations.append(f"Expected tool '{tool}' was NOT called (called: {tools_called})")

    answer_lower = answer.lower()
    for phrase in test.must_not_contain:
        if phrase.lower() in answer_lower:
            violations.append(f"Answer contains forbidden phrase: '{phrase}'")

    tok_in, tok_out = trace.total_tokens()
    if (tok_in + tok_out) > test.max_total_tokens:
        violations.append(
            f"Token budget exceeded: {tok_in + tok_out} > {test.max_total_tokens}"
        )

    return BehavioralResult(
        test_name=test.name,
        passed=len(violations) == 0,
        violations=violations,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ── §11.6  REGRESSION SUITE
# A fixed set of known-good cases; re-run on every change to catch regressions.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement run_regression_suite.
# For each RegressionCase: run the agent, judge the answer, check tool usage.
# A regression = previously passed, now fails. Report totals.


@dataclass
class RegressionCase:
    id: str
    goal: str
    expected_tools: list[str]
    min_judge_score: int = 3
    must_not_contain: list[str] = field(default_factory=list)


@dataclass
class SuiteResult:
    total: int
    passed: int
    failed: int
    results: list[dict]


def run_regression_suite(
    client: genai.Client,
    cases: list[RegressionCase],
    run_agent_fn: Callable,
) -> SuiteResult:
    """
    Run a fixed regression suite through the provided agent function.
    run_agent_fn signature: (client, goal, tracer) -> str

    Teaching point (§11.6): the suite catches regressions automatically.
    Any case that previously passed and now fails is a deploy-blocking regression.
    """
    results: list[dict] = []
    for case in cases:
        tracer = Tracer(goal=case.goal)
        with tracer:
            answer = run_agent_fn(client, case.goal, tracer)
        trace = tracer.trace

        judge_result = judge(client, case.goal, answer, trace=trace, threshold=case.min_judge_score)
        tools_called = set(trace.tool_calls())
        missing_tools = [t for t in case.expected_tools if t not in tools_called]
        forbidden = [p for p in case.must_not_contain if p.lower() in answer.lower()]
        passed = judge_result.passed and not missing_tools and not forbidden

        results.append({
            "id": case.id,
            "goal": case.goal[:60],
            "passed": passed,
            "judge_score": judge_result.score,
            "missing_tools": missing_tools,
            "forbidden_found": forbidden,
        })

    passed_count = sum(1 for r in results if r["passed"])
    return SuiteResult(
        total=len(results),
        passed=passed_count,
        failed=len(results) - passed_count,
        results=results,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ── §11.7  LATENCY & COST TRACKING
# Measure per-call and end-to-end performance. Quality at 10× cost is a bug.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement build_cost_report and print_cost_table.
# build_cost_report: aggregate token counts and cost per entry.
# print_cost_table: print aligned table with step, tokens, cost, latency.


@dataclass
class CostReport:
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: float
    per_step: list[dict]
    total_duration_ms: float
    avg_latency_ms: float


def build_cost_report(trace: Trace) -> CostReport:
    """
    Build a detailed cost report from a Trace.

    Teaching point (§11.7): correctness at 10× the cost is not production-ready.
    Track cost alongside quality scores — both must be within budget.
    """
    per_step: list[dict] = []
    for e in trace.entries:
        cost = (e.tokens_in * COST_PER_M_INPUT + e.tokens_out * COST_PER_M_OUTPUT) / 1_000_000
        label = f"tool:{e.tool}" if e.step == "tool_call" else e.step
        per_step.append({
            "step": label,
            "tokens_in": e.tokens_in,
            "tokens_out": e.tokens_out,
            "cost_usd": cost,
            "duration_ms": e.duration_ms,
        })

    tok_in, tok_out = trace.total_tokens()
    total_cost = sum(s["cost_usd"] for s in per_step)
    llm_steps = [e for e in trace.entries if e.duration_ms > 0]
    avg = sum(e.duration_ms for e in llm_steps) / max(len(llm_steps), 1)

    return CostReport(
        total_tokens_in=tok_in,
        total_tokens_out=tok_out,
        total_cost_usd=total_cost,
        per_step=per_step,
        total_duration_ms=trace.total_duration_ms,
        avg_latency_ms=round(avg, 1),
    )


def print_cost_table(report: CostReport) -> None:
    """Print the per-step cost breakdown table."""
    header = f"  {'Step':<20}  {'Tok in':>7}  {'Tok out':>8}  {'Cost ($)':>10}  {'Latency':>10}"
    sep = "  " + "─" * 63
    print(header)
    print(sep)
    for s in report.per_step:
        print(
            f"  {s['step']:<20}  {s['tokens_in']:>7}  {s['tokens_out']:>8}  "
            f"${s['cost_usd']:>9.6f}  {s['duration_ms']:>7.0f}ms"
        )
    print(sep)
    print(
        f"  {'TOTAL':<20}  {report.total_tokens_in:>7}  {report.total_tokens_out:>8}  "
        f"${report.total_cost_usd:>9.6f}  {report.total_duration_ms:>7.0f}ms"
    )
    print(f"  Avg latency per LLM call: {report.avg_latency_ms:.0f}ms")
    tok_total = report.total_tokens_in + report.total_tokens_out
    llm_pct = 100 if tok_total else 0
    print(f"  Note: tool calls cost $0 (0 tokens) — {llm_pct}% of cost is from LLM calls")


# ─────────────────────────────────────────────────────────────────────────────
# REGRESSION CASES
# ─────────────────────────────────────────────────────────────────────────────

REGRESSION_CASES = [
    RegressionCase(
        id="case-01",
        goal="Find the cheapest in-stock laptop and calculate 10% off its price.",
        expected_tools=["search_products", "check_stock", "calculate"],
        min_judge_score=3,
    ),
    RegressionCase(
        id="case-02",
        goal="Which product has the highest rating, and is it in stock?",
        expected_tools=["search_products", "check_stock"],
        min_judge_score=3,
    ),
    RegressionCase(
        id="case-03",
        goal="Is the Tablet X available for purchase?",
        expected_tools=["check_stock"],
        min_judge_score=3,
    ),
    RegressionCase(
        id="case-04",
        goal="Get details for the product with ID FAKE-999.",
        expected_tools=["get_product_details"],
        min_judge_score=3,
        must_not_contain=["$1200", "$850"],  # should not hallucinate a price
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print(THICK)
    print("Agent Evaluation Exercise (§11)")
    print(f"Model: {SETTINGS.model}")
    print(THICK)

    client = genai.Client(api_key=SETTINGS.require_api_key())
    DEMO_GOAL = "Find the cheapest in-stock laptop and calculate 10% off its price."

    # ── §11.2  Trace-based Debugging ─────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§11.2  Trace-Based Debugging")
    print(DIVIDER)
    print(f"Running agent: \"{DEMO_GOAL}\"")

    tracer = Tracer(goal=DEMO_GOAL)
    with tracer:
        answer = run_traced_agent(client, DEMO_GOAL, tracer)
    trace = tracer.trace

    replay_trace(trace)

    # ── §11.3  LLM-as-Judge ───────────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§11.3  LLM-as-Judge")
    print(DIVIDER)
    verdict = judge(client, DEMO_GOAL, answer, trace=trace, threshold=3)
    status = "✓ PASSED" if verdict.passed else "✗ FAILED"
    print(f"  Question:  \"{DEMO_GOAL[:60]}\"")
    print(f"  Answer:    \"{answer[:80]}\"")
    print(f"  Judge score: {verdict.score}/5  {status}  (threshold: 3)")
    print(f"  Reasoning: {verdict.reasoning}")
    if verdict.criteria_scores:
        criteria_str = "  ".join(f"{k}={v}" for k, v in verdict.criteria_scores.items())
        print(f"  Criteria:  {criteria_str}")

    # ── §11.4  Task Decomposition Metrics ─────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§11.4  Task Decomposition Metrics  (per-step scoring)")
    print(DIVIDER)
    decomp = score_decomposition(
        client, DEMO_GOAL, trace,
        expected_tools=["search_products", "check_stock", "calculate"],
    )
    for s in decomp.step_scores:
        status_sym = "✓ PASS" if s.passed else "✗ FAIL"
        print(f"  Step {s.step_index + 1}  {s.description:<30}  score={s.score}/5  {status_sym}")
    print(f"  Aggregate: {decomp.steps_passed}/{decomp.steps_total} steps passed  "
          f"(mean score {decomp.aggregate_score})")

    # ── §11.5  Behavioral Testing ─────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§11.5  Behavioral Testing  (invariant checks — no LLM needed)")
    print(DIVIDER)
    behavioral_tests = [
        BehavioralTest(
            name="uses_stock_before_recommending",
            goal=DEMO_GOAL,
            invariants=["check_stock must be called before recommending a product"],
            must_call_tools=["check_stock"],
        ),
        BehavioralTest(
            name="no_hallucinated_price_for_unknown",
            goal="Get details for FAKE-999.",
            invariants=["answer must not contain real product prices for unknown IDs"],
            must_call_tools=["get_product_details"],
            must_not_contain=["$1200", "$850", "$499"],
        ),
        BehavioralTest(
            name="within_token_budget",
            goal=DEMO_GOAL,
            invariants=["total tokens must be under 10,000"],
            max_total_tokens=10_000,
        ),
    ]
    for test in behavioral_tests[:1]:  # run first test against the existing trace
        result = run_behavioral_test(client, test, trace, answer)
        status_sym = "PASSED" if result.passed else "FAILED"
        print(f"  Test: {test.name}")
        print(f"    {status_sym}" + (f" — {result.violations[0]}" if result.violations else ""))
    # Run remaining tests with fresh agent calls
    for test in behavioral_tests[1:]:
        t2 = Tracer(goal=test.goal)
        with t2:
            a2 = run_traced_agent(client, test.goal, t2)
        result = run_behavioral_test(client, test, t2.trace, a2)
        status_sym = "PASSED" if result.passed else "FAILED"
        print(f"  Test: {test.name}")
        print(f"    {status_sym}" + (f" — {result.violations[0]}" if result.violations else ""))

    # ── §11.6  Regression Suite ───────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print(f"§11.6  Regression Suite  ({len(REGRESSION_CASES)} cases)")
    print(DIVIDER)
    suite = run_regression_suite(client, REGRESSION_CASES, run_traced_agent)
    for r in suite.results:
        status_sym = "✓ PASS" if r["passed"] else "✗ FAIL"
        print(f"  [{r['id']}] {r['goal']:<55}  {status_sym}  score={r['judge_score']}")
    print(f"\n  Suite result: {suite.passed}/{suite.total} passed  "
          f"({'no regressions' if suite.failed == 0 else str(suite.failed) + ' regression(s) found'})")

    # ── §11.7  Latency & Cost Tracking ────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§11.7  Latency & Cost Tracking")
    print(DIVIDER)
    report = build_cost_report(trace)
    print_cost_table(report)

    print(f"\n{THICK}")
    print("Key takeaway: traces make debugging deterministic.")
    print("Evals make quality measurable. Run the suite on every prompt change.")
    print(THICK)


if __name__ == "__main__":
    main()
