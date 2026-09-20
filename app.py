# app.py
import streamlit as st
import os
import subprocess
import tempfile
import glob
import mimetypes
import hashlib
import requests
import json
import re

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
    /* ... (Your existing CSS remains unchanged) ... */
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

# --- Helper: Direct Syndication API Fallback ---
def fetch_via_syndication_api(tweet_url):
    """Fallback method using X's syndication API directly."""
    media_items = []
    try:
        # Extract tweet ID from URL
        tweet_id_match = re.search(r'/status/(\d+)', tweet_url)
        if not tweet_id_match:
            return []
        
        tweet_id = tweet_id_match.group(1)
        
        # Generate a random token for the syndication endpoint (as per yt-dlp's approach)
        import random
        import string
        token = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        
        # Call the syndication API
        api_url = "https://cdn.syndication.twimg.com/tweet-result"
        params = {
            'id': tweet_id,
            'token': token,
            'lang': 'en'
        }
        headers = {
            'User-Agent': 'Googlebot/2.1 (+http://www.google.com/bot.html)'
        }
        
        response = requests.get(api_url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # Parse media from the syndication response
        media_details = data.get('mediaDetails', [])
        if not media_details and 'quoted_tweet' in data:
            media_details = data['quoted_tweet'].get('mediaDetails', [])
        
        for detail in media_details:
            if detail.get('type') == 'video' or detail.get('type') == 'animated_gif':
                variants = detail.get('video_info', {}).get('variants', [])
                # Get the highest bitrate MP4
                best_variant = None
                best_bitrate = 0
                for variant in variants:
                    if variant.get('content_type') == 'video/mp4':
                        bitrate = variant.get('bitrate', 0)
                        if bitrate > best_bitrate:
                            best_bitrate = bitrate
                            best_variant = variant
                if best_variant:
                    media_items.append({
                        'url': best_variant['url'],
                        'type': 'video',
                        'ext': 'mp4'
                    })
            elif detail.get('type') == 'photo':
                media_items.append({
                    'url': detail['media_url_https'] + ':orig',
                    'type': 'image',
                    'ext': 'jpg'
                })
        
        return media_items
        
    except Exception as e:
        st.warning(f"Syndication API fallback failed: {str(e)}")
        return []

# --- Download Logic ---
if fetch_clicked:
    if not tweet_url:
        st.warning("⚠️ Please enter a valid URL.")
    else:
        with tempfile.TemporaryDirectory(prefix="twitter_dl_") as temp_dir:
            
            with st.spinner("Analyzing link and extracting all available media..."):
                try:
                    # --- TIER 1: Attempt yt-dlp with syndication API (most stable) ---
                    ytdlp_args_syndication = [
                        "yt-dlp",
                        "--extractor-args", "twitter:api=syndication",
                        "-f", "bestvideo+bestaudio/best",
                        "--merge-output-format", "mp4",
                        "-o", os.path.join(temp_dir, "ytdlp_vid_%(id)s_%(autonumber)s.%(ext)s"),
                        tweet_url
                    ]
                    result_syndication = subprocess.run(ytdlp_args_syndication, capture_output=True, text=True)
                    
                    # Check if syndication succeeded
                    video_files = glob.glob(os.path.join(temp_dir, "ytdlp_vid_*"))
                    
                    if not video_files:
                        # --- TIER 2: Attempt yt-dlp with legacy API ---
                        st.info("Syndication API failed, trying legacy API...")
                        ytdlp_args_legacy = [
                            "yt-dlp",
                            "--extractor-args", "twitter:api=legacy",
                            "-f", "bestvideo+bestaudio/best",
                            "--merge-output-format", "mp4",
                            "-o", os.path.join(temp_dir, "ytdlp_vid_%(id)s_%(autonumber)s.%(ext)s"),
                            tweet_url
                        ]
                        subprocess.run(ytdlp_args_legacy, capture_output=True, text=True)
                        video_files = glob.glob(os.path.join(temp_dir, "ytdlp_vid_*"))
                    
                    # --- TIER 3: If yt-dlp fails entirely, use direct Syndication API ---
                    if not video_files:
                        st.info("yt-dlp failed, attempting direct Syndication API fallback...")
                        syndication_media = fetch_via_syndication_api(tweet_url)
                        if syndication_media:
                            for idx, media in enumerate(syndication_media):
                                try:
                                    resp = requests.get(media['url'], headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
                                    if resp.status_code == 200:
                                        ext = media['ext']
                                        filename = f"syndication_media_{idx}.{ext}"
                                        filepath = os.path.join(temp_dir, filename)
                                        with open(filepath, 'wb') as f:
                                            f.write(resp.content)
                                except Exception as e:
                                    continue
                    
                    # 4. Fetch images using gallery-dl (still works for images)
                    subprocess.run([
                        "gallery-dl", 
                        "--directory", temp_dir, 
                        tweet_url
                    ], capture_output=True)
                    
                    # 5. Collect ALL downloaded files recursively
                    all_files = glob.glob(os.path.join(temp_dir, "**", "*"), recursive=True)
                    file_paths = [f for f in all_files if os.path.isfile(f)]
                    
                    valid_video_exts = [".mp4", ".webm", ".mkv", ".mov"]
                    valid_image_exts = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
                    
                    extracted_media = []
                    seen_hashes = set()
                    
                    for fp in file_paths:
                        basename = os.path.basename(fp)
                        basename_lower = basename.lower()
                        
                        is_video = any(basename_lower.endswith(ext) for ext in valid_video_exts)
                        is_image = any(basename_lower.endswith(ext) for ext in valid_image_exts)
                        
                        if not (is_video or is_image):
                            continue
                            
                        # Skip duplicate videos from gallery-dl
                        if is_video and not (basename.startswith("ytdlp_vid_") or basename.startswith("syndication_media_")):
                            continue
                            
                        with open(fp, "rb") as f:
                            data = f.read()
                        
                        file_hash = hashlib.md5(data).hexdigest()
                        if file_hash in seen_hashes:
                            continue
                        seen_hashes.add(file_hash)
                        
                        mime_type, _ = mimetypes.guess_type(fp)
                        if not mime_type:
                            mime_type = "application/octet-stream"
                        
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

# --- Display Results (Unchanged from your original code) ---
# ... (Your existing display logic remains exactly the same) ...
