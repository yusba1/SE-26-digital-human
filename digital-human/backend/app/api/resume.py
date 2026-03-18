"""简历上传接口"""
from uuid import uuid4

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.services.resume_parser import extract_text_from_pdf
from app.services.resume_store import resume_store

router = APIRouter()

MAX_PDF_SIZE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 8000
ALLOWED_CONTENT_TYPES = {"application/pdf"}


@router.post("/resume/upload")
async def upload_resume(file: UploadFile = File(...)) -> dict:
    if not file:
        raise HTTPException(status_code=400, detail="未上传文件")

    filename = (file.filename or "").lower()
    if file.content_type not in ALLOWED_CONTENT_TYPES and not filename.endswith(".pdf"):
        raise HTTPException(status_code=415, detail="仅支持 PDF 文件")

    try:
        pdf_bytes = await file.read()
    finally:
        await file.close()

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="PDF 文件为空")
    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="PDF 文件过大")

    try:
        resume_text = extract_text_from_pdf(pdf_bytes, max_chars=MAX_TEXT_CHARS)
    except Exception:
        raise HTTPException(status_code=422, detail="PDF 解析失败")
    if not resume_text:
        raise HTTPException(status_code=422, detail="未识别到简历文本")

    resume_id = uuid4().hex
    await resume_store.put(resume_id, resume_text)

    return {
        "resume_id": resume_id,
        "text_length": len(resume_text),
    }
