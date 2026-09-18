"""
strikethrough_detector.py
==========================
Detecte si un mot/token a un trait de biffage (ex: "YES" raye pour indiquer
que la reponse est "NO"), en analysant les PIXELS de sa bounding box sur
l'image du document.

Necessaire car sur un SCAN (contrairement a un PDF natif), il n'y a pas de
rectangle vectoriel a inspecter (voir extract_health_declaration.py qui
utilisait cette approche vectorielle sur du PDF natif) - seulement des
pixels. Un trait de biffage produit une bande horizontale de pixels sombres
QUASI CONTINUE sur une grande partie de la largeur du mot, ce qui le
distingue des traits normaux des lettres (plus fragmentes, jamais aussi
continus sur toute la largeur).
"""

import cv2
import numpy as np


def is_token_struck(image_gray: np.ndarray, bbox: dict,
                     dark_threshold: int = 127,
                     line_fraction_threshold: float = 0.55) -> bool:
    """
    Args:
        image_gray: image en niveaux de gris (numpy array) de la PAGE COMPLETE
        bbox: bounding box du token a analyser {"x0","y0","x1","y1"}
        dark_threshold: seuil de binarisation (0-255)
        line_fraction_threshold: fraction de pixels sombres sur une ligne
            horizontale au-dela de laquelle on considere que c'est un trait
            de biffage plutot que les traits normaux des lettres

    Returns:
        True si un trait de biffage est detecte dans la bbox
    """
    x0, y0, x1, y1 = int(bbox["x0"]), int(bbox["y0"]), int(bbox["x1"]), int(bbox["y1"])
    crop = image_gray[y0:y1, x0:x1]
    if crop.size == 0:
        return False

    _, binary = cv2.threshold(crop, dark_threshold, 255, cv2.THRESH_BINARY_INV)
    h, w = binary.shape
    if h == 0 or w == 0:
        return False

    row_dark_fraction = binary.sum(axis=1) / 255 / w
    # Bande elargie (25%-85% de la hauteur) : la position exacte du trait
    # varie selon la precision de la bbox OCR, pas toujours parfaitement
    # centree sur le texte.
    band = row_dark_fraction[int(h * 0.25): int(h * 0.85)]
    if len(band) == 0:
        return False

    return bool(band.max() > line_fraction_threshold)


def resolve_yes_no(image_gray: np.ndarray, yes_bbox: dict = None, no_bbox: dict = None) -> str:
    """
    Determine la reponse YES/NO reelle en verifiant lequel des deux est
    barre. Retourne "YES", "NO", ou None si indetermine (aucun des deux
    trouve, ou aucun des deux ne semble barre alors que les 2 sont presents
    - cas ambigu a ne pas deviner).
    """
    yes_struck = is_token_struck(image_gray, yes_bbox) if yes_bbox else False
    no_struck = is_token_struck(image_gray, no_bbox) if no_bbox else False

    if yes_struck and not no_struck:
        return "NO"
    if no_struck and not yes_struck:
        return "YES"
    return None  