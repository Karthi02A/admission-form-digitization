import uuid
import mimetypes
import logging
from time import perf_counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.config.settings import ALLOWED, ALIASES, MAX_BYTES, MAX_FILES, MAX_PAGES, FILES
from app.services import store
import pymupdf
from PIL import Image
from app.services.extraction import extract_document_with_ai
from app.config.ai_settings import load_ai_settings
from app.services.exports import excel_bytes, csv_bytes

router = APIRouter()
logger = logging.getLogger(__name__)
CERTIFICATE_FIELDS = {"Transfer Certificate", "Mark Sheets", "Community Certificate", "Income Certificate"}


def now():
    return datetime.now(timezone.utc).isoformat()


def find(batch_id, doc_id):
    b = store.get(batch_id)
    if not b:
        raise HTTPException(404, "Batch not found")
    for d in b["documents"]:
        if d["document_id"] == doc_id:
            return b, d
    raise HTTPException(404, "Document not found")


def public_document(document_data):
    return {key: value for key, value in document_data.items() if key != "extracted_text"}




def already_extracted_with_current_model(document_data):
    """Skip only when saved results were produced by the currently selected model."""
    if document_data.get("status") not in {"extracted", "review_required", "reviewed"}:
        return False
    metrics = document_data.get("extraction_metrics") or {}
    try:
        current = load_ai_settings()
    except Exception:
        return False
    return metrics.get("provider") == current.provider and metrics.get("model") == current.model


def empty_fields():
    return {field: "" for field in ALIASES}


def validate_original_file(path: Path) -> None:
    """Validate file structure only; this does not run OCR or a vision model."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            with pymupdf.open(path) as pdf:
                if pdf.is_encrypted:
                    raise ValueError("Password-protected PDFs are not supported")
                if len(pdf) < 1:
                    raise ValueError("The PDF contains no pages")
                if len(pdf) > MAX_PAGES:
                    raise ValueError(f"PDF exceeds the {MAX_PAGES}-page limit")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("The uploaded PDF is invalid or cannot be opened") from exc
        return
    if suffix in {".jpg", ".jpeg", ".png"}:
        try:
            with Image.open(path) as image:
                image.verify()
        except Exception as exc:
            raise ValueError("The uploaded image is invalid or cannot be opened") from exc
        return
    raise ValueError("Only PDF, JPG, JPEG and PNG files are accepted")


def missing_fields(fields):
    # '-' means the certificate checkbox was not selected; that is a known value.
    return [key for key, value in fields.items() if not str(value or "").strip() or (str(value).strip() == "-" and key not in CERTIFICATE_FIELDS)]


class FieldValue(BaseModel):
    value: str = Field(max_length=5000)


@router.get("/api/batches")
def batches():
    return {"batches": store.listing()}


@router.post("/api/batches")
def create_batch():
    b = {"batch_id": uuid.uuid4().hex, "created_at": now(), "updated_at": now(), "status": "created", "documents": []}
    store.save(b)
    return b


def batch_progress(batch):
    docs = batch.get("documents", [])
    total = len(docs)
    completed_statuses = {"extracted", "review_required", "reviewed", "failed", "needs_template_review"}
    completed = sum(d.get("status") in completed_statuses for d in docs)
    succeeded = sum(d.get("status") in {"extracted", "review_required", "reviewed"} for d in docs)
    failed = sum(d.get("status") == "failed" for d in docs)
    needs_template_review = sum(d.get("status") == "needs_template_review" for d in docs)
    processing = sum(d.get("status") == "processing" for d in docs)
    current = next((d.get("document_id") for d in docs if d.get("status") == "processing"), None)
    return {
        "total": total,
        "completed": completed,
        "succeeded": succeeded,
        "failed": failed,
        "needs_template_review": needs_template_review,
        "processing": processing,
        "current_document_id": current,
        "percent": round((completed / total) * 100) if total else 100,
    }


@router.get("/api/batches/{batch_id}")
def get_batch(batch_id: str):
    b = store.get(batch_id)
    if not b:
        raise HTTPException(404, "Batch not found")
    return {**b, "processing_progress": batch_progress(b), "documents": [public_document(d) for d in b["documents"]]}


@router.post("/api/batches/{batch_id}/upload")
async def upload(batch_id: str, files: Annotated[list[UploadFile], File(...)], extract_now: bool = Query(default=False, alias="extract")):
    b = store.get(batch_id)
    if not b:
        raise HTTPException(404, "Batch not found")
    if not files:
        raise HTTPException(400, "Select at least one file")
    if len(b["documents"]) + len(files) > MAX_FILES:
        raise HTTPException(400, f"Batch limit is {MAX_FILES} documents")
    results = []
    for f in files:
        name = Path(f.filename or "upload").name
        ext = Path(name).suffix.lower()
        did = uuid.uuid4().hex
        target = FILES / f"{did}{ext}"
        try:
            if ext not in ALLOWED:
                raise ValueError("Only PDF, JPG, JPEG and PNG files are accepted")
            data = await f.read(MAX_BYTES + 1)
            if not data:
                raise ValueError("File is empty")
            if len(data) > MAX_BYTES:
                raise ValueError(f"File exceeds {MAX_BYTES // (1024 * 1024)} MB")
            target.write_bytes(data)
            validate_original_file(target)
            fields = empty_fields()
            quality = {"total_fields": len(fields), "filled_fields": 0, "missing_fields": list(fields), "review_required": True}
            d = {
                "document_id": did,
                "original_filename": name,
                "stored_filename": target.name,
                "content_type": mimetypes.guess_type(target.name)[0] or "application/octet-stream",
                "created_at": now(),
                "status": "uploaded",
                "extraction_method": None,
                "extracted_text": "",
                "fields": fields,
                "quality": quality,
            }
            b["documents"].append(d)
            results.append({"document_id": did, "filename": name, "status": d["status"], "extraction_method": None, "quality": quality})
        except Exception as e:
            if target.exists():
                target.unlink()
            results.append({"filename": name, "status": "failed", "error": str(e)})
        finally:
            await f.close()
    b["updated_at"] = now()
    b["status"] = "ready_for_review" if b["documents"] else "empty"
    store.save(b)
    return {"batch_id": batch_id, "status": b["status"], "results": results, "documents": [public_document(d) for d in b["documents"]]}


@router.get("/api/batches/{batch_id}/documents/{doc_id}")
def document(batch_id: str, doc_id: str):
    _, d = find(batch_id, doc_id)
    return public_document(d)


def process_batch_extraction(batch_id: str) -> None:
    """Extract every uploaded document sequentially and persist progress after each one."""
    batch = store.get(batch_id)
    if not batch:
        return
    batch["status"] = "processing"
    batch["updated_at"] = now()
    for document_data in batch.get("documents", []):
        if already_extracted_with_current_model(document_data):
            continue
        document_data["status"] = "processing"
        document_data["error"] = None
        document_data["updated_at"] = now()
        batch["updated_at"] = now()
        store.save(batch)
        path = (FILES / document_data.get("stored_filename", "")).resolve()
        started = perf_counter()
        try:
            if path.parent != FILES.resolve() or not path.is_file():
                raise FileNotFoundError("Original file not found")
            fields, quality, metrics = extract_document_with_ai(path)
            metrics["request_total_ms"] = round((perf_counter() - started) * 1000)
            document_data.update({
                "fields": fields,
                "quality": quality,
                "extraction_method": f"{metrics.get('provider', 'ai')}_vision_api",
                "extraction_metrics": metrics,
                "status": "review_required" if quality.get("review_required") else "extracted",
                "error": None,
                "updated_at": now(),
            })
        except Exception as error:
            logger.exception("AI extraction failed: batch_id=%s document_id=%s", batch_id, document_data.get("document_id"))
            document_data.update({"status": "failed", "error": str(error), "updated_at": now()})
        batch["updated_at"] = now()
        store.save(batch)
    statuses = [d.get("status") for d in batch.get("documents", [])]
    batch["status"] = "completed_with_errors" if any(status == "failed" for status in statuses) else "completed"
    batch["updated_at"] = now()
    store.save(batch)


@router.post("/api/batches/{batch_id}/extract", status_code=202)
def extract_batch(batch_id: str, background_tasks: BackgroundTasks):
    batch = store.get(batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    if not batch.get("documents"):
        raise HTTPException(400, "Upload at least one valid document before extraction")
    # A second request can arrive before the background task starts. Treat
    # both queued and processing as active so the same batch is not enqueued twice.
    if batch.get("status") in {"queued", "processing"}:
        return {"batch_id": batch_id, "status": batch.get("status"), "processing_progress": batch_progress(batch)}
    batch["status"] = "queued"
    for document_data in batch["documents"]:
        if document_data.get("status") not in {"extracted", "review_required", "reviewed"}:
            document_data["status"] = "queued"
    batch["updated_at"] = now()
    store.save(batch)
    background_tasks.add_task(process_batch_extraction, batch_id)
    return {"batch_id": batch_id, "status": "queued", "processing_progress": batch_progress(batch)}


@router.post("/api/batches/{batch_id}/documents/{doc_id}/extract")
def extract_document(batch_id: str, doc_id: str):
    batch, document_data = find(batch_id, doc_id)
    path = (FILES / document_data.get("stored_filename", "")).resolve()
    if path.parent != FILES.resolve() or not path.is_file():
        raise HTTPException(404, "Original file not found")
    if already_extracted_with_current_model(document_data):
        return public_document(document_data)
    started = perf_counter()
    try:
        fields, quality, metrics = extract_document_with_ai(path)
        metrics["request_total_ms"] = round((perf_counter() - started) * 1000)
        document_data.update({"fields": fields, "quality": quality, "extraction_method": f"{metrics.get('provider', 'ai')}_vision_api", "extraction_metrics": metrics, "status": "review_required" if quality["review_required"] else "extracted", "error": None, "updated_at": now()})
    except Exception as error:
        logger.exception("AI extraction failed: batch_id=%s document_id=%s", batch_id, doc_id)
        document_data.update({"status": "failed", "error": str(error), "updated_at": now()})
    batch["updated_at"] = now()
    # Preserve batch-level processing state if a background batch is running.
    if batch.get("status") not in {"queued", "processing"}:
        statuses = [item.get("status") for item in batch.get("documents", [])]
        batch["status"] = "completed_with_errors" if any(s == "failed" for s in statuses) else "completed"
    store.save(batch)
    return public_document(document_data)


@router.get("/api/batches/{batch_id}/documents/{doc_id}/file")
def preview(batch_id: str, doc_id: str):
    _, d = find(batch_id, doc_id)
    p = (FILES / d["stored_filename"]).resolve()
    if p.parent != FILES.resolve() or not p.is_file():
        raise HTTPException(404, "Original file not found")
    return FileResponse(p, media_type=d["content_type"], filename=d["original_filename"], content_disposition_type="inline")


@router.patch("/api/batches/{batch_id}/documents/{doc_id}/fields/{field_name}")
def update_field(batch_id: str, doc_id: str, field_name: str, payload: FieldValue):
    b, d = find(batch_id, doc_id)
    if field_name not in d["fields"]:
        raise HTTPException(404, "Unknown field")
    d["fields"][field_name] = payload.value.strip()
    missing = missing_fields(d["fields"])
    d["quality"] = {"total_fields": len(d["fields"]), "filled_fields": len(d["fields"]) - len(missing), "missing_fields": missing, "review_required": bool(missing)}
    d["status"] = "review_required" if missing else "reviewed"
    d["updated_at"] = now()
    b["updated_at"] = now()
    store.save(b)
    return {"status": "saved", "field": field_name, "value": d["fields"][field_name], "quality": d["quality"]}


@router.get("/api/batches/{batch_id}/export.xlsx")
def export_xlsx(batch_id: str):
    b = store.get(batch_id)
    if not b:
        raise HTTPException(404, "Batch not found")
    return Response(excel_bytes(b), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="admission-{batch_id}.xlsx"'})


@router.get("/api/batches/{batch_id}/export.csv")
def export_csv(batch_id: str):
    b = store.get(batch_id)
    if not b:
        raise HTTPException(404, "Batch not found")
    return Response(csv_bytes(b), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="admission-{batch_id}.csv"'})


@router.delete("/api/batches/{batch_id}")
def delete_batch(batch_id: str):
    b = store.get(batch_id)
    if not b:
        raise HTTPException(404, "Batch not found")
    for d in b["documents"]:
        p = (FILES / d.get("stored_filename", "")).resolve()
        if p.parent == FILES.resolve() and p.is_file():
            p.unlink()
    store.delete(batch_id)
    return {"message": "Batch and its documents deleted", "batch_id": batch_id}
