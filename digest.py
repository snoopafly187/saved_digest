import os
import time
import random
import requests
import yaml
import datetime
from praw import Reddit
from prawcore.exceptions import PrawcoreException
from pathlib import Path

# === CONFIG & ENV SETUP ===
SCRIPT_DIR = Path.cwd()
cfg = SCRIPT_DIR / "config.yml"
if not cfg.exists():
    raise FileNotFoundError("Missing config.yml")
config = yaml.safe_load(cfg.read_text())

env = {
    "OPENAI_API_KEY":    os.getenv("OPENAI_API_KEY", "").strip(),
    "OPENAI_PROJECT_ID": os.getenv("OPENAI_PROJECT_ID", "").strip(),
    "REDDIT_CLIENT_ID":  os.getenv("REDDIT_CLIENT_ID", "").strip(),
    "REDDIT_SECRET":     os.getenv("REDDIT_SECRET", "").strip(),
    "REDDIT_USER_AGENT": os.getenv("REDDIT_USER_AGENT", "").strip(),
    "REDDIT_USERNAME":   os.getenv("REDDIT_USERNAME", "").strip(),
    "REDDIT_PASSWORD":   os.getenv("REDDIT_PASSWORD", "").strip(),
}
missing = [k for k, v in env.items() if not v]
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

# === FETCH UP TO 200 SAVED POSTS ===
saved_posts = []
try:
    for post in reddit.user.me().saved(limit=200):
        if getattr(post, "title", None):
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

print(f"✅ Retrieved {len(saved_posts)} saved posts (capped at 200)")

# === HELPERS ===
def chunk_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]

def call_openai(payload, max_retries=5):
    backoff = 1.0
    last_status = None
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
        last_status = resp.status_code
        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            wait = backoff + random.uniform(0, backoff * 0.1)
            print(f"⚠️ {resp.status_code}, retrying in {wait:.1f}s (attempt {attempt})")
            time.sleep(wait)
            backoff = min(backoff * 2, 30)
            continue
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    raise RuntimeError(f"❌ OpenAI failed after {max_retries} attempts (last {last_status})")

# === BATCH & SUMMARIZE WITH DETAILED EXTRACTION ===
date_str = datetime.date.today().isoformat()
batches = list(chunk_list(saved_posts, 10))
summaries = []

for idx, batch in enumerate(batches, start=1):
    post_block = "\n\n".join(f"Title: {p['title']}\nBody: {p['selftext']}" for p in batch)

    prompt = f"""Here are {len(batch)} saved Reddit posts (batch {idx}/{len(batches)}) on {date_str}. Please:

1. **Group** these posts into clear, descriptive categories.
2. For **each category**, write:
   - A **heading** (`## Category Name`)
   - A **brief overview** sentence.
   - **Top 3–5 specifics** mentioned in this category (e.g. actual book titles, tool names, nootropic substances, life hacks, etc.).
   - **Key insights** or pros/cons around each specific.
   - A one-sentence **“so what?” takeaway** explaining why these specifics matter.

_Do not_ list every title here—we’ll append the full title+link list at the end.

---

**Posts:**  
{post_block}
"""

    approx_tokens = len(prompt) // 4
    print(f"🛠️ Batch {idx}/{len(batches)} → ≈ {approx_tokens} tokens")

    payload = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are a research assistant."},
            {"role": "user",   "content": prompt}
        ],
        "temperature": 0.5,
    }

    try:
        result = call_openai(payload)
    except Exception as e:
        print(f"❌ Batch {idx} failed: {e}. Skipping.")
        summaries.append(f"**Batch {idx} skipped due to API errors**\n")
        time.sleep(2)
        continue

    summaries.append(result)
    time.sleep(1)

# === ASSEMBLE FINAL DIGEST ===
header = f"# Reddit Digest ({len(saved_posts)} posts) — {date_str}\n\n"
body   = "\n\n".join(summaries)
links  = "\n".join(f"- [{p['title']}]({p['url']})" for p in saved_posts)

final_md = f"""{header}{body}

---

## All Post Links
{links}
"""

out_dir = SCRIPT_DIR / "digests"
out_dir.mkdir(exist_ok=True)
out_file = out_dir / f"digest_{date_str}.md"
out_file.write_text(final_md, encoding="utf-8")
print(f"✅ Digest saved to {out_file}")
