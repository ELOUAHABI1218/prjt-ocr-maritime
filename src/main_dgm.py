"""
main_dgm.py - Pipeline OCR pour Dangerous Cargo Manifest (DGM)
======================================================================

FIX (2026-09-08) :
    - _make_narrow_columns_retry_fn prend maintenant la liste de TOUTES
      les pages traitees (image + offset Y de depart de chacune), et non
      plus seulement l'image de la page 1. Bug reel observe : sur un
      tableau qui s'etend sur plusieurs pages, les classes des lignes
      situees sur la page 2+ n'etaient JAMAIS recuperees par le retry
      colonnes etroites (class/quantity, necessaire car ces chiffres
      sont souvent trop petits pour l'OCR standard) - le crop de retry
      etait mecaniquement borne a la hauteur en pixels de la SEULE image
      de la page 1 (`min(page1_used_image.shape[0], table_end_y)`),
      donc toute plage Y au-dela de la page 1 retombait a une bande
      vide. Desormais, pour une plage [table_start_y, table_end_y] en
      coordonnees CUMULEES, on determine quelle(s) page(s) elle
      recouvre reellement, et on relance le retry sur CHACUNE de ces
      pages avec ses propres coordonnees locales (image + offset),
      avant de recombiner les resultats en coordonnees globales.
"""

import argparse
import os
import re
import sys
import time
import traceback
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from src.pdf_converter import pdf_to_images
from src.image_preprocessing import preprocess, estimate_image_quality
from src.ocr_engine import run_ocr
from src.ocr_postprocessing import postprocess
from src.dgm_extractor import extract_dgm_full
from src.json_exporter import build_output, export_json


ROTATION_CANDIDATES = [
    cv2.ROTATE_90_COUNTERCLOCKWISE,
    None,
    cv2.ROTATE_90_CLOCKWISE,
    cv2.ROTATE_180,
]

ORIENTATION_KEYWORDS = [
    "dangerous cargo manifest", "booking nr", "container number",
    "technical name", "imo number", "flag state",
]

ORIENTATION_SCORE_THRESHOLD = 3
DEFAULT_ROTATION = cv2.ROTATE_90_COUNTERCLOCKWISE
DEFAULT_ROTATION_MIN_SCORE = 2

SHARPNESS_THRESHOLD = 80
PROCESS_PAGE1_ONLY = False

RETRY_ZONE_TOP_MARGIN = 60
RETRY_ZONE_HEIGHT = 140
RETRY_ZONE_UPSCALE = 2.0

NARROW_COL_UPSCALE = 3.0
NARROW_COL_X_MARGIN = 30
NARROW_COL_PAD = 30

_UNSET = object()

LABEL_STRIP_PATTERNS = [
    re.compile(r"call\s*sign", re.IGNORECASE),
    re.compile(r"imo\s*n\w{0,3}umber", re.IGNORECASE),
    re.compile(r"flag\s*state", re.IGNORECASE),
    re.compile(r"\beta\b", re.IGNORECASE),
    re.compile(r"etd", re.IGNORECASE),
    re.compile(r"previous\s*port", re.IGNORECASE),
    re.compile(r"next\s*port", re.IGNORECASE),
]


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


def _retry_ocr_flag_state_zone(used_image, detections):
    flag_state_det = next(
        (d for d in detections if "flag state" in d["text"].lower()), None
    )
    if flag_state_det is None:
        print("      🔎 'Flag State' introuvable -> pas de retry possible sur cette zone")
        return []

    y_top = max(0, int(flag_state_det["bbox"]["y0"]) - RETRY_ZONE_TOP_MARGIN)
    y_bottom = min(used_image.shape[0], int(flag_state_det["bbox"]["y0"]) + RETRY_ZONE_HEIGHT)

    strip = used_image[y_top:y_bottom, :]
    if strip.size == 0:
        return []

    if RETRY_ZONE_UPSCALE and RETRY_ZONE_UPSCALE != 1.0:
        h, w = strip.shape[:2]
        strip = cv2.resize(strip, (int(w * RETRY_ZONE_UPSCALE), int(h * RETRY_ZONE_UPSCALE)),
                            interpolation=cv2.INTER_CUBIC)

    pad = 40
    pad_shape = (pad,) + strip.shape[1:]
    white_pad = np.full(pad_shape, 255, dtype=strip.dtype)
    padded = np.vstack([white_pad, strip, white_pad])

    print(f"      🔎 Retry cible zone Flag State -> Previous/Next port of call "
          f"(bande {padded.shape[1]}x{padded.shape[0]}, upscale x{RETRY_ZONE_UPSCALE})...")

    raw = run_ocr(padded)
    clean = postprocess(raw)

    scale = RETRY_ZONE_UPSCALE if RETRY_ZONE_UPSCALE else 1.0
    for d in clean:
        d["bbox"]["x0"] = d["bbox"]["x0"] / scale
        d["bbox"]["x1"] = d["bbox"]["x1"] / scale
        d["bbox"]["y0"] = (d["bbox"]["y0"] - pad) / scale + y_top
        d["bbox"]["y1"] = (d["bbox"]["y1"] - pad) / scale + y_top

    print(f"      🔎 {len(clean)} detections supplementaires trouvees (retry zone Flag State) :")
    for d in clean:
        print(f"         y={d['bbox']['y0']:.0f} x={d['bbox']['x0']:.0f}  '{d['text']}'")

    return clean


def _strip_label_bearing_detections(dets: list) -> list:
    def _matches(d):
        low = d["text"].lower()
        return any(p.search(low) for p in LABEL_STRIP_PATTERNS)

    kept = [d for d in dets if not _matches(d)]
    removed = len(dets) - len(kept)
    if removed:
        print(f"      🧹 {removed} detection(s) originale(s) portant un label cible "
              f"retiree(s) (remplacee(s) par le retry)")
    return kept


def _dedupe_detections(dets: list, y_tol: float = 25) -> list:
    def _normalize(text):
        return re.sub(r"[^a-z0-9]", "", text.lower())

    ordered = sorted(dets, key=lambda d: -len(d["text"]))
    kept = []
    for d in ordered:
        d_norm = _normalize(d["text"])
        d_y = (d["bbox"]["y0"] + d["bbox"]["y1"]) / 2
        is_dup = False
        if d_norm:
            for k in kept:
                k_norm = _normalize(k["text"])
                k_y = (k["bbox"]["y0"] + k["bbox"]["y1"]) / 2
                if abs(d_y - k_y) <= y_tol and k_norm and (d_norm == k_norm or d_norm in k_norm):
                    is_dup = True
                    break
        if not is_dup:
            kept.append(d)
    return sorted(kept, key=lambda d: (d["bbox"]["y0"], d["bbox"]["x0"]))


def _looks_garbled(clean: list) -> bool:
    return sum(1 for d in clean if len(set(d["text"].lower())) <= 3 and len(d["text"]) > 5) > 5


def _make_narrow_columns_retry_fn(page_images):
    """
    page_images : liste de (image_utilisee, y_offset_de_cette_page) pour
    CHAQUE page traitee (pas seulement la page 1 — voir docstring du
    module pour le bug reel que ce changement corrige).

    Pour une plage [table_start_y, table_end_y] en coordonnees CUMULEES
    (globales, apres decalage entre pages), on determine quelle(s)
    page(s) elle recouvre reellement, on relance le retry sur CHACUNE
    en coordonnees locales a cette page, puis on reconvertit les
    resultats en coordonnees globales avant de les renvoyer combines.
    """
    def _retry(anchors: list, table_start_y: float, table_end_y: float) -> list:
        anchor_dict = dict(anchors)
        if "class" not in anchor_dict:
            return []

        x_start = max(0, int(anchor_dict["class"]) - NARROW_COL_X_MARGIN)
        x_end = int(anchor_dict.get("unite", anchor_dict["class"] + 350))

        all_extra = []

        for page_image, page_y_offset in page_images:
            page_height = page_image.shape[0]
            page_y_top_global = page_y_offset
            page_y_bottom_global = page_y_offset + page_height

            # Intersection entre la plage demandee et la portion couverte par CETTE page.
            y_top_global = max(table_start_y, page_y_top_global)
            y_bottom_global = min(table_end_y, page_y_bottom_global)
            if y_bottom_global <= y_top_global:
                continue  # cette page n'est pas concernee par cette plage

            y_top_local = max(0, int(y_top_global - page_y_offset))
            y_bottom_local = min(page_height, int(y_bottom_global - page_y_offset))
            if y_bottom_local <= y_top_local or x_end <= x_start:
                continue

            strip = page_image[y_top_local:y_bottom_local, x_start:x_end]
            if strip.size == 0:
                continue

            h, w = strip.shape[:2]
            strip = cv2.resize(strip, (int(w * NARROW_COL_UPSCALE), int(h * NARROW_COL_UPSCALE)),
                                interpolation=cv2.INTER_CUBIC)

            pad_shape = (NARROW_COL_PAD,) + strip.shape[1:]
            white_pad = np.full(pad_shape, 255, dtype=strip.dtype)
            padded = np.vstack([white_pad, strip, white_pad])

            print(f"      🔎 Retry cible colonnes class/quantity (page a offset "
                  f"{page_y_offset:.0f}, bande {padded.shape[1]}x{padded.shape[0]}, "
                  f"upscale x{NARROW_COL_UPSCALE})...")

            raw = run_ocr(padded)
            clean = postprocess(raw)

            for d in clean:
                d["bbox"]["x0"] = d["bbox"]["x0"] / NARROW_COL_UPSCALE + x_start
                d["bbox"]["x1"] = d["bbox"]["x1"] / NARROW_COL_UPSCALE + x_start
                d["bbox"]["y0"] = (d["bbox"]["y0"] - NARROW_COL_PAD) / NARROW_COL_UPSCALE + y_top_local + page_y_offset
                d["bbox"]["y1"] = (d["bbox"]["y1"] - NARROW_COL_PAD) / NARROW_COL_UPSCALE + y_top_local + page_y_offset

            for d in clean:
                print(f"         y={d['bbox']['y0']:.0f} x={d['bbox']['x0']:.0f}  '{d['text']}'")

            all_extra.extend(clean)

        return all_extra

    return _retry


def process_dgm_pdf(pdf_path: str, output_dir: str = "output") -> dict:
    print(f"\n📄 Traitement DGM : {os.path.basename(pdf_path)}")
    start_total = time.time()

    pages_dir = os.path.join(output_dir, "pages")
    image_paths = pdf_to_images(pdf_path, pages_dir, dpi=300)
    print(f"   ✅ Conversion: {len(image_paths)} pages")

    all_detections = []
    page1_detections = []
    page_images = []  # (image_utilisee, y_offset_de_cette_page) pour CHAQUE page
    page_width = None
    page1_rotation = _UNSET
    y_offset = 0.0

    for idx, img_path in enumerate(image_paths):
        if PROCESS_PAGE1_ONLY and idx > 0:
            print(f"   ⏭️  Page {idx+1} ignoree (tableau pas encore implemente)")
            continue

        print(f"   🔍 OCR page {idx+1}...")
        start_ocr = time.time()
        processed = preprocess(img_path, do_binarize=False)

        if idx == 0:
            clean, used_image, rotation_used = _ocr_page1_fast(processed)
            page1_rotation = rotation_used
        else:
            clean, used_image, rotation_used = _ocr_with_best_rotation(processed, known_rotation=page1_rotation)

        print(f"      📐 Largeur/hauteur de la page {idx+1} : {used_image.shape[1]} x {used_image.shape[0]}")

        gray_for_quality = used_image if used_image.ndim == 2 else cv2.cvtColor(used_image, cv2.COLOR_BGR2GRAY)
        quality = estimate_image_quality(gray_for_quality)
        garbled = _looks_garbled(clean)
        print(f"      📊 Qualite estimee : nettete={quality['sharpness']:.1f}, contraste={quality['contrast']:.1f}"
              f"{' | texte incoherent detecte' if garbled else ''}")

        if garbled or quality["sharpness"] < SHARPNESS_THRESHOLD:
            print("      ⚠️  Page probablement degradee -> re-OCR avec enhance_for_ocr()...")
            processed_enhanced = preprocess(img_path, do_binarize=False, do_enhance=True)
            clean_enhanced, _, _ = _ocr_with_best_rotation(processed_enhanced, known_rotation=page1_rotation)
            print(f"      🔎 Passage ameliore : {len(clean_enhanced)} detections (vs {len(clean)} initiales)")
            clean.extend(clean_enhanced)

        if idx == 0:
            extra_flag_zone = _retry_ocr_flag_state_zone(used_image, clean)
            if extra_flag_zone:
                clean = _strip_label_bearing_detections(clean)
                clean.extend(extra_flag_zone)

        # Capture l'offset de CETTE page AVANT de shifter ses propres
        # detections et avant de l'incrementer pour la page suivante.
        current_page_y_offset = y_offset

        if y_offset > 0:
            for d in clean:
                d["bbox"]["y0"] += y_offset
                d["bbox"]["y1"] += y_offset

        avant = len(clean)
        clean = _dedupe_detections(clean)
        if len(clean) < avant:
            print(f"      🧹 {avant - len(clean)} detection(s) dupliquee(s) retiree(s)")

        if idx == 0:
            page1_detections = list(clean)
            page_width = used_image.shape[1]

        page_images.append((used_image, current_page_y_offset))

        all_detections.extend(clean)
        print(f"      → {len(clean)} détections en {time.time() - start_ocr:.2f}s")

        y_offset += used_image.shape[0] + 200

    print(f"\n   📊 Extraction des champs DGM...")
    start_extract = time.time()

    retry_fn = _make_narrow_columns_retry_fn(page_images) if page_images else None
    fields = extract_dgm_full(page1_detections, all_detections,
                               retry_narrow_columns_fn=retry_fn, page_width=page_width)
    print(f"      → extraction en {time.time() - start_extract:.2f}s")

    print("\n   🔧 DEBUG champs extraits :")
    for k, v in fields.items():
        if k != "dangerous_goods":
            print(f"      {k}: {v!r}")
    print(f"      dangerous_goods: {len(fields.get('dangerous_goods', []))} ligne(s)")
    for row in fields.get("dangerous_goods", [])[:5]:
        print(f"         {row}")

    result = build_output("DGM", fields, pdf_path)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_path = os.path.join(output_dir, f"{base_name}_result.json")
    export_json(result, output_path)

    print(f"\n   ⏱️  Total: {time.time() - start_total:.2f}s")
    print(f"   ✅ Résultat: {output_path}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Pipeline OCR - Dangerous Cargo Manifest")
    parser.add_argument("pdf_path", help="Chemin vers le PDF DGM")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"❌ Fichier '{args.pdf_path}' inexistant")
        return

    try:
        process_dgm_pdf(args.pdf_path, args.output_dir)
    except Exception as e:
        print(f"❌ Erreur : {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
