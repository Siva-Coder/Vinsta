import instaloader
import os

# Load environment variables
username = os.getenv("INSTAGRAM_USERNAME")
password = os.getenv("INSTAGRAM_PASSWORD")

if not username or not password:
    print("❌ Error: Missing Instagram credentials.")
    exit()

# Initialize Instaloader
loader = instaloader.Instaloader()

# Login and save a fresh session
try:
    loader.login(username, password)
    loader.save_session_to_file(f"session-{username}")
    print("✅ Instagram session refreshed successfully!")
except Exception as e:
    print(f"❌ Failed to refresh session: {e}")