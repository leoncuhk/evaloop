# The verification layer

How evaloop scores a project, what it does to keep that
score meaningful, and where each control stops. The README summarises this; the
detail is here.

This is the core value of the project. After each work session:

### 1. Independent `verify_command`

Runs a command that the orchestrator controls, not the LLM. Configured in `mode.conf` or overridden per-project with a `.verify` file:

```ini
# modes/experiment/mode.conf
verify_command = python run_backtest.py --split train

# examples/qlib-quant/.verify (project-level override)
verify_command = python qlib_backtest.py --split train
hidden_verify_command = python qlib_backtest.py --split test
```

### 2. Hidden out-of-sample validation

`hidden_verify_command` runs on data the LLM never sees. The metric is written to `.state/hidden_metrics.json` and is never fed back to the LLM by the orchestrator.

Why it matters, empirically: research agents on [MLE-bench](https://arxiv.org/html/2507.02554) show a persistent **9–13% validation/test generalization gap**. An agent optimising a visible metric will find the gap. A number the agent never sees is the only one that measures whether the work generalizes.

### 3. Scoring integrity

Not surfacing a metric is not the same as an agent being unable to obtain it. Everything under the project directory is writable by the agent — including `.verify` and the scripts it names. A live session in [`examples/goal-vs-loop/logs/session_4.log`](examples/goal-vs-loop/logs/session_4.log) ran the hidden split itself and reported `hidden test split = 1.5233` in its own summary.

Three controls, in order of strength:

**Seal the scoring definition** — `--sealed-verify FILE` reads the verification config from a path outside the project. It outranks the project's `.verify`, so an agent that rewrites `.verify` changes nothing. The harness refuses a sealed file that resolves inside the project. **The held-out record is written beside it**, in the operator's own space — through 7.2 it went to `<project>/.state/hidden_metrics.json`, the directory every mode instructs the agent to read first, which made "never fed back" untrue by one `cat`. Without a sealed config there is nowhere else to put it, and the run says so.

```bash
# operator-owned, outside the repo the agent works in
echo 'hidden_verify_command=python3 run_backtest.py --split test' > ~/scoring/proj.conf
python run.py loop ./proj --sealed-verify ~/scoring/proj.conf
```

**Fingerprint what does the scoring** — before each session the orchestrator hashes `.verify` and every in-project file the verification commands invoke, then re-hashes afterwards. A change means the session rewrote its own scoring, and the metric is reported as untrusted rather than as a result:

```
verify: PASS (exit 0) | metric: 99.0
TAMPERED: scoring inputs changed during the session: score.py
The metric above was produced by definitions this session rewrote. Do not treat it as a result.
```

**Detect leaks after the fact** — each session's transcript is scanned for the hidden invocation and for the hidden metric's own value. Hits are recorded with the metric, so a contaminated number is never silently mixed with clean ones:

```json
[
  {"session": "1", "metric": 0.84, "timestamp": "...", "sealed": true},
  {"session": "3", "metric": 1.5233, "timestamp": "...", "sealed": false,
   "leaks": ["hidden metric 1.5233 appears in transcript"]}
]
```

This is the architecture [sandbox-policy research](https://github.com/islo-labs/reward-hack-bench) converges on — scoring runs where the agent does not control it, and the verdict is computed outside the agent's reach. Detection is the weakest of the three and is honest about it: it marks a metric contaminated, it never certifies one clean. For adversarial settings, seal the config *and* run the hidden command against data on a filesystem the agent cannot read.

### 4. The held-out metric decides when you are done

A held-out number that nothing reads is decoration. Until 7.2 that is what this
one was: written to `.state/hidden_metrics.json`, consulted by nothing. The loop
declared victory when `best_metric` — the figure the agent had spent every
session raising — reached its target.

![The exit condition: a session ends, the visible metric is checked against the target, and only if it clears does a second amber decision ask whether the held-out metric clears it too; no there means not done because the gains did not transfer. The second question is the one the agent never sees](assets/evaloop-held-out-gate.png)

The exit condition now asks both:

```
Orient: visible 3.6430 meets the target and held-out -0.0297 does not:
        the gains have not transferred
```

Those are the real figures from [`examples/qlib-quant`](examples/qlib-quant/.state/history/hidden-oos-2026-07-30.md).
Under the old rule that run reports success. Under this one it keeps going and
says why.

Three properties make the gate safe to trust:

**It can only withhold completion, never cause it.** A high held-out figure
never finishes a run on its own. Selecting on the held-out segment is the move
this project exists to prevent, so the gate refuses false victories without
steering the search.

**It reads the latest clean record, not the best one.** Taking the maximum would
be choosing a configuration by its held-out score. The latest record describes
the tree as it stands, which is what would ship.

**A discredited measurement is not evidence.** Records from sessions that
rewrote their own scoring, or that were caught quoting the held-out number, are
dropped — and if every record is discredited the gate stays shut, so corrupting
the record is not a way through.

Projects with no `hidden_verify_command` behave exactly as before.

#### Orient, computed rather than asked

The line above is printed every session and costs nothing: it is arithmetic over
two series already on disk. Boyd's Orient phase is the one that updates your
model of the situation, and in a metric-driven loop the model most likely to be
stale is *the visible metric still tracks what I want*.

Three candidate rules were tested against the qlib figures. Direction agreement
(both series rising) says continue — both did rise. Gap convergence says
improving — the gap narrowed from 4.09 to 3.67. Only *does the held-out figure
clear the target* catches it. The two cleverer rules were discarded because real
data rejected them.

The strategist prompt still runs on `--orient-interval`, but it is now handed
`.state/orient.md` — the conclusion — rather than left to infer it from raw
state. Orient is arithmetic; Decide is judgement.

### 5. What this runs on your machine

`run.py loop` starts an agent **with permissions bypassed** — `bypassPermissions`
on the SDK path, `--dangerously-skip-permissions` on the CLI path. That is
deliberate: a loop that stops for approval every session is not autonomous. It
also means the agent executes shell commands in your project directory without
asking, for as many sessions as your limits allow.

There is a `PreToolUse` hook that refuses a short list of obviously destructive
commands (`rm -rf /`, `git push --force`, `DROP TABLE`, …). It matches
substrings, so it is a guard against an agent's accident, **not a security
boundary against an adversarial one**. Measured against its own list:

| Command | Result |
|---|---|
| `rm -rf /` | blocked |
| `cd / && rm -rf .` | blocked |
| `rm -fr /` | **allowed** |
| `rm  -rf /` (two spaces) | **allowed** |
| `python3 -c "import shutil; shutil.rmtree('/')"` | **allowed** |

Run the loop in a container, a VM, or a throwaway working copy — anywhere you
would be willing to let an unattended process run `rm`. `verify` and `status`
make no LLM calls and start no agent, so they are safe to run anywhere.

The Orient phase is the one exception: it runs with `disallowed_tools=["Bash",
"Write"]` and a hook restricting `Edit` to `.state/`, because a strategist that
can modify code is a strategist that can break the build between sessions.

### 6. Budget & stuck controls

- **Circuit breaker**: stops after N consecutive sessions with no progress
- **Budget cap**: `--max-budget` prevents runaway spending
- **Retry**: automatic single retry on error/timeout (don't waste session slots)
