(function () {
  "use strict";

  var busy = false;
  var lastSelectedIds = [];

  // ---------------- theme ----------------

  // Kept in gui_state.json through backend.save_theme(); localStorage is only
  // a fast hint so a dark-mode user doesn't see a light flash before
  // get_bootstrap() answers (pywebview may run with private storage).
  var THEME_KEY = "zhshelper.theme";

  try {
    if (localStorage.getItem(THEME_KEY) === "dark") {
      document.documentElement.dataset.theme = "dark";
    }
  } catch (e) { /* private storage - fall back to the boot value */ }

  function setTheme(theme, persist) {
    var dark = theme === "dark";
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    var btn = $("btn-theme");
    if (btn) btn.title = dark ? "切换到浅色模式" : "切换到深色模式";
    try { localStorage.setItem(THEME_KEY, dark ? "dark" : "light"); } catch (e) {}
    if (persist) {
      var apiTheme = window.pywebview && window.pywebview.api && window.pywebview.api.save_theme;
      try {
        var pending = apiTheme && apiTheme.call(window.pywebview.api, dark ? "dark" : "light");
        if (pending && pending.catch) pending.catch(function () {});
      } catch (e) { /* older build without save_theme - theme still applies */ }
    }
  }

  function wireTheme() {
    $("btn-theme").addEventListener("click", function () {
      setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark", true);
    });
  }

  function $(id) { return document.getElementById(id); }

  function api() { return window.pywebview.api; }

  // ---------------- logs ----------------

  var LOG_LIMIT = 800;
  var logCount = 0;
  var logAutoScroll = true;

  // helper.py prints a scraped tree view ("  |  |_ ...") and progress bars use
  // \r; the backend already drops progress lines, the rest only needs the
  // tree prefix and control characters stripped.
  function cleanLogLine(raw) {
    var s = String(raw == null ? "" : raw).replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, "");
    while (s.slice(0, 3) === "  |") { s = s.slice(3); }
    s = s.replace(/^\s*\|\s*/, "");
    return s.replace(/\s+$/, "");
  }

  function logLevelFor(s) {
    if (/^\[出错\]|Traceback|Exception|ERROR|失败/.test(s)) return "err";
    if (/^\[已停止\]|^\[已强制停止\]|警告|WARN|验证码|人机验证|过期/.test(s)) return "warn";
    if (s.charAt(0) === "[") return "sys";
    return "";
  }

  function nowClock() {
    var d = new Date();
    function p2(n) { return n < 10 ? "0" + n : "" + n; }
    return p2(d.getHours()) + ":" + p2(d.getMinutes()) + ":" + p2(d.getSeconds());
  }

  function logIsVisible() {
    var panel = $("panel-logs");
    return !!panel && panel.classList.contains("active");
  }

  function addLog(raw, level) {
    var text = cleanLogLine(raw);
    var view = $("log-view");
    if (!text || !view) return;

    var empty = $("log-empty");
    if (empty) empty.hidden = true;

    var lv = level || logLevelFor(text);
    var row = document.createElement("div");
    row.className = "log-line" + (lv ? " " + lv : "");

    var time = document.createElement("span");
    time.className = "log-time";
    time.textContent = nowClock();

    var body = document.createElement("span");
    body.className = "log-text";
    body.textContent = text;

    row.appendChild(time);
    row.appendChild(body);
    view.appendChild(row);
    logCount++;

    var lines = view.querySelectorAll(".log-line");
    while (lines.length > LOG_LIMIT) {
      view.removeChild(lines[0]);
      lines = view.querySelectorAll(".log-line");
      logCount--;
    }

    $("log-meta").textContent = logCount + " 行";

    if (logAutoScroll) view.scrollTop = view.scrollHeight;
    if (!logIsVisible()) {
      var dot = $("log-dot");
      if (dot) dot.hidden = false;
    }
  }

  function clearLogs() {
    var view = $("log-view");
    if (!view) return;
    Array.prototype.forEach.call(view.querySelectorAll(".log-line"), function (n) {
      view.removeChild(n);
    });
    logCount = 0;
    $("log-meta").textContent = "0 行";
    var empty = $("log-empty");
    if (empty) empty.hidden = false;
    var dot = $("log-dot");
    if (dot) dot.hidden = true;
  }

  function onLogTabShown() {
    var dot = $("log-dot");
    if (dot) dot.hidden = true;
    var view = $("log-view");
    if (view && logAutoScroll) view.scrollTop = view.scrollHeight;
  }

  function wireLogs() {
    $("btn-log-clear").addEventListener("click", clearLogs);
    $("btn-log-autoscroll").addEventListener("click", function () {
      logAutoScroll = !logAutoScroll;
      this.classList.toggle("active", logAutoScroll);
      this.setAttribute("aria-pressed", logAutoScroll ? "true" : "false");
      if (logAutoScroll) {
        var view = $("log-view");
        view.scrollTop = view.scrollHeight;
      }
    });
  }

  // ---------------- tabs ----------------

  function showTab(name) {
    document.querySelectorAll(".tab").forEach(function (t) {
      t.classList.toggle("active", t.dataset.tab === name);
    });
    document.querySelectorAll(".tab-panel").forEach(function (p) { p.classList.remove("active"); });
    var panel = $("panel-" + name);
    if (panel) panel.classList.add("active");
    if (name === "logs") onLogTabShown();
  }

  function wireTabs() {
    document.querySelectorAll(".tab").forEach(function (tab) {
      tab.addEventListener("click", function () { showTab(tab.dataset.tab); });
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
    // out, the standby check once there's nothing left to scan.
    var qr = $("qr-box");
    $("qr-img").hidden = true;
    qr.classList.remove("has-qr", "is-loading");
    qr.classList.toggle("is-standby", !!isCompact);
    $("qr-placeholder").hidden = false;
    $("qr-placeholder").textContent = isCompact ? "已登录，无需扫码" : QR_IDLE_TEXT;
    // the marketing line under the QR would contradict "已登录" - swap it too
    var desc = document.querySelector(".login-desc");
    if (desc) {
      desc.textContent = isCompact
        ? "登录状态有效，可随时切换账号或重新登录。"
        : "使用「智慧树」App 扫码，登录后可同步课程与学习进度。";
    }
  }

  function onLoginQr(dataUri) {
    addLog("二维码已生成，等待使用「智慧树」App 扫码", "sys");
    var img = $("qr-img");
    img.src = dataUri;
    img.hidden = false;
    // light tile needed for scanning (see .qr-box.has-qr in style.css)
    var qr = $("qr-box");
    qr.classList.remove("is-loading", "is-standby");
    qr.classList.add("has-qr");
    $("qr-placeholder").hidden = true;
  }

  function onLoginStatus(status) {
    if (status && status.indexOf("failed:") === 0) {
      setLoginStatus("登录失败：" + status.slice(7), "bad");
      addLog("登录失败：" + status.slice(7), "err");
      return;
    }
    var entry = LOGIN_STATUS_TEXT[status];
    if (entry) {
      setLoginStatus(entry[0], entry[1]);
      if (status !== "qr") addLog("登录状态：" + entry[0], entry[1] === "bad" ? "err" : "sys");
    }
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
    addLog("开始登录，正在生成二维码…", "sys");
    setBusy(true, "login");
    setLoginCompact(false);
    $("qr-img").hidden = true;
    var qr = $("qr-box");
    qr.classList.remove("has-qr", "is-standby");
    qr.classList.add("is-loading");
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
        // Nothing actually started server-side - undo the button swap and
        // the loading tile above.
        $("qr-box").classList.remove("is-loading");
        $("qr-placeholder").textContent = QR_IDLE_TEXT;
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

  // ---------------- captcha hand-off ----------------

  function openCaptchaFlow() {
    var btn = $("btn-captcha-open");
    if (!captchaCourseId || btn.disabled) return;
    var label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "正在打开…";

    function restore() {
      btn.disabled = false;
      btn.textContent = label;
    }

    api().open_captcha_flow(captchaCourseId).then(function (r) {
      restore();
      if (r && r.ok) {
        $("captcha-status").textContent = r.inApp === false
          ? "已在系统浏览器打开登录页，完成验证后回来重新运行"
          : "已打开登录窗口，进入课程列表后会自动跳到该课程";
        addLog("已打开人机验证页：" + (r.url || ""), "sys");
      } else if (r && r.error === "no_credentials") {
        showTab("settings");
        $("save-hint").textContent = "请先填写账号和密码";
        addLog("缺少账号或密码，无法自动登录", "warn");
        var account = $("opt-username");
        if (account) account.focus();
      } else {
        $("captcha-status").textContent = "打开失败：" + ((r && r.error) || "未知错误");
        addLog("打开验证页失败：" + ((r && r.error) || "未知错误"), "err");
      }
    }).catch(function () {
      restore();
      $("captcha-status").textContent = "打开失败，请重试";
      addLog("打开验证页失败", "err");
    });
  }

  function wireCaptcha() {
    $("btn-captcha-open").addEventListener("click", openCaptchaFlow);
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
    // group badges in the two list headers
    var cz = $("count-zhidao"), ch = $("count-hike");
    if (cz) cz.textContent = zc;
    if (ch) ch.textContent = hc;
    // a group with no rows is noise - hide it and show one shared empty state
    var gz = $("group-zhidao"), gh = $("group-hike"), empty = $("courses-empty");
    if (gz) gz.hidden = !zc;
    if (gh) gh.hidden = !hc;
    if (empty) empty.hidden = !!(zc + hc);
  }

  function loadCourses(forceRefresh) {
    $("courses-hint").textContent = "正在加载课程列表…";
    return api().get_courses(forceRefresh).then(function (list) {
      $("courses-hint").textContent = "共 " + list.length + " 门课程，勾选后点击右侧「开始运行」。";
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
  // studyCourse() returns early (without raising) both on CAPTCHA and on a
  // user-configured time limit, so the backend can't tell GUI-side which one
  // happened - a course that exits this far short of finishing its current
  // video is almost always the CAPTCHA case in practice.
  var CAPTCHA_THRESHOLD = 80;
  // course that raised the last CAPTCHA - the hand-off button opens that one
  var captchaCourseId = null;

  // helper.py's tree-view prints nest with a literal repeating "  |" prefix.
  // Only the video name is pulled out of it - chapter/lesson lines and
  // everything else from the scraping process are no longer surfaced
  // anywhere in the UI (see logs/*.log on disk for the full detail).
  function handleRunLine(raw) {
    var s = raw.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, "");
    while (s.slice(0, 3) === "  |") { s = s.slice(3); }
    var name = null;
    if (s.indexOf("__Studying video ") === 0) name = s.slice(17).trim();
    else if (s.indexOf("__Studying chapter ") !== 0 && s.indexOf("__Studying lesson ") !== 0 && s.indexOf("__Studying ") === 0) name = s.slice(11).trim();
    if (name) $("current-video").textContent = "当前的视频为: " + name;
  }

  function onRunLog(line) {
    handleRunLine(line);
    addLog(line);
  }

  function onRunProgress(p) {
    lastPercent = p.percent;
    $("progress-fill").style.width = Math.max(0, Math.min(100, p.percent)) + "%";
    $("progress-percent").textContent = p.percent.toFixed(1) + "%";
    $("progress-caption").textContent = p.prefix + (p.suffix ? " · " + p.suffix : "");
  }

  function onRunCourseStart(id) {
    captchaCourseId = null;
    addLog("开始课程：" + (courseNameById[id] || id), "sys");
    $("current-course").textContent = "当前的课程为: " + (courseNameById[id] || id);
    $("current-video").textContent = "";
    lastPercent = 0;
    $("progress-fill").style.width = "0%";
    $("progress-percent").textContent = "0%";
  }

  function onRunCourseEnd(id) {
    if (!userStopRequested && lastPercent < CAPTCHA_THRESHOLD) {
      captchaCourseId = id || null;
      $("captcha-alert").hidden = false;
      $("captcha-status").textContent = "在打开的登录页完成验证后，回来重新运行";
      addLog("检测到人机验证，已记录课程 " + (courseNameById[id] || id), "warn");
    }
  }

  function onRunFinished() {
    addLog("本次运行已结束", "sys");
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
        addLog("开始运行，共 " + ids.length + " 门课程", "sys");
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
        addLog("已请求停止，将在当前课程完成后停止", "sys");
        userStopRequested = true;
        $("progress-caption").textContent = "将在当前课程完成后停止。";
        api().stop_run(false);
        setRunButton(RUN_STOPPING);
      } else if (runState === RUN_STOPPING) {
        addLog("已请求强制停止", "warn");
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
        limit: numOrNull("opt-limit"),
        username: $("opt-username").value.trim(),
        password: $("opt-password").value
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
    wireTheme();
    wireLogs();
    wireLogin();
    wireCaptcha();
    wireCourses();
    wireRun();
    wireSettings();

    api().get_bootstrap().then(function (boot) {
      var ver = boot.version ? ("v" + boot.version) : "";
      $("version-text").textContent = ver;
      if ($("about-version")) $("about-version").textContent = ver;
      var st = boot.state || {};
      if (st.theme === "dark" || st.theme === "light") setTheme(st.theme, false);
      var cfg = boot.settings || {};
      if (cfg.username != null) $("opt-username").value = cfg.username;
      if (cfg.password != null) $("opt-password").value = cfg.password;
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
