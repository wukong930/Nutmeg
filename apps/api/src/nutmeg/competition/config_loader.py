from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from nutmeg.domain.competition import CompetitionConfig


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"competition config must be a YAML mapping: {path}")
    return payload


def load_competition_config(path: str | Path) -> CompetitionConfig:
    config_path = Path(path)
    return CompetitionConfig.model_validate(_read_yaml(config_path))


def load_competition_configs(directory: str | Path) -> list[CompetitionConfig]:
    config_dir = Path(directory)
    if not config_dir.exists():
        return []
    configs = [load_competition_config(path) for path in sorted(config_dir.glob("*.yaml"))]
    seen: set[str] = set()
    for config in configs:
        if config.competition_id in seen:
            raise ValueError(f"duplicate competition_id: {config.competition_id}")
        seen.add(config.competition_id)
    return configs
