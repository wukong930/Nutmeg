# docs/archive/ — per-week writeups from shipped versions

_Added at post-v9 P1#30. The root `docs/` was at 64 files; moving
all per-week writeups here cuts it to 38 (~46% drop) while keeping
every doc that's still actively referenced (HANDOFFs, ROADMAPs,
retrospectives, post-v9 P1 chain, current cards & guides) at root._

## What lives here

| Dir | Contents | Count |
|---|---|---:|
| `v5/` | V5 W5-W11 per-week writeups (ablation, catboost migration, observation loop, etc.) | 7 |
| `v6/` | V6 W5-W11 per-week writeups (lineup work, dashboard, cup data) | 7 |
| `v7/` | V7 W1-W3 + W6-W8 per-week writeups (live odds + cup data) | 6 |
| `v8/` | V8 W1-W4 + W6-W7 per-week writeups (cup union + national-team Elo) | 6 |
| `v9/` | V9 W3-W6 per-week writeups (recorder + CI cache + ECE) | 6 |
| **Total** | | **32** |

## What does NOT live here (stays at `docs/` root)

- `V<N>_HANDOFF.md` — single source of truth per version (V4-V9)
- `V<N>_ROADMAP.md` — version plan (V5-V9)
- `V10_HANDOFF_TEMPLATE.md` + `V10_ROADMAP_DRAFT.md` — V10 starter kit
- `v<N>_retrospective.md` (or `v6_w12_retrospective.md`) — version retros
- `post_v9_p1_*.md` — current P1 patch chain (22 files)
- `post_v9_p1_index.md` — chain index, primary entry point for "where are we now"
- `post_v8_p1_patches.md` — V9 prologue (kept for continuity)
- `v4_baseline_card.md` + `v4_multi_season_card.md` — current bench cards
- `v5_w12_paid_data_decision.md` — current subscription decision (still relevant)
- `v5_external_data_coverage.md` — current data source registry
- `local_deployment_guide.md` — current ops guide
- `weekly/` — auto-generated weekly cards from `weekly-bench.yml`
- `legacy/` — older archive (V2/V3 era pre-dating V5 git history)

## Linking conventions

When a root doc cites an archived writeup:
```markdown
See [v6_w7_lineup_production.md](archive/v6/v6_w7_lineup_production.md)
```

When an archived doc cites another archived writeup in a different
version:
```markdown
See [v6_w5_lineup_ablation.md](../v6/v6_w5_lineup_ablation.md)
```

Intra-version archive links can stay bare (same directory):
```markdown
See [v5_w5_ablation.md](v5_w5_ablation.md)
```

## When to add to archive

When a version `V<N+1>` ships:
- The retrospective `v<N+1>_retrospective.md` stays at root
  (because the next handoff cycle references it)
- Per-week writeups `v<N+1>_w*.md` move here under
  `docs/archive/v<N+1>/` once V<N+2>_ROADMAP is drafted
  (they're "shipped history" by then)
- Update root docs that link to the moved writeups (sed pattern
  in P1#30 commit serves as a template)

## Git history

All moves used `git mv` to preserve per-file history. From a
file in archive:
```bash
git log --follow archive/v6/v6_w7_lineup_production.md
```
shows the pre-move commits too.
