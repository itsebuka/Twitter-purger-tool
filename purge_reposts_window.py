"""
X (Twitter) May 2026 - July 2026 Repost Purger
Filters and deletes all reposts (retweets) created between May 1, 2026 and July 31, 2026.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
import requests

# Reconfigure stdout for UTF-8 on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Optional dotenv support
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

AUTH_TOKEN = os.getenv("AUTH_TOKEN", "").strip() or "51c752155f1489e7a36ed3595bb4a68ded7bf42d"
CT0_CSRF   = os.getenv("CT0_CSRF", "").strip() or "a21abe5bf24a95c8a2f9d2483a8c7001eafbbaf152226c3effa1f61a56d53c51633b820ef80398ba8b122645dcc20d5946cfaa626f28f083e0f23d9cc18ad229fb2024360280a4194ae7172e3a62fa42"

ARCHIVE_PATH  = "tweets.js"
PROGRESS_FILE = "reposts_purge_progress.json"

QUERY_ID = "nxpZCY2K-I6QoFHAHeojFQ"
URL = f"https://x.com/i/api/graphql/{QUERY_ID}/DeleteTweet"

# Target Window: May 1, 2026 to July 31, 2026
START_DATE = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
END_DATE   = datetime(2026, 7, 31, 23, 59, 59, tzinfo=timezone.utc)

HEADERS = {
    "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
    "x-csrf-token": CT0_CSRF,
    "cookie": f"auth_token={AUTH_TOKEN}; ct0={CT0_CSRF};",
    "content-type": "application/json",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

session = requests.Session()
session.headers.update(HEADERS)

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return set(str(x) for x in json.load(f))
        except Exception:
            pass
    return set()

def save_progress(processed_ids):
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(processed_ids), f, indent=2)
    except Exception as e:
        print(f"[!] Warning saving progress: {e}")

def extract_repost_targets(archive_file=ARCHIVE_PATH):
    if not os.path.exists(archive_file):
        print(f"[!] Archive file '{archive_file}' not found.")
        return []

    print(f"[*] Reading archive from: {archive_file}...")
    with open(archive_file, "r", encoding="utf-8") as f:
        raw_text = f.read()

    prefix_match = re.match(r"^(window\.YTD\.tweet\w*\.part\d*\s*=\s*)", raw_text)
    json_clean = raw_text[len(prefix_match.group(1)):] if prefix_match else raw_text
    data = json.loads(json_clean)

    targets = []
    for item in data:
        t = item.get("tweet", item)
        tweet_id = str(t.get("id_str") or t.get("id"))
        created_at_str = t.get("created_at", "")
        full_text = t.get("full_text", "")

        # Check if it's a repost (starts with RT @)
        is_repost = full_text.startswith("RT @")

        if is_repost and created_at_str and tweet_id:
            try:
                dt = datetime.strptime(created_at_str, "%a %b %d %H:%M:%S %z %Y")
                if START_DATE <= dt <= END_DATE:
                    targets.append({
                        "id": tweet_id,
                        "created_at": dt.strftime("%Y-%m-%d"),
                        "text": full_text[:60].replace("\n", " ")
                    })
            except Exception:
                pass

    return targets

def delete_tweet_api(tweet_id):
    payload = {
        "variables": {"tweet_id": str(tweet_id), "dark_request": False},
        "queryId": QUERY_ID
    }
    try:
        response = session.post(URL, json=payload, timeout=15)
    except Exception as e:
        return "network_error", str(e), 5

    if response.status_code == 200:
        res_json = response.json()
        if "errors" in res_json:
            msg = res_json["errors"][0].get("message", "")
            return "graphql_error", msg, 0
        return "success", "", 0
    elif response.status_code == 429:
        reset_epoch = response.headers.get("x-rate-limit-reset")
        wait_seconds = max(int(float(reset_epoch) - time.time()) + 5, 30) if reset_epoch else 900
        return "rate_limited", f"Rate limited. Reset in {wait_seconds}s", wait_seconds
    elif response.status_code in (401, 403):
        return "forbidden", "HTTP 401/403: Auth token invalid or expired", 0
    else:
        return "failed", f"HTTP {response.status_code}", 0

def run_purge():
    print("=" * 65)
    print("   🔁 X (Twitter) Repost Purger: May 2026 - July 2026 Window    ")
    print("=" * 65)

    targets = extract_repost_targets()
    print(f"[+] Total Reposts found between May 1, 2026 & July 31, 2026: {len(targets)}")

    processed_ids = load_progress()
    pending = [t for t in targets if t["id"] not in processed_ids]
    print(f"[+] Already Deleted: {len(targets) - len(pending)}")
    print(f"[+] Remaining to Delete: {len(pending)}\n")

    if not pending:
        print("[+] All reposts in this window have already been deleted!")
        return

    deleted_count = 0
    for i, target in enumerate(pending, 1):
        t_id = target["id"]
        c_date = target["created_at"]

        print(f"[{i}/{len(pending)}] [+] Deleting Repost {t_id} ({c_date})...", end="", flush=True)

        status, msg, wait_sec = delete_tweet_api(t_id)

        if status == "success" or "not found" in msg.lower() or "does not exist" in msg.lower():
            deleted_count += 1
            processed_ids.add(t_id)
            save_progress(processed_ids)
            print(" ✅ [Deleted]")
        elif status == "rate_limited":
            print(f" ⚠️ [429 Rate Limit] Sleeping {wait_sec}s until Twitter window resets...")
            time.sleep(wait_sec)
            retry_status, retry_msg, _ = delete_tweet_api(t_id)
            if retry_status == "success" or "not found" in retry_msg.lower():
                deleted_count += 1
                processed_ids.add(t_id)
                save_progress(processed_ids)
                print("    ↳ Retry successful ✅")
        elif status == "forbidden":
            print(f" ❌ [Auth Error] {msg}")
            break
        else:
            print(f" ❌ [{status}] {msg}")
            # Mark processed to avoid infinite loop
            processed_ids.add(t_id)
            save_progress(processed_ids)

        time.sleep(0.3)

    print("\n" + "=" * 65)
    print(f"🎉 Session Complete! Deleted {deleted_count} reposts.")
    print("=" * 65)

if __name__ == "__main__":
    run_purge()
