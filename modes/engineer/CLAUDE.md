# auto-dev-agentos — Agent Workflow (Engineer Mode)

> Auto-read by Claude Code. Defines rules for every agent session.

## Core Principle

You are one session in a long-running autonomous pipeline. You have **NO memory** of previous sessions. All state lives in files. Each session = fresh context.

## State Files

| File | Purpose |
|------|---------|
| `spec.md` | Project specification (read-only, human-written) |
| `.state/tasks.json` | Task queue with status, steps, acceptance_criteria, and verify_command |
| `.state/progress.md` | Append-only work log |
| `.state/features.json` | Feature checklist with `passes` boolean |
| `.state/learnings.md` | Accumulated project knowledge — read first, append last |

## Workflow (every session)

### 1. Orient — Read state first (MANDATORY)

```bash
cat spec.md
cat .state/tasks.json
tail -50 .state/progress.md
cat .state/learnings.md 2>/dev/null || true
git log --oneline -10 2>/dev/null || true
```

### 2. Act — Do ONE task only

- Pick the first `"status": "pending"` task
- Set it to `"in_progress"` immediately
- Implement it following the task's `steps` array
- Keep changes small and focused

### 3. Verify — Mandatory feedback loops

**Run ALL checks before committing. Do NOT skip any.**

```bash
# Build / typecheck
npm run build 2>&1 || npx tsc --noEmit 2>&1 || true
# Tests
npm test 2>&1 || true
# Lint
npm run lint 2>&1 || true
```

If any check fails, **fix the issue first**. Do not commit broken code.

### 4. Record — Update state files

- Set task status to `"done"` in `.state/tasks.json`
- Append to `.state/progress.md`:
  ```
  ## Session [N] — [timestamp]
  **Task**: T[id] — [title]
  **Done**: [what was accomplished]
  **Verified**: [which checks passed]
  **Issues**: [problems, or "none"]
  **Next**: [what next session should do]
  ```
- Update `.state/features.json` if a feature now passes

### 5. Update Learnings

Append any discoveries to `.state/learnings.md` (create it if absent):
- Patterns discovered ("this project uses X for Y")
- Gotchas ("when changing X, must also update Y")
- Useful context ("the main API routes are in server.js")

Write them there, **not** into this file: this `CLAUDE.md` is a copy of the mode
template that the engine drops into the project, so it is not version-controlled
and anything you append to it is lost on the next run.

### 6. Commit

```bash
git add -A
git commit -m "feat(T[id]): [task title] — verified"
```

### 7. Stop

After ONE task, stop. The orchestrator starts a new session with fresh context.

## Rules

1. **One task per session** — Never attempt multiple tasks
2. **Verify before done** — Untested code must not be marked done
3. **Never delete tasks** — Only change status forward
4. **Keep code working** — Every commit = buildable state
5. **Respect existing patterns** — Follow conventions already in the project
6. **If stuck** — Write `BLOCKED:` in progress.md and stop immediately
7. **Read past learnings** — check `.state/learnings.md` before starting a task
