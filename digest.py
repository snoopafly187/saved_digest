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

# === FETCH UP TO 200 SAVED POSTS + TOP COMMENT ===
saved_posts = []
for post in reddit.user.me().saved(limit=200):
    if not getattr(post, "title", None):
        continue
    try:
        post.comments.replace_more(limit=0)
        top = max(post.comments, key=lambda c: c.score) if post.comments else None
        top_text = top.body if top else "[no comments]"
        top_score = top.score if top else 0
    except Exception:
        top_text = "[error fetching comment]"
        top_score = 0

    saved_posts.append({
        "title": post.title,
        "selftext": post.selftext or "[no self-text]",
        "url": f"https://reddit.com{post.permalink}",
        "top_comment": top_text,
        "top_score": top_score
    })

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
    for attempt in range(1, max_retries+1):
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {env['OPENAI_API_KEY']}",
                "OpenAI-Project": env["OPENAI_PROJECT_ID"],
                "Content-Type": "application/json"
            },
            json=payload,
        )
        if resp.status_code in (429,) or 500 <= resp.status_code < 600:
            wait = backoff + random.uniform(0, backoff*0.1)
            print(f"⚠️ {resp.status_code}, retrying in {wait:.1f}s (attempt {attempt})")
            time.sleep(wait)
            backoff = min(backoff*2, 30)
            continue
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    raise RuntimeError(f"OpenAI failed after {max_retries} attempts")

# === BATCH & PROMPT WITH DEEP-DIVE BULLETS ===
date_str = datetime.date.today().isoformat()
batches = list(chunk_list(saved_posts, 10))
all_summaries = []

for idx, batch in enumerate(batches, start=1):
    post_block = ""
    for i, p in enumerate(batch, start=1):
        post_block += (
            f"### Post {i}\n"
            f"**Title:** {p['title']}\n"
            f"**Body:** {p['selftext']}\n"
            f"**Top Comment (score {p['top_score']}):** {p['top_comment']}\n\n"
        )

    prompt = f"""SYSTEM: You are a research assistant helping a prompt-engineering hobbyist, Obsidian power user, and podcast creator.

USER: We're processing **batch {idx}/{len(batches)}** of saved Reddit posts on **{date_str}**.

**TASKS:**
1. **Group** these posts into **3–5** categories.
   - 🔥 Mark any category about prompt engineering or AI/tools with a fire emoji.

2. For **each category**, produce:
   - A heading (`## Category Name`).
   - A **2–3 sentence overview**.
   - **5–7 bullet points**, each of which must:
     1. Begin with the post’s **title** as a Markdown link—`[Title](URL)`.
     2. Show the OP’s **initial prompt** exactly as they wrote it.
     3. Show the **top upvoted comment** text.
     4. Summarize the **key insight** or takeaway from that comment.
     5. End with a one-sentence **“so what?” takeaway** explaining why this matters.
     6. Add a **Next action:** one concrete step to try tomorrow.

3. At the very end, under **## For You**, suggest **2–3 project ideas** or next steps tailored to the user’s interests.

_Do not_ list every title here—we will auto‐append a full **References** section with all titles and links after the batches.

---

**Posts:**  
{post_block}
"""

    print(f"🛠️ Sending batch {idx}/{len(batches)} (~{len(prompt)//4} tokens)…")
    payload = {
        "model": "gpt-4",
        "messages": [
            {"role":"system", "content":"You are a research assistant helping a prompt-engineering hobbyist, Obsidian power user, and podcast creator."},
            {"role":"user",   "content":prompt}
        ],
        "temperature": 0.5
    }

    try:
        batch_summary = call_openai(payload)
    except Exception as e:
        print(f"❌ Batch {idx} failed: {e}")
        all_summaries.append(f"**Batch {idx} skipped due to API errors**\n")
        continue

    all_summaries.append(batch_summary)
    time.sleep(1)

# === ASSEMBLE FINAL MD ===
header = f"# Reddit Digest ({len(saved_posts)} posts) — {date_str}\n\n"
body = "\n\n---\n\n".join(all_summaries)
final_md = f"{header}{body}\n"

out_dir = SCRIPT_DIR / "digests"
out_dir.mkdir(exist_ok=True)
out_file = out_dir / f"digest_{date_str}.md"
out_file.write_text(final_md, encoding="utf-8")
print(f"✅ Digest saved to {out_file}")
