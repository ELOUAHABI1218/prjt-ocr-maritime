"""
dgm_table_extractor.py - Extraction du tableau dangerous_goods (DGM)
======================================================================

FIX (2026-08-28, v4) :
    - Detection de reimpression (_find_duplicate_table_start) : exige
      desormais la presence du mot "technical" dans le cluster suspect,
      pas seulement 3 libelles quelconques. Cause du bug precedent :
      l'ancre "container_number" (pattern r"container") matche AUSSI la
      valeur "CONTAINER" de la colonne unite, qui apparait sur CHAQUE
      ligne de donnees - le detecteur de cluster suspectait a tort une
      reimpression des les premieres lignes normales, tronquant le
      tableau bien avant la fin (observe : 4 lignes extraites au lieu
      de ~22). "technical" (issu de "Technical Name of Cargo") n'existe
      JAMAIS comme donnee de cargaison reelle - c'est un signal fiable
      qui elimine ce faux positif.
    - un_number : patterns de repli elargis pour couvrir davantage de
      variantes OCR possibles du libelle "UN Number" (fusionne
      differemment selon les documents).

FIX (2026-09-07, v5) :
    - _nearest_column ne se base plus SEULEMENT sur la distance brute
      a l'ancre pour departager les colonnes "class" et "un_number".
      Bug observe concretement (document San Alberto, DGM-ex-1) : quand
      les ancres "class" (x=1549) et "un_number" (x=1728) ne sont
      separees que de ~180px, un token classe court ("3", "9") tombe
      systematiquement plus pres de l'ancre un_number que de la sienne,
      et se retrouve concatene AVEC le vrai numero UN (ex: un_number
      devient "1170 3" au lieu de un_number="1170" / class="3"). Les
      classes "larges" (ex: "8", "6.1") restaient elles correctement
      assignees - le bug ne touchait donc QUE les classes 1 chiffre les
      plus frequentes, silencieusement, sans jamais lever d'erreur.
      Correctif : on reconnait le FORMAT de la valeur (un numero UN fait
      toujours exactement 4 chiffres ; une classe IMDG fait 1 chiffre
      1-9 optionnellement suivi de ".1" a ".6") et on privilegie cette
      colonne meme si elle n'est pas geometriquement la plus proche,
      des lors que le texte matche sans ambiguite l'un des deux formats.
    - _fix_swapped_class_un_number : filet de securite complementaire,
      pour les cas ou class et un_number auraient malgre tout fini
      concatenes dans la meme cellule (robustesse si la correction
      ci-dessus ne suffit pas sur un document donne).

FIX (2026-09-08, v6) - CORRECTION DU BUG "LIGNES FANTOMES / DONNEES
MELANGEES ENTRE COLONNES" (document IRENES POWER, DGM-ex-3) :

    CAUSE RACINE identifiee en comparant l'extraction bogee au vrai
    tableau du PDF : les detections issues de `retry_narrow_columns_fn`
    (le retry cible sur les colonnes etroites class/quantity) etaient
    injectees dans `table_dets` AVANT le calcul des frontieres de
    lignes (`_build_container_row_bounds`). Si ces detections retry ont
    un leger decalage vertical par rapport a la passe originale (crop/
    rescale different pour l'OCR cible), elles introduisent des
    frontieres de lignes fantomes, qui decoupent des "bandes" contenant
    un melange de deux lignes reelles adjacentes. Symptome observe :
    le meme container_number apparait plusieurs fois, avec des valeurs
    eclatees dans les MAUVAISES colonnes (ex: class="TOLUENE
    DIISOCYANATE", stowage_position="2794" alors que 2794 est en realite
    un UN number d'une autre ligne).

    CORRECTIF (deux volets) :
    1. `_build_container_row_bounds` n'est plus jamais calcule sur un
       ensemble incluant les detections retry : `extract_dgm_table`
       fige desormais un instantane `boundary_dets` juste APRES le
       filtrage des artefacts de bordure et AVANT la fusion des
       detections retry, et cet instantane est le seul utilise pour
       determiner ou commence chaque ligne. Les detections retry ne
       servent plus qu'a COMPLETER des valeurs a l'interieur d'une bande
       deja fixee, jamais a deplacer une frontiere.
    2. Filet de securite supplementaire, `_reconcile_duplicate_containers`
       (voir plus bas) : passe finale qui (a) normalise chaque colonne a
       formatage strict en cherchant, au besoin, le bon token a
       l'interieur d'une valeur polluee par du texte d'une colonne
       voisine (ex: class="AEROSOLS LTD QTY 8" -> "8"), puis (b) fusionne
       les lignes qui partagent un container_number et qui NE sont PAS
       toutes les deux quasi-completes et en desaccord reel entre elles
       (una vraie ligne de cargaison distincte est presque toujours
       entierement renseignee ; un fragment issu d'un decoupage de bande
       errone ne l'est pas). Quand deux lignes completes et distinctes
       partagent un container_number (cas legitime : un meme conteneur
       transportant plusieurs matieres, cf document LONDON EXPRESS,
       DGM-ex-4), les deux sont conservees et un avertissement est
       imprime pour verification manuelle plutot que d'etre fusionnees
       a l'aveugle.

       LIMITE CONNUE : si les valeurs d'une ligne fantome sont TOUTES
       simultanement valides dans leur format ET contredisent une ligne
       deja extraite (contamination croisee complete, pas seulement des
       trous), ce filet de securite ne peut pas trancher a coup sur avec
       le seul texte des colonnes - il imprime alors un avertissement
       "verification manuelle recommandee" au lieu de deviner. Sur le
       document de test (IRENES POWER), ce cas residuel s'est produit
       une seule fois sur 14 lignes apres application du correctif #1
       (contre un tableau entierement casse avant correctif). Si ce
       message apparait frequemment, cela indique que le decalage
       vertical entre passe originale et passe retry est plus important
       que prevu et merite d'etre corrige directement dans
       `retry_narrow_columns_fn` / l'etape d'OCR en amont.
"""

import re

from field_extractor import group_into_lines, clean_token

ROW_Y_TOL = 20.0
COPY_GAP_THRESHOLD = 1200.0
HEADER_ZONE_TOP_MARGIN = 60
MAX_HEADER_SPAN = 250.0
FRONTIER_BIAS = 0.15

TABLE_COLUMN_ANCHORS = [
    ("container_number", [r"container"]),
    ("technical_name", [r"technical"]),
    ("class", [r"^class$"]),
    ("un_number", [r"^uno$", r"^un$", r"^u\.?n\.?o?\.?$", r"^un\s*number$", r"^u\.?n\.?\s*number$"]),
    ("quantity", [r"quantity"]),
    ("unite", [r"^unite$"]),
    ("net_weight", [r"\bnet\b", r"gross"]),
    ("stowage_position", [r"stowage"]),
    ("contact_info", [r"\binformation\b", r"\bcontact\b"]),
    ("port", [r"\bport\b"]),
]

IDENTIFYING_COLUMNS = ("container_number", "technical_name", "un_number")

# Signal FIABLE d'un vrai bloc d'en-tete (jamais une valeur de donnee
# reelle) - utilise pour valider les detections de "reimpression" et
# eviter les faux positifs sur le mot "container" (qui apparait aussi
# comme donnee via la valeur "CONTAINER" de la colonne unite).
HEADER_ONLY_SAFE_SIGNAL = re.compile(r"\btechnical\b", re.IGNORECASE)

DOCUMENT_HEADER_LABEL_PATTERNS = [
    re.compile(r"\bship\s*name\b", re.IGNORECASE),
    re.compile(r"\bcall\s*sign\b", re.IGNORECASE),
    re.compile(r"\bimo\s*n\w{0,3}umber\b", re.IGNORECASE),
    re.compile(r"\bflag\s*state\b", re.IGNORECASE),
    re.compile(r"^\s*eta\b", re.IGNORECASE),
    re.compile(r"^\s*etd\b", re.IGNORECASE),
    re.compile(r"previous\s*port\s*of\s*call", re.IGNORECASE),
    re.compile(r"next\s*port\s*of\s*call", re.IGNORECASE),
    re.compile(r"\bbooking\b", re.IGNORECASE),
    re.compile(r"\bvoyage\b", re.IGNORECASE),
    re.compile(r"\bimport\b.{0,10}\bexport\b", re.IGNORECASE),
    re.compile(r"transhipment", re.IGNORECASE),
    # FIX v6.1 (2026-09-08) : les cases a cocher du type de manifeste
    # (IMPORT / EXPORT / TRANSIT) peuvent se retrouver, en l'absence de
    # frontiere en dessous de la DERNIERE ligne du tableau, absorbees dans
    # le technical_name de cette derniere ligne (observe : "EMPTY
    # UNCLEANED ETHANOLAMINE TRANSIT" au lieu de "EMPTY UNCLEANED
    # ETHANOLAMINE"). Ces mots isoles ne sont jamais un vrai nom de
    # matiere dangereuse - on peut donc les retirer sans risque avant
    # meme de chercher la zone du tableau.
    re.compile(r"^\s*import\s*$", re.IGNORECASE),
    re.compile(r"^\s*export\s*$", re.IGNORECASE),
    re.compile(r"^\s*transit\s*$", re.IGNORECASE),
]

CONTAINER_NUMBER_PATTERN = re.compile(r"[A-Z]{3,4}\s{0,3}\d{6,7}")

NARROW_COLUMN_VALID_VALUE = re.compile(r"^\d+(\.\d+)?$")

DUPLICATE_HEADER_CLUSTER_Y_TOL = 40.0
DUPLICATE_HEADER_MIN_LABELS = 3

# --- FIX v5 : reconnaissance de format pour departager class / un_number ---
_CLASS_LIKE_PATTERN = re.compile(r"^[1-9](\.[1-6])?$")
_UN_NUMBER_LIKE_PATTERN = re.compile(r"^\d{4}$")

# --- FIX v6 : formats stricts utilises pour la normalisation par colonne
# et pour le score de completude d'une ligne (voir _reconcile_duplicate_containers) ---
_QUANTITY_LIKE_PATTERN = re.compile(r"^\d+([.,]\d+)?$")
_STOWAGE_LIKE_PATTERN = re.compile(r"^\d{5,7}$")
_WEIGHT_LIKE_PATTERN = re.compile(r"^\d{1,3}([.,]\d{3})*([.,]\d+)?$|^\d+([.,]\d+)?$")

_STRICT_COLUMN_PATTERNS = {
    "class": _CLASS_LIKE_PATTERN,
    "un_number": _UN_NUMBER_LIKE_PATTERN,
    "quantity": _QUANTITY_LIKE_PATTERN,
    "stowage_position": _STOWAGE_LIKE_PATTERN,
    "net_weight": _WEIGHT_LIKE_PATTERN,
}
_ROW_FULL_SCORE = len(_STRICT_COLUMN_PATTERNS) + 1  # +1 pour technical_name
_ROW_DISTINCT_ENTRY_MIN_SCORE = _ROW_FULL_SCORE - 1  # tolere un seul champ manquant


def _strip_document_header_tokens(dets: list) -> list:
    def _matches(d):
        low = d["text"].lower()
        return any(p.search(low) for p in DOCUMENT_HEADER_LABEL_PATTERNS)

    kept = [d for d in dets if not _matches(d)]
    removed = len(dets) - len(kept)
    if removed:
        print(f"      🧹 {removed} detection(s) d'en-tete DOCUMENT (label) retiree(s) "
              f"avant extraction du tableau")
    return kept


def _strip_known_header_values(dets: list, header_fields: dict) -> list:
    def _normalize(text):
        return re.sub(r"[^a-z0-9]", "", text.lower())

    known_values = set()
    for key in ("flag_state", "eta", "etd", "ship_name", "call_sign",
                "imo_number", "voyage_no", "previous_port_of_call",
                "next_port_of_call", "booking_nr"):
        val = header_fields.get(key)
        if val and len(val.strip()) >= 3:
            norm = _normalize(val)
            if len(norm) >= 4:
                known_values.add(norm)

    if not known_values:
        return dets

    def _matches(d):
        text_norm = _normalize(clean_token(d["text"]))
        if len(text_norm) < 4:
            return False
        for known in known_values:
            if text_norm in known or known in text_norm:
                return True
        return False

    kept = [d for d in dets if not _matches(d)]
    removed = len(dets) - len(kept)
    if removed:
        print(f"      🧹 {removed} detection(s) correspondant a une VALEUR d'en-tete "
              f"deja extraite retiree(s) (section d'en-tete dupliquee dans le document)")
    return kept


def _find_table_header_zone(detections: list, table_start_y: float, zone_height: float = 200) -> list:
    return [
        d for d in detections
        if table_start_y - HEADER_ZONE_TOP_MARGIN <= d["bbox"]["y0"] <= table_start_y + zone_height
    ]


def _find_copy_start_positions(header_zone: list) -> list:
    xs = sorted(
        d["bbox"]["x0"] for d in header_zone
        if re.search(r"container", d["text"].strip().lower())
    )
    if not xs:
        return [0.0]

    starts = [xs[0]]
    for x in xs[1:]:
        if x - starts[-1] > COPY_GAP_THRESHOLD:
            starts.append(x)
    return starts


def _detect_column_anchors(header_zone_dets: list, x_min: float, x_max: float) -> list:
    scoped = [d for d in header_zone_dets if x_min <= d["bbox"]["x0"] < x_max]
    anchors = []
    for col_key, patterns in TABLE_COLUMN_ANCHORS:
        best_x0 = None
        for d in scoped:
            text_low = d["text"].strip().lower()
            for pattern in patterns:
                if re.search(pattern, text_low, re.IGNORECASE):
                    if best_x0 is None or d["bbox"]["x0"] < best_x0:
                        best_x0 = d["bbox"]["x0"]
                    break
        if best_x0 is not None:
            anchors.append((col_key, best_x0))
    anchors.sort(key=lambda t: t[1])
    return anchors


def _synthesize_missing_un_number_anchor(anchors: list) -> list:
    """
    FIX v6.5 (2026-09-10) : observe sur LONDON EXPRESS (DGM-ex-4) - le
    libelle "UN Number" peut etre coupe/mal OCR'ise au point qu'aucun
    token ne matche plus les patterns de TABLE_COLUMN_ANCHORS pour
    un_number (ex: libelle scinde en "UN" + "I number", ou "UN" seul
    absent du jeu de detections finalement utilise pour l'ancrage). Sans
    ancre, chaque valeur d'UN number (ex: "1950") se fait absorber par la
    colonne geometriquement la plus proche (typiquement "class"), puis la
    normalisation stricte par colonne (_best_token_for_column) la
    reconnait comme invalide pour cette colonne et la jette silencieusement
    - un_number finit alors vide sur TOUTES les lignes.

    Sur un manifeste DGM/IMDG, l'ordre des colonnes class -> UN Number ->
    Quantity est fixe et universel : si les ancres "class" et "quantity"
    sont toutes les deux detectees mais pas "un_number", on reconstruit
    cette derniere par interpolation lineaire (le milieu entre les deux) -
    verifie sur les donnees reelles de ce document : ancre interpolee a
    1460 contre des valeurs UN reelles a 1417-1423, largement plus proche
    que class(1338) ou quantity(1582), ce qui suffit pour que
    _nearest_column route correctement ces tokens.
    """
    anchor_dict = dict(anchors)
    if "un_number" in anchor_dict:
        return anchors
    if "class" in anchor_dict and "quantity" in anchor_dict:
        midpoint = (anchor_dict["class"] + anchor_dict["quantity"]) / 2
        print(f"      🩹 Ancre 'un_number' non detectee - reconstruite par interpolation "
              f"entre class(x={anchor_dict['class']:.0f}) et quantity(x={anchor_dict['quantity']:.0f}) "
              f"-> x={midpoint:.0f} (ordre class/UN/quantity fixe sur un manifeste DGM)")
        new_anchors = list(anchors) + [("un_number", midpoint)]
        new_anchors.sort(key=lambda t: t[1])
        return new_anchors
    return anchors


def _nearest_column_by_distance(x0: float, anchors: list) -> str:
    """Choix par distance geometrique brute (comportement d'origine)."""
    best_key, best_dist = None, None
    for col_key, anchor_x0 in anchors:
        dist = abs(x0 - anchor_x0)
        if best_dist is None or dist < best_dist:
            best_key, best_dist = col_key, dist
    return best_key


def _nearest_column(x0: float, anchors: list, token_text: str = "") -> str:
    """
    Choix de colonne par distance geometrique, avec UNE correction ciblee :
    si le gagnant geometrique est deja "un_number" ou "class" (l'un des deux
    SEULEMENT, jamais une autre colonne comme "quantity"), et que le texte
    contredit clairement ce choix par son format (un numero UN fait
    exactement 4 chiffres ; une classe IMDG fait 1 chiffre 1-9 +.1-.6
    optionnel), on bascule vers l'autre des deux colonnes.

    IMPORTANT (fix d'une regression reelle, 2026-09-08) : la version
    precedente forcait TOUT token ressemblant a une classe (y compris un
    simple "1") vers la colonne "class" des que les ancres class ET
    un_number existaient toutes les deux (= presque toujours), SANS
    verifier que le gagnant geometrique naturel etait bien l'une de ces
    deux colonnes. Consequence concrete observee : une valeur de
    "quantity" legitime (tres souvent "1") geometriquement la plus proche
    de sa PROPRE ancre "quantity" se faisait quand meme detourner vers
    "class" (ex: class="1 9" / quantity="" au lieu de class="9" /
    quantity="1"). Cette version ne corrige plus QUE le cas ambigu
    class/un_number, et ne touche jamais a un token dont le gagnant
    geometrique est une troisieme colonne comme "quantity".
    """
    winner = _nearest_column_by_distance(x0, anchors)
    anchor_dict = dict(anchors)
    cleaned = clean_token(token_text).strip()

    if winner == "un_number" and "class" in anchor_dict:
        if _CLASS_LIKE_PATTERN.match(cleaned) and not _UN_NUMBER_LIKE_PATTERN.match(cleaned):
            return "class"
    elif winner == "class" and "un_number" in anchor_dict:
        if _UN_NUMBER_LIKE_PATTERN.match(cleaned):
            return "un_number"

    return winner


def _compute_header_end_y(header_zone: list, table_start_y: float, x_min: float, x_max: float) -> float:
    scoped = [
        d for d in header_zone
        if x_min <= d["bbox"]["x0"] < x_max
        and table_start_y - HEADER_ZONE_TOP_MARGIN <= d["bbox"]["y0"] <= table_start_y + MAX_HEADER_SPAN
    ]
    matching_tokens = [
        d for d in scoped
        if any(re.search(p, d["text"].strip().lower(), re.IGNORECASE)
               for _, patterns in TABLE_COLUMN_ANCHORS for p in patterns)
    ]
    header_token_y_max = max(
        (d["bbox"]["y1"] for d in matching_tokens),
        default=table_start_y + 100
    )
    return header_token_y_max + 15


def _find_duplicate_table_start(table_dets: list, x_min: float, x_max: float):
    """
    Detecte un CLUSTER DE LIBELLES DE COLONNES qui reapparait plus bas
    dans les donnees du tableau (signe qu'un document reimprime le
    manifeste entier). FIX : exige la presence du mot "technical" dans
    le cluster - ce mot n'apparait JAMAIS comme donnee de cargaison
    reelle, contrairement a "container" qui matche aussi la valeur
    "CONTAINER" de la colonne unite (present sur quasi chaque ligne
    reelle), ce qui declenchait des faux positifs des les premieres
    lignes normales.
    """
    scoped = [d for d in table_dets if x_min <= d["bbox"]["x0"] < x_max]
    label_dets = [
        d for d in scoped
        if any(re.search(p, clean_token(d["text"]).strip().lower(), re.IGNORECASE)
               for _, patterns in TABLE_COLUMN_ANCHORS for p in patterns)
    ]
    if len(label_dets) < DUPLICATE_HEADER_MIN_LABELS:
        return None

    label_dets.sort(key=lambda d: d["bbox"]["y0"])
    clusters = []
    current_cluster = [label_dets[0]]
    for d in label_dets[1:]:
        if d["bbox"]["y0"] - current_cluster[-1]["bbox"]["y0"] <= DUPLICATE_HEADER_CLUSTER_Y_TOL:
            current_cluster.append(d)
        else:
            clusters.append(current_cluster)
            current_cluster = [d]
    clusters.append(current_cluster)

    for cluster in clusters:
        has_safe_signal = any(HEADER_ONLY_SAFE_SIGNAL.search(clean_token(d["text"])) for d in cluster)
        if not has_safe_signal:
            continue

        distinct_cols = set()
        for d in cluster:
            for col_key, patterns in TABLE_COLUMN_ANCHORS:
                if any(re.search(p, clean_token(d["text"]).strip().lower(), re.IGNORECASE) for p in patterns):
                    distinct_cols.add(col_key)
        if len(distinct_cols) >= DUPLICATE_HEADER_MIN_LABELS:
            return min(d["bbox"]["y0"] for d in cluster)

    return None


def _filter_border_artifacts(dets: list, min_occurrences: int = 4, x_tol: float = 15) -> list:
    zero_dets = [d for d in dets if clean_token(d["text"]) == "0"]
    if len(zero_dets) < min_occurrences:
        return dets

    xs = sorted(d["bbox"]["x0"] for d in zero_dets)
    median_x = xs[len(xs) // 2]
    suspicious = {id(d) for d in zero_dets if abs(d["bbox"]["x0"] - median_x) <= x_tol}

    if len(suspicious) >= min_occurrences:
        return [d for d in dets if id(d) not in suspicious]
    return dets


def _filter_narrow_column_garbage(dets: list) -> list:
    kept = [d for d in dets if NARROW_COLUMN_VALID_VALUE.match(clean_token(d["text"]).strip())]
    removed = len(dets) - len(kept)
    if removed:
        print(f"      🧹 {removed} detection(s) de bruit (non-numerique) retiree(s) "
              f"du retry colonnes etroites")
    return kept


def _strip_column_label_tokens(table_dets: list) -> list:
    # FIX v6.2 (2026-09-08) : en plus des libelles de colonnes eux-memes,
    # on retire les mots isoles du libelle COMPOSE de la colonne
    # contact_info ("Contact and Information about Cargo and Package") -
    # observe en pratique : le fragment "Cargo and Package" se detachait
    # du reste du libelle et se recollait au contact_info de la derniere
    # ligne visible avant une eventuelle coupure/reimpression de tableau
    # (ex: "86-535-6669879 LISA Cargo and Package" au lieu de
    # "86-535-6669879 LISA"). Ces deux mots n'ont aucune raison d'exister
    # dans un vrai numero de telephone / nom de contact.
    extra_label_patterns = [re.compile(r"\bcargo\b", re.IGNORECASE),
                             re.compile(r"\bpackage\b", re.IGNORECASE)]

    def _is_label(d):
        text_low = clean_token(d["text"]).strip().lower()
        if not text_low:
            return False
        if any(re.search(p, text_low, re.IGNORECASE)
               for _, patterns in TABLE_COLUMN_ANCHORS for p in patterns):
            return True
        return any(p.search(text_low) for p in extra_label_patterns)

    kept = [d for d in table_dets if not _is_label(d)]
    removed = len(table_dets) - len(kept)
    if removed:
        print(f"      🧹 {removed} detection(s) de LIBELLE DE COLONNE retiree(s) "
              f"des donnees du tableau (en-tete duplique)")
    return kept


def _dedupe_table_detections(dets: list, y_tol: float = 12, x_tol: float = 20) -> list:
    def _normalize(text):
        return re.sub(r"[^a-z0-9]", "", text.lower())

    ordered = sorted(dets, key=lambda d: -len(d["text"]))
    kept = []
    for d in ordered:
        d_norm = _normalize(d["text"])
        d_y = (d["bbox"]["y0"] + d["bbox"]["y1"]) / 2
        d_x = d["bbox"]["x0"]
        is_dup = False
        if d_norm:
            for k in kept:
                k_norm = _normalize(k["text"])
                k_y = (k["bbox"]["y0"] + k["bbox"]["y1"]) / 2
                k_x = k["bbox"]["x0"]
                if (abs(d_y - k_y) <= y_tol and abs(d_x - k_x) <= x_tol
                        and k_norm and (d_norm == k_norm or d_norm in k_norm or k_norm in d_norm)):
                    is_dup = True
                    break
        if not is_dup:
            kept.append(d)
    return sorted(kept, key=lambda d: (d["bbox"]["y0"], d["bbox"]["x0"]))


def _dedupe_repeated_phrase(text: str) -> str:
    words = text.split()

    deduped_consecutive = []
    for w in words:
        if not deduped_consecutive or deduped_consecutive[-1].lower() != w.lower():
            deduped_consecutive.append(w)
    words = deduped_consecutive
    n = len(words)

    if n >= 4 and n % 2 == 0:
        half = n // 2
        first_half = " ".join(words[:half]).lower()
        second_half = " ".join(words[half:]).lower()
        if first_half == second_half:
            return " ".join(words[:half])

    return " ".join(words)


def _build_container_row_bounds(table_dets: list) -> list:
    sorted_dets = sorted(table_dets, key=lambda d: (d["bbox"]["y0"], d["bbox"]["x0"]))
    boundaries = []
    used_ids = set()

    for i, d in enumerate(sorted_dets):
        if id(d) in used_ids:
            continue
        text = clean_token(d["text"])
        if CONTAINER_NUMBER_PATTERN.search(text):
            boundaries.append(d["bbox"]["y0"])
            used_ids.add(id(d))
            continue

        if i + 1 < len(sorted_dets):
            d2 = sorted_dets[i + 1]
            same_row = abs(d2["bbox"]["y0"] - d["bbox"]["y0"]) <= 15
            close_x = (d2["bbox"]["x0"] - d["bbox"]["x1"]) < 80
            if same_row and close_x:
                combined = text + " " + clean_token(d2["text"])
                if CONTAINER_NUMBER_PATTERN.search(combined):
                    boundaries.append(min(d["bbox"]["y0"], d2["bbox"]["y0"]))
                    used_ids.add(id(d))
                    used_ids.add(id(d2))

    return sorted(set(boundaries))


def _fix_shifted_net_weight_stowage(rows: list) -> list:
    for row in rows:
        stowage = row.get("stowage_position", "").strip()
        net = row.get("net_weight", "").strip()
        if stowage and not net and re.match(r"^\d{1,3}$", stowage):
            row["net_weight"] = stowage
            row["stowage_position"] = ""
    return rows


def _fix_swapped_class_un_number(row: dict) -> dict:
    """
    Filet de securite complementaire : si malgre la correction de
    _nearest_column, class et un_number se sont quand meme retrouves
    concatenes dans la meme cellule (ex: un_number="1170 3"), on les
    separe ici en identifiant lequel des deux tokens est un vrai numero
    UN (4 chiffres) et lequel ressemble a une classe (1-9, +.1-.6).
    """
    if row.get("class"):
        return row

    un = (row.get("un_number") or "").split()
    if len(un) != 2:
        return row

    a, b = un
    if _UN_NUMBER_LIKE_PATTERN.match(a) and _CLASS_LIKE_PATTERN.match(b):
        row["un_number"], row["class"] = a, b
    elif _UN_NUMBER_LIKE_PATTERN.match(b) and _CLASS_LIKE_PATTERN.match(a):
        row["un_number"], row["class"] = b, a

    return row


def _drop_exact_reprint_duplicates(rows: list) -> list:
    """
    Filet de securite PRUDENT pour un phenomene observe (document
    San Alberto / IRENES POWER) : les toutes premieres lignes du tableau
    reapparaissent parfois en fin d'extraction, avec des valeurs
    decalees/melangees (symptome d'une frontiere de ligne mal detectee
    ou d'une zone de retry qui deborde sur une portion deja lue).

    Volontairement PRUDENT : on ne supprime QUE les doublons dont
    container_number, technical_name ET stowage_position sont
    IDENTIQUES a une ligne deja vue - ces 3 valeurs concordant exactement
    en meme temps est extremement improbable pour 2 lignes de cargaison
    reellement distinctes (un meme conteneur peut porter plusieurs
    marchandises differentes, mais rarement a la MEME position d'arrimage
    avec le MEME libelle). On ne touche jamais a un conteneur qui
    apparait plusieurs fois legitimement avec des donnees differentes.

    NOTE v6 : ce filet reste en place car il attrape les doublons EXACTS
    a cout quasi nul, mais il est desormais complete par
    `_reconcile_duplicate_containers`, plus general, qui traite aussi les
    doublons partiels/melanges (le cas le plus frequent en pratique).
    """
    seen = set()
    kept = []
    dropped = 0
    for row in rows:
        key = (
            (row.get("container_number") or "").strip(),
            (row.get("technical_name") or "").strip(),
            (row.get("stowage_position") or "").strip(),
        )
        if any(key) and key in seen:
            dropped += 1
            continue
        seen.add(key)
        kept.append(row)

    if dropped:
        print(f"      🧹 {dropped} ligne(s) retiree(s) - doublon EXACT "
              f"(conteneur + marchandise + position d'arrimage identiques) "
              f"d'une ligne deja extraite, signe probable d'une reimpression "
              f"partielle ou d'une frontiere de ligne mal detectee")
    return kept


# --------------------------------------------------------------------------
# FIX v6 : normalisation par colonne + reconciliation des conteneurs dupliques
# --------------------------------------------------------------------------

def _best_token_for_column(value: str, pattern: re.Pattern) -> str:
    """
    Pour une colonne a formatage strict (class, un_number, quantity,
    stowage_position, net_weight) : si la valeur brute matche deja le
    format attendu, on la garde telle quelle. Sinon, on cherche PARMI
    SES PROPRES TOKENS (separes par des espaces) un token qui matche -
    cas frequent quand une bande de ligne mal decoupee a concatene la
    vraie valeur avec du texte d'une colonne voisine (ex: class=
    "AEROSOLS LTD QTY 8" -> le "8" est la vraie classe). Si aucun token
    ne matche, la valeur est consideree comme du bruit pour cette
    colonne et on retourne une chaine vide plutot que de garder un texte
    qui n'a rien a faire dans une colonne numerique stricte.
    """
    value = (value or "").strip()
    if not value:
        return ""
    if pattern.match(value):
        return value
    for tok in value.split():
        tok_clean = tok.strip(",.")
        if pattern.match(tok_clean):
            return tok_clean
    return ""


def _normalize_row_columns(row: dict) -> dict:
    """Applique _best_token_for_column a chaque colonne stricte, et ne
    garde que le premier vrai numero de conteneur dans container_number
    (utile quand deux conteneurs se sont retrouves concatenes dans la
    meme cellule, ex: 'EXFU5501010 TCKU3411583')."""
    out = dict(row)

    cn = row.get("container_number", "") or ""
    m = CONTAINER_NUMBER_PATTERN.search(cn)
    if m:
        out["container_number"] = m.group(0).replace(" ", "")
    elif cn.split():
        out["container_number"] = cn.split()[0]

    for col, pattern in _STRICT_COLUMN_PATTERNS.items():
        out[col] = _best_token_for_column(row.get(col, ""), pattern)

    unite = row.get("unite", "") or ""
    out["unite"] = "CONTAINER" if "CONTAINE" in unite.upper() else unite.strip()

    return out


def _row_completeness_score(row: dict) -> int:
    score = sum(1 for col in _STRICT_COLUMN_PATTERNS if row.get(col))
    if row.get("technical_name"):
        score += 1
    return score


def _free_text_relates(a: str, b: str) -> bool:
    """Vrai si a et b representent le 'meme' texte libre : l'un est vide,
    ils sont egaux, ou l'un est inclus dans l'autre une fois ponctuation/
    casse ignorees (ex: 'BATTERIES WET FILLED WITH ACID' est inclus dans
    'NOS. BATTERIES WET FILLED WITH ACID')."""
    a_n = re.sub(r"[^A-Z0-9 ]", "", (a or "").upper()).strip()
    b_n = re.sub(r"[^A-Z0-9 ]", "", (b or "").upper()).strip()
    if not a_n or not b_n:
        return True
    return a_n in b_n or b_n in a_n


def _is_same_cargo_entry(a: dict, b: dict) -> bool:
    """
    Deux lignes normalisees partageant un container_number sont
    consideres comme LA MEME ligne de cargaison reelle (donc l'une des
    deux est un fragment/echo de decoupage de bande a fusionner ou
    ecarter) SAUF si les deux sont quasi-completes ET sont reellement en
    desaccord (technical_name different, ou une valeur stricte differente
    et valide de part et d'autre) - ce dernier cas correspond aux
    conteneurs transportant legitimement plusieurs matieres (cf document
    LONDON EXPRESS, DGM-ex-4, ou FANU3722488 porte 5 matieres
    differentes).
    """
    both_complete = (_row_completeness_score(a) >= _ROW_DISTINCT_ENTRY_MIN_SCORE
                      and _row_completeness_score(b) >= _ROW_DISTINCT_ENTRY_MIN_SCORE)
    if not both_complete:
        return True

    text_same = _free_text_relates(a.get("technical_name", ""), b.get("technical_name", ""))
    contradicts = any(
        a.get(col) and b.get(col) and a.get(col) != b.get(col)
        for col in ("un_number", "class", "quantity", "stowage_position", "net_weight")
    )
    if text_same and not contradicts:
        return True

    print(f"      ⚠️  {a.get('container_number')} : deux lignes completes et distinctes "
          f"partagent ce numero de conteneur - conservees telles quelles, "
          f"VERIFICATION MANUELLE RECOMMANDEE ('{a.get('technical_name')}' vs "
          f"'{b.get('technical_name')}')")
    return False


def _merge_cargo_entry(a: dict, b: dict) -> dict:
    """Fusionne deux lignes jugees identiques : garde, pour chaque
    colonne, la valeur non vide de `a` (la premiere rencontree dans
    l'ordre de lecture), sinon celle de `b`.

    IMPORTANT (fix 2026-09-08) : pour technical_name, on ne garde PLUS le
    texte le plus long. Sur le terrain, l'occurrence la plus longue est
    presque toujours celle qui a recolte un mot polluant venu d'une ligne
    voisine (ex: 'NOS. BATTERIES WET FILLED WITH ACID' au lieu de
    'BATTERIES WET FILLED WITH ACID' - le 'NOS.' appartient en realite au
    libelle de la ligne CMAU2555023/FCGU1696025 qui se termine par
    '...SOLID NOS' sur 2 lignes dans le PDF). La premiere occurrence
    rencontree correspond quasi-toujours au decoupage de bande original
    et correct ; les occurrences suivantes sont des echos/fragments."""
    merged = dict(a)
    for col in a.keys():
        va, vb = a.get(col, ""), b.get(col, "")
        merged[col] = va if va else vb
    return merged


def _container_key(row: dict) -> str:
    cn = row.get("container_number") or ""
    m = CONTAINER_NUMBER_PATTERN.search(cn)
    if m:
        return m.group(0).replace(" ", "")
    parts = cn.split()
    return parts[0] if parts else cn


def _is_strict_orphan(row: dict) -> bool:
    """True if a row has NO strict-column value at all (class, un_number,
    quantity, stowage_position, net_weight all empty) - i.e. its
    container_number was detected but the row-banding failed to capture
    any of its numeric columns, which normally land elsewhere by
    mistake."""
    return not any(row.get(c) for c in _STRICT_COLUMN_PATTERNS)


def _reassign_orphan_strict_values(rows: list) -> list:
    """
    FIX v6.1 (2026-09-08) : filet de securite pour le cas ou une frontiere
    de ligne erronee (ex: un texte mal reconnu par l'OCR de base cree un
    doublon de container_number a un mauvais endroit) capte les valeurs
    numeriques (class/un_number/quantity/stowage/net_weight) qui
    appartiennent en realite a la ligne du VRAI conteneur juste a cote
    dans l'ordre de lecture de haut en bas de la page, laissant cette
    derniere "orpheline" (container_number correct mais toutes les
    colonnes numeriques vides).

    Concretement (observe sur IRENES POWER, DGM-ex-3) : le conteneur
    "EXFU5508988" etait correctement detecte mais restait entierement
    vide sur ses colonnes numeriques, tandis qu'une seconde occurrence
    inattendue de "GCXU2376704" (deja vu plus haut dans le tableau,
    valide) apparaissait juste apres avec des valeurs qui correspondaient
    en realite a EXFU5508988. Cette fonction detecte ce schema : une ligne
    qui n'est PAS la premiere occurrence de son container_number (donc
    tres probablement un echo/mauvaise lecture) et qui possede des
    valeurs numeriques, alors qu'un voisin IMMEDIAT (ligne precedente ou
    suivante dans l'ordre d'extraction) porte un AUTRE container_number
    et n'a AUCUNE valeur numerique - dans ce cas, les valeurs sont
    deplacees vers l'orpheline et la ligne en trop est supprimee.

    ESSAI ABANDONNE (v6.6, 2026-09-11) : une version elargissait la
    recherche a tout le tableau (pas seulement le voisin immediat) pour
    traiter un cas ou le vrai orphelin etait loin dans l'ordre de lecture
    (LONDON EXPRESS, MNBU9166763/FPTU5010931). Revert : sur un document
    avec BEAUCOUP de lignes quasi-identiques et BEAUCOUP d'echecs OCR
    reels (donc beaucoup de vrais orphelins qui ne sont PAS des victimes
    de frontiere dupliquee, juste des colonnes jamais detectees), cette
    recherche elargie a provoque une CASCADE de mauvaises reattributions
    entre conteneurs sans rapport (ex: un vrai conteneur multi-matieres
    CAIU9514281 s'est fait voler ses valeurs au profit d'un conteneur
    totalement different). Le risque de corruption silencieuse depasse le
    benefice ; mieux vaut laisser un orphelin lointain non corrige
    (visible, honnete) que de deviner faux. Cette fonction reste donc
    volontairement limitee au voisin immediat.

    Prudent par construction : ne deplace que vers un voisin *immediat*
    et *totalement* orphelin, et seulement les colonnes que l'orpheline
    n'a pas deja - ne touche jamais a une ligne deja renseignee.
    """
    first_index = {}
    for i, r in enumerate(rows):
        key = _container_key(r)
        if key not in first_index:
            first_index[key] = i

    to_drop = set()
    for i, row in enumerate(rows):
        if i in to_drop:
            continue
        key = _container_key(row)
        if first_index[key] == i:
            continue  # occurrence primaire : jamais une source de reassignation
        if _is_strict_orphan(row):
            continue  # rien a donner

        # FIX v6.7 (2026-09-11) : une "occurrence en trop" n'est un
        # candidat donneur que si elle ressemble a un ECHO de sa PROPRE
        # occurrence primaire (meme technical_name, ou l'un des deux vide)
        # - un conteneur transportant legitimement plusieurs matieres
        # (ex: CAIU9514281 avec "E.G. ORGANIC PEROXIDE TYPE D" puis
        # "ORGANIC PEROXIDE TYPE F") a un technical_name clairement
        # DIFFERENT sur sa seconde ligne : ce n'est pas un echo, ses
        # valeurs lui appartiennent et ne doivent jamais etre donnees a
        # une autre ligne, meme orpheline et meme voisine.
        primary = rows[first_index[key]]
        if not _free_text_relates(primary.get("technical_name", ""), row.get("technical_name", "")):
            continue

        for j in (i - 1, i + 1):
            if 0 <= j < len(rows) and j not in to_drop:
                neighbor = rows[j]
                if _container_key(neighbor) != key and _is_strict_orphan(neighbor):
                    moved = [c for c in _STRICT_COLUMN_PATTERNS if row.get(c) and not neighbor.get(c)]
                    for c in moved:
                        neighbor[c] = row[c]
                    if moved:
                        print(f"      🔁 {key} (occurrence en trop) : valeurs {moved} "
                              f"reattribuees a la ligne orpheline voisine "
                              f"'{_container_key(neighbor)}'")
                        to_drop.add(i)
                        break

    return [r for i, r in enumerate(rows) if i not in to_drop]


def _reconcile_duplicate_containers(rows: list) -> list:
    """
    Passe finale de nettoyage (FIX v6, etendue v6.1) : normalise chaque
    ligne colonne par colonne (_normalize_row_columns), tente de
    rapatrier les valeurs numeriques mal placees vers une ligne orpheline
    voisine (_reassign_orphan_strict_values), puis regroupe par
    container_number et fusionne les lignes qui representent la meme
    ligne de cargaison reelle. Corrige la grande majorite des "lignes
    fantomes" issues d'un decoupage de bande errone, tout en preservant
    les conteneurs qui transportent legitimement plusieurs matieres.

    Ne pretend pas resoudre 100% des cas : si une ligne fantome est
    ACCIDENTELLEMENT complete et coherente en elle-meme mais contient des
    valeurs contaminees par une ligne voisine, aucune heuristique basee
    uniquement sur le texte des colonnes ne peut trancher avec certitude
    - un avertissement est alors imprime pour verification manuelle au
      lieu de deviner silencieusement.
    """
    normalized = [_normalize_row_columns(r) for r in rows]
    normalized = _reassign_orphan_strict_values(normalized)

    groups: dict = {}
    order: list = []
    for row in normalized:
        cn = row.get("container_number", "")
        if cn not in groups:
            groups[cn] = []
            order.append(cn)
        bucket = groups[cn]
        placed = False
        for i, existing in enumerate(bucket):
            if _is_same_cargo_entry(existing, row):
                bucket[i] = _merge_cargo_entry(existing, row)
                placed = True
                break
        if not placed:
            bucket.append(row)

    result = []
    for cn in order:
        result.extend(groups[cn])

    if len(result) < len(rows):
        print(f"      🧹 {len(rows) - len(result)} ligne(s) fusionnee(s)/ecartee(s) "
              f"par reconciliation des conteneurs dupliques ({len(rows)} -> {len(result)} lignes)")

    return result


def _clean_contact_info_cross_column_leaks(rows: list) -> list:
    """
    FIX v6.2 (2026-09-08) : observe sur IRENES POWER - certaines lignes
    voient leur contact_info prefixe par des valeurs qui appartiennent en
    realite a une AUTRE colonne d'une autre ligne (ex: contact_info=
    "10386,21 130912 Mr. Mohamed ..." ou "10386,21" est le net_weight et
    "130912" le stowage_position de la ligne TCKU3411583, pas de cette
    ligne-ci). Ce n'est jamais un vrai numero de telephone dans ce
    document (les telephones y comportent toujours un "+", un "-", ou au
    moins 8 chiffres bruts) - on peut donc retirer sans risque, d'un
    contact_info, tout token qui correspond EXACTEMENT a une valeur de
    net_weight/quantity/stowage_position deja utilisee ailleurs dans le
    tableau.

    Ne resout PAS les cas ou le contact_info d'une ligne a ete entierement
    REMPLACE par le nom/telephone d'une autre ligne (aucune valeur
    numerique a filtrer dans ce cas) - ce type de contamination necessite
    les detections brutes de la colonne contact_info pour etre corrige
    fiablement, et est signale separement (voir extract_dgm_table).
    """
    known_numeric_values = set()
    for r in rows:
        for col in ("net_weight", "quantity", "stowage_position"):
            v = (r.get(col) or "").strip()
            if v:
                known_numeric_values.add(v)

    for r in rows:
        ci = (r.get("contact_info") or "").strip()
        if not ci:
            continue
        tokens = ci.split()
        kept = [t for t in tokens if t.strip(",.") not in known_numeric_values]
        cleaned = " ".join(kept).strip()
        if cleaned != ci:
            print(f"      🧹 {r.get('container_number')} : contact_info nettoye "
                  f"d'un fragment numerique appartenant a une autre ligne "
                  f"('{ci}' -> '{cleaned}')")
            r["contact_info"] = cleaned
    return rows


def _prune_far_echo_cluster(dets: list, gap_threshold: float = 350,
                             duplicate_match_ratio: float = 0.5) -> list:
    """
    FIX v6.4 (2026-09-09) : observe sur IRENES POWER - un groupe de
    detections isole tres a droite du reste du tableau (~+1400px, au-dela
    d'un vide net) s'est avere etre un ECHO : chaque texte qu'il contient
    duplique, mot pour mot, une donnee deja lue plus a gauche (ex:
    "ZEYNEP YILDIZ" a sa position reelle x=2901 ET en echo a x=4352). Le
    decalage vertical de cet echo DERIVE au fil des lignes, si bien qu'il
    finit par tomber dans la bande d'une AUTRE ligne que la sienne et la
    contamine (ex: FCGU1696025 recevait "ZEYNEP YILDIZ", contact reel de
    TEMU2531640, a la place de son propre "Pilar Ramos").

    FIX du fix (v6.3 -> v6.4) : la premiere version ne regardait que la
    colonne la plus a droite par ANCRE - or les ancres unite/net_weight/
    stowage_position de ce document sont elles-memes mal calibrees (leurs
    vraies donnees tombent a un x SUPERIEUR a l'ancre "contact_info"), si
    bien qu'elles comblaient artificiellement l'espace entre le vrai
    contact_info et son echo, et le vide (~400px) repassait sous le seuil
    - le filtre ne se declenchait jamais. Cette version :
      1. cherche le vide sur l'ENSEMBLE des detections de la ligne/zone
         (pas une colonne precise, dont la position peut etre mal calibree) ;
      2. ne supprime le groupe isole a droite QUE si une bonne partie
         (>= `duplicate_match_ratio`) de ses textes (normalises, casse et
         ponctuation ignorees) est un DOUBLON EXACT d'un texte deja present
         dans le reste des detections - une vraie colonne supplementaire
         legitime n'aurait aucune raison de dupliquer verbatim des donnees
         d'autres lignes, donc ce test evite de supprimer une colonne reelle
         par erreur.
    """
    if len(dets) < 4:
        return dets

    xs = sorted(set(round(d["bbox"]["x0"]) for d in dets))
    clusters = [[xs[0]]]
    for x in xs[1:]:
        if x - clusters[-1][-1] > gap_threshold:
            clusters.append([x])
        else:
            clusters[-1].append(x)

    if len(clusters) <= 1:
        return dets

    far_lo, far_hi = clusters[-1][0], clusters[-1][-1]
    far_dets = [d for d in dets if far_lo - 1 <= d["bbox"]["x0"] <= far_hi + 1]
    far_ids = {id(d) for d in far_dets}
    rest_dets = [d for d in dets if id(d) not in far_ids]

    def _norm(text):
        return re.sub(r"[^A-Z0-9]", "", (text or "").upper())

    rest_norm_texts = {_norm(d["text"]) for d in rest_dets if _norm(d["text"])}
    if not far_dets or not rest_norm_texts:
        return dets

    dup_count = sum(1 for d in far_dets if _norm(d["text"]) in rest_norm_texts)
    ratio = dup_count / len(far_dets)

    if ratio >= duplicate_match_ratio:
        print(f"      🧹 {len(far_dets)} detection(s) 'echo' retiree(s) - groupe isole "
              f"a droite (x>={far_lo:.0f}) dont {dup_count}/{len(far_dets)} valeurs "
              f"dupliquent exactement des donnees deja lues plus a gauche "
              f"(probable reimpression/echo OCR)")
        return rest_dets

    return dets


def _rows_from_detections(table_dets: list, anchors: list, boundary_dets: list = None) -> list:
    """
    boundary_dets : ensemble de detections a utiliser UNIQUEMENT pour
    calculer les frontieres de lignes (_build_container_row_bounds).
    FIX v6 : doit etre l'ensemble de detections D'AVANT la fusion des
    detections retry (`retry_narrow_columns_fn`), pour eviter qu'un
    leger decalage vertical des detections retry ne cree des frontieres
    fantomes qui decoupent des bandes a cheval sur deux lignes reelles.
    Si non fourni (retro-compatibilite), on retombe sur table_dets
    comme avant.
    """
    table_dets = _filter_border_artifacts(table_dets)
    if boundary_dets is None:
        boundary_dets = table_dets
    else:
        boundary_dets = _filter_border_artifacts(boundary_dets)

    boundaries = _build_container_row_bounds(boundary_dets)
    if not boundaries:
        return []

    max_y = max(d["bbox"]["y1"] for d in table_dets) + 10

    band_starts = [0.0]
    for i in range(len(boundaries) - 1):
        gap = boundaries[i + 1] - boundaries[i]
        midpoint = boundaries[i] + gap * (0.5 + FRONTIER_BIAS)
        band_starts.append(midpoint)
    band_starts.append(max_y)

    # DEBUG (temporaire) : affiche les frontieres de lignes reellement
    # utilisees, pour diagnostiquer un cas ou une detection tombe dans la
    # mauvaise bande (ou aucune bande) malgre une position y qui semblait
    # correcte au vu d'autres dumps (retry class/quantity, contact_info...).
    print(f"      🐞 DEBUG bandes de lignes (container boundaries -> [debut, fin) reel) :")
    for i, b in enumerate(boundaries):
        print(f"         ligne {i+1} : boundary={b:.0f}  bande=[{band_starts[i]:.0f}, {band_starts[i+1]:.0f})")

    raw_rows = []
    for i in range(len(boundaries)):
        y_start = band_starts[i]
        y_end = band_starts[i + 1]
        band_dets = [d for d in table_dets if y_start <= d["bbox"]["y0"] < y_end]
        if not band_dets:
            continue

        row_buckets = {col_key: [] for col_key, _ in anchors}
        for tok in sorted(band_dets, key=lambda w: (w["bbox"]["y0"], w["bbox"]["x0"])):
            token_text = clean_token(tok["text"])
            col_key = _nearest_column(tok["bbox"]["x0"], anchors, token_text=token_text)
            if token_text:
                row_buckets[col_key].append(token_text)

        row = {
            col_key: _dedupe_repeated_phrase(" ".join(words).strip())
            for col_key, words in row_buckets.items()
        }
        raw_rows.append(row)

    rows = []
    for row in raw_rows:
        has_identity = any(row.get(c) for c in IDENTIFYING_COLUMNS)

        if not has_identity:
            if rows:
                for col_key, value in row.items():
                    if value:
                        prev_value = rows[-1].get(col_key, "")
                        rows[-1][col_key] = (prev_value + " " + value).strip()
            continue

        rows.append(row)

    rows = _fix_shifted_net_weight_stowage(rows)
    rows = [_fix_swapped_class_un_number(r) for r in rows]
    rows = _drop_exact_reprint_duplicates(rows)
    rows = _reconcile_duplicate_containers(rows)
    rows = _clean_contact_info_cross_column_leaks(rows)
    return rows


def extract_dgm_table(all_detections: list, table_start_y: float,
                       retry_narrow_columns_fn=None, header_fields=None) -> list:
    all_detections = _strip_document_header_tokens(all_detections)
    if header_fields:
        all_detections = _strip_known_header_values(all_detections, header_fields)

    header_zone = _find_table_header_zone(all_detections, table_start_y)

    copy_starts = _find_copy_start_positions(header_zone)
    if len(copy_starts) > 1:
        print(f"      ⚠️  {len(copy_starts)} copies du tableau detectees cote a cote "
              f"(x={[f'{x:.0f}' for x in copy_starts]}) - traitement independant de chacune")

    all_rows = []
    page_max_x = max((d["bbox"]["x1"] for d in all_detections), default=copy_starts[-1] + 3000)

    for i, x_start in enumerate(copy_starts):
        x_end = copy_starts[i + 1] if i + 1 < len(copy_starts) else page_max_x + 1
        x_scope_start = max(0, x_start - 100)

        anchors = _detect_column_anchors(header_zone, x_scope_start, x_end)
        if not anchors:
            print(f"      ⚠️  Copie {i+1} : aucune colonne reconnue - ignoree")
            continue
        anchors = _synthesize_missing_un_number_anchor(anchors)

        label = f" (copie {i+1}/{len(copy_starts)})" if len(copy_starts) > 1 else ""
        print(f"      📊 Colonnes du tableau detectees{label} : "
              f"{', '.join(f'{k}(x={x:.0f})' for k, x in anchors)}")

        missing_cols = [k for k, _ in TABLE_COLUMN_ANCHORS if k not in {a[0] for a in anchors}]
        if missing_cols:
            print(f"      ⚠️  Colonnes NON detectees{label} : {', '.join(missing_cols)}")

        header_end_y = _compute_header_end_y(header_zone, table_start_y, x_scope_start, x_end)
        print(f"      🔍 DEBUG table_start_y={table_start_y:.0f}, header_end_y={header_end_y:.0f}{label}")

        table_dets = [
            d for d in all_detections
            if d["bbox"]["y0"] > header_end_y and x_scope_start <= d["bbox"]["x0"] < x_end
        ]
        if not table_dets:
            continue

        # FIX v6.4 : retrait du cluster "echo" isole a droite (voir
        # _prune_far_echo_cluster) - fait sur l'ENSEMBLE des detections de
        # la zone tableau, pas colonne par colonne (les ancres unite/
        # net_weight/stowage_position peuvent etre mal calibrees sur ce
        # type de document, ce qui rendrait un decoupage par colonne peu
        # fiable ici).
        table_dets = _prune_far_echo_cluster(table_dets)

        table_end_y = max(d["bbox"]["y1"] for d in table_dets)

        # FIX v6 : instantane des detections AVANT ajout du retry, pour le
        # calcul des frontieres de lignes uniquement (voir _rows_from_detections).
        boundary_dets = list(table_dets)

        if retry_narrow_columns_fn is not None:
            extra = retry_narrow_columns_fn(anchors, header_end_y, table_end_y)
            if extra:
                extra = [d for d in extra if x_scope_start <= d["bbox"]["x0"] < x_end]
                extra = _filter_narrow_column_garbage(extra)
                if extra:
                    print(f"      🔎 {len(extra)} detection(s) supplementaire(s){label} "
                          f"(retry colonnes etroites class/quantity)")
                    table_dets = table_dets + extra

        avant = len(table_dets)
        table_dets = _dedupe_table_detections(table_dets)
        if len(table_dets) < avant:
            print(f"      🧹 {avant - len(table_dets)} detection(s) dupliquee(s){label} "
                  f"retiree(s) (passe originale + retry)")

        table_dets = _strip_column_label_tokens(table_dets)
        boundary_dets = _strip_column_label_tokens(boundary_dets)

        rows = _rows_from_detections(table_dets, anchors, boundary_dets=boundary_dets)
        all_rows.extend(rows)

    return all_rows


# --------------------------------------------------------------------------
# DEBUG (temporaire) : dump brut (y, x, texte) d'une colonne du tableau,
# pour diagnostiquer une colonne mal extraite (meme methode que celle qui
# a permis de corriger class/quantity). A retirer une fois le probleme
# contact_info diagnostique/corrige.
# --------------------------------------------------------------------------

def debug_dump_column_zone(all_detections: list, anchors: list, col_key: str,
                            header_end_y: float, table_end_y: float,
                            x_scope_end: float = None, y_margin: float = 30) -> None:
    """
    Affiche, dans le meme format que le retry class/quantity
    ('y=.... x=.... 'texte''), toutes les detections brutes qui tombent
    dans la plage x de la colonne `col_key` (ex: "contact_info"), entre
    header_end_y et table_end_y.

    Usage (a inserer temporairement dans extract_dgm_table, juste apres
    la ligne "table_dets = [...]" et AVANT le merge des detections retry) :

        debug_dump_column_zone(all_detections, anchors, "contact_info",
                                header_end_y, table_end_y)

    anchors : la liste (col_key, x0) deja calculee par _detect_column_anchors
              dans extract_dgm_table pour la copie de tableau en cours.
    x_scope_end : optionnel - x de fin de la copie de tableau en cours
                  (x_end dans extract_dgm_table), pour ne pas deborder sur
                  une eventuelle copie voisine cote a cote. Si omis, on
                  prend +l'infini.
    """
    anchor_dict = dict(anchors)
    if col_key not in anchor_dict:
        print(f"      🐞 DEBUG : colonne '{col_key}' non trouvee parmi les anchors "
              f"{[k for k, _ in anchors]} - rien a afficher")
        return

    sorted_anchors = sorted(anchors, key=lambda t: t[1])
    x_min = anchor_dict[col_key]
    x_max = x_scope_end if x_scope_end is not None else float("inf")
    for k, x0 in sorted_anchors:
        if x0 > x_min:
            x_max = min(x_max, x0)
            break

    print(f"      🐞 DEBUG dump brut colonne '{col_key}' "
          f"(x=[{x_min:.0f}, {x_max:.0f}], y=[{header_end_y - y_margin:.0f}, "
          f"{table_end_y + y_margin:.0f}]) :")

    scoped = [
        d for d in all_detections
        if x_min <= d["bbox"]["x0"] < x_max
        and header_end_y - y_margin <= d["bbox"]["y0"] <= table_end_y + y_margin
    ]
    for d in sorted(scoped, key=lambda w: (w["bbox"]["y0"], w["bbox"]["x0"])):
        print(f"         y={d['bbox']['y0']:.0f} x={d['bbox']['x0']:.0f}  '{d['text']}'")

    if not scoped:
        print("         (aucune detection trouvee dans cette zone)")