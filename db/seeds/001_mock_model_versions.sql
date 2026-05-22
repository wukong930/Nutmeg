INSERT INTO model_versions (
  model_version,
  model_family,
  status,
  feature_version,
  calibration_version,
  metrics_json,
  params_json
) VALUES (
  'poisson-m1.0.0',
  'poisson',
  'active',
  'features-m1.0.0',
  'calibration-m1.0.0',
  '{}',
  '{"max_goals": 8}'
) ON CONFLICT (model_version) DO NOTHING;
