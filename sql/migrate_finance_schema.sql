-- Apply once to an existing database created before inception_date and the
-- date-range index were added to the finance schema.
-- Example: mysql -h <host> -P <port> -u <user> -p <database> < sql/migrate_finance_schema.sql
ALTER TABLE assets
    ADD COLUMN inception_date DATE NULL AFTER properties;

CREATE INDEX idx_daily_prices_date ON daily_prices (date);
