# Learnings — goal-vs-loop

Accumulated knowledge from past sessions. Read this before proposing an
experiment; it exists to stop future sessions from re-running known dead ends.

## Current state of this example

The working tree is reset to **baseline** (`strategies.py` at the original dual
MA crossover, Sharpe 0.8363) so the example is a clean starting point. A
completed 4-session run is preserved under `.state/history/`, and its full
commit-by-commit history is in `session-history.bundle` at the project root:

| File | What it holds |
|---|---|
| `.state/history/journal-exp001-002.json` | EXP-001 and EXP-002 with hypothesis, steps, metrics, learnings |
| `.state/history/progress-sessions-1-4.md` | The Theorizer/Executor session log |
| `logs/session_{1..4}.log` | Verbatim transcripts of the four live agent sessions |
| `../session-history.bundle` | The nested git repo — `git clone session-history.bundle` to replay the 5 commits |

## What the run found

- **EXP-001 — the short leg was the dominant drag.** Replacing
  `signals[fast_ma <= slow_ma] = -0.5` with `= 0.0` moved Sharpe 0.8363 → 1.3477
  in one single-variable change. The data-generating process has positive drift
  (~12.6% annualized) plus AR(1)=0.15 momentum, so shorting every downtrend
  signal fights the secular uptrend and bleeds on whipsaws.
- **EXP-002 — conviction sizing beat the binary timer.**
  `signals = ((fast_ma - slow_ma)/slow_ma * 25).clip(0, 1)` moved Sharpe
  1.3477 → 1.9084, clearing the 1.5 target. Negative spread clips to 0, so it
  strictly preserves the EXP-001 win. Mechanism: K=25 keeps most uptrend days in
  the proportional regime, so exposure scales down near the crossover (weak,
  whipsaw-prone) and stays near 1.0 only on wide, established spreads.
- Both gains are on the **visible all-data metric**. The DGP is synthetic with
  injected momentum, so the mechanism is real *for this DGP* and says nothing
  about real markets.

## Process finding: the hidden split is not enforced

Session 4's transcript reports:

> Robustness check (diagnostic only — the orchestrator owns the official
> hidden-OOS verification): train split = 1.7697, **hidden test split = 1.5233**.

The agent ran `--split test` itself and put the number in its own report. It was
transparent about doing so, and it drew the right conclusion — but that is the
point: **nothing stopped it.** The agent has shell access and the hidden split is
one flag away.

So the guarantee this harness actually provides today is: *the orchestrator does
not feed the hidden metric back.* It is **not**: *the agent cannot obtain it.*
Treat any hidden-OOS number produced inside a session as contaminated, and see
the README's "Empirical Record" section for what closing this gap would require.
