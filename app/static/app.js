(function () {
  const overlay = document.getElementById("loading-overlay");

  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.dataset.loading === "true") {
      if (overlay) overlay.hidden = false;
      form.querySelectorAll("button").forEach(function (button) {
        button.disabled = true;
      });
    }
  });

  const clock = document.getElementById("header-clock");
  if (clock) {
    const tick = function () {
      const now = new Date();
      clock.setAttribute("datetime", now.toISOString());
      clock.textContent = now.toLocaleString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        second: "2-digit",
      });
    };
    tick();
    setInterval(tick, 1000);
  }

  const noteBody = document.getElementById("body");
  const count = document.getElementById("char-count");
  if (noteBody && count) {
    const update = function () {
      count.textContent = String(noteBody.value.length);
    };
    noteBody.addEventListener("input", update);
    update();
  }
})();
