# Contributing to evaloop

## Quick Setup

```bash
git clone https://github.com/leoncuhk/evaloop
cd evaloop

# Verify harness
python3 run.py list-modes
python3 run.py status examples/todo-app
python3 run.py verify examples/quant-lab

# Run all tests (54 total)
python3 tests/test_run.py           # 17 unit tests
python3 tests/test_integration.py   # 37 integration tests

# Test session loop with simulation (no LLM calls)
python3 run.py loop --simulate --pause 0 examples/tamper-demo
```

## Project Structure

- `run.py` — Verification harness CLI (v6.0, subcommands: verify/loop/status, 485 lines)
- `core.py` — Core verification API + pure functions (251 lines)
- `modes/<name>/` — Mode-specific logic (conf + CLAUDE.md + prompts)
- `tests/` — Unit tests + integration tests (no SDK dependency)
- `docs/` — Design rationale and methodology articles
- `examples/` — Demo projects (todo-app, quant-lab, qlib-quant)

## Adding a New Mode

evaloop ships one mode. A mode is just a directory, so defining your own is
how you point the loop at a different kind of work.

1. Create `modes/<name>/mode.conf`:
   ```ini
   description=What this mode does
   entry_file=input.md
   state_file=state.json
   pending_query=[.items[] | select(.status == "pending")] | length
   progress_query=[.items[] | select(.status == "done")] | length
   phase_init=planner
   phase_work=worker
   phase_review=checker
   phase_orient=strategist
   claude_md=CLAUDE.md
   verify_command=your-test-command
   hidden_verify_command=your-hidden-test-command
   ```

2. Create `modes/<name>/CLAUDE.md` — agent workflow rules
3. Create `modes/<name>/prompts/` with 3-4 prompt files:
   - `planner.md` (init phase)
   - `worker.md` (work phase)
   - `checker.md` (review phase)
   - `strategist.md` (orient phase, optional)

4. Test with subcommands:
   ```bash
   python3 run.py status <project-dir> --mode <name>
   python3 run.py verify <project-dir> --mode <name>
   python3 run.py loop --mode <name> --simulate --pause 0 <project-dir>
   ```

## Code Style

- Python: Standard library only in `core.py` and `run.py` (except `claude-agent-sdk`). No type annotations on existing code unless changing the function.
- Prompts: Markdown. Include explicit Input, Steps, Rules, and Output sections.
- Tests: Add tests for any new pure functions. Tests must not require the SDK.

## Pull Request Process

1. Fork and create a feature branch
2. Make changes
3. Run all checks:
   ```bash
   python3 -c "import ast; ast.parse(open('run.py').read())"
   python3 -c "import ast; ast.parse(open('core.py').read())"
   python3 tests/test_run.py
   python3 tests/test_integration.py
   ```
4. Ensure run.py stays under 500 lines
5. Open a PR with a clear description of what changed and why

## Design Principles

Before making changes, understand the project's core thesis:

> Reliability in long-running AI agent tasks comes from system discipline — not from smarter models.

Changes should:
- Keep the engine minimal (< 500 lines)
- Not add framework dependencies
- Prefer file-based state over in-memory state
- Prefer deterministic orchestration over LLM-driven flow control
- Include tests that prove the behavior without requiring an LLM
