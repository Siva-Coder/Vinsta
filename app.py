import base64
import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
from playwright.sync_api import sync_playwright
import time

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

# Function to refresh Instagram cookies using Playwright
def refresh_instagram_cookies():
    with sync_playwright() as p:
        # Launch a headless browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Navigate to Instagram login page
        page.goto("https://www.instagram.com/accounts/login/")
        page.wait_for_selector("input[name='username']")

        # Fill in login credentials (use environment variables for security)
        page.fill("input[name='username']", os.getenv("INSTAGRAM_USERNAME"))
        page.fill("input[name='password']", os.getenv("INSTAGRAM_PASSWORD"))

        # Click the login button
        page.click("button[type='submit']")
        page.wait_for_selector("svg[aria-label='Instagram']")  # Wait for the home page to load

        # Extract cookies
        cookies = context.cookies()
        with open("cookies.txt", "w") as f:
            for cookie in cookies:
                f.write(
                    f"{cookie['domain']}\t"
                    f"{'TRUE' if cookie['domain'].startswith('.') else 'FALSE'}\t"
                    f"{cookie['path']}\t"
                    f"{'TRUE' if cookie['secure'] else 'FALSE'}\t"
                    f"{cookie['expires']}\t"
                    f"{cookie['name']}\t"
                    f"{cookie['value']}\n"
                )

        # Close the browser
        browser.close()

# Function to check if cookies are expired
def are_cookies_expired():
    if not os.path.exists("cookies.txt"):
        return True  # Cookies file doesn't exist

    with open("cookies.txt", "r") as f:
        lines = f.readlines()
        for line in lines:
            if "sessionid" in line:
                expires = int(line.split("\t")[4])  # Get the expiration timestamp
                if expires < time.time():  # Compare with current time
                    return True  # Cookies are expired
    return False

# Function to download Instagram reel
def download_reel(url: str):
    output_filename = "reel.mp4"

    # Check if cookies are expired or missing
    if are_cookies_expired():
        print("Cookies are expired")
        refresh_instagram_cookies()

    ydl_opts = {
        "format": "best",
        "cookiefile": "cookies.txt",  # Use stored cookies
        "outtmpl": output_filename,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if os.path.exists(output_filename):
        return output_filename
    return None

# Function to encode video to Base64
def encode_video_to_base64(video_path: str):
    """Convert video file to Base64 encoded string."""
    with open(video_path, "rb") as video_file:
        encoded_string = base64.b64encode(video_file.read()).decode("utf-8")
    return encoded_string

# API endpoint to download Instagram reel
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

# Home page
@app.get("/")
def get_home_page():
    return "Home"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)