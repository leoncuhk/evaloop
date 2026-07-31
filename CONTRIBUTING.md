# Contributing to evaloop

## Setup

Nothing to install for the checks below — evaloop is standard library only.

```bash
git clone https://github.com/leoncuhk/evaloop && cd evaloop

python3 run.py list-modes
python3 run.py status examples/quant-lab
python3 run.py verify examples/quant-lab          # needs numpy + pandas

python3 tests/test_run.py                         # 17 unit tests
python3 tests/test_integration.py                 # 76 integration tests

# the loop end to end, replayed from a script — no LLM calls
python3 run.py loop --simulate --pause 0 examples/tamper-demo
```

## Layout

- `core.py` — verification, scoring integrity, state, metrics. Pure functions,
  usable as a library without the CLI
- `run.py` — the CLI and the optional session loop
- `modes/experiment/` — the one bundled loop. `--mode` also takes a path, so
  your own can live in your own project
- `tests/` — no SDK, no network, no LLM
- `bench/` — the adversarial benchmark. Live sessions, so it is not part of CI
- `docs/` — verification, empirical record, design rationale, and an archive of
  essays describing the pre-7.0 architecture
- `examples/` — quant-lab, tamper-demo, goal-vs-loop, qlib-quant

## Defining your own loop

A mode is a directory with a `mode.conf`, a `CLAUDE.md`, and a `prompts/`
folder. It does not have to live in this repository:

```ini
description=What this loop does
entry_file=hypothesis.md
state_file=journal.json

# The engine validates written state against these. A mode that omits them is
# not validated, and that should be a choice you made, not one you inherited.
state_array=experiments
valid_statuses=pending,running,accepted,rejected,error

pending_query=[.experiments[] | select(.status == "pending")] | length
progress_query=[.experiments[] | select(.status == "accepted" or .status == "rejected")] | length

phase_init=theorizer
phase_work=executor
phase_review=analyst
phase_orient=strategist
claude_md=CLAUDE.md

verify_command=your-scoring-command
metric_pattern=[Metric] Your Label:
verify_timeout=300

# Better placed in a sealed file outside the project. See docs/verification.md.
hidden_verify_command=your-held-out-command
```

Then `prompts/<name>.md` for each phase you named, and:

```bash
python3 run.py status  <project> --mode ./my-loop
python3 run.py verify  <project> --mode ./my-loop
python3 run.py loop    <project> --mode ./my-loop --simulate --pause 0
```

`tests/test_integration.py::test_user_defined_mode_drives_the_loop` drives an
unfamiliar mode end to end, to keep this a real extension point.

## What a change has to satisfy

**Claims must cite files.** Anything the README asserts about what was measured
has to point at a tracked artifact a reader can open. Several things have been
deleted from this repository for failing that: a validation script that printed
"VALIDATED" without establishing it, a fabricated experiment journal shipped as
an example, and three documented protections that no code path called.

**Evidence is tracked.** Session transcripts, archived runs and learnings are
version-controlled. Resetting an example to baseline means moving its records
into `.state/history/`, never deleting them.

**Tests prove behaviour without an LLM.** Every check in `tests/` runs offline.
Behaviour that needs a live model belongs in `bench/`.

**The engine stays small.** CI fails the build if `run.py` exceeds 660 lines or
`core.py` exceeds 600. Raise a budget only when the code that pushed it past is
worth more than the constraint, and say so in the commit.

**Standard library only** in `core.py` and `run.py`. `claude-agent-sdk` is
optional and imported behind a try/except.

## Before opening a PR

```bash
python3 -c "import ast; ast.parse(open('run.py').read())"
python3 -c "import ast; ast.parse(open('core.py').read())"
python3 tests/test_run.py && python3 tests/test_integration.py
python3 run.py loop --simulate --pause 0 examples/tamper-demo | grep TAMPERED
```

CI runs those plus the size budget on Python 3.10, 3.11 and 3.12.

## The thesis

> A loop can run unattended only for as long as its metric survives its own
> optimiser.

Changes should keep the evaluator separated from the generator, prefer
deterministic orchestration to LLM-driven control flow, prefer file state to
in-memory state, and state their limits where the limits are.
