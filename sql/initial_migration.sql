-- Initial migration for BlinkScoring ML schema

-- 1. Feature store (immutable snapshots)
CREATE TABLE IF NOT EXISTS feature_store_snapshots (
  snapshot_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          uuid NOT NULL,
  decision_ts      timestamptz NOT NULL,       -- when advance decision happened
  json_features    jsonb NOT NULL,
  created_at       timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feature_snapshots_user_id ON feature_store_snapshots(user_id);
CREATE INDEX IF NOT EXISTS idx_feature_snapshots_decision_ts ON feature_store_snapshots(decision_ts DESC);

-- 2. Model metadata
CREATE TABLE IF NOT EXISTS blink_models (
  model_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_tag      text UNIQUE,                -- e.g. 'v3.2.0-2025-05-05'
  artifact_url     text NOT NULL,
  train_auc        numeric,
  train_date       timestamptz,
  git_sha          text,
  promoted_to_prod boolean DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_blink_models_version_tag ON blink_models(version_tag);
CREATE INDEX IF NOT EXISTS idx_blink_models_promoted ON blink_models(promoted_to_prod) WHERE promoted_to_prod = true;

-- 3. Add ML columns to risk_score_audits if they don't exist
DO $$
BEGIN
  -- Check if risk_score_audits table exists
  IF EXISTS (
    SELECT FROM pg_tables 
    WHERE schemaname = 'public' AND tablename = 'risk_score_audits'
  ) THEN 
    -- Check for ML columns and add if they don't exist
    IF NOT EXISTS (
      SELECT FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'risk_score_audits' AND column_name = 'blink_ml_score'
    ) THEN
      ALTER TABLE risk_score_audits ADD COLUMN blink_ml_score numeric;
    END IF;
    
    IF NOT EXISTS (
      SELECT FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'risk_score_audits' AND column_name = 'blink_ml_version'
    ) THEN
      ALTER TABLE risk_score_audits ADD COLUMN blink_ml_version text;
    END IF;
    
    IF NOT EXISTS (
      SELECT FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'risk_score_audits' AND column_name = 'shap_top5'
    ) THEN
      ALTER TABLE risk_score_audits ADD COLUMN shap_top5 jsonb;
    END IF;
    
    IF NOT EXISTS (
      SELECT FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'risk_score_audits' AND column_name = 'snapshot_timestamp'
    ) THEN
      ALTER TABLE risk_score_audits ADD COLUMN snapshot_timestamp timestamptz DEFAULT now();
    END IF;
  ELSE
    -- Create risk_score_audits table if it doesn't exist
    CREATE TABLE risk_score_audits (
      id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id              uuid NOT NULL,
      snapshot_timestamp   timestamptz NOT NULL DEFAULT now(),
      blink_ml_score       numeric,
      blink_ml_version     text,
      shap_top5            jsonb, -- Top features that influenced the score
      raw_features         jsonb, -- Raw feature values used
      created_at           timestamptz NOT NULL DEFAULT now()
    );
    
    CREATE INDEX IF NOT EXISTS idx_risk_score_audits_user_id ON risk_score_audits(user_id);
    CREATE INDEX IF NOT EXISTS idx_risk_score_audits_created_at ON risk_score_audits(created_at);
  END IF;
END
$$;

-- 4. Add last_transaction_timestamp to users table if it doesn't exist
DO $$
BEGIN
  IF EXISTS (
    SELECT FROM pg_tables 
    WHERE schemaname = 'public' AND tablename = 'users'
  ) THEN
    IF NOT EXISTS (
      SELECT FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'last_transaction_timestamp'
    ) THEN
      ALTER TABLE users ADD COLUMN last_transaction_timestamp timestamptz;
    END IF;
  END IF;
END
$$;

-- 5. Create trigger to update last_transaction_timestamp when a new transaction is added
CREATE OR REPLACE FUNCTION update_user_last_transaction_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  -- Find the user_id associated with this transaction
  WITH transaction_user AS (
    SELECT u.id AS user_id
    FROM users u
    JOIN asset_report_items ari ON ari.asset_report_id = (
      SELECT ari_inner.asset_report_id 
      FROM asset_report_items ari_inner
      JOIN asset_report_accounts ara_inner ON ara_inner.asset_report_item_id = ari_inner.id
      WHERE ara_inner.id = NEW.asset_report_account_id
      LIMIT 1
    )
    LIMIT 1
  )
  UPDATE users
  SET last_transaction_timestamp = CURRENT_TIMESTAMP
  FROM transaction_user
  WHERE users.id = transaction_user.user_id;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop the trigger if it already exists
DROP TRIGGER IF EXISTS tr_update_last_transaction_timestamp ON asset_report_transactions;

-- Create the trigger
CREATE TRIGGER tr_update_last_transaction_timestamp
AFTER INSERT ON asset_report_transactions
FOR EACH ROW
EXECUTE FUNCTION update_user_last_transaction_timestamp();

-- 6. Create feature delta tracking table (for incremental updates)
CREATE TABLE IF NOT EXISTS blink_feature_raw (
  id bigserial PRIMARY KEY,
  user_id uuid NOT NULL,
  source_ts timestamptz NOT NULL,
  feature_name text NOT NULL,
  feature_value numeric,
  feature_value_text text,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_blink_feature_raw_user_id ON blink_feature_raw(user_id);
CREATE INDEX IF NOT EXISTS idx_blink_feature_raw_source_ts ON blink_feature_raw(source_ts);
CREATE INDEX IF NOT EXISTS idx_blink_feature_raw_feature_name ON blink_feature_raw(feature_name);

-- 7. User last transaction timestamp tracking
CREATE TABLE IF NOT EXISTS user_feature_status (
  user_id uuid PRIMARY KEY,
  last_txn_ts timestamptz NOT NULL DEFAULT now(),
  last_score_ts timestamptz,
  needs_scoring boolean DEFAULT true,
  updated_at timestamptz DEFAULT now()
);

-- 8. Create the view for ML features
CREATE OR REPLACE VIEW blink_ml_features AS
WITH recent_features AS (
  SELECT user_id, feature_name, feature_value,
         ROW_NUMBER() OVER (PARTITION BY user_id, feature_name ORDER BY source_ts DESC) as rn
  FROM blink_feature_raw
  WHERE source_ts > (now() - interval '90 days')
)
SELECT 
  user_id,
  now() as as_of,
  jsonb_object_agg(feature_name, feature_value) as features
FROM recent_features
WHERE rn = 1
GROUP BY user_id;

-- 9. Dead Letter Queue for failed scoring attempts
CREATE TABLE IF NOT EXISTS blink_scoring_deadletter (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  features jsonb NOT NULL,
  error_message text,
  retry_count integer DEFAULT 0,
  last_retry_at timestamptz,
  created_at timestamptz DEFAULT now(),
  resolved_at timestamptz
);

-- 10. Partial index on risk_score_audits for recent entries
-- Create a regular index instead of a partial index with now()
CREATE INDEX IF NOT EXISTS risk_score_recent_idx
  ON risk_score_audits (user_id, created_at DESC);

-- 11. Setup pg_cron if not already installed
-- Note: This might require superuser permissions on Supabase
-- Uncomment these if you have the necessary permissions:
-- CREATE EXTENSION IF NOT EXISTS pg_cron;
-- 
-- SELECT cron.schedule('*/5 * * * *', $$
--   UPDATE user_feature_status
--   SET needs_scoring = true,
--       last_txn_ts = now()
--   FROM (
--     SELECT DISTINCT art.asset_report_account_id
--     FROM asset_report_transactions art
--     WHERE art.created_at > (now() - interval '5 minutes')
--   ) new_txns
--   JOIN asset_report_accounts ara ON new_txns.asset_report_account_id = ara.id
--   JOIN asset_reports ar ON ara.asset_report_item_id IN (
--     SELECT id FROM asset_report_items WHERE asset_report_id = ar.id
--   )
--   WHERE user_feature_status.user_id = ar.user_id;
-- $$); 