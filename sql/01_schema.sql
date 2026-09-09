CREATE TABLE IF NOT EXISTS pipeline_runs (
 run_id CHAR(36) PRIMARY KEY, started_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
 completed_at TIMESTAMP(6) NULL, status VARCHAR(16) NOT NULL, source_hashes JSON NOT NULL,
 observation_start DATE NOT NULL, as_of_date DATE NOT NULL, summary JSON NULL
);
CREATE TABLE IF NOT EXISTS raw_records (
 source_name VARCHAR(32) NOT NULL, source_row INT NOT NULL, payload JSON NOT NULL,
 run_id CHAR(36) NOT NULL, PRIMARY KEY(source_name, source_row)
);
CREATE TABLE IF NOT EXISTS dim_customer (
 user_id VARCHAR(64) COLLATE utf8mb4_bin PRIMARY KEY, first_purchase_id VARCHAR(64) NOT NULL,
 first_purchase_date DATE NOT NULL, acquisition_line VARCHAR(32) NOT NULL,
 cohort_month DATE NOT NULL, INDEX idx_cohort_line(cohort_month, acquisition_line)
);
CREATE TABLE IF NOT EXISTS fact_purchase (
 purchase_id VARCHAR(64) COLLATE utf8mb4_bin PRIMARY KEY,
 user_id VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
 venue_id VARCHAR(64) NOT NULL, product_line VARCHAR(32) NOT NULL, purchase_date DATE NOT NULL,
 CONSTRAINT fk_customer FOREIGN KEY (user_id) REFERENCES dim_customer(user_id),
 INDEX idx_user_date_line(user_id, purchase_date, product_line),
 INDEX idx_date_line(purchase_date, product_line)
);
CREATE TABLE IF NOT EXISTS quarantine_purchase (
 purchase_id VARCHAR(64) COLLATE utf8mb4_bin PRIMARY KEY, user_id VARCHAR(64) NOT NULL,
 purchase_date DATE NOT NULL, reason VARCHAR(64) NOT NULL, payload JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS analysis_config (
 id INT PRIMARY KEY, observation_start DATE NOT NULL, as_of_date DATE NOT NULL, run_id CHAR(36) NOT NULL
);
CREATE TABLE IF NOT EXISTS mart_retention (
 cohort_month DATE NOT NULL, acquisition_line VARCHAR(32) NOT NULL, month_number INT NOT NULL,
 activity_month DATE NOT NULL, cohort_users INT NOT NULL, eligible TINYINT NOT NULL,
 platform_active_users INT NULL, same_line_active_users INT NULL,
 platform_retention DECIMAL(12,8) NULL, same_line_retention DECIMAL(12,8) NULL,
 PRIMARY KEY(cohort_month, acquisition_line, month_number)
);
CREATE TABLE IF NOT EXISTS mart_repurchase (
 acquisition_line VARCHAR(32) PRIMARY KEY, eligible_users INT NOT NULL,
 repeat_users_30d INT NOT NULL, cross_line_users_30d INT NOT NULL,
 repeat_rate_30d DECIMAL(12,8) NULL, cross_line_rate_30d DECIMAL(12,8) NULL
);
CREATE TABLE IF NOT EXISTS mart_monthly (
 activity_month DATE NOT NULL, product_line VARCHAR(32) NOT NULL,
 purchase_events INT NOT NULL, active_users INT NOT NULL,
 PRIMARY KEY(activity_month, product_line)
);
