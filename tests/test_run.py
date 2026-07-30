"""Tests for core utility functions (no SDK dependency)."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core import count_by_status, load_conf, get_phase


# ═══════════════════════════════════════════
# count_by_status
# ═══════════════════════════════════════════

def test_count_pending_tasks():
    data = {"tasks": [
        {"id": 1, "status": "done"}, {"id": 2, "status": "pending"},
        {"id": 3, "status": "pending"}, {"id": 4, "status": "in_progress"},
    ]}
    q = '[.tasks[] | select(.status == "pending" or .status == "in_progress")] | length'
    assert count_by_status(data, q) == 3

def test_count_done():
    data = {"tasks": [{"status": "done"}, {"status": "pending"}, {"status": "done"}]}
    assert count_by_status(data, '[.tasks[] | select(.status == "done")] | length') == 2

def test_count_researcher():
    data = {"experiments": [
        {"status": "accepted"}, {"status": "rejected"},
        {"status": "pending"}, {"status": "running"},
    ]}
    q = '[.experiments[] | select(.status == "pending" or .status == "planned" or .status == "running")] | length'
    assert count_by_status(data, q) == 2

def test_count_third_shape():
    data = {"findings": [{"status": "verified"}, {"status": "dismissed"}, {"status": "pending"}]}
    assert count_by_status(data, '[.findings[] | select(.status == "verified" or .status == "dismissed")] | length') == 2

def test_count_empty():
    assert count_by_status({"tasks": []}, '[.tasks[] | select(.status == "pending")] | length') == 0

def test_count_missing_array():
    assert count_by_status({}, '[.tasks[] | select(.status == "pending")] | length') == 0

def test_count_prefers_status_field():
    data = {"items": [{"status": "pending", "type": "critical"}, {"status": "critical"}]}
    assert count_by_status(data, '[.items[] | select(.type == "critical" and .status == "pending")] | length') == 1


# ═══════════════════════════════════════════
# load_conf
# ═══════════════════════════════════════════

def test_load_conf_basic():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "mode.conf").write_text("description=Test\nentry_file=spec.md\n")
        assert load_conf(Path(d)) == {"description": "Test", "entry_file": "spec.md"}

def test_load_conf_comments():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "mode.conf").write_text("# comment\ndescription=Test\n\n")
        assert load_conf(Path(d)) == {"description": "Test"}

def test_load_conf_missing():
    with tempfile.TemporaryDirectory() as d:
        assert load_conf(Path(d)) == {}

def test_load_conf_value_with_equals():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "mode.conf").write_text('q=[.tasks[] | select(.status == "pending")] | length\n')
        assert "==" in load_conf(Path(d))["q"]


# ═══════════════════════════════════════════
# get_phase
# ═══════════════════════════════════════════

def test_phase_no_state():
    assert get_phase(Path("/nonexistent.json"), {}) == "init"

def test_phase_pending():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"tasks": [{"status": "pending"}, {"status": "done"}]}, f)
        f.flush()
        assert get_phase(Path(f.name), {}) == "work"

def test_phase_all_done():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"tasks": [{"status": "done"}, {"status": "done"}]}, f)
        f.flush()
        assert get_phase(Path(f.name), {}) == "done"

def test_phase_target_met():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"experiments": [], "best_metric": 1.89, "target_metric": 1.5}, f)
        f.flush()
        assert get_phase(Path(f.name), {"pending_query": '[.experiments[] | select(.status == "pending")] | length'}) == "done"

def test_phase_target_not_met():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"experiments": [], "best_metric": 0.84, "target_metric": 1.5}, f)
        f.flush()
        assert get_phase(Path(f.name), {"pending_query": '[.experiments[] | select(.status == "pending")] | length'}) == "init"

def test_phase_invalid_json():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("not json"); f.flush()
        assert get_phase(Path(f.name), {}) == "init"


if __name__ == "__main__":
    tests = [n for n in sorted(dir()) if n.startswith("test_")]
    passed = failed = 0
    for name in tests:
        try:
            globals()[name](); passed += 1; print(f"  PASS  {name}")
        except Exception as e:
            failed += 1; print(f"  FAIL  {name}: {e}")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
