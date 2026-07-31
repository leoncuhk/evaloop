#!/usr/bin/env python3
"""
evaloop v7.5.0 — Evaluation-Driven Autonomous Development

For loops whose acceptance criterion is a metric rather than a test suite.
The orchestrator scores the work, keeps a held-out metric the agent never sees,
and records which of those numbers can be trusted.

Usage:
  python run.py verify <project-dir> [--sealed-verify FILE]   # score only, no LLM
  python run.py loop <project-dir> [--sealed-verify FILE]     # session loop + scoring
  python run.py status <project-dir>                          # show phase/progress

Scoring integrity: --sealed-verify FILE keeps the scoring definition outside the
project, so an agent that rewrites .verify changes nothing. In-project scoring
files are fingerprinted around each session, and transcripts are scanned for
hidden-metric leaks.
"""

import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
VERSION = "7.5.0"
COMPLETE_SIGNAL = "<promise>COMPLETE</promise>"
DEFAULT_MODE = "experiment"

from core import (
    load_conf, get_phase, progress_count, run_verification,
    resolve_verify_cmd, safe_read_state, scoring_fingerprint,
    fingerprint_diff, validate_state, divergence_report,
)

_sdk_available = False
try:
    from claude_agent_sdk import (
        query, ClaudeAgentOptions, HookMatcher, ResultMessage, AssistantMessage,
    )
    _sdk_available = True
except ImportError:
    pass

# ═══════════════════════════════════════════════════════════════
# Hooks — SDK Safety Layer
# ═══════════════════════════════════════════════════════════════

BLOCKED_PATTERNS = [
    "rm -rf /", "rm -rf ~", "rm -rf .",
    "git push --force", "git push -f", "DROP TABLE", "DROP DATABASE",
]


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}


async def safety_guard(input_data: dict, _tool_use_id, _ctx) -> dict:
    """PreToolUse: block obviously dangerous Bash commands."""
    cmd = input_data.get("tool_input", {}).get("command", "")
    for p in BLOCKED_PATTERNS:
        if p in cmd:
            return _deny(f"Blocked: {p}")
    return {}


async def orient_edit_guard(input_data: dict, _tool_use_id, _ctx) -> dict:
    """PreToolUse: orient phase can only edit .state/ files."""
    if input_data.get("tool_name") == "Edit":
        path = input_data.get("tool_input", {}).get("file_path", "")
        if "/.state/" not in path:
            return _deny(f"Orient phase: can only edit .state/ files, not {path}")
    return {}


# ═══════════════════════════════════════════════════════════════
# Phase Configuration
# ═══════════════════════════════════════════════════════════════

PHASE_CONF = {
    "orient": {"allowed_tools": ["Read", "Glob", "Grep", "Edit"],
               "disallowed_tools": ["Bash", "Write"], "hooks": {}},
    "review": {"allowed_tools": ["Read", "Glob", "Grep", "Edit", "Bash"],
               "disallowed_tools": [], "hooks": {}},
    "default": {"allowed_tools": ["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
                "disallowed_tools": [], "hooks": {}},
}
if _sdk_available:
    PHASE_CONF["orient"]["hooks"] = {
        "PreToolUse": [HookMatcher(matcher="Edit", hooks=[orient_edit_guard])]}
    PHASE_CONF["review"]["hooks"] = {
        "PreToolUse": [HookMatcher(matcher="Bash", hooks=[safety_guard])]}
    PHASE_CONF["default"]["hooks"] = {
        "PreToolUse": [HookMatcher(matcher="Bash", hooks=[safety_guard])]}

PHASE_KEYS = {
    "init": "phase_init", "work": "phase_work",
    "review": "phase_review", "orient": "phase_orient",
}

# ═══════════════════════════════════════════════════════════════
# Session Execution — Real SDK + Simulated
# ═══════════════════════════════════════════════════════════════


async def run_session(
    project: Path, mode_dir: Path, conf: dict,
    phase: str, label: str, max_turns: int,
) -> dict:
    """Execute one agent session via SDK query()."""
    prompt_name = conf.get(PHASE_KEYS.get(phase, ""), phase)
    prompt_file = mode_dir / "prompts" / f"{prompt_name}.md"
    if not prompt_file.exists():
        return {"status": "skipped", "cost": 0.0, "turns": 0, "complete": False}

    result = {"status": "unknown", "cost": 0.0, "turns": 0, "complete": False}
    log_parts = []
    pc = PHASE_CONF.get(phase, PHASE_CONF["default"])
    opts_kwargs = dict(
        allowed_tools=pc["allowed_tools"], max_turns=max_turns,
        cwd=str(project), permission_mode="bypassPermissions", hooks=pc["hooks"],
    )
    if pc["disallowed_tools"]:
        opts_kwargs["disallowed_tools"] = pc["disallowed_tools"]

    try:
        async for msg in query(
            prompt=prompt_file.read_text(),
            options=ClaudeAgentOptions(**opts_kwargs),
        ):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if hasattr(block, "text"):
                        log_parts.append(block.text)
                        if COMPLETE_SIGNAL in block.text:
                            result["complete"] = True
            if isinstance(msg, ResultMessage):
                result["status"] = msg.subtype
                result["cost"] = msg.total_cost_usd or 0.0
                result["turns"] = msg.num_turns
                if COMPLETE_SIGNAL in (msg.result or ""):
                    result["complete"] = True
    except Exception as e:
        result["status"] = "error"
        log_parts.append(f"ERROR: {e}")

    log_dir = project / "logs"
    log_dir.mkdir(exist_ok=True)
    (log_dir / f"session_{label}.log").write_text("\n".join(log_parts))
    return result


async def run_simulated_session(
    project: Path, mode_dir: Path, conf: dict,
    phase: str, label: str, sim_script: list, sim_idx: int,
) -> dict:
    """Execute a simulated session from sim_script.json."""
    result = {"status": "success", "cost": 0.0, "turns": 1, "complete": False}
    entry = sim_script[sim_idx] if sim_idx < len(sim_script) else (
        sim_script[-1] if sim_script else None)
    if entry is None:
        return {"status": "skipped", "cost": 0.0, "turns": 0, "complete": False}

    state_changes = entry.get("state_changes", {})
    if state_changes:
        state_file = project / ".state" / conf.get("state_file", "tasks.json")
        data = {}
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
            except (json.JSONDecodeError, ValueError):
                pass
        for k, v in state_changes.items():
            data[k] = v
        state_file.write_text(json.dumps(data, indent=2) + "\n")

    # A simulated session may also rewrite project files, so that misbehaviour
    # the integrity checks exist to catch — an agent editing its own scoring —
    # is reproducible without spending a real session on it.
    for rel, content in entry.get("file_writes", {}).items():
        target = project / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    result["complete"] = entry.get("complete", False)
    result["cost"] = entry.get("cost", 0.0)
    result["status"] = entry.get("status", "success")
    log_dir = project / "logs"
    log_dir.mkdir(exist_ok=True)
    (log_dir / f"session_{label}.log").write_text(
        entry.get("transcript", f"[SIMULATE] phase={phase} entry={json.dumps(entry)}"))
    return result


async def run_cli_session(
    project: Path, mode_dir: Path, conf: dict,
    phase: str, label: str, max_turns: int,
) -> dict:
    """Execute one agent session via claude CLI (no SDK needed)."""
    prompt_name = conf.get(PHASE_KEYS.get(phase, ""), phase)
    prompt_file = mode_dir / "prompts" / f"{prompt_name}.md"
    if not prompt_file.exists():
        return {"status": "skipped", "cost": 0.0, "turns": 0, "complete": False}

    result = {"status": "unknown", "cost": 0.0, "turns": 0, "complete": False}
    try:
        proc = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions", "--output-format", "text"],
            input=prompt_file.read_text(), capture_output=True, text=True,
            cwd=str(project), timeout=900,
        )
        output = proc.stdout or ""
        stderr = proc.stderr or ""
        result["status"] = "success" if proc.returncode == 0 else "error"
        result["turns"] = 1
        if COMPLETE_SIGNAL in output:
            result["complete"] = True
        if proc.returncode != 0 and not output:
            output = f"[claude -p exit code {proc.returncode}]\nSTDERR:\n{stderr}"
    except subprocess.TimeoutExpired:
        output = "[TIMEOUT] claude -p exceeded 900s"
        result["status"] = "timeout"
    except Exception as e:
        output = f"ERROR: {e}"
        result["status"] = "error"

    log_dir = project / "logs"
    log_dir.mkdir(exist_ok=True)
    (log_dir / f"session_{label}.log").write_text(output[-10000:])
    return result


# ═══════════════════════════════════════════════════════════════
# Dual-Loop Engine
# ═══════════════════════════════════════════════════════════════

def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def resolve_mode(name: str) -> Path:
    """A mode is a directory. Accept a path to one, or the name of a bundled one.

    Resolving only bundled names made `modes/` a registry rather than an
    extension point: defining your own loop meant putting it inside this
    repository. A path lets it live in your project, where it belongs.
    """
    candidate = Path(name).expanduser()
    if candidate.is_dir() and (candidate / "mode.conf").is_file():
        return candidate.resolve()
    bundled = SCRIPT_DIR / "modes" / name
    if bundled.is_dir():
        return bundled
    available = sorted(d.name for d in (SCRIPT_DIR / "modes").iterdir() if d.is_dir())
    sys.exit(f"Mode '{name}' is neither a directory containing mode.conf nor one "
             f"of the bundled modes: {', '.join(available)}")


def _is_inside(path: Path, parent: Path) -> bool:
    """True if path sits under parent — i.e. within the agent's reach."""
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _write_orient_brief(project: Path, orient: dict) -> None:
    """Hand the strategist a conclusion, not a pile of state.

    Boyd's chain is Orient then Decide. The orchestrator does the orienting —
    it is arithmetic — and the strategist is asked only for the judgement that
    arithmetic cannot make.
    """
    lines = ["# Orient brief", "",
             "Written by the orchestrator before this session. The held-out",
             "figure below is the one the working sessions never see; it is",
             "shown to you so the decision can account for it. Do not copy it",
             "into any file the working sessions read.", ""]
    for key, label in [("visible", "Best visible metric"),
                       ("held_out", "Latest held-out metric"),
                       ("target", "Target"),
                       ("gap", "Gap (visible − held out)"),
                       ("measurements", "Clean held-out measurements")]:
        if orient.get(key) is not None:
            lines.append(f"- {label}: {orient[key]}")
    lines += ["", f"**Assessment**: {orient['verdict']}", ""]
    if orient.get("target") is not None and not orient["gate_open"]:
        lines.append("The run cannot be declared complete while this holds, "
                     "however good the visible metric looks.")
    (project / ".state").mkdir(parents=True, exist_ok=True)
    (project / ".state" / "orient.md").write_text("\n".join(lines) + "\n")


def _read_session_log(project: Path, session: int) -> str:
    """Read back what the session said, for hidden-metric leak detection."""
    text = []
    for name in (f"session_{session}.log", f"session_{session}_retry.log"):
        log = project / "logs" / name
        if log.is_file():
            text.append(log.read_text(errors="replace"))
    return "\n".join(text)


async def _dispatch(sim, proj, mdir, conf, phase, label, turns, sscript, sidx):
    """Route to simulated, SDK, or CLI session."""
    if sim:
        return await run_simulated_session(proj, mdir, conf, phase, label, sscript, sidx), sidx + 1
    if _sdk_available:
        return await run_session(proj, mdir, conf, phase, label, turns), sidx
    return await run_cli_session(proj, mdir, conf, phase, label, turns), sidx


async def engine(args):
    """Dual-loop engine: outer OODA (strategic) + inner session (tactical)."""
    simulate = getattr(args, "simulate", False)
    lp = "[SIMULATE] " if simulate else ""

    mode_dir = resolve_mode(args.mode)

    conf = load_conf(mode_dir)
    project = Path(args.project_dir).resolve()
    project.mkdir(parents=True, exist_ok=True)
    (project / ".state").mkdir(exist_ok=True)
    (project / "logs").mkdir(exist_ok=True)

    entry = conf.get("entry_file", "spec.md")
    if not (project / entry).exists():
        sys.exit(f"No {entry} in {project}. Required for --mode {args.mode}.")

    # The project CLAUDE.md is an engine-owned runtime artifact (gitignored), so
    # refresh it whenever the mode template changes. Leaving a stale copy in
    # place would keep feeding old instructions to every future session.
    src = mode_dir / conf.get("claude_md", "CLAUDE.md")
    if not src.exists():
        src = SCRIPT_DIR / "CLAUDE.md"
    if src.exists():
        dst = project / "CLAUDE.md"
        template = src.read_text()
        if not dst.exists():
            dst.write_text(template)
        elif dst.read_text() != template:
            dst.write_text(template)
            print(f"  Refreshed CLAUDE.md from the {mode_dir.name} mode template")

    sealed = Path(args.sealed_verify).resolve() if getattr(args, "sealed_verify", None) else None
    if sealed and not sealed.is_file():
        sys.exit(f"Sealed verification file not found: {sealed}")
    if sealed and _is_inside(sealed, project):
        sys.exit(f"Sealed verification file must live outside the project "
                 f"the agent can write to: {sealed}")
    if sealed:
        print(f"  Sealed scoring config: {sealed}")

    state_path = project / ".state" / conf.get("state_file", "tasks.json")
    sim_script, sim_idx = [], 0
    if simulate:
        sim_path = project / ".state" / "sim_script.json"
        if not sim_path.exists():
            sys.exit(f"[SIMULATE] No sim_script.json in {project / '.state'}")
        sim_script = json.loads(sim_path.read_text())

    mode_label = f"{'[SIMULATE] ' if simulate else ''}evaloop v{VERSION}"
    print(f"\n  {mode_label} | {args.mode} | max {args.max_sessions} sessions | ${args.max_budget:.0f} budget")
    print(f"  Project: {project}\n")

    session, sessions_run, no_progress, total_cost = 0, 0, 0, 0.0
    untrusted = 0

    while True:
        session += 1
        if session > args.max_sessions:
            print(f"{lp}[{ts()}] Max sessions ({args.max_sessions}). Stopping.")
            break

        phase = get_phase(state_path, conf, sealed)
        if phase == "done":
            print(f"{lp}[{ts()}] All work complete!")
            break

        # ── OODA Orient ──
        # Observe and Orient are arithmetic on two series and run every round.
        # Decide is a judgement call and stays with the strategist, which is now
        # handed the conclusion rather than left to infer it from raw state.
        orient = divergence_report(state_path, conf, sealed)
        if orient["target"] is not None:
            print(f"{lp}[{ts()}] Orient: {orient['verdict']}")
        if session > 1 and session % args.orient_interval == 0:
            print(f"\n{lp}[{ts()}] == OODA Decide ==")
            _write_orient_brief(project, orient)
            r, sim_idx = await _dispatch(simulate, project, mode_dir, conf,
                                         "orient", f"orient_{session}", 15, sim_script, sim_idx)
            total_cost += r["cost"]
            if r["status"] != "skipped":
                print(f"{lp}[{ts()}] Orient: {r['status']} | ${r['cost']:.4f}")
            phase = get_phase(state_path, conf, sealed)
            if phase == "done":
                print(f"{lp}[{ts()}] Orient determined: complete!")
                break

        prev = progress_count(state_path, conf)

        # ── Tactical Session ──
        fp_before = scoring_fingerprint(project, conf, sealed)
        print(f"\n{lp}[{ts()}] Session #{session} -- {phase} [{args.mode}]")
        r, sim_idx = await _dispatch(simulate, project, mode_dir, conf,
                                     phase, str(session), args.max_turns, sim_script, sim_idx)
        sessions_run += 1
        total_cost += r["cost"]
        print(f"{lp}[{ts()}] #{session}: {r['status']} | "
              f"${r['cost']:.4f} | {r['turns']} turns | total ${total_cost:.4f}")

        if r["complete"]:
            print(f"{lp}[{ts()}] Agent confirmed complete!")
            break

        if total_cost >= args.max_budget:
            print(f"{lp}[{ts()}] Budget cap (${total_cost:.4f} >= ${args.max_budget:.2f}). Stopping.")
            break

        # ── Retry on error ──
        # A retry is another paid call, so it passes the same gate. Checking only
        # before the retry let a run finish over its cap.
        if (r["status"] in ("error", "timeout") and not simulate
                and total_cost < args.max_budget):
            print(f"{lp}[{ts()}] Session failed ({r['status']}), retrying once...")
            await asyncio.sleep(10)
            r, sim_idx = await _dispatch(False, project, mode_dir, conf,
                                         phase, f"{session}_retry", args.max_turns, sim_script, sim_idx)
            total_cost += r["cost"]
            print(f"{lp}[{ts()}] Retry: {r['status']} | ${r['cost']:.4f}")
            if r["complete"]:
                print(f"{lp}[{ts()}] Agent confirmed complete!")
                break
            if total_cost >= args.max_budget:
                print(f"{lp}[{ts()}] Budget cap (${total_cost:.4f} >= "
                      f"${args.max_budget:.2f}). Stopping.")
                break

        # ── State Validation ──
        # The LLM writes state directly; the orchestrator reads it back and
        # says so when it is malformed, rather than acting on nonsense.
        data, read_err = safe_read_state(state_path)
        if read_err and state_path.exists():
            print(f"{lp}[{ts()}] WARNING: unreadable state — {read_err}")
        elif data is not None:
            state_ok, state_errs = validate_state(data, conf)
            if not state_ok:
                print(f"{lp}[{ts()}] WARNING: invalid state after session "
                      f"#{session}: {'; '.join(state_errs[:3])}")

        # ── Orchestrator Verification ──
        if phase == "work":
            tampered = fingerprint_diff(fp_before,
                                        scoring_fingerprint(project, conf, sealed))
            vr = run_verification(
                str(project), conf, session_label=str(session), sealed=sealed,
                tampered=tampered, session_log=_read_session_log(project, session))
            if vr["verify"] and not vr["verify"]["success"]:
                print(f"{lp}[{ts()}] WARNING: Verification failed "
                      f"(exit {vr['verify']['exit_code']})")
            if not vr["integrity"]["trusted"]:
                untrusted += 1

        # ── Circuit Breaker ──
        if phase == "work" and r["status"] not in ("error", "timeout"):
            curr = progress_count(state_path, conf)
            if curr <= prev:
                no_progress += 1
                print(f"{lp}[{ts()}] No progress ({no_progress}/{args.no_progress_max})")
                if no_progress >= args.no_progress_max:
                    print(f"{lp}[{ts()}] Stuck. Stopping.")
                    break
            else:
                no_progress = 0

        # ── Tactical Review ──
        if session >= args.review_interval and session % args.review_interval == 0:
            print(f"\n{lp}[{ts()}] == Tactical Review ==")
            r, sim_idx = await _dispatch(simulate, project, mode_dir, conf,
                                         "review", f"review_{session}", 20, sim_script, sim_idx)
            total_cost += r["cost"]
            print(f"{lp}[{ts()}] Review: {r['status']} | ${r['cost']:.4f}")

        await asyncio.sleep(args.pause)

    print(f"\n{lp}[{ts()}] Done. {args.mode} | {sessions_run} sessions | ${total_cost:.4f}")
    if untrusted:
        print(f"{lp}[{ts()}] {untrusted} session(s) rewrote their own scoring inputs. "
              f"Those metrics are not results.")


# ═══════════════════════════════════════════════════════════════
# Subcommands
# ═══════════════════════════════════════════════════════════════


def cmd_verify(args):
    """Run verification only — no LLM calls."""
    mode_dir = resolve_mode(args.mode)
    conf = load_conf(mode_dir)
    project = Path(args.project_dir).resolve()
    if not project.is_dir():
        sys.exit(f"Project directory not found: {project}")
    sealed = Path(args.sealed_verify).resolve() if getattr(args, "sealed_verify", None) else None
    if sealed and not sealed.is_file():
        sys.exit(f"Sealed verification file not found: {sealed}")
    if sealed and _is_inside(sealed, project):
        sys.exit(f"Sealed verification file must live outside the project: {sealed}")
    print(f"  evaloop v{VERSION} verify | {args.mode}\n  Project: {project}")
    print(f"  Sealed scoring config: {sealed}\n" if sealed
          else "  Scoring config: mode.conf / project .verify (agent-writable)\n")
    result = run_verification(str(project), conf, session_label="manual",
                              sealed=sealed)
    if not result["verify"] and not result["hidden"]:
        print("  No verify_command or hidden_verify_command configured.")
        print(f"  Check modes/{args.mode}/mode.conf or {project}/.verify")
        return
    ok = all(r["success"] for k, r in result.items() if r and k != "integrity")
    sys.exit(0 if ok else 1)


def cmd_status(args):
    """Show project phase and progress."""
    mode_dir = resolve_mode(args.mode)
    conf = load_conf(mode_dir)
    project = Path(args.project_dir).resolve()
    sealed = Path(args.sealed_verify).resolve() if getattr(args, "sealed_verify", None) else None
    state_path = project / ".state" / conf.get("state_file", "tasks.json")
    entry = conf.get("entry_file", "spec.md")
    phase = get_phase(state_path, conf, sealed)
    done = progress_count(state_path, conf)
    prompt_name = conf.get(PHASE_KEYS.get(phase, ""), phase)
    prompt_file = mode_dir / "prompts" / f"{prompt_name}.md"
    print(f"  evaloop v{VERSION} status | {args.mode}")
    print(f"  Project: {project}\n")
    print(f"  Phase:  {phase} | Progress: {done} done")
    print(f"  Entry:  {entry} {'(OK)' if (project / entry).exists() else '(MISSING)'}")
    print(f"  State:  {conf.get('state_file','tasks.json')} {'(OK)' if state_path.exists() else '(new)'}")
    print(f"  Prompt: {prompt_file.name} {'(OK)' if prompt_file.exists() else '(MISSING)'}")


def cmd_list_modes(_args):
    """List available modes."""
    print("Available modes:")
    for d in sorted((SCRIPT_DIR / "modes").iterdir()):
        if d.is_dir():
            c = load_conf(d)
            print(f"  {d.name} -- {c.get('description', '(no description)')}")


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse

    def _mode(p):
        p.add_argument("--mode", default=DEFAULT_MODE,
                       help="A bundled mode name, or a path to a directory "
                            "containing mode.conf")

    top = argparse.ArgumentParser(
        description=f"evaloop v{VERSION} — Verification Harness")
    sub = top.add_subparsers(dest="command")

    def _sealed(p):
        p.add_argument("--sealed-verify", metavar="FILE",
                       help="Verification config outside the project, so the "
                            "agent cannot redefine how it is scored")

    p_v = sub.add_parser("verify", help="Run verification only (no LLM)")
    p_v.add_argument("project_dir"); _mode(p_v); _sealed(p_v)

    p_s = sub.add_parser("status", help="Show phase and progress")
    p_s.add_argument("project_dir"); _mode(p_s); _sealed(p_s)

    sub.add_parser("list-modes", help="List available modes")

    p_l = sub.add_parser("loop", help="Run session loop with verification")
    p_l.add_argument("project_dir"); _mode(p_l); _sealed(p_l)
    for flag, tp, dfl in [("--max-sessions", int, 50), ("--max-turns", int, 50),
                           ("--max-budget", float, 10.0), ("--review-interval", int, 5),
                           ("--orient-interval", int, 10), ("--no-progress-max", int, 3),
                           ("--pause", int, 5)]:
        p_l.add_argument(flag, type=tp, default=dfl)
    p_l.add_argument("--simulate", action="store_true")

    # Backward compat: rewrite argv before parsing
    raw = sys.argv[1:]
    subcommands = {"verify", "status", "list-modes", "loop"}
    if raw and raw[0] not in subcommands and raw[0] not in ("-h", "--help"):
        if "--list-modes" in raw:
            raw = ["list-modes"]
        elif "--dry-run" in raw:
            raw = ["status"] + [a for a in raw if a != "--dry-run"]
        else:
            raw = ["loop"] + raw
    args = top.parse_args(raw)
    if not args.command:
        return top.print_help()

    dispatch = {"verify": cmd_verify, "status": cmd_status, "list-modes": cmd_list_modes}
    if args.command in dispatch:
        return dispatch[args.command](args)
    if args.command == "loop":
        if not getattr(args, "simulate", False) and not _sdk_available:
            try:
                subprocess.run(["claude", "--version"], capture_output=True, check=True)
            except (FileNotFoundError, subprocess.CalledProcessError):
                sys.exit("Neither claude-agent-sdk nor claude CLI found.\n"
                         "  pip install claude-agent-sdk  OR  npm i -g @anthropic-ai/claude-code\n"
                         "  Or use --simulate for testing without either.")
        asyncio.run(engine(args))


if __name__ == "__main__":
    main()
