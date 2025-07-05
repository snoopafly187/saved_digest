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

# Fetch posts and top comments
post_texts = []

for post in reddit.subreddit(SUBREDDIT).hot(limit=LIMIT):
    if post.stickied:
        continue

    post.comments.replace_more(limit=0)
    top_comments = [
        comment.body.strip()
        for comment in post.comments[:3]
        if hasattr(comment, "body") and comment.body.strip()
    ]

    comments_joined = "\n".join(f"- {comment}" for comment in top_comments)
    thread_text = f"### {post.title}\n{comments_joined}\n"
    post_texts.append(thread_text)

content_for_gpt = "\n\n".join(post_texts)

# Build GPT prompt
messages = [
    {
        "role": "system",
        "content": (
            "You are a research assistant. You are given a list of Reddit threads with their titles and top comments. "
            "Your task is to extract insights, identify major themes, and summarize them in concise, categorized Markdown format. "
            "Structure the output for Obsidian. Use clear section headers (##) for each theme. "
            "Group similar threads together under one section when possible. Avoid speculation — only summarize what's there."
        ),
    },
    {
        "role": "user",
        "content": content_for_gpt,
    },
]

# Call OpenAI
response = requests.post(
    "https://api.openai.com/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Project": OPENAI_PROJECT_ID,
