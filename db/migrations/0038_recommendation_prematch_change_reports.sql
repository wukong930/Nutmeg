CREATE TABLE IF NOT EXISTS recommendation_prematch_change_reports (
  recommendation_prematch_change_report_id BIGSERIAL PRIMARY KEY,
  report_key TEXT NOT NULL UNIQUE,
  window_start_utc TIMESTAMPTZ NOT NULL,
  window_end_utc TIMESTAMPTZ NOT NULL,
  pass_type TEXT,
  mode TEXT,
  strategy TEXT,
  stage_count INT NOT NULL DEFAULT 0,
  changed_stage_count INT NOT NULL DEFAULT 0,
  incident_count INT NOT NULL DEFAULT 0,
  critical_incident_count INT NOT NULL DEFAULT 0,
  locked_preservation_stage_count INT NOT NULL DEFAULT 0,
  report_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source TEXT NOT NULL DEFAULT 'recommendation_prematch_change_report_v3_1',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recommendation_prematch_reports_window
  ON recommendation_prematch_change_reports(window_start_utc DESC, window_end_utc DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_prematch_reports_mode_pass
  ON recommendation_prematch_change_reports(pass_type, mode, window_end_utc DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_prematch_reports_incidents
  ON recommendation_prematch_change_reports(incident_count DESC, window_end_utc DESC);
