(function () {
  "use strict";

  var busy = false;
  var lastSelectedIds = [];

  function $(id) { return document.getElementById(id); }

  function api() { return window.pywebview.api; }

  // ---------------- tabs ----------------

  function wireTabs() {
    var tabs = document.querySelectorAll(".tab");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        tabs.forEach(function (t) { t.classList.remove("active"); });
        tab.classList.add("active");
        document.querySelectorAll(".tab-panel").forEach(function (p) { p.classList.remove("active"); });
        $("panel-" + tab.dataset.tab).classList.add("active");
      });
    });
  }

  // ---------------- title bar ----------------

  function wireTitlebar() {
    $("btn-min").addEventListener("click", function () { api().minimize_window(); });
    $("btn-close").addEventListener("click", function () { api().close_window(); });
  }

  // ---------------- login ----------------

  var LOGIN_STATUS_TEXT = {
    "qr": ["请使用「智慧树」App 扫码", "pending"],
    "scanned": ["已扫描，请在手机上确认", "pending"],
    "confirming": ["正在登录…", "pending"],
    "expired": ["二维码已过期，正在刷新…", "pending"],
    "success": ["登录成功", "ok"],
    "cancelled": ["已取消登录", ""]
  };

  function setLoginStatus(text, cls) {
    var el = $("login-status");
    el.textContent = text;
    el.className = "status-chip" + (cls ? " " + cls : "");
  }

  var QR_IDLE_TEXT = '点击"开始登录"生成二维码';

  function setLoginCompact(isCompact) {
    $("login-card").classList.toggle("compact", isCompact);
    $("btn-relogin").hidden = !isCompact;
    // The QR card itself always stays in the layout (fixed slot, no reflow
    // when logging in/out) - only its content swaps: the code while logged
    // out, a plain "logged in" note in the same box once there's nothing
    // left to scan.
    $("qr-img").hidden = true;
    $("qr-placeholder").hidden = false;
    $("qr-placeholder").textContent = isCompact ? "已登录，无需扫码" : QR_IDLE_TEXT;
  }

  function onLoginQr(dataUri) {
    var img = $("qr-img");
    img.src = dataUri;
    img.hidden = false;
    $("qr-placeholder").hidden = true;
  }

  function onLoginStatus(status) {
    if (status && status.indexOf("failed:") === 0) {
      setLoginStatus("登录失败：" + status.slice(7), "bad");
      return;
    }
    var entry = LOGIN_STATUS_TEXT[status];
    if (entry) setLoginStatus(entry[0], entry[1]);
  }

  function onLoginFinished() {
    setBusy(false);
    $("btn-cancel-login").hidden = true;
    // Restored regardless of outcome - the .compact CSS rule still hides it
    // when login succeeded, this only matters for the failed/cancelled path
    // where the user needs "开始登录" back to retry.
    $("btn-login").hidden = false;
    var success = $("login-status").classList.contains("ok");
    setLoginCompact(success);
    if (success) loadCourses(false);
  }

  function startLogin() {
    setBusy(true, "login");
    setLoginCompact(false);
    $("qr-img").hidden = true;
    $("qr-placeholder").hidden = false;
    $("qr-placeholder").textContent = "正在生成二维码…";
    setLoginStatus("正在生成二维码…", "pending");
    // One action button on the status row at a time - swap "开始登录" for
    // "取消登录" rather than showing both (one of them disabled) side by side.
    $("btn-login").hidden = true;
    $("btn-cancel-login").hidden = false;
    api().start_qr_login().then(function (r) {
      if (!r.ok) {
        setBusy(false);
        setLoginStatus("当前有其他操作在进行，请稍后再试", "bad");
        // Nothing actually started server-side - undo the button swap above.
        $("btn-login").hidden = false;
        $("btn-cancel-login").hidden = true;
      }
    });
  }

  function wireLogin() {
    $("btn-login").addEventListener("click", startLogin);
    $("btn-relogin").addEventListener("click", startLogin);
    $("btn-cancel-login").addEventListener("click", function () {
      api().cancel_login();
    });
  }

  // ---------------- courses ----------------

  // Populated by renderCourses() below - lets onRunCourseStart show a human
  // name for course ids that only the backend knows about.
  var courseNameById = {};

  function courseRow(c) {
    var row = document.createElement("label");
    row.className = "course-row";
    var cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "course-checkbox";
    cb.value = c.id;
    cb.checked = lastSelectedIds.indexOf(c.id) !== -1;
    var name = document.createElement("span");
    name.className = "course-name";
    name.textContent = c.name;
    row.appendChild(cb);
    row.appendChild(name);
    return row;
  }

  function renderCourses(list) {
    var zhidao = $("list-zhidao");
    var hike = $("list-hike");
    zhidao.innerHTML = "";
    hike.innerHTML = "";
    var zc = 0, hc = 0;
    list.forEach(function (c) {
      courseNameById[c.id] = c.name;
      if (c.type === "zhidao") { zhidao.appendChild(courseRow(c)); zc++; }
      else { hike.appendChild(courseRow(c)); hc++; }
    });
    if (!zc) zhidao.innerHTML = '<div class="empty-hint">暂无数据</div>';
    if (!hc) hike.innerHTML = '<div class="empty-hint">暂无数据</div>';
  }

  function loadCourses(forceRefresh) {
    $("courses-hint").textContent = "正在加载课程列表…";
    return api().get_courses(forceRefresh).then(function (list) {
      $("courses-hint").textContent = "共 " + list.length + " 门课程，勾选后设置右侧参数即可运行。";
      renderCourses(list);
    }).catch(function () {
      $("courses-hint").textContent = "加载失败，请确认已登录后重试。";
    });
  }

  function selectedCourseIds() {
    return Array.prototype.map.call(document.querySelectorAll(".course-checkbox:checked"), function (cb) { return cb.value; });
  }

  function wireCourses() {
    $("btn-refresh-courses").addEventListener("click", function () { loadCourses(true); });
    $("btn-select-all").addEventListener("click", function () {
      document.querySelectorAll(".course-checkbox").forEach(function (cb) { cb.checked = true; });
    });
    $("btn-select-none").addEventListener("click", function () {
      document.querySelectorAll(".course-checkbox").forEach(function (cb) { cb.checked = false; });
    });
  }

  // ---------------- run status ----------------

  // Latest video-level progress percent, tracked so onRunCourseEnd can tell
  // a normal finish from one cut short (see CAPTCHA_THRESHOLD below).
  var lastPercent = 0;
  // True once the user has clicked 停止/强制停止 - suppresses the captcha
  // guess in onRunCourseEnd, since stopping early on purpose isn't captcha.
  var userStopRequested = false;
  // fuckCourse() returns early (without raising) both on CAPTCHA and on a
  // user-configured time limit, so the backend can't tell GUI-side which one
  // happened - a course that exits this far short of finishing its current
  // video is almost always the CAPTCHA case in practice.
  var CAPTCHA_THRESHOLD = 80;

  // fucker.py's tree-view prints nest with a literal repeating "  |" prefix.
  // Only the video name is pulled out of it - chapter/lesson lines and
  // everything else from the scraping process are no longer surfaced
  // anywhere in the UI (see logs/*.log on disk for the full detail).
  function handleRunLine(raw) {
    var s = raw.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, "");
    while (s.slice(0, 3) === "  |") { s = s.slice(3); }
    var name = null;
    if (s.indexOf("__Fucking video ") === 0) name = s.slice(16).trim();
    else if (s.indexOf("__Fucking chapter ") !== 0 && s.indexOf("__Fucking lesson ") !== 0 && s.indexOf("__Fucking ") === 0) name = s.slice(10).trim();
    if (name) $("current-video").textContent = "当前的视频为: " + name;
  }

  function onRunLog(line) { handleRunLine(line); }

  function onRunProgress(p) {
    lastPercent = p.percent;
    $("progress-fill").style.width = Math.max(0, Math.min(100, p.percent)) + "%";
    $("progress-percent").textContent = p.percent.toFixed(1) + "%";
    $("progress-caption").textContent = p.prefix + (p.suffix ? " · " + p.suffix : "");
  }

  function onRunCourseStart(id) {
    $("current-course").textContent = "当前的课程为: " + (courseNameById[id] || id);
    $("current-video").textContent = "";
    lastPercent = 0;
    $("progress-fill").style.width = "0%";
    $("progress-percent").textContent = "0%";
  }

  function onRunCourseEnd() {
    if (!userStopRequested && lastPercent < CAPTCHA_THRESHOLD) {
      $("captcha-alert").hidden = false;
    }
  }

  function onRunFinished() {
    setBusy(false);
    setRunButton(RUN_IDLE);
    $("current-course").textContent = "";
    $("current-video").textContent = "";
    $("progress-caption").textContent = "已结束";
    $("progress-fill").classList.remove("active");
    $("live-dot").classList.remove("on");
  }

  // ---------------- run ----------------

  function numOrNull(id) {
    var v = $(id).value;
    return v === "" ? null : Number(v);
  }

  // One button carries three states so the dashboard only ever shows a
  // single run control: idle -> running (click = graceful stop) -> stopping
  // (click again = force stop, since a graceful stop can be left waiting on
  // the current video).
  var RUN_IDLE = "idle", RUN_RUNNING = "running", RUN_STOPPING = "stopping";
  var runState = RUN_IDLE;

  function setRunButton(state) {
    runState = state;
    var btn = $("btn-run-toggle");
    btn.disabled = false;
    if (state === RUN_RUNNING) {
      btn.textContent = "停止";
      btn.className = "btn btn-run btn-secondary";
    } else if (state === RUN_STOPPING) {
      btn.textContent = "强制停止";
      btn.className = "btn btn-run btn-warn";
    } else {
      btn.textContent = "开始运行";
      btn.className = "btn btn-run btn-primary";
    }
  }

  function wireRun() {
    $("btn-run-toggle").addEventListener("click", function () {
      if (runState === RUN_IDLE) {
        var ids = selectedCourseIds();
        if (!ids.length) {
          $("progress-caption").textContent = "请先在左侧课程列表中勾选至少一门课程。";
          document.querySelector(".courses-card").scrollIntoView({ behavior: "smooth", block: "start" });
          return;
        }
        setBusy(true);
        setRunButton(RUN_RUNNING);
        userStopRequested = false;
        $("captcha-alert").hidden = true;
        $("progress-fill").classList.add("active");
        $("live-dot").classList.add("on");
        $("progress-caption").textContent = "运行中…";
        var options = { speed: numOrNull("opt-speed"), threshold: numOrNull("opt-threshold"), limit: numOrNull("opt-limit") };
        api().start_run(ids, options).then(function (r) {
          if (!r.ok) {
            setBusy(false);
            setRunButton(RUN_IDLE);
            $("progress-fill").classList.remove("active");
            $("live-dot").classList.remove("on");
            $("progress-caption").textContent = "当前有其他操作在进行，请稍后再试。";
          }
        });
      } else if (runState === RUN_RUNNING) {
        userStopRequested = true;
        $("progress-caption").textContent = "将在当前课程完成后停止。";
        api().stop_run(false);
        setRunButton(RUN_STOPPING);
      } else if (runState === RUN_STOPPING) {
        $("progress-caption").textContent = "将在数秒内强制中断当前课程。";
        api().stop_run(true);
        $("btn-run-toggle").disabled = true;
      }
    });
  }

  // ---------------- settings ----------------

  function wireSettings() {
    $("btn-save-settings").addEventListener("click", function () {
      var patch = {
        speed: numOrNull("opt-speed"),
        threshold: numOrNull("opt-threshold"),
        limit: numOrNull("opt-limit")
      };
      api().save_settings(patch).then(function () {
        var hint = $("save-hint");
        hint.textContent = "已保存";
        setTimeout(function () { hint.textContent = ""; }, 2000);
      });
    });
    $("btn-visit-site").addEventListener("click", function () {
      api().open_url("https://suzume.cloud");
    });
  }

  // ---------------- busy state ----------------

  function setBusy(v) {
    busy = v;
    $("btn-login").disabled = busy;
    $("btn-relogin").disabled = busy;
    $("btn-refresh-courses").disabled = busy;
    if (!busy) $("btn-cancel-login").hidden = true;
  }

  // ---------------- bridge ----------------

  var HANDLERS = {
    onLoginQr: onLoginQr,
    onLoginStatus: onLoginStatus,
    onLoginFinished: onLoginFinished,
    onRunLog: onRunLog,
    onRunProgress: onRunProgress,
    onRunCourseStart: onRunCourseStart,
    onRunCourseEnd: onRunCourseEnd,
    onRunFinished: onRunFinished
  };

  window.__bridge = function (event, args) {
    var fn = HANDLERS[event];
    if (fn) fn.apply(null, args);
  };

  // ---------------- scaling ----------------

  // The whole UI is authored at a fixed 1080x620 canvas (see .app-shell) and
  // uniformly scaled to fit the actual window - "等比缩放": the layout never
  // reflows or distorts, it just gets uniformly bigger/smaller, letterboxed
  // if the window's aspect ratio doesn't match the canvas exactly.
  var DESIGN_W = 1080, DESIGN_H = 620;

  function applyScale() {
    var shell = document.querySelector(".app-shell");
    var scale = Math.min(window.innerWidth / DESIGN_W, window.innerHeight / DESIGN_H);
    var offsetX = (window.innerWidth - DESIGN_W * scale) / 2;
    var offsetY = (window.innerHeight - DESIGN_H * scale) / 2;
    shell.style.transform = "translate(" + offsetX + "px, " + offsetY + "px) scale(" + scale + ")";
  }

  // ---------------- splash ----------------

  // Not logged in: nothing to wait for, so the splash just holds for a fixed
  // 3s instead of flashing instantly. Logged in: held until loadCourses()
  // settles instead, since that's the thing worth masking with the splash -
  // see init() below.
  var SPLASH_MIN_MS = 3000;

  function hideSplash() {
    var el = $("splash");
    if (!el) return;
    el.classList.add("hide");
    setTimeout(function () { el.remove(); }, 300);
  }

  // ---------------- init ----------------

  function init() {
    applyScale();
    window.addEventListener("resize", applyScale);
    wireTabs();
    wireTitlebar();
    wireLogin();
    wireCourses();
    wireRun();
    wireSettings();

    api().get_bootstrap().then(function (boot) {
      $("version-text").textContent = boot.version ? ("v" + boot.version) : "";
      var st = boot.state || {};
      if (st.speed != null) $("opt-speed").value = st.speed;
      if (st.threshold != null) $("opt-threshold").value = st.threshold;
      if (st.limit) $("opt-limit").value = st.limit;
      lastSelectedIds = st.lastCourseIds || [];
      if (boot.loggedIn) {
        setLoginStatus("登录成功", "ok");
        setLoginCompact(true);
        loadCourses(false).then(hideSplash);
      } else {
        setTimeout(hideSplash, SPLASH_MIN_MS);
      }
    }).catch(hideSplash);
  }

  window.addEventListener("pywebviewready", init);
})();
