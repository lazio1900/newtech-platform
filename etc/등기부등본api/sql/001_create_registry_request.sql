CREATE TABLE IF NOT EXISTS registry_request (
    id              BIGSERIAL PRIMARY KEY,
    ic_id           INTEGER UNIQUE,
    address         TEXT NOT NULL,
    dong            TEXT,
    ho              TEXT,
    type            TEXT NOT NULL DEFAULT '집합건물',
    address_norm    TEXT NOT NULL,
    issued_date     DATE NOT NULL,
    status          TEXT NOT NULL,
    pdf_path        TEXT,
    cost            INTEGER DEFAULT 0,
    apick_pl_id     INTEGER,
    requester_id    TEXT,
    listing_id      TEXT,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    CONSTRAINT uq_registry_address_type_date UNIQUE (address_norm, type, issued_date)
);

CREATE INDEX IF NOT EXISTS idx_registry_listing   ON registry_request(listing_id);
CREATE INDEX IF NOT EXISTS idx_registry_requester ON registry_request(requester_id);
CREATE INDEX IF NOT EXISTS idx_registry_created   ON registry_request(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_registry_status    ON registry_request(status);
