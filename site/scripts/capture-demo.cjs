// Records the API replies a running Unio dashboard gives for a demo project,
// for the website's live demo (scripts/demo.mjs serves them back).
//   node scripts/capture-demo.cjs http://127.0.0.1:40981/
// Needs Playwright: set PLAYWRIGHT_MODULE (and CHROMIUM_PATH) if it is not
// installed here. Check demo/fixtures.json for private paths before committing.
const pw = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const fs = require("fs");
const path = require("path");
(async () => {
  const browser = await pw.chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  const replies = {};
  page.on("response", async (response) => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith("/api/") || response.request().method() !== "GET") return;
    try { replies[url.pathname + url.search] = { status: response.status(), body: await response.json() }; } catch (_) {}
  });
  await page.goto(process.argv[2] || "http://127.0.0.1:40981/");
  await page.waitForSelector(".task-row", { timeout: 20000 });
  await page.click("#view-map");
  for (const node of await page.locator("#tasks-map-container [data-kind]").all()) await node.click({ force: true }).catch(() => {});
  await page.waitForTimeout(1500);
  await browser.close();
  fs.writeFileSync(path.join(__dirname, "..", "demo", "fixtures.json"), JSON.stringify(replies, null, 1) + "\n");
  console.log(Object.keys(replies).join("\n"));
})();
