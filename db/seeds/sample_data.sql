-- MLCC 계측 시스템 개발/테스트용 샘플 데이터
USE dc_db;

-- 계측기 등록
INSERT INTO instruments (name, model, manufacturer, instrument_type, gpib_address, description) VALUES
    ('Keysight E4980A', 'E4980A', 'Keysight', 'lcr_meter', 17, 'Precision LCR Meter 20Hz-2MHz'),
    ('Keysight B2901A', 'B2901A', 'Keysight', 'dc_source',  23, 'SMU DC Bias Source');

-- 샘플 측정 세션
INSERT INTO measurement_sessions (client_id, session_name, operator) VALUES
    ('station-01', 'MLCC 100nF DC바이어스 특성 평가', 'engineer01'),
    ('station-02', '온도별 용량 변화 측정',           'engineer02');

-- 원시 GPIB 응답
INSERT INTO raw_measurements (session_id, instrument_id, raw_response) VALUES
    (1, 1, '+1.00000E-07,+0.00100'),
    (1, 1, '+9.80000E-08,+0.00120'),
    (2, 1, '+1.05000E-07,+0.00090');

-- 정규화된 MLCC 측정값
INSERT INTO mlcc_measurements
    (raw_measurement_id, session_id, instrument_id, characteristic, value, unit, frequency, dc_bias, temperature)
VALUES
    (1, 1, 1, 'capacitance', 1.0e-7,  'F', 1000.0,  0.0, 25.0),
    (1, 1, 1, 'esr',         0.001,   'Ω', 1000.0,  0.0, 25.0),
    (2, 1, 1, 'capacitance', 9.8e-8,  'F', 1000.0, 10.0, 25.0),
    (2, 1, 1, 'esr',         0.0012,  'Ω', 1000.0, 10.0, 25.0),
    (3, 2, 1, 'capacitance', 1.05e-7, 'F', 1000.0,  0.0, 85.0),
    (3, 2, 1, 'esr',         0.0009,  'Ω', 1000.0,  0.0, 85.0);
