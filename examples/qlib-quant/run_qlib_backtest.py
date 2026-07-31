#!/usr/bin/env python3
"""
Qlib Backtest Runner — evaloop loop integration.

Trains LightGBM on CSI300 Alpha158 features, evaluates predictions
via IC and a simple top-k signal-return correlation.

Usage:
  python run_qlib_backtest.py                # test period
  python run_qlib_backtest.py --split train  # validation period (visible to LLM)
  python run_qlib_backtest.py --split test   # test period (hidden from LLM)

Output (parsed by verify_command):
  [Metric] Sharpe Ratio: <float>
  [Metric] IC Mean: <float>
"""
import argparse
import os
import sys
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

from pathlib import Path

TRAIN_START, TRAIN_END = "2018-01-01", "2021-12-31"
VALID_START, VALID_END = "2022-01-01", "2022-12-31"
TEST_START, TEST_END = "2023-01-01", "2023-12-31"


def score(model, dataset, seg, topk=30):
    """Score a fitted model on one segment. IC and a top-k long-short Sharpe.

    Factored out so the rolling study in run_rolling.py measures with exactly
    this code. Two implementations of one metric is how two answers to one
    question happen.
    """
    import numpy as np
    import pandas as pd

    pred = model.predict(dataset, segment=seg)
    if isinstance(pred, pd.Series):
        pred = pred.to_frame("score")
    else:
        pred.columns = ["score"]
    label = dataset.prepare(seg, col_set="label")
    if isinstance(label, pd.DataFrame):
        label = label.iloc[:, 0]

    common = pred.index.intersection(label.index)
    pred_aligned = pred.loc[common, "score"]
    label_aligned = label.loc[common]

    ic_series = pred_aligned.groupby("datetime").corr(label_aligned)
    ic_mean = float(ic_series.mean()) if len(ic_series) > 0 else 0.0

    daily = []
    for dt, group in pred_aligned.groupby("datetime"):
        top = group.nlargest(topk).index.get_level_values("instrument")
        bottom = group.nsmallest(topk).index.get_level_values("instrument")
        day = label_aligned.xs(dt, level="datetime")
        daily.append(float(day.reindex(top).mean() - day.reindex(bottom).mean()))

    daily = np.array(daily)
    if len(daily) > 5 and daily.std() > 0:
        return {"sharpe": float(np.sqrt(252) * daily.mean() / daily.std()),
                "ann_return": float(daily.mean() * 252), "ic": ic_mean,
                "days": len(daily)}
    return {"sharpe": 0.0, "ann_return": 0.0, "ic": ic_mean, "days": len(daily)}


def run(split="all"):
    import qlib
    import numpy as np
    import pandas as pd
    from qlib.utils import init_instance_by_config

    qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")

    config_path = Path(__file__).parent / "qlib_config.yaml"
    if config_path.exists():
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)
    else:
        config = default_config()

    dataset = init_instance_by_config(config["dataset"])
    model = init_instance_by_config(config["model"])
    model.fit(dataset)

    # Get predictions and labels for evaluation segment
    if split == "train":
        seg = "valid"
    elif split == "test":
        seg = "test"
    else:
        seg = "test"

    topk = config.get("strategy", {}).get("topk", 30)
    m = score(model, dataset, seg, topk)
    sharpe, ann_return, ic_mean = m["sharpe"], m["ann_return"], m["ic"]

    print(f"[Metric] Sharpe Ratio: {sharpe:.4f}")
    print(f"[Metric] Annualized Return: {ann_return:.4f}")
    print(f"[Metric] IC Mean: {ic_mean:.4f}")


def default_config():
    return {
        "model": {"class": "LGBModel", "module_path": "qlib.contrib.model.gbdt",
                  "kwargs": {"loss": "mse", "learning_rate": 0.05, "num_leaves": 128, "max_depth": 6}},
        "dataset": {"class": "DatasetH", "module_path": "qlib.data.dataset",
                    "kwargs": {"handler": {"class": "Alpha158", "module_path": "qlib.contrib.data.handler",
                                           "kwargs": {"start_time": TRAIN_START, "end_time": TEST_END,
                                                      "fit_start_time": TRAIN_START, "fit_end_time": TRAIN_END,
                                                      "instruments": "csi300"}},
                               "segments": {"train": [TRAIN_START, TRAIN_END],
                                           "valid": [VALID_START, VALID_END],
                                           "test": [TEST_START, TEST_END]}}},
        "strategy": {"topk": 30, "n_drop": 5},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["train", "test", "all"], default="all")
    args = parser.parse_args()
    try:
        run(args.split)
    except Exception as e:
        # Deliberately no [Metric] line: a crash is a failed verification, and
        # printing 0.0000 would enter the journal as a real measurement.
        print(f"[Error] {e}", file=sys.stderr)
        sys.exit(1)
