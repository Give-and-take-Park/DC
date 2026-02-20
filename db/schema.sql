-- MLCC 계측기 데이터 수집 시스템 스키마
-- MariaDB 운영 서버에서 직접 실행하거나,
-- Alembic 마이그레이션을 사용하는 경우 `alembic upgrade head` 를 사용하세요.

CREATE DATABASE IF NOT EXISTS dc_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE dc_db;

-- 계측기 등록 정보
CREATE TABLE IF NOT EXISTS instruments (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    name             VARCHAR(200)    NOT NULL,
    model            VARCHAR(100)    NOT NULL,
    manufacturer     VARCHAR(100),
    instrument_type  ENUM('lcr_meter','dc_source','oscilloscope','multimeter') NOT NULL,
    gpib_address     INT,
    description      VARCHAR(500),
    INDEX idx_model (model)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 측정 세션 (1회 측정 작업 단위)
CREATE TABLE IF NOT EXISTS measurement_sessions (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    client_id    VARCHAR(100) NOT NULL,
    session_name VARCHAR(200),
    started_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at     DATETIME,
    operator     VARCHAR(100),
    notes        TEXT,
    INDEX idx_client_id (client_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 계측기 원시 GPIB 응답 (감사/재처리용)
CREATE TABLE IF NOT EXISTS raw_measurements (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    session_id    INT  NOT NULL,
    instrument_id INT,
    raw_response  TEXT NOT NULL,
    measured_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_id    (session_id),
    INDEX idx_instrument_id (instrument_id),
    FOREIGN KEY (session_id)    REFERENCES measurement_sessions(id),
    FOREIGN KEY (instrument_id) REFERENCES instruments(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 정규화된 MLCC 특성값
CREATE TABLE IF NOT EXISTS mlcc_measurements (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    raw_measurement_id INT,
    session_id         INT  NOT NULL,
    instrument_id      INT,
    characteristic     ENUM('capacitance','esr','df','impedance','q_factor','dc_bias') NOT NULL,
    value              DOUBLE NOT NULL,
    unit               VARCHAR(20) NOT NULL,
    frequency          DOUBLE,        -- Hz
    dc_bias            DOUBLE,        -- V
    temperature        DOUBLE,        -- °C
    measured_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_id     (session_id),
    INDEX idx_instrument_id  (instrument_id),
    INDEX idx_characteristic (characteristic),
    FOREIGN KEY (raw_measurement_id) REFERENCES raw_measurements(id),
    FOREIGN KEY (session_id)         REFERENCES measurement_sessions(id),
    FOREIGN KEY (instrument_id)      REFERENCES instruments(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
