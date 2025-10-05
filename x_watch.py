#!/usr/bin/env python3
"""
Monitor new posts from a given X (Twitter) handle using X API v2.
- Uses Bearer Token (App-only) auth.
- Stores the latest seen tweet ID in state.json to fetch only new posts next run.
- Prints a concise summary with timestamps in UTC and WIB.
"""
import os
import json
import time
from datetime import datetime, timezone, timedelta
import requests
from pathlib import Path

STATE_FILE = Path("state.json")
HANDLE = os.getenv("HANDLE", "Thekokocrypto")  # default per your request
BEARER = os.getenv("X_BEARER_TOKEN")
BASE = "https://api.x.com/2"  # x.com alias for api.twitter.com endpoints

def wib_time(iso_str: str) -> str:
    """Convert ISO8601 UTC time to Asia/Jakarta (WIB, UTC+7) string."""
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    wib = dt + timedelta(hours=7)
    return wib.strftime("%Y-%m-%d %H:%M:%S WIB")

def headers():
    if not BEARER:
        raise RuntimeError("Missing X_BEARER_TOKEN in environment.")
    return {"Authorization": f"Bearer {BEARER}"}

def get_user_id(username: str) -> str:
    url = f"{BASE}/users/by/username/{username}"
    params = {"user.fields": "name,username"}
    r = requests.get(url, headers=headers(), params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["data"]["id"]

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}

def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))

def fetch_new_tweets(user_id: str, since_id: str | None):
    url = f"{BASE}/users/{user_id}/tweets"
    # Exclude replies/retweets to keep the signal clean; adjust if you want everything
    params = {
        "max_results": 25,
        "exclude": "retweets,replies",
        "tweet.fields": "created_at,public_metrics,lang",
    }
    if since_id:
        params["since_id"] = since_id

    r = requests.get(url, headers=headers(), params=params, timeout=30)
    if r.status_code == 403:
        raise RuntimeError("403 Forbidden. Your API tier might not allow this endpoint or parameters.")
    r.raise_for_status()
    data = r.json()
    tweets = data.get("data", [])
    # API returns newest first; we'll sort oldest->newest for a nice chronologic summary
    tweets.sort(key=lambda t: t["id"])
    return tweets

def summarize(t):
    created_utc = t["created_at"]
    text = t.get("text", "").strip().replace("\n", " ")
    # Make a compact preview
    preview = (text[:120] + "…") if len(text) > 120 else text
    url = f"https://x.com/{HANDLE}/status/{t['id']}"
    return f"- {wib_time(created_utc)} | {preview}\n  {url}"

def main():
    state = load_state()
    handle_key = HANDLE.lower()
    last_id = state.get(handle_key, {}).get("since_id")

    try:
        user_id = get_user_id(HANDLE)
    except Exception as e:
        print(f"[ERROR] Failed to resolve user id for @{HANDLE}: {e}")
        return 1

    try:
        new_tweets = fetch_new_tweets(user_id, last_id)
    except Exception as e:
        print(f"[ERROR] Failed to fetch tweets: {e}")
        return 1

    if not new_tweets:
        print("No new posts since last check.")
        return 0

    # Update since_id to newest
    newest_id = new_tweets[-1]["id"]
    state.setdefault(handle_key, {})["since_id"] = newest_id
    save_state(state)

    # Print summary
    print(f"@{HANDLE} — {len(new_tweets)} new post(s):")
    for t in new_tweets:
        print(summarize(t))

    # Also write a markdown report for convenience
    report_name = f"report_{HANDLE}_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.md"
    with open(report_name, "w", encoding="utf-8") as f:
        f.write(f"# Updates for @{HANDLE}\n\n")
        for t in new_tweets:
            f.write(summarize(t) + "\n")
    print(f"\nSaved report: {report_name}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
