"""Media downloader with direct CDN and yt-dlp fallback support."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

import httpx
import yt_dlp

from app.logging import log_info, log_warning

TEMP_PREFIX = "ig_tg_"
CHUNK_SIZE = 8192
DOWNLOAD_TIMEOUT_SECONDS = 120.0
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


class DownloadError(Exception):
    """Raised when Instagram media cannot be downloaded."""


def _kind_from_media_type(media_type: str) -> str:
    """Map an Instagram media type to a Telegram media kind."""
    return "video" if media_type.upper() == "VIDEO" else "photo"


def _kind_from_path(file_path: str) -> str:
    """Infer Telegram media kind from a downloaded file extension."""
    suffix = Path(file_path).suffix.lower()
    return "video" if suffix in VIDEO_EXTENSIONS else "photo"


def _size_mb(file_path: str) -> float:
    """Return a file's size in megabytes."""
    return os.path.getsize(file_path) / (1024 * 1024)


def _direct_extension(media_type: str) -> str:
    """Choose a safe filename extension for direct downloads."""
    return ".mp4" if media_type.upper() == "VIDEO" else ".jpg"


def _find_downloaded_file(tmpdir: str) -> str | None:
    """Return the first non-empty file downloaded by yt-dlp."""
    for item in Path(tmpdir).iterdir():
        if item.is_file() and item.stat().st_size > 0:
            return str(item)
    return None


def _download_direct(direct_url: str, media_type: str) -> tuple[str, str, float]:
    """Download media from Instagram's direct CDN URL."""
    tmpdir = tempfile.mkdtemp(prefix=TEMP_PREFIX)
    success = False
    file_path = os.path.join(tmpdir, f"{uuid.uuid4().hex}{_direct_extension(media_type)}")
    try:
        with httpx.stream(
            "GET",
            direct_url,
            follow_redirects=True,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        ) as response:
            response.raise_for_status()
            with open(file_path, "wb") as output:
                for chunk in response.iter_bytes(CHUNK_SIZE):
                    if chunk:
                        output.write(chunk)
        if os.path.getsize(file_path) <= 0:
            raise DownloadError("direct download produced an empty file")
        success = True
        return file_path, _kind_from_media_type(media_type), _size_mb(file_path)
    except (DownloadError, httpx.HTTPError, OSError) as exc:
        raise DownloadError(f"direct download failed: {exc}") from exc
    finally:
        if not success:
            shutil.rmtree(tmpdir, ignore_errors=True)


def _download_ytdlp(permalink: str) -> tuple[str, str, float]:
    """Download media through yt-dlp."""
    tmpdir = tempfile.mkdtemp(prefix=TEMP_PREFIX)
    success = False
    options = {
        "outtmpl": f"{tmpdir}/%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "sleep_interval": 2,
        "max_sleep_interval": 5,
        "format": "best[ext=mp4]/best",
        "retries": 3,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(permalink, download=True)
            file_path = ydl.prepare_filename(info)
        if not os.path.exists(file_path):
            file_path = _find_downloaded_file(tmpdir) or file_path
        if not os.path.exists(file_path) or os.path.getsize(file_path) <= 0:
            raise DownloadError("yt-dlp did not produce a usable media file")
        success = True
        return file_path, _kind_from_path(file_path), _size_mb(file_path)
    except (
        DownloadError,
        yt_dlp.utils.DownloadError,
        OSError,
        TypeError,
        AttributeError,
    ) as exc:
        raise DownloadError(f"yt-dlp download failed: {exc}") from exc
    finally:
        if not success:
            shutil.rmtree(tmpdir, ignore_errors=True)


def download_media(
    permalink: str,
    direct_url: str | None,
    media_type: str,
) -> tuple[str, str, float]:
    """Download Instagram media and return file path, kind, and size."""
    if direct_url:
        try:
            result = _download_direct(direct_url, media_type)
            log_info("download", "", f"Direct CDN succeeded: {result[1]} {result[2]:.1f}MB")
            return result
        except DownloadError as exc:
            log_warning("download", "", f"{exc}; trying yt-dlp fallback")
    try:
        result = _download_ytdlp(permalink)
    except DownloadError as exc:
        raise DownloadError(f"Unable to download Instagram media: {exc}") from exc
    log_info("download", "", f"yt-dlp succeeded: {result[1]} {result[2]:.1f}MB")
    return result
