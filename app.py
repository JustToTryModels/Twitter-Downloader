# app_advanced.py
import streamlit as st
import os
import subprocess
import tempfile
import glob
import mimetypes
import hashlib
import json
import re
import requests
from pathlib import Path

# --- Page Configuration ---
st.set_page_config(
    page_title="Advanced X Media Downloader",
    page_icon="🐦",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# --- Custom CSS (same premium UI as before) ---
st.markdown(
    """
<style>
    /* ... (Your existing CSS remains entirely valid and is omitted for brevity) ... */
    .media-card { background: #ffffff; border-radius: 16px; padding: 15px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); border: 1px solid #EFF3F4; margin-bottom: 20px; }
    @media (prefers-color-scheme: dark) { .media-card { background: #15202B; border: 1px solid #38444D; } }
</style>
""",
    unsafe_allow_html=True,
)

# --- Header Section ---
st.markdown('<div class="main-title">X / Twitter Downloader 🐦</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Advanced, multi-strategy media downloader with cookie support.</div>', unsafe_allow_html=True)

# --- Session State Initialization ---
if "media_items" not in st.session_state:
    st.session_state.media_items = []
    st.session_state.last_url = None
    st.session_state.status_message = None
    st.session_state.error_details = None

# --- Helper Functions ---

def get_cookies_from_browser() -> str | None:
    """
    Attempts to export cookies from common browsers into a Netscape-format string.
    Returns the cookie string or None if extraction fails.
    """
    # List of browser profiles to try. The format is (browser_name, profile_path)
    # This is a best-effort list. Paths vary by OS and user setup.
    browser_configs = [
        ("chrome", None),  # Default profile
        ("firefox", None),  # Default profile
        ("edge", None),
        ("brave", None),
    ]

    for browser, profile in browser_configs:
        try:
            # We use gallery-dl's --cookies-from-browser flag to extract cookies.
            # We just need the raw cookie file content, so we use a temporary file.
            with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False) as tmp:
                cookie_file_path = tmp.name

            cmd = ["gallery-dl", "--cookies-from-browser", browser]
            if profile:
                cmd += ["--profile", profile]
            # We use a harmless command that requires cookies to trigger the export.
            cmd += ["--verbose", "--simulate", "https://x.com/robots.txt"]

            subprocess.run(cmd, capture_output=True, text=True, timeout=15)

            if os.path.exists(cookie_file_path) and os.path.getsize(cookie_file_path) > 0:
                with open(cookie_file_path, "r") as f:
                    cookie_content = f.read()
                os.unlink(cookie_file_path)  # Clean up
                return cookie_content
            else:
                if os.path.exists(cookie_file_path):
                    os.unlink(cookie_file_path)
        except Exception:
            # If a browser fails, just move on to the next one.
            continue
    return None


def download_via_syndication_api(tweet_url: str, temp_dir: str) -> list:
    """
    Fallback method: Uses X's public Syndication API to fetch media URLs,
    then downloads them directly with requests.
    """
    extracted_media = []
    # Extract Tweet ID from URL
    match = re.search(r"status/(\d+)", tweet_url)
    if not match:
        return []
    tweet_id = match.group(1)

    syndication_url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&lang=en"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    }

    try:
        response = requests.get(syndication_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        # The syndication API structure can vary, but media is often in 'mediaDetails' or 'video'
        media_items = []
        if "mediaDetails" in data:
            media_items.extend(data["mediaDetails"])
        if "video" in data and "variants" in data["video"]:
            media_items.append(data["video"])

        for i, media in enumerate(media_items):
            media_url = None
            media_type = "image"
            file_ext = ".jpg"

            if "media_url_https" in media:  # Image
                media_url = media["media_url_https"]
            elif "variants" in media:  # Video
                # Select the highest bitrate MP4 variant
                mp4_variants = [v for v in media["variants"] if v.get("content_type") == "video/mp4"]
                if mp4_variants:
                    best_variant = sorted(mp4_variants, key=lambda x: x.get("bitrate", 0), reverse=True)[0]
                    media_url = best_variant["src"]
                    media_type = "video"
                    file_ext = ".mp4"

            if media_url:
                file_name = f"syndication_{tweet_id}_{i}{file_ext}"
                file_path = os.path.join(temp_dir, file_name)
                # Download the file
                file_resp = requests.get(media_url, headers=headers, stream=True, timeout=20)
                file_resp.raise_for_status()
                with open(file_path, "wb") as f:
                    for chunk in file_resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                # Read the file back to create the media item dict
                with open(file_path, "rb") as f:
                    data = f.read()
                mime_type, _ = mimetypes.guess_type(file_path)
                extracted_media.append({
                    "name": file_name,
                    "data": data,
                    "mime": mime_type or "application/octet-stream",
                    "type": media_type,
                })
    except Exception as e:
        # Log the error but don't crash; the main function will handle the empty list.
        pass

    return extracted_media


# --- Input Area ---
st.write("")
tweet_url = st.text_input("URL Input", placeholder="Paste X/Twitter link here...", label_visibility="collapsed")

col1, col2 = st.columns([3, 1])
with col1:
    show_preview = st.toggle("Show media previews", value=True)
    use_browser_cookies = st.toggle(
        "Use browser cookies for authentication (Required for most content)",
        value=True,
        help="If enabled, the app will try to use your logged-in browser session. Ensure you are logged into X in a supported browser.",
    )
with col2:
    fetch_clicked = st.button("Get Media")

st.markdown("<br>", unsafe_allow_html=True)

# --- Download Logic ---
if fetch_clicked:
    if not tweet_url:
        st.warning("⚠️ Please enter a valid URL.")
    else:
        with tempfile.TemporaryDirectory(prefix="twitter_dl_adv_") as temp_dir:
            with st.spinner("Analyzing link with advanced strategies..."):
                extracted_media = []
                cookie_file_path = None

                # --- Strategy 1: Authenticated yt-dlp with Cookies ---
                if use_browser_cookies:
                    cookie_content = get_cookies_from_browser()
                    if cookie_content:
                        # Write cookies to a temporary file for yt-dlp
                        with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False) as tmp_cookie:
                            tmp_cookie.write(cookie_content)
                            cookie_file_path = tmp_cookie.name

                        try:
                            subprocess.run(
                                [
                                    "yt-dlp",
                                    "--cookies", cookie_file_path,
                                    "-f", "bestvideo+bestaudio/best",
                                    "--merge-output-format", "mp4",
                                    "-o", os.path.join(temp_dir, "ytdlp_%(id)s_%(autonumber)s.%(ext)s"),
                                    tweet_url,
                                ],
                                capture_output=True,
                                text=True,
                                timeout=60,
                            )
                        except subprocess.TimeoutExpired:
                            pass
                        finally:
                            if cookie_file_path and os.path.exists(cookie_file_path):
                                os.unlink(cookie_file_path)

                # --- Strategy 2: Fallback to Syndication API ---
                if not extracted_media:
                    extracted_media = download_via_syndication_api(tweet_url, temp_dir)

                # --- Strategy 3: Fallback to yt-dlp with guest API modes ---
                if not extracted_media:
                    try:
                        subprocess.run(
                            [
                                "yt-dlp",
                                "--extractor-args", "twitter:api=syndication",
                                "-f", "bestvideo+bestaudio/best",
                                "--merge-output-format", "mp4",
                                "-o", os.path.join(temp_dir, "ytdlp_guest_%(id)s_%(autonumber)s.%(ext)s"),
                                tweet_url,
                            ],
                            capture_output=True,
                            text=True,
                            timeout=60,
                        )
                    except subprocess.TimeoutExpired:
                        pass

                # --- Collect ALL downloaded files ---
                all_files = glob.glob(os.path.join(temp_dir, "**", "*"), recursive=True)
                file_paths = [f for f in all_files if os.path.isfile(f)]

                valid_video_exts = [".mp4", ".webm", ".mkv"]
                valid_image_exts = [".jpg", ".jpeg", ".png", ".gif", ".webp"]

                seen_hashes = set()

                for fp in file_paths:
                    basename = os.path.basename(fp)
                    basename_lower = basename.lower()

                    is_video = any(basename_lower.endswith(ext) for ext in valid_video_exts)
                    is_image = any(basename_lower.endswith(ext) for ext in valid_image_exts)

                    if not (is_video or is_image):
                        continue

                    # Deduplication: skip videos not from yt-dlp if we already have some from syndication
                    if is_video and not basename.startswith("ytdlp") and not basename.startswith("syndication"):
                        # This is likely a gallery-dl duplicate, skip it
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
                        "type": media_type,
                    })

                if extracted_media:
                    st.session_state.media_items = extracted_media
                    st.session_state.last_url = tweet_url
                    st.session_state.status_message = "success"
                else:
                    st.session_state.status_message = "error_no_media"

# --- Display Results (unchanged from your original code) ---
st.markdown("---")
if st.session_state.status_message == "success":
    st.success(f"✅ Successfully extracted {len(st.session_state.media_items)} media item(s)!")
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
                key=f"dl_{idx}_{st.session_state.last_url}",
            )
            st.markdown('</div>', unsafe_allow_html=True)
elif st.session_state.status_message == "error_no_media":
    st.error("🚫 **Failed to fetch media.** All strategies failed. Please ensure you are logged into X in your browser and try again.")
elif st.session_state.status_message == "error_general":
    st.error(f"⚠️ **An unexpected error occurred:** {st.session_state.error_details}")

# --- Footer & Clear Cache (unchanged) ---
st.markdown("<br><br>", unsafe_allow_html=True)
cc_col1, cc_col2, cc_col3 = st.columns([1, 1, 1])
with cc_col2:
    if st.button("Clear Cache", use_container_width=True):
        st.session_state.media_items = []
        st.session_state.last_url = None
        st.session_state.status_message = None
        st.session_state.error_details = None
        st.rerun()
st.caption("ℹ️ **Note:** This tool uses your browser's authenticated session to access content. It requires that you are logged into X in Chrome, Firefox, Edge, or Brave.")
