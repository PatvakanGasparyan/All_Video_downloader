import asyncio
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable

DOWNLOADS_DIR = "downloads"

QUALITY_FORMATS = {
    "360": "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
    "480": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
    "720": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "1080": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "best": "bestvideo+bestaudio/best",
    "small": "best[filesize<80M]/best[filesize<40M]/worstvideo+worstaudio/worst",
}

PROGRESS_RE = re.compile(
    r"\[download\]\s+(?P<percent>\d+(?:\.\d+)?)%"
    r"(?:\s+of\s+(?P<total>[^\s]+))?"
    r"(?:\s+at\s+(?P<speed>[^\s]+))?"
    r"(?:\s+ETA\s+(?P<eta>\S+))?",
    re.IGNORECASE,
)
DESTINATION_RE = re.compile(r"\[download\] Destination:\s*(.+)", re.IGNORECASE)
ALREADY_DOWNLOADED_RE = re.compile(
    r"\[download\]\s+(.+?)\s+has already been downloaded", re.IGNORECASE
)

SKIP_SUFFIXES = (".part", ".ytdl", ".json", ".temp")


def _yt_dlp_executable():
    name = "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"
    venv_bin = os.path.join(os.path.dirname(sys.executable), name)
    if os.path.isfile(venv_bin):
        return venv_bin
    return shutil.which(name) or name


def _ffmpeg_location():
    bin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")
    if os.path.isdir(bin_dir) and (
        os.path.isfile(os.path.join(bin_dir, "ffmpeg.exe"))
        or os.path.isfile(os.path.join(bin_dir, "ffmpeg"))
    ):
        return bin_dir
    found = shutil.which("ffmpeg")
    return os.path.dirname(found) if found else None


def _format_filesize_bytes(size: int) -> str:
    if size <= 0:
        return "N/A"
    return f"{round(size / (1024 * 1024))} MB"


def _format_filesize(raw):
    if not raw or raw == "NA":
        return "N/A"
    try:
        return _format_filesize_bytes(int(raw))
    except (TypeError, ValueError):
        return "N/A"


def _short_error(stderr: str) -> str:
    text = stderr.strip()
    if "Cloudflare anti-bot" in text:
        return (
            "Сайт заблокировал скачивание (Cloudflare). "
            "Попробуйте YouTube или другую ссылку."
        )
    if "ERROR:" in text:
        return text.split("ERROR:", 1)[-1].strip().split("\n", 1)[0]
    return text or "Не удалось скачать видео"


def _normalize_quality(quality: str) -> str:
    key = (quality or "720").strip().lower()
    return key if key in QUALITY_FORMATS else "720"


def _append_ffmpeg_args(cmd: list[str]) -> list[str]:
    ffmpeg = _ffmpeg_location()
    if ffmpeg:
        cmd[1:1] = ["--ffmpeg-location", ffmpeg, "--merge-output-format", "mp4"]
    return cmd


def _run_yt_dlp(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        _append_ffmpeg_args(cmd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _parse_size_to_bytes(text: str) -> int | None:
    if not text:
        return None
    match = re.match(r"([\d.]+)\s*([KMG]?i?B)", text.strip(), re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).upper()
    multipliers = {
        "B": 1,
        "KB": 1024,
        "KIB": 1024,
        "MB": 1024**2,
        "MIB": 1024**2,
        "GB": 1024**3,
        "GIB": 1024**3,
    }
    return int(value * multipliers.get(unit, 1))


def _fetch_video_info(
    url: str, on_progress: Callable[[dict], None] | None = None
) -> dict:
    stop_pulse = threading.Event()

    def pulse_preparing():
        step = 0
        while not stop_pulse.is_set():
            if on_progress:
                on_progress(
                    {
                        "percent": min(12, step),
                        "total": "",
                        "speed": "",
                        "eta": "",
                        "status": "preparing",
                    }
                )
            step = (step + 1) % 13
            stop_pulse.wait(0.35)

    pulse_thread = None
    if on_progress:
        pulse_thread = threading.Thread(target=pulse_preparing, daemon=True)
        pulse_thread.start()

    try:
        cmd = [
            _yt_dlp_executable(),
            "--skip-download",
            "--print",
            "%(title)s|||%(duration_string)s|||%(filesize_approx)s",
            url,
        ]
        result = _run_yt_dlp(cmd)
        if result.returncode != 0:
            raise ValueError(_short_error(result.stderr))

        line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        parts = line.split("|||")
        if len(parts) < 3:
            raise ValueError("Не удалось получить информацию о видео")

        return {
            "title": parts[0],
            "duration": parts[1] or "00:00",
            "filesize": _format_filesize(parts[2]),
        }
    finally:
        stop_pulse.set()
        if pulse_thread:
            pulse_thread.join(timeout=1)


def _list_download_files() -> set[str]:
    if not os.path.isdir(DOWNLOADS_DIR):
        return set()
    return {
        name
        for name in os.listdir(DOWNLOADS_DIR)
        if not name.endswith(SKIP_SUFFIXES)
    }


def _find_downloaded_file(since: float) -> str:
    candidates: list[tuple[float, str]] = []
    for name in _list_download_files():
        path = os.path.join(DOWNLOADS_DIR, name)
        if not os.path.isfile(path):
            continue
        mtime = os.path.getmtime(path)
        if mtime >= since - 2:
            candidates.append((mtime, name))

    if not candidates:
        raise ValueError("Файл не создан. Установите ffmpeg для этого формата.")

    candidates.sort(reverse=True)
    return candidates[0][1]


def _build_download_cmd(url: str, quality: str) -> list[str]:
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    fmt = QUALITY_FORMATS[_normalize_quality(quality)]

    return [
        _yt_dlp_executable(),
        "-f",
        fmt,
        "-N",
        "4",
        "--socket-timeout",
        "30",
        "--retries",
        "5",
        "--fragment-retries",
        "5",
        "--newline",
        "--progress",
        "-o",
        os.path.join(DOWNLOADS_DIR, "%(title)s.%(ext)s"),
        url,
    ]


def _handle_output_line(
    line: str,
    on_progress: Callable[[dict], None],
    destinations: list[str],
):
    dest_match = DESTINATION_RE.search(line)
    if dest_match:
        destinations.append(dest_match.group(1).strip())
        return

    already_match = ALREADY_DOWNLOADED_RE.search(line)
    if already_match:
        destinations.append(already_match.group(1).strip())
        on_progress(
            {
                "percent": 100,
                "total": "",
                "speed": "",
                "eta": "",
                "status": "downloading",
            }
        )
        return

    if line.startswith("[download]"):
        match = PROGRESS_RE.search(line)
        if match:
            on_progress(
                {
                    "percent": float(match.group("percent")),
                    "total": (match.group("total") or "").strip(),
                    "speed": (match.group("speed") or "").strip(),
                    "eta": (match.group("eta") or "").strip(),
                    "status": "downloading",
                }
            )
        return

    if "Downloading webpage" in line or "Extracting" in line:
        on_progress(
            {
                "percent": 0,
                "total": "",
                "speed": "",
                "eta": "",
                "status": "preparing",
            }
        )
    elif "Merging formats" in line or "Post-processing" in line:
        on_progress(
            {
                "percent": 99,
                "total": "",
                "speed": "",
                "eta": "",
                "status": "processing",
            }
        )


def _watch_download_size(
    stop_event: threading.Event,
    on_progress: Callable[[dict], None],
    started_at: float,
    last_progress: dict,
):
    """Fallback progress from .part file growth when yt-dlp output is buffered."""
    while not stop_event.is_set():
        downloaded = 0
        for name in os.listdir(DOWNLOADS_DIR):
            path = os.path.join(DOWNLOADS_DIR, name)
            if not os.path.isfile(path):
                continue
            if name.endswith((".part", ".ytdl")) or os.path.getmtime(path) >= started_at - 1:
                downloaded += os.path.getsize(path)

        current = last_progress.get("percent") or 0
        total_text = last_progress.get("total") or ""
        total_bytes = _parse_size_to_bytes(total_text) if total_text else None

        if downloaded > 0:
            if total_bytes:
                percent = min(99.0, (downloaded / total_bytes) * 100)
            else:
                percent = max(current, 1.0)

            if percent > current:
                size_mb = downloaded / (1024 * 1024)
                on_progress(
                    {
                        "percent": percent,
                        "total": total_text or f"{size_mb:.1f} MiB",
                        "speed": last_progress.get("speed", ""),
                        "eta": last_progress.get("eta", ""),
                        "status": "downloading",
                    }
                )
        stop_event.wait(0.35)


def _download_sync(
    url: str, quality: str, on_progress: Callable[[dict], None] | None = None
) -> dict:
    def report(data: dict):
        last_progress.update(data)
        if on_progress:
            on_progress(data)

    last_progress: dict = {
        "percent": 0,
        "total": "",
        "speed": "",
        "eta": "",
        "status": "starting",
    }
    report(last_progress.copy())

    report(
        {
            "percent": 0,
            "total": "",
            "speed": "",
            "eta": "",
            "status": "preparing",
        }
    )
    info = _fetch_video_info(url, on_progress=report)

    started_at = time.time()
    cmd = _build_download_cmd(url, quality)
    cmd = _append_ffmpeg_args(cmd)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    output_lines: list[str] = []
    destinations: list[str] = []
    stop_watch = threading.Event()
    watcher = threading.Thread(
        target=_watch_download_size,
        args=(stop_watch, report, started_at, last_progress),
        daemon=True,
    )
    watcher.start()

    if process.stdout:
        for line in iter(process.stdout.readline, ""):
            line = line.strip()
            if not line:
                continue
            output_lines.append(line)
            _handle_output_line(line, report, destinations)

    process.wait()
    stop_watch.set()
    watcher.join(timeout=2)

    if process.returncode != 0:
        raise ValueError(_short_error("\n".join(output_lines) or "Не удалось скачать видео"))

    if destinations:
        filepath = destinations[-1]
        if not os.path.isabs(filepath):
            filepath = os.path.normpath(filepath)
        filename = os.path.basename(filepath)
    else:
        filename = _find_downloaded_file(started_at)
        filepath = os.path.join(DOWNLOADS_DIR, filename)
    size_on_disk = os.path.getsize(filepath) if os.path.isfile(filepath) else 0

    report(
        {
            "percent": 100,
            "total": "",
            "speed": "",
            "eta": "",
            "status": "done",
        }
    )

    return {
        "title": info["title"],
        "duration": info["duration"],
        "filename": filename,
        "filesize": _format_filesize_bytes(size_on_disk)
        if size_on_disk
        else info["filesize"],
        "original_url": url,
        "quality": _normalize_quality(quality),
    }


async def download_video(
    url: str,
    quality: str = "720",
    on_progress: Callable[[dict], None] | None = None,
) -> dict:
    return await asyncio.to_thread(_download_sync, url, quality, on_progress)
