from __future__ import annotations

from pathlib import Path

from nutmeg.competition import load_competition_configs


def test_competition_configs_load_from_yaml() -> None:
    configs = load_competition_configs(Path("configs/competitions"))
    competition_ids = {config.competition_id for config in configs}

    assert "EPL" in competition_ids
    assert "JPN_J1" in competition_ids
    assert {
        "ENG_CHAMPIONSHIP",
        "ESP_SEGUNDA_DIVISION",
        "FIFA_WORLD_CUP",
        "FRA_LIGUE_2",
        "GER_2_BUNDESLIGA",
        "ITA_SERIE_B",
        "JPN_J2",
        "KOR_K_LEAGUE_1",
        "NED_EREDIVISIE",
        "PRT_PRIMEIRA_LIGA",
        "UEFA_CHAMPIONS_LEAGUE",
        "UEFA_CONFERENCE_LEAGUE",
        "UEFA_EUROPA",
    }.issubset(competition_ids)
    assert all(config.provider_primary for config in configs)
    assert all(config.model_status in {"beta", "experimental"} for config in configs)
