import json
import os
import sys
import threading
import time
import webbrowser

import webview

import backend
import resources


class Api:
    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def _push(self, event, *args):
        window = self._window
        if window is None:
            return
        # A single generic dispatcher keeps every push the same shape; args
        # are JSON-encoded so arbitrary log text/course names can't break the
        # generated JS. Never pass evaluate_js's callback= form here — on the
        # Windows/WinForms backend that throws when called off the main
        # thread (pywebview#906), and every push here comes from a worker
        # thread.
        try:
            window.evaluate_js(
                "window.__bridge && window.__bridge(%s, %s)" % (json.dumps(event), json.dumps(list(args)))
            )
        except Exception:
            pass

    def get_bootstrap(self):
        return backend.get_bootstrap()

    def get_courses(self, force_refresh=False):
        return backend.get_courses(force_refresh)

    def start_qr_login(self):
        return backend.start_login(self._push)

    def cancel_login(self):
        return backend.request_stop(force=True)

    def start_run(self, course_ids, options=None):
        return backend.start_run(course_ids, options or {}, self._push)

    def stop_run(self, force=False):
        return backend.request_stop(force=force)

    def get_settings(self):
        return backend.get_settings()

    def save_settings(self, patch=None):
        return backend.save_settings(patch or {})

    def open_captcha_flow(self, course_id=None):
        """Open the Zhihuishu login center in an in-app browser window,
        pre-fill the saved credentials, and once the user has passed login /
        CAPTCHA and reached the course portal, navigate that window to the
        course that hit the CAPTCHA. The CAPTCHA itself is always solved by
        the user."""
        ctx = backend.captcha_context(course_id)
        if not ctx.get("account") or not ctx.get("password"):
            return {"ok": False, "error": "no_credentials"}

        try:
            win = webview.create_window(
                "智慧树登录 · 完成人机验证",
                ctx["loginUrl"],
                width=1020,
                height=760,
                min_size=(720, 560),
            )
        except Exception:
            win = None

        if win is None:
            webbrowser.open(ctx["loginUrl"])
            return {"ok": True, "inApp": False, "url": ctx["courseUrl"]}

        threading.Thread(
            target=self._watch_captcha_window, args=(win, ctx), daemon=True
        ).start()
        return {"ok": True, "inApp": True, "url": ctx["courseUrl"]}

    def _watch_captcha_window(self, win, ctx):
        account = json.dumps(ctx.get("account") or "", ensure_ascii=False)
        password = json.dumps(ctx.get("password") or "", ensure_ascii=False)
        fill_js = _FILL_LOGIN_JS % (account, password)

        def fill_login(*_):
            # runs on the GUI thread (loaded event), not this worker thread -
            # evaluate_js off-thread is unreliable on the WinForms backend.
            try:
                win.evaluate_js(fill_js)
            except Exception:
                pass
        try:
            win.events.loaded += fill_login
        except Exception:
            pass

        deadline = time.time() + 15 * 60
        while time.time() < deadline:
            time.sleep(1.0)
            try:
                url = win.get_current_url() or ""
            except Exception:
                return  # window closed
            on_login = "login.zhihuishu.com" in url or "passport.zhihuishu.com" in url
            if "zhihuishu.com" in url and not on_login:
                # the browser is on the course portal now - jump straight to
                # the course whose video raised the CAPTCHA
                time.sleep(1.2)
                try:
                    win.load_url(ctx["courseUrl"])
                except Exception:
                    pass
                return

    def save_theme(self, theme):
        # UI-only preference: lives in gui_state.json next to speed/threshold,
        # not in config.json (which is the helper's own runtime config).
        backend.save_gui_state({"theme": "dark" if theme == "dark" else "light"})
        return {"ok": True}

    def minimize_window(self):
        if self._window:
            self._window.minimize()

    def close_window(self):
        if self._window:
            self._window.destroy()

    def open_url(self, url):
        webbrowser.open(url)


_FILL_LOGIN_JS = """(function () {
  function setValue(el, value) {
    if (!el) return false;
    try {
      var desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
      desc.set.call(el, value);
    } catch (e) { el.value = value; }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }
  var account = document.querySelector('input[name="account"], #account, #lname, input[type="text"], input[type="tel"]');
  var password = document.querySelector('input[type="password"]');
  var okAccount = setValue(account, %s);
  var okPassword = setValue(password, %s);
  if (!okPassword) {
    var nodes = Array.prototype.slice.call(document.querySelectorAll("div,span,a,li,button"));
    var tab = nodes.filter(function (el) {
      return /账号登录|密码登录|账号密码/.test((el.textContent || "").trim());
    })[0];
    if (tab) tab.click();
  }
  if (okAccount && okPassword) {
    setTimeout(function () {
      var nodes = Array.prototype.slice.call(document.querySelectorAll("button,a,div,span"));
      var btn = nodes.filter(function (el) {
        var txt = (el.textContent || "").trim();
        return /^(登录|立即登录|登 录)$/.test(txt) && el.offsetParent !== null;
      })[0];
      if (btn) btn.click();
    }, 800);
  }
  return okAccount && okPassword;
})()"""


# the project's own modules - in a packaged build all of them live inside the exe
PROJECT_MODULES = ("app", "backend", "resources", "helper", "utils", "ObjDict", "logger", "push", "sign", "zd_utils")


def selftest(online=False):
    """Hidden `ZHSHelper.exe --selftest [--online]`: exercises the build's
    internals and writes selftest.json next to the exe - used to verify a
    packaged build. --online additionally fetches a login QR code from
    Zhihuishu (then cancels) and, if cookies.json holds a session, lists the
    account's courses; nothing is ever played or submitted."""
    import traceback
    result = {}

    def check(name, fn):
        try:
            result[name] = {"ok": True, "detail": fn()}
        except Exception as e:
            result[name] = {"ok": False, "detail": "%s: %s" % (type(e).__name__, e), "trace": traceback.format_exc()[-800:]}

    def web_ui():
        html = resources.ui_html()
        for needle in ("window.__bridge", "<style>", "data:image/png;base64,"):
            if needle not in html:
                raise RuntimeError("UI document is missing %r" % needle)
        return len(html)

    check("web_ui", web_ui)

    def data_dir():
        import utils
        from logger import logger
        paths = {"config": utils.getConfigPath(), "cookies": utils.getRealPath("./cookies.json"), "logs": logger.path}
        for name, p in paths.items():
            if os.path.dirname(p) != backend.ROOT and p != os.path.join(backend.ROOT, "logs"):
                raise RuntimeError("%s resolves outside the app folder: %s" % (name, p))
        if not os.path.isdir(logger.path):
            raise RuntimeError("log folder was not created")
        return paths

    check("data_dir", data_dir)
    check("settings", lambda: backend.get_settings()["logLevel"])

    def upstream_logic():
        # Reference values were produced by the original, unminified sources;
        # the packaged (minified) modules must reproduce them exactly.
        from zd_utils import Cipher, getEv, WatchPoint, HOME_KEY, VIDEO_KEY, QA_KEY
        from sign import sign
        from utils import HMS, versionCmp
        from ObjDict import ObjDict
        data = json.dumps({"a": 1, "b": "中文", "c": [1, 2]})
        expected = {
            HOME_KEY: "9qx0B9PmD0pyNBqlGmFmua6U8p8kYjQ7TcOjiJhTHPIU2OdUkFPKeJw1HVSWUSGW",
            VIDEO_KEY: "ixpAFdp1BIjutzKCDdXIVRy8Uq7PjeD5fXRCB08BtPQNeM0FVwIkwbt8TUbp0tqa",
            QA_KEY: "rH+iuK7H8ybwsIimw0PkVZGpGhvoExFGuhQIbS+F4Fu7f2uKyscI8zc+95PVLoaq",
        }
        for key, cipher_text in expected.items():
            c = Cipher(key)
            if c.encrypt(data) != cipher_text or c.decrypt(cipher_text) != data:
                raise RuntimeError("AES mismatch for key %r" % key)
        if getEv([1, 2, "a"]) != "4b41424f15":
            raise RuntimeError("getEv mismatch")
        if sign({k: "x" for k in ("uuid", "courseId", "fileId", "studyTotalTime", "startDate",
                                  "endDate", "endWatchTime", "startWatchTime")}) != "6e47ec93dfaa5785ba2af79be27bc0c4":
            raise RuntimeError("sign mismatch")
        wp = WatchPoint()
        wp.add(60)
        if wp.get() != "0,1,2,2,3,3,3,4,4,5,5,5,6,6,7,7,7,8,8,9,9,9,10,10,11,11,11,12,12,13,13,13":
            raise RuntimeError("WatchPoint mismatch")
        if HMS(seconds=3725) != "1:02:05" or versionCmp("1.2.10", "1.2.9") <= 0:
            raise RuntimeError("utils mismatch")
        od = ObjDict({"a": {"b": 1}}, default=None)
        if od.a.b != 1 or od.missing is not None:
            raise RuntimeError("ObjDict mismatch")
        helper = backend.get_helper()
        return {"helper": type(helper).__name__, "speed": helper.speed}

    check("upstream_logic", upstream_logic)

    def qr_image():
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (64, 64), "white").save(buf, "PNG")
        uri = backend._to_data_uri(buf.getvalue())
        if not uri.startswith("data:image/png;base64,"):
            raise RuntimeError(uri[:40])
        return len(uri)

    check("qr_image", qr_image)

    def tls_bundle():
        import certifi
        import requests.utils
        path = requests.utils.DEFAULT_CA_BUNDLE_PATH
        if not os.path.isfile(path) or not os.path.isfile(certifi.where()):
            raise RuntimeError("CA bundle missing: %s" % path)
        return os.path.getsize(path)

    check("tls_bundle", tls_bundle)

    def bootstrap():
        boot = backend.get_bootstrap()
        expected = json.loads(resources.read_text("meta.json"))["version"]
        if boot["version"] != expected:
            raise RuntimeError("version %r != %r" % (boot["version"], expected))
        return {"version": boot["version"], "loggedIn": boot["loggedIn"]}

    check("bootstrap", bootstrap)

    def no_loose_sources():
        # in a packaged build nothing of the project may sit next to the exe as a file
        if not getattr(sys, "frozen", False):
            return "not frozen"
        found = []
        for name in PROJECT_MODULES:
            mod = sys.modules.get(name)
            path = getattr(mod, "__file__", None) or ""
            if path and os.path.exists(path):
                found.append(path)
        for dirpath, dirnames, filenames in os.walk(backend.ROOT):
            for fn in filenames:
                stem, ext = os.path.splitext(fn)
                if (ext in (".py", ".pyc") and stem in PROJECT_MODULES) or fn in ("meta.json", "index.html", "app.js", "style.css"):
                    found.append(os.path.join(dirpath, fn))
            if "web" in dirnames:
                found.append(os.path.join(dirpath, "web"))
        if found:
            raise RuntimeError("found on disk: %s" % found)
        return "clean"

    check("no_loose_sources", no_loose_sources)

    if online:
        def qr_login():
            # asks Zhihuishu for a login QR code, then cancels the login the
            # way the UI's cancel button does (async KeyboardInterrupt)
            events = []
            backend.start_login(lambda event, *args: events.append((event, args)))
            deadline = time.time() + 30
            while time.time() < deadline and not any(e == "onLoginQr" for e, _ in events):
                time.sleep(0.2)
            got_qr = [a[0] for e, a in events if e == "onLoginQr"]
            backend.request_stop(force=True)
            deadline = time.time() + 15
            while time.time() < deadline and not any(e == "onLoginFinished" for e, _ in events):
                time.sleep(0.2)
            statuses = [a[0] for e, a in events if e == "onLoginStatus"]
            if not got_qr or not got_qr[0].startswith("data:image/"):
                raise RuntimeError("no QR image: %s" % statuses)
            if "cancelled" not in statuses:
                raise RuntimeError("login did not cancel: %s" % statuses)
            return {"qrBytes": len(got_qr[0]), "statuses": statuses}

        check("qr_login", qr_login)

        def courses():
            if not os.path.isfile(os.path.join(backend.ROOT, "cookies.json")):
                return "skipped (no cookies.json)"
            if not backend.get_bootstrap()["loggedIn"]:
                raise RuntimeError("saved session was not accepted")
            items = backend.get_courses(True)
            return {"count": len(items), "types": sorted({c["type"] for c in items})}

        check("courses", courses)

        def run_path():
            # the run worker end to end (stdout capture, error handling, finish
            # events) on a course id that doesn't exist - only without a login,
            # so no account is ever involved
            if backend.get_helper().cookies:
                return "skipped (logged in)"
            state_path = os.path.join(backend.ROOT, "gui_state.json")
            saved = open(state_path, "rb").read() if os.path.isfile(state_path) else None
            events = []
            try:
                backend.start_run(["selftestNoSuchCourse"], {"speed": 1}, lambda event, *args: events.append((event, args)))
                deadline = time.time() + 60
                while time.time() < deadline and not any(e == "onRunFinished" for e, _ in events):
                    time.sleep(0.2)
            finally:
                if saved is None:
                    if os.path.isfile(state_path):
                        os.remove(state_path)
                else:
                    with open(state_path, "wb") as f:
                        f.write(saved)
            names = [e for e, _ in events]
            ends = [a for e, a in events if e == "onRunCourseEnd"]
            if "onRunFinished" not in names or ends != [("selftestNoSuchCourse", False)]:
                raise RuntimeError("unexpected events: %s" % events[:12])
            return {"events": names[:8], "log": [a[0][:80] for e, a in events if e == "onRunLog"][:3]}

        check("run_path", run_path)

    def ui_window():
        # Opens the real window (hidden) and waits for the version label, which
        # only appears once the page has loaded, its script has run and a call
        # into Python has come back.
        api = Api()
        window = webview.create_window("ZHSHelper", html=resources.ui_html(), js_api=api, hidden=True, width=1100, height=665)
        api.set_window(window)
        seen = {}

        def probe():
            try:
                deadline = time.time() + 30
                while time.time() < deadline and not (seen.get("state") or {}).get("version"):
                    time.sleep(0.5)
                    try:
                        seen["state"] = window.evaluate_js(
                            "({version: (document.getElementById('version-text') || {}).textContent || '',"
                            " logo: (document.querySelector('.rail-brand img') || {}).naturalWidth || 0,"
                            " cssRules: document.styleSheets.length ? document.styleSheets[0].cssRules.length : 0,"
                            " tabs: document.querySelectorAll('.tab').length,"
                            " engine: navigator.userAgent})")
                    except Exception as e:
                        seen["error"] = "%s: %s" % (type(e).__name__, e)
            finally:
                window.destroy()

        webview.start(probe)
        state = seen.get("state") or {}
        if not (state.get("version") and state.get("logo") and state.get("cssRules") and state.get("tabs")):
            raise RuntimeError("UI did not come up: %s" % seen)
        return state

    check("ui_window", ui_window)
    result["_summary"] = {"ok": all(v["ok"] for v in result.values()), "frozen": bool(getattr(sys, "frozen", False))}
    with open(os.path.join(backend.ROOT, "selftest.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result["_summary"]["ok"]


def main():
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest(online="--online" in sys.argv) else 1)
    api = Api()
    # the UI is handed over as one in-memory document - there are no web files on disk
    window = webview.create_window(
        "ZHSHelper",
        html=resources.ui_html(),
        js_api=api,
        frameless=True,
        easy_drag=False,
        width=1100,
        height=665,
        min_size=(640, 500),
        background_color="#F2F2F4",
    )
    api.set_window(window)
    webview.start(debug=False)


if __name__ == "__main__":
    main()
