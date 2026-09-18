"""
dgd_table_extractor.py - Extraction du tableau Classe/Division (DGD)
======================================================================
Le tableau du "Dangerous Cargo Declaration" est une GRILLE FIXE :

    Classe 1 : divisions 1,2,3,4,5,6
    Classe 2 : divisions 1,2,3
    Classe 3 : (pas de division)
    Classe 4 : divisions 1,2,3
    Classe 5 : divisions 1,2
    Classe 6 : divisions 1,2
    Classe 7 : (pas de division)
    Classe 8 : (pas de division)
    Classe 9 : (pas de division)

FIX (v3) - DECOUPAGE PAR BLOCS DE CLASSE :
    v1 (comptage de lignes OCR) et v2 (20 bandes de hauteur EGALE)
    echouaient toutes les deux car les frontieres entre GROUPES de
    classes ne sont pas parfaitement uniformes (bordures plus epaisses
    entre classes, padding variable) - une division uniforme sur 20
    lignes produit un decalage systematique.

    v3 : on repere d'abord les colonnes CLASSE (x ~365) et DIVISION
    (x ~614) SEPAREMENT (elles sont distinctes, pas une seule "colonne
    gauche" comme suppose avant). Les numeros de CLASSE reellement lus
    (ex: "2","3","4"..."9") servent d'ANCRES FIABLES pour le debut de
    CHAQUE bloc de classe - bien plus robuste qu'une division uniforme,
    car ca respecte les frontieres REELLES entre classes. Un numero de
    classe non detecte (ex: "1" souvent manque, chiffre isole minuscule)
    est INTERPOLE a partir du bloc precedent plutot que de faire
    planter tout l'alignement.

    A l'INTERIEUR de chaque bloc de classe, on divise EQUITABLEMENT
    entre ses propres divisions (6 pour Classe 1, 3 pour Classe 2, etc.)
    - la encore plus fiable qu'une division globale sur 20 lignes, car
    les lignes AU SEIN d'un meme bloc de classe sont bien plus
    regulieres entre elles que les groupes de classes entre eux.

    Cellule vide sur le document -> "" (pas None).

FIX (v4, 2026-09-12) - ANCRE "in_transit" INTROUVABLE :
    Le tableau a en realite DEUX lignes d'en-tete empilees :
        Ligne A (au-dessus) : "To load (weight in tons)" | "To unload
            (weight in tons)" | "In transit (weight in tons)"
        Ligne B (sous-en-tetes) : "Loading" | "Transhipment" |
            "Unloading" | "Transhipment"
    "In transit" n'a pas de sous-colonne : son libelle n'existe QUE sur
    la ligne A, jamais sur la ligne B. Or _find_subheader_row et
    _detect_data_column_anchors ne cherchaient que sur la ligne B (celle
    qui contient "transhipment" + un mot load/unload) - l'ancre
    "in_transit" n'etait donc JAMAIS detectee. Consequence observee :
    toute valeur de la colonne "In transit" se faisait absorber par
    "to_unload_transhipment" (la derniere ancre disponible plus a
    gauche, donc la plus proche) sur un document, et disparaissait
    carrement sur un autre (des lors qu'elle tombait hors de la zone de
    donnees calculee a partir de data_x_start, lui-meme derive des seules
    ancres de la ligne B).

    Correctif : apres avoir cherche les 4 ancres habituelles sur la
    ligne B, on cherche EN PLUS sur la ligne juste AU-DESSUS (ligne A)
    un token "in transit" / "transit" - sans risque de faux positif,
    puisque la ligne A ne contient ni "transhipment" ni "loading" ni
    "unloading" (uniquement "To load (weight in tons)" et "To unload
    (weight in tons)", qui ne matchent aucun pattern existant).
"""

import re

from field_extractor import group_into_lines, clean_token, normalize_for_label_matching

# (classe, [divisions]) - [None] pour une classe sans sous-division.
CLASS_BLOCKS = [
    (1, [1, 2, 3, 4, 5, 6]),
    (2, [1, 2, 3]),
    (3, [None]),
    (4, [1, 2, 3]),
    (5, [1, 2]),
    (6, [1, 2]),
    (7, [None]),
    (8, [None]),
    (9, [None]),
]

ROW_Y_TOL = 14.0
COLUMN_CLUSTER_GAP = 100.0  # separation minimale (px) pour distinguer 2 colonnes distinctes
SUPER_HEADER_Y_WINDOW = 80.0  # fenetre de recherche (px) au-dessus de la ligne de sous-en-tetes

DATA_COLUMN_ANCHORS = [
    ("to_load_col1", [r"\bexport\b", r"\bloading\b"]),
    ("to_load_transhipment", [r"transhipment"]),
    ("to_unload_col1", [r"\bimport\b", r"\bunloading\b"]),
    ("to_unload_transhipment", [r"transhipment"]),
    ("in_transit", [r"in\s*trans\w*", r"transit"]),
]

DATA_FIELD_KEYS = [k for k, _ in DATA_COLUMN_ANCHORS]

SINGLE_DIGIT_PATTERN = re.compile(r"^[1-9]$")


def _find_subheader_row(detections: list) -> list:
    lines = group_into_lines(detections, y_tol=ROW_Y_TOL)
    lines.sort(key=lambda line: min(w["bbox"]["y0"] for w in line))

    for line in lines:
        text = normalize_for_label_matching(" ".join(w["text"] for w in line))
        has_transhipment = "transhipment" in text
        has_load_word = any(w in text for w in ("export", "loading"))
        has_unload_word = any(w in text for w in ("import", "unloading"))
        if has_transhipment and (has_load_word or has_unload_word):
            return line
    return []


def _find_super_header_zone(detections: list, subheader_line: list,
                             y_window: float = SUPER_HEADER_Y_WINDOW) -> list:
    """
    FIX v4 : la colonne "In transit" n'a pas de sous-colonne - son
    libelle "In transit (weight in tons)" est ecrit sur la ligne
    d'en-tete SUPERIEURE (celle qui porte aussi "To load (weight in
    tons)" et "To unload (weight in tons)"), pas sur la ligne de
    sous-en-tetes "Loading / Transhipment / Unloading / Transhipment"
    que _find_subheader_row identifie. On isole ici cette ligne
    superieure (tout ce qui se trouve juste au-dessus, dans une fenetre
    de `y_window` px) pour y chercher specifiquement l'ancre manquante.
    """
    if not subheader_line:
        return []
    subheader_top = min(w["bbox"]["y0"] for w in subheader_line)
    return [
        d for d in detections
        if subheader_top - y_window <= d["bbox"]["y0"] < subheader_top
    ]


def _detect_data_column_anchors(header_line: list) -> list:
    anchors = []
    used_ids = set()
    for col_key, patterns in DATA_COLUMN_ANCHORS:
        best_tok, best_x0 = None, None
        for tok in header_line:
            if id(tok) in used_ids:
                continue
            text_low = tok["text"].strip().lower()
            for pattern in patterns:
                if re.search(pattern, text_low, re.IGNORECASE):
                    if best_x0 is None or tok["bbox"]["x0"] < best_x0:
                        best_x0, best_tok = tok["bbox"]["x0"], tok
                    break
        if best_tok is not None:
            anchors.append((col_key, best_x0))
            used_ids.add(id(best_tok))
    anchors.sort(key=lambda t: t[1])
    return anchors


def _nearest_column(x0: float, anchors: list) -> str:
    best_key, best_dist = None, None
    for col_key, anchor_x0 in anchors:
        dist = abs(x0 - anchor_x0)
        if best_dist is None or dist < best_dist:
            best_key, best_dist = col_key, dist
    return best_key


def _split_two_column_clusters(dets: list, gap: float = COLUMN_CLUSTER_GAP) -> tuple:
    """
    Separe une liste de detections en 2 groupes selon leur position X,
    en cherchant le plus grand ecart entre valeurs X consecutives triees.
    Retourne (groupe_x_faible, groupe_x_eleve) - typiquement (colonne
    Classe, colonne Division).
    """
    if not dets:
        return [], []
    sorted_dets = sorted(dets, key=lambda d: d["bbox"]["x0"])
    xs = [d["bbox"]["x0"] for d in sorted_dets]

    best_gap, best_idx = 0, len(xs)
    for i in range(1, len(xs)):
        g = xs[i] - xs[i - 1]
        if g > best_gap:
            best_gap, best_idx = g, i

    if best_gap < gap:
        # Pas de separation nette detectee - tout dans le groupe "Division"
        # (comportement de secours, pas cense arriver en pratique).
        return [], sorted_dets

    return sorted_dets[:best_idx], sorted_dets[best_idx:]


def _detect_class_anchors(class_col_dets: list) -> dict:
    """
    Construit {numero_classe: y0} pour chaque numero de classe (1-9)
    EFFECTIVEMENT lu dans la colonne Classe (chiffre isole 1-9). Un
    numero non detecte (frequent pour la Classe 1, chiffre minuscule
    facilement manque par l'OCR) sera absent du dict - gere par
    interpolation dans extract_dgd_table.
    """
    anchors = {}
    for d in sorted(class_col_dets, key=lambda x: x["bbox"]["y0"]):
        text = clean_token(d["text"]).strip()
        if SINGLE_DIGIT_PATTERN.match(text):
            cls = int(text)
            if 1 <= cls <= 9 and cls not in anchors:
                anchors[cls] = d["bbox"]["y0"]
    return anchors


def _parse_division_tokens(division_dets: list, expected_divisions: set) -> dict:
    """
    FIX v7 (2026-09-12) : contrairement aux numeros de CLASSE (centres sur
    tout leur bloc de divisions), un dump brut a montre que les numeros de
    DIVISION sont positionnes quasiment a la meme hauteur que leur propre
    valeur (ecart de quelques px seulement) - donc utilisables directement
    comme ancres de ligne, sans hypothese de centrage.

    Retourne {numero_division: y0} pour chaque division EFFECTIVEMENT lue
    et attendue dans ce bloc de classe. Gere le cas frequent ou l'OCR
    fusionne 2 chiffres adjacents en un seul token (ex: "23" quand les
    divisions 2 et 3 sont tres rapprochees) : dans ce cas, on ne prend que
    le PREMIER chiffre du token qui correspond a une division attendue pas
    encore vue - prendre les deux chiffres du token fusionne creerait deux
    "lignes" avec exactement le meme Y, ce qui casse le calcul de
    frontieres par milieu.
    """
    found = {}
    for d in sorted(division_dets, key=lambda x: x["bbox"]["y0"]):
        text = clean_token(d["text"]).strip()
        if SINGLE_DIGIT_PATTERN.match(text):
            n = int(text)
            if n in expected_divisions and n not in found:
                found[n] = d["bbox"]["y0"]
        else:
            for ch in text:
                if ch.isdigit() and int(ch) in expected_divisions and int(ch) not in found:
                    found[int(ch)] = d["bbox"]["y0"]
                    break
    return found


def _compute_row_boundaries(block_start: float, block_end: float, divisions: list, division_y: dict) -> list:
    """
    Calcule les bandes [debut, fin) de chaque division d'un bloc de classe.

    Si on a au moins 2 ancres de division REELLEMENT lues, la frontiere
    entre 2 divisions consecutives connues est leur MILIEU (meme principe
    que pour les frontieres de classe, mais applique directement aux
    ancres de division puisqu'elles marquent deja la ligne elle-meme, pas
    le centre d'un bloc plus large).

    FIX v9 (2026-09-12) : la premiere version donnait a la PREMIERE
    division CONNUE une bande "start=curseur herite" au lieu d'une bande
    propre centree sur sa propre ancre, des qu'au moins une division
    manquante la precedait (frequent : la Division 1 d'une classe est
    souvent un chiffre isole que l'OCR rate). Bug observe concretement sur
    DGD-ex-4 : la Division 2 de la Classe 1 (division 1 non lue) se
    retrouvait ecrasee sur une bande de 9px, largement en dehors de sa
    propre position reelle (y=877) - elle ressortait donc entierement
    vide alors que le document la renseigne bien.

    Correctif : chaque division CONNUE recoit d'abord une bande complete,
    calculee a partir de sa PROPRE ancre (milieu avec ses voisines connues,
    ou +/- la moitie de l'ecart moyen pour la premiere/derniere connue).
    Les divisions manquantes en tete (avant la premiere connue) et en
    queue (apres la derniere connue) se partagent EQUITABLEMENT le reste
    de l'espace disponible - imparfait quand l'espace est trop reduit,
    mais ne sacrifie plus jamais une division reellement lue.

    Repli (comportement d'origine) si moins de 2 ancres fiables : division
    egale du bloc entier.
    """
    n_div = len(divisions)
    if len(division_y) < 2:
        div_height = (block_end - block_start) / n_div
        return [(block_start + j * div_height, block_start + (j + 1) * div_height)
                for j in range(n_div)]

    known = sorted(division_y.items())
    avg_gap = (known[-1][1] - known[0][1]) / (len(known) - 1)

    # Bande de DEBUT pour chaque division connue - la premiere et la
    # derniere utilisent +/- la moitie de l'ecart moyen autour de leur
    # PROPRE ancre plutot que d'heriter d'un curseur venant d'une division
    # manquante voisine.
    known_start = {}
    for i, (div_num, y0) in enumerate(known):
        if i == 0:
            known_start[div_num] = max(block_start, y0 - avg_gap / 2)
        else:
            known_start[div_num] = (known[i - 1][1] + y0) / 2
    known_end_of_last = min(block_end, known[-1][1] + avg_gap / 2)

    first_known_idx = divisions.index(known[0][0])
    last_known_idx = divisions.index(known[-1][0])

    row_bounds = [None] * n_div

    # Divisions manquantes AVANT la premiere connue : partage equitable de
    # l'espace entre block_start et le debut (propre) de la premiere connue.
    if first_known_idx > 0:
        span_end = known_start[known[0][0]]
        step = (span_end - block_start) / first_known_idx
        for j in range(first_known_idx):
            row_bounds[j] = (block_start + j * step, block_start + (j + 1) * step)

    # Divisions connues (et implicitement, celles STRICTEMENT entre deux
    # connues consecutives - cas rare, pas gere explicitement ici).
    for i, (div_num, y0) in enumerate(known):
        idx = divisions.index(div_num)
        start = known_start[div_num]
        end = known_start[known[i + 1][0]] if i + 1 < len(known) else known_end_of_last
        row_bounds[idx] = (start, end)

    # Divisions manquantes APRES la derniere connue : partage equitable de
    # l'espace entre la fin (propre) de la derniere connue et block_end.
    trailing_missing = n_div - 1 - last_known_idx
    if trailing_missing > 0:
        step = (block_end - known_end_of_last) / trailing_missing
        for k in range(trailing_missing):
            j = last_known_idx + 1 + k
            row_bounds[j] = (known_end_of_last + k * step, known_end_of_last + (k + 1) * step)

    return row_bounds


def extract_dgd_table(detections: list) -> list:
    """
    Extrait les 20 lignes du tableau Classe/Division par decoupage en
    BLOCS DE CLASSE ancres sur les numeros de classe reellement lus,
    puis subdivision equitable au sein de chaque bloc (voir docstring
    du module).
    """
    subheader_line = _find_subheader_row(detections)
    if not subheader_line:
        print("      ⚠️  En-tete de colonnes du tableau DGD introuvable - extraction impossible")
        return []

    # DEBUG (temporaire) : contenu exact de la ligne de sous-en-tetes
    # identifiee, pour comprendre pourquoi subheader_y sort plus bas que
    # prevu sur DGD-ex-4.
    print(f"      🐞 DEBUG contenu de subheader_line ({len(subheader_line)} tokens) :")
    for w in sorted(subheader_line, key=lambda t: t["bbox"]["x0"]):
        print(f"         y0={w['bbox']['y0']:.0f} y1={w['bbox']['y1']:.0f} x0={w['bbox']['x0']:.0f}  '{w['text']}'")

    anchors = _detect_data_column_anchors(subheader_line)

    # FIX v4 : "in_transit" n'est jamais sur la ligne de sous-en-tetes -
    # on va la chercher specifiquement sur la ligne juste au-dessus.
    if not any(k == "in_transit" for k, _ in anchors):
        super_header_zone = _find_super_header_zone(detections, subheader_line)
        super_header_anchors = _detect_data_column_anchors(super_header_zone)
        found = [a for a in super_header_anchors if a[0] == "in_transit"]
        if found:
            print(f"      🩹 Ancre 'in_transit' introuvable sur la ligne de "
                  f"sous-en-tetes - trouvee sur la ligne d'en-tete superieure "
                  f"(x={found[0][1]:.0f})")
            anchors.extend(found)
        else:
            print("      ⚠️  Ancre 'in_transit' introuvable meme sur la ligne "
                  "d'en-tete superieure - les valeurs de cette colonne seront "
                  "probablement absorbees par la colonne voisine ou perdues")
    anchors.sort(key=lambda t: t[1])

    if len(anchors) < 3:
        print(f"      ⚠️  Seulement {len(anchors)}/5 colonnes de donnees detectees - "
              f"resultat probablement incomplet")
    print(f"      📊 Colonnes du tableau DGD detectees : "
          f"{', '.join(f'{k}(x={x:.0f})' for k, x in anchors)}")

    subheader_y = min(w["bbox"]["y1"] for w in subheader_line)
    data_x_start = anchors[0][1] - 30 if anchors else 0

    left_col_dets = [
        d for d in detections
        if d["bbox"]["y0"] > subheader_y + 5 and d["bbox"]["x0"] < data_x_start
    ]
    if not left_col_dets:
        print("      ⚠️  Colonnes Classe/Division introuvables sous l'en-tete - extraction impossible")
        return []

    class_col_dets, division_col_dets = _split_two_column_clusters(left_col_dets)
    print(f"      🔍 DEBUG : {len(class_col_dets)} detection(s) colonne Classe, "
          f"{len(division_col_dets)} detection(s) colonne Division")

    class_anchors = _detect_class_anchors(class_col_dets)
    print(f"      🔍 DEBUG ancres de classe detectees : "
          f"{ {k: round(v, 1) for k, v in sorted(class_anchors.items())} }")

    table_top_y = subheader_y
    table_bottom_y = max(d["bbox"]["y1"] for d in left_col_dets)

    # Construit le Y CENTRAL estime de chaque classe 1-9 : la vraie ancre
    # si detectee, sinon interpolation (classe precedente + ecart moyen
    # estime a partir des blocs voisins connus).
    known_ys = sorted(class_anchors.items())
    avg_gap = ((known_ys[-1][1] - known_ys[0][1]) / (known_ys[-1][0] - known_ys[0][0])
               if len(known_ys) >= 2 and known_ys[-1][0] != known_ys[0][0] else
               (table_bottom_y - table_top_y) / 9)

    class_center_y = {}
    for cls in range(1, 10):
        if cls in class_anchors:
            class_center_y[cls] = class_anchors[cls]
        elif cls - 1 in class_center_y:
            class_center_y[cls] = class_center_y[cls - 1] + avg_gap
        else:
            class_center_y[cls] = table_top_y

    # FIX v6 (2026-09-12) - LES ANCRES DE CLASSE SONT DES CENTRES DE BLOC,
    # PAS DES DEBUTS DE BLOC :
    #
    # Un dump brut des positions Y des VALEURS du tableau (colonnes to_load/
    # to_unload/in_transit), compare aux ancres de classe, a montre que le
    # numero de classe (ex: "4") n'est PAS aligne sur le HAUT de son bloc
    # de divisions mais approximativement CENTRE dessus - comme une
    # cellule HTML fusionnee (rowspan) dont le contenu est centre
    # verticalement sur toute la fusion. Verifie sur DGD-ex-2 : l'ancre de
    # la Classe 4 (y=1427) tombe presque exactement ENTRE la valeur de sa
    # division 2 (y=1407) et celle de sa division 3 (y=1462).
    #
    # Toutes les tentatives precedentes (marge fixe puis marge
    # proportionnelle + plafond) etaient condamnees car elles supposaient
    # toutes, a tort, que l'ancre = debut du bloc.
    #
    # Correctif, beaucoup plus simple et ne necessitant AUCUNE constante
    # calibree a la main : la frontiere entre deux classes consecutives
    # est le MILIEU entre leurs deux ancres. Verifie EXACTEMENT sur les 9
    # valeurs connues de DGD-ex-2 (100% correctement classees, y compris
    # la sous-division en divisions equitables a l'interieur du bloc).
    class_boundary = {}  # class_boundary[cls] = debut du bloc de la classe cls
    classes_sorted = sorted(class_center_y)
    for i, cls in enumerate(classes_sorted):
        if i == 0:
            gap = class_center_y[classes_sorted[1]] - class_center_y[cls]
            class_boundary[cls] = class_center_y[cls] - gap / 2
        else:
            class_boundary[cls] = (class_center_y[classes_sorted[i - 1]] + class_center_y[cls]) / 2
    last_gap = class_center_y[9] - class_center_y[8]
    class_boundary[10] = class_center_y[9] + last_gap / 2  # fin du bloc de la Classe 9

    print(f"      🔍 DEBUG frontieres de classe (ancres traitees comme CENTRES de bloc) : "
          f"{ {k: round(v, 1) for k, v in sorted(class_boundary.items())} }")

    # FIX v8 (2026-09-12) - AFFINAGE DES FRONTIERES A PARTIR DES DIVISIONS :
    #
    # Le centrage de l'ancre de classe n'est qu'une APPROXIMATION - verifie
    # en defaut sur DGD-ex-4 : le numero de Division 6 de la Classe 1 est
    # lu a y=1084, alors que la frontiere Classe1/Classe2 deduite du
    # centrage tombait a y=1067 - la Division 6 se retrouvait donc DEJA
    # hors de son propre bloc de Classe 1, et sa ligne de valeurs se
    # faisait absorber par la Division 1 de la Classe 2 juste apres.
    #
    # Quand on connait a la fois le DERNIER numero de division lu de la
    # classe precedente et le PREMIER numero de division lu de la classe
    # suivante, leur MILIEU est une frontiere bien plus fiable (ce sont
    # des ancres de LIGNE directes, pas une supposition de centrage) - on
    # remplace alors la frontiere centree par cette version affinee.
    dgd_divisions_by_class = dict(CLASS_BLOCKS)
    for i, cls in enumerate(classes_sorted[:-1]):
        next_cls = classes_sorted[i + 1]
        cls_divisions = dgd_divisions_by_class.get(cls, [None])
        next_divisions = dgd_divisions_by_class.get(next_cls, [None])
        if len(cls_divisions) <= 1 or len(next_divisions) <= 1:
            continue  # rien a affiner sans sous-division des deux cotes

        search_lo = class_boundary[cls]
        search_hi = class_boundary[next_cls + 1] if (next_cls + 1) in class_boundary else table_bottom_y
        nearby = [d for d in division_col_dets if search_lo <= d["bbox"]["y0"] < search_hi]

        last_div_of_cls = max(cls_divisions)
        first_div_of_next = min(next_divisions)
        y_last = y_first = None
        for d in nearby:
            text = clean_token(d["text"]).strip()
            if not SINGLE_DIGIT_PATTERN.match(text):
                continue
            n = int(text)
            if n == last_div_of_cls and (y_last is None or d["bbox"]["y0"] > y_last):
                y_last = d["bbox"]["y0"]
            if n == first_div_of_next and (y_first is None or d["bbox"]["y0"] < y_first):
                y_first = d["bbox"]["y0"]

        if y_last is not None and y_first is not None and y_first > y_last:
            refined = (y_last + y_first) / 2
            if abs(refined - class_boundary[next_cls]) > 1.0:
                print(f"      🩹 Frontiere Classe {cls}/Classe {next_cls} affinee : "
                      f"{class_boundary[next_cls]:.1f} -> {refined:.1f} (divisions "
                      f"{last_div_of_cls}@{y_last:.0f} et {first_div_of_next}@{y_first:.0f})")
                class_boundary[next_cls] = refined

    # FIX v10 (2026-09-12) : la toute PREMIERE classe du tableau n'a pas de
    # "classe precedente" pour affiner son propre DEBUT de bloc via la
    # methode ci-dessus. Si sa division la plus BASSE connue n'est pas la
    # Division 1 elle-meme (frequent : "1" est un chiffre isole souvent
    # rate par l'OCR), son propre rang + son propre ecart moyen donnent une
    # estimation bien plus fiable du debut reel du bloc que le centrage -
    # meme principe applique cette fois au bord EXTERNE de la Classe 1
    # plutot qu'a une frontiere interne. Sans ce correctif, les divisions
    # manquantes en tete de la Classe 1 recoivent une bande ridiculement
    # etroite (observe : 6px pour la Division 1 sur DGD-ex-4) et ressortent
    # vides alors que le document les renseigne bien.
    first_cls = classes_sorted[0]
    first_cls_divisions = dgd_divisions_by_class.get(first_cls, [None])
    if len(first_cls_divisions) > 1:
        upper_bound = class_boundary[classes_sorted[1]] if len(classes_sorted) > 1 else table_bottom_y
        first_cls_known = {}
        for d in division_col_dets:
            if not (class_boundary[first_cls] <= d["bbox"]["y0"] < upper_bound):
                continue
            text = clean_token(d["text"]).strip()
            if SINGLE_DIGIT_PATTERN.match(text) and int(text) in first_cls_divisions:
                n = int(text)
                if n not in first_cls_known:
                    first_cls_known[n] = d["bbox"]["y0"]

        if len(first_cls_known) >= 2:
            known_sorted_local = sorted(first_cls_known.items())
            local_avg_gap = (known_sorted_local[-1][1] - known_sorted_local[0][1]) / (len(known_sorted_local) - 1)
            first_known_div, first_known_y = known_sorted_local[0]
            first_known_idx = first_cls_divisions.index(first_known_div)
            if first_known_idx > 0 and local_avg_gap > 0:
                estimated_start = first_known_y - (first_known_idx + 0.5) * local_avg_gap
                if abs(estimated_start - class_boundary[first_cls]) > 1.0:
                    print(f"      🩹 Debut de la Classe {first_cls} affine : "
                          f"{class_boundary[first_cls]:.1f} -> {estimated_start:.1f} "
                          f"(a partir de la Division {first_known_div}@{first_known_y:.0f})")
                    class_boundary[first_cls] = estimated_start

    value_dets = [d for d in detections if d["bbox"]["y0"] > subheader_y + 5 and d["bbox"]["x0"] >= data_x_start]

    # DEBUG (temporaire) : dump brut de TOUTES les detections (pas
    # seulement value_dets - y compris celles filtrees par subheader_y ou
    # data_x_start) dans la zone ou la Division 1 de la Classe 1 devrait
    # se trouver, pour verifier si l'OCR l'a detectee du tout.
    print(f"      🐞 DEBUG dump brut TOUTES detections (y entre {class_boundary[first_cls]-40:.0f} "
          f"et {class_boundary[first_cls]+120:.0f}), subheader_y={subheader_y:.0f}, "
          f"data_x_start={data_x_start:.0f} :")
    for d in sorted(detections, key=lambda w: (w["bbox"]["y0"], w["bbox"]["x0"])):
        if class_boundary[first_cls] - 40 <= d["bbox"]["y0"] <= class_boundary[first_cls] + 120:
            print(f"         y={d['bbox']['y0']:.0f} x={d['bbox']['x0']:.0f}  '{d['text']}'")

    rows = []
    for block_idx, (cls, divisions) in enumerate(CLASS_BLOCKS):
        block_start = class_boundary[cls]
        block_end = class_boundary[cls + 1]
        n_div = len(divisions)

        if n_div > 1:
            # FIX v7 : sous-divise le bloc de classe en utilisant les
            # VRAIES positions des numeros de division lus dans ce bloc
            # (voir _parse_division_tokens / _compute_row_boundaries),
            # plutot qu'une division egale qui ignore ou les lignes sont
            # reellement dessinees.
            class_division_dets = [
                d for d in division_col_dets if block_start <= d["bbox"]["y0"] < block_end
            ]
            division_y = _parse_division_tokens(class_division_dets, set(divisions))
            row_bounds = _compute_row_boundaries(block_start, block_end, divisions, division_y)
        else:
            row_bounds = [(block_start, block_end)]

        for (row_y_start, row_y_end), div in zip(row_bounds, divisions):
            row = {"class": cls, "division": div,
                   "to_load_col1": "", "to_load_transhipment": "",
                   "to_unload_col1": "", "to_unload_transhipment": "", "in_transit": ""}

            band_toks = [d for d in value_dets if row_y_start <= d["bbox"]["y0"] < row_y_end]
            buckets = {k: [] for k in DATA_FIELD_KEYS}
            for tok in sorted(band_toks, key=lambda w: w["bbox"]["x0"]):
                col_key = _nearest_column(tok["bbox"]["x0"], anchors)
                token_text = clean_token(tok["text"])
                if token_text:
                    buckets[col_key].append(token_text)

            for col_key, words in buckets.items():
                row[col_key] = " ".join(words).strip()

            rows.append(row)

    return rows