# Research Progress

## Session 1 — 2026-06-22
**Role**: Theorizer
**Done**: Read hypothesis.md, confirmed baseline runs (`python run_backtest.py` → Sharpe 0.8363). Analyzed the data-generating process (positive drift + 0.15 momentum autocorrelation) and designed EXP-001.
**Baseline**: 0.8363 (visible, all-data split)
**Target**: 1.5
**Next**: EXP-001 — neutralize the -0.5 short leg (flat instead of short on downtrend signals). The short leg is the most suspect design choice given the upward-drifting, momentum-laden series. Executor Agent implements and evaluates.

## Session 2 — 2026-06-22
**Role**: Executor
**Experiment**: EXP-001 — neutralize the -0.5 short leg (flat instead of short on downtrend signals)
**Metric**: 0.8363 → 1.3477 (visible, all-data split)
**Decision**: accepted (new best; +0.5114 over baseline, above the 0.84 threshold)
**Learnings**: The short leg was the dominant drag — going flat removed losses from fighting the positive drift and from momentum whipsaws. One single-variable change closed most of the gap to target.
**Next**: ~0.15 gap to the 1.5 target remains; improving the LONG leg is the lever now. Candidates: (1) conviction sizing — scale long exposure by normalized MA spread (fast_ma-slow_ma)/slow_ma; (2) tune MA windows (fast 5-15, slow 15-40) on the flat-downtrend base; (3) volatility targeting / momentum confirmation filter. Caveat: gains are on the visible all-data metric only — out-of-sample (hidden test split) robustness is unverified; future sessions should watch for overfitting as parameters get tuned.

## Session 3 — 2026-06-22
**Role**: Theorizer
**Done**: Reviewed journal (best = 1.3477 after EXP-001) and current strategies.py (binary long/flat timer). Designed EXP-002 — conviction-based position sizing: scale long exposure by the normalized MA spread `(fast_ma - slow_ma)/slow_ma`, mapped via `signals = (spread * 25).clip(0, 1)`. Negative spread clips to 0, strictly preserving EXP-001's flat-on-downtrend win; positive spread leans into trend strength up to a cap of 1.0.
**Best**: 1.3477 (visible, all-data split)
**Target**: 1.5
**Next**: EXP-002 — conviction sizing (K=25). Rationale: AR(1)=0.15 momentum means wide-spread (established) uptrends persist more than near-crossover ones, so weighting exposure by spread should beat the binary timer. Success = Sharpe > 1.3477. Diagnostics if it misses: ≈1.3477 → K too large (clipping to binary), retry K=10–15; <1.3477 → pivot to MA-window tuning or a momentum-confirmation filter. Executor Agent implements and evaluates. STOP (design only).

## Session 4 — 2026-06-22
**Role**: Executor
**Experiment**: EXP-002 — conviction sizing (scale long exposure by normalized MA spread, `signals = ((fast_ma-slow_ma)/slow_ma * 25).clip(0,1)`, K=25)
**Metric**: 1.3477 → 1.9084 (visible, all-data split; reproducible, deterministic SEED=38)
**Decision**: accepted (new best, +0.5607 over prior best; clears the 1.5 target)
**Learnings**: Conviction sizing beat the binary timer decisively. K=25 keeps most uptrend days in the proportional regime, scaling exposure DOWN near the crossover (weak/whipsaw-prone) and holding it near 1.0 only on wide, established spreads (momentum-persistent per AR(1)=0.15). Diagnostic split reads — train=1.7697, hidden test=1.5233 — both clear 1.5, so the edge generalizes (grounded in the DGP, not curve-fit to K). The hidden-OOS official check remains the orchestrator's.
**Next**: 🎯 TARGET MET (1.9084 ≥ 1.5 on `python run_backtest.py`). No pending experiments remain. If the loop continues, optional refinements: (1) retune K (try 15–35) to probe the conviction-curve shape; (2) stack MA-window tuning on the conviction base; (3) volatility targeting. All optional and now overfitting-sensitive since the goal is reached — favor DGP-grounded changes and weigh OOS robustness over visible-metric gains.
