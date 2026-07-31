# Changelog

## [7.2.0] — 2026-07-31

The held-out metric now decides something. Until this release it was written to
`.state/hidden_metrics.json` and read by nothing: the loop declared victory when
`best_metric` — the figure the agent had spent every session raising — reached
its target. A project whose thesis is that the visible metric cannot be trusted
was stopping on the visible metric.

### Added
- **The held-out gate.** When a held-out series exists, reaching the visible
  target is no longer sufficient to finish a run. Three properties keep it from
  becoming the leak it guards against: it can only withhold completion and never
  cause it, so it never steers the search; it reads the latest clean record
  rather than the best, because taking the maximum would be selecting on the
  held-out segment; and records from sessions that rewrote their own scoring or
  were caught quoting the held-out number are discarded. If every record is
  discredited the gate stays shut, so corrupting the record is not a way through
- **`divergence_report()` — Orient, computed rather than asked.** Printed every
  session at no cost, from two series already on disk. Three candidate rules were
  tested against the real qlib figures: direction agreement and gap convergence
  both say "continue" on a run that produced −0.0297 out of sample, and were
  discarded. Only *does the held-out figure clear the target* survives contact
  with the data
- **`.state/orient.md`** — the strategist is now handed the conclusion instead of
  being left to infer it from raw state. Orient is arithmetic; Decide is
  judgement
- Two diagrams: the exit condition, and the two nested loops
- 8 gate tests anchored on the qlib figures (91 total)

### Changed
- `docs/design-rationale.md` records the older names for this problem: Campbell's
  Law (1979) states the thesis forty-seven years early, and Manheim and
  Garrabrant's Goodhart taxonomy partitions the controls — including causal
  Goodhart, which nothing here catches and probably nothing can. Argyris and
  Schön's single/double-loop distinction describes the architecture more
  precisely than OODA, which remains the right vocabulary for session phases

## [7.1.0] — 2026-07-30

The harness produced its first held-out result, and a review pass found three
places where the code did something the documentation did not admit.

### Added
- **The held-out measurement.** Both qlib configurations scored against 2023 —
  the segment no tuning round ever saw — with the scoring definition sealed
  outside the project. Baseline **−1.1125**, tuned peak **−0.0297**, against
  2.9746 and 3.6430 on the segment they were selected on. Both visible figures
  reproduce the journal at `e8bf29f` to four decimals. Method, caveats and
  reproduction in `examples/qlib-quant/.state/history/hidden-oos-2026-07-30.md`;
  raw records in `hidden-metrics-2026-07-30.json`
- **A section on what the loop runs on your machine.** `run.py loop` starts the
  agent with `bypassPermissions` / `--dangerously-skip-permissions`, which the
  README had never said. The `PreToolUse` blocklist is a guard against an
  agent's accident, not a boundary against an adversarial one, and the README now
  shows measured bypasses of its own list rather than implying it holds

### Removed
- **The `init.sh` hook.** The orchestrator executed `<project>/init.sh` before
  every work session — a file inside the directory the agent writes to, outside
  the scoring fingerprint, documented nowhere and used by no example. A project
  whose thesis is that the orchestrator must not be controllable by the agent
  cannot ship a path for the agent to hand it arbitrary code

### Fixed
- **`--max-budget` could be exceeded by a retry.** The cap was checked before the
  retry, and the retry's cost was added after. A retry is another paid call, so
  it now passes the same gate both before and after
- **A stale claim in CLAUDE.md.** Rule 6 said state was "validated before write,
  backed up before overwrite". The agent writes state directly; the engine reads
  it back afterwards and reports what is malformed, and `safe_write_state` is a
  library entry point the engine loop never calls. The rule now says that

## [7.0.1] — 2026-07-30

### Fixed
- **`metric_pattern` ignored the project and the sealed file.** The commands
  resolved through `.verify` and `--sealed-verify`; the label they print did not,
  so a project could override `verify_command` but not the pattern used to read
  its output — and silently got no metric. It now follows the same precedence
- **A pattern that matches nothing is now reported.** When `metric_pattern` is
  set and the output does contain `[Metric]` lines but none match, the run warns
  instead of recording no metric in silence. Copying a mode without changing its
  label was otherwise a quiet failure. The parser still never guesses: falling
  back to a different `[Metric]` line is the defect that once made a losing
  Sharpe read as a positive return

### Changed
- The architecture diagram's caption now states the limit of the crossed-out
  arrow: evaloop never carries the held-out metric back and seals the scoring
  definition, but it cannot make the held-out data unreadable. That is
  filesystem permissions or a sandbox
- GitHub topics replaced. `agentos` was a leftover of the old name and
  `autonomous-coding` named the case the README explicitly sends elsewhere

## [7.0.0] — 2026-07-30

Renamed to **evaloop**, and cut to one thing.

The project shipped three modes and defended one of them. Held-out metrics,
sealed scoring and integrity checks only ever applied to the hypothesis loop;
engineer mode's criterion was a test suite the agent should not be editing
anyway, and auditor mode's was coverage, which nobody games. Carrying all three
made the project look general and be shallow. What remains is
**evaluation-driven autonomous development**: a loop whose acceptance criterion
is a metric, and the machinery that keeps that metric meaningful while an agent
optimises against it.

### Removed
- **`experiments/run_validation.py`.** It printed "the Loop Engineering approach
  is VALIDATED" and did not establish that: two of its three hypotheses ran
  against hardcoded scripts whose metric trajectories were written into the file,
  so convergence was an input rather than a finding, and the third compared two
  hand-written strategies at 7/12 seeds — indistinguishable from a coin — against
  an arbitrary 55% threshold. What it genuinely checked is covered by the test
  suite and by CI. Removed rather than kept with a corrected verdict
- **Engineer and auditor modes**, with `examples/todo-app` and
  `examples/audit-demo`. `--mode` now defaults to `researcher`
- `assets/auto-dev-agentos-architecture.png`, replaced by a diagram of what the
  project actually does

### Changed
- **Renamed `auto-dev-agentos` → `evaloop`** throughout. The old name promised
  spec-to-code, which is the case this project is now explicit about *not*
  serving
- **A mode declares its own state schema.** `validate_state(data, conf)` reads
  `state_array` and `valid_statuses` from `mode.conf` instead of looking the mode
  up in a table keyed by name. A mode you write yourself is validated too;
  previously it silently passed. `safe_write_state` takes a conf for the same
  reason. **Breaking**: both signatures changed
- README rebuilt around the single loop: a phase table replaces the mode
  comparison, and the architecture section explains the one boundary that matters
- The three methodology essays moved to `docs/archive/` with a header saying what
  they describe. Their arguments still hold; their inventory of modes does not
- `docs/design-rationale.md` explains why the other two modes were cut
- `examples/tamper-demo` rebuilt on the shipped loop

### Added
- **`examples/qlib-quant/PREREQUISITES.md`.** That example needs pyqlib,
  LightGBM and ~800 MB of CSI300 data, none of which ship here — a fresh clone
  could only fail at it, with nothing explaining why. Also records the
  pyOpenSSL/cryptography conflict that breaks it on some environments
- **`assets/evaloop-architecture.png`**: the orchestrator outside the project,
  the sealed config and held-out data reaching only the orchestrator, and the
  path from held-out data into the project drawn as blocked
- `test_user_defined_mode_drives_the_loop` — an unfamiliar mode, with a different
  entry file, state file, array and status vocabulary, driven end to end with no
  code change. The mode directory is an extension point, and this keeps it one
- 81 tests

## [6.3.0] — 2026-07-30

Names what this actually is. The project was described as a general autonomous
development engine, then as a verification harness, while the machinery that
distinguishes it — held-out metrics, sealed scoring, integrity checks — served
exactly one of its three modes. The positioning now matches the code:
**evaluation-driven autonomous development**, for loops whose acceptance
criterion is a metric rather than a test suite.

The argument, briefly: a loop runs unattended only for as long as its metric
survives its own optimiser. Where the criterion is a test suite the agent should
not edit, a coding agent with a test hook is the better tool, and the README now
says so rather than competing for that use.

### Fixed
- **Engineer mode verified successfully on projects with no tests.** The command
  ended in `|| echo "[Metric] Tests: 0"`, which exits 0 — so absent evidence read
  as passing evidence, in the mode whose whole criterion is that tests pass. It
  now selects a runner from what the project contains and lets its exit code
  stand: green suite passes, red suite fails, no suite fails
- The README's `--simulate` quick-start command pointed at `examples/todo-app`,
  which ships no `sim_script.json`, so it had never worked

### Added
- **`examples/tamper-demo`**: the integrity layer shown in two replayed sessions,
  no LLM calls and no cost. Session two marks its task done and rewrites
  `score.py` to report 99.0; the harness reports that metric as `TAMPERED`
  rather than as a result. Self-resetting apart from task state, so it replays
  without git. CI runs this exact demo instead of a private copy of it
- 3 regression tests for engineer verification (80 total)

### Changed
- README rewritten around the metric case: who this is *not* for, first; the
  qlib sweep in this repository as the worked example of the failure it prevents;
  researcher mode leading the mode table, with engineer and auditor scoped
  honestly beneath it
- `run_verification` documented as an evaluator for external search loops
  (AlphaEvolve, OpenEvolve, ShinkaEvolve), which state an unhackable evaluator as
  a prerequisite and leave building it to the user
- `verify` prints whether scoring came from a sealed file or an agent-writable
  one, which `loop` already did
- Every command in the README Quick Start executed before commit

## [6.2.0] — 2026-07-30

Makes the harness's one distinctive claim enforceable. Everything under the
project directory is writable by the agent — `.verify` and the scripts it names
included — so "the orchestrator controls verification" was true only while the
agent chose not to interfere.

### Added
- **`--sealed-verify FILE`**: read the verification config from outside the
  project. It outranks the project's `.verify`, so an agent that rewrites
  `.verify` changes nothing. A sealed path resolving inside the project is
  rejected, since that would defeat the point
- **Scoring fingerprints**: `scoring_fingerprint()` hashes `.verify` and every
  in-project file the verification commands invoke. The engine fingerprints
  before each session and re-checks after; a change is reported as `TAMPERED`
  and the metric is recorded untrusted rather than as a result
- **Hidden-metric leak detection**: `hidden_leak_signals()` scans a session
  transcript for the hidden invocation and for the hidden metric's own value.
  Regression-tested against the real transcripts in this repo — it flags
  `examples/goal-vs-loop/logs/session_4.log` and leaves `session_2.log` alone
- **Provenance in `hidden_metrics.json`**: each record now carries `sealed`,
  plus `tampered` and `leaks` when they apply. A metric whose provenance is
  unknown is worse than no metric
- Simulated sessions accept `file_writes` and `transcript`, so agent
  misbehaviour the integrity checks exist to catch is reproducible without
  spending a real session
- **`verify_timeout`** (seconds, default 300) in `mode.conf`, `.verify`, or the
  sealed file. The qlib example takes 6m41s to score and was being killed at
  300s; a timeout now reports how long it waited, and never yields a metric
- 15 integrity and timeout tests (77 total)
- CI enforces the size budget CLAUDE.md declares, and runs the simulated loop
  plus an end-to-end tamper-detection gate. A stated constraint nothing checks
  is the same class of problem as a documented protection nothing wires in
- **How This Compares** in the README and a Loop-2 comparison in the design
  rationale: eval frameworks, agent loop harnesses, evolutionary search — what
  each is better at, and when not to use this

### Changed
- **State validation is now wired into the engine.** `validate_state` existed,
  was tested, and was called by nothing outside the test suite, while the README
  listed it as an active protection. The engine now reads state back after each
  session and reports malformed state
- **The validator accepts what real runs write**: `round` identifies an item as
  well as `id`, `decision` carries status as well as `status` (including
  `accepted(best)`), and `baseline`/`kept` are valid outcomes. Checked against
  the archived journals — the previous schema rejected
  `journal-rounds-0-10.json`, produced by an actual 12-session run
- `hidden_metrics.json` is written atomically, matching the state-write rule
- Size budgets raised to 620/460 lines to fit the integrity layer
- `examples/qlib-quant/run_qlib_backtest.py` no longer prints
  `[Metric] Sharpe Ratio: 0.0000` when the run crashes. A fabricated zero was
  entering `hidden_metrics.json` as though it were a measurement

## [6.1.0] — 2026-07-30

### Fixed
- **`parse_metric` misread negative metrics.** `[^:]+` spanned newlines and the
  number pattern had no sign, so `[Metric] Sharpe Ratio: -0.8363` did not match
  its own line and the search fell through to the *next* `[Metric]` line —
  returning `0.5550` (the annualized return) as the Sharpe. A losing run was
  reported to the loop as a gain. Signs and scientific notation now parse, and
  the label may no longer span lines
- **`get_phase` crashed on a metric written as a JSON string.** `"1.89" >= 1.5`
  raises `TypeError`, killing the engine mid-loop. Metrics are coerced via the
  new `as_number()`; an unparseable value is treated as no progress, not as
  target-reached
- **`metric_pattern` was dead config.** Declared in `modes/researcher/mode.conf`
  and in the v4.1 changelog, referenced by no code. It now flows through
  `run_verification` → `run_verify_command` → `parse_metric`, selecting one
  labelled metric when a command emits several
- **A stale project `CLAUDE.md` was never refreshed.** The engine wrote it only
  when absent, so an existing project kept receiving the mode instructions it
  was first created with — including, until this release, the instruction to
  append learnings to a gitignored file. The template is now re-copied when it
  differs
- **The run summary reported one more session than it ran.** The loop counter is
  incremented before the exit check; the summary now counts sessions executed

### Added
- 8 regression tests covering the metric and phase defects above (62 total)
- **Tracked empirical record**: session transcripts (`examples/*/logs/`), archived
  run records (`examples/*/.state/history/`), and a distilled MLflow archive are
  now version-controlled. They were previously ignored, so a clone of this repo
  contained no evidence that any mode had ever been run against a live model.
- `examples/goal-vs-loop/session-history.bundle` — the nested git repo produced by
  the 4-session run, as a clonable bundle
- `examples/*/.state/learnings.md` — accumulated cross-session knowledge, tracked.
  Previously appended to the engine-copied `CLAUDE.md`, which is gitignored, so
  every learning was lost on the next run
- **Empirical Record** section in README: what was measured, against which files,
  and what those numbers do not show

### Changed
- Recovered the 11-round qlib hyperparameter journal and progress log that the
  v6.0 baseline reset discarded, into `examples/qlib-quant/.state/history/`
- All three mode templates and their prompts now read and write
  `.state/learnings.md` instead of the `## Learnings` section of `CLAUDE.md`
- Scoped down the hidden-OOS claim in the README. The orchestrator not surfacing
  the hidden metric is not the same as the agent being unable to compute it —
  `examples/goal-vs-loop/logs/session_4.log` shows a session doing exactly that
- `docs/dual-loop-architecture.md` now includes the v4.0 architecture diagram

## [6.0.0] — 2026-06-22

### Changed
- **Repositioned as verification harness**: Project identity shifted from "loop engine" to "verification harness" (Loop 2 in LangChain's stack). The core value is structurally separate evaluation, not session orchestration.
- **Subcommand CLI**: `verify`, `loop`, `status`, `list-modes` subcommands replace flat flags. Full backward compatibility preserved (`python run.py <project>` still works as `loop`).
- **Public verification API**: `core.run_verification()` and `core.resolve_verify_cmd()` are now the primary entry points — usable standalone without the session loop.
- **Dispatch refactor**: Extracted `_dispatch()` helper, removing 4x repeated simulate/SDK/CLI dispatch blocks in engine().

### Removed
- `_resolve_verify_cmd()` and `run_post_session_verification()` from run.py (moved to core.py as public API)
- `--dry-run` flag (replaced by `status` subcommand, backward compat redirects)

### Added
- 7 new integration tests (Group 6: Standalone Verification) — total 54 tests
- README rewritten with Loop 2 positioning, industry context, three usage modes

## [5.0.0] — 2026-06-22

### Changed
- **Single engine**: Removed `run.sh`. `run.py` is now the sole engine, with CLI fallback mode (no SDK needed)
- **Robust progress tracking**: `count_by_status` now checks both `status` and `decision` fields, handling LLM state format variations
- **Session retry**: Failed/timeout sessions get one automatic retry instead of wasting the session slot
- **Smarter circuit breaker**: Error/timeout sessions no longer count toward the stuck detection threshold
- **Clean examples**: Reset qlib-quant to baseline state, cleaned goal-vs-loop

### Removed
- `run.sh` (393 lines) — all functionality subsumed by `run.py` CLI fallback mode
- `jq` dependency — no longer needed

## [4.1.0] — 2026-06-21

### Added
- **Independent verification layer**: orchestrator runs `verify_command` after each work session, independently of LLM self-report
- **Hidden out-of-sample validation**: `hidden_verify_command` in mode.conf runs on data invisible to the LLM, writes to `.state/hidden_metrics.json`
- **State schema validation**: `validate_state()` rejects corrupt/invalid state with clear error messages
- **Atomic state writes**: `safe_write_state()` validates before write, creates automatic backups, uses atomic `os.replace`
- **Budget cap**: `--max-budget` (default $10) stops the loop when cost limit is exceeded
- **Simulation mode**: `--simulate` runs the full orchestration loop using `.state/sim_script.json` — zero LLM calls, deterministic, testable
- **Train/test split**: `run_backtest.py --split train|test` with independent random seed for genuinely out-of-sample data
- **Integration tests**: 30 tests proving autonomous loop orchestration (phase transitions, circuit breaker, state validation, independent verification, full loop simulations)
- **`metric_pattern`** key in researcher mode.conf

### Changed
- `run.py` version bumped to 4.1, SDK import now optional (not required for `--simulate` or `--dry-run`)
- `core.py` expanded from 81 to 180 lines with verification and validation functions
- CI now runs integration tests alongside unit tests, with numpy/pandas for backtest verification
- README repositioned with Loop Engineering framing and verification documentation

## [4.0.0] — 2026-03-30

### Added
- **SDK engine** (`run.py`): Python alternative using Claude Agent SDK
  - Nested dual-loop architecture: outer OODA (strategic) + inner SDK (tactical)
  - `disallowed_tools` enforcement for Orient phase safety
  - `orient_edit_guard` hook restricts strategist edits to `.state/` only
  - Session cost tracking (API key mode)
  - Pure Python jq-query evaluation (no `jq` dependency)
- **Strategist prompts** for all three modes (OODA Orient phase)
  - Anti-oscillation: checks previous Orient decisions before making new ones
  - Explicit distinction from Analyst/Reviewer (prescriptive vs descriptive)
- **`--dry-run` flag** for both engines — see what would run without invoking Claude
- **Unit tests** (`tests/test_run.py`) for pure functions
- **CI** (GitHub Actions): shellcheck, Python syntax, unit tests, smoke tests
- **CONTRIBUTING.md** and issue templates
- **Methodology article**: [Dual-Loop Architecture](docs/dual-loop-architecture.md)

### Changed
- `mode.conf` now supports `phase_orient` key (backward-compatible — ignored by run.sh)
- README restructured: dual architecture diagram, SDK quick-start, updated design principles

## [3.0.0] — 2026-03-16

### Added
- **Auditor mode**: systematic codebase audit (standards → scan → findings → report)
- **Verification schema**: `acceptance_criteria` and `verify_command` fields in tasks
- **TDD workflow** in developer prompt
- **Quant-lab demo**: complete researcher mode example with 6 experiments
- **Methodology article**: [Stateless Agent Architecture](docs/stateless-agent-architecture.md)

## [2.0.0] — 2026-03-03

### Added
- **Mode system**: engineer and researcher modes with distinct workflows
- `modes/` directory structure with mode.conf, CLAUDE.md, and prompts per mode
- Researcher mode: hypothesis → experiment → evaluate → learn cycle

## [1.0.0] — 2026-02-18

### Added
- Initial release: universal engine (`run.sh`)
- Single-loop orchestration with circuit breaker
- File-based state (tasks.json, progress.md)
- Mandatory verification before commit
