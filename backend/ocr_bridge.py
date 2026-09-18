"""
Pont entre l'upload PDF (api.py) et ton pipeline OCR réel :
    main_dgd.py -> process_dgd_pdf(pdf_path, output_dir) -> dict
    main_dgm.py -> process_dgm_pdf(pdf_path, output_dir) -> dict
    main.py     -> process_pdf(pdf_path, output_dir, document_type="Health") -> dict

Ces trois fonctions retournent déjà exactement le format JSON attendu
(document_type / source_file / extracted_at / fields / validation_warnings),
donc ce pont se contente de les localiser, les appeler, et renvoyer leur
résultat tel quel — pas de transformation supplémentaire nécessaire.

Localisation automatique : ces fichiers font `sys.path.append` en se
basant sur LEUR PROPRE emplacement (deux dossiers au-dessus d'eux-mêmes),
donc ce pont les recherche par nom dans tout le projet plutôt que
d'imposer un chemin fixe. Si l'import échoue avec une erreur du type
"No module named 'src'", c'est très probablement parce que ces fichiers
main_*.py ne sont pas positionnés exactement là où ils s'attendent à
être (voir le message d'erreur détaillé plus bas).
"""
import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # dossier contenant backend/, src/, output/...

# Dossiers à ignorer pendant la recherche (gros, lents, non pertinents).
_SKIP_DIR_NAMES = {"node_modules", "venv", ".venv", "rapidocr_env", "__pycache__", ".git", "dist"}

_module_cache: dict[str, object] = {}


class OcrPipelineNotConnected(Exception):
    """Levée si un fichier main_*.py est introuvable ou ne peut pas être importé."""


def _find_file(filename: str) -> Path | None:
    for path in PROJECT_ROOT.rglob(filename):
        if not any(part in _SKIP_DIR_NAMES for part in path.parts):
            return path
    return None


def _load_module(filename: str):
    """Charge un fichier main_*.py par son chemin réel (importlib), avec cache par processus."""
    if filename in _module_cache:
        return _module_cache[filename]

    file_path = _find_file(filename)
    if file_path is None:
        raise OcrPipelineNotConnected(
            f"'{filename}' introuvable dans le projet (recherché sous {PROJECT_ROOT}). "
            f"Vérifie qu'il existe bien et n'est pas dans un dossier ignoré "
            f"({', '.join(_SKIP_DIR_NAMES)})."
        )

    spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
    module = importlib.util.module_from_spec(spec)

    # Tes fichiers dans src/ mélangent deux styles d'import : "from src.x import"
    # (résolu via sys.path.append fait par main_dgd.py lui-même, PROJECT_ROOT)
    # et "from field_extractor import" — SANS "src." — à l'intérieur de fichiers
    # comme dgd_extractor.py, qui suppose que src/ LUI-MÊME est sur sys.path.
    # C'est automatique quand on lance `python main_dgd.py` directement (Python
    # ajoute le dossier du script), mais pas via importlib — on l'ajoute donc
    # explicitement ici pour couvrir les deux styles.
    src_dir = str(file_path.parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:
        missing = str(exc).split("'")[1] if "'" in str(exc) else str(exc)
        if missing == "src" or missing.startswith("src."):
            raise OcrPipelineNotConnected(
                f"Échec de l'import de '{filename}' (trouvé à {file_path}) : {exc}. "
                f"Ce fichier fait `sys.path.append` en supposant être situé exactement "
                f"2 dossiers en dessous de la racine du projet (celle qui contient src/). "
                f"Vérifie sa position réelle : actuellement à "
                f"{file_path.relative_to(PROJECT_ROOT)}, il doit être dans un SOUS-DOSSIER "
                f"de la racine (ex: {PROJECT_ROOT.name}/scripts/{filename}), pas directement "
                f"à la racine à côté de src/."
            ) from exc
        raise OcrPipelineNotConnected(
            f"Échec de l'import de '{filename}' (trouvé à {file_path}) : dépendance manquante "
            f"'{missing}'. Le pipeline OCR a besoin de librairies (opencv, paddleocr, etc.) qui "
            f"ne sont probablement installées que dans ton environnement OCR dédié "
            f"(ex: rapidocr_env), pas dans celui où tourne cette API. Lance uvicorn depuis "
            f"l'environnement qui contient déjà ces dépendances, ou installe '{missing}' "
            f"dans l'environnement actuel."
        ) from exc

    _module_cache[filename] = module
    return module


def detect_document_type(original_filename: str) -> str:
    name = Path(original_filename).stem.upper()
    if "DGD" in name:
        return "DGD"
    if "DGM" in name:
        return "DGM"
    if "HEALTH" in name:
        return "HEALTH"
    raise OcrPipelineNotConnected(
        f"Impossible de déterminer le type de document pour '{original_filename}'. "
        "Choisis un type dans le menu déroulant de l'interface plutôt que "
        "'Détection automatique'."
    )


def run_ocr_pipeline(pdf_path: Path, original_filename: str, document_type_hint: str | None = None) -> dict:
    doc_type = (document_type_hint or detect_document_type(original_filename)).upper()
    output_dir = str(PROJECT_ROOT / "output")

    if doc_type == "DGD":
        module = _load_module("main_dgd.py")
        return module.process_dgd_pdf(str(pdf_path), output_dir)

    if doc_type == "DGM":
        module = _load_module("main_dgm.py")
        return module.process_dgm_pdf(str(pdf_path), output_dir)

    if doc_type == "HEALTH":
        module = _load_module("main.py")
        return module.process_pdf(str(pdf_path), output_dir, document_type="Health")

    raise OcrPipelineNotConnected(f"Type de document non géré par le pont OCR : '{doc_type}'")
