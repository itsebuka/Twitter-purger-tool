# ⚡ Twitter (X) Purger Tool & 24/7 Cloud Runner

<div align="center">
  <h3>Zero-Cost, Hands-Off Archive Cleaner with Dynamic Rate Limit Handling & GitHub Actions 24/7 Cloud Execution</h3>

  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/GitHub%20Actions-Automated-purple.svg" alt="GitHub Actions">
  <img src="https://img.shields.io/badge/Platform-Cloud%20%7C%20Local-orange.svg" alt="Platform">
</div>

---

### 🌟 Why This Exists
Following X (Twitter) API paywall changes, third-party deletion tools charge expensive monthly subscriptions ($10–$50/mo) or require handing over your account OAuth access. 

**Twitter Purger Tool** is a 100% free, private, and fully automated solution. It allows you to:
- Purge tens of thousands of old replies and reposts from your archive.
- Run **24/7 in the cloud on GitHub Actions** while your computer is completely turned off.
- Automatically handle Twitter's strict **15-minute rate-limit windows (200 deletions/window)** with dynamic header detection and sleep countdowns.
- Safely checkpoint progress (`purge_progress.json`) so no deletions or rate limits are ever wasted.

---

### ✨ Features
- 🚀 **24/7 Cloud Execution:** Run on GitHub Actions in the background — no laptop battery or internet connection needed.
- ⏱️ **Dynamic Rate Limit Handling:** Reads `x-rate-limit-reset` directly from Twitter's response headers to sleep the exact number of seconds until the rate limit resets.
- 💾 **Auto-Checkpointing:** Saves progress after every single deletion. Pause (`Ctrl+C`) or stop anytime and resume without re-processing deleted items.
- 🎯 **Targeted Cleaning:** Specifically filters and deletes **Replies and Reposts** on or before a specified cutoff date, leaving your original standalone tweets and recent activity untouched.
- 🔒 **Zero Third-Party Sharing:** Uses direct session tokens stored exclusively on your local machine or private repository secrets.

---

### 📋 Prerequisites & Credentials
To authenticate delete requests, you need two cookie values from your active Twitter web session:

1. Open [x.com](https://x.com) in your browser and make sure you are logged in.
2. Press **`F12`** (or Right-Click $\rightarrow$ **Inspect**) to open Developer Tools.
3. Go to the **Application** tab (or **Storage** in Firefox) $\rightarrow$ **Cookies** $\rightarrow$ `https://x.com`.
4. Copy the values of:
   - **`auth_token`**: (a 40-character hex string)
   - **`ct0`**: (a long CSRF token string)

---

### 🚀 Setup Method 1: 24/7 Cloud Execution (Recommended)
Run entirely in GitHub Actions so you can shut down your laptop and let the cloud handle the 15-minute rate limits.

1. **Fork or Import this repository as a PRIVATE repository.**
   > ⚠️ **CRITICAL:** Ensure your repository is set to **Private** to protect your archive data and session tokens.
2. Add your downloaded `tweets.js` archive file to the root of your repository.
3. Configure your GitHub Repository Secrets:
   - Go to your repository **Settings** $\rightarrow$ **Secrets and variables** $\rightarrow$ **Actions**.
   - Click **New repository secret** and add:
     - `AUTH_TOKEN`: *(your Twitter auth_token)*
     - `CT0_CSRF`: *(your Twitter ct0 token)*
     - `CUTOFF_DATE`: *(e.g. `2026-05-31`)*
4. Enable workflow write permissions:
   - In repo **Settings** $\rightarrow$ **Actions** $\rightarrow$ **General** $\rightarrow$ **Workflow permissions**.
   - Select **Read and write permissions** $\rightarrow$ Click **Save**.
5. Go to the **Actions** tab $\rightarrow$ Click **Twitter 24/7 Cloud Purger** $\rightarrow$ Click **Run workflow**.

The cloud runner will automatically execute, delete tweets in 200-item bursts, sleep through 15-minute rate limit windows, and commit updated progress back to your repo!

---

### 💻 Setup Method 2: Local Python Execution

1. **Clone the repository:**
   ```bash
   git clone https://github.com/itsebuka/Twitter-purger-tool.git
   cd Twitter-purger-tool
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure your credentials:**
   Copy `.env.example` to `.env` and fill in your details:
   ```ini
   AUTH_TOKEN=your_auth_token_here
   CT0_CSRF=your_ct0_csrf_token_here
   CUTOFF_DATE=2026-05-31
   ARCHIVE_PATH=tweets.js
   ```

4. **Add your `tweets.js`:**
   Place your extracted `tweets.js` archive file into the project directory.

5. **Run the purger:**
   ```bash
   python async_purge.py
   ```

---

### 🛠️ In-Browser Console Scripts
If you only have a few hundred recent tweets to delete and don't want to use an archive:
- Open your profile (`/with_replies` or `/likes`) on X.
- Open Developer Tools Console (**`F12`**).
- Paste [`delete-replies.js`](./delete-replies.js), [`delete-reposts.js`](./delete-reposts.js), or [`unlike-tweets.js`](./unlike-tweets.js) and press **Enter**.

---

### 🛡️ Security & Privacy Notice
- Never commit your `.env` file, `auth_token`, or personal `tweets.js` archive to a public repository.
- The `.gitignore` in this project is pre-configured to ignore all archive files and local environment files.

---

### 📄 License
Distributed under the MIT License. See `LICENSE` for more information.
