CREATE TABLE IF NOT EXISTS file_storage (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user          VARCHAR(100)    NOT NULL,
    pass_hash     VARCHAR(255)    NOT NULL,
    code          VARCHAR(64)     NOT NULL,
    json_data     JSON            NULL,
    last_updated  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_file_storage_code (code)
);
