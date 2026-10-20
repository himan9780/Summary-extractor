"""URL parsing, time formatting, video metadata and transcript chunking."""
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(url: str) -> Optional[str]:
    """Return the 11-char video ID from any common YouTube URL, else None."""
    url = (url or "").strip()
    if _ID.match(url):
        return url
    try:
        p = urlparse(url if "://" in url else "https://" + url)
    except ValueError:
        return None
    host = (p.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    vid = None
    if host == "youtu.be":
        vid = p.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        if p.path == "/watch":
            vid = parse_qs(p.query).get("v", [None])[0]
        else:
            m = re.match(r"^/(shorts|embed|live|v)/([^/?]+)", p.path)
            vid = m.group(2) if m else None
    return vid if vid and _ID.match(vid) else None


def fmt_time(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def get_video_info(video_id: str) -> dict:
    """Title/author via YouTube's public oEmbed endpoint (no API key needed)."""
    info = {
        "title": "YouTube video",
        "author": "",
        "thumbnail": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }
    try:
        r = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": info["url"], "format": "json"},
            timeout=8,
        )
        if r.ok:
            data = r.json()
            info["title"] = data.get("title", info["title"])
            info["author"] = data.get("author_name", "")
    except requests.RequestException:
        pass
    return info


def transcript_text(segments: list) -> str:
    """One timestamped line per caption segment (for the transcript tab/export)."""
    return "\n".join(
        f"[{fmt_time(s['start'])}] {s['text'].replace(chr(10), ' ').strip()}"
        for s in segments
    )


def chunk_segments(segments: list, max_chars: int = 18000) -> list:
    """Group segments into chunks of ~max_chars, with a timestamp roughly every minute."""
    chunks, cur, size, last_ts = [], [], 0, -999.0
    start = end = 0.0
    for s in segments:
        txt = s["text"].replace("\n", " ").strip()
        if not txt:
            continue
        if s["start"] - last_ts >= 60:
            txt = f"[{fmt_time(s['start'])}] {txt}"
            last_ts = s["start"]
        if size + len(txt) > max_chars and cur:
            chunks.append({"start": start, "end": end, "text": " ".join(cur)})
            cur, size = [], 0
        if not cur:
            start = s["start"]
        cur.append(txt)
        size += len(txt) + 1
        end = s["start"]
    if cur:
        chunks.append({"start": start, "end": end, "text": " ".join(cur)})
    return chunks
