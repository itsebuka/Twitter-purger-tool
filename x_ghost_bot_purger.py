"""
X (Twitter) Ghost & Bot Account Purger
Audits and un-follows ghost accounts (inactive >6 months), bot/spam profiles,
and low-signal non-mutuals while strictly preserving mutuals, designated handles,
verified accounts, and engineering connections.
"""

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
import requests

# Ensure UTF-8 output on Windows consoles
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

# ================= CONFIGURATION =================
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "").strip() or "51c752155f1489e7a36ed3595bb4a68ded7bf42d"
CT0_CSRF   = os.getenv("CT0_CSRF", "").strip() or "a21abe5bf24a95c8a2f9d2483a8c7001eafbbaf152226c3effa1f61a56d53c51633b820ef80398ba8b122645dcc20d5946cfaa626f28f083e0f23d9cc18ad229fb2024360280a4194ae7172e3a62fa42"

FOLLOWING_ARCHIVE   = os.getenv("FOLLOWING_ARCHIVE", "following.js")
WHITELIST_FILE      = os.getenv("WHITELIST_FILE", "whitelist.txt")
AUDIT_CSV_FILE      = os.getenv("AUDIT_CSV_FILE", "following_cleanup_audit.csv")
HISTORY_LOG_FILE    = os.getenv("HISTORY_LOG_FILE", "unfollowed_history.log")
PROGRESS_JSON_FILE  = os.getenv("PROGRESS_JSON_FILE", "unfollowed_history.json")

UNFOLLOW_API_URL    = "https://x.com/i/api/1.1/friendships/destroy.json"

# Designated handles permanently protected
CORE_PROTECTED_HANDLES = {
    "pau_nigeria",
    "ikejaelectric",
    "vireontech",
}

# Niche engineering & tech keywords for bio matching
ENGINEERING_KEYWORDS = [
    "hardware", "pcb", "electronics", "embedded", "firmware",
    "robotics", "cad", "defense", "founder", "engineer",
    "aerospace", "ai", "c++", "python", "deep learning"
]

HEADERS = {
    "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
    "x-csrf-token": CT0_CSRF,
    "cookie": f"auth_token={AUTH_TOKEN}; ct0={CT0_CSRF};",
    "content-type": "application/x-www-form-urlencoded",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

session = requests.Session()
session.headers.update(HEADERS)
# =================================================

def load_whitelist():
    """Loads custom whitelisted handles from whitelist.txt / whitelist.json."""
    whitelist = set()
    if os.path.exists(WHITELIST_FILE):
        try:
            if WHITELIST_FILE.endswith(".json"):
                with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    whitelist.update(str(x).strip().lstrip("@").lower() for x in data)
            else:
                with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        clean = line.strip().lstrip("@").lower()
                        if clean and not clean.startswith("#"):
                            whitelist.add(clean)
        except Exception as e:
            print(f"[!] Warning reading whitelist file: {e}")
    return whitelist

def load_unfollowed_history():
    """Loads set of user IDs already unfollowed in past runs."""
    history = set()
    if os.path.exists(PROGRESS_JSON_FILE):
        try:
            with open(PROGRESS_JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                history.update(str(x) for x in data)
        except Exception:
            pass
    if os.path.exists(HISTORY_LOG_FILE):
        try:
            with open(HISTORY_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split(",")
                    if parts and parts[0]:
                        history.add(parts[0].strip())
        except Exception:
            pass
    return history

def record_unfollow_success(user_id, screen_name=""):
    """Persists unfollowed user ID to history log and JSON."""
    user_id_str = str(user_id)
    history = load_unfollowed_history()
    history.add(user_id_str)
    try:
        with open(PROGRESS_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(list(history), f, indent=2)
    except Exception as e:
        print(f"[!] Warning updating JSON progress: {e}")

    try:
        with open(HISTORY_LOG_FILE, "a", encoding="utf-8") as f:
            timestamp = datetime.now(timezone.utc).isoformat()
            f.write(f"{user_id_str},{screen_name},{timestamp}\n")
    except Exception as e:
        print(f"[!] Warning appending to history log: {e}")

def parse_following_archive(archive_path=FOLLOWING_ARCHIVE):
    """Extracts followed account IDs from archive following.js."""
    if not os.path.exists(archive_path):
        print(f"[!] Following archive file '{archive_path}' not found.")
        return []

    print(f"[*] Parsing following archive from: {archive_path}...")
    with open(archive_path, "r", encoding="utf-8") as f:
        raw_text = f.read()
        json_clean = re.sub(r"^window\.YTD\.following\w*\.part\d*\s*=\s*", "", raw_text)
        data = json.loads(json_clean)

    accounts = []
    for item in data:
        f_obj = item.get("following", item)
        account_id = f_obj.get("accountId")
        user_link = f_obj.get("userLink", "")
        if account_id:
            accounts.append({
                "rest_id": str(account_id),
                "user_link": user_link
            })
    return accounts

def evaluate_account(profile, custom_whitelist):
    """
    Evaluates account against Whitelist rules and Purge criteria.
    Returns: (verdict, reason, is_bot, days_inactive, last_post_str)
    """
    screen_name = str(profile.get("screen_name", "")).strip().lstrip("@").lower()
    rest_id = str(profile.get("rest_id", "")).strip()
    bio = str(profile.get("description", "")).lower()
    followers_count = profile.get("followers_count", 0)
    friends_count = profile.get("friends_count", 0)
    statuses_count = profile.get("statuses_count", None)
    profile_image_url = profile.get("profile_image_url_https", "")

    # Calculate days inactive if timestamp is present
    last_post_date = profile.get("last_post_date")
    days_inactive = "N/A"
    last_post_str = "Unknown"
    is_inactive_6mo = False

    if last_post_date:
        try:
            if isinstance(last_post_date, str):
                # Parse Twitter timestamp e.g., 'Wed Jan 24 12:00:00 +0000 2026' or ISO
                try:
                    dt = datetime.strptime(last_post_date, "%a %b %d %H:%M:%S %z %Y")
                except ValueError:
                    dt = datetime.fromisoformat(last_post_date)
            else:
                dt = last_post_date

            days = (datetime.now(timezone.utc) - dt).days
            days_inactive = days
            last_post_str = dt.strftime("%Y-%m-%d")
            if days > 180:
                is_inactive_6mo = True
        except Exception:
            pass

    # Bot profile detection
    is_default_avatar = "default_profile_normal" in profile_image_url or "default_profile_images" in profile_image_url
    is_ratio_bot = (friends_count > 1000 and followers_count < 5 and statuses_count == 0)
    is_bot_suspect = is_default_avatar or is_ratio_bot or profile.get("is_suspended", False)

    # -------------------------------------------------------------
    # 1. IMMUTABLE SAFETY WHITELIST (Never Unfollow)
    # -------------------------------------------------------------
    # Rule 1.1: Core Designated Handles or Custom Whitelist
    if screen_name in CORE_PROTECTED_HANDLES or rest_id in CORE_PROTECTED_HANDLES:
        return "PROTECTED_WHITELIST", "Hardcoded Designated Handle", is_bot_suspect, days_inactive, last_post_str

    if screen_name in custom_whitelist or rest_id in custom_whitelist:
        return "PROTECTED_WHITELIST", "Custom User Whitelist", is_bot_suspect, days_inactive, last_post_str

    # Rule 1.2: Mutual Connection (Follows You Back)
    if profile.get("followed_by") is True:
        return "PROTECTED_WHITELIST", "Mutual Connection (Follows Back)", is_bot_suspect, days_inactive, last_post_str

    # Rule 1.3: Verified Accounts (Blue / Gold / Gray)
    if profile.get("is_verified") or profile.get("is_blue_verified"):
        return "PROTECTED_WHITELIST", "Verified Authority / Institution", is_bot_suspect, days_inactive, last_post_str

    # Rule 1.4: Niche Engineering Keywords in Biography
    matched_kws = [kw for kw in ENGINEERING_KEYWORDS if kw in bio]
    if matched_kws:
        return "PROTECTED_WHITELIST", f"Bio Keyword Match ({', '.join(matched_kws[:3])})", is_bot_suspect, days_inactive, last_post_str

    # -------------------------------------------------------------
    # 2. TARGETING & PURGE CRITERIA (Flag for Unfollow)
    # -------------------------------------------------------------
    # Condition 2.1: Bot / Spam Profile
    if is_bot_suspect:
        bot_reason = "Default Avatar" if is_default_avatar else "Follow Ratio Anomaly"
        return "UNFOLLOW_BOT", f"Suspected Bot/Spam Profile ({bot_reason})", True, days_inactive, last_post_str

    # Condition 2.2: Ghost Inactivity (>6 months or 0 posts)
    if is_inactive_6mo:
        return "UNFOLLOW_GHOST", f"Ghost Account (Inactive for {days_inactive} days > 6 months)", False, days_inactive, last_post_str

    if statuses_count == 0:
        return "UNFOLLOW_GHOST", "Ghost Account (0 Total Posts)", False, days_inactive, last_post_str

    # Condition 2.3: Irrelevant Non-Mutual (Default candidate)
    return "UNFOLLOW_IRRELEVANT", "Non-Mutual & Non-Engineering Profile", False, days_inactive, last_post_str

def export_audit_csv(audited_records, output_csv=AUDIT_CSV_FILE):
    """Exports structured audit results to following_cleanup_audit.csv."""
    fieldnames = [
        "screen_name",
        "user_id",
        "followed_by",
        "last_post_date",
        "days_inactive",
        "is_bot_suspect",
        "verdict",
        "reason"
    ]
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in audited_records:
            writer.writerow({
                "screen_name": rec.get("screen_name", ""),
                "user_id": rec.get("user_id", ""),
                "followed_by": rec.get("followed_by", False),
                "last_post_date": rec.get("last_post_date", "Unknown"),
                "days_inactive": rec.get("days_inactive", "N/A"),
                "is_bot_suspect": rec.get("is_bot_suspect", False),
                "verdict": rec.get("verdict", ""),
                "reason": rec.get("reason", "")
            })
    print(f"[+] Audit CSV successfully generated at: {output_csv}")

def execute_unfollow(user_id):
    """Sends authenticated unfollow request to X API."""
    data = {"user_id": str(user_id)}
    try:
        response = session.post(UNFOLLOW_API_URL, data=data, timeout=20)
    except requests.RequestException as e:
        return "network_error", str(e), 10

    if response.status_code == 200:
        return "success", "", 0
    elif response.status_code == 429:
        reset_epoch = response.headers.get("x-rate-limit-reset")
        if reset_epoch:
            wait_seconds = max(int(float(reset_epoch) - time.time()) + 5, 30)
        else:
            wait_seconds = 900
        return "rate_limited", f"Rate limit reset in {wait_seconds}s", wait_seconds
    elif response.status_code == 403:
        return "forbidden", "HTTP 403 Forbidden (Session token expired or blocked)", 0
    elif response.status_code == 404:
        return "not_found", "User already deactivated, suspended, or unfollowed", 0
    else:
        return "failed", f"HTTP {response.status_code}: {response.text[:100]}", 0

def run():
    parser = argparse.ArgumentParser(description="X (Twitter) Ghost & Bot Account Purger")
    parser.add_argument("--dry-run", action="store_true", help="Audit and preview candidates without calling mutation API")
    parser.add_argument("--live-run", action="store_true", help="Execute live throttled unfollow loop")
    parser.add_argument("--limit", type=int, default=60, help="Maximum unfollows per run (default: 60, recommended: 50-75)")
    parser.add_argument("--min-sleep", type=float, default=25.0, help="Minimum jittered sleep interval in seconds (default: 25.0)")
    parser.add_argument("--max-sleep", type=float, default=55.0, help="Maximum jittered sleep interval in seconds (default: 55.0)")
    args = parser.parse_args()

    print("=" * 65)
    print("      X (Twitter) Ghost, Bot & Inactivity Pruning Engine      ")
    print("=" * 65)

    # 1. Ingest Following Data
    raw_accounts = parse_following_archive()
    if not raw_accounts:
        print("[!] No following accounts found to audit. Exiting.")
        return

    print(f"[+] Total Following Accounts Found: {len(raw_accounts)}")

    # 2. Load Whitelists and History
    custom_whitelist = load_whitelist()
    print(f"[+] Loaded {len(custom_whitelist)} Custom Whitelist Handles from '{WHITELIST_FILE}'.")
    unfollowed_history = load_unfollowed_history()
    print(f"[+] Loaded {len(unfollowed_history)} Previously Unfollowed Accounts from History.")

    # 3. Audit and Categorize Accounts
    print("\n[*] Auditing accounts against targeting and whitelist criteria...")
    audited_records = []
    protected_count = 0
    ghost_count = 0
    bot_count = 0
    irrelevant_count = 0
    already_unfollowed_count = 0
    unfollow_queue = []

    for item in raw_accounts:
        rest_id = item["rest_id"]

        if rest_id in unfollowed_history:
            record = {
                "screen_name": item.get("screen_name", ""),
                "user_id": rest_id,
                "followed_by": False,
                "last_post_date": "N/A",
                "days_inactive": "N/A",
                "is_bot_suspect": False,
                "verdict": "ALREADY_UNFOLLOWED",
                "reason": "Processed in previous run"
            }
            already_unfollowed_count += 1
            audited_records.append(record)
            continue

        verdict, reason, is_bot, days_inactive, last_post_str = evaluate_account(item, custom_whitelist)

        record = {
            "screen_name": item.get("screen_name", ""),
            "user_id": rest_id,
            "followed_by": item.get("followed_by", False),
            "last_post_date": last_post_str,
            "days_inactive": days_inactive,
            "is_bot_suspect": is_bot,
            "verdict": verdict,
            "reason": reason
        }

        if verdict == "PROTECTED_WHITELIST":
            protected_count += 1
        elif verdict == "UNFOLLOW_GHOST":
            ghost_count += 1
            unfollow_queue.append(record)
        elif verdict == "UNFOLLOW_BOT":
            bot_count += 1
            unfollow_queue.append(record)
        else:
            irrelevant_count += 1
            unfollow_queue.append(record)

        audited_records.append(record)

    # 4. Generate CSV Report
    export_audit_csv(audited_records)

    # 5. Print Summary Statistics
    total_slated = len(unfollow_queue)
    print("\n" + "-" * 55)
    print("📊 AUDIT & PURGE SUMMARY STATS:")
    print(f"   • Total Scanned:             {len(raw_accounts)}")
    print(f"   • Already Unfollowed:        {already_unfollowed_count}")
    print(f"   • Protected by Whitelist:    {protected_count}")
    print(f"   • Flagged Inactive (>6 mo):  {ghost_count}")
    print(f"   • Flagged Bots / Spam:       {bot_count}")
    print(f"   • Flagged Non-Mutual Other:  {irrelevant_count}")
    print(f"   👉 TOTAL SLATED FOR UNFOLLOW: {total_slated}")
    print("-" * 55)

    if total_slated == 0:
        print("\n[+] All non-whitelisted accounts have been pruned! Your following list is 100% clean.")
        return

    # Cap to safety limit
    batch = unfollow_queue[:args.limit]
    print(f"\n[*] Processing Batch Size: {len(batch)} (Safety Cap: {args.limit} per session)")

    # 6. Dry-Run Mode
    if args.dry_run:
        print("\n[!] === DRY-RUN PREVIEW (No API mutations performed) ===")
        for i, target in enumerate(batch, 1):
            s_name = f"@{target['screen_name']}" if target['screen_name'] else f"ID {target['user_id']}"
            print(f"  [{i}/{len(batch)}] [DRY-RUN] Would Unfollow: {s_name} | Reason: {target['reason']}")
        print(f"\n[+] Dry-run simulation finished. Run with '--live-run' to execute live.")
        return

    # 7. Live Execution Mode
    if not args.live_run:
        confirm = input("\nType 'UNFOLLOW' to confirm live execution (or Ctrl+C to abort): ")
        if confirm.strip() != "UNFOLLOW":
            print("[!] Operation aborted by user.")
            return

    print("\n[*] Starting throttled live unfollow execution loop...")
    success_count = 0

    for i, target in enumerate(batch, 1):
        user_id = target["user_id"]
        s_name = target["screen_name"] or user_id

        print(f"[{i}/{len(batch)}] Unfollowing ID {user_id} (@{s_name})...", end="", flush=True)

        status, msg, wait_sec = execute_unfollow(user_id)

        if status in ("success", "not_found"):
            success_count += 1
            record_unfollow_success(user_id, s_name)
            print(f" [OK] ({status})")
        elif status == "rate_limited":
            print(f" [429 Rate Limited] Waiting {wait_sec}s...")
            time.sleep(wait_sec)
            retry_status, _, _ = execute_unfollow(user_id)
            if retry_status == "success":
                success_count += 1
                record_unfollow_success(user_id, s_name)
                print(f"    ↳ Retry Successful [OK]")
        elif status == "forbidden":
            print(f" [403 Forbidden] {msg}")
            print("[!] Halting execution immediately to protect account safety.")
            break
        else:
            print(f" [Failed] {msg}")

        # Anti-ban jittered sleep between requests
        if i < len(batch):
            sleep_time = random.uniform(args.min_sleep, args.max_sleep)
            print(f"    ⏳ Jittered sleep: {sleep_time:.1f}s (anti-ban safety throttle)...")
            time.sleep(sleep_time)

    print(f"\n[+] Session Complete! Successfully unfollowed {success_count} accounts.")
    print(f"[+] Progress logged to '{PROGRESS_JSON_FILE}' and '{HISTORY_LOG_FILE}'.")

if __name__ == "__main__":
    run()
