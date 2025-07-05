import os
import requests
import yaml
from datetime import datetime
from pathlib import Path
import praw

# Load config
with open("config.yml", "r") as f:
    config = yaml.safe_load(f)

SUBREDDIT = config.get("subreddit", "AskReddit")
LIMIT = config.get("limit", 5)
DIGEST_DIR = Path("digests")
DIGEST_DIR.mkdir(exist_ok=True)

# Load secrets
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_PROJECT_ID = os.getenv("OPENAI_PROJECT_ID")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_SECRET = os.getenv("REDDIT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "reddit-digest-script")

if not all([OPENAI_API_KEY, OPENAI_PROJECT_ID, REDDIT_CLIENT_ID, REDDIT_SECRET]):
    raise ValueError("Missing required API keys or secrets.")

# Initialize Reddit
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_SECRET,
    user_agent=REDDIT_USER_AGENT,
)

# Fetch top posts
posts = reddit.subreddit(SUBREDDIT).hot(limit=LIMIT)
post_texts = []
for post in posts:
    if not post.stickied:
        post_texts.append(f"Title: {post.title}\n{post.selftext[:300]}")

content = "\n\n".join(post_texts)

# Query OpenAI
response = requests.post(
    "https://api.openai.com/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Project": OPENAI_PROJECT_ID,
        "Content-Type": "application/json"
    },
    json={
        "model": "gpt-4o",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant who summarizes Reddit posts into a digest."
            },
            {
                "role": "user",
                "content": content
            }
        ],
        "temperature": 0.7,
    },
)

if response.status_code != 200:
    print("❌ Summary failed:")
    print(response.status_code, response.text)
    exit(1)

summary = response.json()["choices"][0]["message"]["content"]

# Save digest
timestamp = datetime.now().strftime("%Y-%m-%d")
digest_path = DIGEST_DIR / f"digest_{SUBREDDIT}_{timestamp}.txt"
with open(digest_path, "w", encoding="utf-8") as f:
    f.write(summary)

print(f"✅ Digest saved to {digest_path}")
