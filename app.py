import streamlit as st
import os
import io
import subprocess
import tempfile
import glob
import zipfile
import mimetypes

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
        max-width: 800px;
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
        font-size: 16px;
        font-weight: 700;
        padding: 12px 24px;
        border: none;
        border-radius: 9999px;
        width: 100%;
        box-shadow: 0 4px 12px rgba(29, 161, 242, 0.3);
        transition: background-color 0.2s ease, transform 0.1s ease;
    }
    div.stDownloadButton > button:first-child:hover {
        background-color: #1A8CD8;
        color: white;
    }
    div.stDownloadButton > button:first-child:active {
        transform: scale(0.98);
    }

    /* Toggles and Info boxes */
    .stAlert {
        border-radius: 16px;
        border: none;
    }
    
    /* Media Containers */
    .media-container {
        border-radius: 16px;
        overflow: hidden;
        border: 1px solid #EFF3F4;
        margin-top: 1rem;
        margin-bottom: 1rem;
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
    }
</style>
""", unsafe_allow_html=True)

# --- Header Section ---
st.markdown('<div class="main-title">X / Twitter Downloader 🐦</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Easily download high-quality videos, GIFs, and images from any post.</div>', unsafe_allow_html=True)

# --- Initialize session state ---
if 'media_data' not in st.session_state:
    st.session_state.media_data = None
    st.session_state.media_name = None
    st.session_state.media_type = None
    st.session_state.media_mime = None
    st.session_state.previews = []
    st.session_state.last_url = None
    st.session_state.status_message = None

# --- Input Area ---
st.write("") # Spacer
tweet_url = st.text_input("URL Input", placeholder="Paste X/Twitter link here... (e.g., https://x.com/user/status/123)", label_visibility="collapsed")

col1, col2 = st.columns([3, 1])
with col1:
    show_preview = st.toggle("Show media preview", value=True, help="Toggle to display or hide the media before downloading.")
with col2:
    fetch_clicked = st.button("Get Media")

st.markdown("<br>", unsafe_allow_html=True) # Spacer

# --- Download Logic ---
if fetch_clicked:
    if not tweet_url:
        st.warning("⚠️ Please enter a valid URL.")
    else:
        # Use Context Manager for temporary directory to ensure automatic cleanup (STABILITY FIX)
        with tempfile.TemporaryDirectory(prefix="twitter_dl_") as temp_dir:
            
            with st.spinner("Analyzing link and fetching media in highest quality..."):
                try:
                    # 1. Check if the tweet contains a video/GIF
                    video_check = subprocess.run(
                        ["yt-dlp", "--simulate", "--quiet", tweet_url],
                        capture_output=True, text=True
                    )

                    if video_check.returncode == 0:
                        # --- VIDEO/GIF FOUND ---
                        out_template = os.path.join(temp_dir, "%(id)s.%(ext)s")
                        
                        # Run download - fetch highest available quality
                        subprocess.run([
                            "yt-dlp",
                            "-f", "bestvideo+bestaudio/best",
                            "--merge-output-format", "mp4",
                            "-o", out_template,
                            tweet_url
                        ])
                        
                        # Find the downloaded file
                        files = glob.glob(os.path.join(temp_dir, "*"))
                        files = [f for f in files if os.path.isfile(f)]
                        
                        if files:
                            file_path = files[0]
                            file_name = os.path.basename(file_path)
                            mime_type = mimetypes.guess_type(file_path)[0] or "video/mp4"
                            
                            with open(file_path, "rb") as f:
                                data = f.read()
                            
                            st.session_state.media_data = data
                            st.session_state.media_name = file_name
                            st.session_state.media_type = "video"
                            st.session_state.media_mime = mime_type
                            st.session_state.previews = []
                            st.session_state.last_url = tweet_url
                            st.session_state.status_message = "success_video"
                        else:
                            st.session_state.status_message = "error_video"
                    
                    else:
                        # --- NO VIDEO, TRY IMAGES ---
                        subprocess.run(["gallery-dl", "-d", temp_dir, tweet_url])
                        
                        # Find all downloaded images (gallery-dl sometimes creates subfolders)
                        files = glob.glob(os.path.join(temp_dir, "**", "*"), recursive=True)
                        files = [f for f in files if os.path.isfile(f)]  # Filter out directories
                        
                        if files:
                            if len(files) == 1:
                                file_path = files[0]
                                file_name = os.path.basename(file_path)
                                mime_type = mimetypes.guess_type(file_path)[0] or "image/jpeg"
                                
                                with open(file_path, "rb") as f:
                                    data = f.read()
                                
                                st.session_state.media_data = data
                                st.session_state.media_name = file_name
                                st.session_state.media_type = "image"
                                st.session_state.media_mime = mime_type
                                st.session_state.previews = [(data, file_name)]
                                st.session_state.last_url = tweet_url
                                st.session_state.status_message = "success_image_single"
                            else:
                                # Multiple images - load all into memory and zip
                                previews = []
                                for f_path in files:
                                    with open(f_path, "rb") as f:
                                        img_data = f.read()
                                    previews.append((img_data, os.path.basename(f_path)))
                                
                                # Zip the files in memory
                                zip_buffer = io.BytesIO()
                                with zipfile.ZipFile(zip_buffer, 'w') as zipf:
                                    for img_data, fname in previews:
                                        zipf.writestr(fname, img_data)
                                zip_data = zip_buffer.getvalue()
                                
                                st.session_state.media_data = zip_data
                                st.session_state.media_name = "twitter_images.zip"
                                st.session_state.media_type = "zip"
                                st.session_state.media_mime = "application/zip"
                                st.session_state.previews = previews
                                st.session_state.last_url = tweet_url
                                st.session_state.status_message = "success_image_multi"
                        else:
                            st.session_state.status_message = "error_image"
                
                except Exception as e:
                    st.session_state.status_message = "error_general"
                    st.session_state.error_details = str(e)

st.markdown("---")

# --- Display Results ---
if st.session_state.status_message == "success_video":
    st.success("✅ **Media processed successfully!**")
    
    if show_preview:
        st.markdown('<div class="media-container">', unsafe_allow_html=True)
        st.video(st.session_state.media_data)
        st.markdown('</div>', unsafe_allow_html=True)
        
    spacer1, btn_col, spacer2 = st.columns([1, 2, 1])
    with btn_col:
        st.download_button(
            label="Download High-Quality Video",
            data=st.session_state.media_data,
            file_name=st.session_state.media_name,
            mime=st.session_state.media_mime,
            key=f"dl_video_{st.session_state.last_url}"
        )

elif st.session_state.status_message == "success_image_single":
    st.success("✅ **Image processed successfully!**")
    
    if show_preview:
        st.markdown('<div class="media-container">', unsafe_allow_html=True)
        st.image(st.session_state.media_data, use_column_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
    spacer1, btn_col, spacer2 = st.columns([1, 2, 1])
    with btn_col:
        st.download_button(
            label="Download Image",
            data=st.session_state.media_data,
            file_name=st.session_state.media_name,
            mime=st.session_state.media_mime,
            key=f"dl_img_{st.session_state.last_url}"
        )

elif st.session_state.status_message == "success_image_multi":
    st.success("✅ **Media gallery processed successfully!**")
    
    if show_preview:
        st.write(f"📸 **Found {len(st.session_state.previews)} images:**")
        cols = st.columns(2) # Changed to 2 columns for better visibility
        for idx, (img_data, caption) in enumerate(st.session_state.previews):
            with cols[idx % 2]:
                st.markdown('<div class="media-container">', unsafe_allow_html=True)
                st.image(img_data, use_column_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
    spacer1, btn_col, spacer2 = st.columns([1, 2, 1])
    with btn_col:
        st.download_button(
            label=f"Download All ({len(st.session_state.previews)} Images as ZIP)",
            data=st.session_state.media_data,
            file_name="twitter_images.zip",
            mime="application/zip",
            key=f"dl_zip_{st.session_state.last_url}"
        )

elif st.session_state.status_message == "error_video":
    st.error("🚫 **Failed to fetch video.** The tweet might not contain a video, or the server is being rate-limited by X.")
elif st.session_state.status_message == "error_image":
    st.error("🚫 **Failed to fetch images.** The link might be text-only, from a private account, or rate-limited.")
elif st.session_state.status_message == "error_general":
    st.error(f"⚠️ **An unexpected error occurred:** {st.session_state.error_details}")

# --- Footer Disclaimer ---
st.markdown("<br><br>", unsafe_allow_html=True)
st.caption("ℹ️ **Note on availability:** X/Twitter aggressively limits automated access. If you experience errors, it usually means the server's IP has been temporarily restricted. This tool is intended for public, accessible media only.")
