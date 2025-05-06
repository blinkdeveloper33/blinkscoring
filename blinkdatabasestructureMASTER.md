-- ## ENUM Type Definitions
-- Purpose: Defines custom enumerated types used across various tables.

-- ENUM: admin_role_enum
-- Defines roles for administrative users.
CREATE TYPE public.admin_role_enum AS ENUM (
    'superadmin',
    'reviewer',
    'analyst'
);

-- ENUM: approval_status_enum
-- Defines possible statuses for approvals (e.g., user cash advance eligibility).
CREATE TYPE public.approval_status_enum AS ENUM (
    'pending',
    'approved',
    'denied',
    'revoked'
);

-- ENUM: cash_advance_repayment_status
-- Defines statuses related to the repayment of a cash advance.
CREATE TYPE public.cash_advance_repayment_status AS ENUM (
    'scheduled',
    'pending',
    'attempted',
    'successful',
    'failed',
    'grace_period',
    'defaulted'
);

-- ENUM: cash_advance_status_enum
-- Defines the lifecycle statuses of a cash advance request and disbursement.
CREATE TYPE public.cash_advance_status_enum AS ENUM (
    'requested',
    'authorization_pending',
    'authorization_approved',
    'authorization_declined',
    'user_action_required',
    'authorization_failed',
    'disbursing',
    'disbursed',
    'transfer_failed',
    'transfer_returned',
    'transfer_cancelled',
    'repaid',
    'overdue'
);

-- ENUM: disbursement_status
-- Defines statuses specifically for the disbursement process of funds.
CREATE TYPE public.disbursement_status AS ENUM (
    'pending',
    'authorization_pending',
    'authorization_approved',
    'authorization_declined',
    'transfer_pending',
    'transfer_processing',
    'transfer_completed',
    'transfer_failed'
);

-- ENUM: news_content_type
-- Defines the types of content that can be posted in the news section.
CREATE TYPE public.news_content_type AS ENUM (
    'announcement',
    'update',
    'tip',
    'alert',
    'promotion'
);

-- ENUM: notification_channel
-- Defines the channels through which notifications can be delivered.
CREATE TYPE public.notification_channel AS ENUM (
    'in_app',
    'push',
    'email',
    'sms'
);

-- ENUM: notification_priority
-- Defines priority levels for notifications.
CREATE TYPE public.notification_priority AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);

-- ENUM: notification_status
-- Defines the delivery status of a notification.
CREATE TYPE public.notification_status AS ENUM (
    'pending',
    'sent',
    'delivered',
    'failed'
);

-- ENUM: notification_type
-- Defines the different categories or types of notifications.
CREATE TYPE public.notification_type AS ENUM (
    'advance_approval',
    'funds_deposited',
    'repayment_reminder',
    'insufficient_balance',
    'marketing',
    'news',
    'system'
);

-- ENUM: repayment_status
-- Defines the lifecycle statuses for a repayment attempt.
CREATE TYPE public.repayment_status AS ENUM (
    'scheduled',
    'balance_check_pending',
    'balance_check_successful',
    'balance_check_failed',
    'authorization_pending',
    'authorization_approved',
    'authorization_declined',
    'transfer_pending',
    'transfer_processing',
    'transfer_completed',
    'transfer_failed',
    'grace_period',
    'defaulted',
    'delinquent',
    'escalated',
    'submitted',
    'settled',
    'partial'
);

-- ENUM: state_enum
-- Defines the states allowed for user addresses (subset of US states).
CREATE TYPE public.state_enum AS ENUM (
    'Nevada',
    'Missouri',
    'Wisconsin',
    'Kansas',
    'South Carolina',
    'Florida',
    'FL' -- Note: Includes abbreviation, might need standardization
);

-- ENUM: velocity_type_enum
-- Defines the speed/type of cash advance offered.
CREATE TYPE public.velocity_type_enum AS ENUM (
    'instant',
    'same_day',
    'standard'
);


-- ## Table: admin_audit_logs
-- Purpose: Tracks actions performed by administrators within the system for auditing purposes.
-- Relationships:
--   - admin_id: Foreign key referencing the admin_users(id) table, linking the log entry to the specific administrator who performed the action.
--   - target_user_id: Foreign key referencing the users(id) table, linking the log entry to the user account that was affected by the admin action.
create table public.admin_audit_logs (
  id uuid not null,
  admin_id uuid not null,
  action character varying(50) not null,
  target_user_id uuid not null,
  details jsonb null,
  created_at timestamp with time zone not null default now(),
  constraint admin_audit_logs_pkey primary key (id),
  constraint fk_admin_id foreign KEY (admin_id) references admin_users (id) on delete CASCADE,
  constraint fk_target_user_id foreign KEY (target_user_id) references users (id) on delete CASCADE
) TABLESPACE pg_default;

-- Indexes for admin_audit_logs table
create index IF not exists admin_audit_logs_admin_id_idx on public.admin_audit_logs using btree (admin_id) TABLESPACE pg_default;
create index IF not exists admin_audit_logs_target_user_id_idx on public.admin_audit_logs using btree (target_user_id) TABLESPACE pg_default;
create index IF not exists admin_audit_logs_action_idx on public.admin_audit_logs using btree (action) TABLESPACE pg_default;
create index IF not exists admin_audit_logs_created_at_idx on public.admin_audit_logs using btree (created_at) TABLESPACE pg_default;


-- ## Table: admin_sessions
-- Purpose: Stores active session information for administrators, managing their login state using refresh tokens.
-- Relationships:
--   - admin_id: Foreign key referencing the admin_users(id) table, linking the session to the specific administrator.
create table public.admin_sessions (
  id uuid not null,
  admin_id uuid not null,
  refresh_token text not null,
  expires_at timestamp with time zone not null,
  created_at timestamp with time zone not null default now(),
  constraint admin_sessions_pkey primary key (id),
  constraint fk_admin_id foreign KEY (admin_id) references admin_users (id) on delete CASCADE
) TABLESPACE pg_default;

-- Indexes for admin_sessions table
create index IF not exists admin_sessions_admin_id_idx on public.admin_sessions using btree (admin_id) TABLESPACE pg_default;
create index IF not exists admin_sessions_refresh_token_idx on public.admin_sessions using btree (refresh_token) TABLESPACE pg_default;
create index IF not exists admin_sessions_expires_at_idx on public.admin_sessions using btree (expires_at) TABLESPACE pg_default;

-- ## Table: admin_users
-- Purpose: Stores information about administrator accounts, including credentials, roles, and basic profile data.
-- Relationships:
--   - Referenced by: admin_audit_logs(admin_id), admin_sessions(admin_id), notification_batches(created_by), user_cash_advance_approvals(performed_by)
create table public.admin_users (
  id uuid not null default gen_random_uuid (),
  email text not null,
  hashed_password text not null,
  role public.admin_role_enum not null default 'analyst'::admin_role_enum,
  full_name text null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  last_login timestamp with time zone null,
  constraint admin_users_pkey primary key (id),
  constraint admin_users_email_key unique (email)
) TABLESPACE pg_default;

-- Index for admin_users table
create index IF not exists idx_admin_users_email on public.admin_users using btree (email) TABLESPACE pg_default;

-- ## Table: asset_report_account_historical_balances
-- Purpose: Stores historical daily balances for accounts included in an asset report. This allows tracking balance changes over time.
-- Relationships:
--   - asset_report_account_id: Foreign key referencing asset_report_accounts(id), linking the historical balance record to a specific account within an asset report.
create table public.asset_report_account_historical_balances (
  id bigserial not null,
  asset_report_account_id uuid not null,
  balance_date date not null,
  balance_current numeric(18, 2) not null,
  iso_currency_code text null,
  unofficial_currency_code text null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint asset_report_account_historical_balances_pkey primary key (id),
  constraint asset_report_account_historical_ba_asset_report_account_id_fkey foreign KEY (asset_report_account_id) references asset_report_accounts (id) on delete CASCADE
) TABLESPACE pg_default;

-- Index for asset_report_account_historical_balances table
create index IF not exists idx_historical_balances_account on public.asset_report_account_historical_balances using btree (asset_report_account_id) TABLESPACE pg_default;

-- ## Table: asset_report_accounts
-- Purpose: Represents individual bank accounts associated with an item within a Plaid asset report. Contains details like account name, type, balance, and ownership information.
-- Relationships:
--   - asset_report_item_id: Foreign key referencing asset_report_items(id), linking the account to a specific item (bank connection) within the asset report.
--   - Referenced by: asset_report_account_historical_balances(asset_report_account_id), asset_report_transactions(asset_report_account_id)
create table public.asset_report_accounts (
  id uuid not null default gen_random_uuid (),
  asset_report_item_id uuid not null,
  account_id text not null,
  name text null,
  mask text null,
  official_name text null,
  type text null,
  subtype text null,
  iso_currency_code text null,
  unofficial_currency_code text null,
  balance_current numeric(18, 2) null,
  balance_available numeric(18, 2) null,
  balance_limit numeric(18, 2) null,
  days_available integer null,
  historical_balances jsonb null,
  owners jsonb null,
  transactions_count integer null default 0,
  additional_metadata jsonb null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  -- Pre-calculation columns for transaction summary (populated by trigger/job)
  min_transaction_date DATE NULL,      -- Pre-calculated date of the earliest transaction for this account.
  max_transaction_date DATE NULL,      -- Pre-calculated date of the latest transaction for this account.
  calculated_transaction_days_span INTEGER NULL, -- Pre-calculated span in days between the first and last transaction (inclusive).
  has_historical_balances boolean not null default false, -- Flag indicating if historical balances exist for this account
  has_transactions boolean not null default false, -- Flag indicating if transactions exist for this account
  constraint asset_report_accounts_pkey primary key (id),
  constraint asset_report_accounts_asset_report_item_id_fkey foreign KEY (asset_report_item_id) references asset_report_items (id) on delete CASCADE
) TABLESPACE pg_default;

-- Index for asset_report_accounts table
create index IF not exists asset_report_accounts_item_id_idx on public.asset_report_accounts using btree (asset_report_item_id) TABLESPACE pg_default;
-- Additional indexes found in live DB:
CREATE INDEX IF NOT EXISTS idx_ara_has_balances_and_transactions ON public.asset_report_accounts USING btree (has_historical_balances, has_transactions) WHERE ((has_historical_balances = true) AND (has_transactions = true)) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_ara_has_historical_balances ON public.asset_report_accounts USING btree (has_historical_balances) WHERE (has_historical_balances = true) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_ara_has_transactions ON public.asset_report_accounts USING btree (has_transactions) WHERE (has_transactions = true) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_asset_report_accounts_asset_report_item_id ON public.asset_report_accounts USING btree (asset_report_item_id) TABLESPACE pg_default; -- Note: Potentially redundant with asset_report_accounts_item_id_idx
CREATE INDEX IF NOT EXISTS idx_asset_report_accounts_summary_calcs ON public.asset_report_accounts USING btree (transactions_count, calculated_transaction_days_span) TABLESPACE pg_default;


-- ## Table: asset_report_items
-- Purpose: Represents a single financial institution connection (item) within a Plaid asset report. Links the report to institution details.
-- Relationships:
--   - asset_report_id: Foreign key referencing asset_reports(id), linking this item to the overall asset report.
--   - Referenced by: asset_report_accounts(asset_report_item_id)
create table public.asset_report_items (
  id uuid not null default gen_random_uuid (),
  asset_report_id uuid not null,
  item_id text not null,
  institution_id text null,
  institution_name text null,
  date_last_updated timestamp with time zone null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint asset_report_items_pkey primary key (id),
  constraint asset_report_items_asset_report_id_fkey foreign KEY (asset_report_id) references asset_reports (id) on delete CASCADE
) TABLESPACE pg_default;

-- Index for asset_report_items table
create index IF not exists asset_report_items_asset_report_id_idx on public.asset_report_items using btree (asset_report_id) TABLESPACE pg_default;
-- Additional index found in live DB:
CREATE INDEX IF NOT EXISTS idx_asset_report_items_asset_report_id ON public.asset_report_items USING btree (asset_report_id) TABLESPACE pg_default; -- Note: Potentially redundant with above index.


-- ## Table: asset_report_transactions
-- Purpose: Stores transaction data associated with accounts within a Plaid asset report. Includes details like description, amount, date, category, and location.
-- Relationships:
--   - asset_report_account_id: Foreign key referencing asset_report_accounts(id), linking the transaction to a specific account within an asset report.
create table public.asset_report_transactions (
  id bigserial not null,
  asset_report_account_id uuid not null,
  transaction_id text not null,
  original_description text null,
  name text null,
  merchant_name text null,
  amount numeric(18, 2) not null,
  iso_currency_code text null,
  unofficial_currency_code text null,
  date date null,
  pending boolean null,
  category text[] null,
  category_id text null,
  payment_meta jsonb null,
  location jsonb null,
  created_at timestamp with time zone not null default now(),
  inflow_category_l1 character varying(50) null,
  inflow_category_l2 character varying(50) null,
  inflow_category_l3 character varying(50) null,
  inflow_category_l4 character varying(100) null,
  inflow_metadata jsonb null,
  constraint asset_report_transactions_pkey primary key (id),
  constraint asset_report_transactions_asset_report_account_id_fkey foreign KEY (asset_report_account_id) references asset_report_accounts (id) on delete CASCADE
) TABLESPACE pg_default;

-- Index for asset_report_transactions table
create index IF not exists asset_report_transactions_account_id_idx on public.asset_report_transactions using btree (asset_report_account_id) TABLESPACE pg_default;
-- Additional index found in live DB:
CREATE INDEX IF NOT EXISTS idx_art_account_id_date ON public.asset_report_transactions USING btree (asset_report_account_id, date) TABLESPACE pg_default;


-- ## Table: asset_reports
-- Purpose: Stores information about generated Plaid asset reports for users. Contains metadata like the report token, ID, requested duration, and the raw report data.
-- Relationships:
--   - user_id: Foreign key referencing users(id), linking the asset report to the specific user it belongs to.
--   - Referenced by: asset_report_items(asset_report_id)
create table public.asset_reports (
  id uuid not null default gen_random_uuid (),
  user_id uuid not null,
  asset_report_token text not null,
  asset_report_id text null,
  days_requested integer null,
  client_report_id text null,
  date_generated timestamp with time zone null,
  request_id text null,
  raw_report_json jsonb null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint asset_reports_pkey primary key (id),
  constraint asset_reports_asset_report_id_key unique (asset_report_id),
  constraint asset_reports_user_id_fkey foreign KEY (user_id) references users (id) on delete CASCADE
) TABLESPACE pg_default;

-- Indexes for asset_reports table
create index IF not exists asset_reports_asset_report_id_idx on public.asset_reports using btree (asset_report_id) TABLESPACE pg_default;
create index IF not exists asset_reports_asset_report_token_idx on public.asset_reports using btree (asset_report_token) TABLESPACE pg_default;
-- Additional index found in live DB:
CREATE INDEX IF NOT EXISTS idx_asset_reports_user_id ON public.asset_reports USING btree (user_id) TABLESPACE pg_default;


-- ## Table: cash_advances
-- Purpose: Represents cash advance requests made by users. Tracks the principal amount, fees, repayment terms, status, and disbursement/repayment dates.
-- Relationships:
--   - user_id: Foreign key referencing users(id), linking the cash advance to the requesting user.
--   - plaid_item_id: Foreign key referencing plaid_items(id) (ON DELETE SET NULL), linking the advance to the user's primary bank connection at the time of request. If the Plaid item is deleted, this link becomes NULL.
--   - Referenced by: disbursements(cash_advance_id), repayments(cash_advance_id)
create table public.cash_advances (
  id uuid not null default gen_random_uuid (),
  user_id uuid not null,
  plaid_item_id uuid null,
  principal_amount numeric(10, 2) not null default 200.00,
  velocity_type public.velocity_type_enum not null,
  velocity_fee numeric(10, 2) not null,
  discount_amount numeric(10, 2) not null default 0.00,
  final_fee numeric(10, 2) not null,
  repayment_term_days integer not null,
  repayment_due_date date not null,
  status public.cash_advance_status_enum not null default 'requested'::cash_advance_status_enum,
  requested_at timestamp with time zone not null default now(),
  disbursed_at timestamp with time zone null,
  repaid_at timestamp with time zone null,
  metadata jsonb null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  total_repayment_amount numeric null,
  constraint cash_advances_pkey primary key (id),
  constraint cash_advances_plaid_item_id_fkey foreign KEY (plaid_item_id) references plaid_items (id) on delete set null,
  constraint cash_advances_user_id_fkey foreign KEY (user_id) references users (id) on delete CASCADE
) TABLESPACE pg_default;

-- Index for cash_advances table
create index IF not exists idx_cash_advances_user_id on public.cash_advances using btree (user_id) TABLESPACE pg_default;

-- Trigger for cash_advances table: Automatically calculates total_repayment_amount before insert or update.
create trigger update_total_repayment_amount BEFORE INSERT
or
update OF principal_amount,
final_fee on cash_advances for EACH row
execute FUNCTION calculate_total_repayment_amount ();

-- ## Table: disbursement_authorizations
-- Purpose: Records the authorization attempts made via Plaid Transfer API for disbursing funds for a cash advance. Stores details of the authorization decision and rationale.
-- Relationships:
--   - disbursement_id: Foreign key referencing disbursements(id), linking the authorization attempt to a specific disbursement record.
--   - Referenced by: disbursement_transfers(disbursement_authorization_id)
create table public.disbursement_authorizations (
  id uuid not null default gen_random_uuid (),
  disbursement_id uuid not null,
  plaid_authorization_id text null,
  amount numeric not null,
  network text not null,
  decision text null,
  rationale_code text null,
  rationale_description text null,
  raw_response jsonb null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint disbursement_authorizations_pkey primary key (id),
  constraint disbursement_authorizations_disbursement_id_fkey foreign KEY (disbursement_id) references disbursements (id) on delete NO ACTION,
  constraint fk_disbursement foreign KEY (disbursement_id) references disbursements (id) on delete CASCADE
) TABLESPACE pg_default;

-- Trigger for disbursement_authorizations table: Automatically updates the updated_at timestamp on modification.
create trigger update_disbursement_authorizations_updated_at BEFORE
update on disbursement_authorizations for EACH row
execute FUNCTION update_modified_column ();


-- ## Table: disbursement_transfers
-- Purpose: Records the actual Plaid transfer attempts associated with a disbursement authorization. Tracks the transfer status and details.
-- Relationships:
--   - disbursement_id: Foreign key referencing disbursements(id), linking the transfer back to the overall disbursement.
--   - disbursement_authorization_id: Foreign key referencing disbursement_authorizations(id), linking the transfer to its specific authorization record.
create table public.disbursement_transfers (
  id uuid not null default gen_random_uuid (),
  disbursement_id uuid not null,
  disbursement_authorization_id uuid not null,
  plaid_transfer_id text null,
  amount numeric not null,
  status text not null,
  description text null,
  raw_response jsonb null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint disbursement_transfers_pkey primary key (id),
  constraint disbursement_transfers_disbursement_authorization_id_fkey foreign KEY (disbursement_authorization_id) references disbursement_authorizations (id) on delete NO ACTION,
  constraint disbursement_transfers_disbursement_id_fkey foreign KEY (disbursement_id) references disbursements (id) on delete NO ACTION,
  constraint fk_disbursement foreign KEY (disbursement_id) references disbursements (id) on delete CASCADE,
  constraint fk_disbursement_authorization foreign KEY (disbursement_authorization_id) references disbursement_authorizations (id) on delete CASCADE
) TABLESPACE pg_default;

-- Index for disbursement_transfers table
create index IF not exists idx_disbursement_transfers_plaid_transfer_id on public.disbursement_transfers using btree (plaid_transfer_id) TABLESPACE pg_default;

-- Trigger for disbursement_transfers table: Automatically updates the updated_at timestamp on modification.
create trigger update_disbursement_transfers_updated_at BEFORE
update on disbursement_transfers for EACH row
execute FUNCTION update_modified_column ();

-- ## Table: disbursements
-- Purpose: Represents the process of disbursing funds for an approved cash advance. Tracks the status, amount, and completion time of the disbursement.
-- Relationships:
--   - cash_advance_id: Foreign key referencing cash_advances(id), linking the disbursement to the specific cash advance it fulfills.
--   - Referenced by: disbursement_authorizations(disbursement_id), disbursement_transfers(disbursement_id)
create table public.disbursements (
  id uuid not null default gen_random_uuid (),
  cash_advance_id uuid not null,
  status public.disbursement_status not null default 'pending'::disbursement_status,
  amount numeric not null,
  completed_at timestamp with time zone null,
  metadata jsonb null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint disbursements_pkey primary key (id),
  constraint disbursements_cash_advance_id_fkey foreign KEY (cash_advance_id) references cash_advances (id) on delete NO ACTION,
  constraint fk_cash_advance foreign KEY (cash_advance_id) references cash_advances (id) on delete CASCADE
) TABLESPACE pg_default;

-- Index for disbursements table
create index IF not exists idx_disbursements_cash_advance_id on public.disbursements using btree (cash_advance_id) TABLESPACE pg_default;

-- Trigger for disbursements table: Automatically updates the updated_at timestamp on modification.
create trigger update_disbursements_updated_at BEFORE
update on disbursements for EACH row
execute FUNCTION update_modified_column ();

-- ## Table: migrations
-- Purpose: Tracks database schema migrations that have been applied, ensuring migrations are run only once. Typically managed by a migration tool.
-- Relationships: None explicitly defined via foreign keys.
create table public.migrations (
  id serial not null,
  name text not null,
  applied_at timestamp with time zone not null default now(),
  constraint migrations_pkey primary key (id),
  constraint migrations_name_key unique (name)
) TABLESPACE pg_default;

-- ## Table: news
-- Purpose: Stores news items, updates, or articles to be displayed to users within the application. Includes content, publication status, and display properties.
-- Relationships:
--   - Referenced by: news_category_mappings(news_id), user_news_interactions(news_id)
create table public.news (
  id uuid not null default gen_random_uuid (),
  title text not null,
  description text not null,
  content jsonb not null,
  image_url text null,
  content_type public.news_content_type not null default 'update'::news_content_type,
  priority integer not null default 0,
  published_at timestamp with time zone not null default now(),
  expires_at timestamp with time zone null,
  is_active boolean not null default true,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint news_pkey primary key (id)
) TABLESPACE pg_default;

-- Indexes for news table
create index IF not exists news_published_at_idx on public.news using btree (published_at) TABLESPACE pg_default;
create index IF not exists news_is_active_idx on public.news using btree (is_active) TABLESPACE pg_default;
create index IF not exists news_content_type_idx on public.news using btree (content_type) TABLESPACE pg_default;

-- Trigger for news table: Automatically updates the updated_at timestamp on modification.
create trigger update_news_timestamp BEFORE
update on news for EACH row
execute FUNCTION update_timestamp (); -- Assuming update_timestamp() function exists and updates updated_at.

-- ## Table: news_categories
-- Purpose: Defines categories that can be assigned to news items for organization and filtering.
-- Relationships:
--   - Referenced by: news_category_mappings(category_id)
create table public.news_categories (
  id uuid not null default gen_random_uuid (),
  name text not null,
  description text null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint news_categories_pkey primary key (id),
  constraint news_categories_name_key unique (name)
) TABLESPACE pg_default;

-- Trigger for news_categories table: Automatically updates the updated_at timestamp on modification.
create trigger update_news_categories_timestamp BEFORE
update on news_categories for EACH row
execute FUNCTION update_timestamp (); -- Assuming update_timestamp() function exists and updates updated_at.

-- ## Table: news_category_mappings
-- Purpose: Creates a many-to-many relationship between news items and news categories. Allows a news item to belong to multiple categories.
-- Relationships:
--   - news_id: Foreign key referencing news(id), linking to the news item.
--   - category_id: Foreign key referencing news_categories(id), linking to the category.
create table public.news_category_mappings (
  news_id uuid not null,
  category_id uuid not null,
  constraint news_category_mappings_pkey primary key (news_id, category_id),
  constraint news_category_mappings_category_id_fkey foreign KEY (category_id) references news_categories (id) on delete CASCADE,
  constraint news_category_mappings_news_id_fkey foreign KEY (news_id) references news (id) on delete CASCADE
) TABLESPACE pg_default;

-- ## Table: notification_batches
-- Purpose: Defines batches of notifications to be sent to a target audience based on filters. Used for mass notification campaigns (e.g., promotions, announcements).
-- Relationships:
--   - created_by: Foreign key referencing admin_users(id) (ON DELETE SET NULL), indicating which administrator created the batch. If the admin is deleted, this link becomes NULL.
create table public.notification_batches (
  id uuid not null default gen_random_uuid (),
  name text not null,
  type public.notification_type not null,
  title text not null,
  message text not null,
  action_url text null,
  action_text text null,
  image_url text null,
  priority public.notification_priority not null default 'medium'::notification_priority,
  target_user_filter jsonb null default '{}'::jsonb,
  scheduled_at timestamp with time zone null,
  sent_at timestamp with time zone null,
  total_count integer null default 0,
  success_count integer null default 0,
  failure_count integer null default 0,
  created_by uuid null,
  status character varying(50) null default 'pending'::character varying,
  metadata jsonb null default '{}'::jsonb,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint notification_batches_pkey primary key (id),
  constraint fk_created_by foreign KEY (created_by) references admin_users (id) on delete set null
) TABLESPACE pg_default;


-- ## Table: notification_deliveries
-- Purpose: Tracks the delivery status of individual notifications across different channels (e.g., push, in-app, email). Logs attempts, success/failure, and external identifiers.
-- Relationships:
--   - notification_id: Foreign key referencing notifications(id), linking the delivery record to the specific notification being delivered.
create table public.notification_deliveries (
  id uuid not null default gen_random_uuid (),
  notification_id uuid not null,
  channel public.notification_channel not null,
  status public.notification_status not null default 'pending'::notification_status,
  external_id text null,
  attempt_count integer null default 0,
  last_attempted_at timestamp with time zone null,
  delivered_at timestamp with time zone null,
  error_message text null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint notification_deliveries_pkey primary key (id),
  constraint fk_notification foreign KEY (notification_id) references notifications (id) on delete CASCADE
) TABLESPACE pg_default;

-- Indexes for notification_deliveries table
create index IF not exists idx_notification_deliveries_notification_id on public.notification_deliveries using btree (notification_id) TABLESPACE pg_default;
create index IF not exists idx_notification_deliveries_channel on public.notification_deliveries using btree (channel) TABLESPACE pg_default;
create index IF not exists idx_notification_deliveries_status on public.notification_deliveries using btree (status) TABLESPACE pg_default;

-- ## Table: notification_queue
-- Purpose: Acts as a queue for notifications that need to be generated and sent based on templates and context. Processed by a background worker to create entries in the `notifications` table.
-- Relationships:
--   - user_id: Foreign key referencing users(id), specifying the recipient user.
--   - template_code: Foreign key referencing notification_templates(code), specifying the template to use.
--   - notification_id: Foreign key referencing notifications(id) (ON DELETE SET NULL), linking to the actual notification record once created. If the notification is deleted, this link becomes NULL.
create table public.notification_queue (
  id uuid not null default gen_random_uuid (),
  user_id uuid not null,
  template_code character varying(100) not null,
  context jsonb not null default '{}'::jsonb,
  channels notification_channel[] not null default '{in_app}'::notification_channel[],
  priority public.notification_priority not null default 'medium'::notification_priority,
  scheduled_at timestamp with time zone null default now(),
  processed_at timestamp with time zone null,
  notification_id uuid null,
  status character varying(50) null default 'pending'::character varying,
  error_message text null,
  created_at timestamp with time zone null default now(),
  constraint notification_queue_pkey primary key (id),
  constraint fk_notification foreign KEY (notification_id) references notifications (id) on delete set null,
  constraint fk_template foreign KEY (template_code) references notification_templates (code) on delete RESTRICT,
  constraint fk_user foreign KEY (user_id) references users (id) on delete CASCADE
) TABLESPACE pg_default;

-- Indexes for notification_queue table
create index IF not exists idx_notification_queue_status on public.notification_queue using btree (status) TABLESPACE pg_default;
create index IF not exists idx_notification_queue_scheduled_at on public.notification_queue using btree (scheduled_at) TABLESPACE pg_default;

-- ## Table: notification_templates
-- Purpose: Stores reusable templates for generating notification content (title, message, etc.). Allows for consistent messaging and easier management.
-- Relationships:
--   - Referenced by: notification_queue(template_code)
create table public.notification_templates (
  id uuid not null default gen_random_uuid (),
  code character varying(100) not null, -- Unique code used to reference the template
  type public.notification_type not null,
  title_template text not null,
  message_template text not null,
  action_url_template text null,
  action_text_template text null,
  default_image_url text null,
  default_priority public.notification_priority not null default 'medium'::notification_priority,
  default_channels notification_channel[] not null default '{in_app}'::notification_channel[],
  is_active boolean null default true,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint notification_templates_pkey primary key (id),
  constraint notification_templates_code_key unique (code)
) TABLESPACE pg_default;

-- ## Table: notifications
-- Purpose: Stores individual notifications generated for specific users. Contains the final content, read/dismissed status, and metadata.
-- Relationships:
--   - user_id: Foreign key referencing users(id), linking the notification to its recipient user.
--   - Referenced by: notification_deliveries(notification_id), notification_queue(notification_id)
create table public.notifications (
  id uuid not null default gen_random_uuid (),
  user_id uuid not null,
  type public.notification_type not null,
  title text not null,
  message text not null,
  action_url text null,
  action_text text null,
  image_url text null,
  priority public.notification_priority not null default 'medium'::notification_priority,
  is_read boolean null default false,
  is_dismissed boolean null default false,
  metadata jsonb null default '{}'::jsonb,
  created_at timestamp with time zone null default now(),
  read_at timestamp with time zone null,
  dismissed_at timestamp with time zone null,
  expires_at timestamp with time zone null,
  constraint notifications_pkey primary key (id),
  constraint fk_user foreign KEY (user_id) references users (id) on delete CASCADE,
  constraint notifications_user_id_fkey foreign KEY (user_id) references users (id) on delete NO ACTION
) TABLESPACE pg_default;

-- Indexes for notifications table
create index IF not exists idx_notifications_user_id on public.notifications using btree (user_id) TABLESPACE pg_default;
create index IF not exists idx_notifications_type on public.notifications using btree (type) TABLESPACE pg_default;
create index IF not exists idx_notifications_created_at on public.notifications using btree (created_at) TABLESPACE pg_default;
create index IF not exists idx_notifications_is_read on public.notifications using btree (is_read) TABLESPACE pg_default;
create index IF not exists idx_notifications_expires_at on public.notifications using btree (expires_at) TABLESPACE pg_default;

-- Trigger for notifications table: Deletes expired notifications after insertion.
create trigger trigger_delete_expired_notifications
after INSERT on notifications for EACH STATEMENT
execute FUNCTION delete_expired_notifications (); -- Assuming delete_expired_notifications() function exists.

-- ## Table: plaid_items
-- Purpose: Stores information about Plaid Items, representing a connection to a financial institution for a specific user. Includes access tokens, item IDs, and linked account details. This seems to represent the primary linked account for a user.
-- Relationships:
--   - user_id: Foreign key referencing users(id), linking the Plaid item (bank connection) to the user. Has a unique constraint, implying one primary Plaid item per user in this table.
--   - Referenced by: cash_advances(plaid_item_id)
create table public.plaid_items (
  id uuid not null default gen_random_uuid (),
  user_id uuid not null,
  access_token text not null,
  item_id text not null,
  institution_id text null,
  institution_name text null,
  account_id text not null,
  account_name text null,
  account_mask text null,
  account_subtype text null,
  verification_status text null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  status text null,
  official_name text null,
  iso_currency_code text null,
  unofficial_currency_code text null,
  balance_available numeric(18, 2) null,
  balance_current numeric(18, 2) null,
  balance_limit numeric(18, 2) null,
  ach_account_number text null,
  ach_routing_number text null,
  wire_routing text null,
  is_tokenized_account_number boolean not null default false,
  verification_insights jsonb null,
  auth_method text null,
  last_auth_retrieved_at timestamp with time zone null,
  oauth_state_id character varying(255) null,
  is_oauth_connection boolean null default false,
  oauth_consent_expiration_time timestamp without time zone null,
  oauth_last_consent_update timestamp without time zone null,
  rtp_credit_supported boolean null default null, -- Whether the institution supports receiving RTP credit transfers for this account
  last_capabilities_check_at timestamp with time zone null, -- Timestamp of the last /transfer/capabilities/get check
  last_capabilities_check_request_id text null, -- Plaid request_id from the last capabilities check
  constraint plaid_items_pkey primary key (id),
  constraint plaid_items_user_id_key unique (user_id),
  constraint plaid_items_user_id_fkey foreign KEY (user_id) references users (id) on delete CASCADE
) TABLESPACE pg_default;

-- Indexes for plaid_items table
CREATE INDEX IF NOT EXISTS idx_plaid_items_created_at_desc ON public.plaid_items USING btree (created_at DESC) TABLESPACE pg_default;

-- ## Table: plaid_link_tokens
-- Purpose: Stores Plaid Link tokens generated for users to initiate the Plaid Link flow for connecting bank accounts. These tokens are short-lived.
-- Relationships:
--   - user_id: Foreign key referencing users(id) (ON DELETE CASCADE), linking the token to the user initiating the flow. If the user is deleted, associated tokens are removed.
create table public.plaid_link_tokens (
  id bigserial not null,
  user_id uuid null, -- Nullable? Might be generated before user creation/login in some flows.
  link_token text not null,
  expiration timestamp with time zone null,
  created_at timestamp with time zone not null default now(),
  constraint plaid_link_tokens_pkey primary key (id),
  constraint plaid_link_tokens_user_id_fkey foreign KEY (user_id) references users (id) on delete CASCADE
) TABLESPACE pg_default;


-- ## Table: plaid_oauth_institutions
-- Purpose: Stores information about financial institutions supported by Plaid, specifically focusing on their OAuth support status and details. Helps manage OAuth connections and migrations.
-- Relationships: None explicitly defined via foreign keys. Likely used as a reference table.
create table public.plaid_oauth_institutions (
  id uuid not null default uuid_generate_v4 (),
  institution_id text not null, -- Plaid's unique ID for the institution
  name text not null,
  country_code text null default 'US'::text,
  products text[] null default array[]::text[],
  url text null,
  primary_color text null,
  logo_base64 text null,
  oauth_supported boolean null default false,
  oauth_migration_status text null,
  supported_auth_methods jsonb null,
  status_health jsonb null,
  last_updated timestamp with time zone null default CURRENT_TIMESTAMP,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  constraint plaid_oauth_institutions_pkey primary key (id),
  constraint plaid_oauth_institutions_institution_id_key unique (institution_id),
  constraint plaid_oauth_institutions_oauth_migration_status_check check (
    (
      oauth_migration_status = any (
        array[
          'not_started'::text,
          'in_progress'::text,
          'completed'::text
        ]
      )
    )
  )
) TABLESPACE pg_default;

-- Indexes for plaid_oauth_institutions table
create index IF not exists idx_plaid_oauth_institutions_name on public.plaid_oauth_institutions using btree (name) TABLESPACE pg_default;
create index IF not exists idx_plaid_oauth_institutions_oauth_supported on public.plaid_oauth_institutions using btree (oauth_supported) TABLESPACE pg_default;

-- ## Table: plaid_processed_webhook_events
-- Purpose: Logs Plaid webhook events related to transfers that have been successfully processed by the application. This prevents duplicate processing of the same event.
-- Relationships: None explicitly defined via foreign keys. Relies on `event_id`, `transfer_id`, `event_type` for uniqueness.
create table public.plaid_processed_webhook_events (
  id uuid not null default gen_random_uuid (),
  event_id text not null, -- Unique ID from Plaid for the specific event instance
  transfer_id text not null,
  webhook_type text not null,
  webhook_code text not null,
  event_type text not null,
  payload jsonb not null,
  created_at timestamp with time zone not null default now(),
  constraint plaid_processed_webhook_events_pkey primary key (id),
  constraint unique_webhook_event unique (event_id, transfer_id, event_type) -- Ensures event uniqueness
) TABLESPACE pg_default;

-- Indexes for plaid_processed_webhook_events table
create index IF not exists idx_plaid_webhook_transfer_id on public.plaid_processed_webhook_events using btree (transfer_id) TABLESPACE pg_default;
create index IF not exists idx_plaid_webhook_event_id on public.plaid_processed_webhook_events using btree (event_id) TABLESPACE pg_default;

-- ## Table: repayment_authorizations
-- Purpose: Records authorization attempts made via Plaid Transfer API for collecting repayments for a cash advance. Stores details of the authorization decision.
-- Relationships:
--   - repayment_id: Foreign key referencing repayments(id), linking the authorization attempt to a specific scheduled repayment.
--   - Referenced by: repayment_transfers(repayment_authorization_id)
create table public.repayment_authorizations (
  id uuid not null default gen_random_uuid (),
  repayment_id uuid not null,
  plaid_authorization_id text null,
  amount numeric not null,
  network text not null,
  decision text null,
  rationale_code text null,
  rationale_description text null,
  raw_response jsonb null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint repayment_authorizations_pkey primary key (id),
  constraint fk_repayment foreign KEY (repayment_id) references repayments (id) on delete CASCADE,
  constraint repayment_authorizations_repayment_id_fkey foreign KEY (repayment_id) references repayments (id) on delete NO ACTION
) TABLESPACE pg_default;

-- Trigger for repayment_authorizations table: Automatically updates the updated_at timestamp on modification.
create trigger update_repayment_authorizations_updated_at BEFORE
update on repayment_authorizations for EACH row
execute FUNCTION update_modified_column (); -- Assuming update_modified_column() function exists and updates updated_at.

-- ## Table: repayment_balance_checks
-- Purpose: Logs the results of balance checks performed before attempting a repayment collection. Helps determine if sufficient funds are likely available.
-- Relationships:
--   - repayment_id: Foreign key referencing repayments(id), linking the balance check to the specific repayment attempt it precedes.
create table public.repayment_balance_checks (
  id uuid not null default gen_random_uuid (),
  repayment_id uuid not null,
  account_balance numeric null,
  balance_sufficient boolean not null,
  plaid_response jsonb null,
  created_at timestamp with time zone not null default now(),
  constraint repayment_balance_checks_pkey primary key (id),
  constraint fk_repayment foreign KEY (repayment_id) references repayments (id) on delete CASCADE,
  constraint repayment_balance_checks_repayment_id_fkey foreign KEY (repayment_id) references repayments (id) on delete NO ACTION
) TABLESPACE pg_default;

-- ## Table: repayment_transfers
-- Purpose: Records the actual Plaid transfer attempts associated with collecting a repayment, linked to a specific repayment authorization. Tracks the transfer status.
-- Relationships:
--   - repayment_id: Foreign key referencing repayments(id), linking the transfer back to the overall scheduled repayment.
--   - repayment_authorization_id: Foreign key referencing repayment_authorizations(id), linking the transfer to its specific authorization record.
create table public.repayment_transfers (
  id uuid not null default gen_random_uuid (),
  repayment_id uuid not null,
  repayment_authorization_id uuid not null,
  plaid_transfer_id text null,
  amount numeric not null,
  status text not null,
  description text null,
  raw_response jsonb null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint repayment_transfers_pkey primary key (id),
  constraint fk_repayment foreign KEY (repayment_id) references repayments (id) on delete CASCADE,
  constraint fk_repayment_authorization foreign KEY (repayment_authorization_id) references repayment_authorizations (id) on delete CASCADE,
  constraint repayment_transfers_repayment_authorization_id_fkey foreign KEY (repayment_authorization_id) references repayment_authorizations (id) on delete NO ACTION,
  constraint repayment_transfers_repayment_id_fkey foreign KEY (repayment_id) references repayments (id) on delete NO ACTION
) TABLESPACE pg_default;

-- Index for repayment_transfers table
create index IF not exists idx_repayment_transfers_plaid_transfer_id on public.repayment_transfers using btree (plaid_transfer_id) TABLESPACE pg_default;

-- Trigger for repayment_transfers table: Automatically updates the updated_at timestamp on modification.
create trigger update_repayment_transfers_updated_at BEFORE
update on repayment_transfers for EACH row
execute FUNCTION update_modified_column (); -- Assuming update_modified_column() function exists and updates updated_at.

-- ## Table: repayments
-- Purpose: Represents scheduled or attempted repayments for a cash advance. Tracks the due date, amount, status, attempt count, and completion details.
-- Relationships:
--   - cash_advance_id: Foreign key referencing cash_advances(id), linking the repayment schedule to the specific cash advance.
--   - user_id: Foreign key referencing users(id), linking the repayment to the user (denormalized, also available via cash_advance_id -> user_id).
--   - plaid_item_id: Foreign key referencing plaid_items(id) (ON DELETE SET NULL), linking to the Plaid item used for repayment attempts (potentially same as cash_advance.plaid_item_id, but could differ if updated). If the Plaid item is deleted, this link becomes NULL.
--   - Referenced by: repayment_authorizations(repayment_id), repayment_balance_checks(repayment_id), repayment_transfers(repayment_id)
create table public.repayments (
  id uuid not null default gen_random_uuid (),
  cash_advance_id uuid not null,
  user_id uuid not null,
  plaid_item_id uuid null,
  scheduled_date date not null,
  amount numeric not null,
  status public.repayment_status not null default 'scheduled'::repayment_status,
  attempt_count integer not null default 0,
  grace_period_days integer not null default 0,
  penalty_fee numeric not null default 0,
  last_attempt_at timestamp with time zone null,
  completed_at timestamp with time zone null,
  metadata jsonb null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint repayments_pkey primary key (id),
  constraint fk_cash_advance foreign KEY (cash_advance_id) references cash_advances (id) on delete CASCADE,
  constraint repayments_cash_advance_id_fkey foreign KEY (cash_advance_id) references cash_advances (id) on delete NO ACTION,
  constraint fk_user foreign KEY (user_id) references users (id) on delete CASCADE, -- Added constraint for user_id
  constraint fk_plaid_item foreign KEY (plaid_item_id) references plaid_items (id) on delete set null, -- Added constraint for plaid_item_id
  constraint repayments_cash_advance_id_fkey foreign KEY (cash_advance_id) references cash_advances (id)
) TABLESPACE pg_default;

-- Indexes for repayments table
create index IF not exists idx_repayments_cash_advance_id on public.repayments using btree (cash_advance_id) TABLESPACE pg_default;
create index IF not exists idx_repayments_user_id on public.repayments using btree (user_id) TABLESPACE pg_default;
create index IF not exists idx_repayments_scheduled_date on public.repayments using btree (scheduled_date) TABLESPACE pg_default;
create index IF not exists idx_repayments_status on public.repayments using btree (status) TABLESPACE pg_default;

-- Trigger for repayments table: Automatically updates the updated_at timestamp on modification.
create trigger update_repayments_updated_at BEFORE
update on repayments for EACH row
execute FUNCTION update_modified_column (); -- Assuming update_modified_column() function exists and updates updated_at.

-- ## Table: risk_score_audits
-- Purpose: Logs snapshots of calculated risk scores and underlying metrics for users. Includes the calculated Blink Score, component points, raw metrics, system recommendations, and any administrative overrides.
-- Relationships:
--   - user_id: Foreign key referencing users(id), linking the audit record to the specific user whose score was calculated.
--   - asset_report_id: Foreign key referencing asset_reports(id) (optional), linking to the asset report used for the score calculation if applicable.
--   - admin_user_id: Foreign key referencing admin_users(id) (optional), linking to the administrator who may have reviewed or overridden the score/recommendation.
create table public.risk_score_audits (
  id uuid not null default gen_random_uuid(),
  user_id uuid not null,
  snapshot_timestamp timestamp with time zone not null,
  asset_report_id uuid null,
  metric_observed_history_days integer null,
  metric_median_paycheck numeric null,
  metric_paycheck_regularity numeric null,
  metric_days_since_last_paycheck integer null,
  metric_overdraft_count90 integer null,
  metric_net_cash30 numeric null,
  metric_debt_load30 numeric null,
  metric_volatility90 numeric null,
  points_observed_history integer null,
  points_median_paycheck integer null,
  points_paycheck_regularity integer null,
  points_days_since_last_paycheck integer null,
  points_overdraft_count90 integer null,
  points_net_cash30 integer null,
  points_debt_load30 integer null,
  points_volatility90 integer null,
  base_score integer null,
  blink_score_s numeric null, -- This seems to be the final Blink Score
  system_recommendation text null,
  admin_user_id uuid null,
  admin_decision public.approval_status_enum null, -- Assuming approval_status_enum based on usage elsewhere
  admin_decision_reason text null,
  admin_decision_timestamp timestamp with time zone null,
  calculation_engine_version character varying null,
  metric_clean_buffer7 numeric null,
  metric_buffer_volatility numeric null,
  points_liquidity integer null,
  metric_deposit_multiplicity30 numeric null,
  points_deposit_multiplicity integer null,
  flag_od_vol boolean null,
  flag_cash_crunch boolean null,
  flag_debt_trap boolean null,
  created_at timestamp with time zone not null default now(),
  constraint risk_score_audits_pkey primary key (id),
  constraint fk_user foreign key (user_id) references users(id) on delete cascade,
  constraint fk_asset_report foreign key (asset_report_id) references asset_reports(id) on delete set null,
  constraint fk_admin_user foreign key (admin_user_id) references admin_users(id) on delete set null
) TABLESPACE pg_default;

-- Indexes for risk_score_audits table
CREATE INDEX IF NOT EXISTS idx_risk_score_audits_user_id ON public.risk_score_audits USING btree (user_id) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_risk_score_audits_admin_user_id ON public.risk_score_audits USING btree (admin_user_id) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_risk_score_audits_blink_score_s ON public.risk_score_audits USING btree (blink_score_s) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_risk_score_audits_created_at ON public.risk_score_audits USING btree (created_at) TABLESPACE pg_default;

-- ## Table: transfer_event_cursor
-- Purpose: Stores the last processed Plaid transfer event ID for each environment (sandbox, development, production). Used by a background process to poll for new transfer events without processing duplicates.
-- Relationships: None explicitly defined via foreign keys.
create table public.transfer_event_cursor (
  id serial not null,
  environment text not null, -- e.g., 'sandbox', 'development', 'production'
  last_event_id bigint not null default 0,
  updated_at timestamp with time zone not null,
  constraint transfer_event_cursor_pkey primary key (id),
  constraint transfer_event_cursor_environment_check check (
    (
      environment = any (
        array[
          'sandbox'::text,
          'development'::text,
          'production'::text
        ]
      )
    )
  )
) TABLESPACE pg_default;

-- Index for transfer_event_cursor table
create index IF not exists transfer_event_cursor_environment_idx on public.transfer_event_cursor using btree (environment) TABLESPACE pg_default;

-- ## Table: user_cash_advance_approvals
-- Purpose: Records the approval or rejection status of a user's eligibility for cash advances, potentially performed manually by an administrator.
-- Relationships:
--   - user_id: Foreign key referencing users(id), linking the approval record to the specific user.
--   - performed_by: Foreign key referencing admin_users(id), linking to the administrator who made the approval/rejection decision.
create table public.user_cash_advance_approvals (
  id bigserial not null,
  user_id uuid not null,
  status public.approval_status_enum not null,
  performed_by uuid null,
  reason text null,
  created_at timestamp with time zone not null default now(),
  constraint user_cash_advance_approvals_pkey primary key (id),
  constraint user_cash_advance_approvals_performed_by_fkey foreign KEY (performed_by) references admin_users (id) on delete NO ACTION,
  constraint user_cash_advance_approvals_user_id_fkey foreign KEY (user_id) references users (id) on delete CASCADE
) TABLESPACE pg_default;

-- Indexes for user_cash_advance_approvals table
create index IF not exists idx_cash_advance_approvals_performed_by on public.user_cash_advance_approvals using btree (performed_by) TABLESPACE pg_default;
create index IF not exists idx_cash_advance_approvals_user on public.user_cash_advance_approvals using btree (user_id) TABLESPACE pg_default;


-- ## Table: user_devices
-- Purpose: Stores information about devices (e.g., mobile phones) registered by users, primarily for sending push notifications.
-- Relationships:
--   - user_id: Foreign key referencing users(id), linking the device to the user.
create table public.user_devices (
  id uuid not null default gen_random_uuid (),
  user_id uuid not null,
  device_token text not null,
  device_type character varying(50) not null,
  is_active boolean null default true,
  last_used_at timestamp with time zone null default now(),
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint user_devices_pkey primary key (id),
  constraint unique_device_token unique (device_token),
  constraint fk_user foreign KEY (user_id) references users (id) on delete CASCADE
) TABLESPACE pg_default;

-- Indexes for user_devices table
create index IF not exists idx_user_devices_user_id on public.user_devices using btree (user_id) TABLESPACE pg_default;
create index IF not exists idx_user_devices_is_active on public.user_devices using btree (is_active) TABLESPACE pg_default;


-- ## Table: user_hourly_stats
-- Purpose: Aggregates statistics on an hourly basis, such as the number of new user signups and new bank connections. Used for monitoring and reporting growth trends.
-- Relationships: None explicitly defined via foreign keys. Time-series data.
create table public.user_hourly_stats (
  hour_timestamp timestamp with time zone not null, -- The beginning of the hour for which stats are recorded
  new_users_count integer not null default 0,
  new_bank_connections_count integer not null default 0,
  created_at timestamp with time zone not null default now(),
  constraint user_hourly_stats_pkey primary key (hour_timestamp)
) TABLESPACE pg_default;

-- Index for user_hourly_stats table
create index IF not exists user_hourly_stats_timestamp_idx on public.user_hourly_stats using btree (hour_timestamp desc) TABLESPACE pg_default;


-- ## Table: user_news_interactions
-- Purpose: Tracks user interactions with news items, specifically recording whether a user has viewed or dismissed a particular news article.
-- Relationships:
--   - user_id: Foreign key referencing users(id), linking the interaction to the user.
--   - news_id: Foreign key referencing news(id), linking the interaction to the news item.
create table public.user_news_interactions (
  user_id uuid not null,
  news_id uuid not null,
  viewed boolean not null default false,
  viewed_at timestamp with time zone null,
  dismissed boolean not null default false,
  dismissed_at timestamp with time zone null,
  constraint user_news_interactions_pkey primary key (user_id, news_id),
  constraint user_news_interactions_news_id_fkey foreign KEY (news_id) references news (id) on delete CASCADE,
  constraint user_news_interactions_user_id_fkey foreign KEY (user_id) references users (id) on delete CASCADE
) TABLESPACE pg_default;

-- Index for user_news_interactions table
create index IF not exists user_news_interactions_viewed_idx on public.user_news_interactions using btree (viewed) TABLESPACE pg_default;

-- ## Table: user_notification_preferences
-- Purpose: Stores user-specific preferences for receiving different types of notifications across various channels (in-app, push, email, sms).
-- Relationships:
--   - user_id: Foreign key referencing users(id), linking the preferences to the user. This is also the primary key, ensuring one preference record per user.
create table public.user_notification_preferences (
  user_id uuid not null,
  advance_approval boolean null default true, -- Preference for cash advance approval notifications
  funds_deposited boolean null default true,
  repayment_reminder boolean null default true,
  insufficient_balance boolean null default true,
  marketing boolean null default true,
  news boolean null default true,
  system boolean null default true,
  in_app_enabled boolean null default true,
  push_enabled boolean null default true,
  email_enabled boolean null default true,
  sms_enabled boolean null default true,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint user_notification_preferences_pkey primary key (user_id),
  constraint fk_user foreign KEY (user_id) references users (id) on delete CASCADE
) TABLESPACE pg_default;

-- ## Table: user_otps
-- Purpose: Stores One-Time Passwords (OTPs) generated for users for various verification purposes (e.g., phone verification, login). Tracks the code, type, usage status, and expiration.
-- Relationships:
--   - user_id: Foreign key referencing users(id), linking the OTP to the user it was generated for.
create table public.user_otps (
  id bigserial not null,
  user_id uuid not null,
  otp_code text not null,
  otp_type text not null,
  is_used boolean not null default false,
  expires_at timestamp with time zone not null,
  created_at timestamp with time zone not null default now(),
  constraint user_otps_pkey primary key (id),
  constraint user_otps_user_id_fkey foreign KEY (user_id) references users (id) on delete CASCADE
) TABLESPACE pg_default;


-- ## Table: user_sessions
-- Purpose: Stores active session information for regular users, managing their login state using refresh tokens. Tracks token revocation status.
-- Relationships:
--   - user_id: Foreign key referencing users(id), linking the session to the specific user.
create table public.user_sessions (
  id uuid not null default gen_random_uuid (),
  user_id uuid not null,
  refresh_token text not null,
  expires_at timestamp with time zone not null,
  revoked boolean not null default false,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint user_sessions_pkey primary key (id),
  constraint user_sessions_refresh_token_key unique (refresh_token),
  constraint user_sessions_user_id_fkey foreign KEY (user_id) references users (id) on delete CASCADE
) TABLESPACE pg_default;

-- Index for user_sessions table
create index IF not exists idx_user_sessions_user_id on public.user_sessions using btree (user_id) TABLESPACE pg_default;

-- ## Table: users
-- Purpose: Stores core information about application users, including contact details, profile information, verification status, and agreement to terms. This is a central table referenced by many others.
-- Relationships:
--   - Referenced by: admin_audit_logs(target_user_id), asset_reports(user_id), cash_advances(user_id), notification_queue(user_id), notifications(user_id), plaid_items(user_id), plaid_link_tokens(user_id), repayments(user_id), user_cash_advance_approvals(user_id), user_devices(user_id), user_news_interactions(user_id), user_notification_preferences(user_id), user_otps(user_id), user_sessions(user_id)
create table public.users (
  id uuid not null default gen_random_uuid (),
  email text not null,
  phone_number text null,
  hashed_password text null,
  first_name text not null,
  last_name text not null,
  state public.state_enum not null,
  zip_code text not null,
  is_email_verified boolean not null default false,
  is_phone_verified boolean not null default false,
  agreed_tos boolean not null default false,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  is_sso_user boolean not null default false,
  image_url text null,
  apple_id character varying(255) null,
  constraint users_pkey primary key (id),
  constraint users_email_key unique (email)
) TABLESPACE pg_default;

-- Indexes for users table
CREATE INDEX IF NOT EXISTS idx_users_state ON public.users USING btree (state) TABLESPACE pg_default;

-- Trigger for users table: Automatically creates default notification preferences for a new user upon insertion.
create trigger trigger_create_user_notification_preferences
after INSERT on users for EACH row
execute FUNCTION create_user_notification_preferences (); -- Assuming create_user_notification_preferences() function exists.

-- ## Table: webhook_queue
-- Purpose: Acts as an ingestion queue for incoming webhooks (e.g., from Plaid). Stores the raw payload and processing status, allowing for asynchronous and reliable webhook handling.
-- Relationships: None explicitly defined via foreign keys.
create table public.webhook_queue (
  id uuid not null, -- Assuming this ID comes from the webhook source or is generated uniquely upon receipt
  webhook_type text not null, -- Source system or type (e.g., 'PLAID')
  webhook_code text not null,
  payload jsonb not null,
  status text not null,
  error text null,
  created_at timestamp with time zone not null,
  updated_at timestamp with time zone not null,
  processed_at timestamp with time zone null,
  constraint webhook_queue_pkey primary key (id),
  constraint webhook_queue_status_check check (
    (
      status = any (
        array[
          'pending'::text,
          'processed'::text,
          'failed'::text
        ]
      )
    )
  )
) TABLESPACE pg_default;

-- Indexes for webhook_queue table
create index IF not exists webhook_queue_status_idx on public.webhook_queue using btree (status) TABLESPACE pg_default;
create index IF not exists webhook_queue_created_at_idx on public.webhook_queue using btree (created_at) TABLESPACE pg_default;
create index IF not exists webhook_queue_type_code_idx on public.webhook_queue using btree (webhook_type, webhook_code) TABLESPACE pg_default;
create index IF not exists webhook_queue_payload_idx on public.webhook_queue using gin (payload jsonb_path_ops) TABLESPACE pg_default; -- GIN index for querying payload content

-- ## Table: admin_balance_checks_log
-- Purpose: Logs the results of real-time balance checks initiated by administrators via the API.
--          Stores a snapshot of the balance for each account checked, along with basic user info at the time of check.
-- Relationships:
--   - admin_id: Foreign key referencing admin_users(id), linking the log entry to the admin who performed the check.
--   - target_user_id: Foreign key referencing users(id), linking the log entry to the user whose balance was checked.
CREATE TABLE public.admin_balance_checks_log (
    id bigserial NOT NULL,
    admin_id uuid NOT NULL,                          -- Admin who initiated the check
    target_user_id uuid NOT NULL,                    -- User whose balance was checked
    target_user_first_name text NULL,                -- User's first name at time of check
    target_user_last_name text NULL,                 -- User's last name at time of check
    target_user_state text NULL,                     -- User's state at time of check
    target_user_zip_code text NULL,                  -- User's zip code at time of check
    plaid_account_id text NOT NULL,                  -- Plaid's ID for the specific account
    plaid_item_id text NULL,                         -- Plaid's ID for the linked item (bank connection)
    balance_current numeric(18, 2) NULL,             -- Current balance reported by Plaid (can be null)
    balance_available numeric(18, 2) NULL,           -- Available balance reported by Plaid (can be null)
    iso_currency_code text NULL,                     -- ISO currency code
    unofficial_currency_code text NULL,              -- Unofficial currency code
    check_timestamp timestamp with time zone NOT NULL DEFAULT now(), -- When the check was performed
    plaid_request_id text NULL,                      -- Plaid's request_id for troubleshooting
    CONSTRAINT admin_balance_checks_log_pkey PRIMARY KEY (id),
    CONSTRAINT fk_admin_user FOREIGN KEY (admin_id) REFERENCES admin_users(id) ON DELETE SET NULL, -- Keep log even if admin deleted
    CONSTRAINT fk_target_user FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE CASCADE -- Remove logs if target user deleted
);

-- Indexes for admin_balance_checks_log table
CREATE INDEX IF NOT EXISTS idx_admin_balance_checks_log_admin_id ON public.admin_balance_checks_log USING btree (admin_id);
CREATE INDEX IF NOT EXISTS idx_admin_balance_checks_log_target_user_id ON public.admin_balance_checks_log USING btree (target_user_id);
CREATE INDEX IF NOT EXISTS idx_admin_balance_checks_log_timestamp ON public.admin_balance_checks_log USING btree (check_timestamp);
CREATE INDEX IF NOT EXISTS idx_admin_balance_checks_log_plaid_account_id ON public.admin_balance_checks_log USING btree (plaid_account_id);

-- ## Table: collections_queue (ADDED BASED ON RECONCILIATION)
-- Purpose: Manages repayments that have entered a collections process, likely after failing standard repayment attempts. Tracks assignment and status.
-- Relationships:
--   - repayment_id: Foreign key referencing repayments(id), linking the collections entry to the specific overdue repayment.
--   - assigned_to: Foreign key referencing admin_users(id) (likely, needs verification), indicating the admin responsible for this collection case.
create table public.collections_queue (
  repayment_id uuid not null,
  amount_due numeric not null,
  assigned_to uuid null,
  status character varying not null default 'pending'::character varying, -- Consider creating a specific ENUM type
  escalated_at timestamp with time zone not null,
  updated_at timestamp with time zone not null default now(),
  constraint collections_queue_pkey primary key (repayment_id), -- Assuming repayment_id is PK
  constraint fk_repayment foreign KEY (repayment_id) references repayments (id) on delete CASCADE
  -- constraint fk_assigned_admin foreign KEY (assigned_to) references admin_users (id) on delete set null -- Potential FK
);
COMMENT ON TABLE public.collections_queue IS 'Queue for managing escalated repayment collections.';

-- Indexes for collections_queue table (Example - Adjust as needed)
create index IF not exists idx_collections_queue_status on public.collections_queue using btree (status) TABLESPACE pg_default;
create index IF not exists idx_collections_queue_assigned_to on public.collections_queue using btree (assigned_to) TABLESPACE pg_default;

-- ## Table: worker_control (ADDED BASED ON RECONCILIATION)
-- Purpose: Provides a mechanism to enable or disable specific background workers or jobs within the system.
-- Relationships: None explicit via FK. Relies on worker_name as identifier.
create table public.worker_control (
  worker_name text not null,
  is_enabled boolean not null default true,
  updated_at timestamp with time zone not null default now(),
  constraint worker_control_pkey primary key (worker_name)
);
COMMENT ON TABLE public.worker_control IS 'Control table to enable/disable background workers/jobs.';

## Table List
- admin_audit_logs
- admin_balance_checks_log
- admin_sessions
- admin_users
- asset_report_account_historical_balances
- asset_report_accounts
- asset_report_items
- asset_report_transactions
- asset_reports
- cash_advances
- collections_queue -- ADDED
- disbursement_authorizations
- disbursement_transfers
- disbursements
- migrations
- news
- news_categories
- news_category_mappings
- notification_batches
- notification_deliveries
- notification_queue
- notification_templates
- notifications
- plaid_items
- plaid_link_tokens
- plaid_oauth_institutions
- plaid_processed_webhook_events
- repayment_authorizations
- repayment_balance_checks
- repayment_transfers
- repayments
- risk_score_audits
- transfer_event_cursor
- user_cash_advance_approvals
- user_devices
- user_hourly_stats
- user_news_interactions
- user_notification_preferences
- user_otps
- user_sessions
- users
- webhook_queue
- worker_control -- ADDED

-- ## Summary Table List (auto-generated from comments)
-- - admin_audit_logs: Tracks actions performed by administrators.
-- - admin_balance_checks_log: Logs the results of real-time balance checks initiated by administrators.
-- - admin_sessions: Stores active session information for administrators.
-- - admin_users: Stores information about administrator accounts.
-- - asset_report_account_historical_balances: Stores historical daily balances for accounts in an asset report.
-- - asset_report_accounts: Represents individual bank accounts within an asset report item.
-- - asset_report_items: Represents a financial institution connection within an asset report.
-- - asset_report_transactions: Stores transaction data associated with accounts in an asset report.
-- - asset_reports: Stores information about generated Plaid asset reports for users.
-- - cash_advances: Represents cash advance requests made by users.
-- - collections_queue: Manages repayments that have entered a collections process. -- ADDED
-- - disbursement_authorizations: Records Plaid authorization attempts for disbursing funds.
-- - disbursement_transfers: Records Plaid transfer attempts for disbursements.
-- - disbursements: Represents the process of disbursing funds for a cash advance.
-- - migrations: Tracks applied database schema migrations.
-- - news: Stores news items or articles for users.
-- - news_categories: Defines categories for news items.
-- - news_category_mappings: Many-to-many link between news and categories.
-- - notification_batches: Defines batches of notifications for mass campaigns.
-- - notification_deliveries: Tracks the delivery status of individual notifications.
-- - notification_queue: Queue for generating notifications based on templates.
-- - notification_templates: Stores reusable templates for notification content.
-- - notifications: Stores individual notifications generated for users.
-- - plaid_items: Stores Plaid Item connections (bank links) for users.
-- - plaid_link_tokens: Stores short-lived Plaid Link tokens.
-- - plaid_oauth_institutions: Stores information about Plaid-supported institutions, focusing on OAuth.
-- - plaid_processed_webhook_events: Logs processed Plaid transfer webhook events to prevent duplicates.
-- - repayment_authorizations: Records Plaid authorization attempts for collecting repayments.
-- - repayment_balance_checks: Logs balance check results before repayment attempts.
-- - repayment_transfers: Records Plaid transfer attempts for repayments.
-- - repayments: Represents scheduled or attempted repayments for a cash advance.
-- - risk_score_audits: Logs snapshots of calculated risk scores and underlying metrics for users.
-- - transfer_event_cursor: Stores the last processed Plaid transfer event ID per environment.
-- - user_cash_advance_approvals: Records approval/rejection status for user cash advance eligibility.
-- - user_devices: Stores user device information for push notifications.
-- - user_hourly_stats: Aggregates hourly statistics (new users, connections).
-- - user_news_interactions: Tracks user views/dismissals of news items.
-- - user_notification_preferences: Stores user-specific notification preferences.
-- - user_otps: Stores One-Time Passwords for user verification.
-- - user_sessions: Stores active session information for regular users.
-- - users: Stores core user information.
-- - webhook_queue: Ingestion queue for incoming webhooks.
-- - worker_control: Provides a mechanism to enable or disable specific background workers. -- ADDED

-- ## Trigger Function: update_asset_account_summary
-- Purpose: Recalculates and updates the pre-calculated summary columns 
--          (transactions_count, min_transaction_date, max_transaction_date, calculated_transaction_days_span) 
--          in the `asset_report_accounts` table whenever a change occurs in the related `asset_report_transactions`.
-- Called By Triggers: trigger_update_asset_account_summary_after_insert, 
--                     trigger_update_asset_account_summary_after_delete, 
--                     trigger_update_asset_account_summary_after_update
CREATE OR REPLACE FUNCTION public.update_asset_account_summary()
RETURNS TRIGGER AS $$
DECLARE
  v_account_id UUID;
BEGIN
  -- Determine the account ID to update based on the operation
  IF (TG_OP = 'DELETE') THEN
    v_account_id := OLD.asset_report_account_id;
  ELSE -- INSERT or UPDATE
    v_account_id := NEW.asset_report_account_id;
  END IF;

  IF v_account_id IS NULL THEN
    RAISE WARNING 'Trigger update_asset_account_summary called with NULL account_id. TG_OP: %', TG_OP;
    RETURN NULL;
  END IF;

  -- Recalculate the summary and update the asset_report_accounts table
  WITH summary AS (
    SELECT
      COUNT(t.transaction_id) AS transactions_count,
      MIN(t.date) AS min_transaction_date,
      MAX(t.date) AS max_transaction_date,
      CASE
        WHEN COUNT(t.transaction_id) > 0 THEN GREATEST(1, (MAX(t.date) - MIN(t.date) + 1))
        ELSE NULL
      END AS calculated_transaction_days_span
    FROM public.asset_report_transactions t
    WHERE t.asset_report_account_id = v_account_id
  )
  UPDATE public.asset_report_accounts a
  SET
    transactions_count = COALESCE(s.transactions_count, 0),
    min_transaction_date = s.min_transaction_date,
    max_transaction_date = s.max_transaction_date,
    calculated_transaction_days_span = s.calculated_transaction_days_span
  FROM summary s
  WHERE a.id = v_account_id;

  -- For UPDATE, if the account_id itself changed, update the OLD account summary too
  IF (TG_OP = 'UPDATE' AND OLD.asset_report_account_id IS DISTINCT FROM NEW.asset_report_account_id AND OLD.asset_report_account_id IS NOT NULL) THEN
      WITH old_summary AS (
        SELECT
          COUNT(t.transaction_id) AS transactions_count,
          MIN(t.date) AS min_transaction_date,
          MAX(t.date) AS max_transaction_date,
          CASE
            WHEN COUNT(t.transaction_id) > 0 THEN GREATEST(1, (MAX(t.date) - MIN(t.date) + 1))
            ELSE NULL
          END AS calculated_transaction_days_span
        FROM public.asset_report_transactions t
        WHERE t.asset_report_account_id = OLD.asset_report_account_id
      )
      UPDATE public.asset_report_accounts a
      SET
        transactions_count = COALESCE(os.transactions_count, 0),
        min_transaction_date = os.min_transaction_date,
        max_transaction_date = os.max_transaction_date,
        calculated_transaction_days_span = os.calculated_transaction_days_span
      FROM old_summary os
      WHERE a.id = OLD.asset_report_account_id;
  END IF;

  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
COMMENT ON FUNCTION public.update_asset_account_summary() IS 'Trigger function to recalculate and update summary columns (count, dates, span) in asset_report_accounts based on changes in asset_report_transactions.';

-- ## Triggers on asset_report_transactions (for summary update)
-- Purpose: These triggers ensure that the `update_asset_account_summary` function is called automatically 
--          after insert, delete, or relevant update operations on `asset_report_transactions` 
--          to keep the pre-calculated summary columns in `asset_report_accounts` up-to-date.

-- Trigger after INSERT
CREATE TRIGGER trigger_update_asset_account_summary_after_insert
AFTER INSERT ON public.asset_report_transactions
FOR EACH ROW
EXECUTE FUNCTION public.update_asset_account_summary();
COMMENT ON TRIGGER trigger_update_asset_account_summary_after_insert ON public.asset_report_transactions IS 'Updates asset_report_accounts summary after a transaction is inserted.';

-- Trigger after DELETE
CREATE TRIGGER trigger_update_asset_account_summary_after_delete
AFTER DELETE ON public.asset_report_transactions
FOR EACH ROW
EXECUTE FUNCTION public.update_asset_account_summary();
COMMENT ON TRIGGER trigger_update_asset_account_summary_after_delete ON public.asset_report_transactions IS 'Updates asset_report_accounts summary after a transaction is deleted.';

-- Trigger after UPDATE (only if relevant columns change)
CREATE TRIGGER trigger_update_asset_account_summary_after_update
AFTER UPDATE OF asset_report_account_id, date ON public.asset_report_transactions
FOR EACH ROW
EXECUTE FUNCTION public.update_asset_account_summary();
COMMENT ON TRIGGER trigger_update_asset_account_summary_after_update ON public.asset_report_transactions IS 'Updates asset_report_accounts summary after a transaction''s account_id or date is updated.';

-- ## Trigger Function: calculate_total_repayment_amount
-- Purpose: Calculates the total repayment amount for a cash advance.
CREATE OR REPLACE FUNCTION public.calculate_total_repayment_amount()
RETURNS TRIGGER AS $$
BEGIN
    NEW.total_repayment_amount = NEW.principal_amount + NEW.final_fee;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
COMMENT ON FUNCTION public.calculate_total_repayment_amount() IS 'Trigger function to calculate the total repayment amount for a cash advance.';

-- ## Trigger Function: update_modified_column
-- Purpose: Sets the updated_at column to the current timestamp. Used by various triggers.
CREATE OR REPLACE FUNCTION public.update_modified_column()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
   NEW.updated_at = now();
   RETURN NEW;
END;
$function$;
COMMENT ON FUNCTION public.update_modified_column() IS 'Sets the updated_at column to the current timestamp.';

-- ## Trigger Function: update_timestamp
-- Purpose: Sets the updated_at column to the current timestamp. (Potentially redundant with update_modified_column).
CREATE OR REPLACE FUNCTION public.update_timestamp()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$function$;
COMMENT ON FUNCTION public.update_timestamp() IS 'Sets the updated_at column to the current timestamp.';

-- ## Function: backfill_user_hourly_stats
-- Purpose: Backfills historical data into the user_hourly_stats table for a given date range.
CREATE OR REPLACE FUNCTION public.backfill_user_hourly_stats(backfill_start_date timestamp with time zone, backfill_end_date timestamp with time zone)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
DECLARE
    current_processing_hour timestamptz;
    next_processing_hour timestamptz;
    v_new_users_count int;
    v_new_connections_count int;
BEGIN
    -- Ensure the start date is truncated to the beginning of an hour
    current_processing_hour := date_trunc('hour', backfill_start_date);

    RAISE NOTICE 'Starting backfill from % up to (but not including) %', current_processing_hour, backfill_end_date;

    -- Loop through each hour from the start date up to the end date
    WHILE current_processing_hour < backfill_end_date LOOP
        next_processing_hour := current_processing_hour + interval '1 hour';

        -- Count new users created during this specific historical hour
        SELECT COUNT(*)
        INTO v_new_users_count
        FROM public.users
        WHERE created_at >= current_processing_hour
          AND created_at < next_processing_hour;

        -- Count distinct users who connected their first bank account during this specific historical hour
        SELECT COUNT(DISTINCT p.user_id)
        INTO v_new_connections_count
        FROM public.plaid_items p
        WHERE p.created_at >= current_processing_hour
          AND p.created_at < next_processing_hour;

        -- Insert the stats for the processed hour.
        -- ON CONFLICT DO NOTHING is safer for backfill in case of overlap or reruns.
        -- If a record for this hour already exists (e.g., from the hourly job), skip it.
        INSERT INTO public.user_hourly_stats (hour_timestamp, new_users_count, new_bank_connections_count, created_at)
        VALUES (current_processing_hour, v_new_users_count, v_new_connections_count, now())
        ON CONFLICT (hour_timestamp)
        DO NOTHING; -- Ignore duplicates during backfill

        -- Move to the next hour
        current_processing_hour := next_processing_hour;

        -- Optional: Add a small delay to prevent overloading the DB if backfilling many hours
        -- PERFORM pg_sleep(0.05); -- Sleep for 50 milliseconds

    END LOOP;

    RAISE NOTICE 'Backfill completed up to %', backfill_end_date;
END;
$function$;
COMMENT ON FUNCTION public.backfill_user_hourly_stats(timestamp with time zone, timestamp with time zone) IS 'Backfills historical data into the user_hourly_stats table for a given date range.';

-- ## Function: update_user_hourly_stats
-- Purpose: Calculates and updates the user_hourly_stats table for the most recently completed hour. Usually run by a scheduler.
CREATE OR REPLACE FUNCTION public.update_user_hourly_stats()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
DECLARE
    current_hour_start timestamptz;
    previous_hour_start timestamptz;
    v_new_users_count int;
    v_new_connections_count int;
BEGIN
    -- Calculate the start of the current and previous hours
    current_hour_start := date_trunc('hour', now());
    previous_hour_start := current_hour_start - interval '1 hour';

    -- Count new users created in the previous hour
    SELECT COUNT(*)
    INTO v_new_users_count
    FROM public.users
    WHERE created_at >= previous_hour_start
      AND created_at < current_hour_start;

    -- Count distinct users who connected their first bank account in the previous hour
    SELECT COUNT(DISTINCT p.user_id)
    INTO v_new_connections_count
    FROM public.plaid_items p
    WHERE p.created_at >= previous_hour_start
      AND p.created_at < current_hour_start;
      -- Note: If you only want to count the *very first time* a user ever connects,
      -- you might need a more complex check here involving user sign-up date
      -- or ensuring no prior plaid_items exist for that user before previous_hour_start.
      -- This version counts distinct users connecting within the specific hour.

    -- Insert or update the stats for the previous hour
    INSERT INTO public.user_hourly_stats (hour_timestamp, new_users_count, new_bank_connections_count, created_at)
    VALUES (previous_hour_start, v_new_users_count, v_new_connections_count, now())
    ON CONFLICT (hour_timestamp)
    DO UPDATE SET
        new_users_count = EXCLUDED.new_users_count,
        new_bank_connections_count = EXCLUDED.new_bank_connections_count,
        created_at = now(); -- Update the timestamp when the row is updated

    -- Optional: Log the action
    RAISE NOTICE 'Updated user_hourly_stats for hour: % | New Users: % | New Connections: %',
                 previous_hour_start, v_new_users_count, v_new_connections_count;

END;
$function$;
COMMENT ON FUNCTION public.update_user_hourly_stats() IS 'Calculates and updates the user_hourly_stats table for the most recently completed hour. Usually run by a scheduler.';

-- ## Trigger Function: delete_expired_notifications
-- Purpose: Deletes expired notifications from the notifications table.
CREATE OR REPLACE FUNCTION public.delete_expired_notifications()
RETURNS TRIGGER AS $$
BEGIN
-- BEGIN --
    DELETE FROM notifications
    WHERE expires_at IS NOT NULL
    AND expires_at < NOW();
    RETURN NULL;
-- END --
END;
$$ LANGUAGE plpgsql;
COMMENT ON FUNCTION public.delete_expired_notifications() IS 'Trigger function to delete expired notifications.';

-- ## Function: claim_asset_reports_to_fetch (ADDED BASED ON RECONCILIATION)
-- Purpose: Selects a batch of asset reports that need to be fetched from Plaid or further processed (e.g., expanding JSON data). Specifically targets Florida users and reports that haven't been fully processed. Used by a worker process.
CREATE OR REPLACE FUNCTION public.claim_asset_reports_to_fetch(_batch_size integer DEFAULT 30)
 RETURNS TABLE(asset_report_pk uuid, asset_report_token text)
 LANGUAGE plpgsql
AS $function$
begin
  return query
  select ar.id, ar.asset_report_token
  from asset_reports ar
  join users u on u.id = ar.user_id and u.state = 'Florida' -- Note: Hardcoded state filter
  where ar.asset_report_token is not null
    and (
      ar.raw_report_json is null -- Never fetched
      or not exists (           -- Or fetched but not fully exploded (missing accounts)
        select 1
        from asset_report_items ari
        join asset_report_accounts ara on ara.asset_report_item_id = ari.id
        where ari.asset_report_id = ar.id
      )
    )
  limit _batch_size;
end;
$function$;
COMMENT ON FUNCTION public.claim_asset_reports_to_fetch(integer) IS 'Selects a batch of asset reports (for Florida users) needing fetch/processing.';


-- ## Function: update_user_hourly_stats
-- ... existing code ...
COMMENT ON FUNCTION public.create_user_notification_preferences() IS 'Trigger function to create default notification preferences for a new user.';

-- ## Table: blink_repay_logs
-- Purpose: Logs events and activities related to the Blink Repay background process or worker.
-- Relationships: None.
create table public.blink_repay_logs (
  id uuid not null default gen_random_uuid(), -- Primary Key
  timestamp timestamp with time zone not null default now(), -- Event timestamp
  worker text not null, -- Identifier for the worker instance/type
  event_type text not null, -- Type of event (e.g., 'job_start', 'repayment_attempt', 'success', 'failure')
  details jsonb null, -- Additional context or error information
  created_at timestamp with time zone not null default now(), -- Record creation timestamp
  constraint blink_repay_logs_pkey primary key (id)
) TABLESPACE pg_default;

-- Indexes for blink_repay_logs table
-- CREATE UNIQUE INDEX blink_repay_logs_pkey ON public.blink_repay_logs USING btree (id) -- Implicit PK Index


-- ## Table: interval_metrics
-- Purpose: Stores aggregated user activity and application performance metrics calculated over specific time intervals (e.g., hourly, daily).
-- Relationships: None. Time-series data.
create table public.interval_metrics (
  interval_start_time timestamp with time zone not null, -- Primary Key & Start time of the interval
  total_downloads integer not null default 0,
  verified_emails integer not null default 0,
  banks_connected integer not null default 0,
  reports_created integer not null default 0,
  successful_reports_created integer not null default 0,
  florida_successful_reports integer not null default 0,
  approved_blinkers integer not null default 0,
  denied_blinkers integer not null default 0,
  active_blinkers integer not null default 0,
  active_blinkers_15_days integer not null default 0,
  active_blinkers_7_days integer not null default 0,
  active_blinkers_instant integer not null default 0,
  active_blinkers_standard integer not null default 0,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint interval_metrics_pkey primary key (interval_start_time)
) TABLESPACE pg_default;

-- Indexes for interval_metrics table
-- CREATE UNIQUE INDEX interval_metrics_pkey ON public.interval_metrics USING btree (interval_start_time) -- Implicit PK Index

-- Trigger for interval_metrics table: Automatically updates the updated_at timestamp on modification. (Needs verification if trigger exists)
-- create trigger update_interval_metrics_updated_at BEFORE
-- update on interval_metrics for EACH row
-- execute FUNCTION update_modified_column ();


-- ## Table: manual_balance_check_log
-- Purpose: Logs the results of automated balance checks performed before initiating a repayment collection. Differs from admin_balance_checks_log which logs checks initiated by admins.
-- Relationships:
--   - user_id: Foreign key referencing users(id).
create table public.manual_balance_check_log (
    id bigserial NOT NULL,                            -- Primary Key (auto-incrementing)
    user_id uuid NOT NULL,                            -- User whose balance was checked
    plaid_account_id text NOT NULL,                   -- Plaid's ID for the specific account
    "timestamp" timestamp with time zone NOT NULL DEFAULT now(), -- When the check was performed
    balance_available numeric(18, 2) NULL,            -- Available balance reported by Plaid
    balance_current numeric(18, 2) NULL,              -- Current balance reported by Plaid
    safe_to_withdraw_amount numeric NOT NULL,         -- Calculated amount deemed safe to withdraw
    iso_currency_code text NULL,                      -- ISO currency code
    target_repayment_amount numeric(18, 2) NULL,      -- The repayment amount being considered
    check_result text NOT NULL,                       -- Result (e.g., 'SAFE', 'UNSAFE', 'ERROR', 'INSUFFICIENT')
    performed_by_tool text NULL,                      -- Identifier for the tool/script performing the check
    plaid_request_id text NULL,                       -- Plaid's request_id for troubleshooting
    CONSTRAINT manual_balance_check_log_pkey PRIMARY KEY (id),
    CONSTRAINT fk_manual_balance_check_log_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE -- Confirmed FK. Assuming CASCADE based on prior context.
);

-- Indexes for manual_balance_check_log table
-- CREATE UNIQUE INDEX manual_balance_check_log_pkey ON public.manual_balance_check_log USING btree (id); -- Implicit PK Index
CREATE INDEX IF NOT EXISTS idx_manual_balance_check_log_user_id ON public.manual_balance_check_log USING btree (user_id);
CREATE INDEX IF NOT EXISTS idx_manual_balance_check_log_timestamp ON public.manual_balance_check_log USING btree ("timestamp");
CREATE INDEX IF NOT EXISTS idx_manual_balance_check_log_plaid_account_id ON public.manual_balance_check_log USING btree (plaid_account_id);
CREATE INDEX IF NOT EXISTS idx_manual_balance_check_log_result ON public.manual_balance_check_log USING btree (check_result); -- Renamed from previous guess


-- ## Table: migrations
-- ... existing code ...