# evaloop — Project Instructions

> Auto-read by Claude Code when working on this repository.

## What This Project Is

Evaluation-driven autonomous development: a harness for loops whose acceptance
criterion is a metric rather than a test suite. Two engines:
- `run.py` (~577 lines of Python) — subcommand CLI: verify, loop, status, list-modes
- `core.py` (~446 lines) — pure functions: verification, scoring integrity, state, metrics

## Architecture

- `core.py` — verification harness core (`run_verification`, `resolve_verify_cmd`, state, metrics)
- `run.py` — CLI + optional session loop (wraps core.py verification around agent sessions)
- `modes/<name>/` — mode-specific logic (mode.conf + CLAUDE.md + prompts/)
- `examples/<project>/.state/learnings.md` — cross-session knowledge, tracked
- `examples/<project>/.state/history/` — archived records of completed runs
- `examples/<project>/logs/` — verbatim session transcripts, tracked
- `tests/test_run.py` — unit tests for core.py functions
- `tests/test_integration.py` — integration tests (loop orchestration + standalone verification)

## Working on This Codebase

- Run tests: `python3 tests/test_run.py && python3 tests/test_integration.py`
- Syntax check: `python3 -c "import ast; ast.parse(open('run.py').read())"` 
- Smoke test: `python3 run.py status examples/quant-lab`
- Integrity demo: `python3 run.py loop --simulate --pause 0 examples/tamper-demo`
  (reset with `rm -rf examples/tamper-demo/.state/journal.json examples/tamper-demo/logs`)
- Verify test: `python3 run.py verify examples/quant-lab`
- Simulation test: `python3 run.py loop --simulate --pause 0 examples/tamper-demo`
- run.py must stay under 620 lines, core.py under 460 lines
- Pure functions go in core.py, not in run.py

## Key Design Rules

1. **Structurally separate evaluation** — verification is architecturally independent from generation
2. **Hidden out-of-sample** — `hidden_verify_command` output never fed back to LLM,
   and with `--sealed-verify` the agent cannot redefine or reach the command
2b. **Scoring integrity** — in-project scoring files are fingerprinted around each
   session; a rewritten scorer makes the metric untrusted, never a result
3. **Stateless sessions** — each LLM call starts fresh, state lives in files
4. **Deterministic orchestration** — Python decides flow, not LLM
5. **One task per session** — no multi-task sessions
6. **State validation** — JSON state validated before write, backed up before overwrite
7. **Budget cap** — max cost per run prevents runaway spending
8. **Minimal** — no frameworks, no Docker, no magic
9. **Evidence is tracked** — session transcripts, archived runs, and learnings are
   version-controlled. Resetting an example to baseline means moving its records
   into `.state/history/`, never deleting them.
10. **Claims cite files** — anything the README asserts about what was measured
    must point at a tracked artifact that a reader can open.
