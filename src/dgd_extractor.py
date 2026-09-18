"""
dgd_extractor.py - Extraction complete d'un Dangerous Cargo Declaration
=========================================================================
En-tete : Booking Nr, Voyage No, Ship Name, Call Sign, IMO Number,
Flag State, ETA, ETD, Previous/Next port of call.

Mise en page particuliere : plusieurs champs sur la MEME ligne physique,
separes par des pointilles de formulaire ("……") ou des espaces, ex:
    "Ship Name…MAERSK BENGUELA… Call Sign… VRLA3…… IMO Number…9355367 …"

Le systeme colonnes gauche/droite de field_extractor.py (concu pour 2
champs par ligne, alignes en 2 colonnes fixes) ne convient pas ici (3
champs par ligne, positions X variables selon la longueur du texte
precedent). A la place : on reconstruit le texte de CHAQUE ligne
physique, puis on extrait chaque valeur par regex BORNEE entre son
propre libelle et le PROCHAIN libelle attendu sur la meme ligne (ou fin
de ligne si dernier champ).
"""

import re

from field_extractor import group_into_lines, clean_token, is_junk_token
from dgd_table_extractor import extract_dgd_table

# Champs attendus par ligne physique, DANS L'ORDRE ou ils apparaissent.
# Chaque tuple : (field_key, liste de patterns regex acceptes pour le libelle).
HEADER_LINES_SPEC = [
    [
        ("booking_nr", [r"booking\s*n\w{0,2}"]),
        ("voyage_no", [r"voyage\s*no", r"n\s*°?\s*voyage", r"\bvoyage\b"]),
    ],
    [
        ("ship_name", [r"ship\s*name"]),
        ("call_sign", [r"call\s*s?\w{0,2}ign", r"call\s*sign"]),
        ("imo_number", [r"imo\s*n\w{0,3}umber"]),
    ],
    [
        ("flag_state", [r"flag\s*state"]),
        ("eta", [r"\beta\b"]),
        ("etd", [r"\betd\b"]),
    ],
    [
        ("previous_port_of_call", [r"previous\s*port\s*of\s*call", r"p\w*ious\s*port\s*of\s*call",
                                    r"\bp\w{2,10}\s*port\s*of\s*call"]),
        ("next_port_of_call", [r"next\s*port\s*of\s*call"]),
    ],
]

ALL_LABEL_PATTERNS = [p for line_spec in HEADER_LINES_SPEC for _, patterns in line_spec for p in patterns]

# Caracteres de pointilles de formulaire + ponctuation a nettoyer en
# debut/fin de valeur extraite.
_STRIP_CHARS = " .…_:()\u2018\u2019'\"-"


def _clean_extracted_value(value: str) -> str:
    value = value.strip(_STRIP_CHARS)
    # Retire les points de suite internes restants ("MAERSK…BENGUELA" ne
    # devrait pas arriver car les labels bornent bien, mais par securite
    # on normalise les espaces multiples issus du nettoyage).
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _extract_fields_from_line_text(line_text: str, line_spec: list) -> dict:
    """
    Extrait chaque champ de line_spec depuis le texte d'UNE ligne
    physique, en bornant chaque valeur entre son propre libelle et le
    PROCHAIN libelle de la meme ligne (ou fin de chaine pour le dernier).
    """
    # Localise la position de fin de match de chaque libelle present.
    matches = []
    for field_key, patterns in line_spec:
        for pattern in patterns:
            m = re.search(pattern, line_text, re.IGNORECASE)
            if m:
                matches.append((field_key, m.start(), m.end()))
                break

    matches.sort(key=lambda t: t[1])

    result = {}
    for i, (field_key, start, end) in enumerate(matches):
        next_start = matches[i + 1][1] if i + 1 < len(matches) else len(line_text)
        raw_value = line_text[end:next_start]
        value = _clean_extracted_value(raw_value)
        result[field_key] = value if value and not is_junk_token(value) else None

    return result


def extract_dgd_header(detections: list) -> dict:
    """
    Extrait les 10 champs d'en-tete du DGD. Un champ non trouve (libelle
    absent) ou dont la valeur est vide sur le document retourne None.
    """
    all_fields = {}
    for line_spec in HEADER_LINES_SPEC:
        for field_key, _ in line_spec:
            all_fields[field_key] = None

    lines = group_into_lines(detections, y_tol=14.0)
    lines.sort(key=lambda line: min(w["bbox"]["y0"] for w in line))

    used_line_idx = set()
    for line_spec in HEADER_LINES_SPEC:
        expected_labels = [p for _, patterns in line_spec for p in patterns]

        best_idx, best_score = None, 0
        for idx, line in enumerate(lines):
            if idx in used_line_idx:
                continue
            text_low = " ".join(w["text"] for w in line).lower()
            score = sum(1 for p in expected_labels if re.search(p, text_low, re.IGNORECASE))
            if score > best_score:
                best_idx, best_score = idx, score

        if best_idx is None or best_score == 0:
            continue

        used_line_idx.add(best_idx)
        sorted_line = sorted(lines[best_idx], key=lambda w: w["bbox"]["x0"])
        line_text = " ".join(clean_token(w["text"]) for w in sorted_line)

        extracted = _extract_fields_from_line_text(line_text, line_spec)
        all_fields.update({k: v for k, v in extracted.items() if v is not None})

    if all_fields.get("imo_number"):
        digits = re.sub(r"[^\d]", "", all_fields["imo_number"])
        all_fields["imo_number"] = digits if digits else None

    return all_fields


def extract_dgd_full(detections: list) -> dict:
    """Point d'entree complet : en-tete + tableau Classe/Division."""
    header = extract_dgd_header(detections)
    table = extract_dgd_table(detections)
    return {**header, "class_division_table": table}