# Tamper demo

Two sessions, replayed from a script with no LLM calls, showing what evaloop does
when a session rewrites the thing that scores it.

Session 1 designs an experiment. Session 2 marks it accepted and edits
`run_backtest.py` to report 99.0 instead of 0.5.

The metric the orchestrator reads *is* the rewritten one — it cannot un-run the
edit. What it can do is notice, and refuse to call the number a result.

    python run.py loop --simulate --pause 0 examples/tamper-demo

Expected tail:

    verify: PASS (exit 0) | metric: 99.0
    TAMPERED: scoring inputs changed during the session: run_backtest.py
    The metric above was produced by definitions this session rewrote.
    1 session(s) rewrote their own scoring inputs. Those metrics are not results.

The same check fires on any edit to `.verify` or to a script a verification
command invokes. `--sealed-verify` prevents the equivalent attack on the config
itself, by keeping it outside the directory the agent can write to.

## Running it again

The demo leaves journal state behind, so a second run finds the work already done
and exits. Clear it and replay — no git needed, session 1 restores the scorer:

    rm -rf examples/tamper-demo/.state/journal.json examples/tamper-demo/logs
