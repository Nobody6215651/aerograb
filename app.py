import os
import re
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(
    title="Universal Stream Extractor",
    description="High-performance backend engine designed to extract multi-resolution stream configurations.",
    version="1.1.0"
)

# Enable Cross-Origin Resource Sharing (CORS) for global clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compile a strict regex filter to prevent command injection exploits
URL_VALIDATOR = re.compile(
    r'^https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)$'
)

def sanitize_and_verify_url(url: str) -> str:
    """Verifies the incoming URL against strict security filters."""
    url_stripped = url.strip()
    if not URL_VALIDATOR.match(url_stripped):
        raise ValueError("Malformed URL target rejected.")
    return url_stripped

@app.get("/")
def health_check():
    return {"status": "online", "engine": "yt-dlp", "core": "FastAPI"}

@app.get("/extract")
def extract_media_payload(url: str = Query(..., description="The media URL to extract")):
    try:
        validated_url = sanitize_and_verify_url(url)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))

    # Configuration paths for custom authentication cookies
    cookie_path = os.path.join(os.getcwd(), "cookies.txt")
    
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }

    # Dynamically inject the Netscape cookie file if present on the server
    if os.path.exists(cookie_path):
        ydl_opts['cookiefile'] = cookie_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            raw_info = ydl.extract_info(validated_url, download=False)
            sanitized_info = ydl.sanitize_info(raw_info)

        formats_list = sanitized_info.get("formats", [])
        video_payload = []
        audio_payload = []

        # Parse available format streams for client-side resolution rendering
        for fmt in formats_list:
            stream_url = fmt.get("url")
            if not stream_url:
                continue

            vcodec = fmt.get("vcodec", "none")
            acodec = fmt.get("acodec", "none")
            height = fmt.get("height")
            ext = fmt.get("ext", "mp4")

            # Audio extraction logic: Parse streams that contain audio without video [cite: 18, 19]
            if vcodec == "none" and acodec != "none":
                audio_payload.append({
                    "format_id": fmt.get("format_id"),
                    "ext": "mp3" if ext in ["m4a", "webm", "opus"] else ext,
                    "url": stream_url,
                    "bitrate": int(fmt.get("abr", 128)),
                    "filesize": fmt.get("filesize") or fmt.get("filesize_approx")
                })

            # Video extraction logic: Target exact resolutions requested by user interface [cite: 20, 21]
            elif vcodec != "none":
                if height in [480, 720, 1080]:
                    video_payload.append({
                        "format_id": fmt.get("format_id"),
                        "resolution": f"{height}p",
                        "height": height,
                        "ext": ext if ext == "mp4" else "mp4",
                        "url": stream_url,
                        "filesize": fmt.get("filesize") or fmt.get("filesize_approx")
                    })

        # Fallback mechanism: If no exact resolutions match, capture generic video files [cite: 8, 20]
        if not video_payload:
            for fmt in formats_list:
                height = fmt.get("height")
                if height and height >= 360 and fmt.get("vcodec") != "none":
                    video_payload.append({
                        "format_id": fmt.get("format_id"),
                        "resolution": f"{height}p",
                        "height": height,
                        "ext": fmt.get("ext", "mp4"),
                        "url": fmt.get("url"),
                        "filesize": fmt.get("filesize") or fmt.get("filesize_approx")
                    })

        return {
            "title": sanitized_info.get("title", "Extracted Media Stream"),
            "uploader": sanitized_info.get("uploader", "Generic Platform Source"),
            "thumbnail": sanitized_info.get("thumbnail"),
            "duration_seconds": sanitized_info.get("duration"),
            "videos": sorted(video_payload, key=lambda x: x['height'], reverse=True),
            "audios": sorted(audio_payload, key=lambda x: x['bitrate'], reverse=True)
        }

    except Exception as raw_exc:
        raise HTTPException(status_code=500, detail=f"Core extraction engine error: {str(raw_exc)}")