-- Randata Finance API -- tracked assets catalogue
--
-- Stores one row per tracked instrument/symbol, formalising the categories
-- that previously lived only as hardcoded lists in app/assets.py.
--
-- asset_type values: 'fx' | 'index' | 'metal' | 'stock' | 'crypto'
-- properties:       JSON object with category-specific metadata, e.g.
--                   FX:    {"display": "EUR/USD"}
--                   index: {"region": "US"}
--                   metal: {"display": "XAU", "unit": "USD per troy ounce"}
--                   stock: {}
--                   crypto:{"display": "BTC"}
--
-- Run this once against the application database (the one referenced by
-- DATABASE_URL), e.g.:
--   mysql -h <host> -P <port> -u <user> -p <database> < sql/create_assets_table.sql

CREATE TABLE IF NOT EXISTS assets (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol      VARCHAR(20)     NOT NULL,
    name        VARCHAR(100)    NOT NULL,
    asset_type  VARCHAR(30)     NOT NULL,
    properties  JSON            NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_assets_symbol (symbol),
    KEY idx_assets_type (asset_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;