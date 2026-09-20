-- Randata Finance API -- homes
--
-- One row per tracked real-estate listing, owned by a `users` row.
-- Address, pricing, sizing and realtor contact metadata are stored as
-- plain columns instead of a JSON blob so they can be queried and
-- indexed individually (this is the replacement for the monolithic
-- `file_storage` JSON documents that became slow to load and save).
--
-- Run this once against the application database (the one referenced by
-- DATABASE_URL), e.g.:
--   mysql -h <host> -P <port> -u <user> -p <database> < sql/create_homes_table.sql

CREATE TABLE IF NOT EXISTS homes (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id         BIGINT UNSIGNED NOT NULL,
    title           VARCHAR(255)    NULL,
    street          VARCHAR(255)    NULL,
    zip             VARCHAR(20)     NULL,
    city            VARCHAR(100)    NULL,
    canton          VARCHAR(20)     NULL,
    price           DECIMAL(18,2)   NULL,
    size            DECIMAL(10,2)   NULL,
    rooms           DECIMAL(4,1)    NULL,
    built           INT             NULL,
    renovated       INT             NULL,
    house_type      VARCHAR(60)     NULL,
    floor           INT             NULL,
    url             VARCHAR(500)    NULL,
    main_image      VARCHAR(500)    NULL,
    status          VARCHAR(50)     NULL,
    notes           TEXT            NULL,
    realtor_name    VARCHAR(255)    NULL,
    realtor_phone   VARCHAR(50)     NULL,
    realtor_email   VARCHAR(255)    NULL,
    garage          INT             NULL,
    garage_included TINYINT(1)      NULL DEFAULT 0,
    garage_price    DECIMAL(18,2)   NULL,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_homes_user_id (user_id, id),
    CONSTRAINT fk_homes_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;