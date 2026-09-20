# ============================================================================
#  app.py — X / Twitter Media Downloader · advanced, cookie-free edition
# ----------------------------------------------------------------------------
#  WHY THE OLD VERSION BROKE:
#  X removed anonymous ("guest") access to its internal APIs during 2024-2025
#  and started aggressively blocking datacenter IPs. yt-dlp and gallery-dl
#  both depended on guest access, so without cookies they get rejected even
#  for public posts.
#
#  HOW THIS VERSION WORKS (no cookies, no login, ever):
#   1. cdn.syndication.twimg.com — the endpoint X serves its official "Embed
#      Tweet" widgets from. Still open anonymously. The required ?token= is
#      computed exactly like X's own embed JavaScript:
#          token = (Number(tweet_id) / 1e15) * Math.PI
#   2. api.vxtwitter.com  — public mirror API (fallback)
#   3. api.fxtwitter.com  — public mirror API (fallback)
#   4. yt-dlp             — optional last resort
#  Media is downloaded straight from X's public CDN (pbs.twimg.com /
#  video.twimg.com), which never requires authentication.
#
#  Extras: parallel downloads · retry w/ exponential backoff · HLS→MP4 remux
#  via ffmpeg · /photo/N + /video/N selectors · quoted-post media · dedup ·
#  ZIP bundling · live strategy log.
# ============================================================================

import glob
import hashlib
import io
import math
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import streamlit as st

# ============================================================================
#  CONSTANTS
# ============================================================================

UA_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
UA_BOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result"
VX_API = "https://api.vxtwitter.com"
FX_API = "https://api.fxtwitter.com"

TWEET_ID_RE = re.compile(r"(?:status|statuses)[/=](\d{15,25})", re.IGNORECASE)
INTENT_ID_RE = re.compile(r"tweet_id=(\d{15,25})", re.IGNORECASE)
BARE_ID_RE = re.compile(r"^\s*(\d{15,25})\s*$")
HANDLE_RE = re.compile(r"([A-Za-z0-9_]{1,15})/status(?:es)?/\d{15,25}", re.IGNORECASE)
SELECTOR_RE = re.compile(r"/(photo|video)/(\d{1,2})", re.IGNORECASE)

NON_HANDLES = {"i", "web", "intent", "hashtag", "search", "explore",
               "home", "settings", "compose", "messages"}

PBS_MEDIA_KEY_RE = re.compile(r"pbs\.twimg\.com/media/([A-Za-z0-9_\-]+)")
VID_MP4_RE = re.compile(
    r"https?://(?:video|media)\.twimg\.com/[^\s\"'<>\\]+?\.mp4(?:\?[^\s\"'<>\\]*)?",
    re.IGNORECASE)
VID_M3U8_RE = re.compile(
    r"https?://(?:video|media)\.twimg\.com/[^\s\"'<>\\]+?\.m3u8(?:\?[^\s\"'<>\\]*)?",
    re.IGNORECASE)
RES_RE = re.compile(r"/(\d{2,4})x(\d{2,4})/")

IMG_EXTS = {"jpg": "jpg", "jpeg": "jpg", "png": "png", "webp": "webp", "gif": "gif"}
VIDEO_ITEM_EXTS = {".mp4", ".webm", ".mkv", ".mov"}
IMAGE_ITEM_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

KIND_LABEL = {"image": "Image", "video": "Video", "gif": "GIF (as MP4)"}

MAX_PREVIEW_BYTES = 60 * 1024 * 1024    # don't inline-preview files larger than this
MAX_ZIP_BYTES = 400 * 1024 * 1024      # don't build a ZIP bundle above this


class StrategyError(Exception):
    """Raised when one extraction strategy cannot produce media."""


@dataclass
class MediaRef:
    kind: str                       # "image" | "video" | "gif"
    url: Optional[str] = None       # best direct URL (pbs orig / mp4)
    hls_url: Optional[str] = None   # HLS fallback (remuxed via ffmpeg)
    width: int = 0
    height: int = 0
    bitrate: int = 0
    duration_s: float = 0.0
    alt: str = ""
    ext: str = "jpg"
    source: str = "unknown"
    scope: str = "main"             # "main" | "quoted"
    preloaded: Optional[bytes] = None
    note: str = ""


# ============================================================================
#  NETWORK LAYER (session with retries + exponential backoff)
# ============================================================================

@st.cache_resource
def http_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3, connect=3, read=3, backoff_factor=1.2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": UA_BROWSER,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "*/*",
    })
    return s


# ============================================================================
#  URL PARSING
# ============================================================================

def parse_tweet_url(raw: str) -> Tuple[Optional[str], Optional[str],
                                        Optional[Tuple[str, int]], str]:
    """Returns (tweet_id, handle, (selector_kind, selector_index), error)."""
    text = (raw or "").strip()
    if not text:
        return None, None, None, "empty"

    m = BARE_ID_RE.match(text)                     # bare ID pasted directly
    if m:
        return m.group(1), None, None, ""

    final_text = text
    m = TWEET_ID_RE.search(text) or INTENT_ID_RE.search(text)
    if not m and re.match(r"^https?://", text, re.IGNORECASE):
        try:                                       # t.co / shorteners
            resp = http_session().head(text, allow_redirects=True, timeout=8)
            final_text = resp.url or text
            m = TWEET_ID_RE.search(final_text) or INTENT_ID_RE.search(final_text)
        except requests.RequestException:
            m = None
    if not m:
        return None, None, None, "no_id"

    tid = m.group(1)

    handle = None
    hm = HANDLE_RE.search(final_text)
    if hm and hm.group(1).lower() not in NON_HANDLES:
        handle = hm.group(1)

    selector = None
    sm = SELECTOR_RE.search(final_text)
    if sm:
        selector = (sm.group(1).lower(), int(sm.group(2)))

    return tid, handle, selector, ""


# ============================================================================
#  STRATEGY 1 — OFFICIAL SYNDICATION (EMBED) ENDPOINT
# ============================================================================

def _js_number_to_string(x: float) -> str:
    """Mimic JavaScript's Number -> String conversion (what X's embed JS uses)."""
    if math.isnan(x) or math.isinf(x):
        return "0"
    if x == int(x) and abs(x) < 1e21:
        return str(int(x))
    return repr(x)


def syndication_token_candidates(tid: str) -> List[str]:
    """
    X's embed JavaScript computes the syndication token as
    (Number(id) / 1e15) * Math.PI — we replicate it exactly (including the
    double-precision rounding of big IDs) plus a few defensive variants.
    """
    seen, out = set(), []

    def _add(v: str) -> None:
        if v and v not in seen:
            seen.add(v)
            out.append(v)

    try:
        n = float(tid)  # same IEEE-754 rounding as JS Number(id)
        _add(_js_number_to_string((n / 1e15) * math.pi))
    except ValueError:
        pass
    try:
        i = int(tid)
        _add(_js_number_to_string((i // 1_000_000_000_000_000) * math.pi))
        _add(_js_number_to_string((i / 1_000_000_000_000_000) * math.pi))
    except ValueError:
        pass
    _add("a")
    _add("0")
    return out


def fetch_syndication(tid: str) -> dict:
    s = http_session()
    param_sets = [{"id": tid, "lang": "en", "token": tok}
                  for tok in syndication_token_candidates(tid)]
    param_sets.append({"id": tid, "lang": "en"})

    header_sets = [
        {"User-Agent": UA_BROWSER,
         "Referer": "https://platform.twitter.com/",
         "Accept": "*/*"},
        {"User-Agent": UA_BOT, "Accept": "*/*"},
    ]

    last = ""
    for params in param_sets:
        for headers in header_sets:
            try:
                r = s.get(SYNDICATION_URL, params=params, headers=headers,
                          timeout=(10, 20))
            except requests.RequestException as exc:
                last = f"network error: {exc}"
                continue
            if r.status_code == 429:
                raise StrategyError("X is rate-limiting this server on the "
                                    "embed endpoint (HTTP 429) — retry in a minute")
            if r.status_code == 200 and r.content:
                try:
                    data = r.json()
                except ValueError:
                    last = "non-JSON response"
                    continue
                if isinstance(data, dict):
                    if data.get("errors"):
                        last = f"API error: {str(data['errors'])[:200]}"
                        continue
                    if (data.get("mediaDetails") is not None
                            or data.get("text") is not None or data.get("id_str")):
                        return data
                    last = "unexpected payload shape"
                else:
                    last = "unexpected payload type"
            else:
                last = f"HTTP {r.status_code}"
    raise StrategyError(last or "embed endpoint unreachable")


def _media_list(payload: dict) -> list:
    media = payload.get("mediaDetails")
    if media is None:
        media = payload.get("media_details")
    if media is None:
        media = (payload.get("entities") or {}).get("media")
    return media or []


def upgrade_photo_url(u: str) -> str:
    """Rewrite any pbs.twimg.com media URL to its original full resolution."""
    if not u:
        return ""
    u = u.strip().replace("&amp;", "&")
    if not u.startswith("http"):
        u = "https://" + u.lstrip("/")
    sp = urlsplit(u)
    q = dict(parse_qsl(sp.query))
    fmt = (q.get("format") or "").lower()
    if not fmt:
        seg = sp.path.rsplit("/", 1)[-1]
        if "." in seg:
            fmt = seg.rsplit(".", 1)[-1].lower()
    fmt = IMG_EXTS.get(fmt, "jpg")
    return f"https://pbs.twimg.com{sp.path}?format={fmt}&name=orig"


def parse_media_detail(m: dict, source: str, scope: str) -> List[MediaRef]:
    mtype = (m.get("type") or "").lower()
    oi = m.get("original_info") or {}
    try:
        w = int(oi.get("width") or 0)
    except (TypeError, ValueError):
        w = 0
    try:
        h = int(oi.get("height") or 0)
    except (TypeError, ValueError):
        h = 0
    if (not w or not h) and isinstance(m.get("sizes"), dict):
        large = m["sizes"].get("large") or {}
        w = w or int(large.get("w") or 0)
        h = h or int(large.get("h") or 0)
    alt = m.get("ext_alt_text") or ""

    if mtype == "photo":
        url = upgrade_photo_url(m.get("media_url_https") or m.get("media_url") or "")
        if not url:
            return []
        fmt = url.split("format=")[-1].split("&")[0] if "format=" in url else "jpg"
        return [MediaRef(kind="image", url=url, width=w, height=h, alt=alt,
                         ext=fmt, source=source, scope=scope)]

    vi = m.get("video_info") or {}
    variants = [v for v in (vi.get("variants") or [])
                if isinstance(v, dict) and v.get("url")]
    mp4s = [v for v in variants if "mp4" in str(v.get("content_type", "")).lower()]
    m3u8 = next((v["url"] for v in variants
                 if "mpegurl" in str(v.get("content_type", "")).lower()), None)
    try:
        duration = float(vi.get("duration_millis") or 0) / 1000.0
    except (TypeError, ValueError):
        duration = 0.0
    kind = "gif" if mtype == "animated_gif" else "video"

    if mp4s:  # pick the highest-bitrate MP4 rendition
        best = max(mp4s, key=lambda v: int(v.get("bitrate") or 0))
        return [MediaRef(kind=kind, url=best["url"], hls_url=m3u8, width=w,
                         height=h, bitrate=int(best.get("bitrate") or 0),
                         duration_s=duration, alt=alt, ext="mp4",
                         source=source, scope=scope)]
    if m3u8:  # HLS-only (rare) — remuxed with ffmpeg later
        return [MediaRef(kind=kind, url=None, hls_url=m3u8, width=w, height=h,
                         duration_s=duration, alt=alt, ext="mp4", source=source,
                         scope=scope, note="HLS stream — remuxing with ffmpeg")]
    return []


def parse_syndication_payload(data: dict) -> Tuple[List[MediaRef], dict]:
    refs: List[MediaRef] = []
    for m in _media_list(data):
        refs.extend(parse_media_detail(m, "syndication", "main"))
    user = data.get("user") or {}
    meta = {
        "author": user.get("screen_name") or "",
        "author_name": user.get("name") or "",
        "text": data.get("text") or "",
        "created_at": data.get("created_at") or "",
    }
    quoted = data.get("quoted_tweet_result") or data.get("quoted_tweet")
    if isinstance(quoted, dict):
        for m in _media_list(quoted):
            refs.extend(parse_media_detail(m, "syndication", "quoted"))
    return refs, meta


# ============================================================================
#  STRATEGIES 2 & 3 — PUBLIC MIRROR APIs (schema-agnostic URL harvesting)
# ============================================================================

def _harvest_twimg_strings(node, found: List[str]) -> None:
    """Recursively walk any JSON and collect every twimg.com media URL.
    Makes the mirror fallbacks immune to API schema changes."""
    if isinstance(node, dict):
        for v in node.values():
            _harvest_twimg_strings(v, found)
    elif isinstance(node, list):
        for v in node:
            _harvest_twimg_strings(v, found)
    elif isinstance(node, str) and "twimg.com" in node:
        found.append(node.strip())


def normalize_harvested(urls: List[str], source: str) -> List[MediaRef]:
    photos: dict = {}
    videos: dict = {}
    m3u8s: List[str] = []

    for raw in urls:
        u = raw.replace("&amp;", "&")

        if "pbs.twimg.com/media/" in u:
            m = PBS_MEDIA_KEY_RE.search(u)
            if m:
                sp = urlsplit(u if u.startswith("http") else "https://" + u)
                q = dict(parse_qsl(sp.query))
                fmt = (q.get("format") or "").lower()
                if not fmt:
                    seg = sp.path.rsplit("/", 1)[-1]
                    fmt = seg.rsplit(".", 1)[-1].lower() if "." in seg else "jpg"
                photos[m.group(1)] = IMG_EXTS.get(fmt, "jpg")
            continue

        m = VID_MP4_RE.search(u)
        if m:
            url = m.group(0)
            path = urlsplit(url).path
            resm = RES_RE.search(path)
            area = int(resm.group(1)) * int(resm.group(2)) if resm else 0
            w, h = (int(resm.group(1)), int(resm.group(2))) if resm else (0, 0)
            kind = "gif" if "/tweet_video/" in path else "video"
            g = re.search(r"/(?:ext_tw_video|amplify_video)/(\d+)", path)
            gkey = g.group(1) if g else path
            score = (0 if "/hevc/" not in path else 1, area)  # prefer AVC, biggest
            if gkey not in videos or score > videos[gkey][0]:
                videos[gkey] = (score, url, kind, w, h)
            continue

        m = VID_M3U8_RE.search(u)
        if m:
            m3u8s.append(m.group(0))

    refs: List[MediaRef] = []
    if videos:
        # A post can't mix videos and photos — any pbs links are video posters.
        for _score, url, kind, w, h in videos.values():
            refs.append(MediaRef(kind=kind, url=url, width=w, height=h,
                                 ext="mp4", source=source))
    else:
        for key, fmt in photos.items():
            refs.append(MediaRef(
                kind="image",
                url=f"https://pbs.twimg.com/media/{key}?format={fmt}&name=orig",
                ext=fmt, source=source))
    if not refs and m3u8s:
        refs.append(MediaRef(kind="video", url=None, hls_url=m3u8s[0], ext="mp4",
                             source=source,
                             note="HLS stream — remuxing with ffmpeg"))
    return refs


def _extract_meta_generic(data: dict) -> dict:
    node = data.get("tweet") if isinstance(data.get("tweet"), dict) else data
    user = node.get("user") or node.get("author") or {}
    return {
        "author": node.get("user_screen_name") or user.get("screen_name") or "",
        "author_name": node.get("user_name") or user.get("name") or "",
        "text": node.get("text") or node.get("tweet_text") or "",
        "created_at": str(node.get("created_at") or node.get("date") or ""),
    }


def fetch_via_mirror(api_base: str, tid: str, handle: Optional[str],
                     name: str) -> Tuple[List[MediaRef], dict]:
    s = http_session()
    urls = []
    if handle:
        urls.append(f"{api_base}/{handle}/status/{tid}")
    urls += [f"{api_base}/i/status/{tid}",
             f"{api_base}/status/{tid}",
             f"{api_base}/_/status/{tid}"]
    headers = {"Accept": "application/json", "Referer": "https://x.com/"}

    last = ""
    for url in urls:
        try:
            r = s.get(url, headers=headers, timeout=(10, 20))
        except requests.RequestException as exc:
            last = f"network error: {exc}"
            continue
        if r.status_code != 200 or not r.content:
            last = f"HTTP {r.status_code}"
            continue
        try:
            data = r.json()
        except ValueError:
            last = "non-JSON payload"
            continue
        if not isinstance(data, dict):
            last = "unexpected payload type"
            continue
        code = data.get("code")
        if data.get("error") or (code is not None and code != 200):
            last = f"API error: {str(data.get('error') or code)[:160]}"
            continue
        found: List[str] = []
        _harvest_twimg_strings(data, found)
        refs = normalize_harvested(found, source=name)
        if refs:
            return refs, _extract_meta_generic(data)
        last = "payload contained no twimg.com media"
    raise StrategyError(last or "no media found")


# ============================================================================
#  STRATEGY 4 — yt-dlp (optional last resort)
# ============================================================================

def fetch_via_ytdlp(target_url: str) -> List[MediaRef]:
    if not shutil.which("yt-dlp"):
        raise StrategyError("yt-dlp is not installed on the server")
    with tempfile.TemporaryDirectory(prefix="tdl_yt_") as td:
        out_tpl = os.path.join(td, "media_%(autonumber)03d.%(ext)s")
        cmd = ["yt-dlp", "--no-warnings", "--no-playlist",
               "--socket-timeout", "15", "--retries", "2",
               "-f", "bv*+ba/b", "--merge-output-format", "mp4",
               "-o", out_tpl, target_url]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=240)
        except subprocess.TimeoutExpired:
            raise StrategyError("yt-dlp timed out")
        files = [f for f in glob.glob(os.path.join(td, "**", "*"), recursive=True)
                 if os.path.isfile(f)]
        refs: List[MediaRef] = []
        for fp in sorted(files):
            ext = os.path.splitext(fp)[1].lower()
            if ext in VIDEO_ITEM_EXTS:
                kind = "video"
            elif ext in IMAGE_ITEM_EXTS:
                kind = "image"
            else:
                continue
            with open(fp, "rb") as fh:
                data = fh.read()
            if data:
                refs.append(MediaRef(kind=kind, ext=ext.lstrip(".") or "bin",
                                     source="yt-dlp", preloaded=data))
        if not refs:
            err = (proc.stderr or b"").decode("utf-8", "ignore").strip().splitlines()
            raise StrategyError("yt-dlp: " + (err[-1] if err else "no media produced"))
        return refs


# ============================================================================
#  DOWNLOAD LAYER (parallel, with HLS remux fallback)
# ============================================================================

def _download_direct(url: str) -> Tuple[bytes, str]:
    s = http_session()
    candidates = [url]
    if "pbs.twimg.com" in url:  # graceful degradation for photos
        for size in ("large", "medium", "small"):
            candidates.append(re.sub(r"name=[^&]+", f"name={size}", url))
    headers = {"Referer": "https://x.com/"}
    last = ""
    for u in candidates:
        try:
            with s.get(u, headers=headers, stream=True, timeout=(15, 180)) as r:
                if r.status_code == 200:
                    buf = io.BytesIO()
                    for chunk in r.iter_content(chunk_size=256 * 1024):
                        if chunk:
                            buf.write(chunk)
                    data = buf.getvalue()
                    if data:
                        return data, (r.headers.get("Content-Type") or
                                      "").split(";")[0].strip()
                    last = "empty response body"
                else:
                    last = f"HTTP {r.status_code}"
        except requests.RequestException as exc:
            last = f"network error: {exc}"
    raise StrategyError(last or "download failed")


def _download_hls(m3u8_url: str) -> Tuple[bytes, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise StrategyError("only an HLS stream was available and ffmpeg is missing")
    with tempfile.TemporaryDirectory(prefix="tdl_hls_") as td:
        out = os.path.join(td, "video.mp4")
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", m3u8_url,
               "-c", "copy", "-bsf:a", "aac_adtstoasc",
               "-movflags", "+faststart", out]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=600)
        except subprocess.TimeoutExpired:
            raise StrategyError("ffmpeg timed out while remuxing the stream")
        if proc.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
            detail = (proc.stderr or b"").decode("utf-8", "ignore")[:300]
            raise StrategyError(f"ffmpeg remux failed: {detail}")
        with open(out, "rb") as fh:
            return fh.read(), "video/mp4"


def download_bytes_for_ref(ref: MediaRef) -> Tuple[bytes, str]:
    if ref.preloaded is not None:
        ext_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                   "webp": "image/webp", "gif": "image/gif", "mp4": "video/mp4",
                   "webm": "video/webm", "mkv": "video/x-matroska"}
        return ref.preloaded, ext_map.get((ref.ext or "").lower(),
                                          "application/octet-stream")
    if ref.url:
        return _download_direct(ref.url)
    if ref.hls_url:
        return _download_hls(ref.hls_url)
    raise StrategyError("media reference has no usable URL")


def _build_item(i: int, ref: MediaRef, data: bytes, mime: str,
                handle: str, tid: str) -> dict:
    kind = ref.kind
    ext = (ref.ext or "").lower() or ("mp4" if kind in ("video", "gif") else "jpg")
    if mime and (mime.startswith("image/") or mime.startswith("video/")):
        if mime == "image/jpeg":
            ext = "jpg"
        elif mime in ("image/png", "image/webp", "image/gif",
                      "video/mp4", "video/webm"):
            ext = mime.split("/", 1)[1]
    else:
        mime = {"image": "image/jpeg", "video": "video/mp4",
                "gif": "video/mp4"}.get(kind, "application/octet-stream")
        if kind == "image" and ext in ("png", "webp"):
            mime = f"image/{ext}"

    tag = {"image": "img", "video": "vid", "gif": "gif"}[kind]
    handle_part = re.sub(r"[^A-Za-z0-9_]", "", handle or "")[:32] or "tweet"
    res_part = f"_{ref.width}x{ref.height}" if ref.width and ref.height else ""
    name = f"{handle_part}_{tid}_{tag}{i + 1}{res_part}.{ext}"

    return {
        "name": name,
        "data": data,
        "mime": mime,
        "type": kind,
        "meta": {
            "width": ref.width, "height": ref.height,
            "bitrate_kbps": int(ref.bitrate / 1000) if ref.bitrate else 0,
            "duration_s": round(ref.duration_s, 1),
            "size_mb": round(len(data) / (1024 * 1024), 2),
            "alt": ref.alt, "source": ref.source, "scope": ref.scope,
            "note": ref.note,
        },
    }


def download_all_refs(refs: List[MediaRef], handle: str, tid: str,
                      progress=None, log=None) -> Tuple[List[dict], List[str]]:
    items: List[dict] = []
    errors: List[str] = []
    if not refs:
        return items, errors

    def _work(i: int, ref: MediaRef):
        try:
            data, mime = download_bytes_for_ref(ref)
            return (i, ref, data, mime, None)
        except Exception as exc:  # noqa: BLE001 — surface per-item failures
            return (i, ref, None, None, str(exc))

    slots = [None] * len(refs)
    completed = 0
    with ThreadPoolExecutor(max_workers=min(4, len(refs))) as pool:
        futures = [pool.submit(_work, i, r) for i, r in enumerate(refs)]
        for fut in as_completed(futures):
            i, ref, data, mime, err = fut.result()
            slots[i] = (ref, data, mime, err)
            completed += 1
            if progress:
                try:
                    progress(min(completed / len(refs), 1.0),
                             text=f"Downloaded {completed}/{len(refs)} file(s)…")
                except Exception:
                    pass
            if err and log:
                log(f"⚠️ item {i + 1} ({ref.kind}) failed — {err}")

    seen = set()
    for i, slot in enumerate(slots):
        if slot is None:
            errors.append(f"Item {i + 1}: download did not return")
            continue
        ref, data, mime, err = slot
        if err:
            errors.append(f"Item {i + 1} ({ref.kind}): {err}")
            continue
        if not data:
            errors.append(f"Item {i + 1}: empty file")
            continue
        digest = hashlib.md5(data).hexdigest()   # dedupe identical files
        if digest in seen:
            continue
        seen.add(digest)
        items.append(_build_item(i, ref, data, mime, handle, tid))
    return items, errors


# ============================================================================
#  ORCHESTRATION
# ============================================================================

def gather_media(tid: str, handle: Optional[str], tweet_url: str,
                  include_quoted: bool, allow_ytdlp: bool,
                  log) -> Tuple[List[MediaRef], dict, str]:
    attempts: List[str] = []

    # --- 1/4 official embed (syndication) endpoint -------------------------
    try:
        log("Strategy 1/4 — official embed (syndication) endpoint…")
        payload = fetch_syndication(tid)
        refs_all, meta = parse_syndication_payload(payload)
        refs = refs_all if include_quoted else \
            [r for r in refs_all if r.scope == "main"]
        if refs:
            log(f"✅ found {len(refs)} media item(s)")
            return refs, meta, "syndication"
        if refs_all:
            return [], meta, "quoted_only"
        if payload.get("text") is not None or payload.get("id_str"):
            return [], meta, "text_only"
        attempts.append("syndication: no media in payload")
    except StrategyError as exc:
        attempts.append(f"syndication: {exc}")
        log(f"⚠️ failed — {exc}")

    # --- 2/4 + 3/4 public mirror APIs ---------------------------------------
    for step, (base, name) in enumerate(((VX_API, "vxtwitter"),
                                         (FX_API, "fxtwitter")), start=2):
        try:
            log(f"Strategy {step}/4 — {name} mirror API…")
            refs, meta = fetch_via_mirror(base, tid, handle, name)
            if refs:
                log(f"✅ found {len(refs)} media item(s)")
                return refs, meta, name
        except StrategyError as exc:
            attempts.append(f"{name}: {exc}")
            log(f"⚠️ failed — {exc}")

    # --- 4/4 yt-dlp ----------------------------------------------------------
    if allow_ytdlp:
        try:
            log("Strategy 4/4 — yt-dlp extractor…")
            target = tweet_url if tweet_url.startswith("http") else \
                f"https://x.com/i/web/status/{tid}"
            refs = fetch_via_ytdlp(target)
            if refs:
                log(f"✅ found {len(refs)} media item(s)")
                return refs, {"author": handle or "", "author_name": "",
                              "text": "", "created_at": ""}, "yt-dlp"
        except StrategyError as exc:
            attempts.append(f"yt-dlp: {exc}")
            log(f"⚠️ failed — {exc}")

    raise StrategyError(" || ".join(attempts) or "all strategies failed")


def apply_selector(refs: List[MediaRef], selector: Tuple[str, int]) -> List[MediaRef]:
    kind, idx = selector
    if kind == "photo":
        pool = [r for r in refs if r.kind == "image"]
    else:
        pool = [r for r in refs if r.kind in ("video", "gif")]
    if not pool:
        return refs
    if 1 <= idx <= len(pool):
        return [pool[idx - 1]]
    return pool


def build_zip(items: List[dict]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for it in items:
            method = zipfile.ZIP_STORED if it["type"] in ("video", "gif") \
                else zipfile.ZIP_DEFLATED
            zf.writestr(it["name"], it["data"], compress_type=method)
    return buf.getvalue()


def handle_fetch(raw_url: str, include_quoted: bool, allow_ytdlp: bool) -> None:
    for key in ("media_items", "strategy", "zip_bytes", "zip_name",
                "item_errors", "total_bytes"):
        st.session_state[key] = [] if key == "media_items" else None
    st.session_state.meta = {}
    st.session_state.status = None
    st.session_state.error_details = None

    tid, handle, selector, _ = parse_tweet_url(raw_url)
    st.session_state.tweet_id = tid

    if not tid:
        st.session_state.status = "failed"
        st.session_state.error_details = (
            "Couldn't find a post ID in that input. Paste a full link like "
            "https://x.com/username/status/1234567890123456789 (or just the ID).")
        return

    with st.status("🛰️ Contacting extraction backends…", expanded=True) as sb:
        def log(msg: str) -> None:
            st.write(msg)

        log(f"🔎 Parsed post ID `{tid}`" + (f" (from @{handle})" if handle else ""))

        try:
            refs, meta, strategy = gather_media(tid, handle, raw_url,
                                                include_quoted, allow_ytdlp, log)
        except StrategyError as exc:
            st.session_state.status = "failed"
            st.session_state.error_details = str(exc)
            sb.update(label="Extraction failed", state="error", expanded=True)
            return

        st.session_state.meta = meta
        st.session_state.strategy = strategy

        if strategy == "text_only":
            st.session_state.status = "no_media"
            sb.update(label="This post has no media", state="complete", expanded=False)
            return
        if strategy == "quoted_only":
            st.session_state.status = "quoted_only"
            sb.update(label="Only the quoted post has media",
                      state="complete", expanded=False)
            return
        if not refs:
            st.session_state.status = "failed"
            st.session_state.error_details = "No downloadable media was found."
            sb.update(label="No media found", state="error", expanded=True)
            return

        if selector:
            log(f"🎯 URL selector `/{selector[0]}/{selector[1]}` applied.")
            refs = apply_selector(refs, selector)

        log(f"⬇️ Downloading {len(refs)} file(s) straight from X's CDN…")
        bar = st.progress(0.0, text="Preparing downloads…")
        items, item_errors = download_all_refs(refs, meta.get("author", ""), tid,
                                               bar.progress, log)
        bar.empty()
        st.session_state.item_errors = item_errors

        if not items:
            st.session_state.status = "failed"
            st.session_state.error_details = ("Media was found, but every download "
                                              "failed — " + " | ".join(item_errors))
            sb.update(label="Downloads failed", state="error", expanded=True)
            return

        st.session_state.media_items = items
        st.session_state.status = "success"
        total = sum(len(it["data"]) for it in items)
        st.session_state.total_bytes = total
        if len(items) > 1 and total <= MAX_ZIP_BYTES:
            st.session_state.zip_bytes = build_zip(items)
            st.session_state.zip_name = f"tweet_{tid}_media.zip"
        sb.update(label=f"Extracted {len(items)} file(s) ✅",
                  state="complete", expanded=False)


# ============================================================================
#  UI
# ============================================================================

st.set_page_config(
    page_title="Twitter Media Downloader",
    page_icon="🐦",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .block-container { padding-top: 3rem; padding-bottom: 2rem; max-width: 900px; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    .main-title {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-weight: 800; font-size: 2.5rem; color: #0F1419;
        text-align: center; margin-bottom: 0.5rem;
    }
    .sub-title { text-align: center; color: #536471; font-size: 1.1rem; margin-bottom: 2.5rem; }

    .stTextInput > div > div > input {
        border-radius: 16px !important; padding: 16px 20px !important;
        font-size: 16px !important; border: 2px solid #EFF3F4 !important;
        background-color: #EFF3F4 !important; color: #0F1419 !important;
        transition: all 0.2s ease-in-out !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: #1DA1F2 !important; background-color: #ffffff !important;
        box-shadow: 0 0 0 4px rgba(29, 161, 242, 0.1) !important;
    }

    div.stButton > button:first-child {
        background-color: #0F1419; color: white; font-size: 16px; font-weight: 700;
        padding: 12px 24px; border: none; border-radius: 9999px; width: 100%;
        transition: background-color 0.2s ease, transform 0.1s ease;
    }
    div.stButton > button:first-child:hover { background-color: #272C30; color: white; }
    div.stButton > button:first-child:active { transform: scale(0.98); }

    div.stDownloadButton > button:first-child {
        background-color: #1DA1F2; color: white; font-size: 15px; font-weight: 700;
        padding: 10px 20px; border: none; border-radius: 9999px; width: 100%;
        box-shadow: 0 4px 12px rgba(29, 161, 242, 0.2);
        transition: background-color 0.2s ease, transform 0.1s ease; margin-top: 10px;
    }
    div.stDownloadButton > button:first-child:hover { background-color: #1A8CD8; color: white; }
    div.stDownloadButton > button:first-child:active { transform: scale(0.98); }

    .media-card {
        background: #ffffff; border-radius: 16px; padding: 15px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06); border: 1px solid #EFF3F4;
        margin-bottom: 20px;
    }

    @media (prefers-color-scheme: dark) {
        .main-title { color: #E7E9EA; }
        .sub-title { color: #71767B; }
        .stTextInput > div > div > input {
            background-color: #202327 !important; border-color: #202327 !important;
            color: #E7E9EA !important;
        }
        .stTextInput > div > div > input:focus { background-color: #000000 !important; }
        div.stButton > button:first-child { background-color: #EFF3F4; color: #0F1419; }
        div.stButton > button:first-child:hover { background-color: #D7DBDC; color: #0F1419; }
        .media-card { background: #15202B; border: 1px solid #38444D; }
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">X / Twitter Downloader 🐦</div>',
            unsafe_allow_html=True)
st.markdown('<div class="sub-title">Download videos, GIFs and images from any public '
            'post — no login, no cookies.</div>', unsafe_allow_html=True)

if "media_items" not in st.session_state:
    st.session_state.media_items = []
    st.session_state.meta = {}
    st.session_state.strategy = None
    st.session_state.tweet_id = None
    st.session_state.status = None
    st.session_state.error_details = None
    st.session_state.item_errors = []
    st.session_state.zip_bytes = None
    st.session_state.zip_name = None
    st.session_state.total_bytes = None

st.write("")
tweet_url = st.text_input(
    "URL Input",
    placeholder="Paste X/Twitter link here… (e.g., https://x.com/user/status/123)",
    label_visibility="collapsed")
st.caption("Accepts x.com / twitter.com / fixupx / fxtwitter / vxtwitter links, "
           "`/photo/N` & `/video/N` selectors, t.co shortlinks, or a bare post ID.")

col1, col2 = st.columns([3, 1])
with col1:
    show_preview = st.toggle("Show media previews", value=True,
                             help="Display media before downloading.")
with col2:
    fetch_clicked = st.button("Get Media")

with st.expander("⚙️ Advanced options"):
    c1, c2 = st.columns(2)
    with c1:
        include_quoted = st.toggle(
            "Include quoted post media", value=True,
            help="Also grab photos/videos from the post being quoted.")
    with c2:
        allow_ytdlp = st.toggle(
            "yt-dlp last-resort fallback", value=False,
            help="X now usually demands login cookies for yt-dlp, so this rarely "
                 "helps — kept as a final fallback.")

st.markdown("<br>", unsafe_allow_html=True)

if fetch_clicked:
    if not tweet_url.strip():
        st.warning("⚠️ Please enter a valid URL.")
    else:
        handle_fetch(tweet_url, include_quoted, allow_ytdlp)

st.markdown("---")

# ---------------------------------------------------------------- results ---
if st.session_state.status == "success":
    items = st.session_state.media_items
    meta = st.session_state.get("meta") or {}
    author = meta.get("author") or ""
    strategy = st.session_state.get("strategy") or "unknown"

    st.success(f"✅ **Successfully extracted {len(items)} media item(s)!**")
    cap_bits = []
    if author:
        cap_bits.append(f"@{author}")
    cap_bits += [f"fetched via **{strategy}**", "no login or cookies used"]
    st.caption(" · ".join(cap_bits))

    with st.expander("🧾 Post details", expanded=False):
        if meta.get("text"):
            st.text(meta["text"])
        if meta.get("created_at"):
            st.caption(f"Posted: {meta['created_at']}")
        tid = st.session_state.tweet_id
        link = (f"https://x.com/{author}/status/{tid}" if author
                else f"https://x.com/i/web/status/{tid}")
        st.markdown(f"[Open original post ↗]({link})")

    st.write("")

    cols = st.columns(2)
    for idx, item in enumerate(items):
        with cols[idx % 2]:
            st.markdown('<div class="media-card">', unsafe_allow_html=True)
            m = item["meta"]

            title_bits = [KIND_LABEL.get(item["type"], item["type"])]
            if m.get("scope") == "quoted":
                title_bits.append("from quoted post")
            st.markdown("**" + " · ".join(title_bits) + "**")

            badges = []
            if m.get("width") and m.get("height"):
                badges.append(f"{m['width']}×{m['height']}")
            if m.get("duration_s"):
                badges.append(f"{m['duration_s']:g}s")
            if m.get("bitrate_kbps"):
                badges.append(f"~{m['bitrate_kbps']} kbps")
            if m.get("size_mb") is not None:
                badges.append(f"{m['size_mb']} MB")
            if badges:
                st.caption("  ·  ".join(badges))

            if show_preview:
                if item["type"] in ("video", "gif"):
                    if len(item["data"]) <= MAX_PREVIEW_BYTES:
                        st.video(item["data"])
                    else:
                        st.info("Preview hidden (>60 MB) — use the download button.")
                else:
                    st.image(item["data"])
            else:
                icon = "🎥" if item["type"] in ("video", "gif") else "📸"
                st.markdown(
                    f"<div style='text-align:center;padding:24px;'><h3>{icon}</h3></div>",
                    unsafe_allow_html=True)

            if m.get("alt"):
                st.caption(f"🖼️ ALT text: {m['alt']}")
            if m.get("note"):
                st.caption(m["note"])

            st.download_button(
                label=f"Download {KIND_LABEL.get(item['type'], 'File')}",
                data=item["data"],
                file_name=item["name"],
                mime=item["mime"],
                key=f"dl_{idx}_{st.session_state.tweet_id}")
            st.caption(item["name"])
            st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.get("item_errors"):
        with st.expander(f"⚠️ {len(st.session_state['item_errors'])} item(s) "
                         "could not be downloaded"):
            for e in st.session_state["item_errors"]:
                st.write(f"- {e}")

    if st.session_state.get("zip_bytes"):
        st.write("")
        st.download_button(
            label=f"⬇️ Download all {len(items)} file(s) as ZIP",
            data=st.session_state.zip_bytes,
            file_name=st.session_state.get("zip_name") or "twitter_media.zip",
            mime="application/zip")
    elif len(items) > 1 and (st.session_state.get("total_bytes") or 0) > MAX_ZIP_BYTES:
        st.caption("📦 ZIP bundle skipped — combined size exceeds 400 MB. "
                   "Use the individual buttons instead.")

elif st.session_state.status == "no_media":
    st.info("📝 This post was fetched successfully, but it contains no photos "
            "or videos (text-only).")
elif st.session_state.status == "quoted_only":
    st.info("📝 This post has no media of its own — enable 'Include quoted post "
            "media' in Advanced options to grab the quoted post's media.")
elif st.session_state.status == "failed":
    st.error("🚫 **Could not fetch this post.** Most likely causes: the account "
             "is private/protected, the post was deleted, the link is wrong, or "
             "X is temporarily rate-limiting this server. Every backend was "
             "already tried automatically.")
    with st.expander("🔍 Technical details"):
        st.code(st.session_state.error_details or "No details captured.")

# ----------------------------------------------------------------- footer ---
st.markdown("<br><br>", unsafe_allow_html=True)

cc_col1, cc_col2, cc_col3 = st.columns([1, 1, 1])
with cc_col2:
    if st.button("Clear Cache"):
        for key in ("media_items", "meta", "strategy", "tweet_id", "status",
                    "error_details", "item_errors", "zip_bytes", "zip_name",
                    "total_bytes"):
            st.session_state.pop(key, None)
        st.session_state.media_items = []
        st.rerun()

st.caption("ℹ️ **Note:** No login or cookies required — media is pulled straight "
           "from X's public embed endpoint and CDN. If all backends fail at once, "
           "X is likely rate-limiting this server's IP; wait a minute and retry.")
st.markdown('<div style="text-align: center;"><a href="https://github.com/JustToTryModels/'
            'Twitter-Downloader/blob/main/app.py" target="_blank" style="color: #536471; '
            'text-decoration: none; font-size: 14px;">View Source Code on GitHub 💻</a></div>',
            unsafe_allow_html=True)
