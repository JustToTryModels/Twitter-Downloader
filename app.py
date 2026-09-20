from concurrent.futures import ThreadPoolExecutor
import io
import re
import urllib.parse
import zipfile
from typing import Any, Dict, List, Optional
import requests
import streamlit as st
import yt_dlp

# --- Streamlit Page Setup ---
st.set_page_config(
    page_title="Pro X/Twitter Downloader",
    page_icon="🐦",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# --- High-Performance CSS ---
st.markdown(
    """
<style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 800px;
    }
    #MainMenu, footer, header {visibility: hidden;}

    .main-title {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-weight: 900;
        font-size: 2.5rem;
        text-align: center;
        letter-spacing: -0.5px;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        text-align: center;
        color: #71767B;
        font-size: 1.05rem;
        margin-bottom: 1.8rem;
    }
    
    /* Input Box */
    .stTextInput > div > div > input {
        border-radius: 14px !important;
        padding: 14px 18px !important;
        font-size: 16px !important;
        background-color: #F7F9F9 !important;
        border: 2px solid #E1E8ED !important;
        transition: all 0.2s ease;
    }
    .stTextInput > div > div > input:focus {
        border-color: #1DA1F2 !important;
        background-color: #ffffff !important;
        box-shadow: 0 0 0 3px rgba(29, 161, 242, 0.15) !important;
    }
    
    /* Tweet Card */
    .tweet-card {
        background: #ffffff;
        border: 1px solid #E1E8ED;
        border-radius: 16px;
        padding: 20px;
        margin: 20px 0;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    .tweet-author {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 12px;
    }
    .tweet-avatar {
        width: 44px;
        height: 44px;
        border-radius: 50%;
        background-color: #E1E8ED;
    }
    .tweet-text {
        font-size: 1.05rem;
        line-height: 1.5;
        color: #0F1419;
        margin-bottom: 10px;
        white-space: pre-wrap;
        word-break: break-word;
    }
    
    /* Media Cards */
    .media-card {
        background: #ffffff;
        border: 1px solid #EFF3F4;
        border-radius: 14px;
        padding: 14px;
        margin-bottom: 15px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    
    /* Action Buttons */
    div.stButton > button {
        border-radius: 9999px !important;
        font-weight: 700 !important;
        padding: 12px 24px !important;
        background-color: #0F1419 !important;
        color: white !important;
        border: none !important;
        transition: 0.2s;
    }
    div.stButton > button:hover {
        background-color: #272C30 !important;
    }
    div.stDownloadButton > button {
        border-radius: 9999px !important;
        font-weight: 700 !important;
        background-color: #1DA1F2 !important;
        color: white !important;
        border: none !important;
        width: 100% !important;
    }
    div.stDownloadButton > button:hover {
        background-color: #1A8CD8 !important;
    }

    /* Dark Mode */
    @media (prefers-color-scheme: dark) {
        .tweet-card {
            background: #16181C;
            border-color: #2F3336;
        }
        .tweet-text { color: #E7E9EA; }
        .media-card {
            background: #16181C;
            border-color: #2F3336;
        }
        .stTextInput > div > div > input {
            background-color: #202327 !important;
            border-color: #2F3336 !important;
            color: #E7E9EA !important;
        }
        div.stButton > button {
            background-color: #EFF3F4 !important;
            color: #0F1419 !important;
        }
        div.stButton > button:hover {
            background-color: #D7DBDC !important;
        }
    }
</style>
""",
    unsafe_allow_html=True,
)


# --- Core Twitter Extraction Engine ---
class TwitterMediaEngine:
    @staticmethod
    def extract_status_id(url: str) -> Optional[str]:
        """Extract status ID from any Twitter/X URL format."""
        match = re.search(r"(?:twitter\.com|x\.com)/[^/]+/status/(\d+)", url)
        return match.group(1) if match else None

    @classmethod
    def get_highest_resolution_image_url(cls, url: str) -> str:
        """Forces Twitter image URLs to point to their uncompressed original upload."""
        if "twimg.com" in url:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            base_url = url.split("?")[0]
            
            ext = "jpg"
            if "format" in qs and qs["format"]:
                ext = qs["format"][0]
            else:
                ext_match = re.search(r"\.(jpg|jpeg|png|webp)$", base_url, re.IGNORECASE)
                if ext_match:
                    ext = ext_match.group(1)
            
            base_clean = re.sub(r"\.(jpg|jpeg|png|webp)$", "", base_url, flags=re.IGNORECASE)
            return f"{base_clean}?format={ext}&name=orig"
        return url

    @classmethod
    def fetch_via_tier1_fxtwitter(cls, tweet_id: str) -> Optional[Dict[str, Any]]:
        """Tier 1: Query FxTwitter/FixTweet API."""
        try:
            endpoint = f"https://api.fxtwitter.com/status/{tweet_id}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            resp = requests.get(endpoint, headers=headers, timeout=6)
            if resp.status_code != 200:
                return None
            data = resp.json()
            tweet = data.get("tweet")
            if not tweet:
                return None

            media_list = []
            if "media" in tweet and "photos" in tweet["media"]:
                for p in tweet["media"]["photos"]:
                    orig_url = cls.get_highest_resolution_image_url(p.get("url", ""))
                    ext = "png" if "format=png" in orig_url.lower() or ".png" in orig_url.lower() else "jpg"
                    media_list.append({
                        "type": "image",
                        "url": orig_url,
                        "thumbnail": orig_url,
                        "filename": f"tweet_{tweet_id}_{len(media_list)+1}.{ext}"
                    })

            if "media" in tweet and "videos" in tweet["media"]:
                for v in tweet["media"]["videos"]:
                    media_list.append({
                        "type": "video",
                        "url": v.get("url"),
                        "thumbnail": v.get("thumbnail_url"),
                        "filename": f"tweet_{tweet_id}_{len(media_list)+1}.mp4"
                    })

            return {
                "author_name": tweet.get("author", {}).get("name", "Unknown"),
                "author_screen": tweet.get("author", {}).get("screen_name", "unknown"),
                "author_avatar": tweet.get("author", {}).get("avatar_url", ""),
                "text": tweet.get("text", ""),
                "media": media_list,
                "tier": "FxTwitter CDN Engine"
            }
        except Exception:
            return None

    @classmethod
    def fetch_via_tier2_syndication(cls, tweet_id: str) -> Optional[Dict[str, Any]]:
        """Tier 2: Query Twitter's official embedded widget CDN."""
        try:
            token = (int(tweet_id) / 1e15) * 3.141592653589793
            endpoint = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token={token}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://platform.twitter.com/",
            }
            resp = requests.get(endpoint, headers=headers, timeout=6)
            if resp.status_code != 200:
                return None
            data = resp.json()

            media_list = []
            for p in data.get("photos", []):
                orig_url = cls.get_highest_resolution_image_url(p.get("url", ""))
                ext = "png" if "format=png" in orig_url.lower() or ".png" in orig_url.lower() else "jpg"
                media_list.append({
                    "type": "image",
                    "url": orig_url,
                    "thumbnail": orig_url,
                    "filename": f"tweet_{tweet_id}_{len(media_list)+1}.{ext}"
                })

            if "video" in data:
                variants = data["video"].get("variants", [])
                mp4_variants = [v for v in variants if v.get("type") == "video/mp4" or "video/mp4" in v.get("src", "")]
                if mp4_variants:
                    best_variant = max(mp4_variants, key=lambda x: x.get("bitrate", 0))
                    media_list.append({
                        "type": "video",
                        "url": best_variant.get("src"),
                        "thumbnail": data["video"].get("poster"),
                        "filename": f"tweet_{tweet_id}_{len(media_list)+1}.mp4"
                    })

            return {
                "author_name": data.get("user", {}).get("name", "Unknown"),
                "author_screen": data.get("user", {}).get("screen_name", "unknown"),
                "author_avatar": data.get("user", {}).get("profile_image_url_https", ""),
                "text": data.get("text", ""),
                "media": media_list,
                "tier": "Syndication API Core"
            }
        except Exception:
            return None

    @classmethod
    def fetch_via_tier3_vxtwitter(cls, tweet_id: str) -> Optional[Dict[str, Any]]:
        """Tier 3: Query VxTwitter API."""
        try:
            endpoint = f"https://api.vxtwitter.com/Twitter/status/{tweet_id}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            resp = requests.get(endpoint, headers=headers, timeout=6)
            if resp.status_code != 200:
                return None
            data = resp.json()

            media_list = []
            for item in data.get("media_extended", []):
                m_type = "video" if item.get("type") in ["video", "gif"] else "image"
                url = item.get("url")
                if m_type == "image":
                    url = cls.get_highest_resolution_image_url(url)
                    ext = "png" if "format=png" in url.lower() or ".png" in url.lower() else "jpg"
                else:
                    ext = "mp4"

                media_list.append({
                    "type": m_type,
                    "url": url,
                    "thumbnail": item.get("thumbnail_url", url),
                    "filename": f"tweet_{tweet_id}_{len(media_list)+1}.{ext}"
                })

            return {
                "author_name": data.get("user_name", "Unknown"),
                "author_screen": data.get("user_screen_name", "unknown"),
                "author_avatar": "",
                "text": data.get("text", ""),
                "media": media_list,
                "tier": "VxTwitter Edge Resolver"
            }
        except Exception:
            return None

    @classmethod
    def fetch_via_tier4_ytdlp(cls, url: str, tweet_id: str) -> Optional[Dict[str, Any]]:
        """Tier 4: In-memory yt-dlp resolver."""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extractor_args": {"twitter": {"api": ["syndication"]}},
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return None

                media_list = []
                formats = info.get("formats", [])
                mp4_formats = [f for f in formats if f.get("ext") == "mp4" and f.get("url")]
                if mp4_formats:
                    best = max(mp4_formats, key=lambda x: (x.get("tbr") or 0, x.get("height") or 0))
                    media_list.append({
                        "type": "video",
                        "url": best["url"],
                        "thumbnail": info.get("thumbnail"),
                        "filename": f"tweet_{tweet_id}_1.mp4"
                    })

                return {
                    "author_name": info.get("uploader", "Twitter User"),
                    "author_screen": info.get("uploader_id", "user"),
                    "author_avatar": "",
                    "text": info.get("description", ""),
                    "media": media_list,
                    "tier": "In-Memory yt-dlp Core"
                }
        except Exception:
            return None

    @classmethod
    def resolve_all(cls, raw_url: str) -> Dict[str, Any]:
        """Tries all tiers sequentially until media is resolved."""
        tweet_id = cls.extract_status_id(raw_url)
        if not tweet_id:
            return {"success": False, "error": "Invalid Twitter/X URL. Make sure it contains `/status/<ID>`."}

        tiers = [
            lambda: cls.fetch_via_tier1_fxtwitter(tweet_id),
            lambda: cls.fetch_via_tier2_syndication(tweet_id),
            lambda: cls.fetch_via_tier3_vxtwitter(tweet_id),
            lambda: cls.fetch_via_tier4_ytdlp(raw_url, tweet_id),
        ]

        for tier_func in tiers:
            result = tier_func()
            if result and result.get("media") and len(result["media"]) > 0:
                result["success"] = True
                result["tweet_id"] = tweet_id
                return result

        return {
            "success": False,
            "error": "Could not extract media. The post might contain only text, is private, or has been deleted."
        }


# --- High-Speed Parallel Asset Pre-fetcher ---
def prefetch_media_in_parallel(media_items: List[Dict[str, Any]]) -> Dict[str, bytes]:
    """Downloads all media assets concurrently using thread workers for 0ms download response."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://twitter.com/",
    })

    def fetch_item(item):
        try:
            r = session.get(item["url"], timeout=15)
            if r.status_code == 200:
                return item["url"], r.content
        except Exception:
            pass
        return item["url"], b""

    results = {}
    with ThreadPoolExecutor(max_workers=min(len(media_items), 8)) as executor:
        for url, data in executor.map(fetch_item, media_items):
            if data:
                results[url] = data
    return results


def build_zip_package(media_items: List[Dict[str, Any]], binaries: Dict[str, bytes]) -> bytes:
    """Pre-packs media items into an in-memory ZIP package instantly."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for item in media_items:
            content = binaries.get(item["url"])
            if content:
                zip_file.writestr(item["filename"], content)
    zip_buffer.seek(0)
    return zip_buffer.getvalue()


# --- Presentation Layer ---
st.markdown('<div class="main-title">X / Twitter Media Downloader 🐦</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">High-res uncompressed media extractor with 4-tier failover.</div>', unsafe_allow_html=True)

# 1. Row 1: Link Section
tweet_url = st.text_input(
    "Twitter / X Post URL",
    placeholder="https://x.com/username/status/123456789...",
    label_visibility="collapsed"
)

# 2. Row 2: Show Media Previews
show_previews = st.checkbox("Show Media Previews", value=True)

# 3. Row 3: Extract Media Button
fetch_btn = st.button("Extract Media", use_container_width=True)

if fetch_btn:
    if not tweet_url.strip():
        st.warning("Please provide a valid tweet URL.")
    else:
        with st.spinner("Resolving media links and buffering assets..."):
            engine_result = TwitterMediaEngine.resolve_all(tweet_url.strip())
            st.session_state["result"] = engine_result

            # Pre-fetch all binary assets in parallel for ultra-responsive instant downloads
            if engine_result.get("success"):
                binaries = prefetch_media_in_parallel(engine_result["media"])
                st.session_state["binaries"] = binaries
                if len(engine_result["media"]) > 1:
                    st.session_state["zip_data"] = build_zip_package(engine_result["media"], binaries)

# --- Render Results (When Media is Loaded) ---
if "result" in st.session_state:
    res = st.session_state["result"]

    if not res.get("success"):
        st.error(f"❌ {res.get('error', 'Unknown error occurred.')}")
    else:
        media_count = len(res["media"])
        binaries = st.session_state.get("binaries", {})

        st.success(f"Successfully extracted {media_count} media item(s) via **{res['tier']}**!")

        # Tweet Card Display
        avatar_html = f'<img src="{res["author_avatar"]}" class="tweet-avatar">' if res.get("author_avatar") else ""
        st.markdown(
            f"""
            <div class="tweet-card">
                <div class="tweet-author">
                    {avatar_html}
                    <div>
                        <div style="font-weight: 700; color: inherit;">{res['author_name']}</div>
                        <div style="color: #71767B; font-size: 0.9rem;">@{res['author_screen']}</div>
                    </div>
                </div>
                <div class="tweet-text">{res['text']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Batch Download ZIP (if multiple media)
        if media_count > 1 and "zip_data" in st.session_state:
            st.download_button(
                label=f"📦 Download All Media ({media_count} items) as .ZIP",
                data=st.session_state["zip_data"],
                file_name=f"twitter_{res['tweet_id']}_all.zip",
                mime="application/zip",
                use_container_width=True,
                key=f"zip_dl_{res['tweet_id']}"
            )
            st.write("")

        # Media Grid
        grid_cols = st.columns(2) if media_count > 1 else [st.container()]

        for idx, item in enumerate(res["media"]):
            target_col = grid_cols[idx % 2] if media_count > 1 else grid_cols[0]
            with target_col:
                st.markdown('<div class="media-card">', unsafe_allow_html=True)
                
                # Fetch cached bytes from RAM
                binary_data = binaries.get(item["url"])

                # Determine MIME type
                if item["type"] == "video":
                    mime_type = "video/mp4"
                elif item["filename"].endswith(".png"):
                    mime_type = "image/png"
                elif item["filename"].endswith(".webp"):
                    mime_type = "image/webp"
                else:
                    mime_type = "image/jpeg"

                # Previews (Direct browser loading for maximum speed)
                if show_previews:
                    if item["type"] == "video":
                        st.video(binary_data if binary_data else item["url"])
                    else:
                        st.image(binary_data if binary_data else item["url"], use_container_width=True)

                # Download button (Immediate memory serving)
                if binary_data:
                    st.download_button(
                        label=f"⬇️ Download {item['type'].upper()} ({idx+1}/{media_count})",
                        data=binary_data,
                        file_name=item["filename"],
                        mime=mime_type,
                        key=f"dl_btn_{res['tweet_id']}_{idx}",
                        use_container_width=True
                    )
                else:
                    st.markdown(f"[🔗 Direct Media Download Link]({item['url']})")

                st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<hr style='margin-top: 2rem; margin-bottom: 1.5rem; opacity: 0.2;'>", unsafe_allow_html=True)

        # Clear Cache Button: ONLY displayed at the very bottom when media is loaded
        if st.button("🗑️ Clear Cache & Reset", use_container_width=True):
            st.cache_data.clear()
            for key in ["result", "binaries", "zip_data"]:
                st.session_state.pop(key, None)
            st.rerun()
