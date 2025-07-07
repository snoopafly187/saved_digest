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

def call_openai_with_backoff(payload, max_retries=5):
    delay = 1
    for attempt in range(1, max_retries + 1):
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {env['OPENAI_API_KEY']}",
                "OpenAI-Project": env["OPENAI_PROJECT_ID"],
                "Content-Type": "application/json"
            },
            json=payload,
        )
        if resp.status_code == 429 and attempt < max_retries:
            print(f"⚠️ Rate-limited, retrying in {delay}s… (attempt {attempt})")
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    raise RuntimeError("❌ Failed after multiple retries")

# === BUILD & CALL IN CHUNKS ===
date_str = datetime.date.today().isoformat()
chunks = list(chunk_list(saved_posts, 50))
partial_summaries = []

for idx, chunk in enumerate(chunks, start=1):
    prompt_posts = "\n\n".join(
        f"Title: {p['title']}\nBody: {p['selftext']}" for p in chunk
    )
    prompt = f"""Here are {len(chunk)} saved Reddit posts (batch {idx}/{len(chunks)}) on {date_str}. Please:
- Group related posts into clear categories
- Summarize each group in Obsidian-style Markdown
- Label this section "Batch {idx}"
- Do NOT list post links here, we’ll append them at the end

Posts:
{prompt_posts}"""
    print(f"🛠️ Sending batch {idx}/{len(chunks)} to OpenAI (≈ {len(prompt)//4} tokens)…")
    summary = call_openai_with_backoff({
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are a research assistant."},
            {"role": "user",   "content": prompt}
        ],
        "temperature": 0.5,
    })
    partial_summaries.append(summary)

# === AGGREGATE FINAL DIGEST ===
header = f"# Reddit Digest ({len(saved_posts)} posts) — {date_str}\n\n"
body = "\n\n".join(partial_summaries)

# Append links at bottom
links = "\n".join(f"- [{p['title']}]({p['url']})" for p in saved_posts)

final_md = f"""{header}{body}

---

## All Post Links
{links}
"""

# === SAVE OUTPUT ===
out_dir = SCRIPT_DIR / "digests"
out_dir.mkdir(exist_ok=True)
out_file = out_dir / f"digest_{date_str}.md"
out_file.write_text(final_md, encoding="utf-8")
print(f"✅ Digest saved to {out_file}")
