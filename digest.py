import os
import time
import requests
import yaml
import datetime
from praw import Reddit
from prawcore.exceptions import PrawcoreException
from pathlib import Path

# === CONFIG & ENV SETUP ===
SCRIPT_DIR = Path.cwd()
cfg_file = SCRIPT_DIR / "config.yml"
if not cfg_file.exists():
    raise FileNotFoundError("Missing config.yml")

config = yaml.safe_load(cfg_file.read_text())

env = {
    "OPENAI_API_KEY":    os.getenv("OPENAI_API_KEY", "").strip(),
    "OPENAI_PROJECT_ID": os.getenv("OPENAI_PROJECT_ID", "").strip(),
    "REDDIT_CLIENT_ID":  os.getenv("REDDIT_CLIENT_ID", "").strip(),
    "REDDIT_SECRET":     os.getenv("REDDIT_SECRET", "").strip(),
    "REDDIT_USER_AGENT": os.getenv("REDDIT_USER_AGENT", "").strip(),
    "REDDIT_USERNAME":   os.getenv("REDDIT_USERNAME", "").strip(),
    "REDDIT_PASSWORD":   os.getenv("REDDIT_PASSWORD", "").strip(),
}
missing = [k for k,v in env.items() if not v]
if missing:
    raise ValueError("Missing env vars: " + ", ".join(missing))

# === REDDIT CLIENT (SCRIPT AUTH) ===
reddit = Reddit(
    client_id=env["REDDIT_CLIENT_ID"],
    client_secret=env["REDDIT_SECRET"],
    user_agent=env["REDDIT_USER_AGENT"],
    username=env["REDDIT_USERNAME"],
    password=env["REDDIT_PASSWORD"],
)

# === FETCH ALL SAVED POSTS ===
saved_posts = []
try:
    for post in reddit.user.me().saved(limit=None):
        if not getattr(post, "title", None):
            continue
        saved_posts.append({
            "title": post.title,
            "selftext": post.selftext or "[no self-text]",
            "url": f"https://reddit.com{post.permalink}"
        })
except PrawcoreException as e:
    print(f"⚠️ Error fetching saved posts: {e}")

if not saved_posts:
    print("⚠️ No saved posts found. Exiting.")
    exit()

print(f"✅ Retrieved {len(saved_posts)} saved posts")

# === HELPERS ===
def chunk_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]

def call_openai_
