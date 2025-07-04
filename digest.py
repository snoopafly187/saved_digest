import os
import requests
import praw
import datetime as dt
from pathlib import Path
from hashlib import sha1

# Hugging Face model
HF_API = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
HF_HEADERS = {"Authorization": f"Bearer {os.environ['HF_TOKEN']}"}

# Reddit login
reddit = praw.Reddit(
    client_id=os.environ["REDDIT_CLIENT_ID"],
    client_secret=os.environ["REDDIT_CLIENT_SECRET"],
    username=os.environ["REDDIT_USERNAME"],
    password=os.environ["REDDIT_PASSWORD"],
    user_agent="saved-summary-digest"
)

# Get all saved posts in last 365 days
since = dt.datetime.utcnow() - dt.timedelta(days=365)
saved = [
    i for i in reddit.user.me().saved(limit=None)
    if hasattr(i, "title") and dt.datetime.utcfromtimestamp(i.created_utc) > since
]

# Helper to summarize
def summarize(text):
    response = requests.post(HF_API, headers=HF_HEADERS, json={"inputs": text})
    if response.status_code == 200:
        return response.json()[0]["summary_text"]
    return "Summary failed."

# Create output folder
out_dir = Path("digests")
out_dir.mkdir(exist_ok=True)

# Group by date
today = dt.datetime.now().strftime("%Y-%m-%d")
digest_path = out_dir / f"{today} Reddit Digest.md"

existing = {}
if digest_path.exists():
    for line in digest_path.read_text().splitlines():
        if line.startswith("## "):
            key = line[3:].strip()
            existing[key] = []

# Write digest
with digest_path.open("w", encoding="utf-8") as f:
    f.write(f"# Reddit Digest – {today}\n\n")
    for post in saved:
        key = post.subreddit.display_name
        body = (post.title or "") + "\n" + getattr(post, "selftext", "")
        content_id = sha1((post.title + body).encode()).hexdigest()

        if key not in existing:
            existing[key] = []

        # skip if already seen
        if content_id in existing[key]:
            continue

        summary = summarize(body[:1000])
        existing[key].append(content_id)

        f.write(f"## {key}\n")
        f.write(f"**[{post.title}]({post.url})**  \n")
        f.write(f"{summary}\n\n")
