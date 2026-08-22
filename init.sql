CREATE TABLE IF NOT EXISTS telemetry (
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    serial_number VARCHAR(64) NOT NULL,
    zone VARCHAR(64),
    firmware VARCHAR(32),
    motor_state VARCHAR(32),
    filter_status VARCHAR(32),
    vacuum_pressure DOUBLE PRECISION,
    fluid_volume DOUBLE PRECISION
);

SELECT create_hypertable('telemetry', 'timestamp', if_not_exists => TRUE);
