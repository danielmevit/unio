// Website demo: the real Unio dashboard, its API calls answered from a
// recorded demo project (demo/fixtures.json). Reading, filtering and
// switching views all work; nothing can be changed or run.
(function () {
  var replies = /*FIXTURES*/null;
  try {
    if (!localStorage.getItem("unio-task-view")) localStorage.setItem("unio-task-view", "map");
    if (!localStorage.getItem("unio-theme-preference")) localStorage.setItem("unio-theme-preference", "dark");
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
