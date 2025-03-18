import os
import base64
import asyncio
import json
import websockets
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
from enum import Enum
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime

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

# Function to extract Instagram cookies using Browserless WebSocket API
async def extract_instagram_cookies():
    # Browserless WebSocket URL
    BROWSERLESS_WS_URL = "wss://chrome.browserless.io"
    BROWSERLESS_API_KEY = "Ry0VHriOagKXZn4022be466f58d5cd3c9fedf2f78b"

    if not BROWSERLESS_API_KEY:
        raise ValueError("Browserless API key is missing. Set the BROWSERLESS_API_KEY environment variable.")

    # Instagram URL
    instagram_url = "https://www.instagram.com"

    # Connect to Browserless WebSocket
    websocket_url = f"{BROWSERLESS_WS_URL}?token={BROWSERLESS_API_KEY}"
    async with websockets.connect(websocket_url) as websocket:
        # Open a new browser page
        await websocket.send(json.dumps({
            "id": 1,
            "method": "Target.createTarget",
            "params": {"url": "about:blank"},
        }))
        response = await websocket.recv()
        print("Response from Target.createTarget:", response)  # Debugging

        # Parse the response
        response_data = json.loads(response)
        if "error" in response_data:
            raise ValueError(f"Browserless error: {response_data['error']['message']}")
        if "result" not in response_data:
            raise ValueError(f"Unexpected response format: {response_data}")

        target_id = response_data["result"]["targetId"]

        # Attach to the target (page)
        await websocket.send(json.dumps({
            "id": 2,
            "method": "Target.attachToTarget",
            "params": {"targetId": target_id, "flatten": True},
        }))

        # Wait for the Target.attachedToTarget event
        session_id = None
        while True:
            response = await websocket.recv()
            print("Response from WebSocket:", response)  # Debugging

            # Parse the response
            response_data = json.loads(response)
            if "method" in response_data and response_data["method"] == "Target.attachedToTarget":
                session_id = response_data["params"]["sessionId"]
                break
            elif "error" in response_data:
                raise ValueError(f"Browserless error: {response_data['error']['message']}")

        if not session_id:
            raise ValueError("Failed to attach to target: sessionId not found.")

        # Navigate to the Instagram page
        await websocket.send(json.dumps({
            "id": 3,
            "method": "Page.navigate",
            "params": {"url": instagram_url},
            "sessionId": session_id,
        }))
        response = await websocket.recv()
        print("Response from Page.navigate:", response)  # Debugging

        # Wait for the page to load
        await websocket.send(json.dumps({
            "id": 4,
            "method": "Runtime.evaluate",
            "params": {
                "expression": """
                    new Promise((resolve) => {
                        const interval = setInterval(() => {
                            if (document.querySelector("svg[aria-label='Instagram']")) {
                                clearInterval(interval);
                                resolve();
                            }
                        }, 100);
                    });
                """,
                "awaitPromise": True,
            },
            "sessionId": session_id,
        }))
        response = await websocket.recv()
        print("Response from Runtime.evaluate:", response)  # Debugging

        # Extract cookies
        await websocket.send(json.dumps({
            "id": 5,
            "method": "Network.getCookies",
            "params": {},
            "sessionId": session_id,
        }))
        response = await websocket.recv()
        print("Response from Network.getCookies:", response)  # Debugging

        # Parse the response
        response_data = json.loads(response)
        if "error" in response_data:
            raise ValueError(f"Browserless error: {response_data['error']['message']}")
        if "result" not in response_data:
            raise ValueError(f"Unexpected response format: {response_data}")

        cookies = response_data["result"]["cookies"]

        # Close the browser
        await websocket.send(json.dumps({
            "id": 6,
            "method": "Target.closeTarget",
            "params": {"targetId": target_id},
        }))

    return cookies

# Function to save cookies to MongoDB
def save_cookies_to_db(platform: str, cookies: list):
    # Save cookies to MongoDB
    cookies_collection.update_one(
        {"platform": platform},
        {"$set": {"cookies": cookies, "timestamp": datetime.utcnow()}},
        upsert=True,
    )
    print(f"Cookies for {platform} have been saved to MongoDB.")

# Function to get cookies from MongoDB
def get_cookies_from_db(platform: str):
    cookies_data = cookies_collection.find_one({"platform": platform})
    if not cookies_data:
        raise HTTPException(status_code=400, detail=f"No cookies found for {platform}. Please refresh cookies.")
    return cookies_data["cookies"]

# Function to download Instagram reel
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
            # Set the flag to TRUE if the domain starts with a dot
            flag = "TRUE" if cookie["domain"].startswith(".") else "FALSE"
            line = (
                f"{cookie['domain']}\t"
                f"{flag}\t"
                f"{cookie['path']}\t"
                f"{str(cookie['secure']).upper()}\t"
                f"{int(cookie.get('expires', 0))}\t"
                f"{cookie['name']}\t"
                f"{cookie['value']}\n"
            )
            f.write(line)
    
    # Verify the contents of the cookies file
    with open("cookies.txt", "r") as f:
        print("Contents of cookies.txt:")
        print(f.read())

    # Use yt-dlp to download the reel
    ydl_opts = {
        "format": "best",
        "cookiefile": "cookies.txt",  # Use stored cookies
        "outtmpl": output_filename,
        "sleep_interval": 10,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_filename
    except Exception as e:
        print(f"An error occurred while downloading Instagram Reel: {e}")
        return None

# Function to download YouTube Shorts
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
async def get_reel(data: ReelRequest):
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
async def refresh_cookies():
    # Refresh Instagram cookies
    instagram_cookies = await extract_instagram_cookies()
    save_cookies_to_db("instagram", instagram_cookies)

    print("Instagram cookies have been refreshed.")

# Run the refresh_cookies function
if __name__ == "__main__":
    import uvicorn
    asyncio.run(refresh_cookies())  # Refresh cookies on startup
    uvicorn.run(app, host="127.0.0.1", port=8000)