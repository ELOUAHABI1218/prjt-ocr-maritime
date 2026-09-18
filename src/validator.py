def validate_and_correct(fields: dict) -> tuple:
    warnings = []
    corrected = dict(fields)
    
    # Corriger "VES" → "YES"
    for field in ["certificate_carried_on_board", "re_inspection_required", "who_affected_area"]:
        if field in corrected and corrected[field]:
            val = str(corrected[field]).upper()
            if "VES" in val:
                corrected[field] = "YES"
    
    return corrected, warnings