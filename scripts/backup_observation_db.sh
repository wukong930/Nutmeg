#!/usr/bin/env bash
# 体检 A2 — nightly online backup of the SQLite observation DBs + WAL checkpoint.
#
# Why: before this, the only backup was a one-off manual .bak from 2026-06-04,
# and NOTHING ever checkpointed the -wal files. The observation DB is the
# project's real asset (every bet, prediction and line snapshot) — it deserves
# better than hope.
#
# What it does, per DB:
#   - sqlite3 ".backup" → consistent ONLINE copy (safe under WAL; doesn't lock
#     out the api_server daemon or the crons)
#   - PRAGMA wal_checkpoint(TRUNCATE) → folds the -wal back into the DB so it
#     can't grow unbounded
#   - rotation: keeps the newest $KEEP copies under data/backups/ (gitignored
#     via *.db), deletes older ones
#
# Installed as com.nutmeg.daily_backup (03:30 daily, after the 02:00 settle)
# by setup_local_pipeline.sh. Safe to run by hand any time.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BACKUP_DIR="data/backups"
KEEP=7
TS="$(date +%Y%m%dT%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 2026-08-20 —— 前向 append-only 历史,**结构上无法回溯**(见 ingest_sporttery
# `_append_unmapped_history` docstring)。它落在 logs/ 下,而 logs/ 在 .gitignore 里、
# 本脚本原本只备 *.db ⇒ 这份数据此前**零副本**。丢了就只能从丢的那天重新开始攒。
for f in logs/sporttery_unmapped_history.jsonl; do
  [[ -f "$f" ]] || continue
  cp "$f" "$BACKUP_DIR/$(basename "$f" .jsonl).${TS}.jsonl"
  ls -1t "$BACKUP_DIR/$(basename "$f" .jsonl)."*.jsonl 2>/dev/null | tail -n +$((KEEP + 1)) \
    | xargs -I{} rm -f {}
done

for db in data/v4_observation.db data/score_ev_forward.db; do
  [[ -f "$db" ]] || continue
  base="$(basename "$db" .db)"
  dest="$BACKUP_DIR/${base}.${TS}.db"
  sqlite3 "$db" ".backup '$dest'"
  sqlite3 "$db" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null
  ls -1t "$BACKUP_DIR/${base}."*.db 2>/dev/null | tail -n +$((KEEP + 1)) \
    | while read -r old; do rm -f "$old"; done
  echo "backup ok: $dest ($(du -h "$dest" | cut -f1 | tr -d ' '))"
done
