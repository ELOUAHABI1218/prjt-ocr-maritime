"""
ocr_postprocessing.py - Nettoyage des détections OCR
"""

# Seuil abaisse : un chiffre ISOLE (ex: "0" pour "Number of passenger on
# board") ou une coche courte (ex: "X", "V") ont naturellement moins de
# contexte visuel qu'un mot entier, donc un score de confiance plus bas -
# meme quand ils sont lus correctement. Un seuil de 0.4 les rejetait
# systematiquement (constate en pratique : "0" absent des detections
# post-filtrage alors que la detection existait probablement en amont).
MIN_CONFIDENCE = 0.15


def postprocess(raw_detections: list[dict], min_confidence: float = MIN_CONFIDENCE) -> list[dict]:
    # Supprimer les vides
    detections = [d for d in raw_detections if d["text"].strip()]
    # Filtrer par confiance
    detections = [d for d in detections if d["confidence"] >= min_confidence]
    # Trier par position (haut→bas, gauche→droite)
    detections.sort(key=lambda d: (d["bbox"]["y0"], d["bbox"]["x0"]))
    return detections