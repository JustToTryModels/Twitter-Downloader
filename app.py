import streamlit as st
import requests
import re
import os
import hashlib
import mimetypes
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# --- Page Configuration ---
st.set_page_config(
    page_title="Twitter / X Media Downloader", 
    page_icon="🐦", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- Custom CSS ---
st.markdown("""
<style>
    .block-container {
        padding-top: 2.5rem;
        padding-bottom: 2rem;
        max-width: 850px;
    }
    #MainMenu, footer, header {visibility: hidden;}

    .main-title {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-weight: 800;
        font-size: 2.3rem;
        color: #0F1419;
        text-align: center;
        margin-bottom: 0.3rem;
    }
    .sub-title {
        text-align: center;
        color: #536471;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .stTextInput > div > div > input {
        border-radius: 14px !important;
        padding: 14px 18px !important;
        font-size: 15px !important;
    }
    .media-card {
        background: #ffffff;
        border-radius: 14px;
        padding: 14px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        border: 1px solid #EFF3F4;
        margin-bottom: 16px;
    }
    @media (prefers-color-scheme: dark) {
        .main-title { color: #E7E9EA; }
        .sub-title { color: #71767B; }
        .media-card {
            background: #15202B;
            border: 1px solid #38444D;
        }
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">X / Twitter Downloader 🐦</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">High-res multi-engine extractor (Images, Videos, GIFs) without requiring cookies.</div>', unsafe_allow_html=True)

# --- Session State ---
if 'media_items' not in st.session_state:
    st.session_state.media_items = []
    st.session_state.last_url = None
    st.session_state.status = None
    st.session_state.error = None

# --- Helper Functions ---

def extract_tweet_id(url: str):
    """Extract numeric tweet ID from any X/Twitter URL variant."""
    match = re.search(r'(?:twitter\.com|x\.com)/[^/]+/status/(\d+)', url)
    return match.group(1) if match else None

def optimize_image_url(url: str) -> str:
    """Ensure images are fetched at maximum resolution (name=orig)."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    qs['name'] = ['orig']
    new_query = urlencode(qs, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

def fetch_via_fxtwitter(tweet_id: str):
    """Engine 1: Primary extraction via syndication resolver."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    endpoint = f"https://api.fxtwitter.com/status/{tweet_id}"
    
    resp = requests.get(endpoint, headers=headers, timeout=10)
    if resp.status_code != 200:
        return None
    
    data = resp.json()
    if data.get("code") != 200 or "tweet" not in data:
        return None

    tweet = data["tweet"]
    media_data = tweet.get("media", {})
    results = []

    # Process all media entities
    all_media = media_data.get("all", [])
    for idx, item in enumerate(all_media):
        mtype = item.get("type")
        direct_url = None

        if mtype == "photo":
            direct_url = optimize_image_url(item.get("url"))
            item_type = "image"
            ext = "jpg"
        elif mtype in ("video", "gif"):
            item_type = "video"
            ext = "mp4"
            # Choose highest bitrate variant if available
            variants = item.get("variants", [])
            if variants:
                mp4_variants = [v for v in variants if v.get("content_type") == "video/mp4"]
                if mp4_variants:
                    best = max(mp4_variants, key=lambda v: v.get("bitrate", 0))
                    direct_url = best.get("url")
            if not direct_url:
                direct_url = item.get("url")
        else:
            continue

        if direct_url:
            filename = f"twitter_{tweet_id}_{idx + 1}.{ext}"
            results.append({
                "url": direct_url,
                "type": item_type,
                "filename": filename
            })

    return results

def fetch_via_vxtwitter(tweet_id: str):
    """Engine 2: Secondary fallback extraction."""
    headers = {"User-Agent": "Mozilla/5.0"}
    endpoint = f"https://api.vxtwitter.com/Twitter/status/{tweet_id}"
    
    resp = requests.get(endpoint, headers=headers, timeout=10)
    if resp.status_code != 200:
        return None
        
    data = resp.json()
    media_list = data.get("media_extended", [])
    results = []
    
    for idx, item in enumerate(media_list):
        mtype = item.get("type")
        url = item.get("url")
        if not url:
            continue

        if mtype == "image":
            url = optimize_image_url(url)
            results.append({
                "url": url,
                "type": "image",
                "filename": f"twitter_{tweet_id}_{idx + 1}.jpg"
            })
        elif mtype in ("video", "gif"):
            results.append({
                "url": url,
                "type": "video",
                "filename": f"twitter_{tweet_id}_{idx + 1}.mp4"
            })
            
    return results

def fetch_via_ytdlp(url: str):
    """Engine 3: In-memory yt-dlp metadata extraction."""
    import yt_dlp
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True
    }
    
    results = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            return None
            
        entries = info.get('entries', [info])
        for idx, entry in enumerate(entries):
            formats = entry.get('formats', [])
            # Find best MP4 video
            valid_mp4s = [f for f in formats if f.get('ext') == 'mp4' and f.get('vcodec') != 'none']
            best_url = None
            if valid_mp4s:
                best = max(valid_mp4s, key=lambda f: f.get('tbr', 0) or 0)
                best_url = best.get('url')
            elif entry.get('url'):
                best_url = entry.get('url')

            if best_url:
                results.append({
                    "url": best_url,
                    "type": "video",
                    "filename": f"twitter_video_{idx + 1}.mp4"
                })
    return results

def download_asset(url: str):
    """Download binary asset from CDN."""
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, stream=True, timeout=15)
    if res.status_code == 200:
        return res.content
    return None

# --- UI & Interaction ---

tweet_url = st.text_input(
    "URL Input", 
    placeholder="https://x.com/username/status/123456789...", 
    label_visibility="collapsed"
)

col1, col2 = st.columns([3, 1])
with col1:
    show_preview = st.toggle("Show Previews", value=True)
with col2:
    fetch_clicked = st.button("Extract Media", use_container_width=True)

if fetch_clicked:
    if not tweet_url:
        st.warning("⚠️ Please provide a valid link.")
    else:
        tweet_id = extract_tweet_id(tweet_url)
        
        if not tweet_id:
            st.error("❌ Could not parse a valid Tweet/Post ID from the supplied URL.")
        else:
            with st.spinner("Resolving media sources..."):
                items = None
                
                # Step 1: Attempt FixTweet resolver
                try:
                    items = fetch_via_fxtwitter(tweet_id)
                except Exception:
                    items = None
                
                # Step 2: Attempt VxTwitter fallback
                if not items:
                    try:
                        items = fetch_via_vxtwitter(tweet_id)
                    except Exception:
                        items = None
                        
                # Step 3: Attempt native yt-dlp fallback
                if not items:
                    try:
                        items = fetch_via_ytdlp(tweet_url)
                    except Exception as e:
                        st.session_state.error = str(e)

                if items:
                    downloaded_items = []
                    for it in items:
                        data = download_asset(it["url"])
                        if data:
                            mime, _ = mimetypes.guess_type(it["filename"])
                            downloaded_items.append({
                                "filename": it["filename"],
                                "type": it["type"],
                                "data": data,
                                "mime": mime or "application/octet-stream"
                            })
                    
                    if downloaded_items:
                        st.session_state.media_items = downloaded_items
                        st.session_state.last_url = tweet_url
                        st.session_state.status = "success"
                    else:
                        st.session_state.status = "error_download"
                else:
                    st.session_state.status = "error_not_found"

st.markdown("---")

# --- Results Presentation ---
if st.session_state.status == "success":
    st.success(f"✅ Found and extracted {len(st.session_state.media_items)} media asset(s).")
    
    cols = st.columns(2)
    for idx, item in enumerate(st.session_state.media_items):
        with cols[idx % 2]:
            st.markdown('<div class="media-card">', unsafe_allow_html=True)
            
            if show_preview:
                if item["type"] == "video":
                    st.video(item["data"])
                else:
                    st.image(item["data"], use_column_width=True)
                    
            st.download_button(
                label=f"💾 Download {item['type'].capitalize()}",
                data=item["data"],
                file_name=item["filename"],
                mime=item["mime"],
                key=f"dl_btn_{idx}"
            )
            st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.status == "error_not_found":
    st.error("🚫 No media found. The post may contain only text, or access was restricted.")
elif st.session_state.status == "error_download":
    st.error("⚠️ Failed while transferring binary media data from CDN servers.")

# Clear Cache
if st.session_state.media_items:
    if st.button("Clear Results"):
        st.session_state.media_items = []
        st.session_state.status = None
        st.rerun()
