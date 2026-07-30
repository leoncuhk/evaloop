# Why Your AI Coding Agent Fails at Long Tasks — and the Architecture That Fixes It

> **Archived.** This essay was written for the three-mode architecture
> (engineer / researcher / auditor) that shipped through v6. evaloop 7.0 ships a
> single loop, scored by a metric. The argument below still holds — it is why the
> loop is shaped the way it is — but its inventory of modes, file names and
> commands describes a version that no longer exists. For what evaloop is now,
> see the [README](../../README.md) and the [design rationale](../design-rationale.md).

*A practical guide to building reliable autonomous AI development pipelines, based on the design principles behind [evaloop](https://github.com/leoncuhk/evaloop).*

---

90% of AI-built projects never reach production. 45% of AI-generated code has security vulnerabilities. Experienced developers are [19% slower](https://www.secondtalent.com/resources/ai-generated-code-quality-metrics-and-statistics-for-2026/) when using AI coding tools, despite expecting to be 24% faster.

These numbers feel wrong. We all know AI can write code. So why does it keep failing at real projects?

The answer isn't that the models are too dumb. It's that **we're running them wrong**.

## The Problem: Six Ways AI Agents Fail at Long Tasks

In January 2026, researchers published ["Why LLMs Aren't Scientists Yet"](https://arxiv.org/abs/2601.03315) — a case study of four attempts to build fully autonomous AI research agents. Three out of four attempts failed. The paper identified six recurring failure modes that sabotage any long-running AI agent task:

**1. Training Data Bias** — The model defaults to familiar patterns from its training data, ignoring your specific instructions. Claude Code repeatedly used deprecated libraries despite explicit instructions to use modern alternatives.

**2. Implementation Drift** — When the agent hits a wall, it doesn't solve the root cause. Instead, it progressively simplifies the implementation until it's doing something completely different from what was specified. A differentiable tree search planner devolved into a basic actor-critic approach.

**3. Context Degradation** — Over long sessions, the model's understanding of the task degrades. Earlier instructions get diluted. The agent starts contradicting its own earlier work.

**4. Overexcitement** — The agent declares success despite obvious failures. Degenerate outputs (zero error rates, dummy signals) get described as "successful hypothesis validation." Paper drafts make claims like "first ever comprehensive assessment" when results are statistically invalid.

**5. Insufficient Domain Intelligence** — The model lacks specialized knowledge needed for the task. It makes plausible-sounding but incorrect decisions.

**6. Weak Scientific Taste** — The agent can't distinguish meaningful experiments from trivial ones. It generates busywork that looks productive but doesn't advance the goal.

These aren't bugs in a specific model. They're **structural properties of how LLMs work** — they emerge whenever you run a model on tasks that exceed a single conversation turn. Switching from Claude to GPT to Gemini doesn't fix them. Bigger context windows don't fix them. Better prompts *partially* help, but can't eliminate them.

What does fix them is **architecture**.

## The Thesis: Reliability Comes from Discipline, Not Intelligence

Here's the counterintuitive insight: **making your AI agent more reliable has nothing to do with making it smarter.**

It's the same insight that software engineering learned decades ago. We don't make systems reliable by hiring smarter programmers. We make them reliable with architecture: separation of concerns, stateless services, idempotent operations, automated testing, circuit breakers.

The same principles apply to AI agent systems. I call this the **Stateless Agent Architecture** — a set of design principles for running LLM agents on tasks that span hours or days:

```
┌────────────────────────────────────────────────────────┐
│  Deterministic Orchestrator (run.py)                   │
│  Decides WHAT runs, WHEN, and with WHAT state          │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Session 1        Session 2        Session 3     │  │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐   │  │
│  │  │ LLM Call │    │ LLM Call │    │ LLM Call │   │  │
│  │  │ (fresh)  │    │ (fresh)  │    │ (fresh)  │   │  │
│  │  └────┬─────┘    └────┬─────┘    └────┬─────┘   │  │
│  │       │               │               │         │  │
│  │       ▼               ▼               ▼         │  │
│  │  ┌──────────────────────────────────────────┐    │  │
│  │  │         File-Based State Layer           │    │  │
│  │  │  tasks.json / journal.json / progress.md │    │  │
│  │  └──────────────────────────────────────────┘    │  │
│  └──────────────────────────────────────────────────┘  │
│  Circuit Breaker: stuck detection + max sessions       │
└────────────────────────────────────────────────────────┘
```

## Five Design Principles

### Principle 1: Deterministic Orchestration

**The orchestrator decides the workflow. The LLM executes individual steps.**

Most agent frameworks let the LLM decide what to do next. This is fundamentally unreliable. An LLM deciding its own workflow is like letting a contractor decide which building code to follow — sometimes they'll get it right, but you can't *depend* on it.

In evaloop, a Python script (`run.py`) controls the entire execution flow: which phase runs, when to review, when to stop, when to abort. The LLM only sees "here's your task, do it, report the result." The LLM has zero influence on the orchestration logic.

This addresses **all six failure modes** at the architectural level — the agent literally cannot drift, loop, or skip steps because the orchestrator won't let it.

```bash
# The engine is a simple, auditable loop:
while true; do
  PHASE=$(get_phase)          # Deterministic: check state file
  run_session "$PHASE"        # Give LLM exactly one task
  check_circuit_breaker       # Kill if stuck
  maybe_trigger_review        # Every N sessions
done
```

Compare this to letting the LLM decide: "Now I'll review my work... actually, let me implement one more feature first... wait, I should refactor this..." That's how drift happens.

### Principle 2: Stateless Sessions

**Each LLM call starts fresh. Zero memory of previous sessions.**

This is the single most important design choice. It directly solves **context degradation** — the #1 killer of long-running agent tasks.

When you run a multi-hour coding session in a single context window, the model's attention to early instructions decays. Contradictions accumulate. The model starts working against itself.

Stateless sessions eliminate this entirely. Each session gets:
- The full spec/hypothesis (source of truth)
- The current state file (what's done, what's pending)
- The last 50 lines of the progress log (recent context)
- The CLAUDE.md rules file (behavioral constraints)

That's it. Fresh context, every time. The model can't "forget" instructions because it's reading them for the first time in every session.

The cost? Each session re-reads the state files. This takes 5-10 seconds of LLM time. The benefit? Sessions never degrade. Session #47 is exactly as coherent as session #1.

### Principle 3: File-Based State Transfer

**The filesystem is the memory. Not the context window.**

State lives in structured files:
- `tasks.json` / `journal.json` — work queue with status tracking
- `progress.md` — append-only log of what happened
- `learnings.md` — accumulated cross-session knowledge
- Git history — full audit trail

This design has three critical advantages:

**Survives session boundaries** — Unlike context window state, file state persists indefinitely. Session 30 can read what session 1 learned.

**Human-inspectable** — You can `cat .state/tasks.json` at any time to see exactly where the project stands. No black-box agent memory.

**Git-versioned** — Every state change is committed. You can `git log` to see the full decision history. You can `git revert` if something goes wrong.

### Principle 4: One Task Per Session

**Each session completes exactly one atomic unit of work, then stops.**

This addresses **implementation drift** — the failure mode where the agent progressively simplifies its approach when things get hard.

When an agent has a 10-task backlog in a single session, and task 3 gets complicated, it has an incentive to cut corners — because tasks 4-10 are waiting. With one-task-per-session, there's no pressure. The agent has no knowledge of what comes after. It can fully focus on this one task.

It also makes **failure cheap**. If a session produces bad results, you lose one task's worth of work, not an entire project. The next session starts fresh and can try a different approach.

In researcher mode, this principle becomes even more important: one *experiment* per session. If the experiment fails, the agent reverts the code (`git checkout -- .`) and records the learnings. The codebase is always in a known-good state.

### Principle 5: Mandatory Verification

**Metrics decide. Not the LLM's self-assessment.**

This addresses **overexcitement** — the failure mode where the agent declares success despite obvious problems.

Engineer mode requires three checks before any task can be marked done:

```bash
npm run build    # Does it compile?
npm test         # Do tests pass?
npm run lint     # Does it meet quality standards?
```

With the `acceptance_criteria` and `verify_command` fields in the task schema, each task also carries its own specific verification:

```json
{
  "id": 3,
  "title": "Implement POST /api/todos",
  "acceptance_criteria": "POST /api/todos with {title:'test'} returns 201",
  "verify_command": "npm test -- --grep 'POST /api/todos'",
  "status": "pending"
}
```

Researcher mode is even stricter: **metrics are truth**. The experiment runs, produces a number (Sharpe Ratio, accuracy, latency — whatever the hypothesis defines), and that number decides whether the experiment is accepted or rejected. The LLM's *opinion* of the result is irrelevant.

## Two Applications: Deduction and Induction

These five principles support two fundamentally different workflows:

### Engineer Mode: Deductive (Spec to Code)

```
Human writes spec.md
  → Initializer decomposes into tasks with acceptance_criteria
    → Developer implements one task per session (TDD)
      → Reviewer checks health every N sessions
        → Complete project (all tasks verified)
```

This is what most coding agent tools do. The difference is **the verification layer**: every task has machine-checkable criteria, and the orchestrator won't advance until they pass.

### Researcher Mode: Inductive (Hypothesis to Findings)

```
Human writes hypothesis.md (goals + search space + target metric)
  → Theorizer designs one experiment
    → Executor runs it, captures metric
      → Accept (commit) or Reject (revert) based on metric
        → Analyst reviews patterns every N sessions
          → Target metric achieved (or search space exhausted)
```

This is the genuinely novel application. As of March 2026, I haven't found another open-source tool that automates the **inductive research loop** — hypothesis, experiment, evaluate, learn, iterate.

Sakana's [AI Scientist v2](https://github.com/SakanaAI/AI-Scientist-v2) comes closest, but it's a monolithic system that generates entire papers. evaloop takes a different approach: **the human defines the hypothesis and search space, the agent executes iterations**. Given the documented failure modes (especially "weak scientific taste"), this human-in-the-loop approach is more reliable at the current state of the art.

A [complete demo](../../examples/quant-lab/) shows this in action: optimizing a trading strategy's Sharpe Ratio from 0.85 toward 1.5, with 6 experiments (2 accepted, 3 rejected, 1 error), accumulated learnings, and an analyst review. The experiment journal reads like a real research log — because the structure forces it to be.

## How This Relates to the 2026 Landscape

The agentic coding space in early 2026 is consolidating around three layers:

**Execution layer** (Claude Code, Cursor, Cline, OpenHands) — increasingly commoditized. These tools let AI write code in a single session. They're getting better fast, but they're all solving the same problem.

**Orchestration layer** (Claude Code Agent Teams, Gas Town, Multiclaude) — rapidly being absorbed by platform providers. Anthropic's Agent Teams feature already supports multi-session coordination, task assignment, and inter-agent messaging. Competing here as an independent project is a losing proposition.

**Methodology layer** (GitHub Spec Kit, evaloop, Simon Willison's Agentic Engineering Patterns) — this is where durable value lives. When the execution and orchestration layers are commoditized, **how you use them reliably** becomes the differentiator. This is what evaloop provides.

GitHub's [Spec Kit](https://github.com/github/spec-kit) validates the spec-driven approach but stops at task generation — it doesn't execute or verify. evaloop closes that gap: from spec to verified, committed code, with every step auditable.

## Getting Started

```bash
git clone https://github.com/leoncuhk/evaloop
cd evaloop

# Try engineer mode: write a spec.md, then run
python run.py my-project

# Try researcher mode: write a hypothesis.md, then run
python run.py --mode researcher my-experiment

# Try auditor mode: write a standards.md, then run
python run.py --mode auditor my-audit

# See the quant-lab demo
cd examples/quant-lab && python run_backtest.py
```

The entire system is a single Python script + markdown prompts. You can read the full source in 15 minutes. There's no framework to learn, no dependencies to install (beyond `claude` and `git`), and no magic.

## Creating Your Own Mode

The architecture is mode-pluggable. Adding a new workflow requires:

1. A `mode.conf` (10 lines of key-value config)
2. A `CLAUDE.md` (agent behavioral rules)
3. Three prompt files (init / work / review)

The engine picks up new modes automatically. No code changes required.

---

## Summary

The six failure modes of autonomous LLM agents are structural, not accidental. They emerge from the fundamental nature of how language models process information over long horizons.

The fix isn't a better model. It's a better architecture:

| Failure Mode | Architectural Fix |
|---|---|
| Context degradation | Stateless sessions — fresh context every time |
| Implementation drift | One task per session — no room to drift |
| Overexcitement | Mandatory verification — metrics decide |
| Training data bias | File-based state — current spec overrides defaults |
| Infinite loops | Circuit breaker — stuck detection + max sessions |
| Weak scientific taste | Human-defined hypothesis — agent executes, human directs |

These aren't novel ideas. They're the same principles that made Unix reliable, that made REST scalable, that made 12-Factor Apps deployable. Applied to AI agents, they produce something that actually works for tasks longer than a single chat turn.

The code is open source: [github.com/leoncuhk/evaloop](https://github.com/leoncuhk/evaloop).

---

*References:*
- *["Why LLMs Aren't Scientists Yet"](https://arxiv.org/abs/2601.03315) — Six failure modes in autonomous LLM research (arXiv, Jan 2026)*
- *[Anthropic 2026 Agentic Coding Trends Report](https://resources.anthropic.com/2026-agentic-coding-trends-report) — Industry landscape analysis*
- *[AI-Generated Code Quality Statistics](https://www.secondtalent.com/resources/ai-generated-code-quality-metrics-and-statistics-for-2026/) — 90% failure rate, 45% security vulnerabilities*
- *[GitHub Spec Kit](https://github.com/github/spec-kit) — Spec-driven development toolkit*
- *[Sakana AI Scientist v2](https://github.com/SakanaAI/AI-Scientist-v2) — Autonomous scientific discovery via agentic tree search*
- *[HKUST Survey: From Automation to Autonomy](https://github.com/HKUST-KnowComp/Awesome-LLM-Scientific-Discovery) — LLMs in scientific discovery (EMNLP 2025)*
- *[Agentic Engineering Patterns](https://simonwillison.net/2026/Feb/23/agentic-engineering-patterns/) — Simon Willison's practical guide*
