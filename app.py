import base64
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import instaloader
import re

app = FastAPI()

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReelRequest(BaseModel):
    url: str

# Initialize Instaloader
loader = instaloader.Instaloader(download_pictures=False, download_comments=False, save_metadata=False, post_metadata_txt_pattern="")

def extract_shortcode(url: str):
    """Extracts the Instagram reel shortcode from various URL formats."""
    match = re.search(r"instagram\.com/reel/([^/?]+)", url)
    if match:
        return match.group(1)  # Extracts only the shortcode
    raise ValueError("Invalid Instagram reel URL")

def login_instagram():
    """Use Instagram cookies for authentication instead of session files."""
    cookies_file = "cookies.txt"

    if not os.path.exists(cookies_file):
        raise HTTPException(status_code=400, detail="Cookies file is missing! Extract it from Firefox.")

    try:
        loader.load_session_from_file(cookies_file)
        print("✅ Logged in using cookies")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to load cookies: {str(e)}")

def download_reel(url: str):
    """Download Instagram reel only (without thumbnails or metadata)."""
    try:
        # Extract shortcode from URL
        shortcode = extract_shortcode(url)
        post = instaloader.Post.from_shortcode(loader.context, shortcode)

        # Configure Instaloader to download only video files
        loader.download_post(post, target="downloads")

        # Find and return only the MP4 file (skip thumbnails)
        for file in os.listdir("downloads"):
            if file.endswith(".mp4"):
                return os.path.join("downloads", file)

        raise Exception("Download failed. No video found.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

def encode_video_to_base64(video_path: str):
    """Convert video file to Base64 encoded string."""
    with open(video_path, "rb") as video_file:
        encoded_string = base64.b64encode(video_file.read()).decode("utf-8")
    return encoded_string

@app.post("/download-reel/")
def get_instagram_reel(data: ReelRequest):
    try:
        video_path = download_reel(data.url)
        if not video_path:
            raise HTTPException(status_code=400, detail="Failed to download video")

        # Convert video to Base64
        base64_video = encode_video_to_base64(video_path)

        # Remove file after encoding to free space
        os.remove(video_path)

        return {"message": "Download successful", "video_base64": base64_video}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/")
def get_home_page():
    return "Home"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)