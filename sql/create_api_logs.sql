-- Randata Finance API -- structured log table
--
-- Stores one row per ingestion/event logged by app/logging_config.py
-- (log_event). Intended to be queried from the dashboard or external tools
-- to see whether the daily (and backfill) fetches are succeeding, how long
-- each took, how many rows were written, and any errors.
--
-- Run this once against the application database (the one referenced by
-- DATABASE_URL), e.g.:
--   mysql -h <host> -P <port> -u <user> -p <database> < sql/create_api_logs.sql

CREATE TABLE IF NOT EXISTS api_logs (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    recorded_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    logger       VARCHAR(64)     NULL,
    level        VARCHAR(16)     NULL,
    message      TEXT            NULL,
    symbol       VARCHAR(32)     NULL,
    duration_ms  INT UNSIGNED    NULL,
    rows_written INT UNSIGNED    NULL,
    success      TINYINT(1)      NULL,
    exception    TEXT            NULL,
    PRIMARY KEY (id),
    KEY idx_api_logs_recorded_at (recorded_at),
    KEY idx_api_logs_symbol (symbol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
