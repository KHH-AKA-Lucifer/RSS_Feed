import os
import json
import time 
import hashlib
import requests
import feedparser
from dotenv import load_dotenv
from typing import Dict, Set, List
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

# Configuration
discord_fastapi_channel = os.getenv("DISCORD_FASTAPI_URL", "").strip()
feed_fastapi_url = os.getenv("FEED_FASTAPI_URL", "").strip()
discord_ml_channel = os.getenv("DISCORD_ML_URL", "").strip()
feed_ml_url = os.getenv("FEED_ML_URL", "").strip()
MAX_POSTS = int(os.getenv("MAX_POSTS", "5"))
FASTAPI_FILE = "fastapi_sent_ids.json"
ML_FILE = "ml_sent_ids.json"

def stable_id(entry: Dict) -> str:
    """
    Create a stable ID for a feed entry for dedupe.
    Prefer guid/id; fallback to ahsh(title+link).
    """
    # get the id from the entry if it exists
    guid = entry.get("id") or entry.get("guid")
    # if guid exists, return it as string
    if guid:
        return str(guid)
    # otherwise, create a hash from title and link
    title = entry.get("title", "")
    link = entry.get("link", "")
    raw = f"{title}|{link}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def load_sent(STATE_FILE: str) -> Set[str]:
    """
    Load the set of sent entry IDs from the state file.
    """
    # if the file does not exist, return an empty set.
    if not os.path.exists(STATE_FILE):
        return set()
    # try to read and parse the file
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("sent_ids", []))
    # on any error, return an empty set
    except Exception:
        return set()

def save_sent(sent_ids: Set[str], STATE_FILE: str) -> None:
    """
    Save the set of sent entry IDs to the state file.
    """
    data = {"sent_ids": sorted(list(sent_ids))}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def post_to_discord(discord_webhook: str, title: str, link: str, published: str = "") -> None:
    # create message content
    content_lines = [f"🆕 **{title}**", link]
    if published:
        content_lines.append(f"_Published on: {published}_")
    # prepare payload for Discord webhook
    payload = {"content": "\n".join(content_lines)}
    # send POST request to Discord webhook
    resp = requests.post(discord_webhook, json=payload, timeout=15)
    # raise exception on failure
    resp.raise_for_status()

def fetch_new_entries(feed_url: str, sent_ids: Set[str]) -> List[Dict]:
    feed = feedparser.parse(feed_url)

    # feedparser sets bozo=True when it encounters parsing issues
    if getattr(feed, "bozo", False) and getattr(feed, "bozo_exception", None):
        # still often usable; we just proceed.
        pass
    
    # get entries up to MAX_POSTS
    entries = feed.entries[:MAX_POSTS]
    # create list of new entries
    new_entries = []
    # filter out already sent entries
    for e in entries:
        eid = stable_id(e)
        if eid not in sent_ids:
            new_entries.append(e)
    # usually RSS is newest-first; reverse to post oldest→newest
    new_entries.reverse()
    return new_entries

def send_updates(discord_webhook: str, feed_url: str, state_file: str) -> None:
    if not discord_webhook:
        raise SystemExit(f"Discord webhook URL is not set in .env")
    if not feed_url:
        raise SystemExit(f"Feed URL is not set in .env")
    
    sent_ids = load_sent(STATE_FILE=state_file)
    new_entries = fetch_new_entries(feed_url, sent_ids)

    if not new_entries:
        print("No new entries to post.")
        return
    
    for e in new_entries:
        title = e.get("title", "No Title")
        link = e.get("link", "")
        published = e.get("published", "") or e.get("updated", "")
        
        print(f"Sending: {title}")
        post_to_discord(discord_webhook=discord_webhook, title=title, link=link, published=published)

        sent_ids.add(stable_id(e))
        time.sleep(4500)  # Rate limiting
    
    save_sent(sent_ids=sent_ids, STATE_FILE=state_file)
    print("Done.")

def main():
    jobs = [
        (discord_fastapi_channel, feed_fastapi_url, FASTAPI_FILE),
        (discord_ml_channel, feed_ml_url, ML_FILE),
    ]

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [
            pool.submit(send_updates, discord_webhook, feed_url, state_file)
            for discord_webhook, feed_url, state_file in jobs
        ]
        for future in futures:
            try:
                future.result()
            except Exception as e:
                print(f"Error occurred: {e}")

if __name__ == "__main__":
    main()