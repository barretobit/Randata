-- Randata Finance API -- dividend events
--
-- One row per ex-dividend date per symbol: the cash dividend per share, in the
-- same currency as the symbol's prices (as Yahoo reports it). Filled from the
-- "Dividends" column of the same Yahoo downloads that store the price bars,
-- so backfills and the nightly ingestion keep it current without extra calls.
--
-- Run this once against the application database (the one referenced by
-- DATABASE_URL), e.g.:
--   mysql -h <host> -P <port> -u <user> -p <database> < sql/create_dividends_table.sql
-- Then run POST /finance/admin/backfill once to collect the stored window's history.

CREATE TABLE IF NOT EXISTS dividends (
    symbol  VARCHAR(20)   NOT NULL,
    date    DATE          NOT NULL,
    amount  DECIMAL(18,6) NOT NULL,
    PRIMARY KEY (symbol, date),
    KEY idx_dividends_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
