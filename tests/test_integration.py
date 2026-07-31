"""
Integration tests for evaloop loop orchestration.

Proves: the system autonomously decides what instruction to give the LLM next,
based solely on state files — no human in the loop.

Run: python tests/test_integration.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core import (
    count_by_status, fingerprint_diff, get_phase, hidden_leak_signals,
    load_conf, parse_metric, progress_count, resolve_verify_cmd,
    run_verification, run_verify_command, safe_read_state, safe_write_state,
    scoring_fingerprint, validate_state, divergence_report,
    hidden_metrics_path,
)

SCRIPT_DIR = Path(__file__).parent.parent


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════

def make_mode_dir(tmp, mode="metric"):
    """A synthetic mode directory.

    evaloop ships one mode, but a mode is just a directory, so these fixtures
    keep two differently-shaped ones to prove the engine reads state generically
    rather than knowing the shipped names. `metric` mirrors the shipped loop;
    `checklist` is a pass/fail shape a user might define.
    """
    mode_dir = Path(tmp) / "modes" / mode
    mode_dir.mkdir(parents=True)
    confs = {
        "metric": (
            "entry_file=hypothesis.md\nstate_file=journal.json\n"
            "state_array=experiments\n"
            "valid_statuses=pending,planned,running,accepted,rejected,error,baseline,kept\n"
            'pending_query=[.experiments[] | select(.status == "pending" or .status == "planned" or .status == "running")] | length\n'
            'progress_query=[.experiments[] | select(.status == "accepted" or .status == "rejected" or .status == "error")] | length\n'
            "phase_init=theorizer\nphase_work=executor\nphase_review=analyst\n"
        ),
        # Deliberately unlike either shipped shape: proves the engine reads a
        # mode's declarations rather than recognising names it already knows.
        "custom": (
            "entry_file=standards.md\nstate_file=findings.json\n"
            "state_array=findings\nvalid_statuses=pending,in_progress,verified,dismissed\n"
            'pending_query=[.findings[] | select(.status == "pending" or .status == "in_progress")] | length\n'
            'progress_query=[.findings[] | select(.status == "verified" or .status == "dismissed")] | length\n'
            "phase_init=initializer\nphase_work=developer\nphase_review=reviewer\n"
        ),
        "checklist": (
            "entry_file=spec.md\nstate_file=tasks.json\n"
            "state_array=tasks\nvalid_statuses=pending,in_progress,done,blocked\n"
            'pending_query=[.tasks[] | select(.status == "pending" or .status == "in_progress")] | length\n'
            'progress_query=[.tasks[] | select(.status == "done")] | length\n'
            "phase_init=initializer\nphase_work=developer\nphase_review=reviewer\n"
        ),
    }
    (mode_dir / "mode.conf").write_text(confs.get(mode, confs["metric"]))
    prompts_dir = mode_dir / "prompts"
    prompts_dir.mkdir()
    for name in ["initializer", "developer", "reviewer", "theorizer", "executor",
                 "analyst", "strategist"]:
        (prompts_dir / f"{name}.md").write_text(f"# {name} prompt stub\n")
    return mode_dir


def write_state(tmp, filename, data):
    state_dir = Path(tmp) / ".state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / filename).write_text(json.dumps(data, indent=2))
    return state_dir / filename


# ═══════════════════════════════════════════
# Group 1: Phase Transitions
# Proves: the loop autonomously decides next phase
# ═══════════════════════════════════════════

def test_phase_init_when_no_state():
    """No state file -> init phase. Loop will dispatch initializer."""
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / ".state" / "tasks.json"
        conf = load_conf(make_mode_dir(tmp, "checklist"))
        assert get_phase(state_path, conf) == "init"


def test_phase_work_when_pending():
    """Pending tasks exist -> work phase. Loop will dispatch developer."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "checklist"))
        state_path = write_state(tmp, "tasks.json", {
            "tasks": [
                {"id": "T1", "status": "done"},
                {"id": "T2", "status": "pending"},
                {"id": "T3", "status": "pending"},
            ]
        })
        assert get_phase(state_path, conf) == "work"


def test_phase_done_when_all_complete():
    """All tasks done -> done phase. Loop exits."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "checklist"))
        state_path = write_state(tmp, "tasks.json", {
            "tasks": [
                {"id": "T1", "status": "done"},
                {"id": "T2", "status": "done"},
            ]
        })
        assert get_phase(state_path, conf) == "done"


def test_metric_target_met():
    """Best metric >= target -> done. Loop exits."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "metric"))
        state_path = write_state(tmp, "journal.json", {
            "experiments": [],
            "best_metric": 1.89,
            "target_metric": 1.5,
        })
        assert get_phase(state_path, conf) == "done"


def test_metric_loop_cycles_back():
    """Target not met, no pending experiments -> init. Loop dispatches theorizer."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "metric"))
        state_path = write_state(tmp, "journal.json", {
            "experiments": [
                {"id": "EXP-001", "status": "rejected"},
            ],
            "best_metric": 0.84,
            "target_metric": 1.5,
        })
        assert get_phase(state_path, conf) == "init"


# ═══════════════════════════════════════════
# Group 2: Circuit Breaker
# Proves: the loop has autonomous safety controls
# ═══════════════════════════════════════════

def test_stuck_detection():
    """3 consecutive sessions with no progress -> should trigger stuck."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "checklist"))
        state_path = write_state(tmp, "tasks.json", {
            "tasks": [{"id": "T1", "status": "pending"}]
        })
        no_progress = 0
        no_progress_max = 3
        for _ in range(5):
            prev = progress_count(state_path, conf)
            # Simulate session that makes no progress (state unchanged)
            curr = progress_count(state_path, conf)
            if curr <= prev:
                no_progress += 1
            else:
                no_progress = 0
            if no_progress >= no_progress_max:
                break
        assert no_progress >= no_progress_max, f"Expected stuck at {no_progress_max}, got {no_progress}"


def test_progress_resets_stuck_counter():
    """Making progress after stuck sessions resets the counter."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "checklist"))
        state_path = write_state(tmp, "tasks.json", {
            "tasks": [
                {"id": "T1", "status": "pending"},
                {"id": "T2", "status": "pending"},
            ]
        })
        no_progress = 0
        # 2 stuck sessions
        for _ in range(2):
            prev = progress_count(state_path, conf)
            curr = progress_count(state_path, conf)
            if curr <= prev:
                no_progress += 1
        assert no_progress == 2
        # Now make progress
        data = json.loads(state_path.read_text())
        data["tasks"][0]["status"] = "done"
        state_path.write_text(json.dumps(data))
        prev = 0
        curr = progress_count(state_path, conf)
        if curr > prev:
            no_progress = 0
        assert no_progress == 0, "Progress should reset stuck counter"


# ═══════════════════════════════════════════
# Group 3: State Validation
# Proves: corruption is caught before damage
# ═══════════════════════════════════════════

CHECKLIST = {"state_array": "tasks",
             "valid_statuses": "pending,in_progress,done,blocked"}
METRIC = {"state_array": "experiments",
          "valid_statuses": "pending,planned,running,accepted,rejected,error,baseline,kept"}


def test_valid_state_against_a_declared_schema():
    data = {"tasks": [{"id": "T1", "status": "pending"}, {"id": "T2", "status": "done"}]}
    valid, errors = validate_state(data, CHECKLIST)
    assert valid, f"Expected valid, got errors: {errors}"


def test_invalid_missing_array():
    valid, errors = validate_state({}, CHECKLIST)
    assert not valid
    assert any("tasks" in e for e in errors)


def test_invalid_status():
    data = {"tasks": [{"id": "T1", "status": "banana"}]}
    valid, errors = validate_state(data, CHECKLIST)
    assert not valid
    assert any("banana" in e for e in errors)


def test_valid_metric_state():
    data = {"experiments": [{"id": "EXP-1", "status": "pending"}]}
    valid, errors = validate_state(data, METRIC)
    assert valid, f"Errors: {errors}"


def test_missing_id():
    data = {"tasks": [{"status": "pending"}]}
    valid, errors = validate_state(data, CHECKLIST)
    assert not valid
    assert any("id" in e for e in errors)


def test_mode_declaring_no_schema_is_not_validated():
    """Silence here is a choice the mode makes, visible in its mode.conf."""
    valid, errors = validate_state({"anything": "goes"}, {})
    assert valid and errors == []


def test_shipped_mode_declares_a_schema():
    """The one mode evaloop ships must not opt out of its own validation."""
    conf = load_conf(SCRIPT_DIR / "modes" / "experiment")
    assert conf.get("state_array") and conf.get("valid_statuses")
    ok, _ = validate_state({"experiments": [{"id": "E", "status": "accepted"}]}, conf)
    assert ok
    bad, errors = validate_state({"experiments": [{"id": "E", "status": "banana"}]}, conf)
    assert not bad and errors


def test_archived_journals_still_validate():
    """Real runs wrote `round`/`decision`. A validator stricter than the reader
    would reject state the loop is happy to act on."""
    conf = load_conf(SCRIPT_DIR / "modes" / "experiment")
    for rel in ["examples/qlib-quant/.state/history/journal-rounds-0-10.json",
                "examples/goal-vs-loop/.state/history/journal-exp001-002.json"]:
        data = json.loads((SCRIPT_DIR / rel).read_text())
        ok, errors = validate_state(data, conf)
        assert ok, f"{rel}: {errors}"


def test_safe_read_corrupt_json():
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.json"
        bad.write_text("not valid json{{{")
        data, err = safe_read_state(bad)
        assert data is None
        assert "invalid JSON" in err
        # Backup should exist
        backups = list(Path(tmp).glob("backup_*"))
        assert len(backups) == 1


def test_safe_write_validates():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        # Invalid data should be rejected
        ok, err = safe_write_state(path, {"no_tasks": []}, CHECKLIST)
        assert not ok
        assert not path.exists()


def test_safe_write_atomic():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        data = {"tasks": [{"id": "T1", "status": "pending"}]}
        ok, err = safe_write_state(path, data, CHECKLIST)
        assert ok, f"Write failed: {err}"
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["tasks"][0]["id"] == "T1"


# ═══════════════════════════════════════════
# Group 4: Independent Verification
# Proves: engine doesn't trust LLM's self-assessment
# ═══════════════════════════════════════════

def test_parse_metric_found():
    output = "Running backtest...\n[Metric] Sharpe Ratio: 1.8900\nDone."
    assert parse_metric(output) == 1.89


def test_parse_metric_integer():
    assert parse_metric("[Metric] Tests: 42") == 42.0


def test_parse_metric_missing():
    assert parse_metric("No metric here\nJust text") is None


def test_parse_metric_negative():
    """A losing run reports a negative metric. Reading it as positive, or
    skipping to the next [Metric] line, would hide a regression from the loop."""
    output = ("[Metric] Sharpe Ratio: -0.8363\n"
              "[Metric] Annualized Return: 0.5550\n"
              "[Metric] IC Mean: 0.0285")
    assert parse_metric(output) == -0.8363


def test_parse_metric_scientific_notation():
    assert parse_metric("[Metric] IC: 1e-3") == 0.001
    assert parse_metric("[Metric] IC: -2.5E+2") == -250.0


def test_parse_metric_leading_decimal_point():
    assert parse_metric("[Metric] Rate: .75") == 0.75


def test_parse_metric_pattern_selects_line():
    """metric_pattern picks one label out of several."""
    output = ("[Metric] Sharpe Ratio: 1.8900\n"
              "[Metric] IC Mean: 0.0285")
    assert parse_metric(output, "[Metric] IC Mean:") == 0.0285
    assert parse_metric(output, "[Metric] Sharpe Ratio:") == 1.89
    assert parse_metric(output, "[Metric] Absent:") is None


def test_verify_command_honours_metric_pattern():
    with tempfile.TemporaryDirectory() as tmp:
        cmd = "printf '[Metric] Sharpe Ratio: 1.5\\n[Metric] IC Mean: 0.03\\n'"
        assert run_verify_command(tmp, cmd)["metric"] == 1.5
        assert run_verify_command(tmp, cmd, metric_pattern="[Metric] IC Mean:")["metric"] == 0.03


def test_run_verification_passes_metric_pattern_from_conf():
    """mode.conf's metric_pattern must reach parse_metric, not sit unused."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = {
            "verify_command": "printf '[Metric] Sharpe: 1.5\\n[Metric] IC: 0.03\\n'",
            "metric_pattern": "[Metric] IC:",
        }
        result = run_verification(tmp, conf, verbose=False)
        assert result["verify"]["metric"] == 0.03


def test_phase_metric_written_as_string():
    """LLMs write numbers as JSON strings. Phase detection must not crash."""
    with tempfile.TemporaryDirectory() as tmp:
        mode_dir = make_mode_dir(tmp, "metric")
        conf = load_conf(mode_dir)
        state = Path(tmp) / "journal.json"
        state.write_text(json.dumps(
            {"experiments": [], "best_metric": "1.89", "target_metric": "1.5"}))
        assert get_phase(state, conf) == "done"
        state.write_text(json.dumps(
            {"experiments": [], "best_metric": "0.5", "target_metric": "1.5"}))
        assert get_phase(state, conf) == "init"


def test_phase_unparseable_metric_is_not_progress():
    """A metric that is not a number must not be read as target reached."""
    with tempfile.TemporaryDirectory() as tmp:
        mode_dir = make_mode_dir(tmp, "metric")
        conf = load_conf(mode_dir)
        state = Path(tmp) / "journal.json"
        state.write_text(json.dumps(
            {"experiments": [], "best_metric": "n/a", "target_metric": 1.5}))
        assert get_phase(state, conf) == "init"


def test_verify_command_success():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_verify_command(tmp, "echo '[Metric] Score: 95.5'")
        assert result["success"]
        assert result["exit_code"] == 0
        assert result["metric"] == 95.5


def test_verify_command_failure():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_verify_command(tmp, "exit 1")
        assert not result["success"]
        assert result["exit_code"] == 1


def test_verify_command_timeout():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_verify_command(tmp, "sleep 10", timeout=1)
        assert not result["success"]
        assert result["stderr"].startswith("timeout")
        assert result["metric"] is None, "a timeout is a failure, not a metric"


def test_hidden_verify_not_in_state():
    """Hidden verification writes to separate file, NOT to LLM-visible state."""
    with tempfile.TemporaryDirectory() as tmp:
        state_dir = Path(tmp) / ".state"
        state_dir.mkdir()
        # Simulate hidden verify: write to hidden_metrics.json
        hidden_path = state_dir / "hidden_metrics.json"
        result = run_verify_command(tmp, "echo '[Metric] Sharpe Ratio: 1.45'")
        hidden_entry = {"session": 1, "metric": result["metric"]}
        hidden_path.write_text(json.dumps([hidden_entry]))
        # The LLM-visible state file should NOT contain this
        state_path = state_dir / "journal.json"
        state_path.write_text(json.dumps({
            "experiments": [{"id": "EXP-1", "status": "accepted"}],
            "best_metric": 1.89,
        }))
        state_data = json.loads(state_path.read_text())
        assert "hidden" not in json.dumps(state_data).lower()
        # But hidden_metrics.json has the data
        hidden_data = json.loads(hidden_path.read_text())
        assert hidden_data[0]["metric"] == 1.45


# ═══════════════════════════════════════════
# Group 5: Full Loop Simulation
# Proves: end-to-end autonomous orchestration
# ═══════════════════════════════════════════

def test_engineer_full_loop():
    """Simulate complete engineer loop: init -> work x3 -> done.
    The loop autonomously decides which phase and prompt to use at each step."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "checklist"))
        state_file = conf.get("state_file", "tasks.json")
        state_path = Path(tmp) / ".state" / state_file
        Path(tmp, ".state").mkdir(exist_ok=True)

        decisions = []

        # --- Session 1: no state -> init -> initializer creates tasks ---
        phase = get_phase(state_path, conf)
        decisions.append(("session_1", phase, conf.get("phase_init")))
        assert phase == "init", f"Expected init, got {phase}"
        # Simulate initializer: create tasks
        write_state(tmp, state_file, {
            "tasks": [
                {"id": "T1", "status": "pending"},
                {"id": "T2", "status": "pending"},
                {"id": "T3", "status": "pending"},
            ]
        })

        # --- Sessions 2-4: pending tasks -> work -> developer ---
        for i, task_id in enumerate(["T1", "T2", "T3"], 2):
            phase = get_phase(state_path, conf)
            decisions.append((f"session_{i}", phase, conf.get("phase_work")))
            assert phase == "work", f"Session {i}: expected work, got {phase}"
            # Simulate developer: complete one task
            data = json.loads(state_path.read_text())
            for t in data["tasks"]:
                if t["id"] == task_id:
                    t["status"] = "done"
            state_path.write_text(json.dumps(data))

        # --- Session 5: all done -> done ---
        phase = get_phase(state_path, conf)
        decisions.append(("session_5", phase, None))
        assert phase == "done", f"Expected done, got {phase}"

        # Verify: 5 autonomous decisions, no human input
        assert len(decisions) == 5
        assert decisions[0][1] == "init"
        assert decisions[1][1] == "work"
        assert decisions[4][1] == "done"


def test_metric_loop_full_cycle():
    """Simulate the metric loop with failure-driven learning:
    init -> work(fail) -> init(cycle back) -> work(succeed) -> done."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "metric"))
        state_file = conf.get("state_file", "journal.json")
        state_path = Path(tmp) / ".state" / state_file
        Path(tmp, ".state").mkdir(exist_ok=True)

        decisions = []

        # Session 1: no state -> init -> theorizer designs experiment
        phase = get_phase(state_path, conf)
        decisions.append(("session_1", phase))
        assert phase == "init"
        write_state(tmp, state_file, {
            "experiments": [{"id": "EXP-001", "status": "pending"}],
            "best_metric": 0.84,
            "target_metric": 1.5,
        })

        # Session 2: pending experiment -> work -> executor runs it -> rejected
        phase = get_phase(state_path, conf)
        decisions.append(("session_2", phase))
        assert phase == "work"
        data = json.loads(state_path.read_text())
        data["experiments"][0]["status"] = "rejected"
        state_path.write_text(json.dumps(data))

        # Session 3: no pending, target not met -> init -> theorizer designs new exp
        phase = get_phase(state_path, conf)
        decisions.append(("session_3", phase))
        assert phase == "init", f"Expected init (cycle back), got {phase}"
        data = json.loads(state_path.read_text())
        data["experiments"].append({"id": "EXP-002", "status": "pending"})
        state_path.write_text(json.dumps(data))

        # Session 4: pending experiment -> work -> executor runs it -> accepted!
        phase = get_phase(state_path, conf)
        decisions.append(("session_4", phase))
        assert phase == "work"
        data = json.loads(state_path.read_text())
        data["experiments"][1]["status"] = "accepted"
        data["best_metric"] = 1.89
        state_path.write_text(json.dumps(data))

        # Session 5: target met -> done
        phase = get_phase(state_path, conf)
        decisions.append(("session_5", phase))
        assert phase == "done"

        # The loop made 5 autonomous decisions including a cycle-back
        assert [d[1] for d in decisions] == ["init", "work", "init", "work", "done"]


def test_user_defined_mode_drives_the_loop():
    """A mode is a directory. Nothing in the engine knows the shipped names.

    evaloop ships one mode; this drives an unfamiliar one — different entry
    file, state file, array, and status vocabulary — end to end with no code
    change, which is what makes the mode directory a real extension point
    rather than a leftover of the three-mode era.
    """
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "custom"))
        state_file = conf.get("state_file", "findings.json")
        state_path = Path(tmp) / ".state" / state_file
        Path(tmp, ".state").mkdir(exist_ok=True)

        # Session 1: init -> scanner creates findings
        phase = get_phase(state_path, conf)
        assert phase == "init"
        write_state(tmp, state_file, {
            "findings": [
                {"id": "F1", "status": "pending"},
                {"id": "F2", "status": "pending"},
            ]
        })

        # Session 2: work -> auditor verifies F1
        phase = get_phase(state_path, conf)
        assert phase == "work"
        data = json.loads(state_path.read_text())
        data["findings"][0]["status"] = "verified"
        state_path.write_text(json.dumps(data))

        # Session 3: work -> auditor dismisses F2
        phase = get_phase(state_path, conf)
        assert phase == "work"
        data = json.loads(state_path.read_text())
        data["findings"][1]["status"] = "dismissed"
        state_path.write_text(json.dumps(data))

        # Session 4: all findings resolved -> done
        phase = get_phase(state_path, conf)
        assert phase == "done"


def test_loop_decides_next_prompt():
    """KEY TEST: Given a state, the engine selects the correct prompt file.
    This proves the system autonomously decides what instruction to give next."""
    with tempfile.TemporaryDirectory() as tmp:
        mode_dir = make_mode_dir(tmp, "checklist")
        conf = load_conf(mode_dir)
        state_file = conf.get("state_file", "tasks.json")
        state_path = Path(tmp) / ".state" / state_file
        Path(tmp, ".state").mkdir(exist_ok=True)

        def resolve_prompt(phase, conf, mode_dir):
            phase_keys = {"init": "phase_init", "work": "phase_work", "review": "phase_review"}
            prompt_name = conf.get(phase_keys.get(phase, ""), phase)
            return mode_dir / "prompts" / f"{prompt_name}.md"

        # State 1: no state -> init -> initializer.md
        phase = get_phase(state_path, conf)
        prompt = resolve_prompt(phase, conf, mode_dir)
        assert phase == "init"
        assert prompt.name == "initializer.md"

        # State 2: pending tasks -> work -> developer.md
        write_state(tmp, state_file, {
            "tasks": [{"id": "T1", "status": "pending"}]
        })
        phase = get_phase(state_path, conf)
        prompt = resolve_prompt(phase, conf, mode_dir)
        assert phase == "work"
        assert prompt.name == "developer.md"

        # State 3: all done -> done -> no prompt needed
        data = json.loads(state_path.read_text())
        data["tasks"][0]["status"] = "done"
        state_path.write_text(json.dumps(data))
        phase = get_phase(state_path, conf)
        assert phase == "done"


def test_loop_decides_metric_prompt():
    """Researcher mode: state determines theorizer vs executor selection."""
    with tempfile.TemporaryDirectory() as tmp:
        mode_dir = make_mode_dir(tmp, "metric")
        conf = load_conf(mode_dir)
        state_path = Path(tmp) / ".state" / "journal.json"
        Path(tmp, ".state").mkdir(exist_ok=True)

        # No state -> init -> theorizer
        phase = get_phase(state_path, conf)
        assert phase == "init"
        assert conf.get("phase_init") == "theorizer"

        # Pending experiment -> work -> executor
        write_state(tmp, "journal.json", {
            "experiments": [{"id": "EXP-1", "status": "pending"}],
            "best_metric": 0.5, "target_metric": 1.5,
        })
        phase = get_phase(state_path, conf)
        assert phase == "work"
        assert conf.get("phase_work") == "executor"

        # All rejected, target not met -> init -> back to theorizer
        data = json.loads(state_path.read_text())
        data["experiments"][0]["status"] = "rejected"
        state_path.write_text(json.dumps(data))
        phase = get_phase(state_path, conf)
        assert phase == "init"
        assert conf.get("phase_init") == "theorizer"


def test_quant_lab_backtest_splits():
    """Verify the actual quant-lab backtest works with train/test splits."""
    quant_dir = SCRIPT_DIR / "examples" / "quant-lab"
    if not (quant_dir / "run_backtest.py").exists():
        return  # skip if example not present

    python = sys.executable
    # All data
    r_all = run_verify_command(str(quant_dir), f"{python} run_backtest.py")
    assert r_all["success"], f"Backtest failed: {r_all['stderr']}"
    assert r_all["metric"] is not None
    assert r_all["metric"] > 1.0

    # Train split
    r_train = run_verify_command(str(quant_dir), f"{python} run_backtest.py --split train")
    assert r_train["success"]
    assert r_train["metric"] is not None

    # Test split (hidden from LLM)
    r_test = run_verify_command(str(quant_dir), f"{python} run_backtest.py --split test")
    assert r_test["success"]
    assert r_test["metric"] is not None

    # Train and test should give different metrics (different data)
    assert r_train["metric"] != r_test["metric"], \
        f"Train ({r_train['metric']}) and test ({r_test['metric']}) should differ"


def test_consistency_jq_vs_python():
    """Verify Python regex-based count matches what jq would produce.
    Uses the actual mode.conf queries from all three modes."""
    test_cases = [
        # (data, query, expected_count)
        (
            {"tasks": [{"status": "pending"}, {"status": "done"}, {"status": "in_progress"}]},
            '[.tasks[] | select(.status == "pending" or .status == "in_progress")] | length',
            2,
        ),
        (
            {"experiments": [{"status": "accepted"}, {"status": "rejected"}, {"status": "pending"}]},
            '[.experiments[] | select(.status == "pending" or .status == "planned" or .status == "running")] | length',
            1,
        ),
        (
            {"findings": [{"status": "verified"}, {"status": "pending"}, {"status": "dismissed"}]},
            '[.findings[] | select(.status == "verified" or .status == "dismissed")] | length',
            2,
        ),
    ]
    for data, query, expected in test_cases:
        result = count_by_status(data, query)
        assert result == expected, f"Query {query[:40]}... expected {expected}, got {result}"


# ═══════════════════════════════════════════
# Group 6: Standalone Verification
# ═══════════════════════════════════════════


def test_run_verification_standalone():
    """run_verification works without the engine — core value of Loop 2."""
    with tempfile.TemporaryDirectory() as tmp:
        python = sys.executable
        conf = {"verify_command": f"{python} -c \"print('[Metric] sharpe: 1.5'); exit(0)\""}
        result = run_verification(tmp, conf, session_label="standalone", verbose=False)
        assert result["verify"] is not None
        assert result["verify"]["success"] is True
        assert result["verify"]["metric"] == 1.5
        assert result["hidden"] is None


def test_run_verification_with_hidden():
    """Hidden verification writes metrics to .state/hidden_metrics.json."""
    with tempfile.TemporaryDirectory() as tmp:
        python = sys.executable
        Path(tmp, ".state").mkdir()
        conf = {
            "verify_command": f"{python} -c \"print('[Metric] acc: 0.95')\"",
            "hidden_verify_command": f"{python} -c \"print('[Metric] oos: 0.82')\"",
        }
        result = run_verification(tmp, conf, session_label="s1", verbose=False)
        assert result["verify"]["success"] is True
        assert result["verify"]["metric"] == 0.95
        assert result["hidden"]["success"] is True
        assert result["hidden"]["metric"] == 0.82
        metrics = json.loads((Path(tmp) / ".state" / "hidden_metrics.json").read_text())
        assert len(metrics) == 1
        assert metrics[0]["session"] == "s1"
        assert metrics[0]["metric"] == 0.82


def test_run_verification_no_commands():
    """Graceful when no verify commands configured."""
    with tempfile.TemporaryDirectory() as tmp:
        result = run_verification(tmp, {}, verbose=False)
        assert result["verify"] is None
        assert result["hidden"] is None


def test_resolve_verify_cmd_from_conf():
    """resolve_verify_cmd reads from mode.conf dict."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = {"verify_command": "pytest", "hidden_verify_command": "pytest --oos"}
        assert resolve_verify_cmd(Path(tmp), conf, "verify_command") == "pytest"
        assert resolve_verify_cmd(Path(tmp), conf, "hidden_verify_command") == "pytest --oos"
        assert resolve_verify_cmd(Path(tmp), conf, "nonexistent") == ""


def test_resolve_verify_cmd_override():
    """.verify file overrides mode.conf."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".verify").write_text(
            "verify_command = bash run_test.sh\nhidden_verify_command = bash oos.sh\n")
        conf = {"verify_command": "original"}
        assert resolve_verify_cmd(Path(tmp), conf, "verify_command") == "bash run_test.sh"
        assert resolve_verify_cmd(Path(tmp), conf, "hidden_verify_command") == "bash oos.sh"


def test_verify_exit_code_pass():
    """Verification passes -> exit code 0 from cmd_verify logic."""
    with tempfile.TemporaryDirectory() as tmp:
        python = sys.executable
        conf = {"verify_command": f"{python} -c \"print('ok')\""}
        result = run_verification(tmp, conf, verbose=False)
        assert result["verify"]["success"] is True


def test_verify_exit_code_fail():
    """Verification fails -> structured result shows failure."""
    with tempfile.TemporaryDirectory() as tmp:
        python = sys.executable
        conf = {"verify_command": f"{python} -c \"exit(1)\""}
        result = run_verification(tmp, conf, verbose=False)
        assert result["verify"]["success"] is False
        assert result["verify"]["exit_code"] == 1


# ═══════════════════════════════════════════
# Group 7: Scoring integrity
#
# The harness's one distinctive claim is that evaluation is separate from
# generation. These prove the separation is enforced, not merely intended.
# ═══════════════════════════════════════════

def _scored_project(tmp, verify_body='verify_command=python3 score.py\n'):
    project = Path(tmp) / "proj"
    (project / ".state").mkdir(parents=True)
    (project / "score.py").write_text('print("[Metric] Sharpe Ratio: 0.5000")\n')
    (project / ".verify").write_text(verify_body)
    return project


def test_fingerprint_covers_verify_file_and_its_scripts():
    with tempfile.TemporaryDirectory() as tmp:
        project = _scored_project(tmp)
        fp = scoring_fingerprint(project, {})
        assert ".verify" in fp
        assert "score.py" in fp


def test_fingerprint_detects_rewritten_scoring_script():
    """An agent that edits its own scorer must not go unnoticed."""
    with tempfile.TemporaryDirectory() as tmp:
        project = _scored_project(tmp)
        before = scoring_fingerprint(project, {})
        (project / "score.py").write_text('print("[Metric] Sharpe Ratio: 99.0")\n')
        assert fingerprint_diff(before, scoring_fingerprint(project, {})) == ["score.py"]


def test_fingerprint_stable_when_only_unrelated_files_change():
    with tempfile.TemporaryDirectory() as tmp:
        project = _scored_project(tmp)
        before = scoring_fingerprint(project, {})
        (project / "notes.md").write_text("scratch work\n")
        assert fingerprint_diff(before, scoring_fingerprint(project, {})) == []


def test_sealed_config_outranks_the_project_verify_file():
    """.verify sits inside the agent's reach; a sealed file does not."""
    with tempfile.TemporaryDirectory() as tmp:
        project = _scored_project(
            tmp, 'hidden_verify_command=echo "[Metric] X: 999.0"\n')
        sealed = Path(tmp) / "sealed.conf"
        sealed.write_text("hidden_verify_command=python3 score.py --split test\n")
        assert resolve_verify_cmd(project, {}, "hidden_verify_command") \
            == 'echo "[Metric] X: 999.0"'
        assert resolve_verify_cmd(project, {}, "hidden_verify_command", sealed) \
            == "python3 score.py --split test"


def test_sealed_config_falls_back_for_keys_it_does_not_define():
    with tempfile.TemporaryDirectory() as tmp:
        project = _scored_project(tmp)
        sealed = Path(tmp) / "sealed.conf"
        sealed.write_text("hidden_verify_command=python3 score.py --split test\n")
        assert resolve_verify_cmd(project, {}, "verify_command", sealed) \
            == "python3 score.py"


def test_leak_detected_when_hidden_metric_value_is_quoted():
    """The real failure: examples/goal-vs-loop/logs/session_4.log."""
    log = ("Robustness check (diagnostic only): train split = 1.7697, "
           "hidden test split = 1.5233. Both clear 1.5.")
    signals = hidden_leak_signals(log, "python3 run_backtest.py --split test", 1.5233)
    assert any("1.5233" in s for s in signals)


def test_leak_detected_when_hidden_command_is_echoed():
    log = "I ran python3 run_backtest.py --split test to sanity-check."
    signals = hidden_leak_signals(log, "python3 run_backtest.py --split test", None)
    assert any("ran command" in s for s in signals)


def test_no_leak_signal_from_a_clean_transcript():
    log = "Edited strategies.py, ran the visible backtest, Sharpe 1.3477. Committed."
    assert hidden_leak_signals(log, "python3 run_backtest.py --split test", 1.5233) == []


def test_low_precision_metric_does_not_trigger_a_false_leak():
    """0.5 appears in ordinary prose; only distinctive values may fire."""
    assert hidden_leak_signals("the ratio was 0.5 overall", "", 0.5) == []


def test_real_session_log_is_flagged_and_a_clean_one_is_not():
    """Regression anchored on the transcripts committed in this repo."""
    logs = SCRIPT_DIR / "examples" / "goal-vs-loop" / "logs"
    cmd = "python3 run_backtest.py --split test"
    assert hidden_leak_signals((logs / "session_4.log").read_text(), cmd, 1.5233)
    assert hidden_leak_signals((logs / "session_2.log").read_text(), cmd, 1.5233) == []


def test_run_verification_reports_untrusted_when_scoring_was_rewritten():
    with tempfile.TemporaryDirectory() as tmp:
        project = _scored_project(tmp)
        result = run_verification(str(project), {}, verbose=False,
                                  tampered=["score.py"])
        assert result["integrity"]["trusted"] is False
        assert result["integrity"]["tampered"] == ["score.py"]


def test_run_verification_records_provenance_in_hidden_metrics():
    with tempfile.TemporaryDirectory() as tmp:
        project = _scored_project(
            tmp, "verify_command=python3 score.py\n"
                 'hidden_verify_command=echo "[Metric] Sharpe Ratio: 1.5233"\n')
        run_verification(str(project), {}, session_label="7", verbose=False,
                         tampered=["score.py"],
                         session_log="hidden test split = 1.5233")
        record = json.loads((project / ".state" / "hidden_metrics.json").read_text())[-1]
        assert record["session"] == "7"
        assert record["metric"] == 1.5233
        assert record["sealed"] is False
        assert record["tampered"] == ["score.py"]
        assert record["leaks"]


def test_clean_run_records_no_integrity_flags():
    with tempfile.TemporaryDirectory() as tmp:
        project = _scored_project(
            tmp, 'hidden_verify_command=echo "[Metric] Sharpe Ratio: 1.5233"\n')
        result = run_verification(str(project), {}, session_label="1", verbose=False,
                                  session_log="Did the work, committed.")
        assert result["integrity"]["trusted"] is True
        record = json.loads((project / ".state" / "hidden_metrics.json").read_text())[-1]
        assert "tampered" not in record and "leaks" not in record


def test_verify_timeout_is_configurable():
    """A full model fit outlives the default. mode.conf and .verify can say so."""
    with tempfile.TemporaryDirectory() as tmp:
        project = _scored_project(tmp, "verify_command=sleep 5\nverify_timeout=1\n")
        result = run_verification(str(project), {}, verbose=False)
        assert result["verify"]["success"] is False
        assert "timeout after 1s" in result["verify"]["stderr"]


def test_verify_timeout_default_applies_when_unset():
    with tempfile.TemporaryDirectory() as tmp:
        project = _scored_project(tmp)
        result = run_verification(str(project), {}, verbose=False)
        assert result["verify"]["success"] is True
        assert result["verify"]["metric"] == 0.5



def test_shipped_mode_fails_when_the_evaluation_script_is_missing():
    """Absent evidence is not passing evidence.

    The mode evaloop ships scores by running the project's own evaluation
    script. A project without one cannot be scored, and must not read as
    scoring zero or as passing.
    """
    conf = load_conf(SCRIPT_DIR / "modes" / "experiment")
    with tempfile.TemporaryDirectory() as tmp:
        result = run_verification(tmp, conf, verbose=False)
        assert result["verify"]["success"] is False
        assert result["verify"]["metric"] is None


def test_shipped_mode_scores_a_project_that_has_one():
    conf = load_conf(SCRIPT_DIR / "modes" / "experiment")
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "run_backtest.py").write_text(
            'print("[Metric] Sharpe Ratio: 1.2345")\n')
        result = run_verification(tmp, conf, verbose=False)
        assert result["verify"]["success"] is True
        assert result["verify"]["metric"] == 1.2345


def test_metric_pattern_follows_the_same_precedence_as_the_commands():
    """A project that overrides verify_command must be able to override the
    label it prints, and a sealed file must be able to fix both."""
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "proj"
        project.mkdir()
        (project / "score.sh").write_text('#!/bin/sh\necho "[Metric] Accuracy: 0.91"\n')
        (project / "score.sh").chmod(0o755)
        mode_conf = {"verify_command": "./score.sh",
                     "metric_pattern": "[Metric] Sharpe Ratio:"}

        # mode.conf alone: the label does not match, so there is no metric
        assert run_verification(str(project), mode_conf, verbose=False)["verify"]["metric"] is None

        # the project's own .verify overrides it
        (project / ".verify").write_text("metric_pattern=[Metric] Accuracy:\n")
        assert run_verification(str(project), mode_conf, verbose=False)["verify"]["metric"] == 0.91

        # a sealed file outranks the project's
        (project / ".verify").write_text("metric_pattern=[Metric] Nonsense:\n")
        sealed = Path(tmp) / "sealed.conf"
        sealed.write_text("metric_pattern=[Metric] Accuracy:\n")
        assert run_verification(str(project), mode_conf, verbose=False,
                                sealed=sealed)["verify"]["metric"] == 0.91


def test_unmatched_metric_pattern_leaves_no_metric():
    """Silently falling back to a different [Metric] line is the defect class
    that made a losing Sharpe read as a positive return. Never guess."""
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "proj"
        project.mkdir()
        (project / "score.sh").write_text(
            '#!/bin/sh\necho "[Metric] Accuracy: 0.91"\necho "[Metric] Loss: 0.02"\n')
        (project / "score.sh").chmod(0o755)
        result = run_verification(str(project), {"verify_command": "./score.sh",
                                                 "metric_pattern": "[Metric] Absent:"},
                                  verbose=False)
        assert result["verify"]["success"] is True
        assert result["verify"]["metric"] is None


# ═══════════════════════════════════════════
# Group 8: The held-out gate
#
# Until 7.2 the held-out metric was written to a file that nothing read, so a
# run could report success on the number it had spent every session optimising.
# ═══════════════════════════════════════════

def _lab(tmp, best, target, hidden=None):
    """A project whose held-out record sits in the unsealed default location."""
    state = Path(tmp) / "proj" / ".state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "journal.json").write_text(json.dumps(
        {"experiments": [], "best_metric": best, "target_metric": target}))
    if hidden is not None:
        (state / "hidden_metrics.json").write_text(json.dumps(hidden))
    return state / "journal.json"


def test_visible_target_alone_no_longer_declares_done():
    """The qlib case, with its real figures: visible 3.6430 against a 1.5
    target, held out -0.0297. The run is not finished."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "metric"))
        path = _lab(tmp, 3.6430, 1.5, [{"session": "1", "metric": -1.1125},
                                       {"session": "2", "metric": -0.0297}])
        assert get_phase(path, conf) == "init"


def test_both_metrics_clearing_the_target_finishes_the_run():
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "metric"))
        path = _lab(tmp, 1.9, 1.5, [{"session": "1", "metric": 1.7}])
        assert get_phase(path, conf) == "done"


def test_without_a_held_out_series_behaviour_is_unchanged():
    """Projects that configure no hidden command must run exactly as before."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "metric"))
        assert get_phase(_lab(tmp, 1.9, 1.5), conf) == "done"
        assert get_phase(_lab(tmp, 0.9, 1.5), conf) == "init"


def test_the_gate_reads_the_latest_record_not_the_best():
    """Taking the maximum would be selecting on the held-out segment — the move
    this project exists to prevent. The latest record describes what would ship."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "metric"))
        path = _lab(tmp, 1.9, 1.5, [{"session": "1", "metric": 1.7},
                                    {"session": "2", "metric": 0.4}])
        assert get_phase(path, conf) == "init"


def test_a_tampered_or_leaked_measurement_is_not_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "metric"))
        path = _lab(tmp, 1.9, 1.5, [{"session": "1", "metric": 9.9,
                                     "tampered": ["score.py"]}])
        assert get_phase(path, conf) == "init", "a rewritten scorer cannot open the gate"
        path = _lab(tmp, 1.9, 1.5, [{"session": "1", "metric": 9.9,
                                     "leaks": ["hidden metric 9.9 appears in transcript"]}])
        assert get_phase(path, conf) == "init", "a leaked measurement cannot open the gate"


def test_the_gate_can_only_withhold_completion_never_cause_it():
    """It must not steer the search — only refuse a false victory."""
    with tempfile.TemporaryDirectory() as tmp:
        conf = load_conf(make_mode_dir(tmp, "metric"))
        path = _lab(tmp, 0.4, 1.5, [{"session": "1", "metric": 9.9}])
        assert get_phase(path, conf) == "init", "held-out alone must not finish a run"


def test_divergence_report_states_the_qlib_case_plainly():
    with tempfile.TemporaryDirectory() as tmp:
        path = _lab(tmp, 3.6430, 1.5, [{"session": "1", "metric": -0.0297}])
        r = divergence_report(path, {})
        assert r["gate_open"] is False
        assert r["gap"] is not None and abs(r["gap"] - 3.6727) < 1e-6
        assert "have not transferred" in r["verdict"]


def test_divergence_report_survives_a_project_with_no_state():
    with tempfile.TemporaryDirectory() as tmp:
        r = divergence_report(Path(tmp) / ".state" / "journal.json", {})
        assert r["gate_open"] is True and r["visible"] is None


def test_sealing_moves_the_held_out_record_out_of_the_project():
    """Through 7.2 this file was written to <project>/.state/, the directory
    every mode instructs the agent to read first. The control benchmark found
    it on its first cell, from a session that was not even trying to cheat."""
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "proj"
        sealed = Path(tmp) / "operator" / "task.conf"
        sealed.parent.mkdir(parents=True)
        unsealed_path = hidden_metrics_path(project, None)
        sealed_path = hidden_metrics_path(project, sealed)
        assert project in unsealed_path.parents, "unsealed still lands in the project"
        assert project not in sealed_path.parents, "sealed must not land in the project"
        assert sealed.parent in sealed_path.parents


def test_a_sealed_run_writes_nothing_readable_into_the_project():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "proj"
        (project / ".state").mkdir(parents=True)
        (project / "hid.py").write_text('print("[Metric] Sharpe Ratio: -0.99")\n')
        sealed = Path(tmp) / "operator" / "task.conf"
        sealed.parent.mkdir(parents=True)
        sealed.write_text("hidden_verify_command=python3 hid.py\n")
        run_verification(str(project), {}, verbose=False, sealed=sealed)
        inside = [p.name for p in (project / ".state").rglob("*") if p.is_file()]
        assert "hidden_metrics.json" not in inside, inside
        assert hidden_metrics_path(project, sealed).is_file()


# ═══════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════

if __name__ == "__main__":
    tests = [n for n in sorted(dir()) if n.startswith("test_")]
    passed = failed = 0
    for name in tests:
        try:
            globals()[name]()
            passed += 1
            print(f"  PASS  {name}")
        except Exception as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
