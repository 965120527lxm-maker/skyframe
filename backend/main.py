"""
SkyFrame Backend v2 — Upload + AI Enhancement + Download

New in v2:
  POST /api/jobs/create           → Start AI enhancement
  GET  /api/jobs/{id}             → Job status + progress
  GET  /api/jobs/{id}/download    → Download enhanced video
  GET  /api/uploads/{id}/jobs     → List jobs for an upload
"""

import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from fastapi.staticfiles import StaticFiles
from pathlib import Path

from pydantic import BaseModel

import config
import database as db
import storage
from enhance import create_enhance_job, EnhanceError

# ═══════════════════════════════════════════════════════
# App
# ═══════════════════════════════════════════════════════
app = FastAPI(title="SkyFrame API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.on_event("startup")
async def startup():
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    await db.init_db()
    has_token = "✅" if config.REPLICATE_API_TOKEN else "❌ (set REPLICATE_API_TOKEN)"
    print(f"✦ SkyFrame API v0.2 — Replicate: {has_token}")


# ═══════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════
class InitUploadRequest(BaseModel):
    filename: str
    mimeType: str
    fileSize: int

class InitUploadResponse(BaseModel):
    uploadId: str
    storageKey: str
    status: str

class CompleteUploadResponse(BaseModel):
    id: str
    status: str
    filename: str
    downloadReady: bool

class UploadDetail(BaseModel):
    id: str
    filename: str
    fileSize: int
    mimeType: str
    status: str
    durationSec: float | None = None
    resolution: str | None = None
    createdAt: str

class CreateJobRequest(BaseModel):
    uploadId: str
    model: str | None = None  # "upscale" or "upscale_premium"

class JobDetail(BaseModel):
    id: str
    uploadId: str
    modelName: str
    status: str  # pending | processing | completed | failed
    progress: float
    errorMessage: str | None = None
    createdAt: str
    completedAt: str | None = None
    downloadReady: bool


# ═══════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════
def _validate_file_meta(filename: str, mime_type: str, file_size: int):
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported format. Allowed: {config.ALLOWED_EXTENSIONS}")
    if mime_type not in config.ALLOWED_MIME_TYPES:
        raise HTTPException(400, f"Unsupported MIME type. Allowed: {config.ALLOWED_MIME_TYPES}")
    if file_size > config.MAX_FILE_SIZE:
        raise HTTPException(400, f"File too large. Max {config.MAX_FILE_SIZE // (1024*1024)}MB")


def _job_to_detail(j: dict) -> JobDetail:
    return JobDetail(
        id=j["id"],
        uploadId=j["upload_id"],
        modelName=j["model_name"],
        status=j["status"],
        progress=j.get("progress") or 0,
        errorMessage=j.get("error_message"),
        createdAt=j["created_at"],
        completedAt=j.get("completed_at"),
        downloadReady=j["status"] == "completed" and bool(j.get("output_key")),
    )


def _upload_to_detail(r: dict) -> UploadDetail:
    return UploadDetail(
        id=r["id"],
        filename=r["original_filename"],
        fileSize=r["file_size"],
        mimeType=r["mime_type"],
        status=r["status"],
        durationSec=r.get("duration_sec"),
        resolution=r.get("resolution"),
        createdAt=r["created_at"],
    )


# ═══════════════════════════════════════════════════════
# Upload Routes (same as v1)
# ═══════════════════════════════════════════════════════

@app.post("/api/uploads/init", response_model=InitUploadResponse)
async def init_upload(body: InitUploadRequest):
    _validate_file_meta(body.filename, body.mimeType, body.fileSize)
    upload_id = "upl_" + uuid.uuid4().hex[:12]
    storage_key = storage.generate_storage_key(upload_id, body.filename)
    now = datetime.now(timezone.utc).isoformat()
    await db.insert_upload({
        "id": upload_id, "user_id": None,
        "original_filename": body.filename,
        "storage_key": storage_key,
        "mime_type": body.mimeType,
        "file_size": body.fileSize,
        "status": "uploading",
        "created_at": now,
    })
    return InitUploadResponse(uploadId=upload_id, storageKey=storage_key, status="uploading")


@app.put("/api/uploads/{upload_id}/file")
async def upload_file(upload_id: str, file: UploadFile = File(...)):
    record = await db.get_upload(upload_id)
    if not record:
        raise HTTPException(404, "Upload not found")
    if record["status"] not in ("uploading",):
        raise HTTPException(400, "Upload already completed or failed")
    try:
        bytes_written = await storage.save_file(record["storage_key"], file)
        await db.update_upload(upload_id, {
            "file_size": bytes_written,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"uploadId": upload_id, "bytesWritten": bytes_written}
    except Exception as e:
        await db.update_upload(upload_id, {"status": "failed"})
        raise HTTPException(500, f"Upload failed: {str(e)}")


@app.post("/api/uploads/{upload_id}/complete", response_model=CompleteUploadResponse)
async def complete_upload(upload_id: str):
    record = await db.get_upload(upload_id)
    if not record:
        raise HTTPException(404, "Upload not found")
    if not storage.file_exists(record["storage_key"]):
        await db.update_upload(upload_id, {"status": "failed"})
        raise HTTPException(400, "File not found in storage")
    await db.update_upload(upload_id, {
        "status": "uploaded",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return CompleteUploadResponse(
        id=upload_id, status="uploaded",
        filename=record["original_filename"], downloadReady=True,
    )


@app.get("/api/uploads/{upload_id}", response_model=UploadDetail)
async def get_upload(upload_id: str):
    record = await db.get_upload(upload_id)
    if not record:
        raise HTTPException(404, "Upload not found")
    return _upload_to_detail(record)


@app.get("/api/uploads/{upload_id}/download")
async def download_original(upload_id: str):
    record = await db.get_upload(upload_id)
    if not record:
        raise HTTPException(404, "Upload not found")
    if record["status"] != "uploaded":
        raise HTTPException(400, "File not ready")
    file_path = storage.get_file_path(record["storage_key"])
    if not file_path.exists():
        raise HTTPException(404, "File not found in storage")
    return FileResponse(
        path=str(file_path),
        filename=record["original_filename"],
        media_type=record["mime_type"],
    )


@app.get("/api/uploads")
async def list_uploads(limit: int = Query(50, le=100), offset: int = Query(0, ge=0)):
    records = await db.list_uploads(limit, offset)
    return {
        "uploads": [_upload_to_detail(r).model_dump() for r in records],
        "total": len(records),
    }


# ═══════════════════════════════════════════════════════
# NEW: AI Enhancement Job Routes
# ═══════════════════════════════════════════════════════

@app.post("/api/jobs/create", response_model=JobDetail)
async def create_job(body: CreateJobRequest):
    """Start an AI enhancement job for an uploaded video."""
    try:
        job = await create_enhance_job(body.uploadId, body.model)
        return _job_to_detail(job)
    except EnhanceError as e:
        raise HTTPException(400, str(e))


@app.get("/api/jobs/{job_id}", response_model=JobDetail)
async def get_job(job_id: str):
    """Get current status of an enhancement job."""
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_to_detail(job)


@app.get("/api/jobs/{job_id}/download")
async def download_enhanced(job_id: str):
    """Download the AI-enhanced video."""
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "completed":
        raise HTTPException(400, f"Job is not complete (status: {job['status']})")
    if not job.get("output_key"):
        raise HTTPException(404, "No output file")

    file_path = storage.get_file_path(job["output_key"])
    if not file_path.exists():
        raise HTTPException(404, "Enhanced file not found in storage")

    # Get original filename for a nice download name
    upload = await db.get_upload(job["upload_id"])
    name = f"enhanced_{upload['original_filename']}" if upload else "enhanced_video.mp4"

    return FileResponse(
        path=str(file_path),
        filename=name,
        media_type="video/mp4",
    )


@app.get("/api/uploads/{upload_id}/jobs")
async def list_jobs_for_upload(upload_id: str):
    """List all enhancement jobs for a given upload."""
    jobs = await db.get_jobs_by_upload(upload_id)
    return {"jobs": [_job_to_detail(j).model_dump() for j in jobs]}


# ── Available models ───────────────────────────────────
@app.get("/api/models")
async def list_models():
    """List available AI enhancement models."""
    return {
        "models": [
            {"key": k, "name": v, "available": bool(config.REPLICATE_API_TOKEN)}
            for k, v in config.REPLICATE_MODELS.items()
        ],
        "default": config.DEFAULT_ENHANCE_MODEL,
    }


# ── Health ─────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "skyframe",
        "version": "0.2.0",
        "aiEnabled": bool(config.REPLICATE_API_TOKEN),
    }

# ── Serve frontend (same-origin) ───────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
