import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

# Важная настройка для Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import db
import downloader

app = FastAPI()

if not os.path.exists("downloads"):
    os.makedirs("downloads")


@dataclass
class DownloadJob:
    status: str = "pending"
    progress: dict = field(
        default_factory=lambda: {
            "percent": 0,
            "total": "",
            "speed": "",
            "eta": "",
            "status": "pending",
        }
    )
    result: dict | None = None
    error: str | None = None


jobs: dict[str, DownloadJob] = {}


@app.on_event("startup")
async def startup():
    await db.init_db()


@app.on_event("shutdown")
async def shutdown():
    await db.close_pool()


class VideoRequest(BaseModel):
    url: str
    quality: str = "720"


def _set_progress(job_id: str, data: dict):
    job = jobs.get(job_id)
    if job:
        prev = job.progress
        percent = max(float(prev.get("percent") or 0), float(data.get("percent") or 0))
        job.progress = {**prev, **data, "percent": percent}
        if job.status == "pending":
            job.status = "running"


async def _run_download(job_id: str, url: str, quality: str):
    job = jobs[job_id]
    job.status = "running"

    def on_progress(data: dict):
        _set_progress(job_id, data)

    try:
        data = await downloader.download_video(url, quality, on_progress)
        data["id"] = await db.save_video(data)
        job.result = data
        job.status = "completed"
        job.progress = {**job.progress, "percent": 100, "status": "done"}
    except ValueError as e:
        job.status = "failed"
        job.error = str(e)
    except Exception as e:
        job.status = "failed"
        job.error = str(e)


@app.post("/download")
async def start_download(req: VideoRequest):
    job_id = str(uuid.uuid4())
    jobs[job_id] = DownloadJob()
    asyncio.create_task(_run_download(job_id, req.url, req.quality))
    return {"success": True, "job_id": job_id}


@app.get("/download/{job_id}")
async def get_download_status(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    payload: dict[str, Any] = {
        "success": job.status == "completed",
        "status": job.status,
        "progress": dict(job.progress),
    }

    if job.status == "completed" and job.result:
        payload["video"] = job.result
    if job.status == "failed":
        payload["error"] = job.error or "Не удалось скачать видео"

    return payload


@app.get("/videos")
async def api_get_videos():
    return {"success": True, "videos": await db.get_videos()}


@app.delete("/videos/{video_id}")
async def api_delete_video(video_id: int):
    filename = await db.delete_video(video_id)
    if filename and os.path.exists(f"downloads/{filename}"):
        os.remove(f"downloads/{filename}")
    return {"success": True}


FAVICON_PATH = os.path.join(os.path.dirname(__file__), "public", "favicon.svg")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(FAVICON_PATH, media_type="image/svg+xml")


app.mount("/", StaticFiles(directory="public", html=True), name="public")
