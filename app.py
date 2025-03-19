import base64
import os
import json
import asyncio
import websockets
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pymongo import MongoClient
from datetime import datetime
import yt_dlp
import random
from enum import Enum
from pydantic import BaseModel
from contextlib import asynccontextmanager
from proxies import PROXY_POOL

class ReelType(str, Enum):
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"

class ReelRequest(BaseModel):
    url: str
    type: ReelType

# MongoDB connection
client = MongoClient("mongodb+srv://siva:123456mongodb@vinsta.ljqdp.mongodb.net/?retryWrites=true&w=majority&appName=vinsta")
db = client["cookies_db"]
cookies_collection = db["cookies"]

# Browserless WebSocket URL and API key
BROWSERLESS_WS_URL = "wss://chrome.browserless.io"
BROWSERLESS_API_KEY = "Ry0VHriOagKXZn4022be466f58d5cd3c9fedf2f78b"  # Replace with your API key

async def extract_instagram_cookies():
    """Extract Instagram cookies using Browserless."""
    instagram_url = "https://www.instagram.com"

    async with websockets.connect(f"{BROWSERLESS_WS_URL}?token={BROWSERLESS_API_KEY}") as websocket:
        # Open a new browser page
        await websocket.send(json.dumps({
            "id": 1,
            "method": "Target.createTarget",
            "params": {"url": "about:blank"},
        }))
        response = await websocket.recv()
        response_data = json.loads(response)
        target_id = response_data["result"]["targetId"]

        # Attach to the target (page)
        await websocket.send(json.dumps({
            "id": 2,
            "method": "Target.attachToTarget",
            "params": {"targetId": target_id, "flatten": True},
        }))

        # Wait for the session ID
        session_id = None
        while True:
            response = await websocket.recv()
            response_data = json.loads(response)
            if response_data.get("method") == "Target.attachedToTarget":
                session_id = response_data["params"]["sessionId"]
                break

        # Navigate to Instagram
        await websocket.send(json.dumps({
            "id": 3,
            "method": "Page.navigate",
            "params": {"url": instagram_url},
            "sessionId": session_id,
        }))
        await websocket.recv()

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
        await websocket.recv()

        # Extract cookies
        await websocket.send(json.dumps({
            "id": 5,
            "method": "Network.getCookies",
            "params": {},
            "sessionId": session_id,
        }))
        response = await websocket.recv()
        response_data = json.loads(response)
        cookies = response_data["result"]["cookies"]

        # Close the browser
        await websocket.send(json.dumps({
            "id": 6,
            "method": "Target.closeTarget",
            "params": {"targetId": target_id},
        }))

    return cookies

def save_cookies_to_db(cookies: list):
    """Save cookies to MongoDB."""
    cookies_collection.update_one(
        {"platform": "instagram"},
        {"$set": {"cookies": cookies, "timestamp": datetime.utcnow()}},
        upsert=True,
    )

def get_cookies_from_db():
    """Retrieve cookies from MongoDB."""
    cookies_data = cookies_collection.find_one({"platform": "instagram"})
    if not cookies_data:
        return None
    return cookies_data["cookies"]

async def refresh_cookies(background_tasks: BackgroundTasks):
    """Refresh Instagram cookies and save them to MongoDB."""
    try:
        cookies = await extract_instagram_cookies()
        save_cookies_to_db(cookies)
        print("Cookies refreshed successfully.")
    except Exception as e:
        print(f"Failed to refresh cookies: {e}")
    finally:
        # Schedule the next refresh after 6 hours
        background_tasks.add_task(refresh_cookies, background_tasks)

def encode_video_to_base64(video_path: str):
    """Convert video file to Base64 encoded string."""
    with open(video_path, "rb") as video_file:
        encoded_string = base64.b64encode(video_file.read()).decode("utf-8")
    return encoded_string
  
def download_instagram_reel(url: str):
    output_filename = "reel.mp4"

    # Get cookies from MongoDB
    cookies = get_cookies_from_db()
    if not cookies:
        raise ValueError("No cookies found. Please refresh cookies.")

    # Save cookies to a temporary file
    with open("cookies.txt", "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for cookie in cookies:
            f.write(
                f"{cookie['domain']}\t"
                f"{'TRUE' if cookie['domain'].startswith('.') else 'FALSE'}\t"
                f"{cookie['path']}\t"
                f"{str(cookie['secure']).upper()}\t"
                f"{int(cookie.get('expires', 0))}\t"
                f"{cookie['name']}\t"
                f"{cookie['value']}\n"
            )

    # Use a random proxy from the pool
    proxy = random.choice(PROXY_POOL)
    print("Using proxy", proxy)
    # Download the reel using yt-dlp
    ydl_opts = {
        "format": "best",
        "cookiefile": "cookies.txt",
        "outtmpl": output_filename,
        "sleep_interval": 10,  # Add a delay to avoid rate limits
        # "proxy": proxy,  # Use a random proxy
        "verbose": True,  # Enable verbose logging
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_filename
    except Exception as e:
        raise ValueError(f"Failed to download Instagram Reel: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    # Refresh cookies on startup
    background_tasks = BackgroundTasks()
    await refresh_cookies(background_tasks)
    yield
    # Cleanup on shutdown (if needed)
    print("Shutting down...")

app = FastAPI(lifespan=lifespan)

@app.post("/download-reel/")
async def download_reel(data: ReelRequest, background_tasks: BackgroundTasks):
    try:
        # Refresh cookies if necessary
        if not get_cookies_from_db():
            await refresh_cookies(background_tasks)

        # Download the Instagram Reel
        video_path = download_instagram_reel(data.url)
        
        # Convert video to Base64
        base64_video = encode_video_to_base64(video_path)

        # Remove file after encoding to free space
        os.remove(video_path)
        return {"message": "Download successful", "video_path": base64_video}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)