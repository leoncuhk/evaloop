#!/usr/bin/env python3
"""
Quant Lab — Backtest Runner
Runs the active strategy and outputs the Sharpe Ratio metric.
Output format: [Metric] Sharpe Ratio: <float>

Supports train/test split for hidden out-of-sample verification:
  python run_backtest.py              # all data (default)
  python run_backtest.py --split train  # first 70% (visible to LLM)
  python run_backtest.py --split test   # last 30% (hidden from LLM)
  python run_backtest.py --split confirm  # a third draw, read once at the end
  python run_backtest.py --split test --blocks 5   # also print per-block samples

--blocks N prints `[Sample] block k: <sharpe>` lines after the metric, so the
held-out gate can judge a lower confidence bound instead of one noisy number.
"""
import argparse
import numpy as np
import pandas as pd
from strategies import active_strategy

SEED = 38
TEST_SEED_OFFSET = 17
CONFIRM_SEED_OFFSET = 29
N_DAYS = 500
TRAIN_RATIO = 0.7


def generate_price_data(n_days=N_DAYS, seed_offset=0):
    """Generate synthetic price data with momentum and cyclical patterns."""
    np.random.seed(SEED + seed_offset)
    returns = np.random.normal(0.0005, 0.015, n_days)
    for i in range(1, n_days):
        returns[i] += 0.15 * returns[i - 1]
    prices = 100 * np.cumprod(1 + returns)
    return pd.DataFrame({
        "close": prices,
        "high": prices * (1 + np.abs(np.random.normal(0, 0.005, n_days))),
        "low": prices * (1 - np.abs(np.random.normal(0, 0.005, n_days))),
        "volume": np.random.randint(1000, 10000, n_days).astype(float),
    })


def calculate_sharpe(returns, risk_free_rate=0.02):
    """Annualized Sharpe Ratio."""
    if len(returns) == 0 or returns.std() == 0:
        return 0.0
    excess_returns = returns - risk_free_rate / 252
    return float(np.sqrt(252) * excess_returns.mean() / excess_returns.std())


def run_backtest(data, strategy_func):
    """Run backtest with given strategy function."""
    signals = strategy_func(data)
    price_returns = data["close"].pct_change().fillna(0)
    strategy_returns = signals.shift(1).fillna(0) * price_returns
    return strategy_returns


def main():
    parser = argparse.ArgumentParser(description="Quant Lab Backtest Runner")
    parser.add_argument(
        "--split", choices=["train", "test", "confirm", "all"], default="all",
        help="Data split: train (first 70%%), test (last 30%%), confirm, or all"
    )
    parser.add_argument("--blocks", type=int, default=0,
                        help="Also print per-block Sharpe samples")
    args = parser.parse_args()

    data = generate_price_data()

    split_point = int(len(data) * TRAIN_RATIO)
    if args.split == "train":
        data = data.iloc[:split_point].reset_index(drop=True)
    elif args.split in ("test", "confirm"):
        offset = TEST_SEED_OFFSET if args.split == "test" else CONFIRM_SEED_OFFSET
        data = generate_price_data(seed_offset=offset)
        data = data.iloc[split_point:].reset_index(drop=True)

    strategy_returns = run_backtest(data, active_strategy)
    sharpe = calculate_sharpe(strategy_returns)
    print(f"[Metric] Sharpe Ratio: {sharpe:.4f}")
    if args.blocks > 1:
        size = len(strategy_returns) // args.blocks
        for k in range(args.blocks):
            block = strategy_returns.iloc[k * size:(k + 1) * size]
            print(f"[Sample] block {k + 1}: {calculate_sharpe(block):.4f}")


if __name__ == "__main__":
    main()
