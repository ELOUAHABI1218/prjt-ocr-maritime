"""
main_dgd.py - Pipeline OCR pour Dangerous Cargo Declaration (DGD)
====================================================================
Reutilise l'infrastructure OCR/rotation deja eprouvee sur le pipeline
DGM (main_dgm.py) - meme famille de documents Tanger Med, memes soucis
d'orientation source variable d'un fichier a l'autre.
"""

import argparse
import os
import re
import sys
import time
import traceback

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2

from src.pdf_converter import pdf_to_images
from src.image_preprocessing import preprocess, estimate_image_quality
from src.ocr_engine import run_ocr
from src.ocr_postprocessing import postprocess
from src.dgd_extractor import extract_dgd_full
from src.json_exporter import build_output, export_json


ROTATION_CANDIDATES = [
    cv2.ROTATE_90_COUNTERCLOCKWISE,
    None,
    cv2.ROTATE_90_CLOCKWISE,
    cv2.ROTATE_180,
]

ORIENTATION_KEYWORDS = [
    "dangerous cargo declaration", "booking nr", "voyage no",
    "class", "division", "in transit",
]

ORIENTATION_SCORE_THRESHOLD = 3
DEFAULT_ROTATION = cv2.ROTATE_90_COUNTERCLOCKWISE
DEFAULT_ROTATION_MIN_SCORE = 2

SHARPNESS_THRESHOLD = 80

_UNSET = object()


def _keyword_score(clean: list) -> int:
    text_all = " ".join(d["text"] for d in clean).lower()
    return sum(1 for kw in ORIENTATION_KEYWORDS if kw in text_all)


def _ocr_with_best_rotation(image, known_rotation=_UNSET, prior_result=None):
    if known_rotation is not _UNSET:
        candidate_image = image if known_rotation is None else cv2.rotate(image, known_rotation)
        raw = run_ocr(candidate_image)
        clean = postprocess(raw)
        print(f"      🔄 Rotation reutilisee : {known_rotation} -> {len(clean)} detections")
        return clean, candidate_image, known_rotation

    best_clean, best_image, best_score, best_rotation = [], image, -1, None
    already_tried = set()

    if prior_result is not None:
        p_clean, p_image, p_rotation, p_score = prior_result
        best_clean, best_image, best_score, best_rotation = p_clean, p_image, p_score, p_rotation
        already_tried.add(p_rotation)
        if p_score >= ORIENTATION_SCORE_THRESHOLD:
            return best_clean, best_image, best_rotation

    for rotation in ROTATION_CANDIDATES:
        if rotation in already_tried:
            continue
        already_tried.add(rotation)
        candidate_image = image if rotation is None else cv2.rotate(image, rotation)
        raw = run_ocr(candidate_image)
        clean = postprocess(raw)
        score = _keyword_score(clean)
        print(f"      🔄 Rotation {rotation} -> {len(clean)} detections, score mots-cles={score}")
        if score > best_score:
            best_clean, best_image, best_score, best_rotation = clean, candidate_image, score, rotation
        if score >= ORIENTATION_SCORE_THRESHOLD:
            break

    return best_clean, best_image, best_rotation


def _ocr_page1_fast(image):
    candidate_image = cv2.rotate(image, DEFAULT_ROTATION)
    raw = run_ocr(candidate_image)
    clean = postprocess(raw)
    score = _keyword_score(clean)
    print(f"      🔄 Rotation par defaut {DEFAULT_ROTATION} -> {len(clean)} detections, score={score}")

    if score >= DEFAULT_ROTATION_MIN_SCORE:
        return clean, candidate_image, DEFAULT_ROTATION

    print("      ⚠️  Score insuffisant avec la rotation par defaut -> test complet des rotations")
    return _ocr_with_best_rotation(
        image, known_rotation=_UNSET,
        prior_result=(clean, candidate_image, DEFAULT_ROTATION, score)
    )


def _looks_garbled(clean: list) -> bool:
    return sum(1 for d in clean if len(set(d["text"].lower())) <= 3 and len(d["text"]) > 5) > 5


def process_dgd_pdf(pdf_path: str, output_dir: str = "output") -> dict:
    print(f"\n📄 Traitement DGD : {os.path.basename(pdf_path)}")
    start_total = time.time()

    pages_dir = os.path.join(output_dir, "pages")
    image_paths = pdf_to_images(pdf_path, pages_dir, dpi=300)
    print(f"   ✅ Conversion: {len(image_paths)} pages")

    # Le DGD tient sur 1 seule page (en-tete + tableau fixe) - inutile de
    # traiter des pages suivantes (signature/tampon uniquement).
    img_path = image_paths[0]

    print(f"   🔍 OCR page 1...")
    start_ocr = time.time()
    processed = preprocess(img_path, do_binarize=False)

    clean, used_image, rotation_used = _ocr_page1_fast(processed)
    print(f"      📐 Largeur/hauteur de la page : {used_image.shape[1]} x {used_image.shape[0]}")

    gray_for_quality = used_image if used_image.ndim == 2 else cv2.cvtColor(used_image, cv2.COLOR_BGR2GRAY)
    quality = estimate_image_quality(gray_for_quality)
    garbled = _looks_garbled(clean)
    print(f"      📊 Qualite estimee : nettete={quality['sharpness']:.1f}, contraste={quality['contrast']:.1f}"
          f"{' | texte incoherent detecte' if garbled else ''}")

    if garbled or quality["sharpness"] < SHARPNESS_THRESHOLD:
        print("      ⚠️  Page probablement degradee -> re-OCR avec enhance_for_ocr()...")
        processed_enhanced = preprocess(img_path, do_binarize=False, do_enhance=True)
        clean_enhanced, _, _ = _ocr_with_best_rotation(processed_enhanced, known_rotation=rotation_used)
        print(f"      🔎 Passage ameliore : {len(clean_enhanced)} detections (vs {len(clean)} initiales)")
        clean.extend(clean_enhanced)

    print(f"      → {len(clean)} détections en {time.time() - start_ocr:.2f}s")

    print(f"\n   📊 Extraction des champs DGD...")
    start_extract = time.time()
    fields = extract_dgd_full(clean)
    print(f"      → extraction en {time.time() - start_extract:.2f}s")

    print("\n   🔧 DEBUG champs extraits :")
    for k, v in fields.items():
        if k != "class_division_table":
            print(f"      {k}: {v!r}")
    table = fields.get("class_division_table", [])
    filled = [r for r in table if any(r.get(c) for c in
              ("to_load_col1", "to_load_transhipment", "to_unload_col1", "to_unload_transhipment", "in_transit"))]
    print(f"      class_division_table: {len(table)} lignes ({len(filled)} avec au moins une valeur)")
    for row in filled:
        print(f"         {row}")

    result = build_output("DGD", fields, pdf_path)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_path = os.path.join(output_dir, f"{base_name}_result.json")
    export_json(result, output_path)

    print(f"\n   ⏱️  Total: {time.time() - start_total:.2f}s")
    print(f"   ✅ Résultat: {output_path}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Pipeline OCR - Dangerous Cargo Declaration")
    parser.add_argument("pdf_path", help="Chemin vers le PDF DGD")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"❌ Fichier '{args.pdf_path}' inexistant")
        return

    try:
        process_dgd_pdf(args.pdf_path, args.output_dir)
    except Exception as e:
        print(f"❌ Erreur : {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()