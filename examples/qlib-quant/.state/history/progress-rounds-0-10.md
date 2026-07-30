# Progress Log — qlib_config.yaml model param tuning (/goal)

Objective: maximize Sharpe of `run_qlib_backtest.py --split train` (=2022 valid segment).
Do NOT run --split test (hidden). Stop when Sharpe stalls or 10 rounds reached.

## Round 0 — Baseline
**Sharpe**: 2.9746 | Ann.Return: 0.5550 | IC: 0.0285
**Params**: lr=0.0421, num_leaves=210, max_depth=8, colsample=0.8879, subsample=0.8789, l1=205.70, l2=580.98
**Decision**: baseline

## Round 1 — reduce regularization (l1=50, l2=100)
**Sharpe**: 3.2075 ↑ | Ann.Return: 0.5685 | IC: 0.0238
**Decision**: ACCEPTED (new best). Model was over-regularized.
**Next**: push regularization lower.

## Round 2 — too little regularization (l1=5, l2=10)
**Sharpe**: 2.6148 ↓ (below baseline) | Ann.Return: 0.4570 | IC: 0.0198
**Decision**: REJECTED. Underfit→overfit; optimum λ near round 1 (50/100).
**Next**: probe higher side, l1=100/l2=200.

## Round 3 — l1=100, l2=200
**Sharpe**: 3.6430 ↑ | Ann.Return: 0.6736 | IC: 0.0268
**Decision**: ACCEPTED (new best). Peak between 100/200 and 205/581.
**Next**: try l1=150/l2=300.

## Round 4 — l1=150, l2=300
**Sharpe**: 3.3430 ↓ | Ann.Return: 0.6111 | IC: 0.0279
**Decision**: REJECTED. Confirms λ peak at 100/200 (round 3). Locking λ=100/200.
**Next**: tune num_leaves (210→128) with λ fixed at 100/200.

## Round 5 — num_leaves 210→128 (λ=100/200)
**Sharpe**: 3.6430 = (identical to round 3) | Ann.Return: 0.6736 | IC: 0.0268
**Decision**: KEPT (equivalent, lower complexity). num_leaves not binding — λ+max_depth cap tree growth first.
**Next**: tune learning_rate 0.0421→0.02.

## Round 6 — learning_rate 0.0421→0.02
**Sharpe**: 3.2294 ↓ | Ann.Return: 0.5950 | IC: 0.0270
**Decision**: REJECTED. Lower lr hurt. Try higher lr.
**Next**: lr=0.07.

## Round 7 — learning_rate 0.0421→0.07
**Sharpe**: 3.0783 ↓ | Ann.Return: 0.5459 | IC: 0.0231
**Decision**: REJECTED. lr=0.0421 is optimal (both 0.02 and 0.07 worse). Reverting lr.
**Next**: max_depth 8→10.

## Round 8 — max_depth 8→10
**Sharpe**: 3.0794 ↓ | Ann.Return: 0.5361 | IC: 0.0218
**Decision**: REJECTED. Deeper trees overfit. Try shallower.
**Next**: max_depth=6.

## Round 9 — max_depth 8→6
**Sharpe**: 3.2114 ↓ | Ann.Return: 0.6224 | IC: 0.0265
**Decision**: REJECTED. max_depth=8 is the peak (6/8/10 → 3.21/3.64/3.08). Reverting to 8.
**Next**: final round — fine λ refinement l1=110/l2=220.

## Round 10 — fine λ refinement l1=110/l2=220
**Sharpe**: 3.3303 ↓ | Ann.Return: 0.6168 | IC: 0.0264
**Decision**: REJECTED. λ=100/200 remains the sharp peak. Restored best config.

## FINAL SUMMARY (10 rounds complete)
Baseline Sharpe 2.9746 → BEST Sharpe **3.6430** (+22.5%, Ann.Return 0.5550→0.6736).
Winning config: lr=0.0421, num_leaves=128, max_depth=8, λ1=100, λ2=200, colsample=0.8879, subsample=0.8789.
Key driver: regularization. Original λ (205/581) was over-regularized; optimum at λ1=100/λ2=200.
lr, max_depth, num_leaves were all already at/near their optima.
Stop condition: reached 10 rounds AND Sharpe plateaued (best found at round 3, unbeaten rounds 4-10).
NOTE: --split test (2023 hidden set) was never run, per instructions.
