import base64
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import random
import os
# from proxies import PROXY_LIST

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

def download_reel(url: str):
    output_filename = "reel.mp4"
    session_id = os.getenv("INSTAGRAM_SESSIONID")
    if not session_id:
        raise Exception("Instagram session ID is missing! Add it as an environment variable.")
    # selected_proxy = random.choice(PROXY_LIST)
    
    ydl_opts = {
        "format": "best",
        "cookies": f"sessionid={session_id}",  # Use stored session ID
        # "outtmpl": "downloads/%(title)s.%(ext)s",
        "outtmpl": "/tmp/%(title)s.%(ext)s"
        # "format": "mp4",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if os.path.exists(output_filename):
        return output_filename
    return None

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