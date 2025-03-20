import base64
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from enum import Enum
import requests
import json

CLIENT_URL = os.getenv("CLIENT_URL")
CLIENT_APP = os.getenv("CLIENT_APP")

app = FastAPI()

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReelType(str, Enum):
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"

class ReelRequest(BaseModel):
    url: str
    type: ReelType

def download_instagram_reel(url: str):
    try:
        output_filename = "ree_video.mp4"
        # Prepare headers and payload
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": CLIENT_APP,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "url": url,
            "action": "post",
        }

        # Send request to client
        response = requests.post(CLIENT_URL, headers=headers, data=data)
        if response.status_code != 200:
            print("Failed to connect to client:", response.status_code)
            return None

        # Initialize video_url outside the inner try block
        video_url = None
        
        # Parse JSON response
        try:
            response_data = json.loads(response.text)
            video_url = response_data["files"][0]["video_url"]
            print(f"Found video URL: {video_url}")
        except (json.JSONDecodeError, KeyError) as e:
            print("Failed to parse video URL from response:", e)
            print("Response:", response.text)
            return None

        # Download the video if video_url was set
        if video_url:
            video_response = requests.get(video_url, stream=True)
            if video_response.status_code == 200:
                with open(output_filename, "wb") as f:
                    for chunk in video_response.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)
                print("Video downloaded as 'reel_video.mp4'")
                return output_filename
            else:
                print("Failed to download video:", video_response.status_code)
        else:
            print("No video URL found to download")

    except Exception as e:
        print(f"An error occurred while downloading reel: {e}")

# Function to encode video to Base64
def encode_video_to_base64(video_path: str):
    """Convert video file to Base64 encoded string."""
    with open(video_path, "rb") as video_file:
        encoded_string = base64.b64encode(video_file.read()).decode("utf-8")
    return encoded_string

# API endpoint to download reel
@app.post("/download-reel/")
def get_reel(data: ReelRequest):
    try:
        video_path = None

        # Handle Instagram Reels
        if data.type == ReelType.INSTAGRAM:
            video_path = download_instagram_reel(data.url)
        # Handle YouTube Shorts
        elif data.type == ReelType.YOUTUBE:
            raise HTTPException(status_code=400, detail="Youtube Feature is coming..")

        if not video_path:
            raise HTTPException(status_code=400, detail="Failed to download video")

        # Convert video to Base64
        base64_video = encode_video_to_base64(video_path)

        # Remove file after encoding to free space
        os.remove(video_path)

        return {"message": "Download successful", "video_base64": base64_video}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Home page
@app.get("/")
def get_home_page():
    return "Vinsta services welcome!"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)