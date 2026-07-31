#!/usr/bin/env python3
"""Rolling-window study: does the tuning gain transfer, across more than one year?

The held-out result recorded on 2026-07-30 rests on a single pair of segments —
selected on 2022, held out on 2023. One fold is an observation, not a finding.
This walks the same two configurations across several folds so the claim can be
stated with a range instead of a point.

Each fold trains from 2018 to the year before its validation year, selects on
the validation year, and is scored on the year after it. The model is fitted
once per fold and per configuration, then scored on both segments — the same
fit, two evaluations — using `score()` from run_qlib_backtest.py so this study
cannot drift from the single-fold runner.

    python run_rolling.py                       # every fold, both configurations
    python run_rolling.py --folds 2022 2023     # only these validation years

Writes .state/history/rolling-<date>.json. Requires the environment described in
PREREQUISITES.md; each fold-configuration pair is a full LightGBM fit.
"""
import argparse
import copy
import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
sys.path.insert(0, str(Path(__file__).parent))

# Validation years. Training always starts in 2018; the test segment is the year
# after validation, so the model never sees it during selection.
FOLDS = [2020, 2021, 2022, 2023, 2024]

CONFIGS = {
    "baseline": {"lambda_l1": 205.7, "lambda_l2": 581.0},
    "tuned": {"lambda_l1": 100.0, "lambda_l2": 200.0},
}


def fold_config(base: dict, valid_year: int, overrides: dict) -> dict:
    """The repository config, re-dated for one fold and re-tuned for one arm."""
    conf = copy.deepcopy(base)
    handler = conf["dataset"]["kwargs"]["handler"]["kwargs"]
    train = (f"2018-01-01", f"{valid_year - 1}-12-31")
    valid = (f"{valid_year}-01-01", f"{valid_year}-12-31")
    test = (f"{valid_year + 1}-01-01", f"{valid_year + 1}-12-31")
    handler["start_time"], handler["end_time"] = train[0], test[1]
    handler["fit_start_time"], handler["fit_end_time"] = train
    conf["dataset"]["kwargs"]["segments"] = {
        "train": list(train), "valid": list(valid), "test": list(test)}
    conf["model"]["kwargs"].update(overrides)
    return conf


_QLIB_READY = False


def ensure_qlib():
    """qlib refuses a second init in one process, so do it once."""
    global _QLIB_READY
    if not _QLIB_READY:
        import qlib
        qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")
        _QLIB_READY = True


def run_fold(base: dict, valid_year: int, arm: str, overrides: dict) -> dict:
    from qlib.utils import init_instance_by_config
    from run_qlib_backtest import score

    ensure_qlib()
    conf = fold_config(base, valid_year, overrides)
    dataset = init_instance_by_config(conf["dataset"])
    model = init_instance_by_config(conf["model"])
    model.fit(dataset)

    topk = conf.get("strategy", {}).get("topk", 30)
    selected = score(model, dataset, "valid", topk)   # what the loop would see
    held_out = score(model, dataset, "test", topk)    # what it never sees
    return {"valid_year": valid_year, "test_year": valid_year + 1, "arm": arm,
            "params": overrides, "selected_on": selected, "held_out": held_out}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folds", nargs="*", type=int, default=FOLDS)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    here = Path(__file__).parent
    import yaml
    base = yaml.safe_load((here / "qlib_config.yaml").read_text())

    results = []
    for valid_year in args.folds:
        for arm, overrides in CONFIGS.items():
            print(f"[fold] valid {valid_year} / test {valid_year + 1} — {arm}", flush=True)
            try:
                r = run_fold(base, valid_year, arm, overrides)
            except Exception as e:                      # a fold that cannot be
                print(f"  failed: {e}", file=sys.stderr)  # scored is not a zero
                r = {"valid_year": valid_year, "test_year": valid_year + 1,
                     "arm": arm, "params": overrides, "error": str(e)}
            results.append(r)
            print(f"  {json.dumps(r)}", flush=True)

    out = Path(args.out) if args.out else (
        here / ".state" / "history" /
        f"rolling-{datetime.now(timezone.utc).date().isoformat()}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "note": ("Rolling-window study. Training starts 2018 in every fold; the "
                 "model is selected on the validation year and scored on the "
                 "year after it. Same fit, two evaluations, scored by "
                 "run_qlib_backtest.score(). Inherits that runner's "
                 "construction: top-30 long-short, daily full turnover, no "
                 "transaction cost."),
        "generated": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }, indent=2) + "\n")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
