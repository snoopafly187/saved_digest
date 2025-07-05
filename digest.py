import os
import openai
import praw
import datetime as dt
from pathlib import Path

client = openai.OpenAI(api_key="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")

# Reddit login
reddit = praw.Reddit(
    client_id=os.environ["REDDIT_CLIENT_ID"],
    client_secret=os.environ["REDDIT_CLIENT_SECRET"],
    username=os.environ["REDDIT_USERNAME"],
    password=os.environ["REDDIT_PASSWORD"],
    user_agent="saved-summary-digest-gpt4"
)

# Settings
MAX_POSTS = 25
MAX_INPUT_CHARS = 3000
TOPIC_KEYWORDS = {
    "AI": ["machine learning", "chatgpt", "openai", "hugging face", "llm"],
    "Design": ["product design", "ux", "ui", "industrial", "portfolio"],
    "Finance": ["money", "invest", "retirement", "stock", "crypto"],
    "Parenting": ["child", "toddler", "parent", "baby", "father", "mother"],
    "Career": ["job", "resume", "interview", "promotion", "quit"],
    "Health": ["fitness", "wellness", "mental", "exercise", "diet"],
    "Philosophy": ["meaning", "truth", "consciousness", "buddhism", "stoic"]
}

def detect_topic(text):
    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text.lower():
                return topic
    return "Misc"

def summarize_with_gpt(text):
    prompt = f"""
Summarize the following Reddit post in 2 clear bullet points, using natural language. Focus on extracting key takeaways or advice.

Reddit post:
\"\"\"{text.strip()}\"\"\"

Summary:
•"""
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.7,
            max_tokens=250
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Summary failed: {str(e)}"

# Get saved posts
saved = [
    i for i in reddit.user.me().saved(limit=MAX_POSTS)
    if hasattr(i, "title")
]

print(f"Found {len(saved)} saved posts")

today = dt.datetime.now().strftime("%Y-%m-%d")
out_dir = Path("digests")
out_dir.mkdir(exist_ok=True)
digest_path = out_dir / f"{today} Reddit Digest.md"

grouped = {}

for post in saved:
    text = (post.title or "") + "\n" + getattr(post, "selftext", "")
    print(f"Processing: {post.title}")

    if not text.strip():
        print("Skipped: empty text")
        continue

    summary = summarize_with_gpt(text[:MAX_INPUT_CHARS])
    topic = detect_topic(text)

    item = f"**[{post.title}]({post.url})**  \n{summary}"
    grouped.setdefault(topic, []).append(item)

# Write output
with digest_path.open("w", encoding="utf-8") as f:
    f.write(f"# Reddit Digest – {today}\n\n")
    for topic, items in grouped.items():
        f.write(f"## {topic}\n")
        for item in items:
            f.write(item + "\n\n")

print("Digest complete.")
