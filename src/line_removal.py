"""
line_removal.py
================
Detecte et efface les traits horizontaux (soulignements de formulaire)
d'une image AVANT l'OCR. Hypothese a tester : les 3 lignes jamais
detectees par PaddleOCR (Date du certificat, valid till...) sont toutes
soulignees - le trait, tres proche du texte, pourrait perturber la
detection (fusion texte+trait en une seule "forme" que le detecteur
rejette ou lit mal).

Technique : ouverture morphologique avec un noyau HORIZONTAL long et FIN,
qui isole les lignes horizontales longues et fines (les soulignements) en
les preservant tandis que le texte (formes plus compactes) disparait de
cette carte. On soustrait ensuite cette carte de lignes de l'image
originale (les remplace par du blanc), sans toucher au texte.
"""

import cv2
import numpy as np


def remove_horizontal_lines(image: np.ndarray, min_line_length_fraction: float = 0.03) -> np.ndarray:
    """
    Efface les traits horizontaux longs et fins d'une image (soulignements
    de formulaire), en preservant le texte.

    Args:
        image: image BGR ou grayscale.
        min_line_length_fraction: longueur minimale d'un trait pour etre
            considere comme un soulignement (fraction de la largeur de
            l'image) - evite d'effacer des traits de lettres normales.

    Returns:
        Image avec les traits horizontaux effaces (remplaces par blanc),
        meme format (BGR ou grayscale) que l'entree.
    """
    is_color = image.ndim == 3
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if is_color else image.copy()

    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    line_length = max(15, int(image.shape[1] * min_line_length_fraction))
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (line_length, 1))
    detected_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)

    # Legere dilatation verticale pour couvrir l'epaisseur reelle du trait
    # (l'ouverture peut le laisser tres fin, 1px).
    dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3))
    detected_lines = cv2.dilate(detected_lines, dilate_kernel, iterations=1)

    result = image.copy()
    if is_color:
        result[detected_lines > 0] = [255, 255, 255]
    else:
        result[detected_lines > 0] = 255

    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.line_removal <image.png>")
        sys.exit(1)
    img = cv2.imread(sys.argv[1])
    cleaned = remove_horizontal_lines(img)
    out_path = "debug_lines_removed.png"
    cv2.imwrite(out_path, cleaned)
    print(f"Image nettoyee sauvegardee : {out_path}")