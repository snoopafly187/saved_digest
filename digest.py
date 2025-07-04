import os
import requests
import praw
import datetime as dt
from pathlib import Path
from hashlib import sha1

# Hugging Face model (more reliable summarizer)
HF_API = "https://api-inference.huggingface.co/models/sshleifer/distilbart-cnn-12-6"
HF_HEADERS = {"Authorization": f"Bearer {os.environ['HF_TOKEN']}"}

# Reddit login
reddit = praw.Reddit(
    client_id=os.environ["REDDIT_CLIENT_ID"],
    client_secret=os.environ["REDDIT_CLIENT_SECRET"],
    username=os.environ["REDDIT_USERNAME"],
    password=os.environ["REDDIT_PASSWORD"],
    user_agent="saved-summary-digest"
)

# Settings
MAX_POSTS = 25
MAX_INPUT_CHARS = 1000
TOPIC_KEYWORDS = {
    "AI": ["machine learning", "chatgpt", "openai", "hugging face", "llm"],
    "Design": ["product design", "ux", "ui", "industrial", "portfolio"],
    "Finance": ["money", "invest", "retirement", "stock", "crypto"],
    "Parenting": ["child", "toddler", "parent", "baby", "father", "mother"],
    "Career": ["job", "resume", "interview", "promotion", "quit"],
    "Health": ["fitness", "wellness", "mental", "exercise", "diet"],
    "Philosophy": ["meaning", "truth", "consciousness", "buddhism", "stoic"]
}

def summarize(text):
    response = requests.post(HF_API, headers=HF_HEADERS, json={"inputs": text})
    if response.status_code == 200:
        return response.json()[0]["summary_text"]
    return "❌ Summary failed."

def detect_topic(text):
    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text.lower():
                return topic
    return "Misc"

# Pull recent saved posts (limit to MAX_POSTS)
since = dt.datetime.utcnow() - dt.timedelta(days=365)
saved = [
    i for i in reddit.user.me().saved(limit=MAX_POSTS)
    if hasattr(i, "title") and dt.datetime.utcfromtimestamp(i.created_utc) > since
]

today = dt.datetime.now().strftime("%Y-%m-%d")
out_dir = Path("digests")
out_dir.mkdir(exist_ok=True)
digest_path = out_dir / f"{today} Reddit Digest.md"

# Prepare post groups
grouped = {}

for post in saved:
    text = (post.title or "") + "\n" + getattr(post, "selftext", "")
    summary = summarize(text[:MAX_INPUT_CHARS])
    topic = detect_topic(text)

    item = f"**[{post.title}]({post.url})**  \n• {summary.strip()}"
    if topic not in grouped:
        grouped[topic] = []
    grouped[topic].append(item)

# Write digest
with digest_path.open("w", encoding="utf-8") as f:
    f.write(f"# Reddit Digest – {today}\n\n")
    for topic, items in grouped.items():
        f.write(f"## {topic}\n")
        for item in items:
            f.write(item + "\n\n")
