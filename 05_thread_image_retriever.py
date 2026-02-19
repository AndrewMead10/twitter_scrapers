# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "requests>=2.31.0",
#     "beautifulsoup4>=4.12.0",
# ]
# ///

"""
Thread & Image Retriever for Twitter Bookmarks

Reads bookmarked tweets from the existing database (04_twitter_bookmarks_advanced.py),
fetches full threads by walking up reply chains via the fxtwitter API,
and downloads all images from each thread.
"""

import json
import sqlite3
import time
import random
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


FXTWITTER_API = "https://api.fxtwitter.com"
SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "output_data" / "twitter_bookmarks.db"
THREADS_DIR = SCRIPT_DIR / "output_data" / "threads"
REQUEST_DELAY = (0.8, 2.0)  # seconds between API requests


def log_info(msg: str):
    print(f"[INFO] {msg}")


def log_ok(msg: str):
    print(f"  ok  {msg}")


def log_warn(msg: str):
    print(f"[WARN] {msg}")


def log_err(msg: str):
    print(f"[ERR]  {msg}")


# ── database helpers ────────────────────────────────────────────────────────


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection):
    """Add columns and tables for thread tracking and image downloads."""
    cur = conn.cursor()

    # Add thread columns to tweets table (idempotent)
    for col in ("conversation_id TEXT", "parent_tweet_id TEXT"):
        try:
            cur.execute(f"ALTER TABLE tweets ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass  # column already exists

    # Drop the old separate thread table
    cur.execute("DROP TABLE IF EXISTS thread_tweets")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS images (
            tweet_id      TEXT NOT NULL,
            url           TEXT NOT NULL,
            local_path    TEXT,
            downloaded_at TIMESTAMP,
            PRIMARY KEY (tweet_id, url)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS retrieval_log (
            tweet_id     TEXT PRIMARY KEY,
            retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()


def get_unprocessed_bookmarks(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Return bookmarked tweets that haven't been thread-retrieved yet."""
    cur = conn.cursor()
    cur.execute("""
        SELECT t.tweet_id, t.user_id, t.url, t.text, t.is_reply
        FROM bookmarks b
        JOIN tweets t USING(tweet_id)
        WHERE t.tweet_id NOT IN (SELECT tweet_id FROM retrieval_log)
        ORDER BY t.timestamp
    """)
    return [dict(row) for row in cur.fetchall()]


def save_tweet_from_api(conn: sqlite3.Connection, api_tweet: Dict, conversation_id: str):
    """Upsert a tweet fetched from the API into the tweets table with thread info."""
    cur = conn.cursor()

    author = api_tweet.get("author", {})
    username = author.get("screen_name", "")
    display_name = author.get("name", "")

    # upsert user
    cur.execute(
        "INSERT OR REPLACE INTO users (user_id, username, display_name) VALUES (?, ?, ?)",
        (username, f"@{username}", display_name),
    )

    media_all = (api_tweet.get("media") or {}).get("all", [])
    has_media = len(media_all) > 0
    media_type = media_all[0]["type"] if media_all else "none"

    parent_tweet_id = api_tweet.get("replying_to_status")

    cur.execute(
        """INSERT OR REPLACE INTO tweets
           (tweet_id, user_id, text, timestamp, url,
            replies_count, retweets_count, likes_count,
            has_media, media_type, is_reply,
            conversation_id, parent_tweet_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            api_tweet["id"],
            username,
            api_tweet.get("text", ""),
            api_tweet.get("created_at"),
            api_tweet.get("url"),
            api_tweet.get("replies", 0),
            api_tweet.get("retweets", 0),
            api_tweet.get("likes", 0),
            has_media,
            media_type,
            api_tweet.get("replying_to") is not None,
            conversation_id,
            parent_tweet_id,
        ),
    )

    conn.commit()


def mark_retrieved(conn: sqlite3.Connection, tweet_id: str):
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO retrieval_log (tweet_id) VALUES (?)", (tweet_id,))
    conn.commit()


def save_image_record(conn: sqlite3.Connection, tweet_id: str, url: str, local_path: str):
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO images (tweet_id, url, local_path, downloaded_at) VALUES (?, ?, ?, ?)",
        (tweet_id, url, local_path, datetime.now().isoformat()),
    )
    conn.commit()


# ── fxtwitter API ───────────────────────────────────────────────────────────


def fetch_tweet(username: str, tweet_id: str) -> Optional[Dict]:
    """Fetch a single tweet from the fxtwitter API."""
    url = f"{FXTWITTER_API}/{username}/status/{tweet_id}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 200:
                return data["tweet"]
        log_warn(f"API returned {resp.status_code} for {tweet_id}")
    except Exception as e:
        log_warn(f"API error for {tweet_id}: {e}")
    return None


def walk_thread_up(username: str, tweet_id: str) -> List[Dict]:
    """Walk up the reply chain from a tweet to the thread root.

    Returns tweets ordered root-first (oldest → newest).
    """
    chain: List[Dict] = []
    visited = set()
    current_username = username
    current_id = tweet_id

    while current_id and current_id not in visited:
        visited.add(current_id)
        tweet = fetch_tweet(current_username, current_id)
        if not tweet:
            break

        chain.append(tweet)
        parent_id = tweet.get("replying_to_status")
        parent_user = tweet.get("replying_to")

        if not parent_id:
            break

        current_id = parent_id
        current_username = parent_user or current_username
        time.sleep(random.uniform(*REQUEST_DELAY))

    chain.reverse()  # root first
    return chain


# ── image downloading ──────────────────────────────────────────────────────


def get_image_urls(api_tweet: Dict) -> List[str]:
    """Extract all photo URLs from a tweet's media."""
    media = api_tweet.get("media") or {}
    photos = media.get("photos", [])
    return [p["url"] for p in photos if p.get("url")]


def download_image(url: str, dest: Path) -> bool:
    """Download an image file. Returns True on success."""
    try:
        resp = requests.get(url, stream=True, timeout=30)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        log_warn(f"Image download failed {url}: {e}")
        return False


def image_filename_from_url(url: str) -> str:
    """Derive a local filename from a pbs.twimg.com URL."""
    path = urlparse(url).path  # e.g. /media/XXXXX.jpg
    name = Path(path).name      # XXXXX.jpg or XXXXX
    # strip query params that got baked in
    name = name.split("?")[0]
    if "." not in name:
        name += ".jpg"
    return name


# ── main logic ──────────────────────────────────────────────────────────────


def process_bookmark(conn: sqlite3.Connection, bookmark: Dict[str, Any]) -> int:
    """Fetch the thread for one bookmark and download images.

    Returns the number of images downloaded.
    """
    tweet_id = bookmark["tweet_id"]
    username = bookmark["user_id"]

    log_info(f"Fetching thread for {username}/{tweet_id}")
    chain = walk_thread_up(username, tweet_id)

    if not chain:
        log_warn(f"Could not fetch tweet {tweet_id}")
        mark_retrieved(conn, tweet_id)
        return 0

    conversation_id = chain[0]["id"]
    thread_dir = THREADS_DIR / f"{conversation_id}"
    thread_dir.mkdir(parents=True, exist_ok=True)

    images_downloaded = 0

    for tweet in chain:
        save_tweet_from_api(conn, tweet, conversation_id)

        for img_url in get_image_urls(tweet):
            fname = image_filename_from_url(img_url)
            dest = thread_dir / f"{tweet['id']}_{fname}"

            if dest.exists():
                continue

            if download_image(img_url, dest):
                save_image_record(conn, tweet["id"], img_url, str(dest.relative_to(SCRIPT_DIR)))
                images_downloaded += 1
                log_ok(f"  {dest.name}")

    # save thread manifest
    manifest = {
        "conversation_id": conversation_id,
        "tweet_count": len(chain),
        "tweets": [
            {
                "id": t["id"],
                "author": t.get("author", {}).get("screen_name"),
                "text": t.get("text", ""),
                "created_at": t.get("created_at"),
                "url": t.get("url"),
                "images": get_image_urls(t),
            }
            for t in chain
        ],
    }
    with open(thread_dir / "thread.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    mark_retrieved(conn, tweet_id)
    return images_downloaded


def export_thread_index(conn: sqlite3.Connection):
    """Export a thread_index.json grouping all threaded tweets by conversation_id."""
    cur = conn.cursor()
    cur.execute("""
        SELECT tweet_id, user_id, text, timestamp, url,
               replies_count, retweets_count, likes_count,
               has_media, media_type, is_reply,
               conversation_id, parent_tweet_id
        FROM tweets
        WHERE conversation_id IS NOT NULL
        ORDER BY conversation_id, timestamp
    """)

    threads: Dict[str, List[Dict]] = {}
    for row in cur.fetchall():
        row_dict = dict(row)
        conv_id = row_dict.pop("conversation_id")
        threads.setdefault(conv_id, []).append(row_dict)

    out_path = SCRIPT_DIR / "output_data" / "thread_index.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(threads, f, indent=2, ensure_ascii=False)

    log_info(f"Exported {len(threads)} threads to {out_path}")


def main():
    if not DB_PATH.exists():
        log_err(f"Database not found: {DB_PATH}")
        log_err("Run 04_twitter_bookmarks_advanced.py first to create it.")
        sys.exit(1)

    conn = open_db(DB_PATH)
    ensure_schema(conn)

    bookmarks = get_unprocessed_bookmarks(conn)
    total = len(bookmarks)

    if total == 0:
        log_info("All bookmarks already processed.")
        export_thread_index(conn)
        conn.close()
        return

    log_info(f"{total} bookmarks to process")
    THREADS_DIR.mkdir(parents=True, exist_ok=True)

    total_images = 0
    for i, bm in enumerate(bookmarks, 1):
        print(f"\n── [{i}/{total}] ──────────────────────────────────────")
        try:
            imgs = process_bookmark(conn, bm)
            total_images += imgs
        except KeyboardInterrupt:
            log_warn("Interrupted – progress saved.")
            break
        except Exception as e:
            log_err(f"Failed on {bm['tweet_id']}: {e}")
            mark_retrieved(conn, bm["tweet_id"])

        time.sleep(random.uniform(*REQUEST_DELAY))

    export_thread_index(conn)
    conn.close()

    print("\n" + "=" * 60)
    print(f"Done. Processed {i}/{total} bookmarks, downloaded {total_images} images.")
    print(f"Threads saved to: {THREADS_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
