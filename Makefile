.PHONY: test lint typecheck web-typecheck web-lint web-build web-e2e validate smoke-postgres deploy-vps smoke-vps acceptance-vps provider-sync-dry-run-vps provider-mapping-bootstrap-vps provider-api-football-discovery-vps provider-api-football-mapping-bootstrap-vps provider-sportmonks-discovery-vps provider-sportmonks-mapping-bootstrap-vps provider-sportmonks-mapping-backfill-vps provider-odds-sync-vps provider-odds-gap-report-vps provider-fallback-odds-probe-vps provider-runtime-monitoring-vps provider-runtime-monitoring-cron-vps provider-gap-remediation-vps provider-onboarding-assessment-vps

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .

typecheck:
	.venv/bin/mypy apps/api/src

web-typecheck:
	cd apps/web && npm run typecheck

web-lint:
	cd apps/web && npm run lint

web-build:
	cd apps/web && npm run build

web-e2e:
	cd apps/web && npm run e2e

validate: test lint typecheck web-typecheck web-lint web-build

smoke-postgres:
	scripts/accuracy-postgres-smoke.sh

deploy-vps:
	scripts/deploy-vps.sh

smoke-vps:
	scripts/vps-smoke.sh

acceptance-vps:
	scripts/vps-acceptance.sh

provider-sync-dry-run-vps:
	scripts/vps-provider-sync-dry-run.sh

provider-mapping-bootstrap-vps:
	scripts/vps-provider-mapping-bootstrap.sh

provider-api-football-discovery-vps:
	scripts/vps-provider-api-football-discovery.sh

provider-api-football-mapping-bootstrap-vps:
	scripts/vps-provider-api-football-mapping-bootstrap.sh

provider-sportmonks-discovery-vps:
	scripts/vps-provider-sportmonks-discovery.sh

provider-sportmonks-mapping-bootstrap-vps:
	scripts/vps-provider-sportmonks-mapping-bootstrap.sh

provider-sportmonks-mapping-backfill-vps:
	NUTMEG_SPORTMONKS_MAPPING_AUTO_DISCOVERY=true scripts/vps-provider-sportmonks-mapping-bootstrap.sh

provider-odds-sync-vps:
	scripts/vps-provider-odds-sync.sh

provider-odds-gap-report-vps:
	scripts/vps-provider-odds-gap-report.sh

provider-fallback-odds-probe-vps:
	scripts/vps-provider-fallback-odds-probe.sh

provider-runtime-monitoring-vps:
	scripts/vps-provider-runtime-monitoring.sh

provider-runtime-monitoring-cron-vps:
	scripts/vps-provider-runtime-monitoring-cron.sh

provider-gap-remediation-vps: provider-mapping-bootstrap-vps provider-sportmonks-mapping-backfill-vps provider-odds-sync-vps provider-odds-gap-report-vps provider-fallback-odds-probe-vps

provider-onboarding-assessment-vps:
	scripts/vps-provider-onboarding-assessment.sh
