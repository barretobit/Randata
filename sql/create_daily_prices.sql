-- Randata Finance API -- daily OHLCV price bars
--
-- The main (first) storage table: one row per stored daily bar per symbol.
-- Keyed by UNIQUE (symbol, date), which drives every query (latest, history,
-- last-updated) and the upsert during ingestion (INSERT ... ON DUPLICATE KEY UPDATE).
--
-- Run this once against the application database (the one referenced by
-- DATABASE_URL), e.g.:
--   mysql -h <host> -P <port> -u <user> -p <database> < sql/create_daily_prices.sql
--
-- Definition mirrors the live table (SHOW CREATE TABLE daily_prices).

CREATE TABLE IF NOT EXISTS daily_prices (
    id      BIGINT       NOT NULL AUTO_INCREMENT,
    symbol  VARCHAR(20)  NOT NULL,
    date    DATE         NOT NULL,
    open    DECIMAL(18,6) DEFAULT NULL,
    high    DECIMAL(18,6) DEFAULT NULL,
    low     DECIMAL(18,6) DEFAULT NULL,
    close   DECIMAL(18,6) DEFAULT NULL,
    volume  BIGINT        DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_symbol_date (symbol, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;