import os
import json
import time 
import hashlib
import requests
import feedparser
from dotenv import load_dotenv
from logger import setup_logger
from typing import Dict, Set, List
from concurrent.futures import ThreadPoolExecutor

load_dotenv()
logger = setup_logger()

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
    logger.debug("Sending to Discord.")
    # send POST request to Discord webhook
    resp = requests.post(discord_webhook, json=payload, timeout=15)
    # raise exception on failure
    resp.raise_for_status()

def fetch_new_entries(feed_url: str, sent_ids: Set[str]) -> List[Dict]:
    logger.debug("Fetching feed: %s", feed_url)
    feed = feedparser.parse(feed_url)

    # feedparser sets bozo=True when it encounters parsing issues
    if getattr(feed, "bozo", False):
        logger.warning(
            "Feed parsing issue for %s: %s",
            feed_url,
            getattr(feed, "bozo_exception", None),
        )
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
    logger.debug(
        "Feed %s: %d inspected, %d new",
        feed_url,
        len(entries),
        len(new_entries),
    )
    # usually RSS is newest-first; reverse to post oldest→newest
    new_entries.reverse()
    return new_entries

def send_updates(discord_webhook: str, feed_url: str, state_file: str) -> None:
    logger.info(f"Checking discord webhook")
    if not discord_webhook:
        raise SystemExit(f"Discord webhook URL is not set in .env")
    logger.info(f"Checking feed URL")
    if not feed_url:
        raise SystemExit(f"Feed URL is not set in .env")
    
    sent_ids = load_sent(STATE_FILE=state_file)
    logger.debug("Loaded %d sent IDs from %s", len(sent_ids), state_file)
    new_entries = fetch_new_entries(feed_url, sent_ids)

    if not new_entries:
        logger.info("No new entries for feed %s", feed_url)
        return
    
    logger.info("Found %d new entires for feed %s", len(new_entries), feed_url)
    
    for e in new_entries:
        title = e.get("title", "No Title")
        link = e.get("link", "")
        published = e.get("published", "") or e.get("updated", "")
        
        logger.info("Sending: %s", title)

        try:
            post_to_discord(discord_webhook=discord_webhook, title=title, link=link, published=published)

            sent_ids.add(stable_id(e))
        except Exception as ex:
            logger.error("Failed to send to Discord: %s", ex)
    
        time.sleep(4500)  # Rate limiting

    save_sent(sent_ids=sent_ids, STATE_FILE=state_file)
    logger.info("Updated ids saved to %s", state_file)

def main():
    logger.info("Starting Medium Discord Alerts Bot")
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
            except KeyboardInterrupt:
                logger.warning("Interrupted by user.")
                STOP_EVENT.set()
                raise
            except Exception as e:
                logger.error("Error in job: %s", e)
    logger.info("ALL Done.")

if __name__ == "__main__":
    main()