from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime


def request_json(
    base_url: str,
    path: str,
    *,
    admin_token: str | None = None,
    payload: Mapping[str, object] | None = None,
    timeout_seconds: int = 120,
    connect_timeout_seconds: int = 15,
    redactions: Sequence[str] = (),
) -> dict[str, object]:
    response, status = request_json_with_status(
        base_url,
        path,
        admin_token=admin_token,
        payload=payload,
        timeout_seconds=timeout_seconds,
        connect_timeout_seconds=connect_timeout_seconds,
        redactions=redactions,
    )
    if status >= 400:
        raise SystemExit(
            "provider_request_failed "
            f"path={path} status={status} body={safe_text(response, redactions)}"
        )
    return response


def request_json_with_status(
    base_url: str,
    path: str,
    *,
    admin_token: str | None = None,
    payload: Mapping[str, object] | None = None,
    timeout_seconds: int = 120,
    connect_timeout_seconds: int = 15,
    redactions: Sequence[str] = (),
) -> tuple[dict[str, object], int]:
    effective_redactions = tuple(item for item in (admin_token, *redactions) if item)
    command = [
        "curl",
        "-sS",
        "--connect-timeout",
        str(connect_timeout_seconds),
        "--max-time",
        str(timeout_seconds),
    ]
    if admin_token is not None:
        command.extend(["-H", f"X-Nutmeg-Admin-Token: {admin_token}"])
    if payload is not None:
        command.extend(
            [
                "-H",
                "Content-Type: application/json",
                "-X",
                "POST",
                "--data",
                json.dumps(dict(payload)),
            ]
        )
    command.extend(["-w", "\n%{http_code}", f"{base_url}{path}"])
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "provider_request_failed "
            f"path={path} curl_exit={completed.returncode} "
            f"stderr={safe_text(completed.stderr, effective_redactions)}"
        )
    body, _, status_code = completed.stdout.rpartition("\n")
    if not status_code.isdigit():
        raise SystemExit(
            "provider_request_failed "
            f"path={path} status=unknown "
            f"body={safe_text(completed.stdout, effective_redactions)}"
        )
    parsed = _json_object(body, redactions=effective_redactions, path=path)
    return parsed, int(status_code)


def safe_text(value: object, redactions: Sequence[str] = ()) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    for secret in redactions:
        if secret:
            text = text.replace(secret, "[redacted]")
    return text.strip()[:500]


def record_provider_ops_run(
    base_url: str,
    *,
    admin_token: str,
    run_name: str,
    status: str = "success",
    run_type: str = "vps_helper",
    source: str = "vps",
    operator_name: str = "nutmeg-vps-helper",
    started_at_utc: datetime | None = None,
    completed_at_utc: datetime | None = None,
    duration_ms: int | None = None,
    exit_code: int | None = 0,
    summary_json: Mapping[str, object] | None = None,
    output_excerpt: str | None = None,
    metadata_json: Mapping[str, object] | None = None,
) -> None:
    completed_at = completed_at_utc or datetime.now(UTC)
    payload: dict[str, object] = {
        "run_name": run_name,
        "run_type": run_type,
        "source": source,
        "status": status,
        "operator_name": operator_name,
        "completed_at_utc": completed_at.isoformat(),
        "exit_code": exit_code,
        "summary_json": dict(summary_json or {}),
        "metadata_json": {
            "secret_value_not_exposed": True,
            **dict(metadata_json or {}),
        },
    }
    if started_at_utc is not None:
        payload["started_at_utc"] = started_at_utc.isoformat()
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if output_excerpt is not None:
        payload["output_excerpt"] = output_excerpt
    try:
        request_json(
            base_url,
            "/ops/provider-runs",
            admin_token=admin_token,
            payload=payload,
            timeout_seconds=45,
        )
    except SystemExit as exc:
        print(
            "provider_ops_run_history_record_failed "
            f"run_name={run_name} error={safe_text(str(exc), [admin_token])}",
            file=sys.stderr,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nutmeg provider helper utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("utc-now")
    record_parser = subparsers.add_parser("record-run")
    record_parser.add_argument("--base-url", required=True)
    record_parser.add_argument("--admin-token", required=True)
    record_parser.add_argument("--run-name", required=True)
    record_parser.add_argument("--status", default="failure")
    record_parser.add_argument("--run-type", default="vps_helper")
    record_parser.add_argument("--source", default="vps")
    record_parser.add_argument("--operator-name", default="nutmeg-vps-helper")
    record_parser.add_argument("--started-at-utc")
    record_parser.add_argument("--completed-at-utc")
    record_parser.add_argument("--duration-ms", type=int)
    record_parser.add_argument("--exit-code", type=int)
    record_parser.add_argument("--summary-json", default="{}")
    record_parser.add_argument("--output-excerpt")
    record_parser.add_argument("--metadata-json", default="{}")
    args = parser.parse_args(argv)
    if args.command == "utc-now":
        print(datetime.now(UTC).isoformat())
        return 0
    if args.command == "record-run":
        record_provider_ops_run(
            args.base_url,
            admin_token=args.admin_token,
            run_name=args.run_name,
            status=args.status,
            run_type=args.run_type,
            source=args.source,
            operator_name=args.operator_name,
            started_at_utc=_optional_datetime(args.started_at_utc),
            completed_at_utc=_optional_datetime(args.completed_at_utc),
            duration_ms=args.duration_ms,
            exit_code=args.exit_code,
            summary_json=_json_mapping(args.summary_json, "summary-json"),
            output_excerpt=args.output_excerpt,
            metadata_json=_json_mapping(args.metadata_json, "metadata-json"),
        )
        return 0
    return 2


def _json_object(
    value: str,
    *,
    redactions: Sequence[str],
    path: str,
) -> dict[str, object]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(
            "provider_request_failed "
            f"path={path} invalid_json={safe_text(value, redactions)}"
        ) from exc
    if not isinstance(parsed, dict):
        raise SystemExit(
            "provider_request_failed "
            f"path={path} expected_json_object={type(parsed).__name__}"
        )
    return {str(key): item for key, item in parsed.items()}


def _json_mapping(value: str, label: str) -> dict[str, object]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid_{label}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit(f"invalid_{label}:expected_object")
    return {str(key): item for key, item in parsed.items()}


def _optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
