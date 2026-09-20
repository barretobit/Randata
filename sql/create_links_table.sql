-- Randata Finance API -- links
--
-- One row per relevant link (listing pages, map searches, etc.) attached
-- to a tracked home, linked to `homes`.
--
-- Run this once against the application database (the one referenced by
-- DATABASE_URL), e.g.:
--   mysql -h <host> -P <port> -u <user> -p <database> < sql/create_links_table.sql

CREATE TABLE IF NOT EXISTS links (
    id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    home_id BIGINT UNSIGNED NOT NULL,
    title   VARCHAR(255)    NULL,
    url     VARCHAR(500)    NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_links_home_id (home_id, id),
    CONSTRAINT fk_links_home FOREIGN KEY (home_id) REFERENCES homes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;