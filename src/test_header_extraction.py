# test_header_extraction.py
import re

header_text = """
Submitted at the port of  
TANGER MED  
Date  
10/07/2026  

Name of Ship or inland navigation vessel  
LONDON EXPRESS  
IMO Number  
9143568  

Arriving from (Last port) *  
LIVORNO, ITALY  
Sailing to (Next port)  
NEW YORK, USA  

Nationality / Flag of vessel  
BERMUDA  
Master's Name  
CAPT. CHERNIKOV, SERGII  

International Gross Tonnage (GT)  
53523  
International Net Tonnage (NT)  
47328  

Has ship / inland navigation vessel visited an affected area identified by World Health Organization?  
NO  

Port and date of visit (affected area)  
NA  

Number of crew members on board**  
31  
Number of passenger on board**  
0
"""

class HeaderExtractor:
    def extract(self, text: str) -> dict:
        clean = re.sub(r'\s+', ' ', text)
        data = {}
        
        m = re.search(r'Submitted at the port of\s+([A-Za-z\s,]+?)(?=\s+Date)', clean, re.IGNORECASE)
        data['submitted_port'] = m.group(1).strip() if m else None
        
        m = re.search(r'Date\s+(\d{2}/\d{2}/\d{4})', clean, re.IGNORECASE)
        data['submission_date'] = m.group(1) if m else None
        
        m = re.search(r'Name of Ship\s+or inland navigation vessel\s+([A-Za-z\s]+?)(?=\s+IMO)', clean, re.IGNORECASE)
        if not m:
            m = re.search(r'Name of Ship\s+([A-Za-z\s]+?)(?=\s+IMO)', clean, re.IGNORECASE)
        data['ship_name'] = m.group(1).strip() if m else None
        
        m = re.search(r'IMO Number\s+(\d{7})', clean, re.IGNORECASE)
        data['imo_number'] = m.group(1) if m else None
        
        m = re.search(r'Arriving from\s*\(Last port\)\s*\*?\s*([A-Za-z\s,]+?)(?=\s+Sailing)', clean, re.IGNORECASE)
        if not m:
            m = re.search(r'Arriving from\s+([A-Za-z\s,]+?)(?=\s+Sailing)', clean, re.IGNORECASE)
        data['last_port'] = m.group(1).strip() if m else None
        
        m = re.search(r'Sailing to\s*\(Next port\)\s*\*?\s*([A-Za-z\s,]+?)(?=\s+Nationality)', clean, re.IGNORECASE)
        if not m:
            m = re.search(r'Sailing to\s+([A-Za-z\s,]+?)(?=\s+Nationality)', clean, re.IGNORECASE)
        data['next_port'] = m.group(1).strip() if m else None
        
        m = re.search(r'Nationality / Flag of vessel\s+([A-Za-z\s]+?)(?=\s+Master)', clean, re.IGNORECASE)
        data['nationality'] = m.group(1).strip() if m else None
        
        m = re.search(r"Master['']s Name\s+([A-Za-z.,\s]+?)(?=\s+International)", clean, re.IGNORECASE)
        data['master_name'] = m.group(1).strip() if m else None
        
        m = re.search(r'Gross Tonnage\s*\(GT\)\s*(\d+)', clean, re.IGNORECASE)
        if not m:
            m = re.search(r'Gross Tonnage\s+(\d+)', clean, re.IGNORECASE)
        data['gross_tonnage'] = int(m.group(1)) if m else None
        
        m = re.search(r'Net Tonnage\s*\(NT\)\s*(\d+)', clean, re.IGNORECASE)
        if not m:
            m = re.search(r'Net Tonnage\s+(\d+)', clean, re.IGNORECASE)
        data['net_tonnage'] = int(m.group(1)) if m else None
        
        m = re.search(r'World Health Organization\?\s*([A-Z]+)', clean, re.IGNORECASE)
        data['who_affected_area'] = m.group(1) if m else None
        
        # CORRECTION : capture des nombres avec **
        m = re.search(r'crew members\s*on board\s*\*{0,2}\s*(\d+)', clean, re.IGNORECASE)
        if not m:
            m = re.search(r'crew members\s+(\d+)', clean, re.IGNORECASE)
        data['crew_members'] = int(m.group(1)) if m else None
        
        m = re.search(r'passenger\s*on board\s*\*{0,2}\s*(\d+)', clean, re.IGNORECASE)
        if not m:
            m = re.search(r'passenger\s+(\d+)', clean, re.IGNORECASE)
        data['passengers'] = int(m.group(1)) if m else None
        
        return data

if __name__ == "__main__":
    extractor = HeaderExtractor()
    result = extractor.extract(header_text)
    
    print("=" * 60)
    print("RÉSULTAT DE L'EXTRACTION DE L'EN-TÊTE")
    print("=" * 60)
    for key, value in result.items():
        print(f"{key:25} : {value}")