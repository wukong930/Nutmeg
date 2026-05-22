ALTER TABLE provider_authorizations
  ADD COLUMN IF NOT EXISTS last_reviewed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS next_review_due_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS provider_authorization_reviews (
  provider_authorization_review_id BIGSERIAL PRIMARY KEY,
  provider_name TEXT NOT NULL REFERENCES provider_authorizations(provider_name),
  review_reference TEXT NOT NULL,
  review_status TEXT NOT NULL CHECK (
    review_status IN ('approved', 'research_only', 'needs_review', 'blocked')
  ),
  reviewed_by TEXT NOT NULL DEFAULT 'nutmeg-ops',
  reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  terms_url TEXT,
  terms_version_hash TEXT,
  allowed_use TEXT NOT NULL,
  commercial_use_allowed BOOLEAN NOT NULL DEFAULT false,
  retention_allowed BOOLEAN NOT NULL DEFAULT false,
  historical_data_allowed BOOLEAN NOT NULL DEFAULT false,
  redistribution_allowed BOOLEAN NOT NULL DEFAULT false,
  rate_limit TEXT,
  next_review_due_at TIMESTAMPTZ,
  evidence_json JSONB NOT NULL DEFAULT '{}',
  notes TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(provider_name, review_reference)
);

CREATE INDEX IF NOT EXISTS idx_provider_authorization_reviews_provider_reviewed
  ON provider_authorization_reviews(provider_name, reviewed_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_authorization_reviews_due
  ON provider_authorization_reviews(next_review_due_at ASC)
  WHERE next_review_due_at IS NOT NULL;

WITH seeded_reviews AS (
  SELECT
    provider_name,
    'seed-' || provider_name AS review_reference,
    CASE
      WHEN status = 'active' THEN 'approved'
      WHEN status = 'blocked' THEN 'blocked'
      WHEN status = 'research_only' THEN 'research_only'
      ELSE 'needs_review'
    END AS review_status,
    owner AS reviewed_by,
    COALESCE(terms_checked_at_utc, now()) AS reviewed_at,
    terms_url,
    NULL::TEXT AS terms_version_hash,
    allowed_use,
    commercial_use_allowed,
    retention_allowed,
    historical_data_allowed,
    redistribution_allowed,
    rate_limit,
    COALESCE(terms_checked_at_utc, now()) + INTERVAL '180 days' AS next_review_due_at,
    jsonb_build_object(
      'source', 'provider_authorization_seed',
      'migration', '0027_provider_authorization_reviews'
    ) AS evidence_json,
    notes
  FROM provider_authorizations
)
INSERT INTO provider_authorization_reviews (
  provider_name,
  review_reference,
  review_status,
  reviewed_by,
  reviewed_at,
  terms_url,
  terms_version_hash,
  allowed_use,
  commercial_use_allowed,
  retention_allowed,
  historical_data_allowed,
  redistribution_allowed,
  rate_limit,
  next_review_due_at,
  evidence_json,
  notes
)
SELECT
  provider_name,
  review_reference,
  review_status,
  reviewed_by,
  reviewed_at,
  terms_url,
  terms_version_hash,
  allowed_use,
  commercial_use_allowed,
  retention_allowed,
  historical_data_allowed,
  redistribution_allowed,
  rate_limit,
  next_review_due_at,
  evidence_json,
  notes
FROM seeded_reviews
ON CONFLICT (provider_name, review_reference)
DO UPDATE SET
  review_status = EXCLUDED.review_status,
  reviewed_by = EXCLUDED.reviewed_by,
  reviewed_at = EXCLUDED.reviewed_at,
  terms_url = EXCLUDED.terms_url,
  terms_version_hash = EXCLUDED.terms_version_hash,
  allowed_use = EXCLUDED.allowed_use,
  commercial_use_allowed = EXCLUDED.commercial_use_allowed,
  retention_allowed = EXCLUDED.retention_allowed,
  historical_data_allowed = EXCLUDED.historical_data_allowed,
  redistribution_allowed = EXCLUDED.redistribution_allowed,
  rate_limit = EXCLUDED.rate_limit,
  next_review_due_at = EXCLUDED.next_review_due_at,
  evidence_json = EXCLUDED.evidence_json,
  notes = EXCLUDED.notes;

WITH latest_review AS (
  SELECT DISTINCT ON (provider_name)
    provider_name,
    reviewed_at,
    next_review_due_at
  FROM provider_authorization_reviews
  ORDER BY provider_name, reviewed_at DESC, provider_authorization_review_id DESC
)
UPDATE provider_authorizations authorizations
SET
  last_reviewed_at = latest_review.reviewed_at,
  next_review_due_at = latest_review.next_review_due_at,
  updated_at = now()
FROM latest_review
WHERE authorizations.provider_name = latest_review.provider_name;
