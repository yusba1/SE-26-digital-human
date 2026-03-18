"""简历 PDF 解析"""
from typing import Optional

import fitz


def extract_text_from_pdf(pdf_bytes: bytes, max_chars: Optional[int] = None) -> str:
    """
    从 PDF 字节流提取文本

    Args:
        pdf_bytes: PDF 文件字节
        max_chars: 可选的最大字符数限制

    Returns:
        提取的文本（已去除首尾空白）
    """
    if not pdf_bytes:
        return ""

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    texts: list[str] = []
    for page in doc:
        page_text = page.get_text("text")
        if page_text:
            texts.append(page_text)
    doc.close()

    full_text = "\n".join(texts).strip()
    if max_chars is not None and len(full_text) > max_chars:
        full_text = full_text[:max_chars].rstrip() + "\n[简历内容过长，已截断]"
    return full_text
