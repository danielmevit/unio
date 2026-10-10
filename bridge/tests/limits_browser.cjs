// Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit).
// https://github.com/danielmevit/unio
// SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
// Designated AI agents & limits in a real browser. Only a deterministic fake
// CLI runs; it logs every argv so the test proves only fixed reads happen.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");
const { once } = require("node:events");
const { chromium } = require(process.env.M2_PLAYWRIGHT_MODULE || "playwright");

(async () => {
  assert.ok(process.env.TMPDIR, "Set TMPDIR to workspace-local tmp before running browser checks");
  const fixture = fs.mkdtempSync(path.join(process.env.TMPDIR, "limits-browser-"));
  for (const name of ["repo", "coord", "wt"]) fs.mkdirSync(path.join(fixture, name));
  const seed = spawnSync("python3", ["-I", "-S", "-B", "-c",
    "import sys; sys.path.insert(0,sys.argv[1]); from bridge.readiness import ReadinessStore; ReadinessStore(sys.argv[2]).record_good('claude','native',True,auth_method='claude.ai')",
    path.resolve(__dirname, "../.."), fixture], { encoding: "utf8" });
  assert.equal(seed.status, 0, seed.stderr);
  const cacheBefore = fs.readFileSync(path.join(fixture, "coord/readiness/observations.json"));
  const data = path.join(fixture, "fake");
  fs.mkdirSync(data);
  const iso = (offset) => new Date(Date.now() + offset * 1000).toISOString().replace("Z", "+00:00");
  const snapshot = {
    schema_version: 1, observed_at: "2026-10-09T16:00:00Z", stopped: false,
    agents: [
      { name: "claude", binary: { value: "claude", present: true }, bench: { off: false, operator_retry_at: null } },
      { name: "codex", binary: { value: "codex", present: true }, bench: { off: false, operator_retry_at: null } },
      { name: "codex-reviewer", binary: { value: "codex", present: null }, bench: { off: true, operator_retry_at: null } },
      { name: "<img src=x onerror=alert(1)>", binary: { value: "x", present: false }, bench: { off: false, operator_retry_at: null } },
    ],
    results: [{ worker: "claude", task: "LIMITS-1", recorded_at: "2026-10-09T16:00:00Z", activity: "running",
      worker_lock: "held", process: { state: "running", exit_code: null },
      validation: { state: "not_run", checks_run: 0, checks_failed: 0 }, review: { state: "not_run", reviewer: null } }],
    retries: [], recent_events: [], warnings: [], evidence: "recorded",
  };
  const policy = { schema_version: 1, mode: "yolo", tier: "low", lead_agent: "codex", lead_group: "codex",
    accounts: { "codex-reviewer": "codex" }, active_native_workflows: { claude: 1 },
    active_with_lead: { claude: 1, codex: 1 }, capacity: "unknown", workflow_enforcement: "native_workflows",
    workflow_limit_per_group: 1, updated_at: iso(-600), owner_email: "secret.person@example.com" };
  const manualWindow = (extra) => Object.assign({ source: "manual", window_minutes: 300, observed_at: iso(-60),
    age_seconds: 60, reset_at: iso(7200), status: "fresh", last_reading_remaining_percent: 42,
    usable_remaining_percent: 42 }, extra);
  const manual = { schema_version: 1, checked_at: iso(0), max_age_seconds: 900, state: "ok", error: null, groups: {
    claude: { status: "recorded", windows: {
      "five-hour": manualWindow({}),
      weekly: manualWindow({ window_minutes: 10080, observed_at: iso(-3600), age_seconds: 3600, status: "stale",
        last_reading_remaining_percent: 80, usable_remaining_percent: null, reset_at: null }) } },
    spare: { status: "recorded", windows: {
      "five-hour": manualWindow({ observed_at: iso(-20000), age_seconds: 20000, reset_at: iso(-60), status: "expired",
        last_reading_remaining_percent: 5, usable_remaining_percent: null }),
      broken: manualWindow({ last_reading_remaining_percent: 150, usable_remaining_percent: 150 }) } } } };
  const codexWindow = (extra) => Object.assign({ status: "fresh", window_minutes: 300, reset_at: iso(5400),
    last_reading_remaining_percent: 69, usable_remaining_percent: 69 }, extra);
  const codex = { schema_version: 1, provider: "codex", checked_at: iso(0), max_age_seconds: 900, state: "ok", error: null,
    groups: { codex: { source: "codex", state: "ok", reason: null, attempted_at: iso(-5), account_kind: "chatgpt",
      observed_at: iso(-5), age_seconds: 5, freshness: "fresh", buckets: { codex: { status: "ok", reason: null, windows: {
        primary: codexWindow({}),
        secondary: codexWindow({ window_minutes: 10080, reset_at: iso(400000), last_reading_remaining_percent: 12.5,
          usable_remaining_percent: 12.5 }) } } }, last_good: null } } };
  const write = (name, value) => fs.writeFileSync(path.join(data, name), typeof value === "string" ? value : JSON.stringify(value));
  write("snapshot.json", snapshot);
  write("policy.json", policy);
  write("manual.json", manual);
  write("codex.json", codex);
  write("exit", "0");
  const engine = path.join(fixture, "fake-unio");
  fs.writeFileSync(engine, `#!/usr/bin/env python3
import json, sys
from pathlib import Path
data = Path(__file__).parent / 'fake'
args = sys.argv[1:]
with open(data / 'argv.log', 'a') as log:
    log.write(json.dumps(args) + '\\n')
if args == ['watch', '--once', '--json']:
    sys.stdout.buffer.write((data / 'snapshot.json').read_bytes()); sys.exit(0)
sys.stderr.write('secret.person@example.com sk-live-TOPSECRET\\n')
if (data / 'exit').read_text() != '0':
    sys.exit(2)
if args == ['policy', '--json']:
    name = 'policy.json'
elif args[:2] == ['capacity', '--project'] and args[3:] == ['show', '--json']:
    name = 'manual.json'
elif args[:2] == ['capacity', '--project'] and args[3:] == ['show', '--provider', 'codex', '--json']:
    name = 'codex.json'
else:
    sys.exit(3)
sys.stdout.buffer.write((data / name).read_bytes())
`, { mode: 0o755 });

  const child = spawn("python3", ["-B", path.resolve(__dirname, "../server.py"), "--project", fixture, "--engine", engine],
    { stdio: ["ignore", "pipe", "pipe"] });
  let stderr = "";
  child.stderr.on("data", (chunk) => { stderr = (stderr + chunk.toString()).slice(-2000); });
  let browser, context;
  const problems = [], requests = [];
  let passed = 0;
  const ok = (name) => { passed++; console.log("PASS " + name); };
  try {
    const origin = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("server startup timed out: " + stderr)), 10000);
      child.once("exit", (code) => { clearTimeout(timer); reject(new Error("server exited " + code + ": " + stderr)); });
      child.stdout.on("data", (chunk) => {
        const match = chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/);
        if (match) { clearTimeout(timer); resolve(match[0]); }
      });
    });
    browser = await chromium.launch(process.env.M2_CHROMIUM_PATH ? { executablePath: process.env.M2_CHROMIUM_PATH } : {});
    context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
    const page = await context.newPage();
    page.on("pageerror", (error) => problems.push("pageerror: " + error.message));
    page.on("console", (message) => { if (message.type() === "error") problems.push("console: " + message.text()); });
    page.on("request", (request) => requests.push({ url: request.url(), method: request.method() }));
    await page.goto(origin);
    await page.waitForFunction(() => document.querySelectorAll("#limits-groups [data-group]").length > 0);

    const sectionText = await page.locator(".limits-section").textContent();
    assert.equal(await page.locator("#limits-title").textContent(), "Designated AI agents & limits");
    assert.equal(await page.locator("#limits-title").evaluate((el) => el.closest("details")), null);
    assert.ok(await page.locator("#limits-title").isVisible());
    assert.ok(!sectionText.includes("TOPSECRET") && !sectionText.includes("secret.person"));
    const lead = await page.textContent("#limits-lead");
    for (const part of ["Registered lead: codex (group codex)", "mode yolo", "tier low", "up to 1 workflow per shared budget",
      "a reservation, not an attached live conversation", "external lead CLI session is not captured"])
      assert.ok(lead.includes(part), lead);
    ok("visible section outside collapsed details; registered-lead/mode/tier reservation overview");

    const route = async (name) => page.locator('#limits-routes [data-route="' + name + '"]').textContent();
    // Each agent card states its facts as labeled readouts: Budget, Running, Tool.
    const facts = async (name) => page.locator('#limits-routes [data-route="' + name + '"] .limits-facts').evaluate((dl) =>
      Object.fromEntries([...dl.children].map((row) => [row.querySelector("dt").textContent, row.querySelector("dd").textContent])));
    const codexRoute = await route("codex");
    assert.ok(codexRoute.includes("Registered lead (reservation)"));
    assert.deepEqual(await facts("codex"), { Budget: "codex, shared with codex-reviewer", Running: "0 + registered lead = 1 of 1", Tool: "installed", "Sign-in": "Unknown" });
    assert.ok((await page.textContent("#limits-caveat")).includes("Sign-in does not establish remaining allowance"));
    assert.ok((await facts("claude"))["Sign-in"].startsWith("Signed in · fresh native observation"));
    const reviewer = await route("codex-reviewer");
    assert.ok(reviewer.includes("Benched OFF"));
    assert.equal((await facts("codex-reviewer")).Budget, "codex, shared with codex");
    assert.equal((await facts("codex-reviewer")).Tool, "Unknown");
    assert.equal((await facts("claude")).Running, "1 of 1");
    assert.equal(await page.locator(".limits-section img").count(), 0);
    assert.equal((await facts("<img src=x onerror=alert(1)>")).Tool, "missing");
    ok("each route: shared group, binary, ON/OFF, native workflow count, cached Claude sign-in distinct from allowance, literal labels");

    assert.equal(await page.locator('#limits-groups [data-group="codex"]').count(), 1, "shared budget shown once");
    const codexGroup = page.locator('#limits-groups [data-group="codex"]');
    assert.ok((await codexGroup.textContent()).includes("Shared by codex, codex-reviewer"));
    const automatic = await codexGroup.locator('.limits-window[data-source="codex"]').allTextContents();
    assert.equal(automatic.length, 2);
    assert.ok(automatic[0].startsWith("codex · 5h · 69% remaining"), automatic[0]);
    assert.ok(/Resets .* · in 1h 2\dm/.test(automatic[0]), automatic[0]);
    assert.ok(automatic[0].includes("Source Automatic Codex · observed 5s before check · fresh"));
    assert.ok(automatic[1].startsWith("codex · weekly · 12.5% remaining") && /in 4d \d+h/.test(automatic[1]), automatic[1]);
    assert.ok(!(await codexGroup.textContent()).includes("81.5"), "windows are never summed");
    ok("Automatic Codex 5h and weekly windows: remaining, reset countdown, age, freshness and source");

    // claude's budget is its own, so its allowance sits inside its card.
    assert.equal(await page.locator('#limits-groups [data-group="claude"]').count(), 0);
    const claude = await page.locator('#limits-routes [data-route="claude"] .limits-window').allTextContents();
    assert.ok(claude[0].startsWith("five-hour · 5h · 42% remaining") && claude[0].includes("Source Manual · observed 1m before check · fresh"), claude[0]);
    assert.ok(claude[1].startsWith("weekly · weekly · last reading 80% · usable Unknown (stale)") && claude[1].includes("Reset time Unknown"), claude[1]);
    const spare = page.locator('#limits-groups [data-group="spare"]');
    const spareWindows = await spare.locator(".limits-window").allTextContents();
    assert.ok(spareWindows.some((t) => t.startsWith("five-hour · 5h · last reading 5% · usable Unknown (expired)")
      && t.includes("has passed · remaining Unknown until a fresh reading")), spareWindows.join("|"));
    assert.ok(spareWindows.some((t) => t.startsWith("broken · invalid reading · remaining Unknown")), spareWindows.join("|"));
    assert.equal(await spare.locator('.limits-window[data-status="invalid"] .limits-meter').count(), 0, "invalid values get no meter");
    assert.ok(await page.locator(".limits-meter span").evaluateAll((spans) => spans.every((s) => parseFloat(s.style.width) <= 100)));
    ok("manual fresh/stale/expired windows; invalid reading is Unknown without a meter; passed reset is not recovery");

    // Unsupported native commands: the section becomes Unknown, activity stays intact.
    write("exit", "2");
    await page.waitForFunction(() => document.getElementById("limits-lead").textContent.includes("Unknown"), null, { timeout: 15000 });
    assert.ok((await page.textContent("#limits-lead")).startsWith("Registered lead, mode and tier: Unknown"));
    assert.ok((await page.textContent("#limits-groups")).includes("Manual and automatic Codex readings are unavailable from the installed CLI and stay Unknown."));
    assert.equal((await facts("claude")).Budget, "Unknown");
    assert.ok((await page.textContent("#status")).includes("STOP clear"));
    assert.ok((await page.textContent("#tasks")).includes("LIMITS-1"));
    ok("unsupported native reads show Unknown without breaking activity");

    // Missing data: a policy group without readings stays Unknown.
    write("exit", "0");
    write("manual.json", Object.assign({}, manual, { state: "missing", groups: {} }));
    write("codex.json", Object.assign({}, codex, { state: "missing", groups: {} }));
    await page.waitForFunction(() => document.querySelector('#limits-groups [data-group="codex"]')
      && document.querySelector('#limits-groups [data-group="codex"]').textContent.includes("No current allowance reading"), null, { timeout: 15000 });
    assert.equal(await page.locator("#limits-groups .limits-window").count(), 0);
    ok("missing readings are Unknown");

    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.ok(await page.locator("#limits-groups").evaluate((el) => el.scrollWidth <= el.clientWidth + 1));
    await page.locator(".limits-section").screenshot({ path: path.join(fixture, "limits-mobile.png") });
    ok("390px layout has no horizontal overflow");

    const argv = fs.readFileSync(path.join(data, "argv.log"), "utf8").trim().split("\n").map((l) => JSON.parse(l));
    const allowed = new Set([JSON.stringify(["watch", "--once", "--json"]), JSON.stringify(["policy", "--json"]),
      JSON.stringify(["capacity", "--project", fixture, "show", "--json"]),
      JSON.stringify(["capacity", "--project", fixture, "show", "--provider", "codex", "--json"])]);
    assert.ok(argv.every((a) => allowed.has(JSON.stringify(a))), JSON.stringify(argv));
    assert.ok(requests.every((r) => r.url.startsWith(origin + "/") && r.method === "GET"));
    assert.ok(requests.some((r) => r.url === origin + "/api/limits"));
    const limitsCalls = argv.filter((a) => a[0] === "policy").length;
    const limitsRequests = requests.filter((r) => r.url === origin + "/api/limits").length;
    assert.ok(limitsCalls < limitsRequests, "server cache serves polls without rerunning reads: " + limitsCalls + "/" + limitsRequests);
    const status = await page.evaluate(async () => (await fetch("/api/limits", { method: "POST", body: "{}" })).status);
    assert.equal(status, 405);
    assert.deepEqual(fs.readdirSync(path.join(fixture, "coord")), ["readiness"]);
    assert.deepEqual(fs.readFileSync(path.join(fixture, "coord/readiness/observations.json")), cacheBefore);
    assert.deepEqual(problems.filter((p) => !p.includes("405")), []);
    ok("only fixed native reads ran; cached polling; same-origin GET only; writes refused; no page errors");
    console.log("Limits browser: " + passed + " assertion groups passed. Fixture retained: " + fixture);
  } finally {
    if (context) await context.close();
    if (browser) await browser.close();
    if (child.exitCode === null) {
      child.kill("SIGINT");
      await Promise.race([once(child, "exit"), new Promise((resolve) => setTimeout(resolve, 2000))]);
      if (child.exitCode === null) child.kill("SIGKILL");
    }
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
