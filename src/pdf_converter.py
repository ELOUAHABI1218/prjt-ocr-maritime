"""
pdf_converter.py - Convertit PDF en images avec pypdfium2

DIAGNOSTIC (2026-08-09) : ajout de la lecture de page.get_rotation()
pour verifier si le PDF source contient une metadonnee de rotation
(/Rotate) que pdfium ignorerait, ou si les pages sont reellement
enregistrees de travers au niveau du contenu lui-meme (auquel cas
aucune correction n'est possible cote conversion - le contenu EST
physiquement tourne dans le fichier).
"""

import os
import pypdfium2 as pdfium

DEFAULT_DPI = 200


def pdf_to_images(pdf_path: str, output_dir: str, dpi: int = DEFAULT_DPI) -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]

    pdf = pdfium.PdfDocument(pdf_path)
    image_paths = []
    scale = dpi / 72.0

    for i, page in enumerate(pdf, start=1):
        # DIAGNOSTIC : verifie si le PDF declare une rotation via /Rotate.
        # pypdfium2 applique deja AUTOMATIQUEMENT cette rotation lors du
        # rendu (page.render() en tient compte nativement) - si cette
        # valeur est 0 alors que l'image sort quand meme de travers,
        # cela confirme que le contenu est physiquement tourne dans le
        # fichier source (scan de travers), pas un probleme de
        # metadonnees ignorees par la conversion.
        rotation_meta = page.get_rotation()
        if rotation_meta != 0:
            print(f"   ℹ️  Page {i} : rotation /Rotate={rotation_meta}° declaree dans le PDF "
                  f"(deja appliquee automatiquement par pdfium)")

        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
        out_path = os.path.join(output_dir, f"{base_name}_page_{i}.png")
        pil_image.save(out_path, "PNG")
        image_paths.append(out_path)

    return image_paths


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 pdf_converter.py <chemin_pdf> [dossier_sortie]")
        sys.exit(1)
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "output/pages"
    paths = pdf_to_images(sys.argv[1], out_dir)
    print(f"{len(paths)} page(s) converties")