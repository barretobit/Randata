-- Randata Finance API -- users
--
-- One row per authenticated user of the real-estate tracking feature.
-- The `user` column mirrors the username convention already used by the
-- `file_storage` table; `pass` holds the password hash, `combined_income`
-- is the household's combined income (optional).
--
-- Run this once against the application database (the one referenced by
-- DATABASE_URL), e.g.:
--   mysql -h <host> -P <port> -u <user> -p <database> < sql/create_users_table.sql

CREATE TABLE IF NOT EXISTS users (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user            VARCHAR(100)    NOT NULL,
    pass            VARCHAR(255)    NOT NULL,
    combined_income DECIMAL(18,2)   NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_user (user)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;