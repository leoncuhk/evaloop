# Learnings — qlib-quant

Accumulated knowledge from past sessions. Read this before proposing an
experiment; it exists to stop future sessions from re-running known dead ends.

## Current state of this example

The working tree is reset to **baseline** (`qlib_config.yaml` at l1=205.7/l2=581,
`.state/journal.json` empty, `best_metric.txt` = 2.9746) so the example is a
clean starting point. The learnings below come from a completed 12-session run
whose records are preserved under `.state/history/`:

| File | What it holds |
|---|---|
| `.state/history/journal-rounds-0-10.json` | The 11-round hyperparameter sweep, one entry per round |
| `.state/history/progress-rounds-0-10.md` | The session-by-session log for those rounds |
| `.state/history/mlflow-runs.json` | Distilled MLflow record of the actual backtest executions |
| `logs/session_1.log` | Transcript of the Theorizer session that designed EXP-011 |

**Do not read the peak Sharpe of 3.6430 as the current metric.** It was reached
on a config that is no longer in the working tree.

## LightGBM hyperparameter tuning for 2022-valid Sharpe (qlib_config.yaml)

- **Regularization (λ1/λ2) is the dominant lever** and is sharply single-peaked. Sweep:
  λ1/λ2 = 5/10→2.61, 50/100→3.21, **100/200→3.64 (peak)**, 150/300→3.34, 205/581→2.97.
  The original config (205/581) was *over*-regularized; too little (5/10) overfits train.
- **learning_rate already optimal at 0.0421**: 0.02→3.23, 0.0421→3.64, 0.07→3.08.
- **max_depth optimal at 8**: 6→3.21, 8→3.64, 10→3.08.
- **num_leaves is NOT binding** — 210 vs 128 give identical results because max_depth=8 + λ cap
  tree growth before the leaf limit. Prefer 128 (same metric, lower complexity).
- Net: baseline Sharpe 2.9746 → 3.6430 (+22.5%) by only lowering λ to 100/200.
- IC and Sharpe are not perfectly aligned: round 1 raised Sharpe while *lowering* IC. Optimize the target (Sharpe).
- `--split train` evaluates the 2022 valid segment; `--split test` (2023) is hidden from the agent.

## Phase transition: model-HP tuning → feature engineering (EXP-011)

- **Model-HP space is exhausted.** All four scalar levers were swept to a single-peaked optimum and the peak has been unbeaten since round 3. Do NOT re-tune lr/max_depth/num_leaves/λ in isolation again — it is a known dead end at Sharpe 3.6430.
- The next lever is **feature engineering** (search-space item #1), the largest untouched one and the project's actual goal. The runner reads `dataset.kwargs.handler.class` straight from `qlib_config.yaml`, so the feature set is swappable with a one-line edit; both `Alpha158` and `Alpha360` handlers exist in the installed qlib.
- Caveat for whoever runs Alpha360: λ=100/200 was tuned for Alpha158's 158 features. Alpha360 has 360 raw features at a different scale, so the same λ may be mis-scaled — an Alpha360 loss is not proof features can't help; re-tune λ on the winning handler before concluding.

## Known limits of this example's measurement

These are properties of `run_qlib_backtest.py`, not discoveries — but any session
that reports a number from it inherits them, so read them before claiming a result.

- **The sweep selected on the evaluation segment.** All 11 rounds scored on
  `--split train`, which maps to the **2022 valid** segment. Choosing
  hyperparameters by the same segment you score on makes the +22.5% a
  selection gain, not an out-of-sample finding.
- **`--split test` (2023) was executed once, and the number was not kept.**
  `.state/history/mlflow-runs.json` records a `--split test` run at commit
  `e8bf29f` on 2026-06-22, but no `hidden_metrics.json` was ever written, so the
  Sharpe it printed is lost. The hidden out-of-sample check therefore has **no
  recorded result** for this example.
- **The backtest is not qlib's pipeline.** Despite `hypothesis.md` requiring
  qlib's standard backtest, `run_qlib_backtest.py` implements its own top-30 /
  bottom-30 long-short with daily full turnover and **no transaction cost, no
  slippage, no position limits**. The `topk`/`n_drop` TopkDropout settings in the
  config are read but never applied. A Sharpe near 3–4 under zero cost is the
  expected magnitude for this construction and should not be read as an edge.
- **Metric naming drift**: the runner's docstring calls the IC a rank
  correlation, but it computes Pearson; it calls the label a next-day return,
  while the Alpha158 default label is a two-day forward return.
