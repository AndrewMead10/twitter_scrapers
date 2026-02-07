# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "requests>=2.31.0",
#     "python-dotenv>=0.19.0",
# ]
# ///

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "output_data" / "twitter_bookmarks.db"
TRACKING_FILE = SCRIPT_DIR / "output_data" / ".uploaded_ids.json"
API_BASE = "https://retriever.sh"


def load_uploaded_ids():
    if TRACKING_FILE.exists():
        return set(json.loads(TRACKING_FILE.read_text()))
    return set()


def save_uploaded_ids(ids):
    TRACKING_FILE.write_text(json.dumps(sorted(ids), indent=2))


def fetch_bookmarks(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.tweet_id, t.text, t.timestamp, t.url,
               t.likes_count, t.retweets_count, t.replies_count,
               t.has_media, t.media_type, t.is_reply,
               u.username, u.display_name
        FROM bookmarks b
        JOIN tweets t ON b.tweet_id = t.tweet_id
        JOIN users u ON t.user_id = u.user_id
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def build_document(bookmark):
    text = bookmark["text"] or ""
    title_text = text[:80].replace("\n", " ")
    title = f"@{bookmark['username']} — {title_text}"

    metadata = {
        "tweet_id": bookmark["tweet_id"],
        "username": bookmark["username"],
        "display_name": bookmark["display_name"],
        "url": bookmark["url"],
        "timestamp": bookmark["timestamp"],
        "likes_count": bookmark["likes_count"],
        "retweets_count": bookmark["retweets_count"],
        "replies_count": bookmark["replies_count"],
        "has_media": bool(bookmark["has_media"]),
        "media_type": bookmark["media_type"],
        "is_reply": bool(bookmark["is_reply"]),
    }

    return {"title": title, "text": text, "metadata": metadata}


def upload_document(doc, project_id, project_key):
    url = f"{API_BASE}/api/rag/projects/{project_id}/documents"
    headers = {"X-Project-Key": project_key, "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=doc, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Upload bookmarks to retriever.sh")
    parser.add_argument("--full", action="store_true", help="Upload all bookmarks (rebuild tracking)")
    args = parser.parse_args()

    load_dotenv(SCRIPT_DIR / ".env")
    project_id = os.getenv("RETRIEVER_PROJECT_ID")
    project_key = os.getenv("RETRIEVER_API_KEY")

    if not project_id or not project_key:
        print("Error: RETRIEVER_PROJECT_ID and RETRIEVER_API_KEY must be set in .env")
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        sys.exit(1)

    bookmarks = fetch_bookmarks(DB_PATH)
    print(f"Found {len(bookmarks)} bookmarks in database")

    if args.full:
        uploaded_ids = set()
        to_upload = bookmarks
    else:
        uploaded_ids = load_uploaded_ids()
        to_upload = [b for b in bookmarks if b["tweet_id"] not in uploaded_ids]

    if not to_upload:
        print("No new bookmarks to upload")
        return

    print(f"Uploading {len(to_upload)} bookmarks...")
    success = 0
    errors = 0

    for i, bookmark in enumerate(to_upload, 1):
        doc = build_document(bookmark)
        try:
            upload_document(doc, project_id, project_key)
            uploaded_ids.add(bookmark["tweet_id"])
            success += 1
            if i % 50 == 0:
                print(f"  Progress: {i}/{len(to_upload)}")
                save_uploaded_ids(uploaded_ids)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print(f"  Rate limited at {i}/{len(to_upload)}, waiting 5s...")
                time.sleep(5)
                try:
                    upload_document(doc, project_id, project_key)
                    uploaded_ids.add(bookmark["tweet_id"])
                    success += 1
                except Exception as retry_err:
                    print(f"  Retry failed for {bookmark['tweet_id']}: {retry_err}")
                    errors += 1
            else:
                print(f"  Error uploading {bookmark['tweet_id']}: {e}")
                errors += 1
        except Exception as e:
            print(f"  Error uploading {bookmark['tweet_id']}: {e}")
            errors += 1

        time.sleep(0.1)

    save_uploaded_ids(uploaded_ids)
    print(f"\nDone: {success} uploaded, {errors} errors, {len(uploaded_ids)} total tracked")


if __name__ == "__main__":
    main()
