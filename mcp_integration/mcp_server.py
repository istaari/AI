"""
Exercise — Model Context Protocol (§6)
=======================================

Simulate the MCP protocol in pure Python to learn how agents discover and call
tools, resources, and prompts at runtime — without hardcoding any capability.

Run from the project root:
    python -m mcp_integration.mcp_server

Learning goals:
    - Understand the MCP server/client model (§6.1)
    - See dynamic tool discovery via tools/list (§6.2)
    - Contrast Resources (read-only data) vs Tools (side effects) (§6.3)
    - Use Prompts as first-class named templates (§6.4)
    - Simulate the capability negotiation handshake (§6.6)

Key insight: the agent NEVER hardcodes tool names. It reads them from the
server at runtime, exactly like a real MCP client would.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from google import genai
from google.genai import types
from shared.config import SETTINGS

DIVIDER = "─" * 65
THICK = "═" * 65


# ─────────────────────────────────────────────────────────────────────────────
# ── §6.1  DATA CLASSES  (represent what the protocol exchanges)
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Define the three MCP capability types.
# MCPTool   → a function the agent can invoke (has side effects)
# MCPResource → static read-only data identified by a URI
# MCPPrompt → a named template the agent can fetch and render


@dataclass
class MCPTool:
    """A callable capability registered on an MCP server."""
    name: str
    description: str
    input_schema: dict          # JSON Schema describing expected args
    fn: Callable                # the actual Python function to execute


@dataclass
class MCPResource:
    """Read-only data exposed by the server, identified by a URI."""
    uri: str                    # e.g. "resource://company/faq"
    description: str
    content: str                # static text content (simulates a file/DB read)


@dataclass
class MCPPrompt:
    """A named prompt template the agent can request and render."""
    name: str
    description: str
    template: str               # may contain {argument} placeholders


# ─────────────────────────────────────────────────────────────────────────────
# ── §6.1  MCP SERVER
# The server is the half that *owns* capabilities.
# It handles protocol messages and returns structured responses.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement MCPServer.
# The server must handle these protocol messages (by method name):
#   initialize          → return protocol version + capability flags
#   tools/list          → return all registered tools (no fn — just schema)
#   tools/call          → execute a named tool, return content
#   resources/list      → return all registered resource URIs
#   resources/read      → return the text content of a URI
#   prompts/list        → return all registered prompt names
#   prompts/get         → render a prompt template with provided arguments


class MCPServer:
    """Simulates an MCP server that exposes tools, resources, and prompts."""

    PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, name: str):
        self.name = name
        self._tools: dict[str, MCPTool] = {}
        self._resources: dict[str, MCPResource] = {}
        self._prompts: dict[str, MCPPrompt] = {}

    # ── Registration ────────────────────────────────────────────────────────

    def register_tool(self, tool: MCPTool) -> None:
        self._tools[tool.name] = tool

    def register_resource(self, resource: MCPResource) -> None:
        self._resources[resource.uri] = resource

    def register_prompt(self, prompt: MCPPrompt) -> None:
        self._prompts[prompt.name] = prompt

    # ── Protocol dispatcher ──────────────────────────────────────────────────

    def handle(self, message: dict) -> dict:
        """Route an incoming protocol message to the correct handler."""
        method = message.get("method", "")
        params = message.get("params", {})
        handlers = {
            "initialize":      lambda: self._handle_initialize(params),
            "tools/list":      self._handle_tools_list,
            "tools/call":      lambda: self._handle_tools_call(params),
            "resources/list":  self._handle_resources_list,
            "resources/read":  lambda: self._handle_resources_read(params),
            "prompts/list":    self._handle_prompts_list,
            "prompts/get":     lambda: self._handle_prompts_get(params),
        }
        handler = handlers.get(method)
        if handler is None:
            return {"error": f"Unknown method: {method}"}
        return handler()

    # ── §6.6  Capability negotiation ─────────────────────────────────────────

    def _handle_initialize(self, params: dict) -> dict:
        """Return protocol version and which capability groups are available."""
        return {
            "protocolVersion": self.PROTOCOL_VERSION,
            "serverInfo": {"name": self.name},
            "capabilities": {
                "tools":     {} if self._tools     else None,
                "resources": {} if self._resources else None,
                "prompts":   {} if self._prompts   else None,
            },
        }

    # ── §6.2  Tool discovery ──────────────────────────────────────────────────

    def _handle_tools_list(self) -> dict:
        """Return tool schemas — NOT the fn (clients can't call Python functions directly)."""
        return {
            "tools": [
                {
                    "name":        t.name,
                    "description": t.description,
                    "inputSchema": t.input_schema,
                }
                for t in self._tools.values()
            ]
        }

    def _handle_tools_call(self, params: dict) -> dict:
        """Execute a named tool with arguments; return structured content."""
        name = params.get("name", "")
        args = params.get("arguments", {})
        tool = self._tools.get(name)
        if tool is None:
            return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}
        try:
            result = tool.fn(**args)
            return {"content": [{"type": "text", "text": str(result)}]}
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"Error: {e}"}]}

    # ── §6.3  Resources (read-only) ───────────────────────────────────────────

    def _handle_resources_list(self) -> dict:
        return {
            "resources": [
                {"uri": r.uri, "description": r.description}
                for r in self._resources.values()
            ]
        }

    def _handle_resources_read(self, params: dict) -> dict:
        uri = params.get("uri", "")
        resource = self._resources.get(uri)
        if resource is None:
            return {"error": f"Resource not found: {uri}"}
        return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": resource.content}]}

    # ── §6.4  Prompts as first-class citizens ─────────────────────────────────

    def _handle_prompts_list(self) -> dict:
        return {
            "prompts": [
                {"name": p.name, "description": p.description}
                for p in self._prompts.values()
            ]
        }

    def _handle_prompts_get(self, params: dict) -> dict:
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        prompt = self._prompts.get(name)
        if prompt is None:
            return {"error": f"Prompt not found: {name}"}
        rendered = prompt.template.format(**arguments) if arguments else prompt.template
        return {
            "description": prompt.description,
            "messages": [{"role": "user", "content": {"type": "text", "text": rendered}}],
        }


# ─────────────────────────────────────────────────────────────────────────────
# ── §6.1  MCP CLIENT
# The client discovers capabilities at connect-time and exposes a clean API.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement MCPClient.
# The client must:
#   1. Send "initialize" and parse the negotiated capabilities
#   2. Discover tools / resources / prompts based on what the server supports
#   3. Expose call_tool, read_resource, get_prompt
#   4. Provide tool_descriptions_for_llm() to inject into a prompt


class MCPClient:
    """Simulates an MCP client using in-process transport (calls server.handle directly)."""

    def __init__(self, server: MCPServer):
        self.server = server
        self._negotiated: dict = {}
        self._tools: list[dict] = []
        self._resources: list[dict] = []
        self._prompts: list[dict] = []

    def _send(self, method: str, params: dict | None = None) -> dict:
        """In-process transport: message passes directly to server.handle()."""
        return self.server.handle({"method": method, "params": params or {}})

    def connect(self) -> dict:
        """Initialize connection and discover all available capabilities."""
        # ── §6.6  Handshake ──────────────────────────────────────────────────
        self._negotiated = self._send("initialize", {
            "protocolVersion": MCPServer.PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
        })
        caps = self._negotiated.get("capabilities", {})

        # Only discover capabilities the server declared it has
        if caps.get("tools") is not None:
            self._tools = self._send("tools/list").get("tools", [])
        if caps.get("resources") is not None:
            self._resources = self._send("resources/list").get("resources", [])
        if caps.get("prompts") is not None:
            self._prompts = self._send("prompts/list").get("prompts", [])

        return self._negotiated

    def list_tools(self) -> list[dict]:
        return self._tools

    def call_tool(self, name: str, args: dict) -> str:
        result = self._send("tools/call", {"name": name, "arguments": args})
        if result.get("isError"):
            return result["content"][0]["text"]
        return result["content"][0]["text"]

    def list_resources(self) -> list[dict]:
        return self._resources

    def read_resource(self, uri: str) -> str:
        result = self._send("resources/read", {"uri": uri})
        if "error" in result:
            return result["error"]
        return result["contents"][0]["text"]

    def list_prompts(self) -> list[dict]:
        return self._prompts

    def get_prompt(self, name: str, arguments: dict | None = None) -> str:
        result = self._send("prompts/get", {"name": name, "arguments": arguments or {}})
        if "error" in result:
            return result["error"]
        return result["messages"][0]["content"]["text"]

    def tool_descriptions_for_llm(self) -> str:
        """Format discovered tools as a string suitable for injection into a system prompt."""
        lines = []
        for t in self._tools:
            schema = t.get("inputSchema", {})
            props = schema.get("properties", {})
            args_str = ", ".join(f"{k}: {v.get('type','any')}" for k, v in props.items())
            lines.append(f"  - {t['name']}({args_str}): {t['description']}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# LLM HELPER
# ─────────────────────────────────────────────────────────────────────────────

def llm(client: genai.Client, system: str, messages: list[dict]) -> str:
    """Single LLM call. messages = [{role, content}, ...]"""
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
            max_output_tokens=1024,
        ),
    )
    return resp.text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# ── GEMINI AGENT USING DYNAMIC MCP DISCOVERY
# The agent never sees hardcoded tool names — only what the server exposes.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement MCPAgent.
# The agent must:
#   1. Use the MCP client's tool_descriptions_for_llm() in the system prompt
#   2. Run a ReAct-style loop (Thought → Action → Observation)
#   3. Call tools through the MCP client (not directly)
#   4. Stop when the model emits {"answer": "..."}


class MCPAgent:
    """
    A Gemini-backed agent that discovers and calls tools dynamically via MCP.
    It never hardcodes tool names — the system prompt is built from discovery.
    """

    MAX_ITERATIONS = 6

    def __init__(self, genai_client: genai.Client, mcp_client: MCPClient):
        self.genai_client = genai_client
        self.mcp_client = mcp_client

    def _build_system(self) -> str:
        tool_list = self.mcp_client.tool_descriptions_for_llm()
        return f"""You are an agent that answers questions using available tools.
At each turn respond with ONLY valid JSON in one of two forms:

To use a tool:
  {{"thought": "...", "action": "<tool_name>", "args": {{...}}}}

When you have enough information:
  {{"thought": "...", "answer": "..."}}

Available tools (discovered dynamically from MCP server):
{tool_list}

Rules:
- Use tools to retrieve real data — do not fabricate answers.
- Stop as soon as you can fully answer the question."""

    def run(self, goal: str) -> str:
        system = self._build_system()
        history: list[dict] = [{"role": "user", "content": goal}]

        for iteration in range(1, self.MAX_ITERATIONS + 1):
            raw = llm(self.genai_client, system, history)
            history.append({"role": "model", "content": raw})

            cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip("` \n")
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                obs = f"Invalid JSON response: {raw[:200]}"
                history.append({"role": "user", "content": f"Observation: {obs}"})
                continue

            thought = parsed.get("thought", "")
            print(f"  [iter {iteration}] Thought: {thought}")

            if "action" in parsed:
                tool_name = parsed["action"]
                tool_args = parsed.get("args", {})
                observation = self.mcp_client.call_tool(tool_name, tool_args)
                print(f"             Action:      {tool_name}({tool_args})")
                print(f"             Observation: {observation[:120]}{'...' if len(observation) > 120 else ''}")
                history.append({"role": "user", "content": f"Observation: {observation}"})

            elif "answer" in parsed:
                return parsed["answer"]

        return "Max iterations reached."


# ─────────────────────────────────────────────────────────────────────────────
# DEMO DATA & SETUP
# ─────────────────────────────────────────────────────────────────────────────

# In-memory audit log — demonstrates tool side effects
_AUDIT_LOG: list[dict] = []


def _search_policy(topic: str) -> str:
    """Simulate a policy database search."""
    policies = {
        "refund":   "Customers may return physical items within 30 days. "
                    "Digital goods are refundable within 14 days if not downloaded.",
        "shipping": "Standard shipping is free on orders over $50. "
                    "Express shipping costs $12.99 and arrives in 2 business days.",
        "privacy":  "We never sell customer data. All data is encrypted at rest "
                    "and in transit. You can request deletion at privacy@acmecorp.com.",
        "support":  "Support is available Monday–Friday 9am–6pm EST. "
                    "Response time is under 4 hours for Pro tier, 24 hours for Free.",
    }
    topic_lower = topic.lower()
    for key, text in policies.items():
        if key in topic_lower:
            return text
    matches = [v for k, v in policies.items() if any(w in k for w in topic_lower.split())]
    return matches[0] if matches else f"No policy found for topic: '{topic}'. Try: refund, shipping, privacy, support."


def _log_query(query: str, result: str) -> str:
    """Log a query to the audit trail — demonstrates a tool with side effects."""
    entry = {
        "query":     query,
        "result":    result[:80] + "..." if len(result) > 80 else result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _AUDIT_LOG.append(entry)
    print(f"  [SIDE EFFECT] Audit entry written: query='{query}' at {entry['timestamp']}")
    return f"Logged. Total audit entries: {len(_AUDIT_LOG)}"


def build_company_server() -> MCPServer:
    """Build a Company Knowledge MCP server with tools, resources, and prompts."""
    server = MCPServer("CompanyKnowledgeServer")

    # ── Tools (have side effects or compute results) ──────────────────────────
    server.register_tool(MCPTool(
        name="search_policy",
        description="Search company policy by topic (refund, shipping, privacy, support).",
        input_schema={
            "type": "object",
            "properties": {"topic": {"type": "string", "description": "Policy topic to search"}},
            "required": ["topic"],
        },
        fn=_search_policy,
    ))
    server.register_tool(MCPTool(
        name="log_query",
        description="Log a query and its result to the audit trail. Use after every search.",
        input_schema={
            "type": "object",
            "properties": {
                "query":  {"type": "string"},
                "result": {"type": "string"},
            },
            "required": ["query", "result"],
        },
        fn=_log_query,
    ))

    # ── Resources (read-only static data) ────────────────────────────────────
    server.register_resource(MCPResource(
        uri="resource://company/faq",
        description="Company FAQ — frequently asked questions and answers.",
        content=(
            "Q: How do I contact support?\n"
            "A: Email support@acmecorp.com or call 1-800-ACME.\n\n"
            "Q: What payment methods do you accept?\n"
            "A: Visa, Mastercard, PayPal, and bank transfer.\n\n"
            "Q: Do you ship internationally?\n"
            "A: Yes, to 42 countries. International shipping takes 7-14 business days."
        ),
    ))
    server.register_resource(MCPResource(
        uri="resource://company/pricing",
        description="Current pricing table for AcmeCorp product tiers.",
        content=(
            "Free tier:       $0/month — 5 GB storage, community support\n"
            "Pro tier:        $29/month — 100 GB storage, priority support, API access\n"
            "Enterprise tier: Contact sales — unlimited storage, SLA, dedicated account manager"
        ),
    ))

    # ── Prompts (named templates) ─────────────────────────────────────────────
    server.register_prompt(MCPPrompt(
        name="summarise_policy",
        description="Summarise a company policy topic in 2 bullet points.",
        template="Summarise the AcmeCorp {topic} policy in exactly 2 concise bullet points.",
    ))

    return server


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print(THICK)
    print("MCP Integration Exercise (§6)")
    print(f"Model: {SETTINGS.model}")
    print(THICK)

    genai_client = genai.Client(api_key=SETTINGS.require_api_key())
    server = build_company_server()
    client = MCPClient(server)

    # ── §6.6  Capability Negotiation Handshake ────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§6.6  Capability Negotiation Handshake")
    print(DIVIDER)
    print(f"Client → initialize  {{protocolVersion: '{MCPServer.PROTOCOL_VERSION}', capabilities: ...}}")
    negotiated = client.connect()
    caps = {k for k, v in negotiated.get("capabilities", {}).items() if v is not None}
    print(f"Server ← protocolVersion: {negotiated['protocolVersion']}")
    print(f"         serverInfo: {negotiated['serverInfo']}")
    print(f"Negotiated capabilities: {', '.join(sorted(caps))}")

    # ── §6.2  Tool Discovery ──────────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§6.2  Tool Discovery (dynamic — agent never hardcodes names)")
    print(DIVIDER)
    tools = client.list_tools()
    print(f"Discovered {len(tools)} tool(s):")
    for t in tools:
        props = t.get("inputSchema", {}).get("properties", {})
        arg_names = ", ".join(props.keys())
        print(f"  - {t['name']}({arg_names}): {t['description']}")

    # ── §6.3  Resources vs Tools ──────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§6.3  Resources (read-only) vs Tools (side effects)")
    print(DIVIDER)
    resources = client.list_resources()
    print(f"Discovered {len(resources)} resource(s):")
    for r in resources:
        print(f"  - {r['uri']} — {r['description']}")

    print("\nReading resource://company/faq  (no side effects):")
    faq = client.read_resource("resource://company/faq")
    for line in faq.splitlines()[:3]:
        print(f"  {line}")
    print("  ...")

    print("\nCalling tool 'log_query'  (has side effects — writes to audit log):")
    result = client.call_tool("log_query", {"query": "demo-probe", "result": "test"})
    print(f"  → {result}")

    # ── §6.4  Prompts as First-Class Citizens ─────────────────────────────────
    print(f"\n{DIVIDER}")
    print("§6.4  Prompts as First-Class Citizens")
    print(DIVIDER)
    prompts = client.list_prompts()
    print(f"Discovered {len(prompts)} prompt(s): {', '.join(p['name'] for p in prompts)}")
    rendered = client.get_prompt("summarise_policy", {"topic": "refund"})
    print(f"Rendered prompt for topic='refund':")
    print(f"  \"{rendered}\"")

    # ── Gemini Agent with Dynamic Tool Discovery ──────────────────────────────
    print(f"\n{DIVIDER}")
    print("Gemini Agent using Dynamic MCP Tool Discovery")
    print(DIVIDER)
    print("The agent's system prompt is built entirely from discovered tool descriptions.")
    print("It has no hardcoded knowledge of what tools exist.\n")

    goal = "What is the refund policy for digital goods, and log that query."
    print(f"Goal: \"{goal}\"\n")

    agent = MCPAgent(genai_client, client)
    answer = agent.run(goal)

    print(f"\n{THICK}")
    print("ANSWER")
    print(THICK)
    print(answer)

    if _AUDIT_LOG:
        print(f"\n{DIVIDER}")
        print(f"Audit log ({len(_AUDIT_LOG)} entr{'y' if len(_AUDIT_LOG) == 1 else 'ies'}):")
        for entry in _AUDIT_LOG:
            print(f"  [{entry['timestamp']}] {entry['query']}")


if __name__ == "__main__":
    main()
