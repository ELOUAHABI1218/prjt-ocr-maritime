"""
dgm_extractor.py - Extraction Dangerous Cargo Manifest                         version peut correcte
======================================================================
========================================================
PRINCIPE : extraction CONFINEE A LA LIGNE PHYSIQUE. Pour chaque ligne
(group_into_lines), on cherche TOUS les labels de champs connus
presents sur cette ligne. La VALEUR de chaque champ trouve est tout ce
qui se trouve, dans le texte de la ligne, ENTRE la fin de son propre
label et le DEBUT du label suivant trouve sur la MEME ligne (ou la fin
de ligne si c'est le dernier). Aucune position X calibree a l'avance -
fonctionne quel que soit le nombre de champs par ligne et le
separateur utilise. Un echec de label n'affecte jamais les autres
champs, meme ceux de la meme ligne.

Compatible avec 2 templates observes :
    - Template A (ex-4) : "Booking Nr .." "Voyage No ...626w.." - un
      champ par ligne, separateurs par points de remplissage.
    - Template B (ex-1/2/3) : "Ship Name : San Alberto  Call Sign:
      A8MW6  IMO Number: 9344643" - jusqu'a 3 champs par ligne,
      separateurs ":".

HISTORIQUE DES FIX :
    - _find_table_start_y : repli sur "container" seul si "container
      number" complet n'est jamais trouve en un seul token (en-tete du
      tableau parfois scinde en 2 tokens OCR separes) - sans ce repli,
      table_start_y retombait a 430 (valeur de secours), excluant TOUT
      l'en-tete utile du document de la recherche.
    - imo_number : tolere le "I" initial perdu par l'OCR, et ne garde
      que les chiffres en sortie (un IMO Number est toujours purement
      numerique - retire le "o" residuel de "IMO" mal reconnu et colle
      au numero, observe concretement : "o9143568").
    - Filet de securite _cap_at_first_date : toute valeur de champ
      (sauf eta/etd) est plafonnee a la premiere date rencontree dedans
      - evite qu'un champ (typiquement flag_state) n'avale une date
      adjacente quand le label ETA lui-meme n'etait pas present sur la
      ligne pour servir de frontiere.
    - booking_nr et autres : une valeur vide apres nettoyage devient ""
      (chaine vide), PAS None - None est reserve au cas ou le LABEL
      LUI-MEME n'a jamais ete trouve nulle part dans le document.
    - _extract_manifest_type : fusionne les lignes proches (<15px
      d'ecart) avant la recherche import/export - un des 5 labels de
      case a cocher peut se retrouver isole dans sa propre "ligne
      physique" par group_into_lines meme avec un ecart de quelques
      px. Tolere aussi un caractere de bruit colle apres le X de coche
      (ex: "XE" au lieu de "X" seul).
    - SINGLE_TOKEN_FIELDS : pour les champs qui n'attendent jamais
      qu'un seul mot (voyage_no, call_sign, booking_nr), on ne garde
      que le premier mot de la valeur nettoyee - corrige un cas ou
      group_into_lines avait fusionne la bonne lecture d'une ligne avec
      un doublon bruite de la meme ligne relu par erreur (observe :
      voyage_no = "626w Yoyuy n eu" au lieu de "626w"). N'affecte
      jamais les champs multi-mots legitimes (ship_name, flag_state,
      previous/next_port_of_call).
"""

import re
from dgm_table_extractor import extract_dgm_table
from field_extractor import (
    normalize_for_label_matching, clean_token, is_junk_token,
    normalize_ocr_results, group_into_lines,
)

DATE_PATTERN = re.compile(r"\d{1,3}[/.\-]\d{1,2}[/.\-]\d{2,4}")
MAX_FALLBACK_VALUE_LENGTH = 40

FIELD_LABEL_PATTERNS = {
    "booking_nr": [r"booking\s*n\.?°?r?"],
    "voyage_no": [
        r"n\.?°?\s*voyage", r"voyage\s*no", r"[vy]{1,2}age\s*n?o?",
    ],
    "ship_name": [r"sh?nip\s*name", r"s[hn]ip\s*name"],
    "call_sign": [r"call\s*sign"],
    "imo_number": [r"i?mo\s*n\w{0,3}umber", r"imo\s*no"],
    "flag_state": [r"flag\s*state"],
    "eta_marker": [r"\beta\b", r"\beta\.{0,3}", r"\bETA\b"],  # frontiere pure, jamais exposee
    "etd": [r"\betd\b", r"\betd\.{0,3}\s*:?"],
    "previous_port_of_call": [
        r"previous\s*port\s*of\s*call",
        r"pre\w{0,3}\s*.{0,4}port\s*of\s*.{0,4}all",
        r"pre\w{0,4}\s*port\s*f\s*al",
        r"previous\s*port\s*of\s*cl{1,2}",
    ],
    "next_port_of_call": [r"next\s*port\s*of\s*call", r"next\s*port"],
}

FALLBACK_PATTERNS = {
    "previous_port_of_call": [
        r"previous\s*port\s*of\s*call",
        r"pre\w{0,4}\s*.{0,6}port\s*.{0,4}(?:of|f)\s*.{0,6}(?:call|all|cl{1,2})",
    ],
    "next_port_of_call": [
        r"next\s*port\s*of\s*call",
        r"nex\w{0,2}\s*port\s*.{0,4}(?:of|f)\s*.{0,6}(?:call|all)",
    ],
}

MANIFEST_TYPE_LABELS = [
    ("import", r"import"),
    ("export", r"export"),
    ("transhipment_unloading", r"transhipment\s*unloading"),
    ("transhipment_loading", r"transhipment\s*loading"),
    ("transit", r"transit"),
]

# Champs qui n'attendent jamais qu'UN SEUL mot - on tronque au premier
# mot pour se proteger d'un doublon bruite fusionne sur la meme ligne.
SINGLE_TOKEN_FIELDS = {"voyage_no", "call_sign", "booking_nr"}


def _find_table_start_y(detections: list) -> float:
    for d in detections:
        if "container number" in d["text"].lower():
            return d["bbox"]["y0"]
    # Repli : en-tete du tableau parfois scinde en 2 tokens OCR
    # separes ("Container" / "Number" sur des lignes differentes).
    for d in detections:
        if re.search(r"\bcontainer\b", d["text"].lower()):
            return d["bbox"]["y0"]
    return 430


def _get_header_lines(detections: list, max_y: float) -> list:
    header_dets = [d for d in detections if d["bbox"]["y0"] < max_y]
    lines = group_into_lines(header_dets, y_tol=12.0)
    lines.sort(key=lambda line: min(w["bbox"]["y0"] for w in line))
    return [sorted(line, key=lambda w: w["bbox"]["x0"]) for line in lines]


def _clean_field_value(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"\.{2,}", " ", value)
    value = re.sub(r"[_~`❏□]+", " ", value)
    value = re.sub(r"^\s*:\s*", "", value)
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" .,:-")
    if len(re.sub(r"[^A-Za-z0-9]", "", value)) < 2:
        return ""
    return value


def _cap_at_first_date(value: str) -> str:
    """
    Plafonne une valeur a la premiere date rencontree dedans - evite
    qu'un champ (typiquement flag_state) n'avale une date adjacente
    quand le label ETA/ETD lui-meme n'etait pas present sur la ligne
    pour servir de frontiere naturelle.
    """
    m = DATE_PATTERN.search(value)
    if m:
        return value[:m.start()].strip()
    return value


def _find_all_field_matches_on_line(line_text_lower: str):
    matches = []
    for field_name, patterns in FIELD_LABEL_PATTERNS.items():
        for pattern in patterns:
            m = re.search(pattern, line_text_lower, re.IGNORECASE)
            if m:
                matches.append((field_name, m.start(), m.end()))
                break
    matches.sort(key=lambda t: t[1])
    return matches


def _fallback_global_search(lines: list, field_name: str) -> str:
    full_text = " \n ".join(" ".join(w["text"] for w in line) for line in lines)
    text_lower = full_text.lower()

    for pattern in FALLBACK_PATTERNS.get(field_name, []):
        m = re.search(pattern, text_lower, re.IGNORECASE)
        if m:
            raw_value = full_text[m.end():m.end() + MAX_FALLBACK_VALUE_LENGTH]
            raw_value = raw_value.split("\n")[0]
            cleaned = _clean_field_value(raw_value)
            if cleaned:
                return cleaned
    return None


def _extract_manifest_type(lines: list) -> list:
    """
    Fusionne d'abord les lignes PROCHES (moins de 15px d'ecart entre
    leur y0) avant de chercher import/export - un des 5 labels de case
    a cocher peut se retrouver isole dans sa propre "ligne physique"
    par group_into_lines meme avec un ecart de quelques px seulement.
    Le test de "X coche" tolere aussi un caractere de bruit colle juste
    apres (ex: "XE" au lieu de "X" seul, artefact OCR observe).
    """
    merged_lines = []
    for line in lines:
        if not line:
            continue
        line_y0 = min(w["bbox"]["y0"] for w in line)
        if merged_lines and abs(line_y0 - merged_lines[-1][1]) < 15:
            merged_lines[-1] = (merged_lines[-1][0] + line, line_y0)
        else:
            merged_lines.append((list(line), line_y0))

    for merged_line, _ in merged_lines:
        sorted_line = sorted(merged_line, key=lambda w: w["bbox"]["x0"])
        line_text = " ".join(w["text"] for w in sorted_line)
        low = line_text.lower()
        if "import" in low and "export" in low:
            checked = []
            label_positions = []
            for key, pattern in MANIFEST_TYPE_LABELS:
                m = re.search(pattern, low)
                if m:
                    label_positions.append((key, m.start(), m.end()))
            label_positions.sort(key=lambda t: t[1])

            for i, (key, m_start, m_end) in enumerate(label_positions):
                next_start = (label_positions[i + 1][1]
                              if i + 1 < len(label_positions) else len(line_text))
                segment = line_text[m_end:next_start]
                if re.search(r"(?<![A-Za-z])X(?![A-Za-z])|(?<![A-Za-z])X[A-Za-z](?![A-Za-z])", segment):
                    checked.append(key)
            return checked if checked else None
    return None


def extract_dgm_header(detections: list) -> dict:
    table_start_y = _find_table_start_y(detections)
    lines = _get_header_lines(detections, table_start_y)

    field_names = [f for f in FIELD_LABEL_PATTERNS if f != "eta_marker"]
    data = {field_name: None for field_name in field_names}

    for line in lines:
        if not line:
            continue
        line_text = " ".join(w["text"] for w in line)
        line_text_lower = line_text.lower()

        matches = _find_all_field_matches_on_line(line_text_lower)
        if not matches:
            continue

        for i, (field_name, m_start, m_end) in enumerate(matches):
            if field_name == "eta_marker":
                continue
            if data.get(field_name) is not None:
                continue
            next_start = matches[i + 1][1] if i + 1 < len(matches) else len(line_text)
            raw_value = line_text[m_end:next_start]
            cleaned = _clean_field_value(raw_value)
            if field_name not in ("eta", "etd"):
                cleaned = _cap_at_first_date(cleaned)
            if field_name in SINGLE_TOKEN_FIELDS and cleaned:
                cleaned = cleaned.split(" ")[0]
            data[field_name] = cleaned

    for field_name in ("previous_port_of_call", "next_port_of_call"):
        if not data.get(field_name):
            fallback = _fallback_global_search(lines, field_name)
            if fallback:
                data[field_name] = fallback

    eta = None
    for line in lines:
        line_text = " ".join(w["text"] for w in line)
        low = line_text.lower()
        if "eta" in low:
            dates = DATE_PATTERN.findall(line_text)
            if dates:
                eta = dates[0]
            break
    data["eta"] = eta

    if not data.get("etd"):
        for line in lines:
            line_text = " ".join(w["text"] for w in line)
            low = line_text.lower()
            if "eta" in low or "etd" in low:
                dates = DATE_PATTERN.findall(line_text)
                if len(dates) >= 2:
                    data["etd"] = dates[1]
                break

    if data.get("call_sign"):
        m = re.search(r"([A-Z0-9]{4,8})", data["call_sign"].upper())
        data["call_sign"] = m.group(1) if m else None

    if data.get("imo_number"):
        digits = re.sub(r"[^\d]", "", data["imo_number"])
        data["imo_number"] = digits if digits else None

    manifest_type = _extract_manifest_type(lines)
    if manifest_type is None:
        manifest_type_det = next(
            (d for d in detections if "import" in d["text"].lower()
             and "export" in d["text"].lower()), None
        )
        checked_types = []
        if manifest_type_det:
            text_low = manifest_type_det["text"].lower()
            for key, pattern in MANIFEST_TYPE_LABELS:
                m = re.search(pattern + r"\s*x\b", text_low)
                if m:
                    checked_types.append(key)
        manifest_type = checked_types if checked_types else None
    data["manifest_type"] = manifest_type

    return data


def extract_dgm(detections: list, **kwargs) -> dict:
    data = extract_dgm_header(detections)
    data["dangerous_goods"] = []
    return data

def extract_dgm_full(page1_detections: list, all_detections: list,
                      retry_narrow_columns_fn=None, **kwargs) -> dict:
    """
    Point d'entree complet : champs d'en-tete (page 1 uniquement) +
    tableau dangerous_goods (toutes pages, coordonnees Y cumulees).
    """
    data = extract_dgm_header(page1_detections)
    table_start_y = _find_table_start_y(page1_detections)
    data["dangerous_goods"] = extract_dgm_table(
        all_detections, table_start_y,
        retry_narrow_columns_fn=retry_narrow_columns_fn,
        header_fields=data,  # NOUVEAU : permet de filtrer les valeurs d'en-tete dupliquees
    )
    return data