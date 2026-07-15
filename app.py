import streamlit as st
import os
import subprocess
import tempfile
import glob
import zipfile
import mimetypes

# --- Page Configuration ---
st.set_page_config(page_title="Fast Twitter Media Downloader", page_icon="⚡", layout="centered")

st.title("⚡ Fast Twitter Media Downloader")
st.write("Paste a Twitter/X link below. Automatically detects and downloads the highest quality videos or images.")

# --- Input Field ---
tweet_url = st.text_input("Enter Twitter/X URL:", placeholder="https://twitter.com/user/status/1234567890")

# --- Download Logic ---
if st.button("Download Media", type="primary"):
    if not tweet_url:
        st.warning("Please enter a valid URL.")
    else:
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp(prefix="twitter_dl_")
        
        with st.spinner("Fetching media at max speed..."):
            
            # 1. ATTEMPT VIDEO DOWNLOAD FIRST (Run once for speed, fail fast if no video)
            out_template = os.path.join(temp_dir, "%(id)s.%(ext)s")
            video_cmd = [
                "yt-dlp", 
                "-f", "bestvideo*+bestaudio/best",  # Force absolute best quality
                "-q", "--no-warnings", 
                "--retries", "1", "--fragment-retries", "1", "--socket-timeout", "10",  # Fail fast if blocked
                "-o", out_template, 
                tweet_url
            ]
            video_result = subprocess.run(video_cmd, capture_output=True, text=True)
            
            # Find any video files generated
            files = glob.glob(os.path.join(temp_dir, "*.*"))
            
            if video_result.returncode == 0 and files:
                # --- VIDEO/GIF FOUND ---
                file_path = files[0]
                file_name = os.path.basename(file_path)
                mime_type = mimetypes.guess_type(file_path)[0] or "video/mp4"
                
                st.success("✅ Highest quality video downloaded!")
                
                # Fast UI render using file path instead of reading bytes
                st.video(file_path)
                
                with open(file_path, "rb") as f:
                    st.download_button(
                        label="⬇️ Click here to download the video",
                        data=f,
                        file_name=file_name,
                        mime=mime_type
                    )
            
            else:
                # 2. IF NO VIDEO, ATTEMPT IMAGE DOWNLOAD (Fail fast configuration)
                img_cmd = [
                    "gallery-dl", 
                    "-d", temp_dir, 
                    "-q", "--no-warnings", 
                    "--retries", "1", "--socket-timeout", "10",  # Fail fast if blocked
                    tweet_url
                ]
                img_result = subprocess.run(img_cmd, capture_output=True, text=True)
                
                # Find all downloaded images (gallery-dl sometimes creates subfolders)
                all_files = glob.glob(os.path.join(temp_dir, "**", "*"), recursive=True)
                image_files = [f for f in all_files if os.path.isfile(f)]
                
                if img_result.returncode == 0 and image_files:
                    st.success("✅ Highest quality images downloaded!")
                    
                    # Single Image
                    if len(image_files) == 1:
                        file_path = image_files[0]
                        file_name = os.path.basename(file_path)
                        mime_type = mimetypes.guess_type(file_path)[0] or "image/jpeg"
                        
                        st.image(file_path, caption=file_name, use_column_width=True)
                        
                        with open(file_path, "rb") as f:
                            st.download_button(
                                label="⬇️ Click here to download the image",
                                data=f,
                                file_name=file_name,
                                mime=mime_type
                            )
                    
                    # Multiple Images
                    else:
                        st.write(f"Found {len(image_files)} images!")
                        
                        # Fast preview grid using file paths
                        cols = st.columns(3)
                        for idx, f_path in enumerate(image_files):
                            with cols[idx % 3]:
                                st.image(f_path, use_column_width=True)
                        
                        # Zip the files
                        zip_path = os.path.join(temp_dir, "twitter_images.zip")
                        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            for f_path in image_files:
                                zipf.write(f_path, os.path.basename(f_path))
                                
                        with open(zip_path, "rb") as f:
                            st.download_button(
                                label="⬇️ Click here to download all images (ZIP)",
                                data=f,
                                file_name="twitter_images.zip",
                                mime="application/zip"
                            )
                else:
                    st.error("❌ Download failed. Twitter might be rate-limiting this server, or the link is private/text-only.")

# --- Footer Note ---
st.markdown("---")
st.caption("⚡ **Speed Note:** This app is highly optimized to fail fast. If Twitter limits the server, you will see an error in seconds rather than waiting minutes.")
