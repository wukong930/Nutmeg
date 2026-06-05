"""V4 observation layer: persist recommendations + outcomes; compute ROI."""
from nutmeg.v4.observation.recorder import record_manual_bet, record_session
from nutmeg.v4.observation.store import (
    SCHEMA_VERSION,
    get_outcome,
    init_db,
    insert_settlement,
    list_unsettled_recommendations,
    open_db,
    upsert_outcome,
)
from nutmeg.v4.observation.settlement import settle_unsettled

__all__ = [
    "SCHEMA_VERSION",
    "record_session",
    "record_manual_bet",
    "init_db",
    "open_db",
    "upsert_outcome",
    "get_outcome",
    "insert_settlement",
    "list_unsettled_recommendations",
    "settle_unsettled",
]
