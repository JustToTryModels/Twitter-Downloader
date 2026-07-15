import streamlit as st
import os
import subprocess
import tempfile
import glob
import mimetypes
import hashlib

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
    st.session_state.last_url = None
    st.session_state.status_message = None
    st.session_state.error_details = None

# --- Input Area ---
st.write("") # Spacer
tweet_url = st.text_input("URL Input", placeholder="Paste X/Twitter link here... (e.g., https://x.com/user/status/123)", label_visibility="collapsed")

col1, col2 = st.columns([3, 1])
with col1:
    show_preview = st.toggle("Show media previews", value=True, help="Toggle to display or hide the media before downloading.")
with col2:
    fetch_clicked = st.button("Get Media")

st.markdown("<br>", unsafe_allow_html=True) # Spacer

# --- Download Logic ---
if fetch_clicked:
    if not tweet_url:
        st.warning("⚠️ Please enter a valid URL.")
    else:
        with tempfile.TemporaryDirectory(prefix="twitter_dl_") as temp_dir:
            
            with st.spinner("Analyzing link and extracting all available media..."):
                try:
                    # 1. Fetch videos/GIFs using yt-dlp
                    # We prefix the output with 'ytdlp_vid_' so we can identify videos downloaded by yt-dlp
                    subprocess.run([
                        "yt-dlp",
                        "-f", "bestvideo+bestaudio/best",
                        "--merge-output-format", "mp4",
                        "-o", os.path.join(temp_dir, "ytdlp_vid_%(id)s_%(autonumber)s.%(ext)s"),
                        tweet_url
                    ], capture_output=True)

                    # 2. Fetch images using gallery-dl
                    subprocess.run([
                        "gallery-dl", 
                        "--directory", temp_dir, 
                        tweet_url
                    ], capture_output=True)

                    # 3. Collect ALL downloaded files recursively
                    all_files = glob.glob(os.path.join(temp_dir, "**", "*"), recursive=True)
                    file_paths = [f for f in all_files if os.path.isfile(f)]

                    valid_video_exts = [".mp4", ".webm", ".mkv"]
                    valid_image_exts = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
                    
                    extracted_media = []
                    seen_hashes = set()

                    for fp in file_paths:
                        basename = os.path.basename(fp)
                        basename_lower = basename.lower()
                        
                        is_video = any(basename_lower.endswith(ext) for ext in valid_video_exts)
                        is_image = any(basename_lower.endswith(ext) for ext in valid_image_exts)

                        # Skip temporary or unwanted files entirely
                        if not (is_video or is_image):
                            continue
                            
                        # DEDUPLICATION FIX: gallery-dl sometimes downloads identical videos alongside yt-dlp.
                        # We force the app to ignore ANY video that was not downloaded by yt-dlp.
                        if is_video and not basename.startswith("ytdlp_vid_"):
                            continue
                            
                        # Read file data into memory
                        with open(fp, "rb") as f:
                            data = f.read()
                        
                        # Deduplicate images (If gallery-dl downloads multiple sizes/thumbnails of the exact same image)
                        file_hash = hashlib.md5(data).hexdigest()
                        if file_hash in seen_hashes:
                            continue
                        seen_hashes.add(file_hash)

                        # Determine Mime Type
                        mime_type, _ = mimetypes.guess_type(fp)
                        if not mime_type:
                            mime_type = "application/octet-stream"

                        # Set type for UI preview handling
                        media_type = "video" if is_video else "image"

                        extracted_media.append({
                            "name": basename,
                            "data": data,
                            "mime": mime_type,
                            "type": media_type
                        })

                    if extracted_media:
                        st.session_state.media_items = extracted_media
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
    st.success(f"✅ **Successfully extracted {len(st.session_state.media_items)} media item(s)!**")
    st.write("")
    
    # Create a clean 2-column grid for the media items
    cols = st.columns(2)
    
    for idx, item in enumerate(st.session_state.media_items):
        with cols[idx % 2]: # Distribute evenly between left and right columns
            st.markdown('<div class="media-card">', unsafe_allow_html=True)
            
            # 1. Preview
            if show_preview:
                if item["type"] == "video":
                    st.video(item["data"])
                else:
                    st.image(item["data"], use_column_width=True)
            else:
                # Fallback if preview is toggled off
                icon = "🎥" if item["type"] == "video" else "📸"
                st.markdown(f"<div style='text-align: center; padding: 20px;'><h3>{icon} {item['type'].title()} File</h3></div>", unsafe_allow_html=True)
            
            # 2. Individual Download Button
            st.download_button(
                label=f"Download {item['type'].title()}",
                data=item["data"],
                file_name=item["name"],
                mime=item["mime"],
                key=f"dl_{idx}_{st.session_state.last_url}"
            )
            
            st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.status_message == "error_no_media":
    st.error("🚫 **Failed to fetch media.** The link might be text-only, from a private account, or the server is temporarily rate-limited by X.")
elif st.session_state.status_message == "error_general":
    st.error(f"⚠️ **An unexpected error occurred:** {st.session_state.error_details}")

# --- Footer Disclaimer ---
st.markdown("<br><br>", unsafe_allow_html=True)
st.caption("ℹ️ **Note:** X/Twitter limits automated access. If you experience errors, it usually means the server's IP has been temporarily restricted.")
