# Claude Code — Plan Mode Guide

How to explore a problem and produce a clear, actionable implementation plan, scaled to project complexity.

---

## The core principle

Plan quality = question quality. A vague prompt produces a hedged plan that tries to cover every possibility. A precise prompt — specific file, specific behavior, specific constraint — produces a direct, readable plan.

Before entering Plan Mode, know:
1. **What** you want changed (not "improve X", but "change X so that Y")
2. **Where** it lives (file paths, function names if known)
3. **What constraints** apply (must not break Z, must stay under N lines, etc.)

---

## Easy Project

**Example task:** Add a `--verbose` flag to a CLI tool that prints extra debug output.

### Exploration needed: minimal

You already know the entry point and what the change looks like. No need to map the codebase first.

### Prompt to use

```
I want to add a --verbose flag to the CLI in src/cli.ts.
When the flag is set, the app should print each step it takes to stdout.

Create a plan. Format:
1. Goal (one sentence)
2. Files to change (with line numbers if known)
3. Ordered steps
4. How to verify it works

No alternatives. Pick the simplest approach.
```

### What a good plan looks like

```
1. Goal
   Add --verbose flag that enables step-level stdout logging.

2. Files
   - src/cli.ts        — add flag to arg parser
   - src/runner.ts     — add conditional log calls

3. Steps
   a. In cli.ts:18, add `--verbose` to the yargs config with type boolean, default false
   b. Pass the flag value down to `runPipeline()` in cli.ts:42
   c. In runner.ts, wrap each step's log statement: `if (verbose) console.log(...)`

4. Verify
   Run: node dist/cli.js --verbose
   Expect step-by-step output in terminal.
   Run: node dist/cli.js (no flag)
   Expect no extra output.
```

### What to avoid

- Don't ask Claude to "improve the CLI" — that's open-ended and invites scope creep.
- Don't let Claude propose a logging library if you just need `console.log`.
- If the plan has more than ~5 steps for this kind of task, reject it: "Too long. This is just a flag + a few log calls. Replan."

---

## Medium Project

**Example task:** Add JWT-based authentication to an existing Express REST API.

### Exploration needed: moderate

You know the goal but not every file it touches. Spend 2–3 minutes mapping the codebase before planning.

### Step 1 — Explore first (outside Plan Mode)

Ask Claude in normal chat:

```
Before we plan anything, map the relevant parts of this codebase for me:
- Where are the Express route definitions?
- Is there any existing auth middleware?
- Where is the user model / DB access layer?
- What does the request lifecycle look like for a protected route?

Read the files, don't guess.
```

Read the response. Correct any wrong assumptions. Now you know:
- `src/routes/` has the routes
- `src/middleware/` is empty (no existing auth)
- `src/models/user.ts` has the User model with `passwordHash`

### Step 2 — Enter Plan Mode with context

```
I want to add JWT authentication to this Express API. Here's what I know:
- Routes are in src/routes/
- src/middleware/ is empty — that's where the new auth middleware will go
- User model is in src/models/user.ts and has a passwordHash field
- We're using the jsonwebtoken npm package (already installed)

Plan the implementation. Format:
1. Goal
2. New files to create (with purpose)
3. Existing files to modify (with specific locations)
4. Ordered steps
5. Edge cases to handle
6. How to verify

Constraints:
- Don't touch the existing route files except to add the middleware
- No refresh tokens — just access tokens for now
- Token expiry: 1 hour
```

### What a good plan looks like

```
1. Goal
   Protect API routes with JWT; issue tokens at POST /auth/login.

2. New files
   - src/middleware/auth.ts     — verifyToken middleware
   - src/routes/auth.ts        — POST /login route

3. Existing files to modify
   - src/app.ts:34             — mount auth router
   - src/app.ts:41             — apply verifyToken to /api/* routes

4. Steps
   a. Create src/middleware/auth.ts: extract Bearer token, verify with jwt.verify,
      attach decoded payload to req.user, call next() or return 401
   b. Create src/routes/auth.ts: find user by email, compare password with bcrypt,
      sign JWT with 1h expiry, return { token }
   c. In src/app.ts:34, add: app.use('/auth', authRouter)
   d. In src/app.ts:41, add: app.use('/api', verifyToken)

5. Edge cases
   - Missing or malformed Authorization header → 401 "No token"
   - Expired token → 401 "Token expired"
   - User not found at login → 401 (don't reveal whether email or password is wrong)

6. Verify
   POST /auth/login with valid credentials → get token
   GET /api/users with token → 200
   GET /api/users without token → 401
   GET /api/users with expired token → 401
```

### What to avoid

- Don't skip the exploration step — without it, the plan will have placeholders ("in the auth file, wherever that is") and vague steps.
- If Claude proposes refresh tokens, session stores, or OAuth: "Out of scope. Access tokens only. Replan."
- If Claude lists more than ~8 steps, it's over-engineering. Push back: "Combine any steps that are in the same file."

---

## Complex Project

**Example task:** Migrate a monolithic Node.js app to a service-based architecture, extracting the payments module into a separate service that communicates over a message queue.

### Exploration needed: thorough

You don't yet know all the dependencies. A rushed plan here will miss coupling that causes failures mid-migration. Spend real time mapping first.

### Step 1 — Deep exploration (outside Plan Mode)

Use the Explore agent or ask Claude a series of focused questions:

```
Explore the codebase and answer each question specifically. Read the files, don't summarize from filenames:

1. What files does the payments module touch directly?
2. What other modules call into payments (grep for require/import of payments)?
3. Does payments write to the database directly, or through a shared ORM layer?
4. What events or side effects does a payment trigger (emails, inventory updates, webhooks)?
5. What shared utilities does payments use (auth, logging, config)?
6. What does the test coverage look like for payments?
```

Review the answers carefully. Note every coupling point — each one is a migration risk.

### Step 2 — Resolve ambiguities before planning

If the exploration reveals unknowns, resolve them now:

```
You found that payments calls userService.getById() directly.
Two options:
a. payments-service calls back to the main app over HTTP to get user data
b. we duplicate the user lookup in payments-service

Which approach fits this architecture better and why?
Don't plan yet — just answer this question.
```

Get alignment on the approach before generating a plan. This is cheaper than replanning after seeing option B listed as "alternatively...".

### Step 3 — Enter Plan Mode with full context

```
I'm extracting the payments module into a standalone Node.js service.
Here's what the exploration revealed:

COUPLING POINTS:
- payments/index.ts imports from shared/db (Prisma client)
- payments/index.ts calls userService.getById() — we'll resolve this via HTTP call back to main app
- payments triggers an email via shared/mailer — we'll keep mailer in main app and trigger via event
- payments writes to tables: payments, payment_events (no other module writes these)

MESSAGE QUEUE: RabbitMQ (already in docker-compose)

DECISION: payments-service is authoritative for payment data; main app publishes payment.requested events, payments-service consumes them and publishes payment.completed back.

Create a phased implementation plan. Format:
1. Goal
2. Phase breakdown (why phases, not one big step)
3. For each phase:
   a. What changes
   b. Files created / modified
   c. How to verify this phase before moving on
4. Rollback strategy if phase 2 or 3 fails
5. Things that can break (coupling risks)

Constraints:
- Each phase must leave the system in a working state
- Don't migrate the DB schema until phase 3
- Main app must continue to work throughout
```

### What a good plan looks like

```
1. Goal
   Extract payments into payments-service; main app communicates via RabbitMQ events.
   Zero downtime: system works after every phase.

2. Why phases
   Big-bang migrations break things in unpredictable ways.
   Each phase is independently deployable and verifiable.

3. Phases

PHASE 1 — Strangler fig: add event publishing alongside existing direct calls
  Changes:
  - Add rabbitmq client to main app (src/lib/queue.ts)
  - In payments/index.ts: after each payment, publish payment.completed to queue
    (existing code path unchanged — queue is additive)
  - Stand up payments-service skeleton that consumes the queue and logs events
  Files:
  - NEW: src/lib/queue.ts
  - MOD: payments/index.ts (add publish call, ~10 lines)
  - NEW: payments-service/src/index.ts (consumer skeleton)
  Verify:
  - Run existing tests — all pass
  - Make a payment; see event appear in payments-service logs
  - Payments still work end-to-end

PHASE 2 — Move business logic into payments-service
  Changes:
  - Move payment processing logic from payments/index.ts to payments-service
  - payments-service calls main app's /internal/users/:id endpoint for user data
  - payments-service publishes payment.completed; main app consumes and triggers email
  Files:
  - MOD: payments-service/src/index.ts (full logic)
  - MOD: payments/index.ts (thin proxy: publish event, wait for response)
  - NEW: src/routes/internal.ts (user lookup endpoint, internal-only)
  - MOD: src/app.ts (mount internal router)
  Verify:
  - Integration test: full payment flow through the queue
  - Response time within 200ms of baseline
  - Email still triggers on payment.completed

PHASE 3 — Cut the cord: remove payments logic from main app
  Changes:
  - Delete payments/ from main app
  - Remove shared/db usage from payments-service; give it its own Prisma client
    pointed at same DB, scoped to payments tables only
  Files:
  - DEL: src/payments/ (entire directory)
  - MOD: payments-service/prisma/schema.prisma (payments + payment_events only)
  Verify:
  - Full regression test suite
  - Load test to confirm no latency regression

4. Rollback strategy
  Phase 1: remove queue.ts and the publish call — zero risk, purely additive
  Phase 2: revert payments/index.ts to direct calls — payments-service can keep running
  Phase 3: git revert + re-deploy main app with payments/ restored (DB schema unchanged)

5. Coupling risks
  - userService.getById() latency adds to payment response time — set 100ms timeout,
    cache user data in payments-service for 60s
  - If RabbitMQ is down in phase 2, payments fail — add a dead-letter queue
  - Prisma migrations in phase 3 must not drop columns still read by old main app
    during the deployment window
```

### What to avoid

- Don't enter Plan Mode before you've done the exploration — you'll get a plan full of "TBD" and "wherever payments is used."
- Don't accept a plan without a rollback strategy for a migration this size.
- If Claude proposes doing phases 1–3 as one step: "No. Each phase must be independently deployable. Replan."
- If the plan doesn't mention coupling risks explicitly: "Add a section on what can break at each phase transition."

---

## Quick Reference

| | Easy | Medium | Complex |
|---|---|---|---|
| Explore before planning? | No | Yes — 2–3 focused questions | Yes — thorough, use Explore agent |
| Resolve ambiguities first? | No | Sometimes | Always |
| Plan format | Goal + files + steps + verify | + edge cases | + phases + rollback + risks |
| Push back if plan has... | >5 steps | >8 steps | no phases or no rollback |
| Key failure mode | Over-engineering a simple change | Missing file coupling | Big-bang plan with no phases |

---

## Universal rules

**Reject and redirect** — if a plan is too complex, don't ask it to "simplify." Tell it *why* it's too complex and re-enter Plan Mode with a tighter prompt.

**Resolve choices before planning** — if two approaches are valid, pick one in chat *before* asking for a plan. Plans that list alternatives are half-plans.

**One constraint = one sentence** — list your constraints explicitly in the prompt. Claude cannot infer "don't use refresh tokens" or "phases only."

**Verify per phase** — any plan that doesn't say how to verify correctness is incomplete. Add "include verification steps for each phase" to your prompt if needed.
