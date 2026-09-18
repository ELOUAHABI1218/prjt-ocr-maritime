"""
ocr_engine.py
=============
Etape 3 du pipeline : execute PaddleOCR sur une image et retourne le texte
detecte avec ses bounding boxes et scores de confiance.

FIX (2026-08-04) : det_limit_side_len augmente.
    PaddleOCR redimensionne en interne l'image AVANT detection (valeur
    par defaut souvent 960px sur le plus grand cote). Une page A4 scannee
    a 300 DPI fait ~2200-2600px de large -> elle est donc fortement
    reduite avant meme d'atteindre le reseau de detection. Du texte deja
    fin/petit (ex: une ligne "Date : 30/01/2026" collee a une bordure de
    tableau) peut alors passer sous le seuil de detectabilite apres ce
    rétrecissement - meme si le meme texte, isole dans une petite image
    (donc a pleine resolution relative), se detecte sans probleme. C'est
    exactement ce qui a ete observe : ces champs echouent sur la page
    entiere mais reussissent sur un crop de test.

    On augmente donc det_limit_side_len pour que la page ne soit plus (ou
    beaucoup moins) reduite avant detection. Cout : legerement plus lent
    et plus gourmand en memoire, acceptable pour un traitement document
    par document (pas de contrainte temps reel).

Format de sortie normalise (independant du format brut de PaddleOCR, pour
decoupler le reste du pipeline de la librairie OCR utilisee) :
    [
        {"text": "Name of Ship", "confidence": 0.998,
         "bbox": {"x0": 50, "y0": 120, "x1": 190, "y1": 145}},
        ...
    ]
"""

from paddleocr import PaddleOCR

_OCR_INSTANCE = None  # instanciation paresseuse (chargement du modele = couteux)

# Cote maximum (px) autorise AVANT reduction interne par PaddleOCR pour la
# detection. Valeur par defaut PaddleOCR ~960 -> trop faible pour une page
# scannee a 300 DPI (~2200-2600px de large). On la porte largement au-dessus
# de la plus grande dimension attendue d'une page pour eviter tout
# sous-echantillonnage du texte fin pres des bordures de tableau.
DET_LIMIT_SIDE_LEN = 3200


def _get_ocr_instance(lang: str = "en", cpu_threads: int = 4):
    """
    Args:
        cpu_threads: nombre de threads internes utilises par CETTE instance
            PaddleOCR pour l'inference.
    """
    global _OCR_INSTANCE
    if _OCR_INSTANCE is None:
        common_kwargs = dict(
            lang=lang,
            cpu_threads=cpu_threads,
            det_db_thresh=0.2,
            det_db_box_thresh=0.4,
            det_db_unclip_ratio=2.0,
            use_dilation=True,
        )

        # Les noms de parametres pour la limite de resize different selon
        # les versions de PaddleOCR (det_limit_side_len sur les versions
        # "legacy", text_det_limit_side_len sur les versions plus recentes
        # basees sur PaddleX). On essaie plusieurs variantes, de la plus
        # recente a la plus ancienne, pour rester compatible sans casser
        # l'installation existante.
        attempts = [
            dict(common_kwargs, use_textline_orientation=False,
                 text_det_limit_side_len=DET_LIMIT_SIDE_LEN,
                 text_det_limit_type="max"),
            dict(common_kwargs, use_textline_orientation=False,
                 det_limit_side_len=DET_LIMIT_SIDE_LEN,
                 det_limit_type="max"),
            dict(common_kwargs, use_angle_cls=False, show_log=False,
                 det_limit_side_len=DET_LIMIT_SIDE_LEN,
                 det_limit_type="max"),
            # Dernier recours : sans le parametre de limite (au cas ou
            # aucune variante de nom ne correspond a la version installee).
            dict(common_kwargs, use_textline_orientation=False),
        ]

        last_error = None
        for kwargs in attempts:
            try:
                _OCR_INSTANCE = PaddleOCR(**kwargs)
                if "text_det_limit_side_len" in kwargs or "det_limit_side_len" in kwargs:
                    print(f"   ✅ PaddleOCR initialise avec limite de resolution etendue ({DET_LIMIT_SIDE_LEN}px)")
                else:
                    print("   ⚠️  PaddleOCR initialise SANS limite de resolution etendue "
                          "(parametre non reconnu sur cette version) - le texte fin pres "
                          "des bords/bordures de tableau peut rester mal detecte.")
                break
            except TypeError as e:
                last_error = e
                continue

        if _OCR_INSTANCE is None:
            raise last_error
    return _OCR_INSTANCE


def _bbox_polygon_to_rect(polygon) -> dict:
    """PaddleOCR retourne un polygone a 4 points [[x,y],[x,y],[x,y],[x,y]].
    On le convertit en rectangle englobant simple."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)}


def run_ocr(image, lang: str = "en", cpu_threads: int = 4) -> list[dict]:
    """
    Execute PaddleOCR sur une image (chemin de fichier OU array numpy issu
    de image_preprocessing.preprocess()).

    Returns:
        Liste de detections normalisees : text, confidence, bbox (x0,y0,x1,y1)
    """
    ocr = _get_ocr_instance(lang, cpu_threads=cpu_threads)
    try:
        raw_results = ocr.ocr(image, cls=False)
    except TypeError:
        raw_results = ocr.ocr(image)

    detections = []
    if not raw_results or raw_results[0] is None:
        return detections

    for line in raw_results[0]:
        polygon, (text, confidence) = line
        detections.append({
            "text": text.strip(),
            "confidence": float(confidence),
            "bbox": _bbox_polygon_to_rect(polygon),
        })

    return detections


if __name__ == "__main__":
    import sys
    import json
    if len(sys.argv) < 2:
        print("Usage: python3 ocr_engine.py <image.png>")
        sys.exit(1)
    results = run_ocr(sys.argv[1])
    print(json.dumps(results, indent=2, ensure_ascii=False))