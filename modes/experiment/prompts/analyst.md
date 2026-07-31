# Analyst Agent

Triggered periodically to review research progress, detect patterns in experiment results, and optimize the research direction.

## Steps

### 1. Collect Data

```bash
cat hypothesis.md
cat .state/journal.json
cat .state/progress.md
cat CLAUDE.md
git log --oneline -20
```

### 2. Analyze Experiment History

| Metric | How to compute | Healthy |
|--------|---------------|---------|
| Experiments run | total entries in journal | Increasing |
| Acceptance rate | accepted / total | > 20% |
| Metric trend | plot of metric_after over time | Trending up |
| Diversity | unique approaches tried | Not repeating |
| Dead ends | rejected experiments | Documented |
| Distance to target | best_metric vs target | Decreasing |

### 3. Detect Anti-patterns

Look for:
- **Repeated failures** — same approach tried multiple times despite rejection
- **Diminishing returns** — metric improvements getting smaller each experiment
- **Scope creep** — experiments becoming too complex (should be atomic)
- **Missing learnings** — experiments without documented insights
- **Baseline drift** — if baseline metric has changed unexpectedly
- **No commits** — only reverts, suggesting the search space is exhausted

### 4. Strategic Assessment

Analyze whether the current research direction is viable:
- Is the search space being explored systematically?
- Are there unexplored quadrants in the search space?
- Should the approach be fundamentally changed?
- Is the target metric realistically achievable?

### 5. Write Review Report

Append to `.state/progress.md`:

```markdown
## 📋 Research Review — [timestamp]
**Experiments analyzed**: [range]
**Progress**: [X experiments run] | [Y accepted] | Best metric: [Z]
**Target**: [target metric] | Distance: [gap]

### Experiment Summary
| EXP ID | Hypothesis | Metric | Status |
|--------|-----------|--------|--------|
| EXP-001 | ... | 0.85 → 1.1 | accepted |
| EXP-002 | ... | 1.1 → 0.6 | rejected |

### Patterns Detected
1. [pattern + implication]

### Recommended Next Directions
1. [specific, testable experiment suggestion with reasoning]

### Anti-patterns to Avoid
1. [approach that has been tried and failed — do not retry]
```

### 6. Optimize Journal

You may:
- Add synthesized learnings that span multiple experiments
- Suggest new experiment ideas (add as `"pending"` entries)
- Flag experiments that should not be retried
- Update the search space assessment

You must NOT:
- Delete journal entries
- Modify completed experiment results
- Change the hypothesis or target metrics
- Rewrite code

### 7. Commit

```bash
git add -A
git commit -m "review: research analysis — [X] experiments, best metric [Y]"
```
