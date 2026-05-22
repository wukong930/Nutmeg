"""Data ingestion and storage."""
from nutmeg.v4.data.schema import MATCH_COLUMNS, Match
from nutmeg.v4.data.ingest import load_all_matches, load_football_data_csv

__all__ = ["MATCH_COLUMNS", "Match", "load_all_matches", "load_football_data_csv"]
