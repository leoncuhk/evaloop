# Held-out measurement — 2026-07-30

The first out-of-sample result this project has produced. Until now the hidden
split had been executed exactly once, at commit `e8bf29f`, and its output was
never persisted; every number in the record came from the segment the
hyperparameters were selected on.

## Method

Two configurations, each scored twice through `run.py verify` with the scoring
definition sealed outside the project:

```
hidden_verify_command=python3 run_qlib_backtest.py --split test   # ~/qlib-sealed.conf
python3 run.py verify examples/qlib-quant --sealed-verify ~/qlib-sealed.conf
```

`--split train` evaluates the **2022 valid** segment — the one all 11 tuning
rounds selected on. `--split test` evaluates **2023**, which no round ever saw.
Everything else held fixed: CSI300, Alpha158, `lr=0.0421`, `max_depth=8`,
`num_leaves=210`, train 2018-01-01 → 2021-12-31.

## Result

| Configuration | 2022 (selected on) | 2023 (held out) |
|---|---|---|
| **A** baseline, λ1=205.7 λ2=581.0 | **2.9746** | **−1.1125** |
| **B** tuned, λ1=100.0 λ2=200.0 | **3.6430** | **−0.0297** |
| Change | **+0.6684 (+22.5%)** | **+1.0828** |

Both visible figures reproduce the journal at `e8bf29f` to four decimals, so the
pipeline is deterministic and the historical record is sound. The held-out
figures are new.

## What this shows

**Neither configuration generalizes.** A Sharpe of 3.64 on the segment it was
selected on corresponds to −0.03 on the year that follows — a gap of roughly 3.7
Sharpe points. Whatever the sweep found, it is not an edge that survives into
2023.

**The tuning direction was real; its magnitude was not.** Lowering λ improved the
held-out figure too, by 1.08. So the sweep was not fitting pure noise — less
regularization genuinely helped this model generalize. But the visible gain of
+0.67 has no out-of-sample counterpart: out of sample the model moves from
clearly losing to roughly flat, not from good to better.

This corrects an earlier reading in `learnings.md` and in review notes, which
called the +22.5% a selection artifact outright. It was not purely that. The
accurate statement is narrower: **the direction transferred, the level did not,
and the visible number was never evidence about 2023 either way.**

## What this does not show

- **One run, one seed, one pair of annual segments.** The pipeline is
  deterministic, so these numbers repeat exactly — but there is no distribution
  across seeds, no rolling window, and therefore no confidence interval.
- **The backtest is not qlib's pipeline.** `run_qlib_backtest.py` implements its
  own top-30 / bottom-30 long-short with daily full turnover and no transaction
  cost, slippage or position limits, despite `hypothesis.md` requiring the
  standard pipeline. Both columns inherit that. These figures compare two
  configurations under one construction; they are not statements about tradeable
  performance.
- **Nothing about other lever classes.** Feature engineering (EXP-011,
  Alpha158 → Alpha360) was never run.

## A note on the measurement itself

Run B's held-out output was:

```
[Metric] Sharpe Ratio: -0.0297
[Metric] Annualized Return: -0.0036
[Metric] IC Mean: -0.0037
```

The metric parser shipped through v6.0 used `([0-9]*\.?[0-9]+)`, which cannot
match a signed number, with a label pattern that spanned newlines. Against this
output it returns `None`; against output where a later `[Metric]` line is
positive it returns that line's value instead. Either way the first held-out
measurement this project ever took would have been recorded wrongly — silently
absent, or silently positive — by the one function whose job is to notice a loss.
It was fixed in 7.0 before these runs, which is the only reason the table above
says what the model actually did.

## Reproducing

Requires the environment in [`../../PREREQUISITES.md`](../../PREREQUISITES.md).
Configuration B is the repository baseline with two values changed:

```
lambda_l1: 205.7  ->  100.0
lambda_l2: 581.0  ->  200.0
```

Each `verify` fits the model twice (once per split), about 14 minutes total.
