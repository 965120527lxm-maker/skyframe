"""
AI Enhancement Service — Replicate Integration

Handles:
  1. Submitting video to Replicate for AI upscaling
  2. Polling for job completion
  3. Downloading enhanced video back to local storage

Supported models:
  - lucataco/real-esrgan-video  (general purpose, good default)
  - topazlabs/video-upscale     (premium quality)
"""

import asyncio
import uuid
import logging
from datetime import datetime, timezone

import httpx
import replicate

import config
import database as db
import storage

logger = logging.getLogger("skyframe.enhance")


class EnhanceError(Exception):
    pass


async def create_enhance_job(
    upload_id: str,
    model_key: str = None,
) -> dict:
    """
    Create an AI enhancement job for an uploaded video.
    Returns the job record.
    """
    upload = await db.get_upload(upload_id)
    if not upload:
        raise EnhanceError("Upload not found")
    if upload["status"] != "uploaded":
        raise EnhanceError("Upload is not ready for enhancement")

    if not config.REPLICATE_API_TOKEN:
        raise EnhanceError("REPLICATE_API_TOKEN not set. Export it to enable AI enhancement.")

    model_key = model_key or config.DEFAULT_ENHANCE_MODEL
    model_name = config.REPLICATE_MODELS.get(model_key)
    if not model_name:
        raise EnhanceError(f"Unknown model: {model_key}. Available: {list(config.REPLICATE_MODELS.keys())}")

    job_id = "job_" + uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()

    await db.insert_job({
        "id": job_id,
        "upload_id": upload_id,
        "model_name": model_name,
        "status": "pending",
        "created_at": now,
    })

    # Fire off the Replicate prediction in background
    asyncio.create_task(_run_prediction(job_id, upload, model_name))

    return await db.get_job(job_id)


async def _run_prediction(job_id: str, upload: dict, model_name: str):
    """
    Background task: submit to Replicate, poll, download result.
    """
    try:
        await db.update_job(job_id, {
            "status": "processing",
            "started_at": datetime.now(timezone.utc).isoformat(),
        })

        # The video file needs to be accessible via URL for Replicate.
        # For local dev: we upload the file to Replicate's file API.
        # For production with S3: just pass the presigned URL.
        file_path = storage.get_file_path(upload["storage_key"])
        if not file_path.exists():
            raise EnhanceError("Source video not found in storage")

        logger.info(f"[{job_id}] Submitting to Replicate model: {model_name}")

        # Run prediction (async polling mode)
        prediction = await asyncio.to_thread(
            _submit_prediction, model_name, file_path
        )

        replicate_id = prediction.id
        await db.update_job(job_id, {"replicate_id": replicate_id})

        logger.info(f"[{job_id}] Replicate prediction: {replicate_id} — waiting...")

        # Poll until done
        result = await asyncio.to_thread(_wait_for_prediction, prediction)

        if result.status == "failed":
            raise EnhanceError(f"Replicate prediction failed: {result.error}")
        if result.status == "canceled":
            raise EnhanceError("Prediction was canceled")

        # Get the output URL
        output_url = _extract_output_url(result)
        if not output_url:
            raise EnhanceError("No output URL returned from Replicate")

        logger.info(f"[{job_id}] Downloading enhanced video...")

        # Download enhanced video to local storage
        output_key = storage.generate_output_key(
            job_id, f"enhanced_{upload['original_filename']}"
        )
        output_size = await _download_output(output_url, output_key)

        await db.update_job(job_id, {
            "status": "completed",
            "output_key": output_key,
            "output_size": output_size,
            "progress": 100,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

        logger.info(f"[{job_id}] ✅ Enhancement complete! Output: {output_key}")

    except Exception as e:
        logger.error(f"[{job_id}] ❌ Enhancement failed: {e}")
        await db.update_job(job_id, {
            "status": "failed",
            "error_message": str(e),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })


def _submit_prediction(model_name: str, file_path) -> "replicate.Prediction":
    """
    Submit a video enhancement prediction to Replicate.
    This runs in a thread because the replicate SDK is synchronous.
    """
    # Build input based on model
    if "real-esrgan" in model_name:
        prediction = replicate.predictions.create(
            model=model_name,
            input={
                "video_path": open(file_path, "rb"),
                "scale": config.DEFAULT_SCALE_FACTOR,
            },
        )
    elif "topazlabs" in model_name:
        prediction = replicate.predictions.create(
            model=model_name,
            input={
                "video": open(file_path, "rb"),
            },
        )
    else:
        # Generic fallback
        prediction = replicate.predictions.create(
            model=model_name,
            input={
                "video": open(file_path, "rb"),
            },
        )
    return prediction


def _wait_for_prediction(prediction) -> "replicate.Prediction":
    """
    Poll Replicate until prediction reaches terminal state.
    """
    prediction.wait()
    return prediction


def _extract_output_url(prediction) -> str | None:
    """
    Extract the output video URL from a completed prediction.
    Replicate outputs vary by model — handle common patterns.
    """
    output = prediction.output

    if output is None:
        return None

    # Some models return a single FileOutput / URL string
    if isinstance(output, str):
        return output

    # FileOutput object
    if hasattr(output, "url"):
        return output.url

    # List of outputs (take the first video)
    if isinstance(output, (list, tuple)):
        for item in output:
            if isinstance(item, str):
                return item
            if hasattr(item, "url"):
                return item.url

    # Dict with common keys
    if isinstance(output, dict):
        for key in ("video", "output", "enhanced_video", "result"):
            if key in output:
                val = output[key]
                return val.url if hasattr(val, "url") else str(val)

    return None


async def _download_output(url: str, output_key: str) -> int:
    """
    Download enhanced video from Replicate URL to local storage.
    """
    dest = storage.get_file_path(output_key)
    storage._ensure_dir(dest)

    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = 0
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(1024 * 1024):
                    f.write(chunk)
                    total += len(chunk)
    return total
