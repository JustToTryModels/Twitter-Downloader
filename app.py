import streamlit as st
import os
import io
import subprocess
import tempfile
import glob
import zipfile
import shutil
import mimetypes

# --- Page Configuration ---
st.set_page_config(
    page_title="Twitter Media Downloader Pro",
    page_icon="🐦",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- Custom CSS for a Beautiful, Professional Look ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Poppins', sans-serif;
}

/* App background */
.stApp {
    background: linear-gradient(160deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
}

/* Hide default Streamlit branding clutter */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* Title styling */
.main-title {
    text-align: center;
    font-size: 3rem;
    font-weight: 800;
    background: linear-gradient(90deg, #FF4B2B, #FF416C, #FF8A00);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0px;
    padding-bottom: 0px;
}

.sub-title {
    text-align: center;
    color: #d1d1e0;
    font-size: 1.05rem;
    margin-top: 4px;
    margin-bottom: 30px;
    font-weight: 400;
}

/* Card containers */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255, 255, 255, 0.06);
    backdrop-filter: blur(12px);
    border-radius: 20px !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    padding: 10px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
}

/* Text input styling */
div[data-baseweb="input"] {
    border-radius: 14px;
    overflow: hidden;
}

.stTextInput input {
    background-color: rgba(255, 255, 255, 0.08) !important;
    color: #ffffff !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    border-radius: 14px !important;
    padding: 14px 18px !important;
    font-size: 16px !important;
}

.stTextInput input::placeholder {
    color: #b0b0c8 !important;
}

/* Toggle label */
.stCheckbox, .stToggle {
    color: #e0e0f0 !important;
}

/* Main action button */
div.stButton > button:first-child {
    background: linear-gradient(90deg, #FF4B2B, #FF416C);
    color: white;
    font-size: 18px;
    font-weight: 700;
    padding: 14px 30px;
    border: none;
    border-radius: 50px;
    box-shadow: 0 4px 20px rgba(255, 65, 108, 0.4);
    transition: all 0.25s ease-in-out;
    width: 100%;
    letter-spacing: 0.5px;
}

div.stButton > button:first-child:hover {
    transform: translateY(-2px) scale(1.02);
    box-shadow: 0 8px 28px rgba(255, 65, 108, 0.6);
}

div.stButton > button:first-child:active {
    transform: scale(0.98);
}

/* Download button */
div.stDownloadButton > button:first-child {
    background: linear-gradient(90deg, #11998e, #38ef7d);
    color: white;
    font-size: 17px;
    font-weight: 700;
    padding: 12px 26px;
    border: none;
    border-radius: 50px;
    box-shadow: 0 4px 16px rgba(56, 239, 125, 0.35);
    transition: all 0.25s ease-in-out;
    width: 100%;
}

div.stDownloadButton > button:first-child:hover {
    transform: translateY(-2px) scale(1.02);
    box-shadow: 0 8px 22px rgba(56, 239, 125, 0.55);
}

/* Success / error / warning boxes */
div[data-testid="stAlert"] {
    border-radius: 14px;
    font-weight: 500;
}

/* Images */
.stImage img {
    border-radius: 14px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.35);
}

/* Video */
video {
    border-radius: 14px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.35);
}

/* Divider */
hr {
    border-color: rgba(255,255,255,0.1);
}

/* Caption text */
.stCaption, .stMarkdown p {
    color: #cfcfe0;
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    border-right: 1px solid rgba(255,255,255,0.08);
}

section[data-testid="stSidebar"] * {
    color: #e0e0f0 !important;
}

/* Badge pill */
.badge {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 30px;
    background: rgba(255, 65, 108, 0.15);
    border: 1px solid rgba(255, 65, 108, 0.4);
    color: #FF8A80 !important;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 14px;
}
</style>
""", unsafe_allow_html=True)

# --- Sidebar Content ---
with st.sidebar:
    st.markdown("### 🐦 About This Tool")
    st.write(
        "A fast, elegant downloader for **Twitter/X** videos, GIFs, and images. "
        "Just paste a tweet link and grab the media in original quality."
    )
    st.markdown("---")
    st.markdown("### ✨ Features")
    st.markdown("""
    - 🎥 Downloads videos & GIFs at best quality
    - 🖼️ Downloads single or multiple images
    - 📦 Auto-zips multi-image tweets
    - 👀 Optional instant preview
    """)
    st.markdown("---")
    st.markdown("### ⚠️ Rate Limits")
    st.write(
        "Twitter aggressively throttles anonymous requests. "
        "If a download fails, please wait a bit and try again."
    )
    st.markdown("---")
    st.caption("Made with ❤️ using Streamlit, yt-dlp & gallery-dl")

# --- Header ---
st.markdown('<div class="main-title">🐦 Twitter Media Downloader</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Paste any Twitter/X link — we\'ll auto-detect and fetch videos or images for you, instantly.</div>',
    unsafe_allow_html=True
)

# --- Initialize session state ---
if 'media_data' not in st.session_state:
    st.session_state.media_data = None
    st.session_state.media_name = None
    st.session_state.media_type = None
    st.session_state.media_mime = None
    st.session_state.previews = []
    st.session_state.last_url = None
    st.session_state.status_message = None

# --- Input Card ---
with st.container(border=True):
    st.markdown('<span class="badge">STEP 1 · PASTE LINK</span>', unsafe_allow_html=True)
    tweet_url = st.text_input(
        "Enter Twitter/X URL:",
        placeholder="🔗  https://twitter.com/user/status/1234567890",
        label_visibility="collapsed"
    )

    col_a, col_b = st.columns([1, 1])
    with col_a:
        show_preview = st.toggle("👀 Show preview", value=True, help="Show a preview of the media after downloading.")
    with col_b:
        st.write("")

    fetch_clicked = st.button("⬇️ Fetch Media")

# --- Download Logic ---
if fetch_clicked:
    if not tweet_url or not tweet_url.strip():
        st.warning("⚠️ Please enter a valid URL before fetching.")
    else:
        temp_dir = tempfile.mkdtemp(prefix="twitter_dl_")
        try:
            with st.status("🔍 Analyzing link and fetching media...", expanded=True) as status:
                found_media = False

                # 1. Check if the tweet contains a video/GIF
                st.write("Checking for video/GIF content...")
                try:
                    video_check = subprocess.run(
                        ["yt-dlp", "--simulate", "--quiet", tweet_url],
                        capture_output=True, text=True, timeout=60
                    )
                except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                    video_check = None
                    st.write(f"⚠️ Video check skipped: {e}")

                if video_check is not None and video_check.returncode == 0:
                    # --- VIDEO/GIF FOUND ---
                    st.write("🎥 Video detected — downloading best quality...")
                    out_template = os.path.join(temp_dir, "%(id)s.%(ext)s")

                    try:
                        subprocess.run([
                            "yt-dlp",
                            "-f", "bestvideo+bestaudio/best",
                            "--merge-output-format", "mp4",
                            "-o", out_template,
                            tweet_url
                        ], timeout=180)
                    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                        st.write(f"❌ Video download error: {e}")

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
                        found_media = True
                        status.update(label="✅ Video fetched successfully!", state="complete")
                    else:
                        st.session_state.status_message = "error_video"
                        status.update(label="❌ Video download failed.", state="error")

                else:
                    # --- NO VIDEO, TRY IMAGES ---
                    st.write("🖼️ No video found — checking for images...")
                    try:
                        subprocess.run(
                            ["gallery-dl", "-d", temp_dir, tweet_url],
                            timeout=120
                        )
                    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                        st.write(f"❌ Image download error: {e}")

                    files = glob.glob(os.path.join(temp_dir, "**", "*"), recursive=True)
                    files = [f for f in files if os.path.isfile(f)]

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
                            found_media = True
                            status.update(label="✅ Image fetched successfully!", state="complete")
                        else:
                            previews = []
                            for f_path in files:
                                with open(f_path, "rb") as f:
                                    img_data = f.read()
                                previews.append((img_data, os.path.basename(f_path)))

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
                            found_media = True
                            status.update(label=f"✅ {len(previews)} images fetched successfully!", state="complete")
                    else:
                        st.session_state.status_message = "error_image"
                        status.update(label="❌ No media could be found.", state="error")

        except Exception as e:
            st.session_state.status_message = "error_generic"
            st.error(f"An unexpected error occurred: {e}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

# --- Display media from session state (persists across reruns and tab switches) ---
if st.session_state.status_message == "success_video":
    with st.container(border=True):
        st.markdown('<span class="badge">STEP 2 · YOUR MEDIA</span>', unsafe_allow_html=True)
        st.success("✅ Video loaded successfully!")

        if show_preview:
            st.video(st.session_state.media_data)

        spacer_col, button_col = st.columns([2, 1])
        with button_col:
            st.download_button(
                label="⬇️ Download Video",
                data=st.session_state.media_data,
                file_name=st.session_state.media_name,
                mime=st.session_state.media_mime,
                key=f"dl_video_{st.session_state.last_url}"
            )

elif st.session_state.status_message == "success_image_single":
    with st.container(border=True):
        st.markdown('<span class="badge">STEP 2 · YOUR MEDIA</span>', unsafe_allow_html=True)
        st.success("✅ Image loaded successfully!")

        if show_preview:
            st.image(st.session_state.media_data, caption=st.session_state.media_name, use_container_width=True)

        spacer_col, button_col = st.columns([2, 1])
        with button_col:
            st.download_button(
                label="⬇️ Download Image",
                data=st.session_state.media_data,
                file_name=st.session_state.media_name,
                mime=st.session_state.media_mime,
                key=f"dl_img_{st.session_state.last_url}"
            )

elif st.session_state.status_message == "success_image_multi":
    with st.container(border=True):
        st.markdown('<span class="badge">STEP 2 · YOUR MEDIA</span>', unsafe_allow_html=True)
        st.success("✅ Images loaded successfully!")

        if show_preview:
            st.write(f"🖼️ Found **{len(st.session_state.previews)}** images!")
            cols = st.columns(3)
            for idx, (img_data, caption) in enumerate(st.session_state.previews):
                with cols[idx % 3]:
                    st.image(img_data, caption=caption, use_container_width=True)

        spacer_col, button_col = st.columns([2, 1])
        with button_col:
            st.download_button(
                label="⬇️ Download All (ZIP)",
                data=st.session_state.media_data,
                file_name="twitter_images.zip",
                mime="application/zip",
                key=f"dl_zip_{st.session_state.last_url}"
            )

elif st.session_state.status_message == "error_video":
    st.error("❌ Failed to download video. Twitter might be rate-limiting this server. Please try again shortly.")

elif st.session_state.status_message == "error_image":
    st.error("❌ Failed to download images. The link might be text-only, private, or rate-limited by Twitter.")

elif st.session_state.status_message == "error_generic":
    st.error("❌ Something went wrong while processing your request. Please try again.")

# --- Footer Note ---
st.markdown("---")
st.markdown(
    """
    <div style="text-align:center; opacity:0.8;">
        <p style="font-size:13px; color:#b0b0c8;">
            ⚠️ <b>Note about Rate Limiting:</b> Twitter aggressively limits anonymous downloads.
            If you get an error, the server's IP may be temporarily blocked. This is normal for public deployment tools.
        </p>
        <p style="font-size:12px; color:#8a8aa8;">Built with 💻 Streamlit · Powered by yt-dlp & gallery-dl</p>
    </div>
    """,
    unsafe_allow_html=True
)
