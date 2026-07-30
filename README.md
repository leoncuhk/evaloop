# auto-dev-agentos

[![CI](https://github.com/leoncuhk/auto-dev-agentos/actions/workflows/ci.yml/badge.svg)](https://github.com/leoncuhk/auto-dev-agentos/actions) [![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Verify your agent's output. Independently. Automatically.

A **verification harness** that wraps around any LLM agent loop. The agent proposes, the harness verifies — with independent commands, hidden out-of-sample data, and a scoring definition the agent cannot reach or rewrite. No frameworks, no Docker, under 1000 lines of Python and nothing outside the standard library.

> **Core thesis**: Reliability in autonomous AI agent tasks comes from *structurally separate evaluation* — the evaluator must be architecturally independent from the generator. This is [Loop 2](https://blog.langchain.dev/the-art-of-loop-engineering/) in LangChain's stack, and the [non-negotiable principle](https://appscale.com) for production agent systems.

## What This Is

In the language of [Loop Engineering](https://addyosmani.com/blog/loop-engineering):

| Layer | What | In this project |
|-------|------|-----------------|
| **Loop 1** (Agent) | LLM tool-calling loop | Claude Code, /goal, or any agent |
| **Loop 2** (Verification) | Independent evaluation | **This project** — `verify_command` + `hidden_verify_command` |
| **Loop 3** (Application) | Session orchestration | `run.py loop` — optional, wraps Loop 1 with Loop 2 |
| **Loop 4** (Hill Climbing) | Cross-run optimization | Hidden metrics tracking in `.state/hidden_metrics.json` |

Your agent (Loop 1) already works. This harness adds the verification layer (Loop 2) that production systems need: independent verification commands, hidden out-of-sample validation, and metric accumulation over time.

## Three Ways to Use

### 1. Standalone verification (no LLM calls)

```bash
# Run verification against your project — verify_command + hidden OOS
python run.py verify examples/quant-lab --mode researcher

# Check project status
python run.py status examples/todo-app
```

### 2. Session loop with verification

```bash
# Run the full loop: agent sessions + independent verification after each
python run.py loop examples/todo-app --mode engineer

# Same thing with backward-compatible syntax
python run.py examples/todo-app
```

### 3. Library import

```python
from core import run_verification, load_conf

conf = load_conf(Path("modes/researcher"))
result = run_verification("/path/to/project", conf, session_label="manual")
# result = {"verify": {"success": True, "metric": 1.89, ...}, "hidden": {"success": True, ...}}
```

## Quick Start

```bash
git clone https://github.com/leoncuhk/auto-dev-agentos
cd auto-dev-agentos

# See available modes
python run.py list-modes

# Check status of example project (zero cost)
python run.py status examples/todo-app

# Run verification only (no LLM calls)
python run.py verify examples/quant-lab --mode researcher

# Test session loop with simulation (no LLM calls, no cost)
python run.py loop --simulate --mode engineer --pause 0 examples/todo-app

# Run for real
mkdir my-project && echo "# My App\nBuild a REST API..." > my-project/spec.md
python run.py loop my-project
```

## The Verification Layer

This is the core value of the project. After each work session:

### 1. Independent `verify_command`

Runs a command that the orchestrator controls, not the LLM. Configured in `mode.conf` or overridden per-project with a `.verify` file:

```ini
# modes/researcher/mode.conf
verify_command = python run_backtest.py --split train

# examples/qlib-quant/.verify (project-level override)
verify_command = python qlib_backtest.py --split train
hidden_verify_command = python qlib_backtest.py --split test
```

### 2. Hidden out-of-sample validation

`hidden_verify_command` runs on data the LLM never sees. The metric is written to `.state/hidden_metrics.json` and is never fed back to the LLM by the orchestrator.

Why it matters, empirically: research agents on [MLE-bench](https://arxiv.org/html/2507.02554) show a persistent **9–13% validation/test generalization gap**. An agent optimising a visible metric will find the gap. A number the agent never sees is the only one that measures whether the work generalizes.

### 3. Scoring integrity

Not surfacing a metric is not the same as an agent being unable to obtain it. Everything under the project directory is writable by the agent — including `.verify` and the scripts it names. A live session in [`examples/goal-vs-loop/logs/session_4.log`](examples/goal-vs-loop/logs/session_4.log) ran the hidden split itself and reported `hidden test split = 1.5233` in its own summary.

Three controls, in order of strength:

**Seal the scoring definition** — `--sealed-verify FILE` reads the verification config from a path outside the project. It outranks the project's `.verify`, so an agent that rewrites `.verify` changes nothing. The harness refuses a sealed file that resolves inside the project.

```bash
# operator-owned, outside the repo the agent works in
echo 'hidden_verify_command=python3 run_backtest.py --split test' > ~/scoring/proj.conf
python run.py loop ./proj --mode researcher --sealed-verify ~/scoring/proj.conf
```

**Fingerprint what does the scoring** — before each session the orchestrator hashes `.verify` and every in-project file the verification commands invoke, then re-hashes afterwards. A change means the session rewrote its own scoring, and the metric is reported as untrusted rather than as a result:

```
verify: PASS (exit 0) | metric: 99.0
TAMPERED: scoring inputs changed during the session: score.py
The metric above was produced by definitions this session rewrote. Do not treat it as a result.
```

**Detect leaks after the fact** — each session's transcript is scanned for the hidden invocation and for the hidden metric's own value. Hits are recorded with the metric, so a contaminated number is never silently mixed with clean ones:

```json
[
  {"session": "1", "metric": 0.84, "timestamp": "...", "sealed": true},
  {"session": "3", "metric": 1.5233, "timestamp": "...", "sealed": false,
   "leaks": ["hidden metric 1.5233 appears in transcript"]}
]
```

This is the architecture [sandbox-policy research](https://github.com/islo-labs/reward-hack-bench) converges on — scoring runs where the agent does not control it, and the verdict is computed outside the agent's reach. Detection is the weakest of the three and is honest about it: it marks a metric contaminated, it never certifies one clean. For adversarial settings, seal the config *and* run the hidden command against data on a filesystem the agent cannot read.

### 4. Budget & stuck controls

- **Circuit breaker**: stops after N consecutive sessions with no progress
- **Budget cap**: `--max-budget` prevents runaway spending
- **Retry**: automatic single retry on error/timeout (don't waste session slots)

## Architecture

![auto-dev-agentos architecture](assets/auto-dev-agentos-architecture.png)

Each session is stateless. State lives in `.state/` files. Session N+1 reads what Session N wrote. The engine decides what runs — the LLM only executes.

|              | **Engineer**         | **Researcher**        | **Auditor**              |
|--------------|----------------------|-----------------------|--------------------------|
| Input        | `spec.md`            | `hypothesis.md`       | `standards.md`           |
| Each session | One task             | One experiment        | One finding              |
| On failure   | Fix and retry        | Revert and learn      | Dismiss with evidence    |
| Exit when    | All tasks pass       | Target metric hit     | All standards covered    |
| State file   | `tasks.json`         | `journal.json`        | `findings.json`          |
| Verification | `npm test` / `pytest`| Backtest metric       | Coverage count           |

## Project Structure

```
auto-dev-agentos/
├── run.py              # Verification harness CLI (573 lines)
├── core.py             # Pure functions: verification, integrity, state (429 lines)
├── modes/
│   ├── engineer/       # spec.md → tasks → implement → verify
│   ├── researcher/     # hypothesis.md → experiment → evaluate → learn
│   └── auditor/        # standards.md → scan → analyze → report
├── tests/
│   ├── test_run.py     # Unit tests (17 tests)
│   └── test_integration.py  # Integration tests (60 tests)
├── experiments/        # run_validation.py — orchestrator conformance checks
├── docs/               # Design rationale and methodology
└── examples/           # Demo projects (todo-app, quant-lab, qlib-quant, goal-vs-loop)
    └── <project>/
        ├── .state/learnings.md   # Cross-session knowledge (tracked)
        ├── .state/history/       # Archived records of completed runs
        └── logs/                 # Verbatim session transcripts
```

## Empirical Record

What has and has not actually been measured. Every claim below points at a file
in this repository, so it can be checked rather than taken on trust.

### What was run against a live model

| Example | Sessions | Outcome | Record |
|---|---|---|---|
| `examples/goal-vs-loop` | 4 (Theorizer/Executor ×2) | Sharpe 0.8363 → 1.9084 on synthetic data, target 1.5 met | [`logs/`](examples/goal-vs-loop/logs/), [`.state/history/`](examples/goal-vs-loop/.state/history/), and `session-history.bundle` (`git clone` it to replay all 5 commits) |
| `examples/qlib-quant` | 12, incl. an 11-round sweep | Sharpe 2.9746 → 3.6430 on the 2022 segment of CSI300 | [`.state/history/`](examples/qlib-quant/.state/history/), [`logs/`](examples/qlib-quant/logs/), [`.state/learnings.md`](examples/qlib-quant/.state/learnings.md) |

Both working trees are reset to baseline so the examples start clean; the runs
above are preserved under `.state/history/` rather than in the live state files.

### What those numbers do not show

- **The qlib sweep selected on the segment it scored on.** `--split train` maps
  to the 2022 *valid* segment, and all 11 rounds were chosen by that number. The
  +22.5% is a selection gain, not an out-of-sample result.
- **The hidden split was executed once and the result was lost.**
  [`mlflow-runs.json`](examples/qlib-quant/.state/history/mlflow-runs.json)
  records a `--split test` run at commit `e8bf29f`, but no `hidden_metrics.json`
  was ever written. There is no recorded hidden-OOS figure for this example.
- **`run_qlib_backtest.py` is not qlib's backtest pipeline.** It implements its
  own top-30/bottom-30 long-short with daily full turnover and no transaction
  cost, slippage, or position limits — despite `hypothesis.md` requiring the
  standard pipeline. The configured `topk`/`n_drop` are read but never applied.
  A Sharpe near 3–4 under zero cost is the expected magnitude of that
  construction, not evidence of an edge.
- **goal-vs-loop runs on synthetic data** with injected drift and AR(1)=0.15
  momentum. The mechanism the agent found is real *for that generator* and says
  nothing about real markets.

### What `experiments/run_validation.py` does and does not test

It checks the orchestrator, not the loop's effectiveness:

- **H1 (convergence)** and **H3 (phase decisions)** run against hardcoded
  `SIMULATION_SCRIPTS` whose metric trajectories are written into the script. They
  demonstrate that the state machine advances and halts correctly. They cannot
  demonstrate that a loop converges, because convergence is an input.
- **H2 (generalization)** compares two hand-written strategies across 12 seeds —
  neither was discovered by a loop. At 7/12 the result is not statistically
  distinguishable from chance (binomial *p* ≈ 0.39 against a fair coin), and the
  script's `win_rate >= 55` pass threshold is an arbitrary cutoff, not a test.

Read it as a conformance suite for the orchestrator. An end-to-end validation —
many live runs, measured against a control — has not been done.

## CLI Reference

```
python run.py verify <project> [--mode MODE] [--sealed-verify FILE]   # verify only
python run.py loop <project> [--mode MODE] [options]   # session loop
python run.py status <project> [--mode MODE]           # show phase/progress
python run.py list-modes                               # list available modes
python run.py <project> [options]                      # backward compat → loop
python run.py --dry-run <project>                      # backward compat → status
```

| Loop option | Default | Description |
|-------------|---------|-------------|
| `--max-sessions` | `50` | Session limit |
| `--max-turns` | `50` | Turn limit within one session |
| `--sealed-verify` | | Scoring config outside the project, beyond the agent's reach |

`verify_timeout` (seconds, default 300) is set in `mode.conf`, `.verify`, or the
sealed file — a full model fit outlives a test suite. A timeout is a failed
check, never a metric.
| `--max-budget` | `10.0` | Maximum cost in USD |
| `--orient-interval` | `10` | Strategic review interval |
| `--review-interval` | `5` | Tactical review every N sessions |
| `--no-progress-max` | `3` | Stuck detection threshold |
| `--pause` | `5` | Seconds between sessions |
| `--simulate` | | Use `.state/sim_script.json` for deterministic testing |

## How This Compares

Three families of tools sit near this one. They solve adjacent problems, and for most of what people need, one of them is the better answer.

**LLM evaluation frameworks** — [DeepEval](https://deepeval.com), [Inspect AI](https://inspect.aisi.org.uk) (UK AISI), [promptfoo](https://promptfoo.dev), [Braintrust](https://braintrust.dev), LangSmith. They score outputs against datasets, with rich metric libraries, LLM-as-judge, CI integration, and red-teaming. **Use them for**: measuring whether a change to a prompt, model, or RAG pipeline made things better. **What they don't do**: wrap a long-running loop in which the agent keeps editing the artifact being scored. Their threat model is a flaky metric, not an agent with write access to the scorer.

**Agent loop harnesses** — [loop-harness](https://github.com/lSAAGl/loop-harness), spec-driven toolkits like [Spec Kit](https://github.com/github/spec-kit), agentic SDLC pipelines. Closest structural siblings: scheduled loops, worktree isolation, a verification gate before anything ships. Their gate is usually a second LLM session judging the first. **Use them for**: shipping agent work safely into a repo. **What they don't do**: hold data back from the agent. An LLM judge is a strong check on *whether the work is sound* and a weak one on *whether the number generalizes*.

**Evolutionary program search** — [AlphaEvolve](https://deepmind.google), [OpenEvolve](https://github.com/codelion/openevolve), [ShinkaEvolve](https://github.com/SakanaAI/ShinkaEvolve). Here the evaluator genuinely is a separate program, with cascade evaluation to prune cheap failures early — architecturally the nearest relative. The community's own guidance is that you must hand-design an unhackable evaluator, because the search will find every loophole in it. **Use them for**: optimising a well-specified objective over many thousands of candidates. **What they don't do**: give you the unhackable evaluator. That is left to you.

**Where this project fits.** It is the small piece those three leave out: a scoring definition the agent cannot reach or rewrite, carried across sessions, with the out-of-sample number withheld by construction rather than by instruction. It is roughly 1000 lines with no dependencies, so it wraps whatever agent you already run instead of replacing it.

**When not to use it.** If your metric is a fixed test suite the agent cannot edit, `verify_command` adds little over running the tests. If you need dashboards, tracing, or dataset management, use a real eval platform. If you need hard isolation against an adversarial agent, you need a sandbox — this gives you sealing and detection, not containment.

### The framing this follows

- **LangChain** [4-loop stack](https://blog.langchain.dev/the-art-of-loop-engineering/): Agent → Verification → Application → Hill Climbing. This project is Loop 2.
- **Osmani** [Loop Engineering](https://addyosmani.com/blog/loop-engineering): "Reliability comes from the loop, not the model."
- **MLE-bench** [research agents](https://arxiv.org/html/2507.02554): a 9–13% validation/test generalization gap — the empirical case for withholding a metric.
- **RewardHackBench** [sandbox policies](https://github.com/islo-labs/reward-hack-bench): scoring belongs in an environment the agent does not control.

## Design Principles

These address the [six failure modes](https://arxiv.org/abs/2601.03315) of autonomous LLM agents:

| Principle | Failure mode it solves |
|-----------|----------------------|
| Independent verification | Overexcitement — orchestrator verifies, not LLM self-report |
| Hidden OOS validation | Overfitting — test data invisible to the LLM |
| Stateless sessions | Context degradation — each session starts fresh |
| File-based state | Context window limits — state survives indefinitely |
| One task per session | Implementation drift — no room to simplify under pressure |
| Circuit breaker | Infinite loops — stuck detection + max sessions + budget cap |
| Deterministic orchestration | All six — code decides flow, not LLM |
| State schema validation | Corruption — malformed state is reported, not acted on |
| Sealed scoring config | Evaluator capture — the agent cannot redefine its own metric |
| Scoring fingerprints | Reward hacking — a rewritten scorer marks the metric untrusted |
| Leak detection | Silent contamination — hidden-metric leaks are recorded with the metric |

## Prerequisites

```bash
pip install claude-agent-sdk               # Optional: adds SDK hooks and cost tracking
npm install -g @anthropic-ai/claude-code   # Claude Code CLI (alternative to SDK)
```

Either SDK or CLI works. Use `--simulate` to test without either.

## FAQ

**How much does it cost?**
`verify` subcommand is free (no LLM). Each `loop` session is one Claude Code invocation. `--max-budget` caps total spend.

**Can I use a different LLM?**
Yes. The verification layer is LLM-agnostic. Replace the `claude -p` call in `run_cli_session()` with your CLI tool.

**Can I resume after Ctrl+C?**
Yes. Same command again. The engine re-reads `.state/` and continues from where it left off.

**What's the `.verify` file?**
Project-level override for verification commands. Takes precedence over `mode.conf`. Useful when the same mode applies to different projects with different test suites.

## References

**Design:**
- [Design Rationale](docs/design-rationale.md) — Why this architecture, what alternatives were considered
- [Peirce's Inquiry Cycle](docs/peirce-inquiry-cycle.md) — Why three roles per mode is logically irreducible
- [Stateless Agent Architecture](docs/stateless-agent-architecture.md) — Full argument for stateless sessions
- [Dual-Loop Architecture](docs/dual-loop-architecture.md) — Strategic orientation via OODA outer loop

**Loop Engineering:**
- [Addy Osmani — Loop Engineering](https://addyosmani.com/blog/loop-engineering) — Canonical definition (June 2026)
- [Boris Cherny — Claude Code & the Future of Engineering](https://x.com/AcquiredFM/status/2062621816393297920) — "My job is to write loops" (June 2026)
- [LangChain — The Art of Loop Engineering](https://blog.langchain.dev/the-art-of-loop-engineering/) — Four-loop stack

**Research:**
- [Why LLMs Aren't Scientists Yet](https://arxiv.org/abs/2601.03315) — Six failure modes in autonomous LLM research (arXiv, 2026)
- [Building Effective AI Coding Agents](https://arxiv.org/abs/2603.05344) — Scaffolding + harness architecture (arXiv, 2026)
- [Anthropic Agentic Coding Trends](https://resources.anthropic.com/2026-agentic-coding-trends-report) — Industry landscape (2026)

**Related tools:**
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — Terminal-native AI agent by Anthropic
- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) — Python SDK for agent loops
- [GitHub Spec Kit](https://github.com/github/spec-kit) — Spec-driven development toolkit
- [OpenHands](https://github.com/All-Hands-AI/OpenHands) — Full-platform autonomous coding agent
- [Omnigent](https://github.com/databricks/omnigent) — Meta-harness for composing agent loops

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Run `python tests/test_run.py && python tests/test_integration.py` before submitting.

## License

AGPL-3.0. See [LICENSE](LICENSE).
