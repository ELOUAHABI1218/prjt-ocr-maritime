"""
json_exporter.py - Export JSON

FIX (2026-08-08) :
    - Ecriture ATOMIQUE : on serialise D'ABORD tout le dict en memoire
      (json.dumps), et on n'ecrit sur disque QU'APRES succes complet de
      la serialisation, via un fichier temporaire + renommage. Avant ce
      fix, json.dump(data, f, ...) ecrivait DIRECTEMENT dans le fichier
      ouvert en mode "w" - si une valeur non serialisable (typiquement
      un numpy.int64/float64 residuel d'un calcul OpenCV/PaddleOCR)
      provoquait une exception EN COURS d'ecriture, le fichier restait
      cree mais vide/tronque (observe concretement : fichier resultat de
      0 octet), sans aucun message d'erreur clair.
    - _make_json_safe (NOUVEAU) : convertit recursivement les types
      numpy (int64, float64, ndarray...) en types Python natifs avant
      serialisation, pour eviter cette classe d'erreur a la source.
"""

import json
import os
from datetime import datetime, timezone


def _make_json_safe(obj):
    """
    Convertit recursivement un objet en types JSON-serialisables natifs.
    Gere en particulier les types numpy (int64, float64, bool_, ndarray)
    qui peuvent se glisser dans les donnees via des calculs OpenCV ou
    PaddleOCR (ex: une coordonnee bbox restee en numpy.float64 plutot
    que convertie en float Python) et que le module json standard ne
    sait pas serialiser.
    """
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]

    # Types numpy - import local pour ne pas rendre numpy obligatoire
    # si ce module est utilise sans le reste du pipeline OCR.
    try:
        import numpy as np
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return _make_json_safe(obj.tolist())
    except ImportError:
        pass

    return obj


def build_output(document_type: str, fields: dict, source_file: str) -> dict:
    return {
        "document_type": document_type,
        "source_file": os.path.basename(source_file),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
    }


def export_json(data: dict, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    safe_data = _make_json_safe(data)

    # Serialisation EN MEMOIRE d'abord - si une valeur pose encore
    # probleme malgre _make_json_safe, l'exception se produit ICI, AVANT
    # de toucher au disque : aucun fichier vide/tronque possible.
    try:
        json_text = json.dumps(safe_data, indent=2, ensure_ascii=False)
    except TypeError as e:
        raise TypeError(
            f"Impossible de serialiser les donnees en JSON pour '{output_path}': {e}. "
            f"Verifie qu'aucune valeur non-standard (type numpy, objet personnalise, "
            f"NaN/Infinity) ne s'est glissee dans les champs extraits."
        ) from e

    # Ecriture ATOMIQUE : fichier temporaire puis renommage. Si le
    # processus est interrompu (crash, Ctrl+C) pendant l'ecriture, le
    # fichier final n'est jamais laisse dans un etat partiel - soit
    # l'ancien contenu (ou rien) subsiste, soit le nouveau contenu
    # complet, jamais un etat intermediaire tronque.
    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(json_text)
    os.replace(tmp_path, output_path)

    return output_path