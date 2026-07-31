# quant-lab — a project that scores, anywhere

The smallest example with a real metric. A synthetic price series, a strategy
file to edit, and a backtest that prints a Sharpe. numpy and pandas are the only
requirements, so this is the example used in the quick start and in CI.

```bash
python run.py verify examples/quant-lab
```

It ships with no `.state/`. Through 7.4 it carried a `journal.json` describing
six experiments and a best metric of 1.89, added as a demo in March and never
produced by a run — there are no transcripts, because there were no sessions. A
repository whose stated rule is that claims must point at a tracked artifact
cannot ship a fabricated experiment log as an example of one. It was removed
rather than relabelled.

For state that came from real sessions, see
[`goal-vs-loop`](../goal-vs-loop/) (four live sessions, transcripts included) and
[`qlib-quant`](../qlib-quant/) (twelve sessions and a five-fold held-out study).
