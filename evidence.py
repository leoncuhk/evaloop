"""
evaloop — what a run's numbers are evidence of.

A loop ends with a metric. Whether that metric can be acted on depends on three
things the metric itself does not show: whether its scoring was intact, whether
it transferred to data the loop never optimised against, and whether the
held-out figure it stopped on was itself selected. This module answers those
questions from the records the engine already keeps, and adds the one
measurement the engine cannot take during a run: a confirmation split that is
read exactly once.

Pure functions except `confirm_once`, which runs a command and writes one file.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from core import (
    _hidden_records, _read_kv, as_number, gate_value, held_out_gate,
    hidden_metrics_path, lower_bound, resolve_verify_cmd, run_verify_command,
    safe_read_state, trusted_hidden,
)

NOT_ESTABLISHED = ("construct validity: whether the metric measures what you "
                   "care about. A held-out sample of the wrong quantity agrees "
                   "with a visible sample of the wrong quantity.")


def confirmation_path(project: Path, sealed: Path) -> Path:
    """Where the confirmation record lives: beside the sealed config."""
    return Path(sealed).parent / f"{Path(project).name}.confirmation.json"


def confirm_once(project: Path, conf: dict, sealed: Path = None,
                 verbose: bool = True) -> dict:
    """Run `confirm_verify_command` once, and never again for this project.

    The held-out gate is consulted after every session and the run stops at the
    first one that clears it, so the held-out figure at the stop is the maximum
    of a noisy series over its stopping time. Reusing a split to decide when to
    stop spends it. The confirmation split is read once, after the decision,
    and is the only figure here that no choice was conditioned on.

    Read from the sealed file only: a confirmation the agent could redefine
    would confirm nothing. Returns the record, the existing one if the split is
    already spent, or None when no sealed confirmation is configured.
    """
    if sealed is None:
        return None
    cmd = _read_kv(Path(sealed)).get("confirm_verify_command", "")
    if not cmd:
        return None
    path = confirmation_path(project, sealed)
    if path.is_file():
        try:
            record = json.loads(path.read_text())
            record["spent"] = True
            if verbose:
                print(f"  confirm: already spent at {record.get('timestamp')}; "
                      f"not re-run")
            return record
        except (json.JSONDecodeError, ValueError):
            pass  # an unreadable record cannot stand in for a measurement
    timeout = int(as_number(resolve_verify_cmd(
        Path(project), conf, "verify_timeout", sealed)) or 300)
    pattern = resolve_verify_cmd(Path(project), conf, "metric_pattern", sealed)
    r = run_verify_command(str(project), cmd, timeout=timeout,
                           metric_pattern=pattern)
    record = {"metric": r.get("metric"), "success": r["success"],
              "timestamp": datetime.now(timezone.utc).isoformat()}
    if r.get("samples"):
        record["samples"] = r["samples"]
        record["lower_bound"] = lower_bound(r["samples"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n")
    os.replace(str(tmp), str(path))
    record["spent"] = False
    if verbose:
        ok = r["success"] and record["metric"] is not None
        print(f"  confirm: {'PASS' if ok else 'FAIL'} | metric: "
              f"{record['metric']} (recorded outside the project; will not re-run)")
    return record


def misplaced_hidden_data(project: Path, sealed: Path = None) -> list:
    """Declared held-out data paths that sit inside the agent's project.

    The sealed file may list `hidden_data=` paths, comma-separated. Sealing the
    command does not seal the data it reads; a held-out file under the project
    is one `cat` away. Only placement is checked. Read permission elsewhere on
    the machine is the sandbox's job, not this function's.
    """
    if sealed is None:
        return []
    raw = _read_kv(Path(sealed)).get("hidden_data", "")
    root = Path(project).resolve()
    out = []
    for item in (s.strip() for s in raw.split(",") if s.strip()):
        p = Path(item).expanduser()
        p = (root / p if not p.is_absolute() else p).resolve()
        try:
            p.relative_to(root)
            out.append(str(p))
        except ValueError:
            pass
    return out


def _basis(record: dict) -> str:
    samples = record.get("samples") or []
    if as_number(record.get("lower_bound")) is not None:
        return f"95% lower bound over {len(samples)} samples"
    return "single value; no uncertainty reported"


def evidence(project: Path, conf: dict, sealed: Path = None) -> dict:
    """What the run's records support, stated at the strength they support it.

    Verdicts, weakest to strongest: `no target`, `no held-out measurement`,
    `not transferred` (visible met, held-out not), `below target`,
    `unconfirmed` (held-out gate open, but its stopping point was selected on
    that same split), `not confirmed`, `confirmed`. Only `confirmed` rests on a
    measurement nothing in the run was conditioned on.
    """
    project = Path(project)
    state_path = project / ".state" / conf.get("state_file", "tasks.json")
    data, _ = safe_read_state(state_path)
    data = data or {}
    target = as_number(data.get("target_metric"))
    margin = as_number(resolve_verify_cmd(project, conf, "held_out_margin",
                                          sealed)) or 0.0
    path = hidden_metrics_path(project, sealed)
    all_records, clean = _hidden_records(path), trusted_hidden(path)
    ev = {"target": target, "margin": margin,
          "visible": as_number(data.get("best_metric")),
          "sealed": sealed is not None,
          "held_out": None, "held_out_queries": len(all_records),
          "discredited": [{"session": r.get("session"),
                           "tampered": r.get("tampered", []),
                           "leaks": r.get("leaks", [])}
                          for r in all_records
                          if r.get("tampered") or r.get("leaks")],
          "confirmation": None, "not_established": NOT_ESTABLISHED}
    if clean:
        last = clean[-1]
        ev["held_out"] = {"metric": as_number(last.get("metric")),
                          "gate_value": gate_value(last), "basis": _basis(last),
                          "session": last.get("session")}
    gate_open, _ = held_out_gate(path, target, margin)
    ev["gate_open"] = gate_open

    if sealed is not None:
        cp = confirmation_path(project, sealed)
        if cp.is_file():
            try:
                c = json.loads(cp.read_text())
                value = gate_value(c)
                ev["confirmation"] = {
                    "metric": as_number(c.get("metric")), "gate_value": value,
                    "basis": _basis(c), "timestamp": c.get("timestamp"),
                    "passed": (target is not None and value is not None
                               and value >= target + margin)}
            except (json.JSONDecodeError, ValueError):
                pass

    if target is None:
        ev["verdict"] = "no target"
    elif ev["held_out"] is None:
        ev["verdict"] = "no held-out measurement"
    elif not gate_open:
        v = ev["visible"]
        ev["verdict"] = ("not transferred" if v is not None and v >= target
                         else "below target")
    elif ev["confirmation"] is None:
        ev["verdict"] = "unconfirmed"
    else:
        ev["verdict"] = ("confirmed" if ev["confirmation"]["passed"]
                         else "not confirmed")
    return ev


_EXPLAIN = {
    "no target": "no target_metric in state; nothing to judge against",
    "no held-out measurement": "every number describes the segment being optimised",
    "not transferred": "the visible target is met and the held-out figure is not",
    "below target": "the held-out figure does not clear the target",
    "unconfirmed": ("the held-out gate is open, but the run stopped when it "
                    "opened, so that figure was selected; read a sealed "
                    "confirm_verify_command once with `evidence --confirm`"),
    "not confirmed": "held-out cleared the gate; the unselected confirmation did not",
    "confirmed": "held-out and the once-read confirmation both clear the target",
}


def render(ev: dict) -> list:
    """Evidence as lines for a terminal."""
    lines = [f"Evidence: {ev['verdict'].upper()} — {_EXPLAIN[ev['verdict']]}"]
    if ev["target"] is not None:
        extra = f" + margin {ev['margin']}" if ev["margin"] else ""
        lines.append(f"  target: {ev['target']}{extra} | visible: {ev['visible']}")
    h = ev["held_out"]
    if h:
        lines.append(f"  held-out: {h['metric']} (judged on {h['gate_value']:.4f}, "
                     f"{h['basis']}); consulted {ev['held_out_queries']} time(s)")
    c = ev["confirmation"]
    if c:
        judged = (f"{c['gate_value']:.4f}" if c["gate_value"] is not None
                  else "none")
        lines.append(f"  confirmation: {c['metric']} (judged on {judged}, "
                     f"{c['basis']}), read once at {c['timestamp']}")
    if not ev["sealed"]:
        lines.append("  no sealed config: the scoring definition was agent-writable")
    for d in ev["discredited"]:
        why = ", ".join(d["tampered"] + d["leaks"])
        lines.append(f"  discredited: session {d['session']} ({why})")
    lines.append(f"  not established: {ev['not_established']}")
    return lines
