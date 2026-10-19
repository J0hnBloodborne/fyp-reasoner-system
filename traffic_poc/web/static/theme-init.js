// Runs before first paint so a saved dark theme does not flash light.
try {
  if (localStorage.getItem("traffic-theme") === "dark") {
    document.documentElement.dataset.theme = "dark";
  }
} catch (error) {
  // Storage can be blocked; the light default applies.
}
