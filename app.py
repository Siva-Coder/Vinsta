import base64
import os
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
from enum import Enum
# from pymongo import MongoClient
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime
import browser_cookie3

app = FastAPI()

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection
client = MongoClient("mongodb+srv://siva:123456mongodb@vinsta.ljqdp.mongodb.net/?retryWrites=true&w=majority&appName=vinsta", server_api=ServerApi('1'))

db = client["cookies_db"]
cookies_collection = db["cookies"]

class ReelType(str, Enum):
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"

class ReelRequest(BaseModel):
    url: str
    type: ReelType

# Function to extract and save cookies to MongoDB
def save_cookies_to_db(platform: str):
    try:
        if platform == "instagram":
            # Extract Instagram cookies using browser-cookie3
            cookies = list(browser_cookie3.firefox(domain_name="instagram.com"))
        elif platform == "youtube":
            # Extract YouTube cookies using browser-cookie3
            cookies = list(browser_cookie3.firefox(domain_name="youtube.com"))
        else:
            raise ValueError("Invalid platform")

        # Convert cookies to a list of dictionaries in Netscape format
        cookies_data = [{
            "domain": cookie.domain,
            "flag": "TRUE" if cookie.domain.startswith('.') else "FALSE",
            "path": cookie.path,
            "secure": "TRUE" if cookie.secure else "FALSE",
            "expires": int(cookie.expires) if cookie.expires else "0",
            "name": cookie.name,
            "value": cookie.value,
        } for cookie in cookies]

        # Save cookies to MongoDB
        cookies_collection.update_one(
            {"platform": platform},
            {"$set": {"cookies": cookies_data, "timestamp": datetime.utcnow()}},
            upsert=True,
        )
        print(f"Cookies for {platform} have been saved to MongoDB.")
    except Exception as e:
        print(f"An error occurred while extracting cookies: {e}")
        raise HTTPException(status_code=500, detail="Failed to extract cookies.")

# Function to get cookies from MongoDB
def get_cookies_from_db(platform: str):
    cookies_data = cookies_collection.find_one({"platform": platform})
    if not cookies_data:
        raise HTTPException(status_code=400, detail=f"No cookies found for {platform}. Please refresh cookies.")
    return cookies_data["cookies"]

def download_instagram_reel(url: str):
    output_filename = "reel.mp4"

    # Get Instagram cookies from MongoDB
    cookies = get_cookies_from_db("instagram")

    # Save cookies to a temporary file in Netscape format
    with open("cookies.txt", "w") as f:
        # Add the required header line
        f.write("# Netscape HTTP Cookie File\n")

        # Write each cookie in Netscape format
        for cookie in cookies:
            line = (
                f"{cookie['domain']}\t"
                f"{cookie['flag']}\t"
                f"{cookie['path']}\t"
                f"{cookie['secure']}\t"
                f"{cookie['expires']}\t"
                f"{cookie['name']}\t"
                f"{cookie['value']}\n"
            )
            f.write(line)

    # Verify the contents of the cookies file
    with open("cookies.txt", "r") as f:
        print("Contents of cookies.txt:")
        print(f.read())

    ydl_opts = {
        "format": "best",
        "cookiefile": "cookies.txt",  # Use stored cookies
        "outtmpl": output_filename,
        "verbose": True,  # Enable verbose logging for debugging
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_filename
    except Exception as e:
        print(f"An error occurred while downloading Instagram Reel: {e}")
        return None

def download_youtube_shorts(url: str):
    output_filename = "shorts.mp4"

    # Get YouTube cookies from MongoDB
    cookies = get_cookies_from_db("youtube")

    # Save cookies to a temporary file in Netscape format
    with open("youtube_cookies.txt", "w") as f:
        # Add the required header line
        f.write("# Netscape HTTP Cookie File\n")

        # Write each cookie in Netscape format
        for cookie in cookies:
            line = (
                f"{cookie['domain']}\t"
                f"{cookie['flag']}\t"
                f"{cookie['path']}\t"
                f"{cookie['secure']}\t"
                f"{cookie['expires']}\t"
                f"{cookie['name']}\t"
                f"{cookie['value']}\n"
            )
            f.write(line)

    # Verify the contents of the cookies file
    with open("youtube_cookies.txt", "r") as f:
        print("Contents of youtube_cookies.txt:")
        print(f.read())

    ydl_opts = {
        "format": "best",  # Download the best available quality
        "cookiefile": "youtube_cookies.txt",  # Use YouTube cookies
        "outtmpl": output_filename,  # Save the video with the specified filename
        "quiet": True,  # Suppress yt-dlp output
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_filename
    except Exception as e:
        print(f"An error occurred while downloading YouTube Shorts: {e}")
        return None

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
            video_path = download_youtube_shorts(data.url)

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
    return "Home"

# Scheduled task to refresh cookies (e.g., using Render's Cron Jobs)
def refresh_cookies():
    save_cookies_to_db("instagram")
    save_cookies_to_db("youtube")
    print("Cookies have been refreshed.")
    
refresh_cookies()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)