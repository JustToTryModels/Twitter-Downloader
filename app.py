import html
import re
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
        padding-bottom: 2.5rem;
        max-width: 760px;
    }
    #MainMenu, footer, header {visibility: hidden;}

    .main-title {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-weight: 900;
        font-size: 2.4rem;
        text-align: center;
        letter-spacing: -0.5px;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        text-align: center;
        color: #71767B;
        font-size: 1rem;
        margin-bottom: 1.6rem;
    }
    
    /* Input Box */
    .stTextInput > div > div > input {
        border-radius: 12px !important;
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
        padding: 18px 20px;
        margin: 18px 0;
        box-shadow: 0 3px 10px rgba(0,0,0,0.03);
    }
    .tweet-author {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 10px;
    }
    .tweet-avatar {
        width: 44px;
        height: 44px;
        border-radius: 50%;
        background-color: #E1E8ED;
        object-fit: cover;
    }
    .tweet-text {
        font-size: 1.02rem;
        line-height: 1.45;
        color: #0F1419;
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
    
    /* Standard Buttons */
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

    /* Download Buttons */
    div.stDownloadButton > button {
        border-radius: 9999px !important;
        font-weight: 700 !important;
        background-color: #00BA7C !important;
        color: white !important;
        border: none !important;
        width: 100% !important;
    }
    div.stDownloadButton > button:hover {
        background-color: #009e69 !important;
    }

    /* Client-Side Image Download Button */
    .dl-btn-container {
        margin-top: 8px;
    }
    .instant-dl-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        background-color: #1DA1F2;
        color: #ffffff !important;
        font-weight: 700;
        font-size: 0.95rem;
        padding: 11px 16px;
        border-radius: 9999px;
        border: none;
        cursor: pointer;
        text-decoration: none !important;
        transition: background-color 0.2s ease;
        box-sizing: border-box;
    }
    .instant-dl-btn:hover {
        background-color: #1A8CD8;
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


# --- Core Twitter Extraction Engine (Metadata Only - 0 Media Data Transferred) ---
class TwitterMediaEngine:
    @staticmethod
    def extract_status_id(url: str) -> Optional[str]:
        """Extract status ID from any Twitter/X URL format."""
        match = re.search(r"(?:twitter\.com|x\.com)/[^/]+/status/(\d+)", url)
        return match.group(1) if match else None

    @classmethod
    def get_highest_resolution_image_url(cls, url: str) -> str:
        """Forces Twitter image URLs to point directly to original uncompressed uploads."""
        if "twimg.com" in url:
            base = url.split("?")[0]
            ext_match = re.search(r"\.(jpg|jpeg|png|webp)$", base, re.IGNORECASE)
            ext = ext_match.group(1) if ext_match else "jpg"
            clean_base = re.sub(r"\.(jpg|jpeg|png|webp)$", "", base, flags=re.IGNORECASE)
            return f"{clean_base}?format={ext}&name=orig"
        return url

    @classmethod
    def fetch_via_tier1_fxtwitter(cls, tweet_id: str) -> Optional[Dict[str, Any]]:
        """Tier 1: Query FxTwitter API."""
        try:
            endpoint = f"https://api.fxtwitter.com/status/{tweet_id}"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(endpoint, headers=headers, timeout=5)
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
                    ext = "png" if "format=png" in orig_url.lower() else "jpg"
                    media_list.append({
                        "type": "image",
                        "url": orig_url,
                        "filename": f"tweet_{tweet_id}_{len(media_list)+1}.{ext}"
                    })

            if "media" in tweet and "videos" in tweet["media"]:
                for v in tweet["media"]["videos"]:
                    media_list.append({
                        "type": "video",
                        "url": v.get("url"),
                        "filename": f"tweet_{tweet_id}_{len(media_list)+1}.mp4"
                    })

            return {
                "author_name": tweet.get("author", {}).get("name", "Twitter User"),
                "author_screen": tweet.get("author", {}).get("screen_name", "user"),
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
            resp = requests.get(endpoint, headers=headers, timeout=5)
            if resp.status_code != 200:
                return None
            data = resp.json()

            media_list = []
            for p in data.get("photos", []):
                orig_url = cls.get_highest_resolution_image_url(p.get("url", ""))
                ext = "png" if "format=png" in orig_url.lower() else "jpg"
                media_list.append({
                    "type": "image",
                    "url": orig_url,
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
                        "filename": f"tweet_{tweet_id}_{len(media_list)+1}.mp4"
                    })

            return {
                "author_name": data.get("user", {}).get("name", "Twitter User"),
                "author_screen": data.get("user", {}).get("screen_name", "user"),
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
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(endpoint, headers=headers, timeout=5)
            if resp.status_code != 200:
                return None
            data = resp.json()

            media_list = []
            for item in data.get("media_extended", []):
                m_type = "video" if item.get("type") in ["video", "gif"] else "image"
                url = item.get("url")
                if m_type == "image":
                    url = cls.get_highest_resolution_image_url(url)
                    ext = "png" if ".png" in url.lower() else "jpg"
                else:
                    ext = "mp4"

                media_list.append({
                    "type": m_type,
                    "url": url,
                    "filename": f"tweet_{tweet_id}_{len(media_list)+1}.{ext}"
                })

            return {
                "author_name": data.get("user_name", "Twitter User"),
                "author_screen": data.get("user_screen_name", "user"),
                "author_avatar": "",
                "text": data.get("text", ""),
                "media": media_list,
                "tier": "VxTwitter Edge Resolver"
            }
        except Exception:
            return None

    @classmethod
    def fetch_via_tier4_ytdlp(cls, url: str, tweet_id: str) -> Optional[Dict[str, Any]]:
        """Tier 4: In-memory yt-dlp metadata resolver."""
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
        """Tries all tiers sequentially to extract only metadata."""
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


# --- Video Stream Proxy Engine (Bypasses Twitter CORS) ---
def fetch_video_binary(url: str) -> Optional[bytes]:
    """Streams video bytes through Python to avoid browser CORS blocks."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://twitter.com/",
    }
    try:
        r = requests.get(url, headers=headers, stream=True, timeout=25)
        if r.status_code == 200:
            return r.content
    except Exception:
        pass
    return None


# --- Client-Side High-Speed Image Downloader ---
def render_instant_image_download_button(url: str, filename: str, label: str) -> str:
    """Zero-server-bandwidth client-side image downloader."""
    safe_url = html.escape(url)
    safe_filename = html.escape(filename)
    safe_label = html.escape(label)
    btn_id = "btn_" + re.sub(r"\W+", "_", filename)

    return f"""
    <div class="dl-btn-container">
        <button id="{btn_id}" class="instant-dl-btn" onclick="downloadImageDirect('{safe_url}', '{safe_filename}', '{btn_id}', '{safe_label}')">
            ⬇️ {safe_label}
        </button>
    </div>
    <script>
    function downloadImageDirect(url, filename, btnId, origLabel) {{
        const btn = document.getElementById(btnId);
        btn.innerText = "⏳ Saving...";
        btn.disabled = true;

        fetch(url, {{ mode: 'cors' }})
            .then(res => {{
                if (!res.ok) throw new Error('Network response was not ok');
                return res.blob();
            }})
            .then(blob => {{
                const blobUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = blobUrl;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(blobUrl);
                document.body.removeChild(a);

                btn.innerText = "✅ Saved!";
                btn.style.backgroundColor = "#00BA7C";
                setTimeout(() => {{
                    btn.innerText = "⬇️ " + origLabel;
                    btn.style.backgroundColor = "#1DA1F2";
                    btn.disabled = false;
                }}, 2500);
            }})
            .catch(() => {{
                // Direct fallback
                const a = document.createElement('a');
                a.href = url;
                a.target = '_blank';
                a.download = filename;
                a.click();
                btn.innerText = "⬇️ " + origLabel;
                btn.disabled = false;
            }});
    }}
    </script>
    """


# --- Presentation Layer ---
st.markdown('<div class="main-title">X / Twitter Media Downloader 🐦</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">High-speed media extractor with zero-waste data streaming.</div>', unsafe_allow_html=True)

# 1. Row 1: Link Section
tweet_url = st.text_input(
    "Twitter / X Post URL",
    placeholder="https://x.com/username/status/123456789...",
    label_visibility="collapsed"
)

# 2. Row 2: Show Media Previews Checkbox
show_previews = st.checkbox("Show Media Previews", value=True)

# 3. Row 3: Extract Media Button
fetch_btn = st.button("Extract Media", use_container_width=True)

if fetch_btn:
    if not tweet_url.strip():
        st.warning("Please provide a valid tweet URL.")
    else:
        with st.spinner("Resolving media links..."):
            engine_result = TwitterMediaEngine.resolve_all(tweet_url.strip())
            st.session_state["result"] = engine_result
            # Clear previous video cache when extracting a new tweet
            st.session_state.pop("video_cache", None)

# --- Render Results ---
if "result" in st.session_state:
    res = st.session_state["result"]

    if not res.get("success"):
        st.error(f"❌ {res.get('error', 'Unknown error occurred.')}")
    else:
        media_count = len(res["media"])
        st.success(f"Found {media_count} media item(s) via **{res['tier']}**!")

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

        # Media Items Grid
        grid_cols = st.columns(2) if media_count > 1 else [st.container()]

        for idx, item in enumerate(res["media"]):
            target_col = grid_cols[idx % 2] if media_count > 1 else grid_cols[0]
            with target_col:
                st.markdown('<div class="media-card">', unsafe_allow_html=True)
                
                # Previews (Only streamed when checkbox is ON)
                if show_previews:
                    if item["type"] == "video":
                        st.video(item["url"])
                    else:
                        st.image(item["url"], use_container_width=True)

                # --- High-Speed Downloads ---
                btn_label = f"Download {item['type'].upper()} ({idx+1}/{media_count})"

                if item["type"] == "image":
                    # Instant client-side direct download (Zero server bandwidth)
                    img_html = render_instant_image_download_button(item["url"], item["filename"], btn_label)
                    st.components.v1.html(img_html, height=50)

                else:
                    # Video: Bypasses Twitter CORS by downloading directly as a true .mp4 file
                    video_cache = st.session_state.setdefault("video_cache", {})
                    cache_key = item["url"]

                    if cache_key in video_cache:
                        # Video file ready in memory: Save to disk
                        st.download_button(
                            label=f"💾 Save {item['filename']} to Device",
                            data=video_cache[cache_key],
                            file_name=item["filename"],
                            mime="video/mp4",
                            key=f"dl_ready_{res['tweet_id']}_{idx}",
                            use_container_width=True
                        )
                    else:
                        # Fetches only this video on-demand (Does not touch images or other videos)
                        if st.button(f"⬇️ {btn_label}", key=f"fetch_vid_{res['tweet_id']}_{idx}", use_container_width=True):
                            with st.spinner("Downloading video file from X CDN..."):
                                vid_bytes = fetch_video_binary(item["url"])
                                if vid_bytes:
                                    video_cache[cache_key] = vid_bytes
                                    st.rerun()
                                else:
                                    st.error("Could not download video. Stream may be restricted.")

                st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<hr style='margin-top: 2rem; margin-bottom: 1.5rem; opacity: 0.2;'>", unsafe_allow_html=True)

        # Clear Cache Button: ONLY displayed at the very bottom when media is loaded
        if st.button("🗑️ Clear Cache & Reset", use_container_width=True):
            st.cache_data.clear()
            st.session_state.clear()
            st.rerun()
