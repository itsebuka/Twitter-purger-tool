# Twitter-purger-tool
A lightweight, zero-API client-side automation suite and Python archive parser to batch-prune historical X (Twitter) interactions, replies, and reposts.

<div align="center">
  <h1>⚡ X Purge Toolkit</h1>
  <p><b>Zero-API, Client-Side Data Sanitization and Privacy Suite for X (Twitter)</b></p>

  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/Dependencies-Zero-blue.svg" alt="Dependencies">
  <img src="https://img.shields.io/badge/Platform-Browser%20%7C%20Python-orange.svg" alt="Platform">
</div>

---

### Why This Exists
Following X API paywall changes, most deletion services charge monthly subscriptions or require handing over full account authentication tokens. `x-purge-toolkit` runs entirely client-side on your local machine using standard browser session primitives and archive parsing.

### Feature Matrix

| Feature | `x-purge-toolkit` | TweetDelete / Redact (Free) | Official X API Tools |
| :--- | :--- | :--- | :--- |
| **Cost** | 100% Free / Open Source | Limited / Paid Paywalls | Paid Enterprise API ($100+/mo) |
| **Credential Sharing** | None (Session Local) | OAuth / Token Handshake | Developer Portal Credentials |
| **Date Range Bounding** | Yes (Custom UTC) | Paywalled | Yes |
| **Mass Unlike** | Yes | Limited | Yes |
| **Archive (>3.2k) Support**| Yes (Local Python) | Paywalled | No |

---

### Quick Start

#### 1. Instant In-Browser Console (No Setup)
1. Navigate to your target timeline tab (`/with_replies`, `/reposts`, or `/likes`).
2. Open DevTools (**`F12`** $\rightarrow$ **Console**).
3. Copy any script from [`/scripts/console`](./scripts/console), adjust the target dates, paste, and press **Enter**.

#### 2. Deep Archive Cleaner (For accounts with >3,200 posts)
1. Request your archive under **Settings $\rightarrow$ Your Account $\rightarrow$ Download an archive**.
2. Run `scripts/python/archive_purger.py` to extract all target post IDs across lifetime history without UI rate limits.

---

### Architecture & Rate Limiting
- **DOM Mutation Safety:** Scripts simulate native browser pointer events (`scrollIntoView`, `click`) rather than raw network spam to prevent platform bot-detection triggers.
- **Randomized Jitter Delays:** Asynchronous wait intervals feature Gaussian/uniform jitter ($\Delta t \approx 800\text{ms} - 1500\text{ms}$) to mirror natural UI latency.

---

### License
Distributed under the MIT License. See `LICENSE` for more information.
