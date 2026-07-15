import streamlit as st
import os
import subprocess
import tempfile
import glob
import zipfile
import mimetypes

# --- Page Configuration ---
st.set_page_config(page_title="Twitter Media Downloader", page_icon="🐦", layout="centered")

st.title("Twitter Media Downloader 🐦")
st.write("Paste a Twitter/X link below. The app will automatically detect and download any videos or images from the tweet.")

# --- Input Field ---
tweet_url = st.text_input("Enter Twitter/X URL:", placeholder="https://twitter.com/user/status/1234567890")

# --- Download Logic ---
if st.button("Download Media", type="primary"):
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
                st.info("🎬 Video or GIF detected. Downloading...")
                out_template = os.path.join(temp_dir, "%(id)s.%(ext)s")
                
                # Run download
                subprocess.run(["yt-dlp", "-o", out_template, tweet_url])
                
                # Find the downloaded file
                files = glob.glob(os.path.join(temp_dir, "*"))
                
                if files:
                    file_path = files[0]
                    file_name = os.path.basename(file_path)
                    mime_type = mimetypes.guess_type(file_path)[0] or "video/mp4"
                    
                    # Show video preview in the app
                    st.video(open(file_path, 'rb').read())
                    
                    # Provide download button
                    with open(file_path, "rb") as f:
                        st.success("Download complete!")
                        st.download_button(
                            label="⬇️ Click here to download the video",
                            data=f,
                            file_name=file_name,
                            mime=mime_type
                        )
                else:
                    st.error("Failed to download video. Twitter might be rate-limiting this server.")
            
            else:
                # --- NO VIDEO, TRY IMAGES ---
                st.info("🖼️ No video detected. Attempting to download images...")
                subprocess.run(["gallery-dl", "-d", temp_dir, tweet_url])
                
                # Find all downloaded images (gallery-dl sometimes creates subfolders)
                files = glob.glob(os.path.join(temp_dir, "**", "*"), recursive=True)
                files = [f for f in files if os.path.isfile(f)] # Filter out directories
                
                if files:
                    st.success("Download complete!")
                    
                    # If only one image, provide direct download
                    if len(files) == 1:
                        file_path = files[0]
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
                    else:
                        # If multiple images, show them and zip them for download
                        st.write(f"Found {len(files)} images!")
                        
                        # Show a preview grid
                        st.session_state['previews'] = []
                        cols = st.columns(3)
                        for idx, f_path in enumerate(files):
                            with cols[idx % 3]:
                                st.image(f_path, use_column_width=True)
                        
                        # Zip the files
                        zip_path = os.path.join(temp_dir, "twitter_images.zip")
                        with zipfile.ZipFile(zip_path, 'w') as zipf:
                            for f_path in files:
                                zipf.write(f_path, os.path.basename(f_path))
                                
                        # Provide download button for the ZIP
                        with open(zip_path, "rb") as f:
                            st.download_button(
                                label="⬇️ Click here to download all images (ZIP)",
                                data=f,
                                file_name="twitter_images.zip",
                                mime="application/zip"
                            )
                else:
                    st.error("Failed to download images. The link might be text-only, private, or rate-limited by Twitter.")

# --- Footer Note ---
st.markdown("---")
st.caption("⚠️ **Note about Rate Limiting:** Twitter aggressively limits anonymous downloads. If you get an error, it means the server's IP has been temporarily blocked by Twitter. This is normal for public deployment tools.")
