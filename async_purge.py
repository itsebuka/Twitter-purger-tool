"""
X (Twitter) Automated Archive Purger & Cloud Runner
Deletes replies and reposts created on or before a specified cutoff date.
Supports local execution and 24/7 background running on GitHub Actions.
"""

import json
import os
import re
import sys
import time
import requests
from datetime import datetime, timezone

# Load .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ================= CONFIGURATION =================
CUTOFF_DATE_STR = os.getenv("CUTOFF_DATE", "2026-05-31")
try:
    parsed_date = datetime.strptime(CUTOFF_DATE_STR, "%Y-%m-%d")
    CUTOFF_DATE = datetime(parsed_date.year, parsed_date.month, parsed_date.day, 23, 59, 59, tzinfo=timezone.utc)
except Exception:
    CUTOFF_DATE = datetime(2026, 5, 31, 23, 59, 59, tzinfo=timezone.utc)

ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", "tweets.js")
PROGRESS_FILE = os.getenv("PROGRESS_FILE", "purge_progress.json")

QUERY_ID = os.getenv("QUERY_ID", "nxpZCY2K-I6QoFHAHeojFQ")
URL = f"https://x.com/i/api/graphql/{QUERY_ID}/DeleteTweet"

# Fallback tokens ensure it works 100% out of the box even if GitHub Secrets fail
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "").strip() or "51c752155f1489e7a36ed3595bb4a68ded7bf42d"
CT0_CSRF   = os.getenv("CT0_CSRF", "").strip() or "a21abe5bf24a95c8a2f9d2483a8c7001eafbbaf152226c3effa1f61a56d53c51633b820ef80398ba8b122645dcc20d5946cfaa626f28f083e0f23d9cc18ad229fb2024360280a4194ae7172e3a62fa42"

HEADERS = {
    "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
    "x-csrf-token": CT0_CSRF,
    "cookie": f"auth_token={AUTH_TOKEN}; ct0={CT0_CSRF};",
    "content-type": "application/json",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

session = requests.Session()
session.headers.update(HEADERS)
# =================================================

def load_processed_ids():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(str(x) for x in data)
        except Exception as e:
            print(f"[!] Warning reading progress file: {e}")
            return set()
    return set()

def save_processed_id(processed_set, tweet_id):
    processed_set.add(str(tweet_id))
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(processed_set), f)
    except Exception as e:
        print(f"[!] Warning writing progress file: {e}")

def extract_targets():
    if not os.path.exists(ARCHIVE_PATH):
        print(f"[!] Cannot find archive file at '{ARCHIVE_PATH}'.")
        return []

    print(f"[*] Parsing archive from: {ARCHIVE_PATH}...")
    with open(ARCHIVE_PATH, "r", encoding="utf-8") as f:
        raw_text = f.read()
        json_clean = re.sub(r"^window\.YTD\.tweet\w*\.part\d*\s*=\s*", "", raw_text)
        tweets = json.loads(json_clean)

    target_items = []
    for item in tweets:
        tweet = item.get("tweet", item)
        tweet_id = tweet.get("id_str")
        created_at_str = tweet.get("created_at")
        full_text = tweet.get("full_text", "")

        if not created_at_str or not tweet_id:
            continue

        tweet_date = datetime.strptime(created_at_str, "%a %b %d %H:%M:%S %z %Y")

        if tweet_date <= CUTOFF_DATE:
            is_reply = bool(tweet.get("in_reply_to_status_id_str") or tweet.get("in_reply_to_user_id_str"))
            is_repost = full_text.startswith("RT @")

            if is_reply or is_repost:
                target_type = "Repost" if is_repost else "Reply"
                target_items.append((tweet_id, tweet_date, target_type))

    return target_items

def delete_item(tweet_id):
    payload = {
        "variables": {"tweet_id": str(tweet_id), "dark_request": False},
        "queryId": QUERY_ID
    }
    
    try:
        response = session.post(URL, json=payload, timeout=15)
    except requests.RequestException as e:
        return "network_error", str(e), 5

    if response.status_code == 200:
        res_json = response.json()
        if "errors" in res_json:
            return "graphql_error", res_json["errors"][0].get("message", "GraphQL Error"), 0
        return "success", "", 0
    elif response.status_code == 429:
        reset_epoch = response.headers.get("x-rate-limit-reset")
        retry_after = response.headers.get("retry-after")
        if reset_epoch:
            wait_seconds = max(int(float(reset_epoch) - time.time()) + 5, 30)
        elif retry_after:
            wait_seconds = int(retry_after) + 5
        else:
            wait_seconds = 900
        return "rate_limited", f"Rate limit reset in {wait_seconds}s", wait_seconds
    else:
        return "failed", f"HTTP {response.status_code}", 0

def run():
    auto_mode = "--auto" in sys.argv or "--yes" in sys.argv or os.getenv("CI") == "true"
    
    all_targets = extract_targets()
    total_found = len(all_targets)
    if total_found == 0:
        print("[!] No matching items found.")
        return

    processed = load_processed_ids()
    targets = [t for t in all_targets if str(t[0]) not in processed]
    total = len(targets)

    print(f"\n[+] Total matching targets in archive: {total_found}")
    print(f"[+] Already processed / deleted:       {len(processed)}")
    print(f"[+] Remaining to delete:               {total}")
    
    if total == 0:
        print("[+] All items already processed! Archive is fully cleaned.")
        return

    if not auto_mode:
        confirm = input("\nType 'YES' to proceed with deletion: ")
        if confirm.strip() != "YES":
            print("[!] Aborted by user.")
            return
    else:
        print("\n[*] Auto mode enabled. Proceeding with deletion immediately...")

    deleted = 0
    idx = 0

    while idx < total:
        tid, tdate, ttype = targets[idx]
        try:
            status, msg, wait_sec = delete_item(tid)

            if status == "success":
                deleted += 1
                save_processed_id(processed, tid)
                print(f"[{len(processed)}/{total_found}] [+] Deleted {ttype} {tid} ({tdate.strftime('%Y-%m-%d')})")
                idx += 1
                time.sleep(1.0)
            elif status == "rate_limited":
                reset_time_str = datetime.fromtimestamp(time.time() + wait_sec).strftime('%H:%M:%S')
                print(f"\n[!] 429 Rate Limit Hit. Waiting {wait_sec}s until {reset_time_str}...")
                
                while wait_sec > 0:
                    mins, secs = divmod(wait_sec, 60)
                    if not auto_mode:
                        print(f"\r[*] Resuming in {mins:02d}m {secs:02d}s... ", end="", flush=True)
                    sleep_chunk = min(wait_sec, 30 if auto_mode else 5)
                    time.sleep(sleep_chunk)
                    wait_sec -= sleep_chunk
                print("\n[*] Resuming deletion now...\n")
            elif status == "graphql_error":
                save_processed_id(processed, tid)
                print(f"[{len(processed)}/{total_found}] [!] Skipped {ttype} {tid} ({msg})")
                idx += 1
                time.sleep(0.5)
            elif status == "network_error":
                print(f"[!] Network error on {tid}: {msg}. Retrying in 5s...")
                time.sleep(5)
            else:
                print(f"[{len(processed)}/{total_found}] [!] HTTP Error {ttype} {tid} ({msg})")
                idx += 1
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n[!] Paused by user. Progress safely recorded.")
            sys.exit(0)

    print(f"\n[+] Process completed. {deleted} items deleted in this session.")

if __name__ == "__main__":
    run()
