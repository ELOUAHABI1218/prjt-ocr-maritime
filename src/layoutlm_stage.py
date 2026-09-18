"""
layoutlm_stage.py
==================
Etape intermediaire entre PaddleOCR et le LLM final (Qwen2.5-3B) :
utilise LayoutLMv3 pour classer chaque mot detecte par l'OCR en 3
categories generiques (checkpoint public FUNSD, PAS finetune sur nos
documents specifiques) :
    - HEADER  : titre/entete de section
    - QUESTION: un LABEL de champ (ex: "Master's Name", "IMO Number")
    - ANSWER  : une VALEUR (ex: "CAPT. CHERNIKOV, SERGII", "9143568")
    - O       : rien d'interessant (texte de paragraphe, etc.)

Puis regroupe les tokens adjacents de meme categorie en ENTITES, et lie
chaque entite QUESTION a l'entite ANSWER la plus proche spatialement (sur
la meme ligne, a droite) - resultat : une liste de paires (label, valeur)
bien plus courte et structuree que le texte OCR brut, a transmettre au LLM
final pour le mapping vers le schema JSON.

IMPORTANT : le checkpoint utilise (nielsr/layoutlmv3-finetuned-funsd) est
un modele GENERIQUE entraine sur des formulaires differents des tiens
(dataset FUNSD). Il peut se tromper sur des mises en page inhabituelles -
c'est un filtre de nettoyage, pas une verite absolue. A affiner (ou
remplacer par un modele finetune sur tes documents) si les resultats sont
insatisfaisants.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image
import torch
from transformers import LayoutLMv3ForTokenClassification, LayoutLMv3Processor

MODEL_CHECKPOINT = "nielsr/layoutlmv3-finetuned-funsd"

_PROCESSOR = None
_MODEL = None


def _get_model():
    """Chargement paresseux (une seule fois) - le modele et le processor
    sont couteux a charger, comme pour PaddleOCR."""
    global _PROCESSOR, _MODEL
    if _MODEL is None:
        _PROCESSOR = LayoutLMv3Processor.from_pretrained(MODEL_CHECKPOINT, apply_ocr=False)
        _MODEL = LayoutLMv3ForTokenClassification.from_pretrained(MODEL_CHECKPOINT)
        _MODEL.eval()
    return _PROCESSOR, _MODEL


def _normalize_bbox(bbox: dict, img_width: int, img_height: int) -> list[int]:
    """LayoutLMv3 attend des bboxes normalisees sur une echelle 0-1000,
    independante de la resolution reelle de l'image."""
    x0 = max(0, min(1000, int(1000 * bbox["x0"] / img_width)))
    y0 = max(0, min(1000, int(1000 * bbox["y0"] / img_height)))
    x1 = max(0, min(1000, int(1000 * bbox["x1"] / img_width)))
    y1 = max(0, min(1000, int(1000 * bbox["y1"] / img_height)))
    return [x0, y0, x1, y1]


def classify_tokens(image: np.ndarray, ocr_results: list[dict]) -> list[dict]:
    """
    Classe chaque detection OCR en HEADER/QUESTION/ANSWER/O via LayoutLMv3.

    Args:
        image: image de la page (numpy array, comme utilise dans le reste
            du pipeline).
        ocr_results: detections PaddleOCR normalisees {"text","bbox",...}.

    Returns:
        Meme liste que ocr_results, avec une cle supplementaire "label"
        ajoutee a chaque detection ("HEADER","QUESTION","ANSWER","O").
    """
    if not ocr_results:
        return []

    processor, model = _get_model()

    # LayoutLMv3 attend une image PIL RGB.
    if image.ndim == 2:
        pil_image = Image.fromarray(image).convert("RGB")
    else:
        # Suppose BGR (convention OpenCV) -> RGB pour PIL.
        pil_image = Image.fromarray(image[:, :, ::-1]).convert("RGB")

    img_w, img_h = pil_image.size
    words = [d["text"] for d in ocr_results]
    boxes = [_normalize_bbox(d["bbox"], img_w, img_h) for d in ocr_results]

    encoding = processor(
        pil_image, words, boxes=boxes,
        return_tensors="pt", truncation=True, padding="max_length",
        max_length=512,
    )

    with torch.no_grad():
        outputs = model(**encoding)

    predictions = outputs.logits.argmax(-1).squeeze().tolist()
    id2label = model.config.id2label

    # word_ids() mappe chaque token (sous-mot) vers l'index du mot ORIGINAL
    # dans `words` - necessaire car le tokenizer peut decouper un mot en
    # plusieurs sous-tokens.
    word_ids = encoding.word_ids(batch_index=0)

    word_label_votes: dict[int, list[str]] = {}
    for token_idx, word_idx in enumerate(word_ids):
        if word_idx is None:
            continue
        raw_label = id2label[predictions[token_idx]]
        simple_label = raw_label.split("-")[-1] if "-" in raw_label else raw_label
        word_label_votes.setdefault(word_idx, []).append(simple_label)

    labeled = []
    for i, d in enumerate(ocr_results):
        votes = word_label_votes.get(i, ["O"])
        # Label majoritaire parmi les sous-tokens du mot.
        label = max(set(votes), key=votes.count)
        labeled.append({**d, "label": label})

    return labeled


def group_into_qa_pairs(labeled_detections: list[dict], y_tol: float = 12.0, max_gap_x: float = 400.0) -> list[dict]:
    """
    Regroupe les detections QUESTION adjacentes en entites completes (un
    label peut s'etaler sur plusieurs mots/lignes), idem pour ANSWER, puis
    lie chaque QUESTION a l'ANSWER la plus proche sur la meme bande
    verticale, a sa droite.

    Returns:
        Liste de {"label": "texte du label detecte", "value": "texte de
        la valeur associee ou None"}.
    """
    from src.field_extractor import group_into_lines, clean_token

    questions = [d for d in labeled_detections if d["label"] == "QUESTION"]
    answers = [d for d in labeled_detections if d["label"] == "ANSWER"]

    # Regroupe les mots QUESTION/ANSWER en lignes visuelles pour former des
    # entites multi-mots (ex: "Master's" + "Name" -> "Master's Name").
    q_lines = group_into_lines(questions, y_tol=y_tol) if questions else []
    a_lines = group_into_lines(answers, y_tol=y_tol) if answers else []

    def line_to_entity(line):
        sorted_words = sorted(line, key=lambda d: d["bbox"]["x0"])
        text = " ".join(clean_token(w["text"]) for w in sorted_words).strip()
        y_center = sum((w["bbox"]["y0"] + w["bbox"]["y1"]) / 2 for w in line) / len(line)
        x_end = max(w["bbox"]["x1"] for w in line)
        x_start = min(w["bbox"]["x0"] for w in line)
        return {"text": text, "y_center": y_center, "x_start": x_start, "x_end": x_end}

    q_entities = [line_to_entity(l) for l in q_lines if l]
    a_entities = [line_to_entity(l) for l in a_lines if l]

    pairs = []
    used_answers = set()
    for q in q_entities:
        best_answer, best_dist = None, float("inf")
        for idx, a in enumerate(a_entities):
            if idx in used_answers:
                continue
            if a["x_start"] < q["x_end"]:
                continue  # la valeur doit etre a DROITE du label
            y_dist = abs(a["y_center"] - q["y_center"])
            x_dist = a["x_start"] - q["x_end"]
            if y_dist < y_tol * 2 and x_dist < max_gap_x:
                dist = y_dist * 10 + x_dist  # priorite forte a l'alignement vertical
                if dist < best_dist:
                    best_dist, best_answer = dist, idx
        value = None
        if best_answer is not None:
            value = a_entities[best_answer]["text"]
            used_answers.add(best_answer)
        pairs.append({"label": q["text"], "value": value})

    return pairs


def extract_qa_pairs(image: np.ndarray, ocr_results: list[dict]) -> list[dict]:
    """Point d'entree unique : OCR -> classification LayoutLMv3 -> paires
    label/valeur nettoyees, pretes a etre transmises au LLM final."""
    labeled = classify_tokens(image, ocr_results)
    return group_into_qa_pairs(labeled)