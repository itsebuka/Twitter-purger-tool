/**
 * Automated Mass Unlike Tool for X (Twitter)
 * Target URL: https://x.com/YOUR_USERNAME/likes
 */
(() => {
  let count = 0;
  const delay = (ms) => new Promise((res) => setTimeout(res, ms));

  async function unlikeAll() {
    const unlikeButtons = Array.from(document.querySelectorAll('button[data-testid="unlike"]'));

    if (unlikeButtons.length === 0) {
      console.log("[i] Fetching likes... Scrolling down.");
      window.scrollBy(0, 1500);
      await delay(2500);
      if (document.querySelectorAll('button[data-testid="unlike"]').length === 0) {
        console.log("No more liked posts found.");
        return;
      }
      return unlikeAll();
    }

    for (const btn of unlikeButtons) {
      try {
        btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
        await delay(250);
        btn.click();
        count++;
        console.log(`[+] Unliked post #${count}`);
        await delay(700 + Math.random() * 300);
      } catch (err) {
        console.error("Unlike error:", err);
      }
    }

    window.scrollBy(0, 1500);
    await delay(2000);
    unlikeAll();
  }

  console.log("Starting unlike purge...");
  unlikeAll();
})();