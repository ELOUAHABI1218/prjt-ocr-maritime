"""
Ingestion des fichiers JSON produits par tes extracteurs
(dgd_main.py / dgm_main.py / health_main.py) vers PostgreSQL,
selon le schéma fourni (documents + tables *_declarations/*_items/*_matrix).

Usage :
    python ingest.py /chemin/vers/dossier_json
    python ingest.py /chemin/vers/un_fichier.json

Idempotent sur les DONNÉES : un document avec le même (document_type,
source_file) voit ses tables de détail remplacées (delete + re-insert).
Idempotent sur les ALERTES : une alerte déjà générée (dedup_key identique
pour ce document_id) n'est jamais dupliquée, même après ré-ingestion —
voir alert_engine.py et le INSERT ON CONFLICT ci-dessous.
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from alert_engine import evaluate_document
from database import SessionLocal, init_db
from date_utils import parse_date
from models import (
    Alert, DGDDeclaration, DGDMatrixRow, DGMCargoItem, DGMDeclaration,
    Document, HealthCrewJoined, HealthDeclaration, HealthPortOfCall,
    HealthQuestion,
)


def to_int(value) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def to_numeric(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def normalize_document_type(raw: str) -> str:
    """'DGD' -> 'DGD', 'DGM' -> 'DGM', 'Health' -> 'HEALTH' (contrainte CHECK du schéma)."""
    return raw.strip().upper()


def upsert_document(session: Session, payload: dict) -> Document:
    doc_type = normalize_document_type(payload["document_type"])
    fields = payload.get("fields", {})
    source_file = payload["source_file"]

    doc = (
        session.query(Document)
        .filter_by(document_type=doc_type, source_file=source_file)
        .one_or_none()
    )
    if doc is None:
        doc = Document(document_type=doc_type, source_file=source_file)
        session.add(doc)

    doc.extracted_at = datetime.fromisoformat(payload["extracted_at"])
    doc.ship_name = fields.get("ship_name")
    doc.imo_number = fields.get("imo_number")
    doc.voyage_no = fields.get("voyage_no")
    doc.raw_json = payload

    session.flush()  # pour obtenir doc.document_id

    # Repart de zéro pour les tables de détail à chaque ré-ingestion.
    session.query(HealthQuestion).filter_by(document_id=doc.document_id).delete()
    session.query(HealthPortOfCall).filter_by(document_id=doc.document_id).delete()
    session.query(HealthCrewJoined).filter_by(document_id=doc.document_id).delete()
    session.query(DGMCargoItem).filter_by(document_id=doc.document_id).delete()
    session.query(DGDMatrixRow).filter_by(document_id=doc.document_id).delete()
    if doc.health:
        session.delete(doc.health)
    if doc.dgm:
        session.delete(doc.dgm)
    if doc.dgd:
        session.delete(doc.dgd)
    session.flush()

    if doc_type == "HEALTH":
        _ingest_health(session, doc, fields)
    elif doc_type == "DGM":
        _ingest_dgm(session, doc, fields)
    elif doc_type == "DGD":
        _ingest_dgd(session, doc, fields)

    return doc


def _ingest_health(session: Session, doc: Document, fields: dict):
    session.add(HealthDeclaration(
        document=doc,
        submitted_port=fields.get("submitted_port"),
        submission_date=parse_date(fields.get("submission_date")),
        last_port=fields.get("last_port"),
        next_port=fields.get("next_port"),
        nationality=fields.get("nationality"),
        master_name=fields.get("master_name"),
        gross_tonnage=to_int(fields.get("gross_tonnage")),
        net_tonnage=to_int(fields.get("net_tonnage")),
        who_affected_area=fields.get("who_affected_area"),
        port_date_visit_area=fields.get("port_date_visit_area"),
        crew_members=to_int(fields.get("crew_members")),
        passengers=str(fields.get("passengers")) if fields.get("passengers") is not None else None,
        certificate_carried_on_board=fields.get("certificate_carried_on_board"),
        certificate_date=parse_date(fields.get("certificate_date")),
        certificate_issued_at=fields.get("certificate_issued_at"),
        valid_till=parse_date(fields.get("valid_till")),
        re_inspection_required=fields.get("re_inspection_required"),
        water_analysis_date=parse_date(fields.get("water_analysis_date")),
        water_analysis_issued_at=fields.get("water_analysis_issued_at"),
        medical_certificate_date=parse_date(fields.get("medical_certificate_date")),
        medical_certificate_issued_at=fields.get("medical_certificate_issued_at"),
        fumigated_cargo=fields.get("fumigated_cargo"),
    ))

    for q_key, answer in (fields.get("health_questions") or {}).items():
        q_no = to_int(str(q_key).replace("q", ""))
        if q_no is None:
            continue
        session.add(HealthQuestion(document_id=doc.document_id, question_no=q_no, answer=str(answer).strip().upper() if answer else None))

    for row in fields.get("ports_of_call", []) or []:
        session.add(HealthPortOfCall(
            document_id=doc.document_id,
            port=row.get("port"),
            date_of_departure=parse_date(row.get("date_of_departure")),
        ))

    for row in fields.get("crew_and_others_joined", []) or []:
        session.add(HealthCrewJoined(
            document_id=doc.document_id,
            name=row.get("name"),
            joined_at_port=row.get("joined_at_port"),
            date_of_joining=parse_date(row.get("date_of_joining")),
        ))


def _ingest_dgm(session: Session, doc: Document, fields: dict):
    session.add(DGMDeclaration(
        document=doc,
        booking_nr=fields.get("booking_nr") or None,
        call_sign=fields.get("call_sign"),
        flag_state=fields.get("flag_state"),
        eta=parse_date(fields.get("eta")),
        etd=parse_date(fields.get("etd")),
        previous_port_of_call=fields.get("previous_port_of_call"),
        next_port_of_call=fields.get("next_port_of_call"),
        manifest_type=fields.get("manifest_type") or None,
    ))

    for row in fields.get("dangerous_goods", []) or []:
        session.add(DGMCargoItem(
            document_id=doc.document_id,
            container_number=row.get("container_number"),
            technical_name=row.get("technical_name"),
            class_=str(row.get("class", "")).strip() or None,
            un_number=row.get("un_number"),
            quantity=row.get("quantity"),
            unite=row.get("unite"),
            net_weight=row.get("net_weight"),
            stowage_position=row.get("stowage_position"),
            contact_info=row.get("contact_info"),
            port=row.get("port"),
        ))


def _ingest_dgd(session: Session, doc: Document, fields: dict):
    session.add(DGDDeclaration(
        document=doc,
        booking_nr=fields.get("booking_nr") or None,
        call_sign=fields.get("call_sign"),
        flag_state=fields.get("flag_state"),
        eta=parse_date(fields.get("eta")),
        etd=parse_date(fields.get("etd")),
        previous_port_of_call=fields.get("previous_port_of_call"),
        next_port_of_call=fields.get("next_port_of_call"),
    ))

    for row in fields.get("class_division_table", []) or []:
        session.add(DGDMatrixRow(
            document_id=doc.document_id,
            class_=str(row.get("class")).strip(),
            division=str(row.get("division")).strip() if row.get("division") is not None else None,
            to_load_main=to_numeric(row.get("to_load_col1")),
            to_load_transhipment=to_numeric(row.get("to_load_transhipment")),
            to_unload_main=to_numeric(row.get("to_unload_col1")),
            to_unload_transhipment=to_numeric(row.get("to_unload_transhipment")),
            in_transit=to_numeric(row.get("in_transit")),
        ))


def insert_alerts(session: Session, doc: Document):
    """INSERT ... ON CONFLICT (document_id, dedup_key) DO NOTHING — jamais de doublon, jamais d'écrasement."""
    new_alerts = evaluate_document(doc)
    if not new_alerts:
        return 0

    stmt = pg_insert(Alert).values([
        {"document_id": doc.document_id, **a} for a in new_alerts
    ]).on_conflict_do_nothing(index_elements=["document_id", "dedup_key"])
    result = session.execute(stmt)
    return result.rowcount or 0


def ingest_file(session: Session, path: Path) -> Document:
    payload = json.loads(path.read_text(encoding="utf-8"))
    doc = upsert_document(session, payload)
    session.flush()

    created = insert_alerts(session, doc)
    session.commit()

    print(f"✔ {path.name} -> document #{doc.document_id} ({doc.document_type}), "
          f"{created} nouvelle(s) alerte(s)")
    return doc


def main():
    if len(sys.argv) != 2:
        print("Usage: python ingest.py <fichier.json | dossier>")
        sys.exit(1)

    target = Path(sys.argv[1])
    init_db()
    session = SessionLocal()

    try:
        files = [target] if target.is_file() else sorted(target.glob("*.json"))
        if not files:
            print(f"Aucun fichier JSON trouvé dans {target}")
            return
        for f in files:
            try:
                ingest_file(session, f)
            except Exception as exc:
                session.rollback()
                print(f"✘ Échec sur {f.name}: {exc}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
