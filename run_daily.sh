#!/bin/bash
set -euo pipefail

cd /run/media/andrew/spinny_boi/coding/twitter_scrapers
source .env
export DISPLAY=:0

uv run 04_twitter_bookmarks_advanced.py
uv run upload_to_retriever.py
