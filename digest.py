import os
import requests
import yaml
import time
import datetime
from dotenv import load_dotenv
from praw import Reddit
from prawcore.exceptions import PrawcoreException
from pathlib import Path

load_dotenv(override=True)

SCRIPT_DIR = Path.cwd()  # Replaces __file__ for Codespaces and notebooks

yaml_path = SCRIPT_DIR / "config.yml"
if not yaml_path.exists():
    raise FileNotFoundError("Missing config.yml file. Please create one with valid users.")

with open(yaml_path, "r") as f:
    config = yaml.safe_load(f)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_PROJECT_ID = os.getenv("OPENAI_PROJECT_ID", "").strip()
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "").strip()
REDDIT_SECRET = os.getenv("REDDIT_SECRET", "").strip()
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "").strip()

required_values = {
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "OPENAI_PROJECT_ID": OPENAI_PROJECT_ID,
    "REDDIT_CLIENT_ID": REDDIT_CLIENT_ID,
    "REDDIT_SECRET": REDDIT_SECRET,
    "REDDIT_USER_AGENT": REDDIT_USER_AGENT
}

missing_keys = [key for key, val in required_values.items() if not val]
if missing_keys:
    raise ValueError(f"Missing required API keys or secrets: {', '.join(missing_keys)}")

reddit = Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_SECRET,
    user_agent=REDDIT_USER_AGENT
)

saved_posts = []
for username in config.get("users", []):
    try:
        user = reddit.redditor(username)
        for post in user.saved(limit=config.get("max_posts", 20)):
            if hasattr(post, "title") and hasattr(post, "selftext"):
                saved_posts.append({
                    "title": post.title,
                    "selftext": post.selftext,
                    "url": f"https://www.reddit.com{post.permalink}"
                })
    except PrawcoreException:
        continue

# Exit early if no posts were found
if not saved_posts:
    print("⚠️ No saved posts found. Exiting.")
    exit()

date_str = datetime.date.today().isoformat()
thread_count = len(saved_posts)
print(f"📊 Found {thread_count} posts from {len(config.get('users', []))} users")

post_bodies = "\n\n".join([
    f"Title: {p['title']}\nBody: {p['selftext']}" for p in saved_posts
])

prompt = f"""Here are {thread_count} Reddit posts saved by a user on {date_str}. Please:

- Group related posts into clear categories
- Provide a brief but contextually clear summary of each group
- Write in clean Obsidian-style Markdown
- At the top, summarize how many posts were processed, what date, and how many categories were found
- Include a reference list of original post titles and links at the bottom

Posts:
{post_bodies}"""

gpt_messages = [
    {
        "role": "system",
        "content": "You are a research assistant. Group similar Reddit posts together, identify major themes, and summarize them in a way that preserves context and clarity."
    },
    {
        "role": "user",
        "content": prompt
    }
]

response = requests.post(
    "https://api.openai.com/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Project": OPENAI_PROJECT_ID,
        "Content-Type": "application/json"
    },
    json={
        "model": "gpt-4o",
        "messages": gpt_messages,
        "temperature": 0.5
    }
)

response.raise_for_status()
completion = response.json()["choices"][0]["message"]["content"]

output_dir = SCRIPT_DIR / "digests"
output_dir.mkdir(exist_ok=True)

output_file = output_dir / f"digest_{config['subreddit']}_{date_str}.md"
with open(output_file, "w", encoding="utf-8") as f:
    f.write(completion)

print(f"✅ Digest saved to {output_file}")
