import streamlit as st
import os
import io
import subprocess
import tempfile
import glob
import zipfile
import mimetypes

# --- Page Configuration ---
st.set_page_config(page_title="Twitter Media Downloader", page_icon="🐦", layout="centered")

# --- Custom CSS for Stylish Buttons ---
st.markdown("""
<style>
/* Style for the main action button ('Fetch Video') */
div.stButton > button:first-child {
    background: linear-gradient(90deg, #FF4B2B, #FF416C);
    color: white;
    font-size: 18px;
    font-weight: bold;
    padding: 12px 30px;
    border: none;
    border-radius: 50px; /* Makes it a pill shape */
    box-shadow: 0 4px 14px 0 rgba(0, 0, 0, 0.1);
    transition: all 0.3s ease-in-out;
    width: 100%;
}

div.stButton > button:first-child:hover {
    transform: scale(1.03);
    box-shadow: 0 6px 20px 0 rgba(0, 0, 0, 0.2);
}

/* Style for the file download button */
div.stDownloadButton > button:first-child {
    background: linear-gradient(90deg, #FF4B2B, #FF416C);
    color: white;
    font-size: 18px;
    font-weight: bold;
    padding: 12px 30px;
    border: none;
    border-radius: 50px;
    box-shadow: 0 4px 14px 0 rgba(0, 0, 0, 0.1);
    transition: all 0.3s ease-in-out;
    width: 100%;
}

div.stDownloadButton > button:first-child:hover {
    transform: scale(1.03);
    box-shadow: 0 6px 20px 0 rgba(0, 0, 0, 0.2);
}
</style>
""", unsafe_allow_html=True)

st.title("Twitter Media Downloader 🐦")
st.write("Paste a Twitter/X link below. The app will automatically detect and download any videos or images from the tweet.")

# --- Initialize session state ---
if 'media_data' not in st.session_state:
    st.session_state.media_data = None
    st.session_state.media_name = None
    st.session_state.media_type = None
    st.session_state.media_mime = None
    st.session_state.previews = []
    st.session_state.last_url = None
    st.session_state.status_message = None

# --- Input Field ---
tweet_url = st.text_input("Enter Twitter/X URL:", placeholder="https://twitter.com/user/status/1234567890", label_visibility="collapsed")

show_preview = st.toggle("Show preview", value=True, help="If enabled, a preview of the media will be shown after loading.")

# --- Download Logic ---
if st.button("⬇️ Fetch Media"):
    if not tweet_url:
        st.warning("Please enter a valid URL.")
    else:
        # Create a temporary directory for this specific download session
        temp_dir = tempfile.mkdtemp(prefix="twitter_dl_")
        
        with st.spinner("Analyzing link and fetching media..."):
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

# --- Display media from session state (persists across reruns and tab switches) ---
if st.session_state.status_message == "success_video":
    st.success("✅ Media loaded successfully!")
    
    if show_preview:
        st.video(st.session_state.media_data)
        
    spacer_col, button_col = st.columns([2, 1])
    with button_col:
        st.download_button(
            label="Download Video",
            data=st.session_state.media_data,
            file_name=st.session_state.media_name,
            mime=st.session_state.media_mime,
            key=f"dl_video_{st.session_state.last_url}"
        )

elif st.session_state.status_message == "success_image_single":
    st.success("✅ Media loaded successfully!")
    
    if show_preview:
        st.image(st.session_state.media_data, caption=st.session_state.media_name, use_column_width=True)
        
    spacer_col, button_col = st.columns([2, 1])
    with button_col:
        st.download_button(
            label="Download Image",
            data=st.session_state.media_data,
            file_name=st.session_state.media_name,
            mime=st.session_state.media_mime,
            key=f"dl_img_{st.session_state.last_url}"
        )

elif st.session_state.status_message == "success_image_multi":
    st.success("✅ Media loaded successfully!")
    
    if show_preview:
        st.write(f"Found {len(st.session_state.previews)} images!")
        cols = st.columns(3)
        for idx, (img_data, caption) in enumerate(st.session_state.previews):
            with cols[idx % 3]:
                st.image(img_data, caption=caption, use_column_width=True)
                
    spacer_col, button_col = st.columns([2, 1])
    with button_col:
        st.download_button(
            label="Download All (ZIP)",
            data=st.session_state.media_data,
            file_name="twitter_images.zip",
            mime="application/zip",
            key=f"dl_zip_{st.session_state.last_url}"
        )

elif st.session_state.status_message == "error_video":
    st.error("Failed to download video. Twitter might be rate-limiting this server.")
elif st.session_state.status_message == "error_image":
    st.error("Failed to download images. The link might be text-only, private, or rate-limited by Twitter.")

# --- Footer Note ---
st.markdown("---")
st.caption("⚠️ **Note about Rate Limiting:** Twitter aggressively limits anonymous downloads. If you get an error, it means the server's IP has been temporarily blocked by Twitter. This is normal for public deployment tools.")
