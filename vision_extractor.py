"""
視覺擷取器:把 PDF / DOCX / PPTX 的每頁/張投影片轉成圖片
─────────────────────────────────────
用於「視覺增強模式」— 讓 Vision-capable AI(Gemini / Claude / GPT-4o)
直接看文件圖片,擷取流程圖、商業模式畫布、數據圖表等視覺資訊。
"""

import io
from pathlib import Path


def extract_images_from_pdf(file_bytes: bytes, dpi: int = 130,
                             max_pages: int = 20) -> list:
    """把 PDF 每頁轉成 PNG bytes。

    Args:
        file_bytes: PDF 原始 bytes
        dpi: 解析度(預設 130 — 平衡品質與檔案大小)
        max_pages: 最多處理頁數(避免 token 爆量)

    Returns:
        list of (page_num, png_bytes) tuples
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("尚未安裝 PyMuPDF,請執行:pip install PyMuPDF")

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    images = []
    total = len(doc)
    pages_to_extract = min(total, max_pages)

    for i in range(pages_to_extract):
        page = doc[i]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        images.append((i + 1, png_bytes))

    doc.close()
    return images, total


def extract_embedded_images_from_docx(file_bytes: bytes) -> list:
    """從 Word 文件中擷取嵌入的圖片。"""
    import zipfile

    images = []
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as z:
            for name in z.namelist():
                if name.startswith("word/media/") and name.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".gif", ".bmp")
                ):
                    img_data = z.read(name)
                    images.append((len(images) + 1, img_data))
    except Exception:
        pass
    return images, len(images)


def extract_slides_from_pptx(file_bytes: bytes, dpi: int = 130,
                              max_slides: int = 30) -> list:
    """
    把 PPTX 每張投影片轉成圖片。
    需要 LibreOffice 或 Microsoft Office 環境支援。
    若無,則退而求其次:擷取投影片中的嵌入圖片。
    """
    # 嘗試用 LibreOffice 命令列轉檔
    images = _try_libreoffice_convert(file_bytes, dpi, max_slides)
    if images:
        return images, len(images)

    # Fallback: 擷取 pptx 中的嵌入圖片
    import zipfile
    images = []
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as z:
            for name in sorted(z.namelist()):
                if name.startswith("ppt/media/") and name.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".gif", ".bmp")
                ):
                    img_data = z.read(name)
                    images.append((len(images) + 1, img_data))
                    if len(images) >= max_slides:
                        break
    except Exception:
        pass
    return images, len(images)


def _try_libreoffice_convert(file_bytes: bytes, dpi: int, max_slides: int) -> list:
    """嘗試用 LibreOffice 命令列把 PPTX 轉成 PDF 再轉圖片。
    若 LibreOffice 不存在,回傳空 list。"""
    import subprocess
    import tempfile
    import os
    import shutil

    # 找 soffice / libreoffice
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        # Windows 常見路徑
        for p in [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]:
            if os.path.exists(p):
                soffice = p
                break
    if not soffice:
        return []

    with tempfile.TemporaryDirectory() as tmp:
        pptx_path = os.path.join(tmp, "in.pptx")
        with open(pptx_path, "wb") as f:
            f.write(file_bytes)
        try:
            subprocess.run([
                soffice, "--headless", "--convert-to", "pdf",
                "--outdir", tmp, pptx_path,
            ], timeout=60, check=False, capture_output=True)
            pdf_path = os.path.join(tmp, "in.pdf")
            if not os.path.exists(pdf_path):
                return []
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            images, _ = extract_images_from_pdf(pdf_bytes, dpi=dpi, max_pages=max_slides)
            return images
        except Exception:
            return []


def extract_images(file_name: str, file_bytes: bytes,
                    max_items: int = 20) -> tuple:
    """
    依副檔名自動選擇圖片擷取方式。

    Returns: (images_list, total_count, source_type)
      images_list: [(page_num, png/jpg_bytes), ...]
      total_count: 文件總頁數/張數
      source_type: "pdf-pages" / "docx-embedded" / "pptx-slides" / "pptx-embedded"
    """
    ext = Path(file_name).suffix.lower()
    if ext == ".pdf":
        images, total = extract_images_from_pdf(file_bytes, max_pages=max_items)
        return images, total, "pdf-pages"
    elif ext == ".docx":
        images, total = extract_embedded_images_from_docx(file_bytes)
        return images[:max_items], total, "docx-embedded"
    elif ext == ".pptx":
        images, total = extract_slides_from_pptx(file_bytes, max_slides=max_items)
        # 區分:LibreOffice 整張投影片轉圖,或退化的嵌入圖
        source = "pptx-slides" if total > 0 and total == len(images) else "pptx-embedded"
        return images, total, source
    else:
        return [], 0, "none"


def compress_image(image_bytes: bytes, max_dim: int = 1568,
                    quality: int = 85) -> bytes:
    """
    壓縮圖片至合理大小(避免 LLM token 浪費)。
    Claude/Gemini 建議單張圖 ≤ 1568px 邊長,JPEG 品質 85% 已足夠閱讀。
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        # 轉 RGB 模式(JPEG 不支援 RGBA)
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # 縮放
        w, h = img.size
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            new_size = (int(w * ratio), int(h * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception:
        return image_bytes


def estimate_vision_tokens(num_images: int, avg_pixels: int = 1568) -> int:
    """估算視覺輸入的 token 數(粗略)。
    Claude: 每張 ~ 1600 tokens;Gemini: 每張 ~ 1290 tokens;一般 Vision LLM:每張 ~ 1500"""
    return num_images * 1500
