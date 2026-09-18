"""
zone_extractor.py
==================
Decoupage automatique de la zone utile d'une page, selon le type de
document, AVANT l'OCR.

NOTE IMPORTANTE (mise a jour) : le rognage VERTICAL de la page 1
(HEADER_ZONES / crop_header_zone) a ete DESACTIVE. Il causait des bugs
recurrents et couteux a diagnostiquer sur differents fichiers (coupait
tantot avant la fin du tableau "Health Questions", tantot avant certains
champs de fin d'en-tete) car la position exacte ou le contenu tient sur la
page varie legerement d'un scan a l'autre (marges, letterhead, etc.).

Le gain de vitesse principal ne vient PAS de ce rognage vertical, mais de
should_run_ocr_on_page() qui evite de faire tourner l'OCR sur les pages
2/3 entierement inutilisees pour le type "Health" - ce gain-la est
conserve. crop_header_zone() est garde comme point d'extension future
(fonction no-op pour l'instant) plutot que supprime, pour ne pas casser
l'import dans main.py.
"""

import numpy as np


def crop_header_zone(image: np.ndarray, document_type: str, margin_fraction: float = 0.05) -> np.ndarray:
    """
    Ne recadre plus l'image (voir note en tete de module) - retourne
    l'image telle quelle. Conserve pour compatibilite d'appel avec
    main.py et comme point d'extension si un recadrage fiable est
    reintroduit plus tard (ex: detection dynamique de la fin du tableau
    plutot qu'une fraction fixe).
    """
    return image


def should_run_ocr_on_page(page_index: int, document_type: str) -> bool:
    """
    Indique si l'OCR doit etre execute sur cette page, selon le type de
    document. Pour "Health", les pages 1 ET 2 (index 0 et 1) sont
    exploitees : la page 1 pour l'en-tete + Health Questions, la page 2
    pour le certificat sanitaire (Valid Sanitation Control..., valid
    till, Re-inspection required) - repere en pratique comme etant a
    cheval entre la fin de la page 1 et le debut de la page 2 selon les
    documents. La page 3 (annexe/signatures/listes d'equipage) reste
    ignoree, non exploitee par field_extractor.py.
    """
    if document_type == "Health":
        return page_index in (0, 1)
    return True