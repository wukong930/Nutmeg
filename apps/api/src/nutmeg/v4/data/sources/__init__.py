"""External data-source adapters added in V5 W3.

Each module exposes:
- ``fetch_*`` : pull from upstream (HTTP/scraping) → raw DataFrame
- ``load_*``  : read cached parquet from data/external/<source>/
- ``ingest_*``: pull + cache + return canonicalized DataFrame ready to join
"""
