#!/usr/bin/env bash

nutmeg_provider_ops_started_at_utc() {
  python3 -m scripts.provider_request_helpers utc-now
}

nutmeg_provider_ops_install_failure_trap() {
  NUTMEG_PROVIDER_OPS_RUN_BASE_URL="$1"
  NUTMEG_PROVIDER_OPS_RUN_ADMIN_TOKEN="$2"
  NUTMEG_PROVIDER_OPS_RUN_NAME="$3"
  NUTMEG_PROVIDER_OPS_RUN_STARTED_AT="$4"
  NUTMEG_PROVIDER_OPS_RUN_TYPE="${5:-vps_helper}"
  NUTMEG_PROVIDER_OPS_RUN_SOURCE="${6:-vps}"
  export NUTMEG_PROVIDER_OPS_RUN_BASE_URL
  export NUTMEG_PROVIDER_OPS_RUN_ADMIN_TOKEN
  export NUTMEG_PROVIDER_OPS_RUN_NAME
  export NUTMEG_PROVIDER_OPS_RUN_STARTED_AT
  export NUTMEG_PROVIDER_OPS_RUN_TYPE
  export NUTMEG_PROVIDER_OPS_RUN_SOURCE
  trap 'nutmeg_provider_ops_record_shell_failure "$LINENO" "$?"' ERR
}

nutmeg_provider_ops_record_shell_failure() {
  local failed_line="$1"
  local exit_code="$2"
  trap - ERR
  set +e
  local completed_at
  completed_at="$(python3 -m scripts.provider_request_helpers utc-now 2>/dev/null)"
  python3 -m scripts.provider_request_helpers record-run \
    --base-url "$NUTMEG_PROVIDER_OPS_RUN_BASE_URL" \
    --admin-token "$NUTMEG_PROVIDER_OPS_RUN_ADMIN_TOKEN" \
    --run-name "$NUTMEG_PROVIDER_OPS_RUN_NAME" \
    --run-type "$NUTMEG_PROVIDER_OPS_RUN_TYPE" \
    --source "$NUTMEG_PROVIDER_OPS_RUN_SOURCE" \
    --status failure \
    --operator-name "nutmeg-vps-helper" \
    --started-at-utc "$NUTMEG_PROVIDER_OPS_RUN_STARTED_AT" \
    --completed-at-utc "$completed_at" \
    --exit-code "$exit_code" \
    --summary-json "{\"stage\":\"shell\",\"line\":$failed_line}" \
    --output-excerpt "provider_helper_failed line=$failed_line exit=$exit_code" \
    --metadata-json '{"secret_value_not_exposed":true,"failure_capture":"shell_err_trap"}' \
    >/dev/null 2>&1 || true
  exit "$exit_code"
}
