"""
FastAPI 后端入口（RAG API）

启动示例（开发）：
  cd 1
  py -3.11 -m uvicorn api_app:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import os
import re
import time
import uuid
import logging
from functools import lru_cache
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import config_data as config
from file_history_store import ChatHistoryStore
from knowledge_base import KnowledgeBaseService, extract_text
from rag import RAGService


logger = logging.getLogger("rag_api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"  # type: ignore[attr-defined]
        return True


logging.getLogger().addFilter(_RequestIdFilter())


@lru_cache(maxsize=1)
def get_kb_service() -> KnowledgeBaseService:
    return KnowledgeBaseService()


@lru_cache(maxsize=1)
def get_rag_service() -> RAGService:
    return RAGService()


def _safe_session_id(session_id: str) -> str:
    session_id = session_id.strip()
    if not session_id:
        raise ValueError("session_id 不能为空")
    # 只允许字母数字下划线横线，避免路径穿越
    session_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    return session_id[:64]


def get_history_store(session_id: str) -> ChatHistoryStore:
    safe_id = _safe_session_id(session_id)
    base_dir = os.path.dirname(config.chat_history_path) or "."
    os.makedirs(base_dir, exist_ok=True)
    filename = f"chat_history_{safe_id}.json"
    path = os.path.join(base_dir, filename)
    return ChatHistoryStore(path=path)


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """
    最小可用鉴权：当环境变量 API_KEY 设置时，要求请求头 X-API-Key 匹配。
    未设置 API_KEY 时，默认放行（便于本地开发）。
    """

    expected = os.getenv("API_KEY", "").strip()
    if not expected:
        return
    if not x_api_key or x_api_key.strip() != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


app = FastAPI(title="RAG API", version="0.1.0")


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    start = time.time()

    # 让 logging format 里能打印 request_id
    extra = {"request_id": request_id}
    request.state.request_id = request_id

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled error", extra=extra)
        raise
    finally:
        elapsed_ms = int((time.time() - start) * 1000)
        logger.info(
            "%s %s %s %dms",
            request.method,
            request.url.path,
            response.status_code if "response" in locals() else 500,
            elapsed_ms,
            extra=extra,
        )

    response.headers["X-Request-Id"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def _doc_to_json(doc: Any) -> dict:
    # 兼容 langchain Document
    return {
        "page_content": getattr(doc, "page_content", ""),
        "metadata": getattr(doc, "metadata", {}) or {},
    }


class UploadItemResult(BaseModel):
    filename: str
    status: str
    message: str


class UploadResponse(BaseModel):
    results: list[UploadItemResult]


class DocumentsResponse(BaseModel):
    documents: list[dict]


class DeleteResponse(BaseModel):
    deleted: int


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="用于隔离历史的会话 ID")
    question: str = Field(..., min_length=1, description="用户问题")


class Citation(BaseModel):
    source: str | None = None
    page_content: str
    metadata: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post(
    "/api/documents/upload",
    response_model=UploadResponse,
    dependencies=[Depends(verify_api_key)],
)
async def upload_documents(
    files: list[UploadFile] = File(...),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
):
    max_files = int(os.getenv("MAX_UPLOAD_FILES", "10"))
    max_mb = int(os.getenv("MAX_UPLOAD_MB", "20"))
    allowed_ext = {".txt", ".md", ".pdf", ".docx"}

    if len(files) > max_files:
        raise HTTPException(status_code=400, detail=f"最多一次上传 {max_files} 个文件")

    results: list[UploadItemResult] = []
    for f in files:
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in allowed_ext:
            results.append(
                UploadItemResult(
                    filename=f.filename,
                    status="error",
                    message=f"不支持的文件类型: {ext}",
                )
            )
            continue

        try:
            t0 = time.time()
            file_bytes = await f.read()
            if len(file_bytes) > max_mb * 1024 * 1024:
                results.append(
                    UploadItemResult(
                        filename=f.filename,
                        status="error",
                        message=f"文件过大（>{max_mb}MB）",
                    )
                )
                continue
            text = extract_text(file_bytes, f.filename)
            msg = kb_service.upload_by_str(text, f.filename)
            status = "ok" if msg.startswith("[成功]") else "skip" if msg.startswith("[跳过]") else "other"
            results.append(UploadItemResult(filename=f.filename, status=status, message=msg))
            logger.info(
                "upload filename=%s bytes=%d elapsed_ms=%d status=%s",
                f.filename,
                len(file_bytes),
                int((time.time() - t0) * 1000),
                status,
                extra={"request_id": "-"},
            )
        except Exception as e:
            logger.exception("upload failed filename=%s", f.filename, extra={"request_id": "-"})
            results.append(
                UploadItemResult(
                    filename=f.filename,
                    status="error",
                    message="处理失败（请检查文件内容/格式）",
                )
            )
    return UploadResponse(results=results)


@app.get(
    "/api/documents",
    response_model=DocumentsResponse,
    dependencies=[Depends(verify_api_key)],
)
def list_documents(kb_service: KnowledgeBaseService = Depends(get_kb_service)):
    return DocumentsResponse(documents=kb_service.list_documents())


@app.delete(
    "/api/documents/{doc_id}",
    response_model=DeleteResponse,
    dependencies=[Depends(verify_api_key)],
)
def delete_document(doc_id: str, kb_service: KnowledgeBaseService = Depends(get_kb_service)):
    deleted = kb_service.delete_document(doc_id)
    return DeleteResponse(deleted=deleted)


@app.post(
    "/api/chat",
    response_model=ChatResponse,
    dependencies=[Depends(verify_api_key)],
)
def chat(
    payload: ChatRequest,
    rag_service: RAGService = Depends(get_rag_service),
):
    store = get_history_store(payload.session_id)
    history = store.load()
    t0 = time.time()
    answer, docs = rag_service.chat(payload.question, history=history)
    elapsed_ms = int((time.time() - t0) * 1000)
    logger.info(
        "chat session_id=%s elapsed_ms=%d citations=%d",
        payload.session_id,
        elapsed_ms,
        len(docs or []),
        extra={"request_id": "-"},
    )

    # 追加历史并裁剪
    history.append({"role": "user", "content": payload.question})
    history.append({"role": "assistant", "content": answer})
    history = ChatHistoryStore.trim(history, config.max_history_rounds)
    store.save(history)

    citations: list[Citation] = []
    for doc in docs or []:
        meta = getattr(doc, "metadata", {}) or {}
        citations.append(
            Citation(
                source=meta.get("source"),
                page_content=getattr(doc, "page_content", ""),
                metadata=meta,
            )
        )

    return ChatResponse(answer=answer, citations=citations)

