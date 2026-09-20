-- Randata Finance API -- visits
--
-- One row per scheduled or past visit to a tracked home, linked to `homes`.
--
-- Run this once against the application database (the one referenced by
-- DATABASE_URL), e.g.:
--   mysql -h <host> -P <port> -u <user> -p <database> < sql/create_visits_table.sql

CREATE TABLE IF NOT EXISTS visits (
    id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    home_id BIGINT UNSIGNED NOT NULL,
    date    DATE            NULL,
    time    TIME            NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_visits_home_id (home_id, id),
    CONSTRAINT fk_visits_home FOREIGN KEY (home_id) REFERENCES homes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;