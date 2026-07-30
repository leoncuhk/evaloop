"""
evaloop — evaluation-driven autonomous development, core.

Pure functions for verification, metric parsing, state management, and phase detection.
Shared by run.py and usable as a library. No SDK dependency.
"""

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def load_conf(mode_dir: Path) -> dict:
    """Load mode.conf as a dict."""
    conf = {}
    conf_file = mode_dir / "mode.conf"
    if conf_file.exists():
        for line in conf_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                conf[k.strip()] = v.strip()
    return conf


def count_by_status(data: dict, jq_query: str) -> int:
    """Evaluate jq-style count queries in pure Python.

    Handles: [.array[] | select(.status == "val" or .status == "val2")] | length
    Also checks 'decision' field as fallback when 'status' is absent,
    since LLMs sometimes use 'decision' instead of 'status' in journal entries.
    """
    m = re.search(r"\.(\w+)\[\]", jq_query)
    if not m:
        return 0
    items = data.get(m.group(1), [])
    statuses = set(re.findall(r"\.status\s*==\s*\"([^\"]+)\"", jq_query))
    if not statuses:
        statuses = set(re.findall(r'"([^"]+)"', jq_query))
    def _matches(item):
        s = item.get("status", "")
        if s in statuses:
            return True
        d = item.get("decision", "")
        return any(d == v or d.startswith(v + "(") for v in statuses) if d else False
    return sum(1 for item in items if _matches(item))


def as_number(value):
    """Coerce a state value to float, or None. LLMs write numbers as strings."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_phase(state_path: Path, conf: dict) -> str:
    """Determine current phase: init | work | done."""
    if not state_path.exists():
        return "init"
    try:
        data = json.loads(state_path.read_text())
    except (json.JSONDecodeError, ValueError):
        return "init"

    pending_q = conf.get(
        "pending_query",
        '[.tasks[] | select(.status == "pending" or .status == "in_progress")] | length',
    )
    if count_by_status(data, pending_q) > 0:
        return "work"

    progress_q = conf.get(
        "progress_query",
        '[.tasks[] | select(.status == "done")] | length',
    )
    done_count = count_by_status(data, progress_q)

    best = as_number(data.get("best_metric")) or 0.0
    target = as_number(data.get("target_metric"))
    if target:
        return "done" if best >= target else "init"

    if done_count == 0:
        return "init"
    return "done"


def progress_count(state_path: Path, conf: dict) -> int:
    """Count completed items (for circuit breaker)."""
    if not state_path.exists():
        return 0
    try:
        data = json.loads(state_path.read_text())
    except (json.JSONDecodeError, ValueError):
        return 0
    progress_q = conf.get(
        "progress_query",
        '[.tasks[] | select(.status == "done")] | length',
    )
    return count_by_status(data, progress_q)


# --- State validation ---

def _schema(conf: dict):
    """The state schema a mode declares, or None if it declares none.

    Modes name their work array and its legal statuses in mode.conf. Reading the
    schema from the mode — rather than from a table keyed by mode name — is what
    lets a mode you wrote yourself be validated too. A mode that declares
    nothing is not validated, and that is visible in its mode.conf rather than
    hidden in this file.
    """
    array_key = conf.get("state_array")
    statuses = {s.strip() for s in conf.get("valid_statuses", "").split(",") if s.strip()}
    return (array_key, statuses) if array_key and statuses else None


def validate_state(data: dict, conf: dict) -> tuple:
    """Validate state against the mode's declared schema. Returns (valid, errors).

    Accepts the field names real runs produce, not just the canonical ones:
    `round` identifies an item as well as `id`, and `decision` carries status as
    well as `status` — including the `accepted(best)` form. `count_by_status`
    already reads state that way, and a validator stricter than the reader would
    reject journals the loop itself is happy to act on.
    """
    errors = []
    if not isinstance(data, dict):
        return False, ["state must be a dict"]
    schema = _schema(conf)
    if not schema:
        return True, []
    array_key, valid_statuses = schema
    if array_key not in data:
        return False, [f"missing required key: {array_key}"]
    items = data[array_key]
    if not isinstance(items, list):
        return False, [f"{array_key} must be an array"]
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{array_key}[{i}]: must be an object")
            continue
        if "id" not in item and "round" not in item:
            errors.append(f"{array_key}[{i}]: missing 'id' (or 'round')")
        raw = item.get("status", item.get("decision"))
        if raw is None:
            errors.append(f"{array_key}[{i}]: missing 'status' (or 'decision')")
        elif str(raw).split("(")[0] not in valid_statuses:
            errors.append(f"{array_key}[{i}]: invalid status '{raw}'")
    return (len(errors) == 0), errors


_NUM = r"(-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"
_METRIC_RE = re.compile(r"\[Metric\]\s+[^:\n]+:\s*" + _NUM)


def parse_metric(output: str, pattern: str = ""):
    """Extract a metric from command output.

    Reads the first parseable `[Metric] <name>: <number>` line. Negative values
    and scientific notation are both valid metrics. `pattern` is mode.conf's
    `metric_pattern` — the literal label prefix to select when a command emits
    several `[Metric]` lines and a specific one is the target.
    """
    if pattern:
        m = re.search(re.escape(pattern.strip()) + r"\s*" + _NUM, output)
    else:
        m = _METRIC_RE.search(output)
    return float(m.group(1)) if m else None


def run_verify_command(project_dir: str, command: str, timeout: int = 60,
                       metric_pattern: str = "") -> dict:
    """Run a verification command and return structured result."""
    try:
        result = subprocess.run(
            command, shell=True, cwd=project_dir,
            capture_output=True, text=True, timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "metric": parse_metric(result.stdout, metric_pattern),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "exit_code": -1, "stdout": "",
                "stderr": f"timeout after {timeout}s", "metric": None}
    except Exception as e:
        return {"success": False, "exit_code": -1, "stdout": "", "stderr": str(e), "metric": None}


def safe_read_state(state_path: Path) -> tuple:
    """Read state file safely. Returns (data, error_message)."""
    if not state_path.exists():
        return None, "file does not exist"
    raw = state_path.read_text()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup = state_path.with_name(f"backup_{ts}_{state_path.name}")
        shutil.copy2(state_path, backup)
        return None, f"invalid JSON (backup: {backup.name}): {e}"
    if not isinstance(data, dict):
        return None, "state must be a dict"
    return data, None


def safe_write_state(state_path: Path, data: dict, conf: dict) -> tuple:
    """Write state with validation and atomic rename. Returns (success, error)."""
    valid, errors = validate_state(data, conf)
    if not valid:
        return False, "; ".join(errors)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup = state_path.with_name(f"backup_{ts}_{state_path.name}")
        shutil.copy2(state_path, backup)
    tmp_path = state_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(str(tmp_path), str(state_path))
    return True, None


# --- Verification harness (Loop 2) ---

def _read_kv(path: Path) -> dict:
    """Parse a `key=value` file, ignoring blanks and # comments."""
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def resolve_verify_cmd(project: Path, conf: dict, key: str,
                       sealed: Path = None) -> str:
    """Resolve a verification command.

    Precedence: a sealed file outside the project > project `.verify` >
    mode.conf. The sealed file is how an operator keeps the scoring definition
    beyond the agent's reach: everything under the project directory is
    writable by the agent, `.verify` included.
    """
    if sealed is not None:
        sealed_conf = _read_kv(Path(sealed))
        if key in sealed_conf:
            return sealed_conf[key]
    local = _read_kv(project / ".verify")
    if key in local:
        return local[key]
    return conf.get(key, "")


def scoring_fingerprint(project: Path, conf: dict, sealed: Path = None) -> dict:
    """Hash every in-project input that decides how this project is scored.

    Covers `.verify` and any file inside the project that a verification
    command invokes. The agent can edit all of these, so the orchestrator
    fingerprints them before a session and re-checks after: a changed hash
    means the run rewrote its own scoring, and its metric cannot be trusted.
    A sealed file lives outside the project and is deliberately not hashed
    here — the agent cannot reach it.
    """
    parts = {}
    vf = project / ".verify"
    if vf.is_file():
        parts[".verify"] = hashlib.sha256(vf.read_bytes()).hexdigest()
    for key in ("verify_command", "hidden_verify_command"):
        cmd = resolve_verify_cmd(project, conf, key, sealed)
        if not cmd:
            continue
        try:
            tokens = shlex.split(cmd)
        except ValueError:
            tokens = cmd.split()
        for tok in tokens:
            candidate = project / tok
            if candidate.is_file():
                rel = tok.lstrip("./")
                parts[rel] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    return parts


def fingerprint_diff(before: dict, after: dict) -> list:
    """Names whose scoring fingerprint changed between two points in time."""
    return sorted(k for k in set(before) | set(after)
                  if before.get(k) != after.get(k))


def _command_core(cmd: str) -> str:
    """The invocation itself, without shell fallbacks or redirections."""
    for sep in ("||", "&&", "|", "2>", ">"):
        cmd = cmd.split(sep)[0]
    return " ".join(cmd.split())


def hidden_leak_signals(log_text: str, hidden_cmd: str = "", metric=None) -> list:
    """Evidence that a session obtained the hidden metric for itself.

    The orchestrator never reports the hidden metric back, but an agent with
    shell access can compute it — a live session in examples/goal-vs-loop did
    exactly that. Two signals:

    - the hidden invocation appears in the transcript
    - the hidden metric's own value appears in the transcript, which the agent
      can only know by having run the command

    The value check needs at least four significant digits to fire, because a
    metric like 0.5 matches ordinary prose. This is a detector, not a barrier:
    it marks a metric contaminated, it never certifies one clean. Sealing the
    command outside the project is the control; this catches what leaks anyway.
    """
    signals = []
    if not log_text:
        return signals
    haystack = " ".join(log_text.split())

    core = _command_core(hidden_cmd)
    if core and core in haystack:
        signals.append(f"ran command: {core}")
    elif core:
        tokens = core.split()
        for i, tok in enumerate(tokens):
            if tok.endswith((".py", ".sh")):
                tail = " ".join(tokens[i:])
                if tail in haystack:
                    signals.append(f"ran command: {tail}")
                break

    value = as_number(metric)
    if value is not None:
        for text in {f"{value:.4f}".rstrip("0"), repr(value)}:
            digits = sum(c.isdigit() for c in text)
            if digits >= 4 and text in haystack:
                signals.append(f"hidden metric {text} appears in transcript")
                break
    return signals


def run_verification(project_dir: str, conf: dict, session_label: str = "",
                     verbose: bool = True, sealed: Path = None,
                     tampered: list = None, session_log: str = "") -> dict:
    """Run verify_command and hidden_verify_command independently.

    This is the core value of the harness: structurally separate evaluation.

    `sealed` points at a verification config outside the project directory, so
    the agent cannot redefine how it is scored. `tampered` carries the names
    whose scoring fingerprint changed during the session. `session_log` is the
    transcript to scan for hidden-metric leaks. Every one of these is recorded
    alongside the metric, because a metric whose provenance is unknown is worse
    than no metric at all.

    Returns {verify: result|None, hidden: result|None, integrity: {...}}.
    """
    project = Path(project_dir)
    tampered = list(tampered or [])
    # Real verification can be a full model fit. The default suits a test suite;
    # anything heavier sets verify_timeout in mode.conf, .verify, or the sealed
    # file. A timeout is a failed check, not a metric of zero.
    timeout = int(as_number(resolve_verify_cmd(
        project, conf, "verify_timeout", sealed)) or 300)
    result = {"verify": None, "hidden": None,
              "integrity": {"tampered": tampered, "leaks": [], "trusted": not tampered}}

    metric_pattern = conf.get("metric_pattern", "")

    verify_cmd = resolve_verify_cmd(project, conf, "verify_command", sealed)
    if verify_cmd:
        vr = run_verify_command(project_dir, verify_cmd, timeout=timeout,
                                metric_pattern=metric_pattern)
        result["verify"] = vr
        if verbose:
            status = "PASS" if vr["success"] else "FAIL"
            metric = f" | metric: {vr['metric']}" if vr.get("metric") is not None else ""
            print(f"  verify: {status} (exit {vr['exit_code']}){metric}")

    hidden_cmd = resolve_verify_cmd(project, conf, "hidden_verify_command", sealed)
    if hidden_cmd:
        hr = run_verify_command(project_dir, hidden_cmd, timeout=timeout,
                                metric_pattern=metric_pattern)
        result["hidden"] = hr
        leaks = hidden_leak_signals(session_log, hidden_cmd, hr.get("metric"))
        result["integrity"]["leaks"] = leaks
        state_dir = project / ".state"
        state_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = state_dir / "hidden_metrics.json"
        existing = []
        if metrics_path.exists():
            try:
                existing = json.loads(metrics_path.read_text())
            except (json.JSONDecodeError, ValueError):
                existing = []
        record = {"session": session_label, "metric": hr.get("metric"),
                  "timestamp": datetime.now(timezone.utc).isoformat(),
                  "sealed": sealed is not None}
        if tampered:
            record["tampered"] = tampered
        if leaks:
            record["leaks"] = leaks
        existing.append(record)
        tmp = metrics_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(existing, indent=2) + "\n")
        os.replace(str(tmp), str(metrics_path))
        if verbose:
            status = "PASS" if hr["success"] else "FAIL"
            print(f"  hidden: {status} (metric written to .state/hidden_metrics.json)")
            for leak in leaks:
                print(f"  CONTAMINATED: {leak}")

    if verbose and tampered:
        print(f"  TAMPERED: scoring inputs changed during the session: "
              f"{', '.join(tampered)}")
        print("  The metric above was produced by definitions this session "
              "rewrote. Do not treat it as a result.")

    return result
