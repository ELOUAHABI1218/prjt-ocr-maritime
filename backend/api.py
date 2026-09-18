"""
API FastAPI — expose les documents et alertes stockés en PostgreSQL,
selon le schéma fourni (documents / *_declarations / *_items / *_matrix / alerts).

Lancer avec :
    uvicorn api:app --reload --port 8000

Documentation interactive auto-générée : http://localhost:8000/docs
"""
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import cast, Date as SqlDate, func
from sqlalchemy.orm import Session, joinedload

from database import get_session, init_db
from models import Alert, DGDMatrixRow, DGMCargoItem, Document, HealthQuestion

app = FastAPI(title=" Maritime Docs API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


# ------------------------------------------------------------------
# Schémas de réponse (Pydantic)
# ------------------------------------------------------------------
class AlertOut(BaseModel):
    alert_id: int
    document_id: int
    alert_type: str
    severity: str
    message: str
    detail: Optional[dict] = None
    acknowledged: bool
    created_at: datetime
    ship_name: Optional[str] = None
    document_type: Optional[str] = None
    source_file: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentOut(BaseModel):
    document_id: int
    document_type: str
    source_file: str
    ship_name: Optional[str] = None
    imo_number: Optional[str] = None
    voyage_no: Optional[str] = None
    loaded_at: Optional[datetime] = None
    alert_count: int = 0

    class Config:
        from_attributes = True


class DocumentDetailOut(DocumentOut):
    raw_json: dict
    alerts: List[AlertOut] = []


# ------------------------------------------------------------------
# Routes — documents
# ------------------------------------------------------------------
@app.get("/documents", response_model=List[DocumentOut])
def list_documents(
    document_type: Optional[str] = None,
    ship_name: Optional[str] = None,
    session: Session = Depends(get_session),
):
    query = session.query(
        Document, func.count(Alert.alert_id).label("alert_count")
    ).outerjoin(Alert, Alert.document_id == Document.document_id)

    if document_type:
        query = query.filter(Document.document_type == document_type.upper())
    if ship_name:
        query = query.filter(Document.ship_name.ilike(f"%{ship_name}%"))

    query = query.group_by(Document.document_id).order_by(Document.loaded_at.desc())

    results = []
    for doc, alert_count in query.all():
        item = DocumentOut.model_validate(doc)
        item.alert_count = alert_count
        results.append(item)
    return results


@app.get("/documents/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: int, session: Session = Depends(get_session)):
    doc = (
        session.query(Document)
        .options(joinedload(Document.alerts))
        .filter(Document.document_id == document_id)
        .one_or_none()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")

    out = DocumentDetailOut.model_validate(doc)
    out.alert_count = len(doc.alerts)
    out.alerts = [AlertOut.model_validate(a) for a in doc.alerts]
    return out


# ------------------------------------------------------------------
# Routes — alertes
# ------------------------------------------------------------------
@app.get("/alerts", response_model=List[AlertOut])
def list_alerts(
    alert_type: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    limit: int = Query(default=100, le=500),
    session: Session = Depends(get_session),
):
    query = session.query(Alert).options(joinedload(Alert.document))
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)
    if acknowledged is not None:
        query = query.filter(Alert.acknowledged == acknowledged)
    query = query.order_by(Alert.created_at.desc()).limit(limit)

    results = []
    for a in query.all():
        out = AlertOut.model_validate(a)
        if a.document:
            out.ship_name = a.document.ship_name
            out.document_type = a.document.document_type
            out.source_file = a.document.source_file
        results.append(out)
    return results


@app.patch("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge_alert(alert_id: int, session: Session = Depends(get_session)):
    alert = session.query(Alert).filter(Alert.alert_id == alert_id).one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte introuvable")
    alert.acknowledged = True
    session.commit()
    session.refresh(alert)
    return alert


# ------------------------------------------------------------------
# Routes — statistiques (pour le dashboard)
# ------------------------------------------------------------------
@app.get("/stats/summary")
def stats_summary(session: Session = Depends(get_session)):
    total_docs = session.query(func.count(Document.document_id)).scalar()
    open_alerts = session.query(func.count(Alert.alert_id)).filter(Alert.acknowledged.is_(False)).scalar()
    by_type = dict(
        session.query(Alert.alert_type, func.count(Alert.alert_id))
        .filter(Alert.acknowledged.is_(False))
        .group_by(Alert.alert_type)
        .all()
    )
    by_doc_type = dict(
        session.query(Document.document_type, func.count(Document.document_id))
        .group_by(Document.document_type)
        .all()
    )
    return {
        "total_documents": total_docs,
        "open_alerts": open_alerts,
        "alerts_by_type": by_type,
        "documents_by_type": by_doc_type,
    }


import re

_CLASS_PATTERN = re.compile(r"^([1-9])(\.[1-6])?")


def _normalize_dgd_class(class_: str | None, division: str | None) -> str:
    """Réduit (class, division) à un label IMDG canonique ('3', '6.2'...), ou bucket 'Autre'."""
    c = (class_ or "").strip()
    if re.fullmatch(r"[1-9]", c):
        d = (str(division) if division is not None else "").strip()
        if re.fullmatch(r"[1-6]", d):
            return f"{c}.{d}"
        return c
    return "Autre / non classifié"


def _normalize_dgm_class(raw: str | None) -> str:
    """
    Extrait un label IMDG canonique depuis une valeur potentiellement bruitée
    (ex: un numéro UN à 4 chiffres collé par erreur au champ classe lors de
    l'extraction OCR, comme '1866' ou '3082 FIRELIGHTERS, SOLID'). Rejette
    tout ce qui n'est pas exactement un chiffre 1-9 (+ subdivision .1-.6)
    suivi d'une frontière non-numérique — un vrai numéro UN à 4 chiffres
    ne matchera donc jamais, même s'il commence par 1-9.
    """
    c = (raw or "").strip()
    m = _CLASS_PATTERN.match(c)
    if not m:
        return "Autre / non classifié"
    end = m.end()
    if end < len(c) and c[end].isdigit():
        return "Autre / non classifié"
    return m.group(0)


@app.get("/documents/{document_id}/class-breakdown")
def document_class_breakdown(document_id: int, session: Session = Depends(get_session)):
    """Répartition des classes IMDG (comptage + pourcentage) pour UN document précis (DGD ou DGM)."""
    doc = session.query(Document).filter(Document.document_id == document_id).one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")

    counts: dict[str, int] = {}

    if doc.document_type == "DGD":
        rows = (
            session.query(DGDMatrixRow.class_, DGDMatrixRow.division, func.count())
            .filter(
                DGDMatrixRow.document_id == document_id,
                (DGDMatrixRow.to_load_main.isnot(None) & (DGDMatrixRow.to_load_main != 0))
                | (DGDMatrixRow.to_load_transhipment.isnot(None) & (DGDMatrixRow.to_load_transhipment != 0))
                | (DGDMatrixRow.to_unload_main.isnot(None) & (DGDMatrixRow.to_unload_main != 0))
                | (DGDMatrixRow.to_unload_transhipment.isnot(None) & (DGDMatrixRow.to_unload_transhipment != 0))
                | (DGDMatrixRow.in_transit.isnot(None) & (DGDMatrixRow.in_transit != 0)),
            )
            .group_by(DGDMatrixRow.class_, DGDMatrixRow.division)
            .all()
        )
        for class_, division, count in rows:
            label = _normalize_dgd_class(class_, division)
            counts[label] = counts.get(label, 0) + count

    elif doc.document_type == "DGM":
        rows = (
            session.query(DGMCargoItem.class_, func.count())
            .filter(DGMCargoItem.document_id == document_id)
            .group_by(DGMCargoItem.class_)
            .all()
        )
        for class_, count in rows:
            label = _normalize_dgm_class(class_)
            counts[label] = counts.get(label, 0) + count

    total = sum(counts.values())
    return {
        "document_id": document_id,
        "document_type": doc.document_type,
        "ship_name": doc.ship_name,
        "source_file": doc.source_file,
        "total": total,
        "breakdown": [
            {"class": k, "count": v, "percentage": round(v / total * 100, 1) if total else 0}
            for k, v in sorted(counts.items())
        ],
    }


@app.get("/history")
def history(session: Session = Depends(get_session)):
    """
    Historique des documents océrisés : temps d'océrisation (si disponible,
    uniquement pour les documents importés via upload PDF — absent pour les
    imports JSON directs) et alertes générées pour chacun.
    """
    docs = session.query(Document).options(joinedload(Document.alerts)).order_by(Document.loaded_at.desc()).all()

    results = []
    for doc in docs:
        pipeline_meta = (doc.raw_json or {}).get("_pipeline_meta") or {}
        results.append({
            "document_id": doc.document_id,
            "document_type": doc.document_type,
            "ship_name": doc.ship_name,
            "source_file": doc.source_file,
            "loaded_at": doc.loaded_at,
            "ocr_seconds": pipeline_meta.get("ocr_seconds"),
            "alerts": [
                {"alert_id": a.alert_id, "alert_type": a.alert_type, "severity": a.severity, "message": a.message, "acknowledged": a.acknowledged}
                for a in doc.alerts
            ],
        })
    return results


@app.get("/stats/all-classes")
def stats_all_classes(session: Session = Depends(get_session)):
    """Occurrences de CHAQUE classe IMDG (1 à 9, toutes confondues) sur l'ensemble des documents."""
    counts: dict[str, int] = {}

    dgd_rows = (
        session.query(DGDMatrixRow.class_, DGDMatrixRow.division, func.count())
        .filter(
            (DGDMatrixRow.to_load_main.isnot(None) & (DGDMatrixRow.to_load_main != 0))
            | (DGDMatrixRow.to_load_transhipment.isnot(None) & (DGDMatrixRow.to_load_transhipment != 0))
            | (DGDMatrixRow.to_unload_main.isnot(None) & (DGDMatrixRow.to_unload_main != 0))
            | (DGDMatrixRow.to_unload_transhipment.isnot(None) & (DGDMatrixRow.to_unload_transhipment != 0))
            | (DGDMatrixRow.in_transit.isnot(None) & (DGDMatrixRow.in_transit != 0))
        )
        .group_by(DGDMatrixRow.class_, DGDMatrixRow.division)
        .all()
    )
    for class_, division, count in dgd_rows:
        label = f"{class_}.{division}" if division else str(class_)
        counts[label] = counts.get(label, 0) + count

    dgm_rows = session.query(DGMCargoItem.class_, func.count()).group_by(DGMCargoItem.class_).all()
    for class_, count in dgm_rows:
        label = (class_ or "").strip() or "?"
        counts[label] = counts.get(label, 0) + count

    return sorted(
        [{"class": k, "count": v} for k, v in counts.items()],
        key=lambda d: d["class"],
    )


@app.get("/stats/dangerous-classes")
def stats_dangerous_classes(session: Session = Depends(get_session)):
    """Répartition des marchandises dangereuses détectées (classes 1 / 6.2 / 7), DGD + DGM confondus."""
    counts: dict[str, int] = {"1": 0, "6.2": 0, "7": 0}

    dgd_rows = (
        session.query(DGDMatrixRow.class_, DGDMatrixRow.division, func.count())
        .filter(
            (
                (DGDMatrixRow.class_ == "1")
                | (DGDMatrixRow.class_ == "7")
                | ((DGDMatrixRow.class_ == "6") & (DGDMatrixRow.division == "2"))
            )
            & (
                (DGDMatrixRow.to_load_main.isnot(None) & (DGDMatrixRow.to_load_main != 0))
                | (DGDMatrixRow.to_load_transhipment.isnot(None) & (DGDMatrixRow.to_load_transhipment != 0))
                | (DGDMatrixRow.to_unload_main.isnot(None) & (DGDMatrixRow.to_unload_main != 0))
                | (DGDMatrixRow.to_unload_transhipment.isnot(None) & (DGDMatrixRow.to_unload_transhipment != 0))
                | (DGDMatrixRow.in_transit.isnot(None) & (DGDMatrixRow.in_transit != 0))
            )
        )
        .group_by(DGDMatrixRow.class_, DGDMatrixRow.division)
        .all()
    )
    for class_, division, count in dgd_rows:
        label = "6.2" if class_ == "6" else str(class_)
        counts[label] = counts.get(label, 0) + count

    dgm_rows = session.query(DGMCargoItem.class_, func.count()).group_by(DGMCargoItem.class_).all()
    for class_, count in dgm_rows:
        c = (class_ or "").strip()
        if c.startswith("6.2"):
            counts["6.2"] += count
        elif c.startswith("1"):
            counts["1"] += count
        elif c.startswith("7"):
            counts["7"] += count

    return [{"class": k, "count": v} for k, v in counts.items()]


@app.get("/stats/health-questions")
def stats_health_questions(session: Session = Depends(get_session)):
    rows = (
        session.query(HealthQuestion.question_no, HealthQuestion.answer, func.count())
        .group_by(HealthQuestion.question_no, HealthQuestion.answer)
        .all()
    )
    by_question: dict[int, dict[str, int]] = {n: {"YES": 0, "NO": 0} for n in range(1, 10)}
    for q_no, answer, count in rows:
        by_question.setdefault(q_no, {"YES": 0, "NO": 0})
        key = (answer or "").upper()
        if key in ("YES", "NO"):
            by_question[q_no][key] = count

    return [
        {"question": f"q{n}", "yes": by_question[n].get("YES", 0), "no": by_question[n].get("NO", 0)}
        for n in sorted(by_question)
    ]


@app.get("/stats/alerts-timeline")
def stats_alerts_timeline(days: int = Query(default=30, le=365), session: Session = Depends(get_session)):
    since = date.today() - timedelta(days=days)
    rows = (
        session.query(cast(Alert.created_at, SqlDate).label("day"), func.count())
        .filter(Alert.created_at >= since)
        .group_by("day")
        .order_by("day")
        .all()
    )
    by_day = {str(day): count for day, count in rows}

    result = []
    for i in range(days, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        result.append({"date": d, "count": by_day.get(d, 0)})
    return result


# ------------------------------------------------------------------
# Routes — ingestion
# ------------------------------------------------------------------
@app.post("/ingest/upload")
async def upload_and_ingest(file: UploadFile = File(...), session: Session = Depends(get_session)):
    """Upload direct d'un JSON déjà extrait (ex: output/DGM-ex-1_result.json)."""
    import json

    from ingest import insert_alerts, upsert_document

    content = await file.read()
    payload = json.loads(content)

    doc = upsert_document(session, payload)
    session.flush()
    created = insert_alerts(session, doc)
    session.commit()

    doc_alerts = (
        session.query(Alert)
        .filter(Alert.document_id == doc.document_id)
        .order_by(Alert.created_at.desc())
        .all()
    )

    return {
        "document_id": doc.document_id,
        "alerts_created": created,
        "extracted_json": payload,
        "alerts": [
            {"alert_id": a.alert_id, "alert_type": a.alert_type, "severity": a.severity, "message": a.message}
            for a in doc_alerts
        ],
    }


@app.post("/ingest/upload-pdf")
async def upload_pdf_and_ingest(
    file: UploadFile = File(...),
    document_type_hint: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    """
    Upload d'un PDF brut : lance le pipeline OCR (voir ocr_bridge.py),
    puis ingère le JSON produit exactement comme /ingest/upload.
    Renvoie le temps d'océrisation seul, le temps total du pipeline
    (OCR + ingestion base de données), le JSON extrait, et le détail
    des alertes applicables à ce document.
    """
    import tempfile
    import time
    from pathlib import Path

    from ingest import insert_alerts, upsert_document
    from ocr_bridge import OcrPipelineNotConnected, run_ocr_pipeline

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers .pdf sont acceptés sur cet endpoint.")

    content = await file.read()

    tmp_dir = Path(tempfile.mkdtemp(prefix="pfa_upload_"))
    tmp_path = tmp_dir / file.filename
    tmp_path.write_bytes(content)

    pipeline_start = time.perf_counter()

    ocr_start = time.perf_counter()
    try:
        payload = run_ocr_pipeline(tmp_path, file.filename, document_type_hint or None)
    except OcrPipelineNotConnected as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Échec de l'extraction OCR : {exc}")
    ocr_seconds = round(time.perf_counter() - ocr_start, 2)

    payload.setdefault("source_file", file.filename)
    # Persiste les temps de traitement dans raw_json (le schéma n'a pas de
    # colonne dédiée) — récupérés ensuite par /history pour affichage.
    payload["_pipeline_meta"] = {"ocr_seconds": ocr_seconds}

    doc = upsert_document(session, payload)
    session.flush()
    created = insert_alerts(session, doc)
    session.commit()

    doc_alerts = (
        session.query(Alert)
        .filter(Alert.document_id == doc.document_id)
        .order_by(Alert.created_at.desc())
        .all()
    )

    pipeline_seconds = round(time.perf_counter() - pipeline_start, 2)

    return {
        "document_id": doc.document_id,
        "alerts_created": created,
        "ocr_seconds": ocr_seconds,
        "pipeline_seconds": pipeline_seconds,
        "extracted_json": payload,
        "alerts": [
            {
                "alert_id": a.alert_id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "message": a.message,
            }
            for a in doc_alerts
        ],
    }
