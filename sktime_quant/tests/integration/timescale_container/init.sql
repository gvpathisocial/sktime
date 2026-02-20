CREATE TABLE IF NOT EXISTS market_data_container_it (
    timestamp TIMESTAMPTZ NOT NULL,
    asset TEXT NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION,
    asset_class TEXT
);

CREATE TABLE IF NOT EXISTS exog_data_container_it (
    timestamp TIMESTAMPTZ NOT NULL,
    asset TEXT NOT NULL,
    factor_1 DOUBLE PRECISION
);

INSERT INTO market_data_container_it
(timestamp, asset, open, high, low, close, volume, asset_class)
VALUES
('2025-01-01T00:00:00Z', 'AAPL', 100, 101, 99, 100.5, 1000, 'stock'),
('2025-01-02T00:00:00Z', 'AAPL', 101, 102, 100, 101.5, 1100, 'stock'),
('2025-01-03T00:00:00Z', 'AAPL', 102, 103, 101, 102.0, 1200, 'stock');

INSERT INTO exog_data_container_it
(timestamp, asset, factor_1)
VALUES
('2025-01-01T00:00:00Z', 'AAPL', 0.1),
('2025-01-02T00:00:00Z', 'AAPL', 0.2),
('2025-01-03T00:00:00Z', 'AAPL', 0.3);
