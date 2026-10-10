// Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit).
// https://github.com/danielmevit/unio
// SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const { chromium } = require(process.env.M2_PLAYWRIGHT_MODULE || "playwright");
(async () => {
  assert.ok(
    process.env.TMPDIR,
    "Set TMPDIR to workspace-local tmp before running browser checks",
  );
  const fixture = fs.mkdtempSync(
    path.join(process.env.TMPDIR, "activity-browser-"),
  );
  for (const name of ["repo", "coord", "wt"])
    fs.mkdirSync(path.join(fixture, name));
  const snapshotFile = path.join(fixture, "coord", "snapshot.json");
  const document = {
    schema_version: 1,
    observed_at: "2026-10-04T21:00:00Z",
    stopped: true,
    agents: [
      {
        name: "OpenCode Go",
        binary: { value: "opencode", present: true },
        bench: { off: true, operator_retry_at: 12345 },
        authentication: "unknown",
        capacity: "unknown",
        execution_boundary: "trusted_host",
      },
    ],
    results: [
      {
        worker: "opencode-m2",
        task: "<img src=x onerror=alert(1)> " + "long_literal_task_".repeat(90),
        recorded_at: "2026-10-04T21:00:00Z",
        activity: "failed",
        worker_lock: "free",
        process: { state: "failed", exit_code: 124 },
        validation: { state: "failed", checks_run: 5, checks_failed: 0 },
        review: { state: "not_run", reviewer: null },
      },
    ],
    retries: [
      {
        task: "keyboard",
        failed_attempts: 2,
        blocked: true,
        retry_granted: false,
      },
    ],
    recent_events: [
      {
        event: "run",
        worker: "opencode-m2",
        exit: 124,
        limit_signal: "runner_log_pattern",
      },
      // Activity log integrity: the same task name on two workers, a failed
      // run followed by a passing one, a merge, and seven newer runs that
      // would push the failure past the newest eight.
      { event: "run", worker: "alpha", task: "shared", exit: 1, ts: "2026-01-01T10:00:00Z" },
      { event: "run", worker: "alpha", task: "shared", exit: 0, duration_s: 5, ts: "2026-01-01T10:05:00Z" },
      { event: "run", worker: "beta", task: "shared", exit: 0, duration_s: 7, ts: "2026-01-01T10:06:00Z" },
      { event: "merge", worker: "alpha", ts: "2026-01-01T10:07:00Z" },
      ...Array.from({ length: 7 }, (_, i) => ({ event: "run", worker: "gamma", task: "later-" + i, exit: 0, duration_s: 1, ts: "2026-01-02T10:0" + i + ":00Z" })),
    ],
    warnings: ["Literal <script>alert(1)</script> " + "long_observer_warning_".repeat(90)],
    evidence: "recorded; use result to recheck revision and readiness",
  };
  fs.writeFileSync(snapshotFile, JSON.stringify(document));
  const engine = path.join(fixture, "watch-fixture");
  fs.writeFileSync(
    engine,
    `#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\nassert sys.argv[1:] == ['watch','--once','--json'], 'only read-only observation allowed'\nsys.stdout.buffer.write((Path(__file__).parent/'coord/snapshot.json').read_bytes())\n`,
    { mode: 0o755 },
  );
  const child = spawn(
    "python3",
    [
      "-B",
      path.resolve(__dirname, "../server.py"),
      "--project",
      fixture,
      "--engine",
      engine,
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
  let stderr = "";
  child.stderr.on("data", (chunk) => {
    stderr = (stderr + chunk.toString()).slice(-2000);
  });
  let browser, context;
  const problems = [],
    requests = [];
  try {
    const origin = await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("Activity server startup timed out: " + stderr)),
        10000,
      );
      child.once("error", (error) => {
        clearTimeout(timer);
        reject(error);
      });
      child.once("exit", (code) => {
        clearTimeout(timer);
        reject(new Error("Activity server exited " + code + ": " + stderr));
      });
      child.stdout.on("data", (chunk) => {
        const match = chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/);
        if (match) {
          clearTimeout(timer);
          resolve(match[0]);
        }
      });
    });
    browser = await chromium.launch(
      process.env.M2_CHROMIUM_PATH
        ? { executablePath: process.env.M2_CHROMIUM_PATH }
        : {},
    );
    context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => problems.push(error.message));
    page.on("request", (request) =>
      requests.push({ url: request.url(), method: request.method() }),
    );
    await page.goto(origin);
    await page.waitForFunction(() =>
      document.getElementById("status").textContent.includes("STOP active"),
    );
    await page.waitForFunction(() => document.getElementById("mode-label").textContent === "Read-only");
    assert.equal(await page.locator("#manual-drafts").isVisible(), false);
    assert.equal(await page.locator("#selected-work").isVisible(), false);
    assert.ok((await page.locator(".notice").textContent()).includes("Read-only preview"));
    await page.keyboard.press("Tab");
    assert.equal(await page.locator(":focus").textContent(), "Skip to workspace");
    await page.keyboard.press("Enter");
    assert.equal(await page.locator(":focus").getAttribute("id"), "workspace");
    await page.keyboard.press("Tab");
    assert.equal(await page.locator(":focus").getAttribute("id"), "refresh");
    assert.ok(await page.locator("#refresh").evaluate((el) => getComputedStyle(el).outlineStyle !== "none"));
    await page.keyboard.press("Enter");
    assert.ok(
      (await page.locator("#tasks").textContent()).includes(
        "Process failed · exit 124",
      ),
    );
    assert.ok(
      (await page.locator("#tasks").textContent()).includes("<img src=x"),
    );
    assert.equal(await page.locator("#tasks img").count(), 0);
    assert.ok(
      (await page.locator("#limits").textContent()).includes(
        "authentication unknown · capacity unknown",
      ),
    );
    assert.ok(
      (await page.locator("#limits").textContent()).includes(
        "not a provider reset",
      ),
    );
    assert.ok(
      (await page.locator("#limits").textContent()).includes("Blocked"),
    );
    // Read-only mode exposes only view controls: the list's only extra
    // buttons copy a suggested command to the clipboard.
    const listButtons = await page.getByRole("button").evaluateAll((nodes) =>
      nodes.filter((node) => !node.closest("#task-summary")).map((node) => node.classList.contains("copy-command") ? "copy" : node.textContent.trim()),
    );
    assert.deepEqual(listButtons.filter((name) => name !== "copy"), ["Refresh", "List", "Work map", "Reset filters"]);
    assert.ok(listButtons.includes("copy"), "the list offers a copyable next step");
    assert.deepEqual(await page.locator("#task-summary button").evaluateAll((nodes) => nodes.map((n) => n.dataset.state)), ["attention", "active", "finished"]);
    // Suggested commands are built from names in project files: every name is
    // either plain or single-quoted, so pasting one can only run unio.
    const commands = await page.locator("#tasks .next-line code").allTextContents();
    assert.ok(commands.length > 0, "the list suggests commands");
    for (const command of commands)
      assert.match(command, /^unio [a-z-]+( ('([^']|'\\'')*'|[A-Za-z0-9._\/@%+=:,][A-Za-z0-9._\/@%+=:,-]*))+$/, "command arguments are quoted: " + command);
    assert.ok(commands.some((c) => c.includes(" '<img src=x onerror=alert(1)> long_literal_task_")), "the task name with markup and spaces is one quoted argument");
    // ...and read-only map nodes.
    await page.click("#view-map");
    const buttons = await page.getByRole("button").evaluateAll((nodes) =>
      nodes.filter((node) => !node.closest("#task-summary")).map((node) => node.closest("#work-map") && node.dataset.nodeKey ? "map-node" : node.textContent.trim()),
    );
    assert.deepEqual(
      buttons.filter((name) => name !== "map-node"),
      ["Refresh", "List", "Work map", "Reset filters", "−", "+", "Fit view", "Reset 100%"],
    );
    assert.equal(buttons.filter((name) => name === "map-node").length, 3);
    assert.equal(
      await page.getByRole("button", { name: "Refresh", exact: true }).count(),
      1,
    );
    const before = fs.readFileSync(snapshotFile);
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    assert.deepEqual(fs.readFileSync(snapshotFile), before);
    if (process.env.M2_SCREENSHOTS) {
      fs.mkdirSync(process.env.M2_SCREENSHOTS, { recursive: true });
      await page.screenshot({
        path: path.join(process.env.M2_SCREENSHOTS, "activity-failed.png"),
        fullPage: true,
      });
    }
    fs.writeFileSync(snapshotFile, "broken observation");
    await page.waitForFunction(() =>
      document.getElementById("status").textContent.includes("unavailable"),
    );
    assert.equal(await page.locator("#tasks").textContent(), "");
    assert.equal(await page.locator("#limits").textContent(), "");
    assert.equal(await page.locator("#events").textContent(), "");
    document.stopped = false;
    document.results[0].activity = "completion_unknown";
    document.results[0].process = { state: "running", exit_code: null };
    fs.writeFileSync(snapshotFile, JSON.stringify(document));
    await page.waitForFunction(() =>
      document.getElementById("status").textContent.includes("STOP clear"),
    );
    assert.ok(
      (await page.locator("#tasks").textContent()).includes(
        "Process running · exit unknown",
      ),
    );
    assert.ok(
      (await page.locator("#tasks").textContent()).includes(
        "Detached processes are not ruled out",
      ),
    );
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await page.getByText("Activity log", {exact:true}).click();
    assert.ok((await page.locator("#events").textContent()).includes("Literal <script>"));
    {
      const rows = await page.locator("#events .timeline-row:not(.timeline-warning)").evaluateAll((els) =>
        els.map((el) => ({ text: el.querySelector(".timeline-text").textContent, tone: el.dataset.tone, mark: (el.querySelector(".agent-badge") || {}).dataset })));
      const shared = rows.filter((r) => r.text.startsWith("shared"));
      assert.equal(shared.length, 1, "past the newest eight only the failed run stays: a failure is never folded away");
      assert.ok(shared[0].tone === "failed" && shared[0].text.includes("exit 1"), "a failed run keeps its own red row");
      assert.ok(!rows.some((r) => r.text.includes("exit 1") && r.text.includes("ran 5s")), "two runs never share a row");
      assert.ok(!rows.some((r) => r.text.startsWith("shared") && r.text.includes("merged")), "a merge is not pinned on one task");
      assert.match(await page.locator("#events-count").textContent(), /· 2 failed ·/);
      await page.locator("#events .log-more").click();
      const all = await page.locator("#events .timeline-row:not(.timeline-warning) .timeline-text").allTextContents();
      assert.equal(all.filter((t) => t.startsWith("shared")).length, 3, "the same task name on two workers stays two separate rows");
      assert.ok(all.some((t) => t.startsWith("alpha's branch") && t.includes("merged")));
    }
    assert.equal(await page.locator("#events script").count(), 0);
    assert.ok(await page.locator("#events").evaluate((el) => el.scrollWidth <= el.clientWidth + 1));
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    if (process.env.M2_SCREENSHOTS)
      await page.screenshot({
        path: path.join(process.env.M2_SCREENSHOTS, "activity-mobile.png"),
        fullPage: true,
      });
    assert.deepEqual(fs.readdirSync(path.join(fixture, "coord")), ["snapshot.json"]);
    assert.deepEqual(problems, []);
    assert.ok(
      requests.every(
        (request) =>
          request.url.startsWith(origin + "/") && request.method === "GET",
      ),
    );
    console.log(
      "Activity browser: recorded failure, unknown completion, escaped text, cache/refresh read-only, unavailable/recovery, narrow layout and same-origin GET-only requests passed",
    );
    console.log("Fixture retained: " + fixture);
  } finally {
    if (context) await context.close();
    if (browser) await browser.close();
    if (child.exitCode === null) {
      child.kill("SIGINT");
      await Promise.race([
        once(child, "exit"),
        new Promise((resolve) => setTimeout(resolve, 2000)),
      ]);
      if (child.exitCode === null) child.kill("SIGKILL");
    }
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
