"""
result_fusion.py - Fusion des résultats (améliorée)
"""

from typing import Dict, List


def should_call_llm(spatial_result: Dict, required_fields: List[str]) -> bool:
    """
    Détermine s'il faut appeler le LLM.
    Vérifie uniquement les champs critiques.
    """
    critical = ["submitted_port", "ship_name", "imo_number"]
    
    for field in critical:
        value = spatial_result.get(field)
        if value is None or value == "" or value == "null":
            return True
    
    return False


def get_missing_fields(spatial_result: Dict, required_fields: List[str]) -> List[str]:
    """Retourne la liste des champs manquants."""
    return [f for f in required_fields if spatial_result.get(f) is None]


def fuse_results(spatial_result: Dict, llm_result: Dict) -> Dict:
    """
    Fusionne les résultats avec priorité à la spatiale.
    Le LLM ne remplace JAMAIS une valeur spatiale valide.
    """
    result = {}
    warnings = []
    
    # Copier tous les champs de la spatiale
    for key, value in spatial_result.items():
        result[key] = value
    
    # Ajouter les champs du LLM uniquement s'ils sont manquants dans la spatiale
    for key, value in llm_result.items():
        if key.startswith("_"):
            continue
        if key not in result or result[key] is None or result[key] == "":
            # Vérifier que la valeur du LLM est plausible
            if value is not None and value != "" and value != "null":
                # Ne pas accepter les valeurs trop longues (> 50 caractères)
                if isinstance(value, str) and len(value) > 50:
                    warnings.append(f"{key}: valeur LLM trop longue ({len(value)} caractères), ignorée")
                    continue
                # Ne pas accepter les valeurs qui contiennent du texte de la Note
                if isinstance(value, str) and any(w in value.lower() for w in ["fever", "cough", "paralysis", "surgeon"]):
                    warnings.append(f"{key}: valeur LLM suspecte ('{value[:30]}...'), ignorée")
                    continue
                result[key] = value
                warnings.append(f"{key}: ajouté par LLM")
    
    if warnings:
        result["_warnings"] = warnings
    
    return result