# Design Rationale

Why evaloop is designed the way it is — and what alternatives were considered.

> **A note on what changed.** Most of this document argues against *orchestration*
> frameworks, because until v6.0 this project competed with them. v6.0 narrowed the
> claim to a verification harness — Loop 2 — which puts it beside a different set of
> tools. The orchestration argument below is still the reason the loop is shaped the
> way it is, and it is preserved. The Loop-2 comparison is new, and it is the one
> that matters when deciding whether to use this.

## The Problem

Long-running LLM agent tasks fail predictably. A [2026 study](https://arxiv.org/abs/2601.03315) documented six recurring failure modes: context degradation, implementation drift, overexcitement, training data bias, insufficient domain knowledge, and weak scientific taste. Three of four autonomous research attempts in the study failed.

These are not model-specific bugs. They are structural properties of how LLMs process information over long horizons. Switching models does not fix them.

## The Design Space

We evaluated three classes of solutions:

### Multi-agent frameworks (BMAD, ChatDev, MetaGPT)

BMAD uses 26 specialized agents. ChatDev simulates a software company with CEO, CTO, programmer, tester roles. MetaGPT assigns SOPs to agents.

**Problem**: More agents = more coordination overhead. Agent-to-agent communication introduces compounding errors. The system becomes harder to debug than the code it produces. Reliability decreases as agent count increases.

### Single-session tools (Claude Code, Aider, Cursor Agent)

These tools run one LLM session that reads code, makes changes, runs tests, iterates. They work well for tasks that fit in a single context window.

**Problem**: Context degradation. After 30+ minutes, the model's attention to early instructions decays. It starts contradicting its own earlier work. Implementation drift accelerates. There is no external checkpoint to catch this.

### Platform agents (OpenHands, Devin)

Full platforms with Docker sandboxes, web GUIs, cloud execution. OpenHands has 68k+ stars. Devin handles end-to-end deployment.

**Problem**: Heavyweight. Docker dependency. Opaque orchestration. A developer cannot read and understand the control flow in 15 minutes. When something goes wrong, debugging requires understanding a complex distributed system.

## Our Choice: Deterministic Multi-Session Orchestration

evaloop takes a fourth approach:

1. **The orchestrator script decides what runs.** The LLM only executes single, well-scoped tasks.
2. **Each session is stateless.** Fresh context every time. No degradation.
3. **State lives in files.** JSON + markdown, git-versioned, human-readable.
4. **One task per session.** No room for drift.
5. **Verification is mandatory.** Tests and metrics decide, not the LLM.

This trades LLM autonomy for system reliability. The model is powerful but unreliable over long horizons. The orchestrator is simple but deterministic. Combining them produces reliability that neither achieves alone.

## What We Intentionally Do Not Do

- **No inter-agent communication.** Each session talks to files, not to other agents.
- **No persistent context.** Context windows are ephemeral; only files persist.
- **No framework dependency.** Python + markdown + git. Runs anywhere.
- **No web UI.** CLI only. The state files *are* the interface.
- **No model routing.** One model, deterministically invoked.

Each of these is a deliberate constraint that eliminates a class of failure modes.

## One Loop

Through v6 this project shipped three modes — engineer (deductive, spec to code),
researcher (inductive, hypothesis to metric) and auditor (abductive, standards to
findings). 7.0 ships only the second.

The reason is that the machinery which distinguishes this project — a held-out
metric, a sealed scoring definition, fingerprints around every session — only
ever applied to the second. Engineer mode's criterion is a test suite the agent
should not be editing anyway; where that is the criterion, a coding agent with a
test-run hook is the better tool, and pretending otherwise cost this project its
focus. Auditor mode's criterion is coverage, which nobody games.

Keeping all three made the project look general and be shallow. The loop itself
is unchanged: hypothesis → experiment → evaluate → learn, one experiment per
session, revert on regression, accumulate learnings.

A mode is still just a directory. The engine reads what a mode declares — entry
file, state file, work array, status vocabulary — and knows nothing about the
name `researcher`. Defining a loop for a different kind of work is a `mode.conf`
away, and the test suite drives an unfamiliar mode end to end to keep that true.

## Positioning

```
Complexity ────────────────────────────────────────────►

  Claude Code     evaloop     Gas Town        BMAD / MetaGPT
  (single session) (multi-session loop) (20-30 agents)  (26+ agents)
  
  Simple but       Simple and           Parallel but     Complex and
  degrades over    reliable over        complex          fragile
  long tasks       long tasks
```

evaloop occupies the space between "powerful but unreliable single session" and "complex multi-agent orchestration." Minimum viable reliability for long-running autonomous tasks.

## The Older Names for This Problem

The framing this project arrived at through practice has been stated before, more
precisely, by people who were not thinking about agents at all. Worth recording,
because it locates the work and shows which parts are genuinely new.

### Campbell's Law (1979)

Donald Campbell wrote the thesis of this project forty-seven years early:

> *"The more any quantitative social indicator is used for social decision-making,
> the more subject it will be to corruption pressures and the more apt it will be
> to distort and corrupt the social processes it is intended to monitor."*

Replace "social indicator" with "verify_command" and "social processes" with "the
work the agent is doing" and nothing else needs changing. An autonomous loop is
the most concentrated form of decision-making pressure a metric can be put under:
it is the *only* consumer of that number, and it consumes it thousands of times.

The companion is [Goodhart's Law](https://en.wikipedia.org/wiki/Goodhart's_law),
in Strathern's formulation: *when a measure becomes a target, it ceases to be a
good measure.*

### Which failure, and what catches it

Manheim and Garrabrant's [taxonomy of Goodhart variants](https://arxiv.org/abs/1803.04585)
splits the law into four mechanisms. They partition this project's controls
almost exactly, including where the controls do not reach:

| Variant | What goes wrong | What catches it here |
|---|---|---|
| **Adversarial** | An agent with its own goals exploits the metric | `--sealed-verify`, scoring fingerprints, leak detection |
| **Regressional** | Selecting on a noisy proxy selects the noise. No bad behaviour required | The held-out metric and its gate |
| **Extremal** | Optimisation walks into a regime where the proxy no longer tracks the goal | The held-out metric, when the held-out data comes from that other regime |
| **Causal** | You intervene on a correlate that was never causally upstream | **Nothing here.** evaloop cannot tell you the metric measures the wrong thing |

Two things follow. The first is that adversarial Goodhart — the variant that
sounds most alarming — is the *least* important of the three this project
addresses, because it requires misbehaviour. Regressional Goodhart requires
none, and it is what the qlib run demonstrates: eleven honest rounds, a visible
Sharpe of 3.6430, a held-out figure of −0.0297.

The second is that causal Goodhart is untouched and probably untouchable by
tooling. If your metric is the wrong thing to measure, a held-out sample of the
wrong thing will agree with the visible sample of the wrong thing. Choosing what
to measure remains a human judgement, and no part of this harness helps with it.

### Single loop, double loop

[Argyris and Schön's](https://infed.org/dir/welcome/chris-argyris-theories-of-action-double-loop-learning-and-organizational-learning/)
distinction describes the architecture more precisely than OODA does:

- **Single-loop learning** — detect a gap between intended and actual, adjust the
  action. *The room is cold, turn the thermostat up.*
- **Double-loop learning** — question the *governing variable* that made that the
  right action. *Why is the room cold — are we heating the street, or is the
  target temperature wrong?*

![Two nested loops. The inner blue loop runs act, measure, compare, adjust, and raises the visible metric. The outer amber loop takes that metric to a held-out check, asks whether the target is still right, and returns a gate decision of stop or continue. Caption: the inner loop hits the target, the outer loop asks whether the target was worth hitting](../assets/evaloop-double-loop.png)

An agent loop optimising `verify_command` is pure single-loop learning, and it
is very good at it. The held-out gate is the second loop: it does not adjust the
action, it asks whether the governing variable — *this metric, at this target* —
still means what it did when the run started.

Boyd's OODA remains the right vocabulary for the *phases* of a session, and the
Orient phase is where the second loop lives: Orient is the update to your model
of the situation, and the model most likely to be stale in a metric-driven loop
is "the visible metric still tracks what I want." That is why Orient in this
project is arithmetic over two series rather than a language model asked for an
opinion — the question has a computable answer.

## The Loop-2 Comparison

Once the claim is "verification harness," the neighbours change. Three families:

### LLM evaluation frameworks

[DeepEval](https://deepeval.com), [Inspect AI](https://inspect.aisi.org.uk) (UK AISI),
[promptfoo](https://promptfoo.dev), [Braintrust](https://braintrust.dev), LangSmith.
Large metric libraries, LLM-as-judge, dataset management, CI integration, and in
promptfoo's case a mature red-teaming CLI. These are more capable than this project at
what they do, and anyone measuring prompt or RAG changes should use one.

**The gap they leave**: their subject is a *system under test* that someone else edits
between runs. They assume the scorer and the thing scored are separated by process and
by person. In an autonomous loop that assumption breaks — the agent edits the artifact,
the tests, and the config, in the same directory, between every measurement. None of
these frameworks defends the scoring definition from the thing being scored, because
they were never asked to.

### Agent loop harnesses

[loop-harness](https://github.com/lSAAGl/loop-harness) is the closest structural
sibling: bash, no framework, scheduled loops, git worktree isolation, and a second
`claude -p` session that must print `VERDICT: PASS` before anything ships. Spec-driven
toolkits ([Spec Kit](https://github.com/github/spec-kit) and its descendants) put
validation gates between phases.

**The gap they leave**: the gate is an LLM judging another LLM's work, on data both can
see. That is a good check on whether the work is *sound* and a weak one on whether a
number *generalizes*. A judge cannot tell you a strategy is overfit if it only ever sees
the fit.

### Evolutionary program search

[AlphaEvolve](https://deepmind.google), [OpenEvolve](https://github.com/codelion/openevolve),
[ShinkaEvolve](https://github.com/SakanaAI/ShinkaEvolve). The nearest relative
architecturally: the evaluator is a separate program, cascade evaluation prunes weak
candidates cheaply, and the search runs for thousands of iterations. ShinkaEvolve
reports no significant overfitting to its public test cases.

**The gap they leave**: the community's own guidance is that you must hand-design an
unhackable evaluator, because the search will find every loophole. That is stated as a
prerequisite, not provided as a feature. This project is an attempt at the missing
piece — a scoring definition that stays out of the search's reach.

### Why hold data back at all

The empirical case is not speculative. Research agents on
[MLE-bench](https://arxiv.org/html/2507.02554) show a persistent **9–13%
validation/test generalization gap**: an agent optimising a proxy metric reliably
converges somewhere the held-out set does not follow. Instructing an LLM to tune
hyperparameters without a withheld set produces severe overfitting. A metric the agent
never sees is the only measurement that survives its own optimiser.

### Why sealing rather than sandboxing

[RewardHackBench](https://github.com/islo-labs/reward-hack-bench) measures whether
execution-environment policies stop agents cheating on evaluations, and finds static
gatekeeping brittle — content filters miss encodings, blocklists miss mirrors. The
architecture that holds is structural: scoring runs in an environment the agent does not
control, and the verdict is computed outside every sandbox.

Full sandboxing would mean Docker, which this project rejects for the reasons above. The
compromise it makes instead:

1. **Seal** the scoring definition outside the project (`--sealed-verify`) — structural,
   and the strongest control here.
2. **Fingerprint** in-project scoring files around each session — catches an agent that
   rewrites its own scorer, and marks the metric untrusted.
3. **Detect** hidden-metric leaks in transcripts — the weakest, and labelled as such. It
   marks a metric contaminated; it never certifies one clean.

This is deliberately less than containment. An agent that reads the hidden dataset
directly defeats all three. Sealing plus filesystem permissions on the held-out data is
the configuration to use when that matters.

## References

- [Why LLMs Aren't Scientists Yet](https://arxiv.org/abs/2601.03315) — Six failure modes (arXiv, 2026)
- [Building Effective AI Coding Agents](https://arxiv.org/abs/2603.05344) — Scaffolding + harness architecture (arXiv, 2026)
- [Spec-Driven Development](https://github.com/github/spec-kit) — GitHub's approach to spec → code
- [BMAD Method](https://github.com/24601/BMAD-AT-CLAUDE) — 26-agent framework
- [The Stateless Agent Architecture](archive/stateless-agent-architecture.md) — Full argument
- [The Dual-Loop Architecture](archive/dual-loop-architecture.md) — Strategic orientation via OODA
