# evaloop — Agent Workflow (Researcher Mode)

> Auto-read by Claude Code. Defines rules for every agent session.

## Core Principle

You are one session in an **iterative research pipeline**. You have **NO memory** of previous sessions. All state lives in files. Each session = fresh context. **Failure is expected** — protect the baseline, accumulate learnings.

## State Files

| File | Purpose |
|------|---------|
| `hypothesis.md` | Research goals, baseline, search space, target metrics (read-only) |
| `.state/journal.json` | Experiment log — every attempt recorded with metrics + learnings |
| `.state/progress.md` | Append-only session log |
| `.state/best_metric.txt` | Current best metric value (single number) |
| `.state/learnings.md` | Accumulated cross-experiment knowledge — read first, append last |

## Key Differences from Engineer Mode

1. **Failure is normal** — revert bad experiments, record learnings, try again
2. **Metrics decide** — code quality is secondary; only metric improvement matters
3. **Never lose the baseline** — always be able to revert to a working state
4. **Accumulate wisdom** — every failed experiment teaches something for the next

## Workflow (every session)

### 1. Orient — Read state first (MANDATORY)

```bash
cat hypothesis.md
cat .state/journal.json
tail -50 .state/progress.md
cat .state/learnings.md 2>/dev/null || true
cat CLAUDE.md
git log --oneline -10 2>/dev/null || true
```

### 2. Act — Follow your assigned role

Your role is determined by the orchestrator (theorizer / executor / analyst).
Follow the instructions in your specific prompt file.

### 3. Record — Update state files

- Update `.state/journal.json` with experiment results
- Append to `.state/progress.md`:
  ```
  ## Session [N] — [timestamp]
  **Role**: [Theorizer|Executor|Analyst]
  **Experiment**: EXP-[id] — [hypothesis]
  **Result**: [metric value or "error"]
  **Decision**: [accepted|rejected|reverted]
  **Learnings**: [what was discovered]
  **Next**: [next direction to explore]
  ```

### 4. Update Learnings

Append **every** discovery to `.state/learnings.md` (create it if absent).
These are critical for future sessions — they prevent repeating failed experiments.

Write them there, **not** into this file: this `CLAUDE.md` is a copy of the mode
template that the engine drops into the project, so it is not version-controlled
and anything you append to it is lost on the next run.

### 5. Commit (only on improvement)

```bash
# Only commit if the experiment improved metrics
git add -A
git commit -m "exp(EXP-[id]): [brief hypothesis] — metric: [value]"
```

If the experiment failed, **revert** instead:
```bash
git checkout -- .
```

### 6. Stop

After ONE experiment cycle, stop. The orchestrator starts a new session.

## Rules

1. **One experiment per session** — never run multiple experiments
2. **Metrics are truth** — only metric improvement justifies a commit
3. **Revert on regression** — if metric drops below baseline, revert immediately
4. **Record everything** — even failed experiments have value as learnings
5. **Never delete journal entries** — the history of failures IS the knowledge
6. **If stuck** — write `BLOCKED:` in progress.md and stop immediately
7. **Read past learnings** — check `.state/learnings.md` and journal.json before proposing
8. **Never delete `.state/history/`** — archived runs are the record that this mode was executed
