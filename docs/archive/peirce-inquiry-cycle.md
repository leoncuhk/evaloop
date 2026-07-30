# Why Three Roles: Peirce's Inquiry Cycle as Architectural Foundation

> **Archived.** This essay was written for the three-mode architecture
> (engineer / researcher / auditor) that shipped through v6. evaloop 7.0 ships a
> single loop, scored by a metric. The argument below still holds — it is why the
> loop is shaped the way it is — but its inventory of modes, file names and
> commands describes a version that no longer exists. For what evaloop is now,
> see the [README](../../README.md) and the [design rationale](../design-rationale.md).

This document explains why every mode in evaloop has exactly three core roles — and why this is not a design choice but a logical necessity.

## Peirce's Theory of Inquiry

Charles Sanders Peirce identified three irreducible stages of reasoning through which all reliable knowledge must pass:

| Stage | Reasoning type | Operation | Direction |
|-------|---------------|-----------|-----------|
| 1 | **Abduction** | From surprising facts, generate a hypothesis that would explain them | Facts → Theory |
| 2 | **Deduction** | From the hypothesis, derive specific testable predictions | Theory → Predictions |
| 3 | **Induction** | Test predictions against new observations, confirm or refute | Predictions → New facts |

The key property: **all three are required.** Abduction without deduction produces untested speculation. Deduction without induction produces unverified theory. Induction without abduction has no hypothesis to test. Remove any one stage and the inquiry process breaks.

## The Three Roles Map to Peirce's Three Stages

Each mode in evaloop has three core roles. The mapping is natural, not forced:

| Peirce stage | Engineer | Researcher | Auditor |
|-------------|----------|------------|---------|
| **Abduction** (generate hypothesis) | Initializer — "If I decompose this spec into these 15 tasks, the project will be complete" | Theorizer — "Momentum indicators may work better than lagging indicators" | Scanner — "This `eval(user_input)` pattern may be a code injection vulnerability" |
| **Deduction** (derive predictions) | Developer — "From task T3, I should create this specific API endpoint" | Executor — "From this hypothesis, I should change parameter X and expect metric Y" | Auditor — "If standard SEC-03 prohibits eval(), and this code uses eval(), then this is a violation" |
| **Induction** (test predictions) | Reviewer — "After 10 sessions, the task decomposition is working / not working" | Analyst — "After 6 experiments, momentum-confirming indicators outperform mean-reversion ones" | Reporter — "After auditing all findings, the codebase has 3 verified critical issues" |

This is why the system needs exactly three roles per mode — not two, not four. It is the minimum complete structure for reliable knowledge growth.

## The Strategist Is Not a Fourth Stage

The Strategist (v4.0) does not add a fourth Peirce stage. It operates *between* cycles.

In Peirce's framework, one round of abduction → deduction → induction produces new facts (t₀'). If those facts are **surprising** (they contradict the current theory), a new cycle begins. If they are **expected**, the current theory is confirmed.

The Strategist is the **surprise detector** — it decides whether to:

- **CONTINUE** — t₀' is not surprising; the current theory holds; keep executing
- **PIVOT** — t₀' is surprising; the theory needs revision; trigger new abduction
- **COMPLETE** — t₀' confirms the theory sufficiently; inquiry can terminate

This maps to Peirce's concept of the "irritation of doubt" that triggers inquiry. The Strategist formalizes the transition between inquiry cycles, not a new stage within one.

## Cross-Mode Composition (Not Yet Implemented)

The three modes themselves could form a macro-level Peirce cycle:

```
Auditor (abduction) — examines a system, discovers surprising problems
    ↓
Engineer (deduction) — from the audit findings, derives and implements fixes
    ↓
Researcher (induction) — validates whether the fixes actually work
    ↓
Back to Auditor — "does the fixed system have new problems?"
```

This inter-mode orchestration (Audit → Engineer → Research → Audit) is a legitimate Peirce cycle at the project lifecycle level. It is not currently implemented — each mode runs independently. Implementing it would require a meta-orchestrator that chains mode outputs as inputs to the next mode.

## Implications for Mode Design

When creating a new mode, the Peirce structure provides a design constraint:

1. The **Init role** must perform abduction — face uncertainty and generate a hypothesis
2. The **Work role** must perform deduction — derive concrete actions from the hypothesis
3. The **Review role** must perform induction — test whether the actions confirmed the hypothesis

If any role is missing, the mode's inquiry process is incomplete:
- Without Init (abduction): the mode has no hypothesis — it acts randomly
- Without Work (deduction): the mode has ideas but never tests them
- Without Review (induction): the mode acts but never learns

This is not a style guideline. It is a logical completeness requirement.

## References

- Peirce, C.S. "Deduction, Induction, and Hypothesis" (1878)
- Peirce, C.S. "A Theory of Probable Inference" (1883)
- Fann, K.T. *Peirce's Theory of Abduction* (1970) — systematic reconstruction of Peirce's inquiry theory
