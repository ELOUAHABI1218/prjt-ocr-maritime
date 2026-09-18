"""
main.py - Pipeline OCR complet et rapide
"""

import argparse
import os
import re
import sys
import time
import traceback

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from src.pdf_converter import pdf_to_images
from src.image_preprocessing import preprocess, estimate_image_quality
from src.ocr_engine import run_ocr
from src.ocr_postprocessing import postprocess
from src.field_extractor import extract_fields, ROWS
from src.json_exporter import build_output, export_json
from src.zone_extractor import crop_header_zone, should_run_ocr_on_page


ROTATION_CANDIDATES = [
    cv2.ROTATE_90_COUNTERCLOCKWISE,
    None,
    cv2.ROTATE_90_CLOCKWISE,
    cv2.ROTATE_180,
]

ORIENTATION_KEYWORDS = [
    "health questions", "submitted at the port", "name of ship",
    "international gross", "master's name", "world health organization",
    "imo number", "nationality",
]

ORIENTATION_SCORE_THRESHOLD = 3

EDGE_STRIP_HEIGHT = 220
EDGE_PADDING = 90

NOTE_TEXT_MARKERS = [
    "note:",
    "disease of an infectious nature",
    "persisting for several days",
    "glandular swelling",
    "shortness of breath",
    "acute skin rash",
    "severe diarrhoea",
    "recurrent convulsions",
]

SHARPNESS_THRESHOLD = 80

_UNSET = object()


def _ocr_with_best_rotation(image, known_rotation=_UNSET):
    """
    Essaie plusieurs rotations sur l'image et retourne (detections, image_utilisee,
    rotation_utilisee) pour celle qui donne le texte le plus reconnaissable.
    """
    if known_rotation is not _UNSET:
        candidate_image = image if known_rotation is None else cv2.rotate(image, known_rotation)
        raw = run_ocr(candidate_image)
        clean = postprocess(raw)
        print(f"      🔄 Rotation reutilisee (page 1) : {known_rotation} -> {len(clean)} detections")
        return clean, candidate_image, known_rotation

    best_clean, best_image, best_score, best_rotation = [], image, -1, None

    for rotation in ROTATION_CANDIDATES:
        candidate_image = image if rotation is None else cv2.rotate(image, rotation)
        raw = run_ocr(candidate_image)
        clean = postprocess(raw)
        text_all = " ".join(d["text"] for d in clean).lower()
        score = sum(1 for kw in ORIENTATION_KEYWORDS if kw in text_all)
        print(f"      🔄 Rotation {rotation} -> {len(clean)} detections, score mots-cles={score}")

        if score > best_score:
            best_clean, best_image, best_score, best_rotation = clean, candidate_image, score, rotation
        if score >= ORIENTATION_SCORE_THRESHOLD:
            break

    return best_clean, best_image, best_rotation


def _retry_ocr_below_note(image, detections, y_offset_for_page):
    """
    Recadre l'image pour EXCLURE le paragraphe "Note:" et relance un OCR
    CIBLE sur le reste (certificat sanitaire, valid till, re-inspection...).
    """
    note_det = next((d for d in detections if d["text"].strip().lower().startswith("note:")), None)
    if note_det is None:
        return []

    note_y_local = note_det["bbox"]["y0"] - y_offset_for_page
    crop_start = int(note_y_local) + 250
    if crop_start >= image.shape[0]:
        return []

    sub_image = image[crop_start:]
    print(f"      🔎 Passage OCR cible sous 'Note:' (image {sub_image.shape[1]}x{sub_image.shape[0]})...")

    raw = run_ocr(sub_image)
    clean = postprocess(raw)

    for d in clean:
        d["bbox"]["y0"] += crop_start + y_offset_for_page
        d["bbox"]["y1"] += crop_start + y_offset_for_page

    print(f"      🔎 {len(clean)} detections supplementaires trouvees sous 'Note:'")
    return clean


def _retry_ocr_page_edges(used_image, y_offset_for_page):
    """
    Relance un OCR CIBLE sur de fines bandes en haut et en bas de la page,
    avec marge blanche ajoutee, pour recuperer le texte colle au bord.
    """
    h = used_image.shape[0]
    extra = []

    strips = [
        ("haut", 0, min(EDGE_STRIP_HEIGHT, h)),
        ("bas", max(0, h - EDGE_STRIP_HEIGHT), h),
    ]

    for label, y_start, y_end in strips:
        if y_end <= y_start:
            continue

        strip = used_image[y_start:y_end]
        pad_shape = (EDGE_PADDING,) + strip.shape[1:]
        white_pad = np.full(pad_shape, 255, dtype=strip.dtype)
        padded_strip = np.vstack([white_pad, strip, white_pad])

        raw = run_ocr(padded_strip)
        clean = postprocess(raw)

        for d in clean:
            d["bbox"]["y0"] += y_start - EDGE_PADDING + y_offset_for_page
            d["bbox"]["y1"] += y_start - EDGE_PADDING + y_offset_for_page

        print(f"      🔎 Bande '{label}' repadee : {len(clean)} detections supplementaires")
        extra.extend(clean)

    return extra


def _retry_ocr_missing_valid_till(used_image, detections, y_offset_for_page):
    """
    Retry cible si "valid till/til" est absent des detections alors que
    "issued at" (certificate) a ete trouve juste au-dessus. Utilise
    maintenant le meme motif tolerant "til{1,2}" que field_extractor.py,
    pour eviter un retry inutile quand le texte est deja present sous
    forme "valid til" (une seule lettre "l", variante OCR observee sur
    un document reel).
    """
    has_valid_till = any(re.search(r"valid\s+til{1,2}\b", d["text"].lower()) for d in detections)
    if has_valid_till:
        return []

    issued_at_det = next(
        (d for d in detections if "issued at" in d["text"].lower()
         and d["bbox"]["y0"] > y_offset_for_page + 500), None
    )
    if issued_at_det is None:
        return []

    anchor_y_local = issued_at_det["bbox"]["y1"] - y_offset_for_page
    crop_start = int(anchor_y_local) + 5
    crop_end = min(crop_start + 300, used_image.shape[0])
    if crop_end <= crop_start:
        return []

    strip = used_image[crop_start:crop_end]
    pad_shape = (60,) + strip.shape[1:]
    white_pad = np.full(pad_shape, 255, dtype=strip.dtype)
    padded_strip = np.vstack([white_pad, strip, white_pad])

    print(f"      🔎 'valid til(l)' introuvable -> retry cible sous 'issued at' "
          f"(bande {padded_strip.shape[1]}x{padded_strip.shape[0]})...")

    raw = run_ocr(padded_strip)
    clean = postprocess(raw)

    for d in clean:
        d["bbox"]["y0"] += crop_start - 60 + y_offset_for_page
        d["bbox"]["y1"] += crop_start - 60 + y_offset_for_page

    print(f"      🔎 {len(clean)} detections supplementaires trouvees (retry valid till) :")
    for d in clean:
        print(f"         y={d['bbox']['y0']:.0f} x={d['bbox']['x0']:.0f}  '{d['text']}'")

    return clean


def _merge_new_detections(existing: list, new_dets: list, y_tol: float = 15, x_tol: float = 15) -> list:
    """
    Filtre les detections de new_dets deja presentes (meme texte EXACT,
    position proche) dans existing.
    """
    merged = []
    for nd in new_dets:
        nd_text = nd["text"].strip().lower()
        is_dup = any(
            nd_text == ed["text"].strip().lower()
            and abs(nd["bbox"]["y0"] - ed["bbox"]["y0"]) <= y_tol
            and abs(nd["bbox"]["x0"] - ed["bbox"]["x0"]) <= x_tol
            for ed in existing
        )
        if not is_dup:
            merged.append(nd)
    return merged


def _normalize_dedup_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _dedupe_detections(dets: list, y_tol: float = 25) -> list:
    """
    Retire les detections QUASI-IDENTIQUES issues d'UNE SEULE passe OCR.
    """
    ordered = sorted(dets, key=lambda d: -len(d["text"]))
    kept = []
    for d in ordered:
        d_norm = _normalize_dedup_text(d["text"])
        d_y = (d["bbox"]["y0"] + d["bbox"]["y1"]) / 2
        is_dup = False
        if d_norm:
            for k in kept:
                k_norm = _normalize_dedup_text(k["text"])
                k_y = (k["bbox"]["y0"] + k["bbox"]["y1"]) / 2
                if abs(d_y - k_y) <= y_tol and k_norm and (d_norm == k_norm or d_norm in k_norm):
                    is_dup = True
                    break
        if not is_dup:
            kept.append(d)
    return sorted(kept, key=lambda d: (d["bbox"]["y0"], d["bbox"]["x0"]))


def _strip_note_paragraph(detections: list) -> list:
    """
    Retire les detections du paragraphe "Note: In the absence of a
    surgeon..." par leur CONTENU TEXTUEL (fixe, connu a l'avance).
    """
    def is_note_line(text: str) -> bool:
        low = text.lower()
        return any(marker in low for marker in NOTE_TEXT_MARKERS)

    kept = [d for d in detections if not is_note_line(d["text"])]
    removed = len(detections) - len(kept)
    if removed:
        print(f"      🧹 {removed} detection(s) du paragraphe 'Note:' retiree(s) (filtrage par contenu)")
    return kept


def _looks_garbled(clean: list) -> bool:
    """
    Beaucoup de tokens avec peu de lettres distinctes (repetitions type
    "GRRRRAAR") signalent un OCR degrade.
    """
    return sum(1 for d in clean if len(set(d["text"].lower())) <= 3 and len(d["text"]) > 5) > 5

def _retry_ocr_ports_table_right_column(used_image, detections, y_offset_for_page):
    """
    Retry cible sur la MOITIE DROITE du tableau des ports d'escale.
    Le tableau a 2 paires Port|Date cote a cote (voir field_extractor.py,
    extract_ports_of_call) ; sur certains documents, le nom du port de la
    colonne DROITE echappe a l'OCR pleine page (bordures du tableau,
    faible contraste) alors que sa date associee, elle, est bien lue -
    observe concretement : "GIBRALTAR"/"TANGER MED" (colonne droite,
    lignes 1 et 4) absents des detections alors que "04.07.2026" et
    "26.06.2026" sont bien presents.

    On recadre uniquement la moitie droite de la zone du tableau (entre
    "List ports of call" et "Upon request"), on ajoute une marge blanche,
    et on relance l'OCR specifiquement dessus.
    """
    start_det = next(
        (d for d in detections if "list ports of" in d["text"].lower()), None
    )
    end_det = next(
        (d for d in detections if "upon request" in d["text"].lower()), None
    )
    if start_det is None or end_det is None:
        return []

    y_start_local = int(start_det["bbox"]["y0"] - y_offset_for_page)
    y_end_local = int(end_det["bbox"]["y0"] - y_offset_for_page)
    if y_end_local <= y_start_local:
        return []

    page_w = used_image.shape[1]
    x_start = page_w // 2  # moitie droite de la page

    strip = used_image[y_start_local:y_end_local, x_start:page_w]
    if strip.size == 0:
        return []

    pad = 60
    pad_shape_v = (pad, strip.shape[1]) + strip.shape[2:]
    pad_shape_h = (strip.shape[0] + 2 * pad, pad) + strip.shape[2:]
    white_v = np.full(pad_shape_v, 255, dtype=strip.dtype)
    white_h = np.full(pad_shape_h, 255, dtype=strip.dtype)
    padded = np.vstack([white_v, strip, white_v])
    padded = np.hstack([white_h, padded, white_h])

    print(f"      🔎 Retry cible colonne droite du tableau des ports "
          f"(bande {padded.shape[1]}x{padded.shape[0]})...")

    raw = run_ocr(padded)
    clean = postprocess(raw)

    for d in clean:
        d["bbox"]["x0"] += x_start - pad
        d["bbox"]["x1"] += x_start - pad
        d["bbox"]["y0"] += y_start_local - pad + y_offset_for_page
        d["bbox"]["y1"] += y_start_local - pad + y_offset_for_page

    print(f"      🔎 {len(clean)} detections supplementaires trouvees (retry ports) :")
    for d in clean:
        print(f"         y={d['bbox']['y0']:.0f} x={d['bbox']['x0']:.0f}  '{d['text']}'")

    return clean

def process_pdf(pdf_path: str, output_dir: str = "output", document_type: str = "Health",
                 extractor: str = "spatial", llm_model: str = None) -> dict:
    print(f"\n📄 Traitement : {os.path.basename(pdf_path)}")
    start_total = time.time()

    pages_dir = os.path.join(output_dir, "pages")
    image_paths = pdf_to_images(pdf_path, pages_dir, dpi=300)
    print(f"   ✅ Conversion: {len(image_paths)} pages")

    detections = []
    page_image = None
    page_width = None
    page_height = None
    y_offset = 0.0
    page1_rotation = _UNSET

    for idx, img_path in enumerate(image_paths):
        if not should_run_ocr_on_page(idx, document_type):
            print(f"   ⏭️  Page {idx+1} ignorée")
            continue

        print(f"   🔍 OCR page {idx+1}...")
        start_ocr = time.time()
        processed = preprocess(img_path, do_binarize=False)
        zone_image = crop_header_zone(processed, document_type)

        clean, used_image, rotation_used = _ocr_with_best_rotation(zone_image, known_rotation=page1_rotation)
        if idx == 0:
            page1_rotation = rotation_used
        print(f"      📐 Largeur/hauteur de la page {idx+1} : {used_image.shape[1]} x {used_image.shape[0]}")

        # Detection de TRANSPOSITION entre pages.
        page1_is_portrait = None
        this_is_portrait = None
        if idx > 0 and page_width and page_height:
            page1_is_portrait = page_height > page_width
            this_is_portrait = used_image.shape[0] > used_image.shape[1]
            if page1_is_portrait != this_is_portrait:
                print(f"      ⚠️  Orientation transposee detectee page {idx+1} "
                      f"(page1 {'portrait' if page1_is_portrait else 'paysage'}, "
                      f"page {idx+1} {'portrait' if this_is_portrait else 'paysage'}) "
                      f"-> redetection independante de la rotation")
                clean, used_image, rotation_used = _ocr_with_best_rotation(zone_image, known_rotation=_UNSET)
                print(f"      📐 Nouvelle largeur/hauteur de la page {idx+1} : "
                      f"{used_image.shape[1]} x {used_image.shape[0]}")

        # Detection de degradation + re-OCR ameliore si necessaire.
        gray_for_quality = used_image if used_image.ndim == 2 else cv2.cvtColor(used_image, cv2.COLOR_BGR2GRAY)
        quality = estimate_image_quality(gray_for_quality)
        garbled = _looks_garbled(clean)
        print(f"      📊 Qualite estimee : nettete={quality['sharpness']:.1f}, contraste={quality['contrast']:.1f}"
              f"{' | texte incoherent detecte' if garbled else ''}")

        if garbled or quality["sharpness"] < SHARPNESS_THRESHOLD:
            print("      ⚠️  Page probablement degradee -> re-OCR avec enhance_for_ocr()...")
            processed_enhanced = preprocess(img_path, do_binarize=False, do_enhance=True)
            zone_enhanced = crop_header_zone(processed_enhanced, document_type)
            if idx > 0 and page1_is_portrait is not None and page1_is_portrait != this_is_portrait:
                enh_rotation = rotation_used
            else:
                enh_rotation = page1_rotation
            clean_enhanced, _, _ = _ocr_with_best_rotation(zone_enhanced, known_rotation=enh_rotation)
            print(f"      🔎 Passage ameliore : {len(clean_enhanced)} detections (vs {len(clean)} initiales)")
            clean.extend(_merge_new_detections(clean, clean_enhanced))

        if y_offset > 0:
            for d in clean:
                d["bbox"]["y0"] += y_offset
                d["bbox"]["y1"] += y_offset

        extra_note = _retry_ocr_below_note(used_image, clean, y_offset)
        extra_note = _merge_new_detections(clean, extra_note)
        clean.extend(extra_note)

        extra_edges = _retry_ocr_page_edges(used_image, y_offset)
        extra_edges = _merge_new_detections(clean, extra_edges)
        clean.extend(extra_edges)

       
        # Dedoublonnage AGRESSIF - DOIT s'executer AVANT le retry
        # valid_till, jamais apres.
        avant = len(clean)
        clean = _dedupe_detections(clean)
        if len(clean) < avant:
            print(f"      🧹 {avant - len(clean)} detection(s) dupliquee(s) retiree(s) (meme passe OCR)")

        clean = _strip_note_paragraph(clean)

        # Retry cible "valid till/til" - APRES le dedoublonnage agressif.
        extra_valid_till = _retry_ocr_missing_valid_till(used_image, clean, y_offset)
        extra_valid_till = _merge_new_detections(clean, extra_valid_till)
        clean.extend(extra_valid_till)

        extra_ports = _retry_ocr_ports_table_right_column(used_image, clean, y_offset)
        extra_ports = _merge_new_detections(clean, extra_ports)
        clean.extend(extra_ports)

        # Normalisation des coordonnees X pour un ecart de deskew NORMAL.
        if idx > 0 and page_width and used_image.shape[1] != page_width:
            ratio = used_image.shape[1] / page_width
            if 0.85 < ratio < 1.18:
                scale_x = page_width / used_image.shape[1]
                for d in clean:
                    d["bbox"]["x0"] *= scale_x
                    d["bbox"]["x1"] *= scale_x
                print(f"      📐 Coordonnees X de la page {idx+1} redimensionnees "
                      f"(ratio {scale_x:.3f}) pour correspondre a la largeur de reference (page 1: {page_width}px)")
            else:
                print(f"      ⚠️  Ecart de largeur trop important pour une simple remise a l'echelle "
                      f"(page {idx+1}: {used_image.shape[1]}px vs reference {page_width}px) - "
                      f"coordonnees laissees telles quelles")

        detections.extend(clean)
        print(f"      → {len(clean)} détections en {time.time() - start_ocr:.2f}s")

        if idx == 0:
            page_image = used_image
            page_width = used_image.shape[1]
            page_height = used_image.shape[0]

        y_offset += used_image.shape[0] + 200

    print(f"\n   🔍 DEBUG : {len(detections)} détections")
    print("   " + "-" * 60)

    sorted_dets = sorted(detections, key=lambda x: (x["bbox"]["y0"], x["bbox"]["x0"]))
    for i, d in enumerate(sorted_dets[:30]):
        print(f"   {i+1:3d}. y={d['bbox']['y0']:6.0f} x={d['bbox']['x0']:6.0f}  '{d['text'][:40]}'")
    if len(detections) > 30:
        print(f"   ... et {len(detections) - 30} autres")

    hq_idx = None
    for i, d in enumerate(sorted_dets):
        if "Health Questions" in d["text"]:
            hq_idx = i
            break

    if hq_idx is not None:
        print(f"\n   🎯 ZONE crew/passengers/port_date (juste avant 'Health Questions', index {hq_idx}) :")
        for d in sorted_dets[max(0, hq_idx - 12):hq_idx]:
            print(f"      y={d['bbox']['y0']:6.0f} x={d['bbox']['x0']:6.0f}  '{d['text'][:50]}'")

        print(f"\n   🎯 ZONE 'Health Questions' + certificat (index {hq_idx} a la fin, {len(sorted_dets) - hq_idx} entrees) :")
        for d in sorted_dets[hq_idx:]:
            print(f"      y={d['bbox']['y0']:6.0f} x={d['bbox']['x0']:6.0f}  '{d['text'][:60]}'")
    else:
        print("\n   ⚠️  'Health Questions' non trouve dans les detections")

    print("\n   🔎 Recherche directe des lignes du certificat :")
    for keyword in ["sanitation", "certificate", "valid til", "carried", "list ports", "issued at"]:
        matches = [d for d in sorted_dets if keyword.lower() in d["text"].lower()]
        if matches:
            for m in matches:
                print(f"      ✅ '{keyword}' trouve : y={m['bbox']['y0']:.0f} x={m['bbox']['x0']:.0f}  '{m['text']}'")
        else:
            print(f"      ❌ '{keyword}' INTROUVABLE dans les {len(sorted_dets)} detections")

    print("\n   🔍 LABELS TROUVÉS :")
    all_labels = []
    for row in ROWS:
        for _, label, _, _ in row:
            if isinstance(label, list):
                all_labels.extend(label)
            else:
                all_labels.append(label)

    found = []
    for d in detections:
        text = d["text"].lower()
        for label in all_labels:
            if label.lower() in text and label not in found:
                found.append(label)
    if found:
        print(f"   ✅ {', '.join(found)}")
    else:
        print("   ❌ AUCUN label trouvé !")

    print(f"\n   📊 Extraction des champs (moteur: {extractor})...")
    start_extract = time.time()

    if extractor == "llm":
        from src.llm_extractor import extract_fields_llm, MODEL_FAST
        fields = extract_fields_llm(detections, model=llm_model or MODEL_FAST)
    elif extractor == "hybrid":
        from src.qwen_mapper import extract_fields_hybrid, MODEL_QWEN
        fields = extract_fields_hybrid(detections, page_image, model=llm_model or MODEL_QWEN)
    else:
        fields = extract_fields(
            ocr_results=detections,
            page_width=page_width,
            page_height=page_height,
            page_image=page_image
        )

    print(f"      → {len(fields)} champs extraits en {time.time() - start_extract:.2f}s")

    from src.validator import validate_and_correct
    fields, validation_warnings = validate_and_correct(fields)
    if validation_warnings:
        print(f"   ⚠️  {len(validation_warnings)} avertissement(s) de validation :")
        for w in validation_warnings:
            print(f"      - {w}")
    else:
        print(f"   ✅ Validation : aucun avertissement")

    result = build_output(document_type, fields, pdf_path)
    result["validation_warnings"] = validation_warnings
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_path = os.path.join(output_dir, f"{base_name}_result.json")
    export_json(result, output_path)

    print(f"   ⏱️  Total: {time.time() - start_total:.2f}s")
    print(f"   ✅ Résultat: {output_path}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Pipeline OCR - extraction documents maritimes")
    parser.add_argument("pdf_path", nargs="?", default=None, help="Chemin vers le PDF (ou dossier)")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--doc-type", default="Health")
    parser.add_argument("--extractor", choices=["spatial", "llm", "hybrid"], default="spatial")
    parser.add_argument("--llm-model", default=None)
    args = parser.parse_args()

    if args.extractor in ("llm", "hybrid"):
        from src.llm_extractor import warmup_model, MODEL_FAST
        default_model = MODEL_FAST if args.extractor == "llm" else "qwen2.5:3b"
        model_name = args.llm_model or default_model
        print(f"🔥 Prechauffage du modele {model_name} (peut prendre 30-90s la premiere fois)...")
        try:
            elapsed = warmup_model(model_name)
            print(f"   ✅ Modele charge en {elapsed:.1f}s")
        except Exception as e:
            print(f"   ❌ {e}")
            return

    if args.pdf_path:
        if os.path.isdir(args.pdf_path):
            files = [f for f in os.listdir(args.pdf_path) if f.lower().endswith('.pdf')]
            if not files:
                print(f"❌ Aucun PDF trouvé dans '{args.pdf_path}'")
                return
            print(f"📁 Traitement de {len(files)} fichiers")
            for f in files:
                try:
                    process_pdf(os.path.join(args.pdf_path, f), args.output_dir, args.doc_type, args.extractor, args.llm_model)
                except Exception as e:
                    print(f"❌ Erreur sur {f}: {e}")
                    traceback.print_exc()
        else:
            if not os.path.exists(args.pdf_path):
                print(f"❌ Fichier '{args.pdf_path}' inexistant")
                return
            process_pdf(args.pdf_path, args.output_dir, args.doc_type, args.extractor, args.llm_model)
        return

    input_dir = "data/health"
    if not os.path.exists(input_dir):
        print(f"❌ Dossier '{input_dir}' inexistant")
        return
    files = [f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')]
    if not files:
        print(f"❌ Aucun PDF trouvé dans '{input_dir}'")
        return
    for f in files:
        try:
            process_pdf(os.path.join(input_dir, f), args.output_dir, args.doc_type, args.extractor, args.llm_model)
        except Exception as e:
            print(f"❌ Erreur sur {f}: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()