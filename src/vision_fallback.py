"""
vision_fallback.py
===================
Filet de secours par MODELE DE VISION (Qwen2.5-VL via Ollama), pour les
champs dont le texte n'est JAMAIS detecte par PaddleOCR (confirme sur
plusieurs approches : seuils assouplis, DPI augmente, recadrage cible -
voir field_extractor.py). Un LLM texte ne peut rien faire dans ce cas
(il ne voit que ce que l'OCR lui donne) ; un modele de VISION lit
directement l'IMAGE et contourne le probleme.

Utilise UNIQUEMENT sur une petite zone recadree (pas la page entiere) :
plus rapide, et evite de demander au modele de tout re-analyser alors
que le reste du document est deja bien extrait par l'approche spatiale.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import cv2
import numpy as np
import requests

from src.llm_extractor import OLLAMA_URL, _parse_llm_json

MODEL_VISION = "moondream"
VISION_TIMEOUT_S = 120  # deja beaucoup plus genereux que necessaire pour un modele aussi leger ; a resserrer une fois la vitesse reelle connue


def _encode_image_base64(image: np.ndarray) -> str:
    """Encode une image numpy (BGR, comme produite par cv2) en base64 PNG,
    format attendu par l'API Ollama pour les modeles de vision."""
    success, buffer = cv2.imencode(".png", image)
    if not success:
        raise ValueError("Echec de l'encodage de l'image en PNG.")
    return base64.b64encode(buffer).decode("utf-8")


def crop_region(image: np.ndarray, y_top: int, y_bottom: int, margin: int = 20) -> np.ndarray:
    """Recadre une bande horizontale de l'image, avec une marge de securite."""
    y0 = max(0, y_top - margin)
    y1 = min(image.shape[0], y_bottom + margin)
    return image[y0:y1]


def ask_simple_question(image_crop: np.ndarray, question: str, model: str = MODEL_VISION,
                         timeout: int = VISION_TIMEOUT_S) -> str:
    """
    Pose UNE question simple en langage naturel (pas de JSON complexe) -
    beaucoup plus a la portee d'un tout petit modele comme moondream
    qu'un schema JSON a plusieurs champs imbriques.
    """
    image_b64 = _encode_image_base64(image_crop)
    payload = {
        "model": model,
        "prompt": question,
        "images": [image_b64],
        "stream": False,
        "keep_alive": "5m",
        "options": {"temperature": 0.0, "num_predict": 50},
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def extract_certificate_fields_vision(
    image_crop: np.ndarray,
    model: str = MODEL_VISION,
    timeout: int = VISION_TIMEOUT_S,
) -> dict[str, Any]:
    """
    Envoie une image recadree (juste la zone du certificat sanitaire) a un
    modele de vision Ollama, et demande les 4 champs qui echappent
    systematiquement a PaddleOCR sur cette zone.

    Returns:
        {"certificate_date": str|None, "certificate_issued_at": str|None,
         "valid_till": str|None} - cle absente si le modele n'a pas
        repondu correctement (pas d'exception levee, filet de secours
        best-effort).
    """
    image_b64 = _encode_image_base64(image_crop)

    prompt = """Cette image est un extrait d'un formulaire maritime officiel. Elle contient une section "certificat sanitaire" avec des champs Date/lieu.

Lis attentivement le texte visible et extrait UNIQUEMENT ces informations, sous forme de JSON strict, rien d'autre :
{
  "certificate_date": "date au format JJ/MM/AAAA telle qu'ecrite a cote de 'Date' (premiere occurrence, section certificat), ou null si illisible",
  "certificate_issued_at": "lieu ecrit a cote de 'issued at:' (premiere occurrence), ou null si illisible",
  "valid_till": "date au format JJ/MM/AAAA ecrite a cote de 'valid till:', ou null si illisible"
}

Ne devine JAMAIS une valeur que tu ne vois pas clairement dans l'image - mets null dans ce cas. Reponds uniquement avec le JSON."""

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "format": "json",
        "keep_alive": "5m",
        "options": {"temperature": 0.0, "num_predict": 300},
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Impossible de joindre Ollama - verifie qu'il tourne et que le "
            f"modele '{model}' est bien telecharge (`ollama pull {model}`)."
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(f"Timeout Ollama vision apres {timeout}s (modele : {model}).") from exc

    raw_response = resp.json().get("response", "")

    try:
        parsed = _parse_llm_json(raw_response)
    except ValueError:
        return {}

    return {
        "certificate_date": parsed.get("certificate_date") or None,
        "certificate_issued_at": parsed.get("certificate_issued_at") or None,
        "valid_till": parsed.get("valid_till") or None,
    }


if __name__ == "__main__":
    import sys
    import time

    if len(sys.argv) < 2:
        print("Usage: python -m src.vision_fallback <image_page.png> [y_top] [y_bottom]")
        sys.exit(1)

    img = cv2.imread(sys.argv[1])
    y_top = int(sys.argv[2]) if len(sys.argv) > 2 else 2500
    y_bottom = int(sys.argv[3]) if len(sys.argv) > 3 else 2900

    crop = crop_region(img, y_top, y_bottom)
    cv2.imwrite("debug_vision_crop.png", crop)
    print(f"Crop sauvegarde : debug_vision_crop.png ({crop.shape[1]}x{crop.shape[0]})")

    if "--simple" in sys.argv:
        questions = [
            "What date is written next to 'valid till:' in this image? Reply with only the date, nothing else.",
            "What date is written next to 'Date' in the certificate section (not the drinking water or medical certificate sections)? Reply with only the date.",
            "What place name is written next to the first 'issued at:' in this image? Reply with only the place name.",
        ]
        for q in questions:
            t0 = time.perf_counter()
            try:
                answer = ask_simple_question(crop, q)
                print(f"Q: {q}\nA: {answer}\n⏱️ {time.perf_counter()-t0:.1f}s\n")
            except Exception as e:
                print(f"Q: {q}\n❌ {e}\n⏱️ {time.perf_counter()-t0:.1f}s\n")
        sys.exit(0)

    t0 = time.perf_counter()
    try:
        result = extract_certificate_fields_vision(crop)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Echec : {e}")
    finally:
        print(f"⏱️  {time.perf_counter() - t0:.2f}s (temps ecoule avant reponse ou timeout)")