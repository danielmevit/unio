/* Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit).
   https://github.com/danielmevit/unio
   SPDX-License-Identifier: AGPL-3.0-only; see LICENSE and NOTICE. No warranty. */
// Runs before the first paint (loaded without defer): applies a saved Light or
// Dark choice at once, so the page never flashes the other theme while the
// deferred scripts load. System needs nothing here; the stylesheet follows it.
// activity.js stays the authority and re-applies the theme when it runs.
(function () {
  try {
    var saved = localStorage.getItem("unio-theme-preference");
    if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
  } catch (_) {}
})();
