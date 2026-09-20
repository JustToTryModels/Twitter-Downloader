import streamlit as st
import os
import re
import math
import glob
import mimetypes
import hashlib
import tempfile
import subprocess
import requests
import io

# --- Page Configuration ---
st.set_page_config(
    page_title="Twitter Media Downloader", 
    page_icon="🐦", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- Custom CSS for Premium UI ---
st.markdown("""
<style>
    /* Main container padding */
    .block-container {
        padding-top: 3rem;
        padding-bottom: 2rem;
        max-width: 900px;
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Typography and Header */
    .main-title {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-weight: 800;
        font-size: 2.5rem;
        color: #0F1419;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-title {
        text-align: center;
        color: #536471;
        font-size: 1.1rem;
        margin-bottom: 2.5rem;
    }

    /* Input Field Styling */
    .stTextInput > div > div > input {
        border-radius: 16px !important;
        padding: 16px 20px !important;
        font-size: 16px !important;
        border: 2px solid #EFF3F4 !important;
        background-color: #EFF3F4 !important;
        color: #0F1419 !important;
        transition: all 0.2s ease-in-out !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: #1DA1F2 !important;
        background-color: #ffffff !important;
        box-shadow: 0 0 0 4px rgba(29, 161, 242, 0.1) !important;
    }

    /* Primary Action Button (Fetch) */
    div.stButton > button:first-child {
        background-color: #0F1419;
        color: white;
        font-size: 16px;
        font-weight: 700;
        padding: 12px 24px;
        border: none;
        border-radius: 9999px; /* Perfect pill shape */
        width: 100%;
        transition: background-color 0.2s ease, transform 0.1s ease;
    }
    div.stButton > button:first-child:hover {
        background-color: #272C30;
        color: white;
    }
    div.stButton > button:first-child:active {
        transform: scale(0.98);
    }

    /* Download Button */
    div.stDownloadButton > button:first-child {
        background-color: #1DA1F2;
        color: white;
        font-size: 15px;
        font-weight: 700;
        padding: 10px 20px;
        border: none;
        border-radius: 9999px;
        width: 100%;
        box-shadow: 0 4px 12px rgba(29, 161, 242, 0.2);
        transition: background-color 0.2s ease, transform 0.1s ease;
        margin-top: 10px;
    }
    div.stDownloadButton > button:first-child:hover {
        background-color: #1A8CD8;
        color: white;
    }
    div.stDownloadButton > button:first-child:active {
        transform: scale(0.98);
    }

    /* Media Containers */
    .media-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 15px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        border: 1px solid #EFF3F4;
        margin-bottom: 20px;
    }
    
    /* Dark mode support */
    @media (prefers-color-scheme: dark) {
        .main-title { color: #E7E9EA; }
        .sub-title { color: #71767B; }
        .stTextInput > div > div > input {
            background-color: #202327 !important;
            border-color: #202327 !important;
            color: #E7E9EA !important;
        }
        .stTextInput > div > div > input:focus {
            background-color: #000000 !important;
        }
        div.stButton > button:first-child {
            background-color: #EFF3F4;
            color: #0F1419;
        }
        div.stButton > button:first-child:hover {
            background-color: #D7DBDC;
            color: #0F1419;
        }
        .media-card {
            background: #15202B;
            border: 1px solid #38444D;
        }
    }
</style>
""", unsafe_allow_html=True)

# --- Header Section ---
st.markdown('<div class="main-title">X / Twitter Downloader 🐦</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Easily download mixed media (multiple videos, GIFs, and images) from any post.</div>', unsafe_allow_html=True)

# --- Initialize session state ---
if 'media_items' not in st.session_state:
    st.session_state.media_items = []
if 'last_url' not in st.session_state:
    st.session_state.last_url = None
if 'status_message' not in st.session_state:
    st.session_state.status_message = None
if 'error_details' not in st.session_state:
    st.session_state.error_details = None
if 'download_cache' not in st.session_state:
    st.session_state.download_cache = {}

# --- Helper Functions for Advanced Extraction ---
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

def extract_tweet_id(url: str) -> str:
    """Extracts status numerical ID from any X/Twitter link format."""
    match = re.search(r'status(?:es)?/(\d+)', url)
    if match:
        return match.group(1)
    match_digits = re.search(r'^\s*(\d{15,22})\s*$', url)
    if match_digits:
        return match_digits.group(1)
    return None

def compute_syndication_token(tweet_id: str) -> str:
    """Replicates browser token generation for Twitter's official syndication embed API."""
    try:
        val = (int(tweet_id) / 1e15) * math.pi
        chars = '0123456789abcdefghijklmnopqrstuvwxyz'
        int_part = int(val)
        frac_part = val - int_part
        int_str = ""
        n = int_part
        if n == 0:
            int_str = "0"
        else:
            while n > 0:
                int_str = chars[n % 36] + int_str
                n //= 36
        frac_str = ""
        for _ in range(16):
            frac_part *= 36
            digit = int(frac_part)
            frac_str += chars[digit]
            frac_part -= digit
            if frac_part == 0:
                break
        return re.sub(r'(0+|\.)', '', f"{int_str}.{frac_str}")
    except Exception:
        return ""

def fetch_media_from_fxtwitter(tweet_id: str):
    """Tier 1: High reliability multi-asset resolver."""
    try:
        res = requests.get(f"https://api.fxtwitter.com/status/{tweet_id}", headers=DEFAULT_HEADERS, timeout=12)
        if res.status_code == 200:
            data = res.json().get("tweet", {})
            media_entries = data.get("media", {}).get("all", [])
            if not media_entries and "quote" in data:
                media_entries = data.get("quote", {}).get("media", {}).get("all", [])
            
            results = []
            for item in media_entries:
                m_type = item.get("type")
                if m_type == "photo":
                    img_url = item.get("url")
                    orig_url = img_url
                    preview_url = img_url
                    if "pbs.twimg.com" in img_url:
                        base = re.sub(r'(\?|&)name=[a-zA-Z0-9_]+', '', img_url)
                        sep = "&" if "?" in base else "?"
                        orig_url = f"{base}{sep}name=orig"
                        preview_url = f"{base}{sep}name=small"
                    results.append({"url": orig_url, "preview_url": preview_url, "type": "image"})
                elif m_type in ["video", "gif"]:
                    variants = item.get("variants", [])
                    chosen_url = item.get("url")
                    if variants:
                        mp4s = [v for v in variants if "mp4" in v.get("content_type", "") or ".mp4" in v.get("url", "")]
                        if mp4s:
                            mp4s.sort(key=lambda x: x.get("bitrate") or 0, reverse=True)
                            chosen_url = mp4s[0].get("url")
                    results.append({"url": chosen_url, "preview_url": chosen_url, "type": "video"})
            return results
    except Exception:
        pass
    return None

def fetch_media_from_vxtwitter(tweet_id: str):
    """Tier 2: Direct failover resolver."""
    try:
        res = requests.get(f"https://api.vxtwitter.com/Twitter/status/{tweet_id}", headers=DEFAULT_HEADERS, timeout=12)
        if res.status_code == 200:
            data = res.json()
            results = []
            for item in data.get("media_extended", []):
                t = "video" if item.get("type") in ["video", "gif"] else "image"
                url = item.get("url")
                orig_url = url
                preview_url = url
                if t == "image" and "pbs.twimg.com" in url:
                    base = re.sub(r'(\?|&)name=[a-zA-Z0-9_]+', '', url)
                    sep = "&" if "?" in base else "?"
                    orig_url = f"{base}{sep}name=orig"
                    preview_url = f"{base}{sep}name=small"
                results.append({"url": orig_url, "preview_url": preview_url, "type": t})
            if not results and data.get("mediaURLs"):
                for url in data["mediaURLs"]:
                    t = "video" if (".mp4" in url or "video.twimg" in url) else "image"
                    results.append({"url": url, "preview_url": url, "type": t})
            return results
    except Exception:
        pass
    return None

def fetch_media_from_syndication(tweet_id: str):
    """Tier 3: Twitter syndication embed API."""
    try:
        token = compute_syndication_token(tweet_id)
        token_param = f"&token={token}" if token else ""
        url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&lang=en{token_param}"
        res = requests.get(url, headers=DEFAULT_HEADERS, timeout=12)
        if res.status_code == 200:
            data = res.json()
            results = []
            for photo in data.get("photos", []):
                purl = photo.get("url", "")
                if purl:
                    base = re.sub(r'(\?|&)name=[a-zA-Z0-9_]+', '', purl)
                    sep = "&" if "?" in base else "?"
                    orig_url = f"{base}{sep}name=orig"
                    preview_url = f"{base}{sep}name=small"
                    results.append({"url": orig_url, "preview_url": preview_url, "type": "image"})
            
            video_info = data.get("video")
            if video_info:
                variants = video_info.get("variants", [])
                mp4s = [v for v in variants if "mp4" in v.get("type", "") or ".mp4" in v.get("src", "")]
                if mp4s:
                    mp4s.sort(key=lambda x: x.get("bitrate") or 0, reverse=True)
                    results.append({"url": mp4s[0].get("src"), "preview_url": mp4s[0].get("src"), "type": "video"})
            return results
    except Exception:
        pass
    return None

# --- Input Area ---
st.write("") # Spacer
tweet_url = st.text_input("URL Input", placeholder="Paste X/Twitter link here... (e.g., https://x.com/user/status/123)", label_visibility="collapsed")

col1, col2 = st.columns([3, 1])
with col1:
    show_preview = st.toggle("Show media previews", value=True, help="Toggle to display or hide the media before downloading.")
with col2:
    fetch_clicked = st.button("Get Media")

st.markdown("<br>", unsafe_allow_html=True) # Spacer

# --- Link Analysis Logic ---
if fetch_clicked:
    if not tweet_url:
        st.warning("⚠️ Please enter a valid URL.")
    else:
        with st.spinner("Analyzing link and extracting all available media..."):
            extracted_media = []
            st.session_state.download_cache = {} # Clear previous file bytes
            tweet_id = extract_tweet_id(tweet_url)

            # Step 1: Attempt direct multi-tier zero-cookie APIs (Metadata only, extremely fast & zero mobile data wasted)
            media_targets = None
            if tweet_id:
                media_targets = fetch_media_from_fxtwitter(tweet_id)
                if not media_targets:
                    media_targets = fetch_media_from_vxtwitter(tweet_id)
                if not media_targets:
                    media_targets = fetch_media_from_syndication(tweet_id)

            if media_targets:
                for idx, item in enumerate(media_targets):
                    m_url = item["url"]
                    m_type = item["type"]
                    p_url = item.get("preview_url", m_url)

                    if m_type == "video":
                        ext = ".mp4"
                        mime = "video/mp4"
                    else:
                        ext = ".png" if ("format=png" in m_url or ".png" in m_url) else ".jpg"
                        mime = "image/png" if ext == ".png" else "image/jpeg"

                    name = f"twitter_{tweet_id}_{idx + 1}{ext}"

                    extracted_media.append({
                        "name": name,
                        "url": m_url,
                        "preview_url": p_url,
                        "mime": mime,
                        "type": m_type,
                        "data": None
                    })

            # Step 2: Fallback to yt-dlp & gallery-dl if web APIs yielded nothing
            if not extracted_media:
                with tempfile.TemporaryDirectory(prefix="twitter_dl_") as temp_dir:
                    try:
                        subprocess.run([
                            "yt-dlp",
                            "--extractor-args", "twitter:api=syndication",
                            "-f", "bestvideo+bestaudio/best",
                            "--merge-output-format", "mp4",
                            "-o", os.path.join(temp_dir, "ytdlp_vid_%(id)s_%(autonumber)s.%(ext)s"),
                            tweet_url
                        ], capture_output=True, timeout=60)

                        subprocess.run([
                            "gallery-dl", 
                            "--directory", temp_dir, 
                            tweet_url
                        ], capture_output=True, timeout=60)

                        all_files = glob.glob(os.path.join(temp_dir, "**", "*"), recursive=True)
                        file_paths = [f for f in all_files if os.path.isfile(f)]

                        valid_video_exts = [".mp4", ".webm", ".mkv"]
                        valid_image_exts = [".jpg", ".jpeg", ".png", ".gif", ".webp"]

                        seen_hashes = set()
                        for fp in file_paths:
                            basename = os.path.basename(fp)
                            basename_lower = basename.lower()
                            
                            is_video = any(basename_lower.endswith(e) for e in valid_video_exts)
                            is_image = any(basename_lower.endswith(e) for e in valid_image_exts)

                            if not (is_video or is_image):
                                continue
                            if is_video and not basename.startswith("ytdlp_vid_"):
                                continue

                            with open(fp, "rb") as f:
                                data = f.read()

                            file_hash = hashlib.md5(data).hexdigest()
                            if file_hash in seen_hashes:
                                continue
                            seen_hashes.add(file_hash)

                            mime_type, _ = mimetypes.guess_type(fp)
                            if not mime_type:
                                mime_type = "video/mp4" if is_video else "image/jpeg"

                            extracted_media.append({
                                "name": basename,
                                "url": None,
                                "preview_url": None,
                                "data": data,
                                "mime": mime_type,
                                "type": "video" if is_video else "image"
                            })
                    except Exception as e:
                        st.session_state.error_details = str(e)

            # Finalize Session State
            if extracted_media:
                st.session_state.media_items = extracted_media
                st.session_state.last_url = tweet_url
                st.session_state.status_message = "success"
            else:
                st.session_state.status_message = "error_no_media"

st.markdown("---")

# --- Display Results ---
if st.session_state.status_message == "success":
    st.success(f"✅ **Successfully extracted {len(st.session_state.media_items)} media item(s)!**")
    st.write("")
    
    # Create a clean 2-column grid for the media items
    cols = st.columns(2)
    
    for idx, item in enumerate(st.session_state.media_items):
        with cols[idx % 2]: # Distribute evenly between left and right columns
            st.markdown('<div class="media-card">', unsafe_allow_html=True)
            
            # 1. Preview Handling (Bandwidth-efficient)
            if show_preview:
                if item["type"] == "video":
                    # Direct CDN streaming: Only streams if the user presses play
                    if item.get("url"):
                        st.video(item["url"])
                    elif item.get("data"):
                        st.video(item["data"])
                else:
                    # Lightweight image preview: Uses small preview resolution to save mobile bandwidth
                    img_source = item.get("preview_url") or item.get("url") or item.get("data")
                    try:
                        st.image(img_source, use_container_width=True)
                    except TypeError:
                        try:
                            st.image(img_source, use_column_width=True)
                        except Exception:
                            st.image(img_source)
                    except Exception:
                        st.markdown("<div style='text-align: center; padding: 20px;'><h3>📸 Image File</h3></div>", unsafe_allow_html=True)
            else:
                # Fallback if preview is toggled off (Transfers 0 KB of media to phone)
                icon = "🎥" if item["type"] == "video" else "📸"
                st.markdown(f"<div style='text-align: center; padding: 20px;'><h3>{icon} {item['type'].title()} File</h3></div>", unsafe_allow_html=True)
            
            # 2. Individual Download Control (On-Demand: Zero background data usage)
            cache_key = f"media_{idx}_{st.session_state.last_url}"
            cached_data = st.session_state.download_cache.get(cache_key) or item.get("data")
            
            if cached_data is not None:
                # File is prepared: Render the direct download button
                st.download_button(
                    label=f"💾 Save {item['type'].title()} to Device",
                    data=cached_data,
                    file_name=item["name"],
                    mime=item["mime"],
                    key=f"save_btn_{idx}_{st.session_state.last_url}"
                )
            else:
                # File not yet downloaded to mobile: Show on-demand fetch button
                if st.button(f"⬇️ Download {item['type'].title()}", key=f"fetch_btn_{idx}_{st.session_state.last_url}"):
                    with st.spinner(f"Preparing high-quality {item['type'].title()}..."):
                        try:
                            res = requests.get(item["url"], headers=DEFAULT_HEADERS, timeout=45)
                            if res.status_code == 200 and len(res.content) > 0:
                                st.session_state.download_cache[cache_key] = res.content
                                st.rerun()
                            else:
                                st.error("Failed to retrieve file from source. Please try again.")
                        except Exception as dl_err:
                            st.error(f"Download failed: {dl_err}")
            
            st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.status_message == "error_no_media":
    st.error("🚫 **Failed to fetch media.** The link might be text-only, from a private account, or the server is temporarily rate-limited by X.")
elif st.session_state.status_message == "error_general":
    st.error(f"⚠️ **An unexpected error occurred:** {st.session_state.error_details}")

# --- Footer Disclaimer ---
st.markdown("<br><br>", unsafe_allow_html=True)

# Centered Clear Cache Button
cc_col1, cc_col2, cc_col3 = st.columns([1, 1, 1])
with cc_col2:
    if st.button("Clear Cache", use_container_width=True):
        st.session_state.media_items = []
        st.session_state.download_cache = {}
        st.session_state.last_url = None
        st.session_state.status_message = None
        st.session_state.error_details = None
        st.rerun()

st.caption("ℹ️ **Note:** X/Twitter limits automated access. If you experience errors, it usually means the server's IP has been temporarily restricted.")
st.markdown('<div style="text-align: center;"><a href="https://github.com/JustToTryModels/Twitter-Downloader/blob/main/app.py" target="_blank" style="color: #536471; text-decoration: none; font-size: 14px;">View Source Code on GitHub 💻</a></div>', unsafe_allow_html=True)
