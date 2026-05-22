from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.workflow import (
    ProviderSyncWorkflowOptions,
    SportMonksFixtureAvailabilitySyncTask,
    TheOddsApiEventOddsSyncTask,
)
from nutmeg.providers.workflow_templates import (
    ARCHIVE_PROVIDER_SYNC_WORKFLOW_TEMPLATE_QUERY,
    INSERT_PROVIDER_SYNC_WORKFLOW_TEMPLATE_QUERY,
    LIST_PROVIDER_SYNC_WORKFLOW_TEMPLATES_QUERY,
    UPDATE_PROVIDER_SYNC_WORKFLOW_TEMPLATE_QUERY,
    PostgresProviderSyncWorkflowTemplateRepository,
    preflight_provider_sync_workflow,
)


class FakeProviderSyncWorkflowTemplateDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_PROVIDER_SYNC_WORKFLOW_TEMPLATE_QUERY:
            return _template_row(
                template_name=str(params["template_name"]),
                fixture_sync_json=params["fixture_sync_json"],
                odds_syncs_json=params["odds_syncs_json"],
                availability_syncs_json=params["availability_syncs_json"],
                run_conflict_detection=params["run_conflict_detection"],
                metadata_json=params["metadata_json"],
            )
        if query == UPDATE_PROVIDER_SYNC_WORKFLOW_TEMPLATE_QUERY:
            return _template_row(
                template_name=str(params["template_name"]),
                fixture_sync_json=params["fixture_sync_json"],
                odds_syncs_json=params["odds_syncs_json"],
                availability_syncs_json=params["availability_syncs_json"],
                run_conflict_detection=params["run_conflict_detection"],
                metadata_json=params["metadata_json"],
            )
        if query == ARCHIVE_PROVIDER_SYNC_WORKFLOW_TEMPLATE_QUERY:
            return _template_row(
                metadata_json=params["metadata_json"],
                archived_at=datetime(2026, 5, 8, 5, 0, tzinfo=UTC),
                archived_by=params["archived_by"],
                archive_reason=params["archive_reason"],
            )
        raise AssertionError(f"unexpected query: {query}")

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PROVIDER_SYNC_WORKFLOW_TEMPLATES_QUERY:
            return [_template_row()]
        raise AssertionError(f"unexpected query: {query}")


def test_provider_sync_workflow_preflight_requires_explicit_task() -> None:
    result = preflight_provider_sync_workflow(ProviderSyncWorkflowOptions())

    assert result.valid is False
    assert result.error_count == 1
    assert result.issues[0].code == "provider_sync_task_required"


def test_provider_sync_workflow_preflight_warns_on_partial_availability_mapping() -> None:
    result = preflight_provider_sync_workflow(
        ProviderSyncWorkflowOptions(
            odds_syncs=(
                TheOddsApiEventOddsSyncTask(
                    sport_key="soccer_epl",
                    provider_event_id="event-1",
                    canonical_fixture_id="fd_fixture_1",
                ),
            ),
            availability_syncs=(
                SportMonksFixtureAvailabilitySyncTask(
                    provider_fixture_id="sm_fixture_1",
                    canonical_fixture_id="fd_fixture_1",
                    team_mappings={"57": "fd_team_57"},
                ),
            ),
            run_conflict_detection=True,
        )
    )

    assert result.valid is True
    assert result.task_count == 2
    assert result.warning_count == 1
    assert result.info_count == 1
    assert result.canonical_fixture_ids == ["fd_fixture_1"]
    assert {
        issue.code for issue in result.issues
    } == {
        "availability_team_mapping_partial",
        "canonical_fixture_ids_deduplicated",
    }


def test_provider_sync_workflow_template_repository_saves_and_lists_templates() -> None:
    database = FakeProviderSyncWorkflowTemplateDatabase()
    repository = PostgresProviderSyncWorkflowTemplateRepository(database)

    saved = repository.save_template(
        template_name="EPL fixture odds",
        description="dry-run smoke",
        dry_run=True,
        fixture_sync={"provider_competition_id": "PL", "season": "2025"},
        odds_syncs=[
            {
                "sport_key": "soccer_epl",
                "provider_event_id": "event-1",
                "canonical_fixture_id": "fd_fixture_1",
            }
        ],
        availability_syncs=[],
        run_conflict_detection=True,
        conflict_observation_lookback_hours=168,
        conflict_limit=1000,
        created_by="admin_api",
        metadata_json={"source": "unit_test"},
    )
    records = repository.list_latest(limit=5)

    assert saved.provider_sync_workflow_template_id == 701
    assert saved.template_name == "EPL fixture odds"
    assert saved.fixture_sync == {"provider_competition_id": "PL", "season": "2025"}
    assert saved.odds_syncs[0]["canonical_fixture_id"] == "fd_fixture_1"
    assert saved.metadata_json == {"source": "unit_test"}
    assert records[0].provider_sync_workflow_template_id == 701
    assert database.fetch_all_calls == [
        (LIST_PROVIDER_SYNC_WORKFLOW_TEMPLATES_QUERY, {"limit": 5})
    ]


def test_provider_sync_workflow_template_repository_updates_and_archives() -> None:
    database = FakeProviderSyncWorkflowTemplateDatabase()
    repository = PostgresProviderSyncWorkflowTemplateRepository(database)

    updated = repository.update_template(
        provider_sync_workflow_template_id=701,
        template_name="EPL updated odds",
        description="updated smoke",
        dry_run=True,
        fixture_sync={"provider_competition_id": "PL", "season": "2026"},
        odds_syncs=[],
        availability_syncs=[],
        run_conflict_detection=False,
        conflict_observation_lookback_hours=24,
        conflict_limit=50,
        updated_by="admin_api",
        metadata_json={"source": "unit_test"},
    )
    archived = repository.archive_template(
        provider_sync_workflow_template_id=701,
        archived_by="admin_api",
        archive_reason="superseded",
        metadata_json={"source": "unit_test"},
    )

    assert updated is not None
    assert updated.template_name == "EPL updated odds"
    assert updated.fixture_sync == {"provider_competition_id": "PL", "season": "2026"}
    assert archived is not None
    assert archived.archived_at == datetime(2026, 5, 8, 5, 0, tzinfo=UTC)
    assert archived.archived_by == "admin_api"
    assert archived.archive_reason == "superseded"


def _template_row(
    *,
    template_name: str = "EPL fixture odds",
    fixture_sync_json: object = '{"provider_competition_id":"PL","season":"2025"}',
    odds_syncs_json: object = (
        '[{"sport_key":"soccer_epl","provider_event_id":"event-1",'
        '"canonical_fixture_id":"fd_fixture_1"}]'
    ),
    availability_syncs_json: object = "[]",
    run_conflict_detection: object = True,
    metadata_json: object = '{"source":"unit_test"}',
    archived_at: object = None,
    archived_by: object = None,
    archive_reason: object = None,
) -> DatabaseRow:
    return {
        "provider_sync_workflow_template_id": 701,
        "template_name": template_name,
        "description": "dry-run smoke",
        "dry_run": True,
        "fixture_sync_json": fixture_sync_json,
        "odds_syncs_json": odds_syncs_json,
        "availability_syncs_json": availability_syncs_json,
        "run_conflict_detection": run_conflict_detection,
        "conflict_observation_lookback_hours": 168,
        "conflict_limit": 1000,
        "created_by": "admin_api",
        "created_at": datetime(2026, 5, 8, 4, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 5, 8, 4, 1, tzinfo=UTC),
        "archived_at": archived_at,
        "archived_by": archived_by,
        "archive_reason": archive_reason,
        "metadata_json": metadata_json,
    }
