"""
Twitter Archive Local Parser & ID Extractor
Extracts exact Tweet/Reply/Repost IDs within a custom date range from your downloaded archive.
"""

import json
import re
from datetime import datetime

ARCHIVE_PATH = "tweet.js"  # Path to your tweet.js or tweets.js file
OUTPUT_FILE = "filtered_ids.txt"

# Target date bounds (YYYY-MM-DD)
START_DATE = datetime.strptime("2026-02-01", "%Y-%m-%d")
END_DATE = datetime.strptime("2026-05-31", "%Y-%m-%d")

def parse_archive():
    with open(ARCHIVE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
        # Strip X's JS variable declaration (e.g., window.YTD.tweet.part0 = [...])
        json_str = re.sub(r"^window\.YTD\.tweet\w*\.part\d*\s*=\s*", "", content)
        tweets = json.loads(json_str)

    matched_ids = []
    for entry in tweets:
        tweet = entry.get("tweet", entry)
        created_at_str = tweet.get("created_at")
        # Format: "Wed May 20 14:02:00 +0000 2026"
        tweet_date = datetime.strptime(created_at_str, "%a %b %d %H:%M:%S %z %Y").replace(tzinfo=None)

        if START_DATE <= tweet_date <= END_DATE:
            matched_ids.append(tweet.get("id_str"))

    with open(OUTPUT_FILE, "w") as out:
        for tid in matched_ids:
            out.write(f"{tid}\n")

    print(f"[+] Extraction complete. Found {len(matched_ids)} posts matching date range.")
    print(f"[+] IDs saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    parse_archive()