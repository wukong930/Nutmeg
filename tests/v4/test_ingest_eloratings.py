"""V14 — eloratings.net World.tsv → snapshot parser.

Guards the WC model's national-Elo source: this is the file load_elo_snapshot
reads (wc_predict / /predictions/wc). The parser must pull the right columns out
of the tab-separated World.tsv and drop junk rows robustly.
"""
from __future__ import annotations

from nutmeg.v4.cli.ingest_eloratings import parse_world_tsv

# Real World.tsv shape: rank, (intra-rank), 2-letter code, current Elo,
# (rank-1y), Elo-1y-ago, then trailing form/goal columns we ignore.
_SAMPLE = (
    "1\t1\tES\t2155\t1\t2189\t7\t1946\t19\t1805\t0\t-17\n"
    "2\t2\tAR\t2114\t1\t2172\t5\t1987\t26\t1751\t0\t+1\n"
    "\n"                                      # blank line → skipped
    "bad\trow\tXX\tnotanumber\t1\t2000\n"     # unparseable → skipped
)


def test_parses_relevant_columns():
    df = parse_world_tsv(_SAMPLE)
    assert list(df.columns) == ["rank", "country_code", "elo", "elo_1y_ago"]
    assert len(df) == 2                       # blank + bad rows dropped
    es = df[df.country_code == "ES"].iloc[0]
    assert es["rank"] == 1
    assert es["elo"] == 2155.0
    assert es["elo_1y_ago"] == 2189.0


def test_empty_input_yields_empty_typed_frame():
    df = parse_world_tsv("")
    assert len(df) == 0
    assert list(df.columns) == ["rank", "country_code", "elo", "elo_1y_ago"]
