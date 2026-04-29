import io
import os
from enum import Enum
from pathlib import Path

from PIL import Image

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False


class OCREngine(Enum):
    CLOUD_VISION = "cloud_vision"
    TESSERACT = "tesseract"


# Tesseract language pack codes for RTL languages
_TESSERACT_LANG_MAP = {
    "auto": "ara+fas+heb+eng",
    "arabic": "ara",
    "persian": "fas",
    "hebrew": "heb",
    "english": "eng",
}


def _load_images(file_bytes: bytes, filename: str) -> list[Image.Image]:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        if not PDF2IMAGE_AVAILABLE:
            raise RuntimeError("pdf2image が未インストールです。pip install pdf2image でインストールしてください。")
        return convert_from_bytes(file_bytes, dpi=300)
    return [Image.open(io.BytesIO(file_bytes)).convert("RGB")]


def _ocr_tesseract(image: Image.Image, lang: str) -> str:
    if not TESSERACT_AVAILABLE:
        raise RuntimeError("pytesseract が未インストールです。pip install pytesseract でインストールしてください。")
    lang_code = _TESSERACT_LANG_MAP.get(lang, _TESSERACT_LANG_MAP["auto"])
    # OEM 1 = LSTM, PSM 6 = uniform block of text
    config = "--oem 1 --psm 6"
    return pytesseract.image_to_string(image, lang=lang_code, config=config)


def _ocr_cloud_vision(image: Image.Image) -> str:
    from google.cloud import vision  # type: ignore

    client = vision.ImageAnnotatorClient()
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    vision_image = vision.Image(content=buf.getvalue())
    response = client.document_text_detection(image=vision_image)
    if response.error.message:
        raise RuntimeError(f"Cloud Vision APIエラー: {response.error.message}")
    return response.full_text_annotation.text


def extract_text(
    file_bytes: bytes,
    filename: str,
    engine: OCREngine = OCREngine.CLOUD_VISION,
    lang: str = "auto",
) -> tuple[str, list[Image.Image]]:
    """OCRテキストと画像リストを返す。"""
    images = _load_images(file_bytes, filename)
    page_texts = []
    for img in images:
        if engine == OCREngine.CLOUD_VISION:
            page_texts.append(_ocr_cloud_vision(img))
        else:
            page_texts.append(_ocr_tesseract(img, lang))
    combined = "\n\n--- ページ区切り ---\n\n".join(page_texts)
    return combined, images
