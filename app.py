import streamlit as st
import os
import subprocess
import tempfile
import glob
import mimetypes
import hashlib
import requests
import re
import io

# --- Page Configuration ---
st.set_page_config(
    page_title="Advanced X / Twitter Downloader", 
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
st.markdown('<div class="main-title">Advanced X / Twitter Downloader 🐦</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Bypass X limits using advanced API extraction. No cookies required. Supports mixed media.</div>', unsafe_allow_html=True)

# --- Initialize session state ---
if 'media_items' not in st.session_state:
    st.session_state.media_items = []
    st.session_state.last_url = None
    st.session_state.status_message = None
    st.session_state.error_details = None

# --- Advanced Extraction Logic ---
def extract_tweet_id(url):
    """Extracts the numerical Tweet ID from any valid X/Twitter URL."""
    match = re.search(r'/status/(\d+)', url)
    return match.group(1) if match else None

def fetch_media_urls_fx_twitter(tweet_id):
    """
    Uses the FixTweet API (api.fxtwitter.com) to bypass X's bot protection 
    and retrieve direct high-quality media URLs without authentication.
    """
    api_url = f"https://api.fxtwitter.com/i/status/{tweet_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(api_url, headers=headers, timeout=15)
        data = response.json()
        if data.get('code') == 200 and data.get('tweet'):
            tweet = data['tweet']
            media = tweet.get('media', {})
            return media.get('all', [])
        return None
    except Exception:
        return None

def fetch_media_urls_vx_twitter(tweet_id):
    """Fallback API using vxtwitter if fxtwitter fails."""
    api_url = f"https://api.vxtwitter.com/i/status/{tweet_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(api_url, headers=headers, timeout=15)
        data = response.json()
        if 'mediaURLs' in data and data['mediaURLs']:
            return [{"url": u, "type": "video" if ("video" in u or "mp4" in u) else "photo"} for u in data['mediaURLs']]
        return None
    except Exception:
        return None

def download_direct_media(url, temp_dir, filename_prefix, headers):
    """Downloads media directly from twimg.com CDN with a browser User-Agent."""
    try:
        # For images, force 'orig' quality
        if 'pbs.twimg.com/media/' in url and '?' not in url:
            url += '?name=orig'
            
        ext = url.split('.')[-1].split('?')[0][:4]
        if ext not in ['mp4', 'jpg', 'jpeg', 'png', 'gif', 'webp']:
            ext = 'mp4' if 'video' in url else 'jpg'
            
        # If it's an HLS stream, let yt-dlp handle it
        if ext in ['m3u8', 'm3u']:
            download_with_ytdlp(url, temp_dir, f"ytdlp_{filename_prefix}")
            return None

        with requests.get(url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            file_path = os.path.join(temp_dir, f"{filename_prefix}_{hashlib.md5(url.encode()).hexdigest()[:8]}.{ext}")
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return file_path
    except Exception:
        return None

def download_with_ytdlp(url, temp_dir, prefix):
    """Fallback mechanism using yt-dlp for direct media URLs."""
    try:
        outtmpl = os.path.join(temp_dir, f"{prefix}_%(id)s.%(ext)s")
        subprocess.run([
            "yt-dlp",
            "--no-playlist",
            "-f", "bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "-o", outtmpl,
            url
        ], capture_output=True, timeout=60)
        return True
    except Exception:
        return False

def process_url(tweet_url, temp_dir):
    extracted_media = []
    seen_hashes = set()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    tweet_id = extract_tweet_id(tweet_url)
    api_media = None
    
    if tweet_id:
        api_media = fetch_media_urls_fx_twitter(tweet_id)
        if not api_media:
            api_media = fetch_media_urls_vx_twitter(tweet_id)
    
    # 1. PRIMARY: Advanced API Direct Download (Bypasses X limits)
    if api_media:
        for idx, item in enumerate(api_media):
            media_type = item.get('type')
            media_url = item.get('url')
            
            # Select highest quality video variant if available
            if media_type in ['video', 'gif']:
                formats = item.get('formats', [])
                best_mp4 = None
                max_bitrate = -1
                for f in formats:
                    if f.get('container') == 'mp4':
                        bitrate = f.get('bitrate', 0)
                        if bitrate > max_bitrate:
                            max_bitrate = bitrate
                            best_mp4 = f.get('url')
                if best_mp4:
                    media_url = best_mp4
                    
            if media_url:
                file_path = download_direct_media(media_url, temp_dir, f"api_{idx}", headers)
                if not file_path:
                    download_with_ytdlp(media_url, temp_dir, f"ytdlp_api_{idx}")
    
    # 2. SECONDARY: Local Tools Fallback (If API failed completely)
    if not os.listdir(temp_dir):
        try:
            subprocess.run([
                "yt-dlp",
                "--no-playlist",
                "--add-header", f"User-Agent:{headers['User-Agent']}",
                "-f", "bestvideo+bestaudio/best",
                "--merge-output-format", "mp4",
                "-o", os.path.join(temp_dir, "ytdlp_vid_%(id)s_%(autonumber)s.%(ext)s"),
                tweet_url
            ], capture_output=True, timeout=45)
        except Exception:
            pass

        try:
            subprocess.run([
                "gallery-dl", 
                "--directory", temp_dir, 
                tweet_url
            ], capture_output=True, timeout=45)
        except Exception:
            pass

    # 3. Collect, Deduplicate and Process Files
    all_files = glob.glob(os.path.join(temp_dir, "**", "*"), recursive=True)
    valid_video_exts = [".mp4", ".webm", ".mkv"]
    valid_image_exts = [".jpg", ".jpeg", ".png", ".gif", ".webp"]

    for fp in all_files:
        if not os.path.isfile(fp): continue
        basename = os.path.basename(fp).lower()
        
        is_video = any(basename.endswith(ext) for ext in valid_video_exts)
        is_image = any(basename.endswith(ext) for ext in valid_image_exts)
        if not (is_video or is_image): continue
            
        with open(fp, "rb") as f:
            data = f.read()
        
        file_hash = hashlib.md5(data).hexdigest()
        if file_hash in seen_hashes: continue
        seen_hashes.add(file_hash)

        mime_type, _ = mimetypes.guess_type(fp)
        if not mime_type: mime_type = "application/octet-stream"

        extracted_media.append({
            "name": os.path.basename(fp),
            "data": data,
            "mime": mime_type,
            "type": "video" if is_video else "image"
        })

    return extracted_media

# --- Input Area ---
st.write("")
tweet_url = st.text_input("URL Input", placeholder="Paste X/Twitter link here... (e.g., https://x.com/user/status/123)", label_visibility="collapsed")

col1, col2 = st.columns([3, 1])
with col1:
    show_preview = st.toggle("Show media previews", value=True, help="Toggle to display or hide the media before downloading.")
with col2:
    fetch_clicked = st.button("Get Media")

st.markdown("<br>", unsafe_allow_html=True)

# --- Download Logic Execution ---
if fetch_clicked:
    if not tweet_url:
        st.warning("⚠️ Please enter a valid URL.")
    else:
        with tempfile.TemporaryDirectory(prefix="twitter_dl_") as temp_dir:
            with st.spinner("🔍 Bypassing X restrictions and analyzing media..."):
                try:
                    media_items = process_url(tweet_url, temp_dir)
                    if media_items:
                        st.session_state.media_items = media_items
                        st.session_state.last_url = tweet_url
                        st.session_state.status_message = "success"
                    else:
                        st.session_state.status_message = "error_no_media"
                except Exception as e:
                    st.session_state.status_message = "error_general"
                    st.session_state.error_details = str(e)

st.markdown("---")

# --- Display Results ---
if st.session_state.status_message == "success":
    st.success(f"✅ **Successfully extracted {len(st.session_state.media_items)} high-quality media item(s)!**")
    st.write("")
    
    cols = st.columns(2)
    for idx, item in enumerate(st.session_state.media_items):
        with cols[idx % 2]:
            st.markdown('<div class="media-card">', unsafe_allow_html=True)
            
            if show_preview:
                if item["type"] == "video":
                    st.video(item["data"])
                else:
                    st.image(item["data"], use_column_width=True)
            else:
                icon = "🎥" if item["type"] == "video" else "📸"
                st.markdown(f"<div style='text-align: center; padding: 20px;'><h3>{icon} {item['type'].title()} File</h3></div>", unsafe_allow_html=True)
            
            st.download_button(
                label=f"Download {item['type'].title()}",
                data=item["data"],
                file_name=item["name"],
                mime=item["mime"],
                key=f"dl_{idx}_{st.session_state.last_url}"
            )
            st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.status_message == "error_no_media":
    st.error("🚫 **Failed to fetch media.** The link might be text-only, from a strictly private account, or the media is deleted.")
elif st.session_state.status_message == "error_general":
    st.error(f"⚠️ **An unexpected error occurred:** {st.session_state.error_details}")

# --- Footer Disclaimer ---
st.markdown("<br><br>", unsafe_allow_html=True)
cc_col1, cc_col2, cc_col3 = st.columns([1, 1, 1])
with cc_col2:
    if st.button("Clear Cache", use_container_width=True):
        st.session_state.media_items = []
        st.session_state.last_url = None
        st.session_state.status_message = None
        st.session_state.error_details = None
        st.rerun()

st.caption("ℹ️ **Note:** This tool uses advanced proxy API endpoints to bypass X/Twitter's native scraping limitations without requiring cookies.")
