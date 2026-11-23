/* Photos / videos stream.
   Desktop: one row; scrolling down moves the row sideways (and sideways swipes work too).
   Phone (<= 700px): one column you scroll normally.
   Order is shuffled on every visit. Media loads only when it gets close to the screen. */

(function () {
  var body = document.body;
  var kind = body.getAttribute("data-kind");               // "photos" | "videos"
  var data = ((window.MEDIA || {})[kind] || []).slice();
  var stream = document.getElementById("stream");
  var track = document.getElementById("track");
  var header = document.querySelector(".site-header");
  var phone = window.matchMedia("(max-width: 700px)");
  var isVideo = kind === "videos";

  if (!data.length) {
    track.innerHTML = '<p class="stream-empty">nothing here yet.</p>';
    return;
  }

  // shuffle (Fisher–Yates)
  for (var i = data.length - 1; i > 0; i--) {
    var j = Math.floor(Math.random() * (i + 1));
    var t = data[i]; data[i] = data[j]; data[j] = t;
  }

  // ---------- build ----------
  var items = data.map(function (m) {
    var fig = document.createElement("figure");
    fig.className = "item";

    var frame = document.createElement("div");
    frame.className = "item__frame";

    var el, btn;
    if (isVideo) {
      el = document.createElement("video");
      el.muted = true;
      el.loop = true;
      el.playsInline = true;
      el.preload = "none";
      el.setAttribute("muted", "");
      el.setAttribute("playsinline", "");
      el.setAttribute("aria-label", m.caption);
    } else {
      el = document.createElement("img");
      el.alt = m.caption;
      el.decoding = "async";
      el.addEventListener("load", function () { el.classList.add("is-loaded"); });
      el.addEventListener("error", function () { el.classList.add("is-loaded"); });
    }
    frame.appendChild(el);

    var cap = document.createElement("figcaption");
    var name = document.createElement("span");
    name.textContent = m.caption;
    cap.appendChild(name);

    var it = { fig: fig, el: el, m: m, loaded: false, playing: false, a: 0, b: 0 };

    if (isVideo) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sound";
      btn.textContent = "sound on";
      btn.setAttribute("aria-pressed", "false");
      btn.addEventListener("click", function () { toggleSound(it); });
      cap.appendChild(btn);
      el.addEventListener("click", function () { toggleSound(it); });
      it.btn = btn;
    }

    fig.appendChild(frame);
    fig.appendChild(cap);
    track.appendChild(fig);
    return it;
  });

  function load(it) {
    it.loaded = true;
    if (isVideo) {
      it.el.poster = it.m.poster;
      it.el.preload = "auto";
      it.el.src = it.m.src;
    } else {
      it.el.src = it.m.src;
    }
  }

  function play(it) {
    if (it.playing) return;
    it.playing = true;
    var p = it.el.play();
    if (p && p.catch) p.catch(function () { it.playing = false; });
  }

  function pause(it) {
    if (!it.playing) return;
    it.playing = false;
    it.el.pause();
  }

  function toggleSound(it) {
    var turnOn = it.el.muted;
    items.forEach(function (o) {
      if (!isVideo) return;
      o.el.muted = true;
      o.btn.textContent = "sound on";
      o.btn.setAttribute("aria-pressed", "false");
    });
    if (turnOn) {
      if (!it.loaded) load(it);
      it.el.muted = false;
      it.btn.textContent = "sound off";
      it.btn.setAttribute("aria-pressed", "true");
      it.playing = false;
      play(it);
    }
  }

  // ---------- layout ----------
  var vertical = false, start = 0, maxX = 0;

  function measure() {
    vertical = phone.matches;
    document.documentElement.style.setProperty("--header-h", header.offsetHeight + "px");

    if (vertical) {
      stream.style.height = "";
      track.style.transform = "";
      items.forEach(function (it) {
        var r = it.fig.getBoundingClientRect();
        it.a = r.top + window.scrollY;
        it.b = r.bottom + window.scrollY;
      });
    } else {
      maxX = Math.max(0, track.scrollWidth - window.innerWidth);
      stream.style.height = (maxX + window.innerHeight) + "px";
      start = stream.getBoundingClientRect().top + window.scrollY;
      items.forEach(function (it) {
        it.a = it.fig.offsetLeft;
        it.b = it.fig.offsetLeft + it.fig.offsetWidth;
      });
    }
  }

  var queued = false;
  function update() {
    queued = false;
    var from, to;
    if (vertical) {
      from = window.scrollY;
      to = from + window.innerHeight;
    } else {
      var x = Math.min(maxX, Math.max(0, window.scrollY - start));
      track.style.transform = "translate3d(" + (-x) + "px,0,0)";
      from = x;
      to = x + window.innerWidth;
    }
    var span = to - from;
    var preFrom = from - span, preTo = to + span * 1.5;   // load a bit ahead

    for (var k = 0; k < items.length; k++) {
      var it = items[k];
      if (!it.loaded && it.b > preFrom && it.a < preTo) load(it);
      if (isVideo && it.loaded) {
        if (it.b > from && it.a < to) play(it); else pause(it);
      }
    }
  }

  function queue() {
    if (!queued) { queued = true; requestAnimationFrame(update); }
  }

  function relayout() {
    // keep roughly the same spot when the window changes size
    var progress = !vertical && maxX ? (window.scrollY - start) / maxX : null;
    measure();
    if (progress !== null && !vertical) {
      window.scrollTo(0, start + Math.max(0, Math.min(1, progress)) * maxX);
    }
    update();
  }

  window.addEventListener("scroll", queue, { passive: true });
  window.addEventListener("resize", function () { clearTimeout(relayout.t); relayout.t = setTimeout(relayout, 120); });
  if (phone.addEventListener) phone.addEventListener("change", relayout);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(relayout);

  // sideways trackpad swipes move the row too
  window.addEventListener("wheel", function (e) {
    if (vertical) return;
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      e.preventDefault();
      window.scrollBy(0, e.deltaX * (e.deltaMode === 1 ? 16 : 1));
    }
  }, { passive: false });

  // arrow keys step one item at a time
  window.addEventListener("keydown", function (e) {
    if (vertical || e.altKey || e.metaKey || e.ctrlKey) return;
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    var step = items[0].fig.offsetWidth + parseFloat(getComputedStyle(track).columnGap || 16);
    window.scrollBy({ top: e.key === "ArrowRight" ? step : -step, behavior: "smooth" });
  });

  // pause everything when the tab is hidden
  document.addEventListener("visibilitychange", function () {
    if (!isVideo) return;
    if (document.hidden) items.forEach(pause); else update();
  });

  // new shuffle each visit, so always start at the beginning
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  window.scrollTo(0, 0);
  measure();
  update();
})();
