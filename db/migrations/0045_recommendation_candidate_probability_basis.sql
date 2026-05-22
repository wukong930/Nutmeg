ALTER TABLE recommendation_candidates
  ADD COLUMN IF NOT EXISTS model_probability NUMERIC,
  ADD COLUMN IF NOT EXISTS calibrated_probability NUMERIC,
  ADD COLUMN IF NOT EXISTS probability_source TEXT NOT NULL DEFAULT 'model';

ALTER TABLE recommendation_candidate_pool_items
  ADD COLUMN IF NOT EXISTS model_probability NUMERIC,
  ADD COLUMN IF NOT EXISTS calibrated_probability NUMERIC,
  ADD COLUMN IF NOT EXISTS probability_source TEXT NOT NULL DEFAULT 'model';

UPDATE recommendation_candidates
SET model_probability = probability
WHERE model_probability IS NULL;

UPDATE recommendation_candidate_pool_items
SET model_probability = probability
WHERE model_probability IS NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'recommendation_candidates_probability_source_check'
  ) THEN
    ALTER TABLE recommendation_candidates
      ADD CONSTRAINT recommendation_candidates_probability_source_check
      CHECK (probability_source IN ('model', 'calibrated'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'recommendation_candidate_pool_items_probability_source_check'
  ) THEN
    ALTER TABLE recommendation_candidate_pool_items
      ADD CONSTRAINT recommendation_candidate_pool_items_probability_source_check
      CHECK (probability_source IN ('model', 'calibrated'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recommendation_candidates_probability_source
  ON recommendation_candidates(probability_source, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_candidate_pool_items_probability_source
  ON recommendation_candidate_pool_items(probability_source, created_at DESC);
