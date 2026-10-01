/**
 * Click a Mermaid diagram to view it full screen, zoomed to fit the window width.
 *
 * Material renders each diagram inside a closed shadow root, and Mermaid caps the
 * SVG at its natural width, so the host element is scaled with CSS `zoom` at that
 * width, measured from the host's height at two widths. In the zoomed view,
 * `+` / `-` or Ctrl + wheel change the zoom, Esc or a click closes it.
 */
(function () {
  const MIN_ZOOM = 0.5;
  const MAX_ZOOM = 6;
  const STEP = 1.25;
  const PROBE_WIDTH = 100;
  let overlay = null;
  let diagram = null;
  let placeholder = null;
  let level = 1;

  function naturalWidth(host) {
    host.style.width = "100000px";
    const fullHeight = host.getBoundingClientRect().height;
    host.style.width = PROBE_WIDTH + "px";
    const probeHeight = host.getBoundingClientRect().height;
    host.style.width = "";
    return (PROBE_WIDTH * fullHeight) / probeHeight;
  }

  function setZoom(value) {
    level = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
    diagram.style.zoom = String(level);
  }

  function open(host) {
    const width = naturalWidth(host);
    diagram = host;
    placeholder = document.createComment("diagram-zoom");
    host.replaceWith(placeholder);
    overlay = document.createElement("div");
    overlay.className = "diagram-zoom-overlay";
    overlay.appendChild(host);
    document.body.appendChild(overlay);
    document.body.classList.add("diagram-zoom-open");
    host.style.width = width + "px";
    const style = getComputedStyle(overlay);
    const room = overlay.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    setZoom(room / width);
  }

  function close() {
    diagram.style.width = "";
    diagram.style.zoom = "";
    placeholder.replaceWith(diagram);
    overlay.remove();
    document.body.classList.remove("diagram-zoom-open");
    overlay = diagram = placeholder = null;
  }

  document.addEventListener("click", (event) => {
    if (overlay) {
      close();
      return;
    }
    const host = event.target.closest && event.target.closest("div.mermaid");
    if (host) open(host);
  });

  document.addEventListener("keydown", (event) => {
    if (!overlay) return;
    if (event.key === "Escape") close();
    else if (event.key === "+" || event.key === "=") setZoom(level * STEP);
    else if (event.key === "-") setZoom(level / STEP);
  });

  document.addEventListener(
    "wheel",
    (event) => {
      if (!overlay || !event.ctrlKey) return;
      event.preventDefault();
      setZoom(event.deltaY < 0 ? level * STEP : level / STEP);
    },
    { passive: false }
  );
})();
