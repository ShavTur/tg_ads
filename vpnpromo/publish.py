"""Deliver finished videos: to Telegram (for review/manual upload) and/or TikTok."""

import os
import time
from pathlib import Path

import requests

from .ideas import VideoScript

TIKTOK_API = "https://open.tiktokapis.com/v2"


def full_caption(script: VideoScript) -> str:
    tags = " ".join("#" + t.lstrip("#").replace(" ", "") for t in script.hashtags)
    return f"{script.caption}\n\n{tags}"


# ---------- Telegram ----------

def send_to_telegram(video: Path, script: VideoScript) -> None:
    token, chat_id = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    # Caption is sent inside <code> so you can copy it in one tap when uploading to TikTok.
    caption = f"<b>{script.title}</b> [{script.format}]\n\n<code>{full_caption(script)}</code>"
    with video.open("rb") as f:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendVideo",
            data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML", "supports_streaming": True},
            files={"video": (video.name, f, "video/mp4")},
            timeout=300,
        )
    resp.raise_for_status()


# ---------- TikTok Content Posting API (Direct Post) ----------

def _tiktok_token() -> str:
    """Use TIKTOK_REFRESH_TOKEN to get a fresh access token if provided, else TIKTOK_ACCESS_TOKEN."""
    refresh = os.environ.get("TIKTOK_REFRESH_TOKEN")
    if not refresh:
        return os.environ["TIKTOK_ACCESS_TOKEN"]
    resp = requests.post(
        f"{TIKTOK_API}/oauth/token/",
        data={
            "client_key": os.environ["TIKTOK_CLIENT_KEY"],
            "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": refresh,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok token refresh failed: {data}")
    return data["access_token"]


def upload_to_tiktok(video: Path, script: VideoScript, privacy: str) -> str:
    token = _tiktok_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    size = video.stat().st_size

    init = requests.post(
        f"{TIKTOK_API}/post/publish/video/init/",
        headers=headers,
        json={
            "post_info": {
                "title": full_caption(script)[:2200],
                "privacy_level": privacy,
                "disable_comment": False,
                "disable_duet": False,
                "disable_stitch": False,
            },
            # single chunk: our videos are well below the 64 MB chunk limit
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1},
        },
        timeout=30,
    ).json()
    if init.get("error", {}).get("code") != "ok":
        raise RuntimeError(f"TikTok init failed: {init}")
    publish_id, upload_url = init["data"]["publish_id"], init["data"]["upload_url"]

    put = requests.put(
        upload_url,
        headers={"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{size - 1}/{size}"},
        data=video.read_bytes(),
        timeout=600,
    )
    put.raise_for_status()

    for _ in range(30):
        status = requests.post(f"{TIKTOK_API}/post/publish/status/fetch/", headers=headers,
                               json={"publish_id": publish_id}, timeout=30).json()
        state = status.get("data", {}).get("status")
        if state == "PUBLISH_COMPLETE":
            return publish_id
        if state == "FAILED":
            raise RuntimeError(f"TikTok publish failed: {status}")
        time.sleep(10)
    return publish_id
