-- Create a view for easy feature extraction during model training
-- This view combines risk_score_audits with outcome labels from repayments/cash_advances

CREATE OR REPLACE VIEW blink_scoring_training_view AS
SELECT
    r.user_id,
    r.snapshot_timestamp,
    -- Feature columns from risk_score_audits
    r.metric_observed_history_days,
    r.metric_median_paycheck,
    r.metric_paycheck_regularity,
    r.metric_days_since_last_paycheck,
    r.metric_overdraft_count90,
    r.metric_net_cash30,
    r.metric_debt_load30,
    r.metric_volatility90,
    r.metric_clean_buffer7,
    r.metric_buffer_volatility,
    r.metric_deposit_multiplicity30,
    -- Original score column renamed or commented out if it doesn't exist
    -- r.score AS original_score,
    -- Target label - whether a user ever defaulted/became delinquent after snapshot time
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM repayments rep
            WHERE rep.user_id = r.user_id
              AND rep.status IN ('defaulted', 'delinquent', 'escalated')
              AND rep.created_at > r.snapshot_timestamp
        )
        OR EXISTS (
            SELECT 1
            FROM cash_advances ca
            WHERE ca.user_id = r.user_id
              AND ca.status = 'overdue'
              AND ca.created_at > r.snapshot_timestamp
        )
        THEN 1 ELSE 0
    END AS target_label
FROM risk_score_audits r;

-- Add an index to improve query performance (optional)
-- CREATE INDEX IF NOT EXISTS idx_risk_score_audits_user_timestamp 
--   ON risk_score_audits(user_id, snapshot_timestamp); 