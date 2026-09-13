---
description: Analyze code at any scope — file, package, or project — to understand, question, and learn from it. Pass a local path or a GitHub URL (file, directory, or repo). Single files are analyzed inline; packages and projects are written to docs/.
argument-hint: <file.java | src/package/ | . | https://github.com/owner/repo/...>
disable-model-invocation: true
---

# /code-explorer — Code Explorer

**Goal:** help you understand, question, and reason about code you built with LLMs — not just describe or rewrite it.

---

## Step 1 — Help / No Arguments

If `$ARGUMENTS` is empty or `--help`, print the following and stop:

```
/code-explorer — Code Explorer
──────────────────────────────────────────────────────────────────
Analyze code at any scope to understand, question, and learn from it.

USAGE
  /code-explorer <target>

TARGETS
  Single file   Path with a file extension
                e.g. src/main/java/com/example/MyService.java

  Package       A directory path
                e.g. src/main/java/com/example/matching/

  Project       . or empty — analyze the entire project

  GitHub URL    A GitHub URL for a file, directory, or repo
                e.g. https://github.com/owner/repo
                e.g. https://github.com/owner/repo/blob/main/File.java
                e.g. https://github.com/owner/repo/tree/main/src/pkg/

FLAGS
  --shallow     Quick overview: 3 sections instead of full analysis
  --full        Force full analysis even on previously cached targets

OUTPUT
  Single file  → inline in this conversation
  Package      → docs/<package_name>.md
  Project      → docs/<project_name>.md

GITHUB MCP SERVERS
  github.com URLs     → github-com MCP server
  Enterprise/internal → github-wdf (primary), github-tools (fallback)
──────────────────────────────────────────────────────────────────
```

---

## Step 2 — Detect Input Type

Examine `$ARGUMENTS`.

**Is it a GitHub URL?**
Yes if it starts with `https://github` or the hostname contains `github`.

Parse the URL:
- Extract `owner`, `repo`, `ref` (the branch/tag/commit — the segment after `/blob/` or `/tree/`), and `file_path` (everything after the ref segment).
- If `ref` is absent (repo root URL), default to `HEAD`.

**MCP server to use:**
| URL domain | Server |
|------------|--------|
| `github.com` | `github-com` |
| Any other host | `github-wdf` (fall back to `github-tools` if it fails) |

**Is it a local path?**
Everything else.

---

## Step 2.5 — Load Project Context

**Read `.claude/CLAUDE.md`** if it exists and is non-empty:
- Extract architecture notes, known patterns, and prior analysis summaries (sections like `## Code Explorer Cache`)
- Store as `KNOWN_CONTEXT` — pass verbatim to every agent prompt so agents skip re-discovering documented facts

**Determine the vocabulary context file path (`VOCAB_CONTEXT_PATH`):**
- Local path → `.claude/CONTEXT.md`
- GitHub URL → `.claude/context/<owner>-<repo>.md` (e.g., `mattpocock/skills` → `.claude/context/mattpocock-skills.md`)

Read `VOCAB_CONTEXT_PATH` if it exists and is non-empty:
- Extract patterns, vocabulary terms, anti-patterns, and ADR entries
- Store as `VOCAB_CONTEXT` — pass verbatim to every agent prompt so agents reference named concepts without re-explaining them
- If `VOCAB_CONTEXT` contains a `LANGUAGE` entry, **skip Step 3.5 entirely** and use the cached value

**Determine the output docs path (`OUTPUT_BASE`):**
- Local path → `docs/`
- GitHub URL → `docs/external/<owner>-<repo>/` (e.g., `docs/external/mattpocock-skills/`)

Create `OUTPUT_BASE` directory if it does not exist.

If neither CLAUDE.md nor VOCAB_CONTEXT_PATH exists or both are empty: set `KNOWN_CONTEXT = ""`, `VOCAB_CONTEXT = ""` and proceed.

---

## Step 3 — Detect Scope

**Parse flags first:**
- If `--shallow` is in `$ARGUMENTS`: set `SHALLOW = true`, remove from args
- If `--full` is in `$ARGUMENTS`: set `FULL = true`, remove from args
- Otherwise: `SHALLOW = false`, `FULL = false`

**Smart shallow default (Package / Project scope only):**
After detecting scope, if `FULL = false` and `KNOWN_CONTEXT` contains a cache entry for the target package or project:
- Set `SHALLOW = true` automatically
- Inform the user: "Cached analysis found — running in shallow mode. Pass `--full` to override."

### From a GitHub URL

| URL pattern | Scope |
|-------------|-------|
| `/blob/<ref>/<path>` where path has a file extension | Single File |
| `/tree/<ref>/<path>` | Package |
| `/<owner>/<repo>` only — no `/blob/` or `/tree/` | Project |

### From a local path

| Condition | Scope |
|-----------|-------|
| Has a source file extension (.java, .ts, .js, .tsx, .jsx, .py, .kt, .go, .rs, .cs, .rb, .swift, .cpp, .c, .h) | Single File |
| Directory: no extension, ends with `/`, or LS confirms it's a directory | Package |
| `.` or empty | Project |

If ambiguous: try `Read` first. If that succeeds → Single File. If it fails → use `LS` to confirm directory → Package.

---

## Step 3.5 — Detect Language & Ecosystem

**Skip if `VOCAB_CONTEXT` already defines `LANGUAGE`** — use the cached value and proceed directly to Step 4.

Otherwise examine file extensions in the target:

| Extensions found | LANGUAGE | ECOSYSTEM_HINTS |
|-----------------|----------|-----------------|
| `.java`, `.kt` | Java / Kotlin | Spring annotations (@Service, @Bean, @Repository), Maven/Gradle structure, DI patterns, checked exceptions, anemic domain model risk |
| `.ts`, `.tsx`, `.js`, `.jsx` | TypeScript / JavaScript | Express middleware, React component lifecycle, decorators, async/await patterns, implicit any, module exports |
| `.py` | Python | Django/FastAPI route decorators, type hints, dataclasses, mutable default args, bare except clauses |
| `.go` | Go | Interfaces, goroutines, channels, error-as-value pattern, goroutine leaks |
| `.rs` | Rust | Ownership, traits, Result/Option, lifetimes |
| Mixed / other | General | No specific hints |

Store `LANGUAGE` and `ECOSYSTEM_HINTS` — pass both to every agent prompt.

---

## Step 4 — Fetch Content (GitHub only)

Use `get_file_contents` on the selected MCP server.

- **Single file**: fetch the file at `file_path`.
- **Package**: fetch the directory at `file_path` to get the listing, then fetch each relevant source file.
- **Project**: fetch the repo root, then explore key subdirectories to map the structure.

---

## Step 4.5 — Check Existing Analysis (Package / Project only)

Determine the output file path: `<OUTPUT_BASE>/<name>.md` (where `<name>` is the directory name for package scope, or the project/repo name for project scope).

If this file already exists:
- Inform the user: "Analysis already exists at `<OUTPUT_BASE>/<name>.md`."
- Ask: "Re-analyze from scratch, or update specific sections? (scratch / update)"
  - **scratch**: proceed normally, overwrite the file
  - **update**: read the existing file, ask which sections to refresh, re-run only those analysis phases, and merge the updates into the existing file
- If the user does not respond within the turn: proceed with scratch

If the file does not exist: proceed normally.

---

## Step 5 — Analyse

---

### SINGLE FILE

Read the file (locally or from fetched GitHub content).

**Line-count threshold:**
Count the lines in the file:
- **< 50 lines** → Quick Summary mode: produce only sections 1 (Overview & Mental Model), 4 (Design & Reasoning), and 8 (Learning). Skip the rest.
- **50–500 lines** → Full 8-section analysis (default).
- **> 500 lines** → Auto-spawn 2 `code-explorer-analyst` agents in parallel even though scope is "single file":
  - Agent 1 — "Structure, responsibilities, flow, and dependencies"
  - Agent 2 — "Quality, failure paths, improvements, and learning"
  Synthesize their output into the full 8-section structure.

**If `SHALLOW = true`:** always produce only sections 1, 4, and 8, regardless of line count.

**Git change history (local files only):**
Run: `git log --oneline -10 -- <file_path>`
Store output as `CHANGE_HISTORY`. Include a one-line note in section 1 (Overview) if the history reveals notable patterns (e.g., "frequently modified", "single author", "recent rewrite"). Skip if the file is from a GitHub URL.

Write the analysis to `docs/explanation.md`. Create the file if it does not exist; overwrite it if it does. Do not show the full analysis inline — only confirm to the user: "Analysis written to docs/explanation.md."

Use this structure for the file:

---

### 📄 Code Explorer: `<filename>`

#### Table of Contents
1. [Overview & Mental Model](#1-overview--mental-model)
2. [Responsibilities & Flow](#2-responsibilities--flow)
3. [Dependencies](#3-dependencies)
4. [Design & Reasoning](#4-design--reasoning)
5. [Complexity & Quality](#5-complexity--quality)
6. [Failure, Testing & Change Impact](#6-failure-testing--change-impact)
7. [Improvements & Experiments](#7-improvements--experiments)
8. [Learning](#8-learning)

---

#### 1. Overview & Mental Model

2–3 sentences max: what this file does, what problem it solves, and one concrete mental model or analogy. No elaboration beyond that.

#### 2. Responsibilities & Flow

For each class and important function/method, state its responsibility, inputs, and outputs in 1–2 sentences.

Then trace the **main execution flow** from entry point to output.
Use an ASCII diagram where it adds genuine clarity:

```
[Input] --> [StepA] --> [StepB] --> [Output]
                           |
                        [Branch]
```

#### 3. Dependencies

| Dependency | Type | Role |
|------------|------|------|
| ... | Internal / External / Framework | ... |

#### 4. Design & Reasoning

For each key design decision, produce a structured block:

**[Decision name]**
- **What:** what pattern or principle is applied
- **Why:** why this approach was likely chosen
- **Alternative:** what a simpler approach would look like
- **Trade-off:** what you gain and lose with each

#### 5. Complexity & Quality

- Time and space complexity of key operations (where non-trivial)
- Good design decisions and why they work
- Code smells, unnecessary complexity, or tight coupling
- Overall assessment (brief)

#### 6. Failure, Testing & Change Impact

- What edge cases and failure paths are present or unhandled?
- What is not validated at system boundaries?
- What would a meaningful test suite cover?
- If you changed this component, what else could break?

#### 7. Improvements & Experiments

Present as a table. No code blocks — describe changes in plain language.

| Improvement | Trade-off | How to validate |
|-------------|-----------|-----------------|
| ... | ... | ... |

#### 8. Learning

**Concepts in this file:**

| Concept | What it means here | Concrete example from the code |
|---------|-------------------|-------------------------------|
| ... | ... | ... |

**Questions to deepen your understanding:**
1. ...
2. ...
3. ...

---

---

### PACKAGE

**Setup:** create a todo list with the following tasks:
1. List all files in the package
2. Spawn parallel analysis agents
3. Read key files from agent findings
4. Synthesize and write docs file

**Phase 1 — List and filter files:**
Use LS (or directory listing from GitHub) to identify all source files in the package/directory.

**Apply exclusion list — remove:**
- Directories: `test/`, `tests/`, `node_modules/`, `target/`, `.git/`, `dist/`, `build/`, `vendor/`, `generated/`
- File patterns: `*Test.java`, `*Spec.java`, `*Mock*.java`, `*IT.java`, `*.generated.*`, `*Fixture*`
- Non-source: `*.xml`, `*.json`, `*.yaml`, `*.yml`, `*.md`, `*.txt`, `Dockerfile`, lockfiles

**Group DTO clusters (token saving):**
Identify files that are pure data containers — classes with only fields, getters, setters, and no logic (matching patterns like `*List.java`, `*Response.java`, `*Request.java`, `*DTO.java`, `*Dto.java`). Do not include these in individual agent FILE_SLICEs. Instead, count them and record a one-line group summary: "N DTO classes — [pattern name, e.g., `@Getter @Setter @JsonIgnoreProperties`], no logic." Include this summary in the Structure section; pass only the summary to agents, not the individual files.

**Build directory tree snapshot:**
Format the filtered file list as a compact tree (relative paths, one per line). Store as `DIRECTORY_TREE` — include this verbatim in every agent prompt so agents skip their own LS/Glob discovery.

**Dynamic agent count (cap: 10 files per agent):**
Count filtered source files (N):
- N ≤ 10 → 2 agents, split files evenly
- N 11–20 → 3 agents, ~7 files each
- N > 20 → 4 agents, ~10 files each (drop lowest-priority files if N > 40)

**Phase 2 — Parallel analysis:**
Spawn agents (count from above) in parallel. Assign each a file slice and a focus:
- Agent 1 — "Data model and key entities" (receives first slice)
- Agent 2 — "Main execution flows and service logic" (receives second slice)
- Agent 3 — "Dependencies, design patterns, and design decisions" (if N > 10)
- Agent 4 — "Quality, risks, and failure paths" (if N > 20)

Each agent prompt must include: `FILE_SLICE_TREE` (only the subtree relevant to their assigned files — not the full DIRECTORY_TREE), `LANGUAGE`, `ECOSYSTEM_HINTS`, `KNOWN_CONTEXT`, `VOCAB_CONTEXT`, `FILE_SLICE`, and the assigned focus.

**Phase 3 — Read key files:**
After agents complete, read every file they flag as important to build full understanding before writing.

**Phase 4 — Write output:**
Determine the package name from the directory name. Create `<OUTPUT_BASE>/<package_name>.md`:

```markdown
# Package Analysis: `<package_name>`

> Generated by /code-explorer | Scope: Package

## Table of Contents
1. [Package Overview & Mental Model](#1-package-overview--mental-model)
2. [Structure & Relationships](#2-structure--relationships)
3. [Design & Reasoning](#3-design--reasoning)
4. [Quality & Risks](#4-quality--risks)
5. [Testing & Change Impact](#5-testing--change-impact)
6. [Improvements & Experiments](#6-improvements--experiments)
7. [Learning](#7-learning)

---

## 1. Package Overview & Mental Model

Purpose of the package, its role in the broader system, and a simple mental model.

## 2. Structure & Relationships

### Files & Modules

| File | Purpose | Key Responsibilities |
|------|---------|---------------------|
| ... | ... | ... |

### Class Diagram

```mermaid
classDiagram
  ...
```

### Data Flow

```mermaid
flowchart LR
  ...
```

## 3. Design & Reasoning

Design patterns, principles applied, reasons for the current structure, and simpler alternatives with trade-offs.

## 4. Quality & Risks

| Dimension | Assessment | Notes |
|-----------|-----------|-------|
| Cohesion | ... | ... |
| Coupling | ... | ... |
| Maintainability | ... | ... |
| Extensibility | ... | ... |
| Overengineering | ... | ... |

Code/design smells, failure paths, reliability concerns.

## 5. Testing & Change Impact

Important test boundaries, coverage gaps, missing edge cases, and the blast radius of key changes.

## 6. Improvements & Experiments

Alternative designs with trade-offs and small experiments that would clarify the consequences.

## 7. Learning

**Key Concepts:**

| Concept | What it means here | Concrete example |
|---------|-------------------|-----------------|
| ... | ... | ... |

**Questions to deepen your understanding:**
1. ...
2. ...
3. ...

## 8. This Run Taught Me

**New patterns discovered:**
- ...

**Terms coined or refined:**
- ...

**Anti-patterns seen:**
- ...

**Potential ADRs (improvements that were rejected with a load-bearing reason):**
- ...
```

**Phase 5 — Write architecture summary to CLAUDE.md:**
Append to `.claude/CLAUDE.md` (local runs only — skip for GitHub URL runs). Do not overwrite existing content — append only:

```
## Code Explorer Cache

### <package_name> — <ISO date>
- **Scope:** package
- **Language:** <LANGUAGE>
- <3–5 bullet points: main patterns, key classes, notable design decisions, important dependencies>
- **Output:** docs/<package_name>.md
```

**Phase 6 — Self-improvement:**
1. Invoke the `learn-code-explorer` agent, passing:
   - `ANALYSIS_OUTPUT`: the path of the docs file just written
   - `TAUGHT_ME`: the full "This Run Taught Me" section from the docs file
   - `CONTEXT_FILE`: `VOCAB_CONTEXT_PATH` (`.claude/CONTEXT.md` for local, `.claude/context/<owner>-<repo>.md` for GitHub URL)
2. Ask the user: "Should I record any rejected improvements as ADRs to prevent re-suggesting them in future runs? (yes / no)"
   - If yes: ask which improvement, then write `.claude/docs/adr/<kebab-title>-<ISO-date>.md` and add a one-line entry to `## Architecture Decisions (ADRs)` in `VOCAB_CONTEXT_PATH`
   - If no: proceed

**Setup:** create a todo list with the following tasks:
1. Map project structure
2. Spawn parallel analysis agents
3. Read key files from agent findings
4. Determine project name
5. Write docs file

**Phase 1 — Map and filter structure:**
Use LS / Glob (or GitHub directory listing) to:
- Identify major packages and modules
- Identify configuration and build files (pom.xml, package.json, build.gradle, mta.yaml, Dockerfile, etc.)
- Identify entry points (main classes, route definitions, service exports)

**Apply exclusion list — remove from the file inventory:**
- Directories: `test/`, `tests/`, `node_modules/`, `target/`, `.git/`, `dist/`, `build/`, `vendor/`, `generated/`
- File patterns: `*Test.java`, `*Spec.java`, `*Mock*.java`, `*IT.java`, `*.generated.*`, `*Fixture*`
- Non-source: `*.xml`, `*.json`, `*.yaml`, `*.yml`, `*.md`, `*.txt`, `Dockerfile`, lockfiles
  (exception: keep `pom.xml`, `package.json`, `build.gradle`, `mta.yaml` for config analysis)

**Build directory tree snapshot:**
Format the filtered file list as a compact tree (relative paths, one per line). Store as `DIRECTORY_TREE` — include this verbatim in every agent prompt so agents skip their own LS/Glob discovery.

**Dynamic agent count (cap: 10 files per agent):**
Count filtered source files (N):
- N ≤ 10 → 2 agents, split files evenly
- N 11–20 → 3 agents, ~7 files each
- N > 20 → 4 agents, ~10 files each (drop lowest-priority files if N > 40)

**Phase 2 — Parallel analysis:**
Spawn agents (count from above) in parallel. Assign each a file slice and a focus:
- Agent 1 — "Overall architecture, major packages, and module boundaries"
- Agent 2 — "End-to-end data flows from API/entry points to data storage"
- Agent 3 — "Design patterns, key architectural decisions, and configuration" (if N > 10)
- Agent 4 — "Quality, observability, testing, and failure paths" (if N > 20)

Each agent prompt must include: `FILE_SLICE_TREE` (only the subtree relevant to their assigned files), `LANGUAGE`, `ECOSYSTEM_HINTS`, `KNOWN_CONTEXT`, `VOCAB_CONTEXT`, `FILE_SLICE`, and the assigned focus.

**Phase 3 — Read key files:**
Read all entry points, core service files, and config files flagged by agents.

**Phase 4 — Determine project name:**
Use the root directory name, the `name` field from a config file (package.json, pom.xml), or the repo name.

**Phase 5 — Write output:**
Create `<OUTPUT_BASE>/<project_name>.md`:

```markdown
# Project Analysis: `<project_name>`

> Generated by /code-explorer | Scope: Project

## Table of Contents
1. [Project Overview & Mental Model](#1-project-overview--mental-model)
2. [Architecture & Data Flow](#2-architecture--data-flow)
3. [Design & Reasoning](#3-design--reasoning)
4. [Quality, Performance & Risks](#4-quality-performance--risks)
5. [Testing, Observability & Change Impact](#5-testing-observability--change-impact)
6. [Improvements & Experiments](#6-improvements--experiments)
7. [Learning](#7-learning)

---

## 1. Project Overview & Mental Model

Purpose, major responsibilities, system boundaries, and a simple mental model of what this project is and does.

## 2. Architecture & Data Flow

### Package & Module Map

| Package / Module | Purpose | Key Components |
|-----------------|---------|---------------|
| ... | ... | ... |

### Architecture Diagram

```mermaid
architecture-beta
  ...
```

### Representative End-to-End Flow

```mermaid
sequenceDiagram
  ...
```

## 3. Design & Reasoning

Architectural patterns (e.g., layered, hexagonal, event-driven), key design decisions, principles applied, and why this architecture may have been chosen. What simpler or different alternatives exist?

## 4. Quality, Performance & Risks

| Dimension | Assessment | Notes |
|-----------|-----------|-------|
| Cohesion | ... | ... |
| Coupling | ... | ... |
| Scalability | ... | ... |
| Maintainability | ... | ... |
| Performance | ... | ... |
| Security | ... | ... |
| Reliability | ... | ... |
| Technical Debt | ... | ... |
| Overengineering | ... | ... |

## 5. Testing, Observability & Change Impact

Testing coverage, logging and monitoring, error handling patterns, and the blast radius of important changes.

## 6. Improvements & Experiments

Alternative architectures and designs with trade-offs. Small experiments that help understand the consequences of a change without full commitment.

## 7. Learning

**Key Concepts:**

| Concept | What it means here | Concrete example |
|---------|-------------------|-----------------|
| ... | ... | ... |

**Questions to think about:**
1. ...
2. ...
3. ...

**What to explore next:**
- ...

## 8. This Run Taught Me

**New patterns discovered:**
- ...

**Terms coined or refined:**
- ...

**Anti-patterns seen:**
- ...

**Potential ADRs:**
- ...
```

**Phase 6 — Write architecture summary to CLAUDE.md:**
Append to `.claude/CLAUDE.md` (local runs only — skip for GitHub URL runs). Do not overwrite existing content — append only:

```
## Code Explorer Cache

### <project_name> — <ISO date>
- **Scope:** project
- **Language:** <LANGUAGE>
- <3–5 bullet points: architectural style, major modules, entry points, key dependencies, notable design decisions>
- **Output:** docs/<project_name>.md
```

**Phase 7 — Self-improvement:**
1. Invoke the `learn-code-explorer` agent, passing:
   - `ANALYSIS_OUTPUT`: the path of the docs file just written
   - `TAUGHT_ME`: the full "This Run Taught Me" section from the docs file
   - `CONTEXT_FILE`: `VOCAB_CONTEXT_PATH` (`.claude/CONTEXT.md` for local, `.claude/context/<owner>-<repo>.md` for GitHub URL)
2. Ask the user: "Should I record any rejected improvements as ADRs to prevent re-suggesting them in future runs? (yes / no)"
   - If yes: ask which improvement, then write `.claude/docs/adr/<kebab-title>-<ISO-date>.md` and add a one-line entry to `## Architecture Decisions (ADRs)` in `VOCAB_CONTEXT_PATH`
   - If no: proceed

---

---

## General Guidelines

Apply throughout all analyses:

**Inline highlights for facts vs. intent:**
- <mark style="background:#d4edda">observed fact</mark> — soft green: directly readable from the code
- <mark style="background:#fff3cd">inferred interpretation</mark> — soft amber: reasoned, not stated

Wrap only the claim itself, not the whole sentence. Example:
> <mark style="background:#d4edda">The buffer is allocated once outside the loop.</mark> <mark style="background:#fff3cd">This was likely chosen to keep heap usage bounded regardless of file size.</mark>

| Principle | How to apply |
|-----------|-------------|
| Facts vs. intent | Wrap observed facts with `<mark style="background:#d4edda">…</mark>` and inferred interpretations with `<mark style="background:#fff3cd">…</mark>` — inline on the claim, not as section labels |
| VOCAB_CONTEXT | Reference terms in VOCAB_CONTEXT by name — do not re-explain concepts already defined there. Say "this follows the [pattern name]" and move on |
| Depth vocabulary | Use precision terms: **shallow module** (interface nearly as complex as the implementation), **seam** (where behaviour can change without editing that place), **leverage** (capability per unit of interface), **locality** (change concentrates in one place). Replace generic "code smell" or "tight coupling" with these |
| DTO grouping | Summarize clusters of pure data classes as one group entry — do not analyze each individually |
| Progressive disclosure | High-level mental model first. Important details second. Internals last |
| Trade-offs not verdicts | "A is simpler; B handles more cases. Given the context here, A is better *because*..." |
| Right diagram type | Flow = processes; Sequence = actor interactions; Class = structure; Architecture = system layout |
| Tables for comparisons | Dependencies, quality dimensions, concept lists — use tables |
| No rewrites | Only show code to illustrate a specific improvement; never rewrite the file |
| Concise & scannable | Headers, short bullets, 1–2 sentence paragraphs |
| Learning mindset | Explain each concept where it appears. Include a concrete example from the code |
