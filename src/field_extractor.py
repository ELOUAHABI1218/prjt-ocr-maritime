"""
field_extractor.py - Extraction par position spatiale
========================================================

FIX (2026-08-09) :
    - VALID_TILL_PATTERN : "till" -> "til{1,2}". PaddleOCR peut lire
      "valid till" avec un seul "l" ("valid til"), confirme sur un
      document reel ('valid til: _15.09.2026' present depuis le debut
      dans les detections brutes, mais jamais matche car la regex
      exigeait l'orthographe exacte "till"). Le contenu utile etait la
      depuis le debut ; seule la recherche etait trop stricte.

FIX (2026-08-08) :
    - CERT_DATE_MAX_DISTANCE : 700 -> 1100px. Le certificat peut etre
      coupe par un saut de page (fin page1 / debut page2) : l'ecart reel
      entre certificate_carried_on_board et la ligne Date/issued at qui
      suit inclut alors la fin de la page 1 + la marge de 200px ajoutee
      entre pages (main.py) + le debut de la page 2 - observe
      concretement a 975px sur un document reel (rejete a tort par
      l'ancien seuil de 700). Le vrai faux positif a rejeter ("Medical
      certificate / Date:" plus bas) est a ~1409px sur ce meme document -
      marge confortable pour distinguer les deux cas avec un seuil de
      1100.
    - crew_and_others_joined : la ligne d'EN-TETE elle-meme ("Name",
      "Joined at port", "Date of joining") ne doit pas etre incluse comme
      une entree du tableau - exclue explicitement via id() des mots de
      header_line, plus un filtre de securite name.lower() != "name".
"""

import re

try:
    from strikethrough_detector import resolve_yes_no
except ImportError:
    resolve_yes_no = None


DEFAULT_COLUMN_FRACTIONS = {
    "left_value_start": 0.30,
    "left_value_end": 0.45,
    "right_value_start": 0.58,
}

Y_TOL = 10.0

ROWS = [
    [("submitted_port", "Submitted at the port of", "left", "left"),
     ("submission_date", "Date", "right", "right")],
    [("ship_name", "Name of Ship or inland navigation vessel", "left", "left"),
     ("imo_number", "IMO Number", "right", "right")],
    [("last_port", "Arriving from", "left", "left"),
     ("next_port", "Sailing to", "right", "right")],
    [("nationality", "Nationality / Flag of vessel", "left", "left"),
     ("master_name", "Master's Name", "right", "right")],
    [("gross_tonnage", "Gross Tonnage", "left", "left"),
     ("net_tonnage", "Net Tonnage", "right", "right")],
    [("who_affected_area", "World Health Organization", "left", "right")],
    [("port_date_visit_area", "date of visit", "left", "left")],
    [("crew_members", ["Number of crew members", "crew members"], "left", "left"),
     ("passengers", ["Number of passenger", "passenger on"], "right", "right")],
    [("certificate_carried_on_board", "Certificate carried", "left", "right")],
    [("certificate_date", "Date", "left", "left"),
     ("certificate_issued_at", "issued at", "left", "right")],
    [("valid_till", "valid till", "right", "right")],
    [("re_inspection_required", "Re-inspection required?", "left", "right")],
    [("water_analysis_date", "analysis of the drinking water", "left", "left"),
     ("water_analysis_issued_at", "issued at", "left", "right")],
    [("medical_certificate_date", "Medical certificate", "left", "left"),
     ("medical_certificate_issued_at", "issued at", "left", "right")],
    [("fumigated_cargo", "transport fumigated cargo", "left", "right")],
]

SENTINEL_LABEL = "Health Questions"
SECOND_SENTINEL_LABEL = "List ports of"

WIDE_RIGHT_FIELDS = {"certificate_carried_on_board",
                      "water_analysis_issued_at", "medical_certificate_issued_at",
                      "certificate_issued_at"}

WIDE_RIGHT_Y_MARGIN = 60

STRIKETHROUGH_FIELDS = {"who_affected_area", "certificate_carried_on_board"}

FULL_LABELS = {
    "submitted_port": "Submitted at the port of",
    "submission_date": "Date",
    "ship_name": "Name of Ship or inland navigation vessel",
    "imo_number": "IMO Number",
    "last_port": "Arriving from (Last port)",
    "next_port": "Sailing to (Next port)",
    "nationality": "Nationality / Flag of vessel",
    "master_name": "Master's Name",
    "gross_tonnage": "International Gross Tonnage",
    "net_tonnage": "International Net Tonnage",
    "who_affected_area": "World Health Organization",
    "port_date_visit_area": "Port and date of visit (affected area)",
    "crew_members": ["Number of crew members", "on board"],
    "passengers": ["Number of passenger", "on board"],
    "certificate_carried_on_board": "Certificate carried",
    "certificate_date": "Date",
    "certificate_issued_at": "issued at",
    "valid_till": "valid till",
    "re_inspection_required": "Re-inspection required?",
    "water_analysis_issued_at": "issued at",
    "medical_certificate_issued_at": "issued at",
}

QUESTION_ANCHORS = {
    1: "died on board",
    2: "infectious nature",
    3: "greater than normal",
    4: "sick person on board now",
    5: "medical practitioner consulted",
    6: "aware of any condition",
    7: "sanitary measure",
    8: "stowaways",
    9: "sick animal or pet",
}

CERT_DATE_MAX_DISTANCE = 1100.0

# FIX : til{1,2} tolere "til" ET "till" (OCR peut manger une lettre).
VALID_TILL_PATTERN = re.compile(r"valid\s+til{1,2}\s*[:\-]?\s*(.+)", re.IGNORECASE)


def normalize_for_label_matching(text: str) -> str:
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def clean_token(text: str) -> str:
    return text.strip("_~`'\u2018\u2019 -*")


def is_junk_token(text: str) -> bool:
    stripped = re.sub(r"[^a-zA-Z0-9]", "", text)
    if stripped:
        return False
    return len(text.strip()) > 2


def normalize_ocr_results(raw_results) -> list:
    normalized = []
    for r in raw_results:
        bbox = r.get("bbox")
        if isinstance(bbox, dict):
            normalized.append(r)
            continue
        if isinstance(bbox, (list, tuple)) and bbox and isinstance(bbox[0], (list, tuple)):
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            normalized.append({
                "text": r["text"],
                "confidence": r.get("confidence", 1.0),
                "bbox": {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)},
            })
    return [d for d in normalized if not is_junk_token(d["text"])]


def group_into_lines(detections: list, y_tol: float = Y_TOL) -> list:
    sorted_dets = sorted(detections, key=lambda d: d["bbox"]["y0"])
    lines = []
    for d in sorted_dets:
        y_center = (d["bbox"]["y0"] + d["bbox"]["y1"]) / 2
        placed = False
        for line in lines:
            line_y = sum((w["bbox"]["y0"] + w["bbox"]["y1"]) / 2 for w in line) / len(line)
            if abs(y_center - line_y) <= y_tol:
                line.append(d)
                placed = True
                break
        if not placed:
            lines.append([d])
    for line in lines:
        line.sort(key=lambda d: d["bbox"]["x0"])
    return lines


def find_row_top_y(lines: list, label_fragment, search_from_idx: int, label_x_range: tuple):
    if isinstance(label_fragment, list):
        for label in label_fragment:
            y_top, new_idx = find_row_top_y(lines, label, search_from_idx, label_x_range)
            if y_top is not None:
                return y_top, new_idx
        return None, search_from_idx

    target = normalize_for_label_matching(label_fragment)
    x_min, x_max = label_x_range

    def col_words(line):
        return [d for d in line if x_min <= d["bbox"]["x0"] < x_max]

    def col_text(line):
        return normalize_for_label_matching(" ".join(d["text"] for d in col_words(line)))

    def line_min_y(*line_group):
        words = [w for line in line_group for w in line]
        return min(w["bbox"]["y0"] for w in words) if words else None

    for i in range(search_from_idx, len(lines)):
        if target in col_text(lines[i]):
            y = line_min_y(lines[i])
            if y is not None:
                return y, i + 1

    for i in range(search_from_idx, len(lines) - 1):
        combined = (col_text(lines[i]) + " " + col_text(lines[i + 1])).strip()
        if target in combined:
            y = line_min_y(lines[i], lines[i + 1])
            if y is not None:
                return y, i + 2

    return None, search_from_idx


def find_row_top_y_after(lines: list, label_fragment, min_y: float, label_x_range: tuple):
    """
    Variante de find_row_top_y qui ne considere que les lignes STRICTEMENT
    APRES min_y - impossible de sauter une ligne suivante par accident.
    """
    filtered = [line for line in lines if min(w["bbox"]["y0"] for w in line) > min_y]
    y_top, _ = find_row_top_y(filtered, label_fragment, 0, label_x_range)
    return y_top


def extract_value_in_band(detections: list, y_top: float, y_bottom: float,
                           x_min: float, x_max: float) -> str:
    in_band = [
        d for d in detections
        if y_top <= d["bbox"]["y0"] < y_bottom
        and x_min <= d["bbox"]["x0"] < x_max
    ]
    lines = group_into_lines(in_band)
    parts = [" ".join(clean_token(d["text"]) for d in line) for line in lines]
    return " ".join(parts).strip()


def extract_inline_fallback(detections: list, y_top: float, y_bottom: float, full_label) -> str:
    labels = full_label if isinstance(full_label, list) else [full_label]
    candidates = [d for d in detections if y_top <= d["bbox"]["y0"] < y_bottom]
    for label in labels:
        pattern = re.compile(r"\s+".join(re.escape(w) for w in label.split()), re.IGNORECASE)
        for d in candidates:
            m = pattern.search(d["text"])
            if m and m.end() < len(d["text"]):
                suffix = d["text"][m.end():].strip(" _:().,\u2018\u2019'\"-*")
                if suffix and not is_junk_token(suffix):
                    return suffix
    return None


def clean_value_against_label(value: str, full_label) -> str:
    """
    Retire le prefixe "label" d'une valeur, QU'ELLE SOIT VIDE OU NON.
    Necessaire quand l'OCR fusionne label et valeur en un seul token.
    """
    if not value or not full_label:
        return value
    labels = full_label if isinstance(full_label, list) else [full_label]
    for label in labels:
        pattern = re.compile(r"^\s*" + r"\s+".join(re.escape(w) for w in label.split()), re.IGNORECASE)
        m = pattern.match(value)
        if m:
            suffix = value[m.end():].strip(" _:().,\u2018\u2019'\"-*")
            if suffix and not is_junk_token(suffix):
                return suffix
    return value


def strip_trailing_valid_till(value: str) -> str:
    """
    Nettoie une valeur de certificate_issued_at qui aurait englouti le
    "valid til(l): ..." qui suit dans le MEME token OCR fusionne.
    """
    if not value:
        return value
    m = re.search(r"\s*valid\s+til{1,2}\s*[:\-]?", value, re.IGNORECASE)
    if m:
        return value[:m.start()].strip()
    return value


def extract_valid_till_fallback(detections: list) -> str:
    """
    "valid till" (ou "valid til", OCR peut manger une lettre) peut se
    retrouver FUSIONNE dans le MEME token OCR qu'une autre ligne.
    Recherche DIRECTE du motif dans le texte brut de TOUTES les
    detections, hors du systeme de lignes.
    """
    for d in detections:
        m = VALID_TILL_PATTERN.search(d["text"])
        if m:
            suffix = m.group(1).strip(" _:().,\u2018\u2019'\"-*")
            if suffix and not is_junk_token(suffix):
                return suffix
    return None


def _find_yes_no_header_columns(detections: list):
    yes_range, no_range = None, None
    for d in detections:
        t = clean_token(d["text"]).upper()
        if t == "YES" and yes_range is None:
            yes_range = (d["bbox"]["x0"], d["bbox"]["x1"])
        elif t == "NO" and no_range is None:
            no_range = (d["bbox"]["x0"], d["bbox"]["x1"])
        if yes_range and no_range:
            break
    return yes_range, no_range


def _pixel_dark_fraction(image_gray, y_top: float, y_bottom: float, x_range, dark_threshold: int = 127) -> float:
    if image_gray is None or x_range is None:
        return 0.0
    x0, x1 = int(x_range[0]), int(x_range[1])
    y0, y1 = int(y_top), int(y_bottom)
    crop = image_gray[y0:y1, x0:x1]
    if crop.size == 0:
        return 0.0
    return float((crop < dark_threshold).sum()) / crop.size


def _resolve_strikethrough_yes_no(detections, y_top, y_bottom, page_image, current_value):
    if page_image is None or resolve_yes_no is None:
        return current_value

    band_dets = [d for d in detections if y_top <= d["bbox"]["y0"] < y_bottom]
    yes_bbox, no_bbox = None, None
    yi, ni = -1, -1

    for d in band_dets:
        text_upper = clean_token(d["text"]).upper()
        yi, ni = text_upper.find("YES"), text_upper.find("NO")
        if yi != -1 and ni != -1 and len(text_upper) > 0:
            bx0, bx1 = d["bbox"]["x0"], d["bbox"]["x1"]
            width = bx1 - bx0
            n = len(text_upper)
            char_x = lambda idx: bx0 + width * (idx / n)
            yes_bbox = {"x0": char_x(yi), "y0": d["bbox"]["y0"], "x1": char_x(yi + 3), "y1": d["bbox"]["y1"]}
            no_bbox = {"x0": char_x(ni), "y0": d["bbox"]["y0"], "x1": char_x(ni + 2), "y1": d["bbox"]["y1"]}
            break

    if yes_bbox is None and no_bbox is None:
        yes_tok = next((d for d in band_dets if clean_token(d["text"]).upper().startswith("YES")), None)
        no_tok = next((d for d in band_dets if "NO" in clean_token(d["text"]).upper()
                        and not clean_token(d["text"]).upper().startswith("YES")), None)
        yes_bbox = yes_tok["bbox"] if yes_tok else None
        no_bbox = no_tok["bbox"] if no_tok else None

    if not (yes_bbox or no_bbox):
        return current_value

    img_for_strike = page_image
    if getattr(img_for_strike, "ndim", 2) == 3:
        import cv2 as _cv2
        img_for_strike = _cv2.cvtColor(img_for_strike, _cv2.COLOR_BGR2GRAY)

    resolved = resolve_yes_no(img_for_strike, yes_bbox, no_bbox)
    if resolved:
        return resolved
    if yi != -1 and ni != -1:
        return None
    return current_value


def extract_ports_of_call(detections: list) -> list:
    """
    FIX (2026-08-09, v2) : y_tol elargi a 40 (au lieu de 15) pour le
    regroupement en lignes de CE tableau specifiquement. Observe sur un
    document reel : les tokens d'une meme ligne physique du tableau
    peuvent s'etaler sur plus de 40px de Y (ex: 'GIBRALTAR' y=4866,
    'TANGER MED' y=4907, '26.06.2026' y=4910 - 48px d'ecart total pour
    la meme ligne), largement au-dessus de la tolerance standard de 15px
    utilisee ailleurs dans le pipeline. Avec l'ancienne tolerance, ces
    tokens etaient scindes en 2 lignes distinctes, cassant l'association
    port/date de la paire concernee.
    """
    dets_sorted = sorted(detections, key=lambda d: (d["bbox"]["y0"], d["bbox"]["x0"]))
    lines_all = group_into_lines(dets_sorted, y_tol=15.0)
    lines_all.sort(key=lambda line: min(w["bbox"]["y0"] for w in line))

    header_line = None
    for line in lines_all:
        text = normalize_for_label_matching(" ".join(w["text"] for w in line))
        if "date of departure" in text:
            header_line = line
            break
    if header_line is None:
        return []

    header_y = min(w["bbox"]["y0"] for w in header_line)
    header_ids = {id(w) for w in header_line}

    end_y = None
    for d in dets_sorted:
        if "upon request" in d["text"].lower():
            end_y = d["bbox"]["y0"]
            break

    table_dets = [
        d for d in dets_sorted
        if id(d) not in header_ids
        and d["bbox"]["y0"] > header_y + 10
        and (end_y is None or d["bbox"]["y0"] < end_y)
    ]
    if not table_dets:
        return []

    # y_tol elargi (voir note en tete de fonction).
    lines = group_into_lines(table_dets, y_tol=20.0)
    lines.sort(key=lambda line: min(w["bbox"]["y0"] for w in line))

    date_pattern = re.compile(r"\d{1,2}[/.]\d{1,2}[/.]\d{2,4}")

    ports = []
    for line in lines:
        words = sorted(line, key=lambda w: w["bbox"]["x0"])
        pending_port_words = []
        last_port_seen = None
        for w in words:
            token = clean_token(w["text"])
            if date_pattern.search(token):
                port_tok = " ".join(pending_port_words).strip()
                if not port_tok and last_port_seen:
                    # Port de cette paire absent de l'OCR (colonne droite
                    # souvent moins bien lue) - on ne garde PAS cette
                    # entree plutot que d'inventer un port incertain.
                    pending_port_words = []
                    continue
                if port_tok:
                    ports.append({"port": port_tok, "date_of_departure": token})
                    last_port_seen = port_tok
                pending_port_words = []
            else:
                pending_port_words.append(token)

    return ports

def extract_crew_passenger_list(detections: list) -> list:
    """
    Extrait le tableau "**Upon request... list crew members, passengers...".
    En-tete recherche par LIGNE (substring), pas par token isole en
    egalite stricte. L'en-tete elle-meme est explicitement EXCLUE des
    entrees retournees (via id() des mots de header_line + filtre
    name.lower() != "name" en securite supplementaire).
    """
    dets_sorted = sorted(detections, key=lambda d: (d["bbox"]["y0"], d["bbox"]["x0"]))
    lines_all = group_into_lines(dets_sorted, y_tol=15.0)
    lines_all.sort(key=lambda line: min(w["bbox"]["y0"] for w in line))

    header_line = None
    for line in lines_all:
        text = normalize_for_label_matching(" ".join(w["text"] for w in line))
        if "name" in text and ("joined" in text or "port" in text):
            header_line = line
            break
    if header_line is None:
        return []

    header_y = min(w["bbox"]["y0"] for w in header_line)
    header_ids = {id(w) for w in header_line}
    sorted_header = sorted(header_line, key=lambda w: w["bbox"]["x0"])
    name_x0 = sorted_header[0]["bbox"]["x0"]

    joined_tok = next((w for w in header_line if "joined" in w["text"].lower()), None)
    date_tok = next((w for w in header_line if "joining" in w["text"].lower()), None)

    joined_x0 = joined_tok["bbox"]["x0"] if joined_tok else name_x0 + 700
    date_x0 = date_tok["bbox"]["x0"] if date_tok else joined_x0 + 600

    end_y = None
    for d in dets_sorted:
        if "i hereby declare" in d["text"].lower():
            end_y = d["bbox"]["y0"]
            break

    table_dets = [
        d for d in dets_sorted
        if id(d) not in header_ids
        and d["bbox"]["y0"] > header_y + 10
        and (end_y is None or d["bbox"]["y0"] < end_y)
    ]
    if not table_dets:
        return []

    lines = group_into_lines(table_dets, y_tol=15.0)
    lines.sort(key=lambda line: min(w["bbox"]["y0"] for w in line))

    entries = []
    for line in lines:
        name_words = sorted([w for w in line if w["bbox"]["x0"] < joined_x0 - 20], key=lambda w: w["bbox"]["x0"])
        joined_words = sorted([w for w in line if joined_x0 - 20 <= w["bbox"]["x0"] < date_x0 - 20], key=lambda w: w["bbox"]["x0"])
        date_words = sorted([w for w in line if w["bbox"]["x0"] >= date_x0 - 20], key=lambda w: w["bbox"]["x0"])

        name = " ".join(clean_token(w["text"]) for w in name_words).strip()
        joined_at = " ".join(clean_token(w["text"]) for w in joined_words).strip()
        date_joining = " ".join(clean_token(w["text"]) for w in date_words).strip()

        if name and name.lower() != "name":
            entries.append({
                "name": name,
                "joined_at_port": joined_at or None,
                "date_of_joining": date_joining or None,
            })

    return entries


def extract_health_questions(detections: list, page_image=None) -> dict:
    start_idx = None
    for i, d in enumerate(detections):
        if "Health Questions" in d["text"]:
            start_idx = i
            break
    if start_idx is None:
        for i, d in enumerate(detections):
            if "YES" in d["text"] and "NO" in d["text"]:
                start_idx = i
                break
    if start_idx is None:
        return {f"q{n}": None for n in range(1, 10)}

    search_space = detections[start_idx:]
    yes_col, no_col = _find_yes_no_header_columns(search_space)

    img_gray = page_image
    if img_gray is not None and getattr(img_gray, "ndim", 2) == 3:
        import cv2 as _cv2
        img_gray = _cv2.cvtColor(img_gray, _cv2.COLOR_BGR2GRAY)

    lines = group_into_lines(search_space)
    line_entries = []
    for line in lines:
        sorted_line = sorted(line, key=lambda d: d["bbox"]["x0"])
        text = " ".join(d["text"] for d in sorted_line).lower()
        y_center = sum((d["bbox"]["y0"] + d["bbox"]["y1"]) / 2 for d in line) / len(line)
        line_entries.append((text, y_center))

    questions = {}

    for q_num in range(1, 10):
        target_num = f"{q_num}."
        anchor_text = QUESTION_ANCHORS.get(q_num, "")
        y_center = None
        for text, y in line_entries:
            if target_num in text or (anchor_text and anchor_text.lower() in text):
                y_center = y
                break

        if y_center is None:
            questions[f"q{q_num}"] = None
            continue

        line_dets = [
            d for d in search_space
            if abs((d["bbox"]["y0"] + d["bbox"]["y1"]) / 2 - y_center) < 30
        ]
        line_dets.sort(key=lambda x: x["bbox"]["x0"])

        xs = [d["bbox"]["x0"] for d in line_dets]
        mid_x = (min(xs) + max(xs)) / 2 if xs else 0
        marks = [
            d for d in line_dets
            if d["bbox"]["x0"] > mid_x and len(clean_token(d["text"]).strip()) <= 3
        ]

        if marks:
            avg_mark_x = sum(m["bbox"]["x0"] for m in marks) / len(marks)
            questions[f"q{q_num}"] = "NO" if avg_mark_x > mid_x else "YES"
            continue

        if img_gray is not None and yes_col and no_col:
            y_top, y_bottom = y_center - 22, y_center + 22
            yes_frac = _pixel_dark_fraction(img_gray, y_top, y_bottom, yes_col)
            no_frac = _pixel_dark_fraction(img_gray, y_top, y_bottom, no_col)
            if max(yes_frac, no_frac) > 0.04:
                questions[f"q{q_num}"] = "YES" if yes_frac > no_frac else "NO"
            else:
                questions[f"q{q_num}"] = None
        else:
            questions[f"q{q_num}"] = None

    return questions




class FieldExtractor:
    def __init__(self, page_width: float = None, column_fractions: dict = None):
        self.page_width = page_width
        self.column_fractions = {**DEFAULT_COLUMN_FRACTIONS, **(column_fractions or {})}

    def extract(self, ocr_results: list = None, page_image=None, **kwargs) -> dict:
        if not ocr_results:
            raise ValueError("ocr_results requis pour l'extraction.")

        detections = normalize_ocr_results(ocr_results)
        page_width = self.page_width or max(d["bbox"]["x1"] for d in detections)
        if not page_width:
            page_width = 2000

        left_x0 = page_width * self.column_fractions["left_value_start"]
        left_x1 = page_width * self.column_fractions["left_value_end"]
        right_x0 = page_width * self.column_fractions["right_value_start"]

        data = {}
        data.update(self._extract_fields(detections, page_width, left_x0, left_x1, right_x0, page_image))
        data["health_questions"] = extract_health_questions(detections, page_image=page_image)
        data["ports_of_call"] = extract_ports_of_call(detections)
        data["crew_and_others_joined"] = extract_crew_passenger_list(detections)
        return data

    def _extract_fields(self, detections, page_width, left_x0, left_x1, right_x0, page_image=None):
        lines = group_into_lines(detections)
        data = {}
        row_tops = []

        crew_row_idx = next(i for i, row in enumerate(ROWS) if row[0][0] == "crew_members")

        # --- Phase 1 : en-tete (jusqu'a crew/passengers inclus). ---
        search_idx = 0
        checkpoint_after_crew = None
        for i, row in enumerate(ROWS):
            if i > crew_row_idx:
                break
            _, label, label_side, _ = row[0]
            label_range = (0, left_x0) if label_side == "left" else (left_x1, right_x0)
            y_top, search_idx = find_row_top_y(lines, label, search_idx, label_range)
            row_tops.append(y_top)
            if i == crew_row_idx:
                checkpoint_after_crew = search_idx

        # --- Phase 2 : bloc certificat + eau + medical + cargo fumige.
        # LABEL cherche sur TOUTE LA LARGEUR + recherche Y CROISSANTE
        # STRICTE. ---
        last_known_y = row_tops[crew_row_idx] if row_tops[crew_row_idx] is not None else -1.0
        full_width_range = (0, page_width * 1.05)

        for i, row in enumerate(ROWS):
            if i <= crew_row_idx:
                continue
            _, label, _, _ = row[0]
            y_top = find_row_top_y_after(lines, label, last_known_y, full_width_range)
            row_tops.append(y_top)
            if y_top is not None:
                last_known_y = y_top

        hq_sentinel_y, _ = find_row_top_y(lines, SENTINEL_LABEL, checkpoint_after_crew, (0, left_x0))
        ports_sentinel_y = find_row_top_y_after(lines, SECOND_SENTINEL_LABEL, last_known_y, full_width_range)

        max_y = max(d["bbox"]["y1"] for d in detections) + 50

        row_tops_ext = list(row_tops)
        row_tops_ext.insert(crew_row_idx + 1, hq_sentinel_y)
        row_tops_ext.append(ports_sentinel_y)

        def ext_index(i):
            return i if i <= crew_row_idx else i + 1

        print("   🔧 DEBUG row_tops (champs certificat) :")
        for i, row in enumerate(ROWS):
            for field_name, _, _, _ in row:
                if field_name in ("certificate_carried_on_board", "certificate_date",
                                   "certificate_issued_at", "valid_till", "re_inspection_required",
                                   "water_analysis_date", "medical_certificate_date", "fumigated_cargo"):
                    print(f"      {field_name}: row_top={row_tops_ext[ext_index(i)]}")
        print(f"      ports_sentinel_y={ports_sentinel_y}")

        for i, row in enumerate(ROWS):
            y_top = row_tops_ext[ext_index(i)]

            if row[0][0] == "certificate_date" and y_top is not None:
                cert_board_idx = next(
                    (j for j, r in enumerate(ROWS) if r[0][0] == "certificate_carried_on_board"), None
                )
                if cert_board_idx is not None:
                    cert_board_y = row_tops_ext[ext_index(cert_board_idx)]
                    if cert_board_y is not None and (y_top - cert_board_y) > CERT_DATE_MAX_DISTANCE:
                        print(f"      ⚠️  certificate_date rejete : ecart {y_top - cert_board_y:.0f}px "
                              f"> CERT_DATE_MAX_DISTANCE={CERT_DATE_MAX_DISTANCE}")
                        y_top = None

            if y_top is None:
                for field_name, _, _, _ in row:
                    data[field_name] = None
                continue

            next_y_top = max_y
            for j in range(ext_index(i) + 1, len(row_tops_ext)):
                if row_tops_ext[j] is not None:
                    next_y_top = row_tops_ext[j]
                    break
            y_bottom = y_top + (next_y_top - y_top) / 2 if next_y_top != max_y else max_y

            for field_name, _, _, value_side in row:
                if value_side == "left":
                    value = extract_value_in_band(detections, y_top, y_bottom, left_x0, left_x1)
                elif field_name in WIDE_RIGHT_FIELDS:
                    narrow_y_bottom = min(y_bottom, y_top + WIDE_RIGHT_Y_MARGIN)
                    value = extract_value_in_band(detections, y_top, narrow_y_bottom, left_x1, page_width * 1.05)
                else:
                    value = extract_value_in_band(detections, y_top, y_bottom, right_x0, page_width * 1.05)

                full_labels = FULL_LABELS.get(field_name)
                if not value:
                    if full_labels:
                        fallback = extract_inline_fallback(detections, y_top, y_bottom, full_labels)
                        if fallback:
                            value = fallback
                elif full_labels:
                    value = clean_value_against_label(value, full_labels)

                if field_name == "certificate_issued_at":
                    value = strip_trailing_valid_till(value)

                if field_name in STRIKETHROUGH_FIELDS:
                    value = _resolve_strikethrough_yes_no(detections, y_top, y_bottom, page_image, value)

                data[field_name] = self._postprocess(field_name, value)

        if data.get("valid_till") is None:
            fallback = extract_valid_till_fallback(detections)
            if fallback:
                data["valid_till"] = fallback

        return data

    @staticmethod
    def _postprocess(field_name: str, value: str):
        value = (value or "").strip()

        if field_name in ("gross_tonnage", "net_tonnage", "crew_members", "passengers"):
            if not value:
                return None
            if re.fullmatch(r"nil", value, re.IGNORECASE):
                return value.upper()
            digits = re.sub(r"[^\d]", "", value)
            return int(digits) if digits else None

        if field_name == "imo_number":
            digits = re.sub(r"[^\d]", "", value)
            return digits if digits else None

        return value


def extract_fields(ocr_results: list, page_width: float = None, page_height: float = None,
                    page_image=None, column_fractions: dict = None, **kwargs) -> dict:
    return FieldExtractor(page_width=page_width, column_fractions=column_fractions).extract(
        ocr_results=ocr_results, page_image=page_image
    )