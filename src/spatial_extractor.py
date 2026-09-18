"""
spatial_extractor.py - Extraction par position spatiale (bounding boxes)
Extrait les champs en utilisant la position des mots dans le document.
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

@dataclass
class FieldConfig:
    """Configuration d'un champ à extraire."""
    name: str
    labels: List[str]
    x_range: Tuple[float, float]  # (min, max) en fraction de la largeur de page
    y_tolerance: int = 30
    postprocess: Optional[str] = None  # 'number', 'imo', 'date'

class SpatialExtractor:
    """Extracteur basé sur la position spatiale (bounding boxes)."""
    
    def __init__(self):
        self.fields = [
            FieldConfig("submitted_port", ["Submitted at the port of", "Submitted at the port of."], (0.0, 0.50)),
            FieldConfig("submission_date", ["Date"], (0.30, 0.60), postprocess="date"),
            FieldConfig("ship_name", ["Name of Ship or inland", "Name of Ship"], (0.0, 0.50)),
            FieldConfig("imo_number", ["IMO Number"], (0.30, 0.60), postprocess="imo"),
            FieldConfig("last_port", ["Arriving from", "Arriving from (Last port)"], (0.0, 0.50)),
            FieldConfig("next_port", ["Sailing to", "Sailing to (Next port)"], (0.30, 0.60)),
            FieldConfig("nationality", ["Nationality / Flag of vessel", "Flag of vessel"], (0.0, 0.50)),
            FieldConfig("master_name", ["Master's Name"], (0.30, 0.60)),
            FieldConfig("gross_tonnage", ["Gross Tonnage", "International Gross Tonnage"], (0.0, 0.50), postprocess="number"),
            FieldConfig("net_tonnage", ["Net Tonnage", "International Net Tonnage"], (0.30, 0.60), postprocess="number"),
            FieldConfig("who_affected_area", ["World Health Organization"], (0.0, 0.50)),
            FieldConfig("port_date_visit_area", ["Port and date of visit"], (0.0, 0.50)),
            FieldConfig("crew_members", ["Number of crew members", "crew members"], (0.0, 0.50), postprocess="number"),
            FieldConfig("passengers", ["Number of passenger", "passenger"], (0.30, 0.60), postprocess="number"),
        ]
        self.certificate_fields = [
            FieldConfig("certificate_carried_on_board", ["Certificate carried on board", "carried on board"], (0.0, 0.80)),
            FieldConfig("certificate_date", ["Date:", "30/01/2026"], (0.0, 0.80), postprocess="date"),
            FieldConfig("certificate_issued_at", ["issued at:"], (0.0, 0.80)),
            FieldConfig("valid_till", ["valid till:", "valid till"], (0.0, 0.80), postprocess="date"),
            FieldConfig("re_inspection_required", ["Re-inspection required"], (0.0, 0.80)),
            FieldConfig("drinking_water_date", ["Last analysis of the drinking water"], (0.0, 0.80), postprocess="date"),
            FieldConfig("drinking_water_issued_at", ["ON BOARD, AT SEA"], (0.0, 0.80)),
            FieldConfig("medical_certificate_date", ["Medical certificate"], (0.0, 0.80), postprocess="date"),
            FieldConfig("medical_certificate_issued_at", ["MUMBAI, INDIA"], (0.0, 0.80)),
            FieldConfig("fumigated_cargo", ["fumigated cargo"], (0.0, 0.80)),
        ]

    def extract(self, detections: List[Dict], page_width: float) -> Dict:
        """
        Extrait les champs en utilisant la position spatiale.
        
        Args:
            detections: Liste des détections OCR (text, bbox, confidence)
            page_width: Largeur de la page en pixels
        
        Returns:
            Dictionnaire des champs extraits
        """
        if not detections:
            return {}
        
        normalized = self._normalize(detections)
        result = {}
        confidence = {}
        
        # Extraction des champs principaux
        for field in self.fields:
            value, conf = self._extract_field(normalized, field, page_width)
            if value is not None:
                result[field.name] = self._postprocess(value, field.postprocess)
                confidence[field.name] = conf
        
        # Extraction des champs du certificat (fallback)
        for field in self.certificate_fields:
            if field.name not in result:
                value, conf = self._extract_field(normalized, field, page_width, search_wide=True)
                if value is not None:
                    result[field.name] = self._postprocess(value, field.postprocess)
        
        return result
    
    def _normalize(self, detections: List[Dict]) -> List[Dict]:
        """Normalise les détections OCR."""
        normalized = []
        for d in detections:
            if not d.get("text", "").strip():
                continue
            bbox = d.get("bbox")
            if not bbox:
                continue
            # Normaliser le bbox
            if isinstance(bbox, dict):
                bbox = bbox
            elif isinstance(bbox, list) and len(bbox) >= 4:
                if isinstance(bbox[0], (list, tuple)):
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    bbox = {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)}
                else:
                    bbox = {"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]}
            else:
                continue
            normalized.append({
                "text": d["text"].strip(),
                "bbox": bbox,
                "confidence": d.get("confidence", 1.0)
            })
        return normalized
    
    def _extract_field(self, detections: List[Dict], field: FieldConfig, page_width: float, 
                       search_wide: bool = False) -> Tuple[Optional[str], float]:
        """
        Extrait un champ spécifique.
        
        Returns:
            (valeur, confiance)
        """
        x_min = page_width * field.x_range[0]
        x_max = page_width * field.x_range[1] if field.x_range[1] < 1.0 else page_width
        
        # Trouver le label
        label_found = None
        for d in detections:
            text_lower = d["text"].lower()
            for label in field.labels:
                if label.lower() in text_lower:
                    label_found = d
                    break
            if label_found:
                break
        
        if not label_found:
            return None, 0.0
        
        # Trouver la valeur
        label_y = (label_found["bbox"]["y0"] + label_found["bbox"]["y1"]) / 2
        label_x_right = label_found["bbox"]["x1"]
        
        best_value = None
        best_dist = float('inf')
        
        for d in detections:
            if d == label_found:
                continue
            other_y = (d["bbox"]["y0"] + d["bbox"]["y1"]) / 2
            other_x = d["bbox"]["x0"]
            
            # Même ligne ou ligne suivante
            if search_wide:
                y_diff = abs(other_y - label_y)
                if y_diff > 80:
                    continue
            else:
                if abs(other_y - label_y) > field.y_tolerance:
                    continue
            
            # À droite du label
            if other_x <= label_x_right + 5:
                continue
            
            # Dans la colonne des valeurs
            if not (x_min <= other_x < x_max):
                continue
            
            # Ne pas prendre un autre label
            is_other_label = False
            for f in self.fields:
                for lbl in f.labels:
                    if lbl.lower() in d["text"].lower() and d != label_found:
                        is_other_label = True
                        break
                if is_other_label:
                    break
            if is_other_label:
                continue
            
            # Vérifier que la valeur n'est pas trop loin
            if search_wide:
                dist = other_x - label_x_right
                if dist < best_dist:
                    best_dist = dist
                    best_value = d["text"]
            else:
                dist = other_x - label_x_right
                if dist < best_dist:
                    best_dist = dist
                    best_value = d["text"]
        
        if best_value:
            conf = 0.9 if best_dist < 200 else 0.6
            return best_value, conf
        
        # Si aucune valeur trouvée, chercher sur la ligne suivante
        if not best_value and not search_wide:
            return self._extract_field(detections, field, page_width, search_wide=True)
        
        return None, 0.0
    
    def _postprocess(self, value: str, postprocess: Optional[str]) -> str:
        """Post-traite la valeur."""
        if not value:
            return None
        value = value.strip()
        
        if postprocess == "number":
            digits = re.sub(r"[^\d]", "", value)
            return int(digits) if digits else None
        elif postprocess == "imo":
            digits = re.sub(r"[^\d]", "", value)
            return digits if digits else None
        elif postprocess == "date":
            # Normaliser les dates
            match = re.search(r'(\d{2}[/.]\d{2}[/.]\d{4})', value)
            if match:
                return match.group(1)
            return value
        
        return value


def extract_spatial(detections: List[Dict], page_width: float) -> Dict:
    """Fonction d'extraction spatiale (point d'entrée)."""
    extractor = SpatialExtractor()
    return extractor.extract(detections, page_width)