# evaloop

[![CI](https://github.com/leoncuhk/evaloop/actions/workflows/ci.yml/badge.svg)](https://github.com/leoncuhk/evaloop/actions) [![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**Evaluation-driven autonomous development.** For loops whose acceptance
criterion is a *metric*, not a test suite.

When an agent's work is judged by a number, the agent is also editing the thing
that produces the number. Left alone, a long loop optimises the measurement
rather than the work, and reports success. This harness keeps the measurement
alive under that pressure: verification the orchestrator runs, a held-out metric
the agent never sees, a scoring definition it cannot reach or rewrite, and a
record of which numbers are trustworthy. Under 1000 lines of Python, nothing
outside the standard library, no Docker.

> **The claim, stated narrowly**: a loop can only run unattended for as long as
> its metric survives its own optimiser. Everything here exists to extend that.

## Is this for you?

| Your acceptance criterion | Use |
|---|---|
| A test suite the agent shouldn't edit | Claude Code, Cursor, [Spec Kit](https://github.com/github/spec-kit). This adds little |
| A quality score you read yourself | An eval platform — [DeepEval](https://deepeval.com), [Inspect AI](https://inspect.aisi.org.uk), [Braintrust](https://braintrust.dev) |
| A metric the agent optimises, on code the agent writes | **This** |

The third row is where autonomous development actually breaks. Research agents
on [MLE-bench](https://arxiv.org/html/2507.02554) show a persistent **9–13%
validation/test generalization gap**: an agent optimising a proxy metric
reliably converges somewhere the held-out set does not follow. It is not
malice — it is what optimisers do. A number the agent never sees is the only
measurement that survives it.

This repository contains a worked case of the failure. An 11-round
hyperparameter sweep improved its metric by 22.5%, every round scored on the
same segment it selected from, and the held-out run that would have settled it
was executed once and its result discarded. Full record in
[`examples/qlib-quant/.state/history/`](examples/qlib-quant/.state/history/).

## Try it

Nothing here needs an API key or an LLM. Both of these run from a fresh clone.

```bash
git clone https://github.com/leoncuhk/evaloop && cd evaloop

# Score a project. Prints the visible metric, records the held-out one,
# exits non-zero on failure.
python run.py verify examples/quant-lab

# Watch a session rewrite its own scorer and get caught. Replayed from a
# script, so no LLM calls and no cost.
python run.py loop --simulate --pause 0 examples/tamper-demo
```

The second prints `TAMPERED: scoring inputs changed during the session` and
refuses to call the metric a result. To replay it, `rm -rf
examples/tamper-demo/.state/journal.json examples/tamper-demo/logs`.

## Three ways to use it

In [Loop Engineering](https://addyosmani.com/blog/loop-engineering) terms this is
Loop 2 with a thin Loop 3 attached; in [harness
engineering](https://addyosmani.com/blog/agent-harness-engineering/) terms it is
the enforcement layer, and it assumes you already have an execution layer —
Claude Code, the Agent SDK, or your own.

### 1. As an evaluator for a search loop you already have

The one that needs no buy-in. Evolutionary program search
([AlphaEvolve](https://deepmind.google), [OpenEvolve](https://github.com/codelion/openevolve),
[ShinkaEvolve](https://github.com/SakanaAI/ShinkaEvolve)) tells you to design an
unhackable evaluator and leaves that to you. This is that evaluator:

```python
from pathlib import Path
from core import run_verification, load_conf

conf = load_conf(Path("modes/experiment"))
result = run_verification(
    "/path/to/candidate",              # what the search just produced
    conf,
    sealed=Path("~/scoring/task.conf").expanduser(),   # outside the candidate
    session_label="gen-42",
)
result["verify"]["metric"]        # what the search may optimise
result["hidden"]["metric"]        # what it may not see
result["integrity"]["trusted"]    # False if the candidate rewrote its scoring
```

### 2. As a verification step around your own agent

```bash
python run.py verify ./my-project --sealed-verify ~/scoring/proj.conf
```

Exits non-zero on failure, so it drops into CI or a shell loop unchanged. No
LLM calls, no cost.

### 3. As the whole loop

```bash
python run.py loop ./my-project --sealed-verify ~/scoring/proj.conf
```

Stateless sessions against `hypothesis.md`, verification after each, hidden
metric accumulated across the run, circuit breaker and budget cap.

### Starting your own

The loop scores by running your project's own evaluation script, so give it one
that already works before spending a session:

```bash
mkdir my-lab
cp examples/quant-lab/{hypothesis.md,run_backtest.py,strategies.py} my-lab/
echo 'hidden_verify_command=python3 run_backtest.py --split test' > ~/task.conf

python run.py verify my-lab                          # confirm it scores
python run.py loop my-lab --sealed-verify ~/task.conf
```

## How it works

Four things happen around every session. Each is one paragraph here and a
section in [docs/verification.md](docs/verification.md).

**The orchestrator runs the scoring.** `verify_command` is executed by evaloop,
not reported by the agent. Configured in `mode.conf`, or per project in
`.verify`, or — beyond the agent's reach — in a sealed file.

**A second metric is withheld.** `hidden_verify_command` runs on data the agent
never sees. Research agents on [MLE-bench](https://arxiv.org/html/2507.02554)
show a persistent 9–13% validation/test generalization gap; a number the agent
never sees is the only measurement that survives its own optimiser.

**The scoring definition is defended.** `--sealed-verify` puts it outside the
project, and the held-out record beside it. Files inside the project that do the
scoring are hashed before and after each session, so a run that rewrites its own
scorer reports `TAMPERED` instead of a result. Transcripts are scanned for the
held-out figure. Sealing is structural, fingerprinting is reliable, leak
detection is neither and says so.

**The held-out metric decides when you are done.** Reaching the visible target
is not sufficient. The gate can only withhold completion, never cause it; it
reads the latest clean record rather than the best; and a discredited record is
not evidence.

![The exit condition: a session ends, the visible metric is checked against the target, and only if it clears does a second amber decision ask whether the held-out metric clears it too; no there means not done because the gains did not transfer. The second question is the one the agent never sees](assets/evaloop-held-out-gate.png)

```
Orient: visible 3.6430 meets the target and held-out -0.0297 does not:
        the gains have not transferred
```

Those are real figures from [`examples/qlib-quant`](docs/empirical-record.md).
Under the old rule that run reports success.

> **What this runs on your machine.** `run.py loop` starts an agent with
> permissions bypassed, and the safety hook is a substring blocklist that stops
> an accident, not an adversary. Run it in a container or a throwaway copy.
> `verify` and `status` make no LLM calls and start no agent.
> [Details](docs/verification.md).

## Architecture

![evaloop architecture: the orchestrator runs the project and reads its metric; the sealed config and held-out data reach the orchestrator only, and the path from held-out data into the project is crossed out](assets/evaloop-architecture.png)

*What the crossed-out arrow means: evaloop never carries the held-out metric back
into the project, and `--sealed-verify` puts the definition of how to score
beyond the agent's reach. It does not make the held-out **data** unreadable — if
that file sits somewhere the agent can open, the agent can open it. Closing that
last path is filesystem permissions or a sandbox, not this tool. The crossed-out
arrow is a guarantee about what evaloop does, and an intent about the rest.*

The agent works inside the project directory and can write anything in it — its
own code, its own state, its own scorer. The orchestrator sits outside. It reads
how to score from a file the agent cannot reach, runs the scoring itself, and
keeps the held-out number on its own side of that boundary.

Each session starts with a fresh context and ends when its one experiment is
done. What carries across sessions is files, not context: the journal, the
progress log, the learnings. Session 30 reads what session 1 wrote.

| Phase | Prompt | What the session does |
|---|---|---|
| **init** | `theorizer` | Read `hypothesis.md` and the journal, design one experiment |
| **work** | `executor` | Run that experiment, keep it or revert it on the metric |
| **review** | `analyst` | Every N sessions, look across experiments for patterns |
| **orient** | `strategist` | Every M sessions, decide continue / pivot / done |

Input is `hypothesis.md`. State is `.state/journal.json`, `.state/progress.md`,
`.state/learnings.md`. The loop exits when the target metric is reached, the
circuit breaker trips, or the budget is spent.

A mode is just a directory under `modes/`. evaloop ships one; copy it and change
`mode.conf` to point the loop at a different kind of work. The engine reads what
a mode declares — its entry file, state file, work array and status
vocabulary — and knows nothing about the shipped names. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## Project Structure

```
evaloop/
├── run.py              # CLI and the optional session loop
├── core.py             # verification, scoring integrity, state, metrics
├── modes/experiment/   # the one bundled loop; --mode also takes a path
├── tests/              # 93 tests, run by CI on 3.10 / 3.11 / 3.12
├── bench/              # does an agent get around the controls? (live sessions)
├── docs/               # verification, empirical record, design rationale, archive
├── assets/             # diagrams
└── examples/
    ├── quant-lab/      # scores anywhere; used by the quick start and CI
    ├── tamper-demo/    # the integrity layer, replayed, no LLM calls
    ├── goal-vs-loop/   # four live sessions, transcripts kept
    └── qlib-quant/     # real market data, twelve sessions, five-fold held-out study
```

## Does any of this matter?

The qlib example ran an eleven-round hyperparameter sweep, then both
configurations were scored across five folds against years no round ever saw.
Paired difference, tuned minus baseline:

| Segment | Mean | *t*(4) | Folds positive |
|---|---|---|---|
| Selected on | **+0.6787** | +5.94 | 5 / 5 |
| Held out | **+0.0260** | +0.06 | 3 / 5 |

**The tuning reliably improves the metric it was chosen by and does nothing
measurable to the one it was not.** Nobody cheated in any of those runs. That is
what a held-out metric buys, and no amount of care on the visible segment would
have shown it.

What has and has not been measured, what those figures do not show, and where
this repository's own earlier readings were wrong:
[docs/empirical-record.md](docs/empirical-record.md).

## CLI Reference

```
python run.py verify  <project> [--sealed-verify FILE]   # score only, no LLM
python run.py loop    <project> [--sealed-verify FILE] [options]
python run.py status  <project>                          # phase and progress
python run.py list-modes                                 # modes found in modes/
python run.py <project> [options]                        # backward compat → loop

--mode NAME   A bundled mode name, or a path to any directory holding a
              mode.conf. Defaults to the bundled `experiment`.
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

### Which failure this catches, and which it does not

Manheim and Garrabrant's [taxonomy of Goodhart variants](https://arxiv.org/abs/1803.04585)
partitions this project's controls, including where they stop:

| Variant | What goes wrong | Caught by |
|---|---|---|
| **Adversarial** | An agent exploits the metric | sealing, fingerprints, leak detection |
| **Regressional** | Selecting on a noisy proxy selects the noise — no misbehaviour required | the held-out metric and its gate |
| **Extremal** | Optimisation walks into a regime where the proxy stops tracking the goal | the held-out metric, if the held-out data is from that regime |
| **Causal** | You intervened on a correlate that was never causally upstream | **nothing here** |

The variant that sounds most alarming, adversarial, is the least important of the
three this project addresses, because it needs someone to misbehave.
Regressional needs no one to misbehave, and it is what the qlib run shows.

Causal Goodhart is untouched and probably untouchable by tooling: a held-out
sample of the wrong thing agrees with a visible sample of the wrong thing.
Choosing what to measure stays with you.

The thesis is older than the tooling. Campbell, 1979: *"The more any quantitative
social indicator is used for social decision-making, the more subject it will be
to corruption pressures and the more apt it will be to distort and corrupt the
social processes it is intended to monitor."* An autonomous loop is the most
concentrated form of that pressure — it is the metric's only consumer, and it
consumes it thousands of times.

### The framing this follows

- **LangChain** [4-loop stack](https://blog.langchain.dev/the-art-of-loop-engineering/): Agent → Verification → Application → Hill Climbing. This project is Loop 2.
- **Osmani** [Loop Engineering](https://addyosmani.com/blog/loop-engineering): "Reliability comes from the loop, not the model."
- **MLE-bench** [research agents](https://arxiv.org/html/2507.02554): a 9–13% validation/test generalization gap — the empirical case for withholding a metric.
- **RewardHackBench** [sandbox policies](https://github.com/islo-labs/reward-hack-bench): scoring belongs in an environment the agent does not control.
- **Argyris & Schön** double-loop learning: the inner loop adjusts the action, the outer questions the governing variable. The held-out gate is the outer loop.
- **Boyd** OODA: Orient updates your model of the situation. Here it is arithmetic over two series, not a language model asked for an opinion.

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

Nothing, for `verify` and `status`. evaloop is standard library only, and there
is no `requirements.txt` because there is nothing to install.

To run the loop you need one of:

```bash
npm install -g @anthropic-ai/claude-code   # the CLI path
pip install claude-agent-sdk               # optional: adds SDK hooks and cost tracking
```

`--simulate` needs neither. The bundled examples want `numpy` and `pandas`, and
`examples/qlib-quant` wants rather more — see its
[prerequisites](examples/qlib-quant/PREREQUISITES.md).

## FAQ

**How much does it cost?**
`verify` subcommand is free (no LLM). Each `loop` session is one Claude Code invocation. `--max-budget` caps total spend.

**Can I use a different LLM?**
Yes. The verification layer is LLM-agnostic. Replace the `claude -p` call in `run_cli_session()` with your CLI tool.

**Can I resume after Ctrl+C?**
Yes. Same command again. The engine re-reads `.state/` and continues from where it left off.

**What's the `.verify` file?**
A per-project override for the scoring commands, taking precedence over `mode.conf`. It lives inside the project, so the agent can edit it — which is why a session that changes it is reported as `TAMPERED`, and why `--sealed-verify` exists for the cases where that is not good enough.

**Why is there a mode system if only one mode ships?**
Because a mode is the only thing that describes your loop: which file states the goal, which file holds the work, and what statuses that work can be in. The engine reads those declarations and knows nothing about the bundled name. `--mode` takes a path, so copy `modes/experiment/` into your own project and point at it there — it does not have to live in this repository.

**What happened to engineer and auditor modes?**
Cut in 7.0. Everything that makes this project worth using — held-out metrics, sealed scoring, integrity checks — only applied to the metric-scored loop. See [the design rationale](docs/design-rationale.md).

## References

**Design:**
- [Design Rationale](docs/design-rationale.md) — Why this architecture, what alternatives were considered
- [Archived essays](docs/archive/) — the stateless-session argument, the OODA outer loop and
  the Peirce three-role case, written for the three-mode architecture that shipped
  through v6. The arguments hold; the mode inventory does not

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
