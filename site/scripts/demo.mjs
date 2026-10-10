// Builds public/demo/: the real dashboard from ../bridge, served on the
// website with its API answered by demo/shim.js from demo/fixtures.json.
// Runs before every build, so the demo always matches the dashboard.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const site = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const bridge = path.join(site, "..", "bridge");
const out = path.join(site, "public", "demo");
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });

let html = fs.readFileSync(path.join(bridge, "index.html"), "utf8");
const anchor = '<link rel="stylesheet" href="activity.css" />';
if (!html.includes(anchor)) throw new Error("bridge/index.html: stylesheet link not found; update scripts/demo.mjs");
// the shim goes first, so it answers the very first request
html = html.replace(anchor, '<script src="demo.js"></script>\n    ' + anchor);
fs.writeFileSync(path.join(out, "index.html"), html);
for (const [, file] of html.matchAll(/(?:src|href)="([a-z_]+\.(?:js|css))"/g))
  if (file !== "demo.js") fs.copyFileSync(path.join(bridge, file), path.join(out, file));

const fixtures = fs.readFileSync(path.join(site, "demo", "fixtures.json"), "utf8").trim();
const shim = fs.readFileSync(path.join(site, "demo", "shim.js"), "utf8");
fs.writeFileSync(path.join(out, "demo.js"), shim.replace("/*FIXTURES*/null", () => fixtures));
console.log("demo: dashboard copied to public/demo");
