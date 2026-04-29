from PIL import Image, ImageEnhance, ImageFilter


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """コントラスト強調・シャープ処理でOCR精度を向上させる。"""
    gray = image.convert("L")
    gray = ImageEnhance.Contrast(gray).enhance(2.0)
    gray = gray.filter(ImageFilter.SHARPEN)
    return gray.convert("RGB")
