"""
Moteur d'alertes — adapté au schéma avec déduplication (dedup_key).

Contrairement à la version précédente, ce module NE crée PAS d'objets Alert
directement : il retourne des dicts (alert_type, severity, message, detail,
dedup_key), qu'ingest.py insère ensuite via INSERT ... ON CONFLICT DO NOTHING
sur (document_id, dedup_key). Conséquence : une alerte déjà générée (et
éventuellement déjà acquittée) n'est jamais dupliquée ni écrasée si le même
document est ré-ingéré — c'est le principe voulu par le schéma fourni.

Règles :
  1. DANGEROUS_CLASS   -> une ligne dgd_matrix (classe 1, 6.2 ou 7) ou
                          dgm_cargo_items (classe normalisée 1/6.2/7) avec
                          une quantité/poids effectivement renseigné(e).
  2. HEALTH_POSITIVE   -> au moins une question q1..q9 répond "YES".
  3. CERTIFICATE_EXPIRED -> health_declarations.valid_till est dépassée.
  4. DOCUMENT_OUTDATED -> la date de référence du document (submission_date
                          pour Health, eta/etd pour DGM/DGD) a plus de 6 mois.
"""
from datetime import date

SIX_MONTHS_DAYS = 182


def _normalize_dgm_class(raw_class: str) -> str | None:
    c = (raw_class or "").strip()
    if not c:
        return None
    if c.startswith("6.2"):
        return "6.2"
    if c.startswith("1"):
        return "1"
    if c.startswith("7"):
        return "7"
    return None


def _has_value(*values) -> bool:
    for v in values:
        if v is None:
            continue
        try:
            if float(v) != 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _check_dangerous_classes(doc) -> list[dict]:
    alerts = []

    for row in doc.dgd_matrix_rows:
        is_dangerous = (
            row.class_ == "1"
            or row.class_ == "7"
            or (row.class_ == "6" and row.division == "2")
        )
        if is_dangerous and _has_value(
            row.to_load_main, row.to_load_transhipment,
            row.to_unload_main, row.to_unload_transhipment, row.in_transit
        ):
            label = f"Classe {row.class_}" + (f".{row.division}" if row.class_ == "6" else "")
            alerts.append({
                "alert_type": "DANGEROUS_CLASS",
                "severity": "CRITICAL",
                "message": f"Cargo dangereux détecté ({label}) sur le DGD de {doc.ship_name or 'navire inconnu'}",
                "detail": {"table": "dgd_matrix", "class": row.class_, "division": row.division},
                "dedup_key": f"dangerous_class:dgd_matrix:class{row.class_}:division{row.division or 'none'}",
            })

    for row in doc.dgm_cargo_items:
        normalized = _normalize_dgm_class(row.class_)
        if normalized:
            alerts.append({
                "alert_type": "DANGEROUS_CLASS",
                "severity": "CRITICAL",
                "message": (
                    f"Cargo dangereux détecté (Classe {normalized}) sur le DGM de "
                    f"{doc.ship_name or 'navire inconnu'} — conteneur {row.container_number or 'N/A'}"
                ),
                "detail": {
                    "table": "dgm_cargo_items",
                    "class": normalized,
                    "container_number": row.container_number,
                    "un_number": row.un_number,
                    "technical_name": row.technical_name,
                },
                "dedup_key": f"dangerous_class:dgm_cargo_items:{row.container_number or row.id}:{row.un_number or ''}",
            })

    return alerts


def _check_health_positive(doc) -> list[dict]:
    positive = [q.question_no for q in doc.health_questions if (q.answer or "").strip().upper() == "YES"]
    if not positive:
        return []

    return [{
        "alert_type": "HEALTH_POSITIVE",
        "severity": "HIGH",
        "message": (
            f"Réponse(s) positive(s) au questionnaire sanitaire pour {doc.ship_name or 'navire inconnu'} "
            f"(question(s) {', '.join(f'q{n}' for n in sorted(positive))})"
        ),
        "detail": {"positive_questions": sorted(positive)},
        "dedup_key": "health_positive",
    }]


def _check_certificate_expired(doc, today: date) -> list[dict]:
    if not doc.health or not doc.health.valid_till:
        return []

    if doc.health.valid_till < today:
        return [{
            "alert_type": "CERTIFICATE_EXPIRED",
            "severity": "HIGH",
            "message": (
                f"Certificat sanitaire expiré pour {doc.ship_name or 'navire inconnu'} "
                f"(valide jusqu'au {doc.health.valid_till.isoformat()})"
            ),
            "detail": {"valid_till": doc.health.valid_till.isoformat(), "checked_on": today.isoformat()},
            "dedup_key": "certificate_expired",
        }]
    return []


def _reference_date(doc):
    if doc.document_type == "HEALTH" and doc.health:
        return doc.health.submission_date
    if doc.document_type == "DGM" and doc.dgm:
        return doc.dgm.eta or doc.dgm.etd
    if doc.document_type == "DGD" and doc.dgd:
        return doc.dgd.eta or doc.dgd.etd
    return None


def _check_document_outdated(doc, today: date) -> list[dict]:
    ref = _reference_date(doc)
    if not ref:
        return []

    age_days = (today - ref).days
    if age_days > SIX_MONTHS_DAYS:
        return [{
            "alert_type": "DOCUMENT_OUTDATED",
            "severity": "MEDIUM",
            "message": (
                f"Document {doc.document_type} de {doc.ship_name or 'navire inconnu'} "
                f"daté du {ref.isoformat()}, soit {age_days} jours (> 6 mois)"
            ),
            "detail": {"reference_date": ref.isoformat(), "age_days": age_days},
            "dedup_key": "document_outdated",
        }]
    return []


def evaluate_document(doc, today: date | None = None) -> list[dict]:
    """
    Retourne une liste de dicts prêts à être insérés dans `alerts` via
    INSERT ... ON CONFLICT (document_id, dedup_key) DO NOTHING.
    """
    today = today or date.today()
    alerts: list[dict] = []
    alerts += _check_dangerous_classes(doc)
    alerts += _check_health_positive(doc)
    alerts += _check_certificate_expired(doc, today)
    alerts += _check_document_outdated(doc, today)
    return alerts
