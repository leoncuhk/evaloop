# evaloop — Project Instructions

> Auto-read by Claude Code (2.1.277+) and Codex when working on this repository.

## What This Project Is

Evaluation-driven autonomous development: a harness for loops whose acceptance
criterion is a metric rather than a test suite. Its value is the standing of the
final number — intact, unselected, transferred — reported as an evidence verdict
rather than a metric. Construct validity is out of scope and always stated so.
- `run.py` (~670 lines of Python) — subcommand CLI: verify, loop, status, evidence, list-modes
- `core.py` (~640 lines) — pure functions: verification, scoring integrity, lower-bound gate, state, metrics
- `evidence.py` (~220 lines) — once-read confirmation split, evidence verdict, held-out data placement

## Architecture

- `core.py` — verification harness core (`run_verification`, `resolve_verify_cmd`, `held_out_gate`, `lower_bound`, state, metrics)
- `evidence.py` — `confirm_once`, `evidence`, `render`, `misplaced_hidden_data`; imports core, never imported by it
- `run.py` — CLI + optional session loop (wraps core.py verification around agent sessions)
- `modes/<name>/` — mode-specific logic (mode.conf + AGENTS.md + prompts/)
- `examples/<project>/.state/learnings.md` — cross-session knowledge, tracked
- `examples/<project>/.state/history/` — archived records of completed runs
- `examples/<project>/logs/` — verbatim session transcripts, tracked
- `tests/test_run.py` — unit tests for core.py functions
- `tests/test_integration.py` — integration tests (loop orchestration + standalone verification)

## Working on This Codebase

- Run tests: `python3 tests/test_run.py && python3 tests/test_integration.py` (examples need numpy and pandas)
- Syntax check: `python3 -c "import ast; ast.parse(open('run.py').read())"` 
- Smoke test: `python3 run.py status examples/quant-lab`
- Integrity demo: `python3 run.py loop --simulate --pause 0 examples/tamper-demo`
  (reset with `rm -rf examples/tamper-demo/.state/journal.json examples/tamper-demo/logs`)
- Verify test: `python3 run.py verify examples/quant-lab`
- Simulation test: `python3 run.py loop --simulate --pause 0 examples/tamper-demo`
- run.py must stay under 700 lines, core.py under 650, evidence.py under 250
- Pure functions go in core.py or evidence.py, not in run.py

## Key Design Rules

1. **Structurally separate evaluation** — verification is architecturally independent from generation
2. **Hidden out-of-sample** — `hidden_verify_command` output never fed back to LLM,
   and with `--sealed-verify` the agent cannot redefine or reach the command
3. **Scoring integrity** — in-project scoring files are fingerprinted around each
   session; a rewritten scorer makes the metric untrusted, never a result
4. **Stateless sessions** — each LLM call starts fresh, state lives in files
5. **Deterministic orchestration** — Python decides flow, not LLM
6. **One task per session** — no multi-task sessions
7. **The held-out metric gates completion** — reaching the visible target is
   not enough. The gate can only withhold completion, never cause it; it reads
   the latest clean record, never the best; discredited records are not evidence;
   it judges a lower confidence bound when the scorer prints `[Sample]` lines,
   else the point value against `target + held_out_margin`
8. **State validation** — the agent writes state directly, so the engine reads it
   back after each session and reports what is malformed; corrupt JSON is backed
   up on read. It does not gate the write. `safe_write_state` validates and
   writes atomically, for callers that write state themselves — the engine loop
   is not one of them
9. **Budget cap** — max cost per run prevents runaway spending
10. **Minimal** — no frameworks, no Docker, no magic
11. **Evidence is tracked** — session transcripts, archived runs, and learnings are
   version-controlled. Resetting an example to baseline means moving its records
   into `.state/history/`, never deleting them.
12. **Claims cite files** — anything the README asserts about what was measured
    must point at a tracked artifact that a reader can open.
13. **A run ends with a verdict, not a number** — the stopping point is selected
    on the held-out split, so the final claim rests on `confirm_verify_command`,
    read from the sealed file once and never re-run. Verdicts never claim more
    than the records support, and always name construct validity as not established.
