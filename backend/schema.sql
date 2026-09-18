-- =====================================================================
-- schema.sql - Schema PostgreSQL pour le pipeline documents maritimes
-- =====================================================================
CREATE TABLE IF NOT EXISTS documents (
    document_id      BIGSERIAL PRIMARY KEY,
    document_type     VARCHAR(10) NOT NULL
                       CHECK (document_type IN ('HEALTH', 'DGM', 'DGD')),
    source_file       TEXT NOT NULL,
    extracted_at      TIMESTAMPTZ,
    ship_name         TEXT,
    imo_number        VARCHAR(20),
    voyage_no         TEXT,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_json          JSONB NOT NULL,
    UNIQUE (document_type, source_file)
);

CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_imo ON documents(imo_number);
CREATE INDEX IF NOT EXISTS idx_documents_raw_json ON documents USING GIN (raw_json);

CREATE TABLE IF NOT EXISTS health_declarations (
    document_id                    BIGINT PRIMARY KEY
                                    REFERENCES documents(document_id) ON DELETE CASCADE,
    submitted_port                 TEXT,
    submission_date                DATE,
    last_port                      TEXT,
    next_port                      TEXT,
    nationality                    TEXT,
    master_name                    TEXT,
    gross_tonnage                  INTEGER,
    net_tonnage                    INTEGER,
    who_affected_area              TEXT,
    port_date_visit_area           TEXT,
    crew_members                   INTEGER,
    passengers                     TEXT,
    certificate_carried_on_board   TEXT,
    certificate_date                DATE,
    certificate_issued_at          TEXT,
    valid_till                     DATE,
    re_inspection_required         TEXT,
    water_analysis_date            DATE,
    water_analysis_issued_at       TEXT,
    medical_certificate_date       DATE,
    medical_certificate_issued_at  TEXT,
    fumigated_cargo                TEXT
);

CREATE TABLE IF NOT EXISTS health_questions (
    document_id   BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    question_no   SMALLINT NOT NULL CHECK (question_no BETWEEN 1 AND 9),
    answer        TEXT,
    PRIMARY KEY (document_id, question_no)
);

CREATE TABLE IF NOT EXISTS health_ports_of_call (
    id                  BIGSERIAL PRIMARY KEY,
    document_id         BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    port                TEXT,
    date_of_departure   DATE
);

CREATE TABLE IF NOT EXISTS health_crew_joined (
    id                BIGSERIAL PRIMARY KEY,
    document_id       BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    name              TEXT,
    joined_at_port    TEXT,
    date_of_joining   DATE
);

CREATE TABLE IF NOT EXISTS dgm_declarations (
    document_id             BIGINT PRIMARY KEY
                             REFERENCES documents(document_id) ON DELETE CASCADE,
    booking_nr              TEXT,
    call_sign               TEXT,
    flag_state              TEXT,
    eta                     DATE,
    etd                     DATE,
    previous_port_of_call   TEXT,
    next_port_of_call       TEXT,
    manifest_type           TEXT[]
);

CREATE TABLE IF NOT EXISTS dgm_cargo_items (
    id                  BIGSERIAL PRIMARY KEY,
    document_id         BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    container_number    TEXT,
    technical_name       TEXT,
    class               TEXT,
    un_number           TEXT,
    quantity            TEXT,
    unite               TEXT,
    net_weight          TEXT,
    stowage_position    TEXT,
    contact_info        TEXT,
    port                TEXT
);

CREATE INDEX IF NOT EXISTS idx_dgm_cargo_class ON dgm_cargo_items(class);

CREATE TABLE IF NOT EXISTS dgd_declarations (
    document_id             BIGINT PRIMARY KEY
                             REFERENCES documents(document_id) ON DELETE CASCADE,
    booking_nr              TEXT,
    call_sign               TEXT,
    flag_state              TEXT,
    eta                     DATE,
    etd                     DATE,
    previous_port_of_call   TEXT,
    next_port_of_call       TEXT
);

CREATE TABLE IF NOT EXISTS dgd_matrix (
    id                       BIGSERIAL PRIMARY KEY,
    document_id              BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    class                    TEXT NOT NULL,
    division                 TEXT,
    to_load_main             NUMERIC,
    to_load_transhipment     NUMERIC,
    to_unload_main           NUMERIC,
    to_unload_transhipment   NUMERIC,
    in_transit               NUMERIC
);

CREATE INDEX IF NOT EXISTS idx_dgd_matrix_class ON dgd_matrix(class, division);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id      BIGSERIAL PRIMARY KEY,
    document_id   BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    alert_type    VARCHAR(50) NOT NULL,
    severity      VARCHAR(10) NOT NULL DEFAULT 'HIGH'
                  CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    message       TEXT NOT NULL,
    detail        JSONB,
    dedup_key     TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged  BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (document_id, dedup_key)
);

CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_ack ON alerts(acknowledged);