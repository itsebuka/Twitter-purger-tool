"""
X (Twitter) Automated Unfollower & Whitelist Engine
Audits, filters, and purges inactive, bot, or non-mutual followed accounts
while deterministically preserving high-value connections.
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

# ================= CONFIGURATION & CONSTANTS =================
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "").strip() or "51c752155f1489e7a36ed3595bb4a68ded7bf42d"
CT0_CSRF   = os.getenv("CT0_CSRF", "").strip() or "a21abe5bf24a95c8a2f9d2483a8c7001eafbbaf152226c3effa1f61a56d53c51633b820ef80398ba8b122645dcc20d5946cfaa626f28f083e0f23d9cc18ad229fb2024360280a4194ae7172e3a62fa42"

FOLLOWING_ARCHIVE = os.getenv("FOLLOWING_ARCHIVE", "following.js")
WHITELIST_FILE    = os.getenv("WHITELIST_FILE", "whitelist.txt")
AUDIT_CSV_FILE    = os.getenv("AUDIT_CSV_FILE", "following_audit.csv")
HISTORY_LOG_FILE  = os.getenv("HISTORY_LOG_FILE", "unfollowed_history.log")
PROGRESS_JSON_FILE= os.getenv("PROGRESS_JSON_FILE", "unfollow_progress.json")

UNFOLLOW_API_URL  = "https://x.com/i/api/1.1/friendships/destroy.json"

# Core designated handles that are permanently protected
CORE_PROTECTED_HANDLES = {
    "pau_nigeria",
    "ikejaelectric",
    "vireontech",
}

# Niche keywords for biographical matching (case-insensitive)
NICHE_KEYWORDS = [
    "hardware", "pcb", "electronics", "embedded", "firmware",
    "robotics", "cad", "defense", "founder", "engineer",
    "aerospace", "deep learning"
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
# =============================================================

def load_whitelist():
    """Loads custom whitelisted handles or user IDs from whitelist.txt / whitelist.json."""
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
    """Persists unfollowed user to history files."""
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
    """Extracts list of followed accounts from archive following.js."""
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
    Applies deterministic whitelist rules to determine action verdict.
    Returns (verdict, reason)
    """
    screen_name = str(profile.get("screen_name", "")).strip().lstrip("@").lower()
    rest_id = str(profile.get("rest_id", "")).strip()

    # Rule 1: Designated Hardcoded Core Handles or Custom Whitelist
    if screen_name in CORE_PROTECTED_HANDLES or rest_id in CORE_PROTECTED_HANDLES:
        return "PROTECTED_WHITELIST", "Hardcoded Core Designated Handle"

    if screen_name in custom_whitelist or rest_id in custom_whitelist:
        return "PROTECTED_WHITELIST", "User Custom Whitelist File"

    # Rule 2: Mutual Connection (Follows You Back)
    if profile.get("followed_by") is True:
        return "PROTECTED_WHITELIST", "Mutual Connection (Follows Back)"

    # Rule 3: Verified Organization or Public Figure
    if profile.get("is_verified") or profile.get("is_blue_verified"):
        return "PROTECTED_WHITELIST", "Verified Authority / Institution"

    # Rule 4: Niche Keyword Match in Biography
    bio = str(profile.get("description", "")).lower()
    matched_keywords = [kw for kw in NICHE_KEYWORDS if kw in bio]
    if matched_keywords:
        return "PROTECTED_WHITELIST", f"Bio Niche Keyword Match ({', '.join(matched_keywords)})"

    # Inactive check
    last_post = profile.get("last_tweet_date")
    if last_post:
        try:
            post_dt = datetime.fromisoformat(last_post) if isinstance(last_post, str) else last_post
            if (datetime.now(timezone.utc) - post_dt).days > 180:
                return "CANDIDATE_UNFOLLOW", "Inactive (>6 months without post) & Non-mutual"
        except Exception:
            pass

    # Default Verdict
    return "CANDIDATE_UNFOLLOW", "Non-mutual / Irrelevant / Inactive Candidate"

def export_audit_csv(audited_accounts, output_csv=AUDIT_CSV_FILE):
    """Exports audited accounts breakdown to following_audit.csv."""
    fieldnames = [
        "rest_id",
        "screen_name",
        "name",
        "followed_by",
        "is_verified",
        "bio",
        "last_tweet_date",
        "action_verdict",
        "reason"
    ]
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for acc in audited_accounts:
            writer.writerow({
                "rest_id": acc.get("rest_id", ""),
                "screen_name": acc.get("screen_name", ""),
                "name": acc.get("name", ""),
                "followed_by": acc.get("followed_by", False),
                "is_verified": acc.get("is_verified", False) or acc.get("is_blue_verified", False),
                "bio": acc.get("description", "").replace("\n", " "),
                "last_tweet_date": acc.get("last_tweet_date", ""),
                "action_verdict": acc.get("action_verdict", ""),
                "reason": acc.get("reason", "")
            })
    print(f"[+] Audit CSV successfully written to: {output_csv}")

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
        return "forbidden", f"HTTP 403 Forbidden (Check credentials / session)", 0
    elif response.status_code == 404:
        return "not_found", "User already deactivated or unfollowed", 0
    else:
        return "failed", f"HTTP {response.status_code}: {response.text[:100]}", 0

def run_engine():
    parser = argparse.ArgumentParser(description="X (Twitter) Unfollower & Whitelist Engine")
    parser.add_argument("--audit-only", action="store_true", help="Audit accounts and export CSV without unfollowing")
    parser.add_argument("--dry-run", action="store_true", help="Simulate unfollow execution without making live API requests")
    parser.add_argument("--run", action="store_true", help="Execute live throttled unfollow loop")
    parser.add_argument("--max-unfollows", type=int, default=60, help="Maximum number of accounts to unfollow in this session (default: 60)")
    parser.add_argument("--min-sleep", type=float, default=25.0, help="Minimum sleep interval between unfollows (default: 25s)")
    parser.add_argument("--max-sleep", type=float, default=60.0, help="Maximum sleep interval between unfollows (default: 60s)")
    args = parser.parse_args()

    print("=" * 65)
    print("      X (Twitter) Automated Unfollower & Whitelist Engine     ")
    print("=" * 65)

    # 1. Ingest archive
    raw_accounts = parse_following_archive()
    if not raw_accounts:
        print("[!] No following accounts found. Exiting.")
        return

    print(f"[+] Total accounts found in following archive: {len(raw_accounts)}")

    # 2. Load Whitelists and History
    custom_whitelist = load_whitelist()
    print(f"[+] Loaded {len(custom_whitelist)} custom whitelisted entries from '{WHITELIST_FILE}'.")
    unfollowed_history = load_unfollowed_history()
    print(f"[+] Loaded {len(unfollowed_history)} previously unfollowed IDs from history.")

    # 3. Audit and apply deterministic rules
    print("\n[*] Auditing and applying deterministic rules...")
    audited_list = []
    candidates = []
    protected = []

    for acc in raw_accounts:
        rest_id = acc["rest_id"]
        profile = {
            "rest_id": rest_id,
            "screen_name": acc.get("screen_name", ""),
            "name": acc.get("name", ""),
            "description": acc.get("description", ""),
            "followed_by": acc.get("followed_by", False),
            "is_verified": acc.get("is_verified", False),
            "is_blue_verified": acc.get("is_blue_verified", False),
            "last_tweet_date": acc.get("last_tweet_date", "")
        }

        if rest_id in unfollowed_history:
            profile["action_verdict"] = "ALREADY_UNFOLLOWED"
            profile["reason"] = "Processed in prior run"
        else:
            verdict, reason = evaluate_account(profile, custom_whitelist)
            profile["action_verdict"] = verdict
            profile["reason"] = reason

            if verdict == "PROTECTED_WHITELIST":
                protected.append(profile)
            else:
                candidates.append(profile)

        audited_list.append(profile)

    # 4. Export CSV
    export_audit_csv(audited_list)

    print("\n" + "-" * 50)
    print("AUDIT SUMMARY:")
    print(f"   * Total Followed Accounts:   {len(raw_accounts)}")
    print(f"   * Already Unfollowed:        {len([x for x in audited_list if x['action_verdict'] == 'ALREADY_UNFOLLOWED'])}")
    print(f"   * Protected by Whitelist:    {len(protected)}")
    print(f"   * Slated for Unfollow:       {len(candidates)}")
    print("-" * 50)

    if args.audit_only:
        print("\n[+] Mode --audit-only active. Review 'following_audit.csv' before proceeding.")
        return

    if not candidates:
        print("\n[+] No pending candidates to unfollow! Account is fully clean.")
        return

    # Cap candidates for safety
    batch_to_process = candidates[:args.max_unfollows]
    print(f"\n[*] Target batch size for this run: {len(batch_to_process)} (Cap: {args.max_unfollows})")

    # 5. Dry-Run Mode
    if args.dry_run:
        print("\n[!] === DRY-RUN MODE (No API requests will be made) ===")
        for i, target in enumerate(batch_to_process, 1):
            s_name = target.get('screen_name') or target['rest_id']
            print(f"  [{i}/{len(batch_to_process)}] [DRY-RUN] Would unfollow: ID {s_name} ({target['reason']})")
        print("\n[+] Dry-run simulation complete. Run with '--run' to execute live.")
        return

    # 6. Live Execution Mode
    if not args.run:
        confirm = input("\nType 'UNFOLLOW' to start live execution (or Ctrl+C to abort): ")
        if confirm.strip() != "UNFOLLOW":
            print("[!] Aborted by user.")
            return

    print("\n[*] Starting live throttled unfollow loop...")
    successful_unfollows = 0

    for i, target in enumerate(batch_to_process, 1):
        user_id = target["rest_id"]
        s_name = target.get("screen_name") or user_id

        print(f"[{i}/{len(batch_to_process)}] Unfollowing ID {user_id} (@{s_name})...", end="", flush=True)

        status, msg, wait_sec = execute_unfollow(user_id)

        if status in ("success", "not_found"):
            successful_unfollows += 1
            record_unfollow_success(user_id, s_name)
            print(f" [OK] ({status})")
        elif status == "rate_limited":
            print(f" [Rate Limited] Waiting {wait_sec}s...")
            time.sleep(wait_sec)
            retry_status, _, _ = execute_unfollow(user_id)
            if retry_status == "success":
                successful_unfollows += 1
                record_unfollow_success(user_id, s_name)
                print("    ↳ Retry successful")
        elif status == "forbidden":
            print(f" [403 Forbidden] {msg}")
            print("[!] Session token may need refresh. Halting safely to protect account.")
            break
        else:
            print(f" [Failed] {msg}")

        # Throttled random backoff between requests
        if i < len(batch_to_process):
            sleep_duration = random.uniform(args.min_sleep, args.max_sleep)
            print(f"    Sleeping {sleep_duration:.1f}s (anti-ban safety throttle)...")
            time.sleep(sleep_duration)

    print(f"\n[+] Session complete. Successfully unfollowed {successful_unfollows} accounts.")
    print(f"[+] Next run can be triggered anytime with '--run'.")

if __name__ == "__main__":
    run_engine()
