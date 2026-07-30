# auto-dev-agentos — Project Instructions

> Auto-read by Claude Code when working on this repository.

## What This Project Is

A verification harness (Loop 2) for LLM agent loops. Two engines:
- `run.py` (~485 lines of Python) — subcommand CLI: verify, loop, status, list-modes
- `core.py` (~251 lines) — pure functions: verification API, state management, metrics

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
- Smoke test: `python3 run.py status examples/todo-app`
- Verify test: `python3 run.py verify examples/quant-lab --mode researcher`
- Simulation test: `python3 run.py loop --simulate --mode engineer --pause 0 /tmp/test-project`
- run.py must stay under 500 lines, core.py under 260 lines
- Pure functions go in core.py, not in run.py

## Key Design Rules

1. **Structurally separate evaluation** — verification is architecturally independent from generation
2. **Hidden out-of-sample** — `hidden_verify_command` output never fed back to LLM
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
