# V5 W10 — Experiment tracking + weekly CI

_The infrastructure to see, in git history, how Nutmeg's prediction quality
evolves week over week — without ad-hoc spreadsheets or manual bench runs._

## What's new

### nutmeg.v4.eval.experiment_tracker

One small module that owns the on-disk layout for tracked runs:

```
data/v4_model/experiments/
  <sha7>_<utc-ts>/
    metadata.json    # git sha, branch, timestamp, cfg, model_type
    pooled.json      # the pooled summary from walk_forward
    card.md          # the human-readable bench card (optional)
```

API surface:

- `track_experiment(result, ...)` — write a new experiment dir from a
  `run_walk_forward` result. Captures current git SHA + branch automatically.
- `list_experiments(...)` — enumerate all experiments in chronological order
  (directory names sort lexically = chronologically because timestamps are
  encoded as `YYYYmmddTHHMMSSZ`).
- `diff_experiments(a, b, metric=...)` — per-slot deltas for log_loss / ECE /
  hit_rate. Skips slots absent in both; returns `delta=None` when only one
  side has the slot (e.g., one run had `--with-ensemble` and the other didn't).
- `format_diff_card(a, b)` — Markdown comparison card.

### `nutmeg-bench --track`

The single-season bench now optionally writes its result + card into the
experiments dir:

```bash
nutmeg-bench --with-ensemble --track --output docs/v4_baseline_card.md
```

Tracking is opt-in so daily exploratory runs don't pollute the experiments
directory. Weekly cron always uses `--track`.

### `nutmeg-experiment-diff`

```bash
# List all tracked experiments
nutmeg-experiment-diff --list

# Diff the latest two
nutmeg-experiment-diff

# Diff specific SHAs (prefix lookup)
nutmeg-experiment-diff --a 2c05708 --b abc1234 \
    --out docs/weekly/diff-2025-W18.md
```

Exit code is 0 in all cases; the analyst inspects the diff and decides
what to do.

### GH Actions weekly cron

`.github/workflows/weekly-bench.yml` — every Sunday at 02:00 UTC the
workflow:

1. Checks out main
2. Installs Python 3.13 + libgomp1 + the project via uv
3. Runs `nutmeg-bench --with-ensemble --track --output docs/weekly/<YYYY-WW>-bench.md`
4. Runs `nutmeg-bench-multi --with-ensemble --output docs/weekly/<YYYY-WW>-multi.md`
5. Runs `nutmeg-experiment-diff --out docs/weekly/<YYYY-WW>-diff.md` (skipped
   on the first run when only one experiment exists)
6. Commits `docs/weekly/*.md` + refreshed `v4_baseline_card.md` /
   `v4_multi_season_card.md` back to main with `[skip ci]` in the message
   so the chore commit doesn't trigger downstream CI

Authored as the GitHub Actions bot. Uses the workflow-level `contents: write`
permission so the default `GITHUB_TOKEN` can push.

Manual trigger available via the Actions tab (`workflow_dispatch`).

### What stays out of git

`data/v4_model/experiments/` itself is in `.gitignore` (W1 plan §code thinning) —
the artifact-level JSON is **per-machine reproducible** from the same source
DataFrame, so committing it just bloats git history. What we DO commit:

- `docs/weekly/<YYYY-WW>-{bench,multi,diff}.md` — the weekly snapshots,
  which ARE worth keeping in git
- `docs/v4_baseline_card.md` / `docs/v4_multi_season_card.md` — refreshed
  on every weekly run

## Why this matters

Until W10, regression detection was manual: someone had to remember to
re-run bench after a refactor and eyeball the cards. With the weekly cron:

- Any silent regression introduced by a future feature lands in a
  `*-diff.md` card the next Sunday
- Trends across V5 sprints (W4 −0.0016, W6 CatBoost −0.0033, W5/W9 rolled
  back, etc.) become a single grep across `docs/weekly/`
- The combination of W8 live-vs-backtest cron + W10 experiment-diff cron
  gives both the "is the model still good?" signal and the "is real
  betting matching the model?" signal in the same weekly cadence

## Tests

16 unit tests in `tests/v4/test_experiment_tracker.py`:

- Git helpers return non-empty strings (real SHA in our repo, fallback otherwise)
- Track creates the right files; metadata has SHA + timestamp + cfg
- Card.md optional; directory name uses `<sha>_<ts>` format
- List handles empty dir, nonexistent dir, corrupt JSON gracefully
- Chronological ordering preserved (sleep + retrack proves timestamps differ)
- Diff signs deltas correctly (improvement = negative)
- Slots absent in one side yield `delta=None` (no crash)
- Diff supports log_loss / ECE / hit_rate metrics
- Card markdown contains all expected section headers

Total V4 suite: **271/271 passing**.

## Operations

For someone running Nutmeg locally:

```bash
# Whenever you change features/models, capture a tracked run
nutmeg-bench --with-ensemble --track

# Anytime — diff against the last good run
nutmeg-experiment-diff
```

For CI: nothing to do — the Sunday cron fires automatically once this
commit lands on `main`.
