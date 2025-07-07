import os
import requests
import yaml
import datetime
from praw import Reddit
from prawcore.exceptions import PrawcoreException
from pathlib import Path

# --- Config and env ---
SCRIPT_DIR = Path.cwd()
# you can now remove max_posts from config.yml if you like
cfg_file = SCRIPT_DIR / "config.yml"
if not cfg_file.exists():
    raise FileNotFoundError("Missing config.yml")
# we’re no longer using config.get("max_posts") here, but you can keep
# users/other settings in config.yml for future extensions
with open(cfg_file) as f:
    config = yaml.safe_load(f)

env_vars = {
    "OPENAI_API_KEY":    os.getenv("OPENAI_API_KEY", "").strip(),
    "OPENAI_PROJECT_ID": os.getenv("OPENAI_PROJECT_ID", "").strip(),
    "REDDIT_CLIENT_ID":  os.getenv("REDDIT_CLIENT_ID", "").strip(),
    "REDDIT_SECRET":     os.getenv("REDDIT_SECRET", "").strip(),
    "REDDIT_USER_AGENT": os.getenv("REDDIT_USER_AGENT", "").strip(),
    "REDDIT_USERNAME":   os.getenv("REDDIT_USERNAME", "").strip(),
    "REDDIT_PASSWORD":   os.getenv("REDDIT_PASSWORD", "").strip(),
}
missing = [k for k,v in env_vars.items() if not v]
if missing:
    raise ValueError("Missing env vars: " + ", ".join(missing))

# --- Reddit client (script auth) ---
reddit = Reddit(
    client_id=env_vars["REDDIT_CLIENT_ID"],
    client_secret=env_vars["REDDIT_SECRET"],
    user_agent=env_vars["REDDIT_USER_AGENT"],
    username=env_vars["REDDIT_USERNAME"],
    password=env_vars["REDDIT_PASSWORD"],
)

# --- Fetch *all* your saved posts ---
saved_posts = []
try:
    # limit=None tells PRAW to page until Reddit’s 1000-item cap
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

# --- Build prompt ---
date_str = datetime.date.today().isoformat()
thread_count = len(saved_posts)
post_bodies = "\n\n".join(
    f"Title: {p['title']}\nBody: {p['selftext']}"
    for p in saved_posts
)
prompt = f"""Here are {thread_count} Reddit posts you’ve saved on {date_str}. Please:
- Group related posts into clear categories
- Summarize in Obsidian-style Markdown
- At the top, state count, date, and category count
- List titles+links at the bottom

Posts:
{post_bodies}"""

print("🛠️ Prompt preview:", prompt[:300].replace("\n"," "))
print(f"📋 Approx tokens: {len(prompt)//4}")

# --- Call OpenAI ---
resp = requests.post(
    "https://api.openai.com/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {env_vars['OPENAI_API_KEY']}",
        "OpenAI-Project": env_vars["OPENAI_PROJECT_ID"],
        "Content-Type": "application/json"
    },
    json={
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are a research assistant."},
            {"role": "user",   "content": prompt}
        ],
        "temperature": 0.5
    }
)
resp.raise_for_status()
completion = resp.json()["choices"][0]["message"]["content"]

# --- Save output ---
out_dir = SCRIPT_DIR / "digests"
out_dir.mkdir(exist_ok=True)
out_file = out_dir / f"digest_{date_str}.md"
with open(out_file, "w", encoding="utf-8") as f:
    f.write(completion)

print(f"✅ Digest saved to {out_file}")
