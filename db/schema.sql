-- DC 프로젝트 초기 스키마
-- 실제 운영 시 Alembic 마이그레이션을 사용하세요.

CREATE DATABASE IF NOT EXISTS dc_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE dc_db;

CREATE TABLE IF NOT EXISTS raw_data (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    client_id   VARCHAR(100) NOT NULL,
    raw_payload JSON         NOT NULL,
    received_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_client_id (client_id)
);

CREATE TABLE IF NOT EXISTS normalized_data (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    raw_data_id   INT          NOT NULL,
    client_id     VARCHAR(100) NOT NULL,
    value         DOUBLE,
    label         VARCHAR(255),
    normalized_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_raw_data_id (raw_data_id),
    INDEX idx_client_id (client_id)
);
