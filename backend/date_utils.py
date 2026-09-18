"""
Parsing robuste des dates issues de l'OCR.

Les extracteurs produisent des dates dans des formats hétérogènes :
  "10/07/2026"      -> jj/mm/aaaa (le plus fréquent, contexte marocain/européen)
  "28.06.2026"       -> jj.mm.aaaa
  "11.07.2026 T"     -> jj.mm.aaaa avec un caractère parasite
  "06/29/2026"       -> mm/jj/aaaa (erreur OCR ponctuelle, jour 29 impossible en jj/mm... donc mm/jj)

Stratégie : nettoyer la chaîne, puis essayer jour-en-premier, puis
mois-en-premier en secours. Retourne None (plutôt que de planter)
si rien ne fonctionne, pour ne jamais bloquer l'ingestion.
"""
import re
from datetime import date
from typing import Optional

from dateutil import parser as dateutil_parser


def clean_date_string(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = str(raw).strip()
    if s.upper() in ("", "N/A", "NA", "NIL", "NONE", "-"):
        return None
    # retire les lettres parasites collées (ex: "11.07.2026 T")
    s = re.sub(r"[^\d/.\-\s]", "", s).strip()
    return s or None


def parse_date(raw: Optional[str]) -> Optional[date]:
    """Retourne un objet date, ou None si non parsable."""
    s = clean_date_string(raw)
    if not s:
        return None

    for dayfirst in (True, False):
        try:
            dt = dateutil_parser.parse(s, dayfirst=dayfirst, fuzzy=True)
            return dt.date()
        except (ValueError, OverflowError):
            continue

    return None


def months_between(d: date, reference: date) -> float:
    """Nombre approximatif de mois écoulés entre d et reference (reference - d)."""
    return ((reference.year - d.year) * 12 + (reference.month - d.month)
            + (reference.day - d.day) / 30.0)
