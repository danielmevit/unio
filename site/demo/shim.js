// Website demo: the real Unio dashboard, its API calls answered from a
// recorded demo project (demo/fixtures.json). Only the work map shows
// (demo.css): drag, zoom and open a node's details; nothing can be
// changed or run.
(function () {
  var replies = /*FIXTURES*/null;
  // always the map with every task, finished ones included, dark like the
  // site (the controls that would change these are hidden in the demo)
  try {
    localStorage.setItem("unio-task-view", "map");
    localStorage.setItem("unio-theme-preference", "dark");
    localStorage.setItem("unio-task-filters:v1", JSON.stringify({ version: 1, search: "", worker: "", state: "all", category: "" }));
  } catch (_) {}
  window.fetch = function (input, init) {
    var url = new URL(typeof input === "string" ? input : input.url, location.href);
    var method = ((init && init.method) || "GET").toUpperCase();
    var reply = method === "GET" ? replies[url.pathname + url.search] : null;
    var body = reply ? reply.body : { error: "This is a demo: nothing can be changed or run here." };
    return Promise.resolve(new Response(JSON.stringify(body), {
      status: reply ? reply.status : 403, headers: { "Content-Type": "application/json" },
    }));
  };
})();
