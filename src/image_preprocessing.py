"""
image_preprocessing.py - Pretraitement pour l'OCR
"""

import cv2
import numpy as np


def enhance_for_ocr(gray: np.ndarray, upscale_factor: float = 1.5) -> np.ndarray:
    """
    Pipeline de rattrapage pour images degradees (flou, bruit, faible
    contraste, compression agressive) - observe sur des fichiers ou l'OCR
    produit du texte incoherent/repetitif ("CRRRRRAR", "GRRRRAAR")
    caracteristique d'une image trop degradee pour le reseau de
    detection/reconnaissance.
    """
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    contrasted = clahe.apply(denoised)

    blurred = cv2.GaussianBlur(contrasted, (0, 0), sigmaX=3)
    sharpened = cv2.addWeighted(contrasted, 1.5, blurred, -0.5, 0)

    if upscale_factor and upscale_factor != 1.0:
        h, w = sharpened.shape
        sharpened = cv2.resize(
            sharpened, (int(w * upscale_factor), int(h * upscale_factor)),
            interpolation=cv2.INTER_CUBIC,
        )

    return sharpened


def estimate_image_quality(gray: np.ndarray) -> dict:
    """
    Estime rapidement la qualite d'une image (nettete via variance du
    Laplacien, contraste via ecart-type des niveaux de gris).
    """
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    contrast_std = float(gray.std())
    return {"sharpness": laplacian_var, "contrast": contrast_std}


def preprocess(image_path: str, do_deskew: bool = True, do_binarize: bool = False,
                do_enhance: bool = False) -> np.ndarray:
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Image introuvable : {image_path}")

    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    if do_deskew:
        coords = np.column_stack(np.where(gray < 200))
        if len(coords) > 0:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            if abs(angle) > 0.5:
                (h, w) = gray.shape
                center = (w // 2, h // 2)
                matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

                cos = abs(matrix[0, 0])
                sin = abs(matrix[0, 1])
                new_w = int((h * sin) + (w * cos))
                new_h = int((h * cos) + (w * sin))

                matrix[0, 2] += (new_w / 2) - center[0]
                matrix[1, 2] += (new_h / 2) - center[1]

                gray = cv2.warpAffine(
                    gray, matrix, (new_w, new_h),
                    flags=cv2.INTER_CUBIC,
                    borderValue=255,
                )

    if do_enhance:
        gray = enhance_for_ocr(gray)

    if do_binarize:
        gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)

    return gray