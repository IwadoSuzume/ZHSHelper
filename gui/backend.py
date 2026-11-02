import os
import sys

# The folder that holds config.json / cookies.json / gui_state.json / logs:
# next to the exe when packaged, the project root when run from source.
if getattr(sys, "frozen", False):
    ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # helper.py/utils.py/etc. live one directory above gui/. A packaged build
    # carries them inside the exe, so nothing on disk is ever imported there.
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

import base64
import ctypes
import contextlib
import io
import json
import re
import threading
from functools import partial

# utils.progressBar's default argument calls os.get_terminal_size() at import
# time, and helper.py calls it directly with no guard. A --windowed build (or
# any console-less launch) has no terminal, so the real os.get_terminal_size()
# raises OSError there. Patch it before the first `import utils`/`import
# helper` below so both call sites get a safe fallback instead of crashing.
_real_get_terminal_size = os.get_terminal_size


def _safe_get_terminal_size(fd=1):
    try:
        return _real_get_terminal_size(fd)
    except OSError:
        return os.terminal_size((120, 30))


os.get_terminal_size = _safe_get_terminal_size


class _SafeStdout:
    """Stands in for sys.stdout/stderr for the whole process lifetime.

    A --windowed build has sys.stdout/stderr set to None, and helper.py's
    tree-view prints + utils.progressBar's \\r-based updates would crash the
    first time they run. This absorbs writes unconditionally, optionally
    tees to a real console when one is attached, and can forward completed
    lines to a `sink` callback so a run/login can capture live output
    without ever swapping sys.stdout itself out.
    """

    def __init__(self, real_stream):
        self._real = real_stream
        self._sink = None
        self._buf = ""

    def set_sink(self, fn):
        self._sink = fn
        self._buf = ""

    def write(self, s):
        if not s:
            return 0
        if self._real is not None:
            try:
                self._real.write(s)
            except Exception:
                pass
        sink = self._sink
        if sink is not None:
            self._buf += s
            while True:
                cut = None
                for ch in ("\n", "\r"):
                    i = self._buf.find(ch)
                    if i != -1 and (cut is None or i < cut):
                        cut = i
                if cut is None:
                    break
                line, self._buf = self._buf[:cut], self._buf[cut + 1:]
                if line.strip():
                    try:
                        sink(line)
                    except Exception:
                        pass
        return len(s)

    def flush(self):
        if self._real is not None:
            try:
                self._real.flush()
            except Exception:
                pass

    def isatty(self):
        return False


_stdout_tee = _SafeStdout(sys.__stdout__)
sys.stdout = _stdout_tee
sys.stderr = _SafeStdout(sys.__stderr__)

# Everything below this line is the real project, imported unmodified.
# utils.getDir() resolves every data path from utils' own __file__, which in a
# packaged build is inside _internal (or nowhere at all). Point it at ROOT
# before logger is imported - logger creates ./logs at import time.
import utils

utils.getDir = lambda: ROOT

from helper import Helper
from utils import getConfigPath, getRealPath, cookie_jar_to_list, versionCmp
from ObjDict import ObjDict
from logger import logger
from push import pushpluser, barkpusher
from PIL import Image

import resources

DEFAULT_CONFIG = {
    "username": "",
    "password": "",
    "qrlogin": True,
    "save_cookies": True,
    "proxies": {},
    "logLevel": "INFO",
    "qr_extra": {
        "show_in_terminal": None,
        "ensure_unicode": False
    },
    "pushplus": {
        "enable": False,
        "token": ""
    },
    "bark": {
        "enable": False,
        "token": "https://example.com/xxxxxxxxx"
    },
    "config_version": "1.3.0"
}

PROGRESS_RE = re.compile(r"^(?P<prefix>.*?) \|(?P<bar>[#\s]*)\|\s*(?P<percent>[\d.]+)%\s*(?P<suffix>.*)$")

ctypes.pythonapi.PyThreadState_SetAsyncExc.argtypes = (ctypes.c_long, ctypes.py_object)
ctypes.pythonapi.PyThreadState_SetAsyncExc.restype = ctypes.c_long

_helper = None
_helper_lock = threading.Lock()

_worker_lock = threading.Lock()
_worker = {"thread": None, "kind": None, "stop": threading.Event(), "force": threading.Event()}


# ---------------------------------------------------------------------------
# config.json / cookies.json / gui_state.json — mirrors main.py's own logic
# so the GUI reads/writes exactly what the CLI would, at the same paths.
# ---------------------------------------------------------------------------

def load_or_migrate_config():
    path = getConfigPath()
    if os.path.isfile(path):
        with open(path, "r+", encoding="utf-8") as f:
            config = ObjDict(json.load(f), default=None)
            if "config_version" not in config:
                config.config_version = "1.0.0"
            if versionCmp(config.config_version, DEFAULT_CONFIG["config_version"]) < 0:
                new = ObjDict(DEFAULT_CONFIG, default=None)
                if versionCmp(config.config_version, "1.0.1") < 0:
                    config.pop("qr_extra", None)
                if versionCmp(config.config_version, "1.3.0") < 0:
                    pushplus = config.pop("push", {})
                    new.pushplus.update(pushplus)
                config.pop("config_version", None)
                new.update(config)
                config = new
                f.seek(0)
                json.dump(config, f, indent=4)
                f.truncate()
        return config
    config = ObjDict(DEFAULT_CONFIG, default=None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
    return config


def _settings_view(config):
    return {
        "proxies": dict(config.proxies or {}),
        "logLevel": config.logLevel or "INFO",
        "pushplusEnable": bool(config.pushplus.enable),
        "pushplusToken": config.pushplus.token or "",
        "barkEnable": bool(config.bark.enable),
        "barkToken": config.bark.token or "",
    }


def get_settings():
    return _settings_view(load_or_migrate_config())


def save_settings(patch):
    config = load_or_migrate_config()
    if "proxies" in patch:
        config.proxies = patch["proxies"] or {}
    if "logLevel" in patch:
        config.logLevel = patch["logLevel"] or "INFO"
    if "pushplusEnable" in patch:
        config.pushplus.enable = bool(patch["pushplusEnable"])
    if "pushplusToken" in patch:
        config.pushplus.token = patch["pushplusToken"] or ""
    if "barkEnable" in patch:
        config.bark.enable = bool(patch["barkEnable"])
    if "barkToken" in patch:
        config.bark.token = patch["barkToken"] or ""
    with open(getConfigPath(), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    # Hot-apply onto the live Helper singleton (if it exists yet) instead of
    # rebuilding it, so an already-logged-in session/cookies/course cache
    # survives a settings change.
    if _helper is not None:
        _helper.proxies = config.proxies or {}
        pushplus_token = config.pushplus.enable and config.pushplus.token or ""
        bark_token = config.bark.enable and config.bark.token or ""
        _helper._pushplus = partial(pushpluser, token=pushplus_token) if pushplus_token else (lambda *a, **k: None)
        _helper._bark = partial(barkpusher, token=bark_token) if bark_token else (lambda *a, **k: None)
    logger.setLevel(config.logLevel or "WARNING")

    # speed/threshold/limit have no config.json field (see start_run) - they
    # live in gui_state.json instead, but are edited on the same settings page.
    state_patch = {k: patch[k] for k in ("speed", "threshold", "limit") if k in patch}
    if state_patch:
        save_gui_state(state_patch)
    return {"ok": True}


_GUI_STATE_DEFAULTS = {"speed": None, "threshold": None, "limit": 0, "lastCourseIds": []}


def _gui_state_path():
    return getRealPath("gui_state.json")


def load_gui_state():
    path = _gui_state_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                merged = dict(_GUI_STATE_DEFAULTS)
                merged.update(data)
                return merged
        except Exception:
            pass
    return dict(_GUI_STATE_DEFAULTS)


def save_gui_state(patch):
    state = load_gui_state()
    state.update(patch or {})
    with open(_gui_state_path(), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    return state


def _try_recover_cookies(helper, config):
    cookies_path = getRealPath("./cookies.json")
    if not (config.save_cookies and os.path.exists(cookies_path)):
        return False
    try:
        with open(cookies_path, "r", encoding="utf-8") as f:
            raw = f.read() or "{}"
            cookies = json.loads(raw)
        helper.cookies = cookies
        ls = helper.getZhidaoList()
        if ls:
            helper.getZhidaoContext(ls[-1].secret)
        ls = helper.getHikeList()
        if ls:
            helper.getHikeContext(ls[-1].courseId)
        return True
    except Exception:
        return False


def _save_cookies_to_disk(helper, config):
    if not config.save_cookies:
        return
    cookies_path = getRealPath("./cookies.json")
    with open(cookies_path, "w", encoding="utf-8") as f:
        json.dump(cookie_jar_to_list(helper.cookies), f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Helper lifecycle — one long-lived instance, hot-reloaded rather than rebuilt
# ---------------------------------------------------------------------------

def get_helper():
    global _helper
    with _helper_lock:
        if _helper is None:
            config = load_or_migrate_config()
            logger.setLevel(config.logLevel or "WARNING")
            pushplus_token = config.pushplus.enable and config.pushplus.token or ""
            bark_token = config.bark.enable and config.bark.token or ""
            _helper = Helper(proxies=config.proxies or {}, pushplus_token=pushplus_token, bark_token=bark_token)
        return _helper


def _to_data_uri(img_bytes):
    fmt = "png"
    try:
        with Image.open(io.BytesIO(img_bytes)) as im:
            fmt = (im.format or "PNG").lower()
    except Exception:
        pass
    b64 = base64.b64encode(img_bytes).decode("ascii")
    return "data:image/%s;base64,%s" % (fmt, b64)


@contextlib.contextmanager
def _capture_stdout(on_line):
    _stdout_tee.set_sink(on_line)
    try:
        yield
    finally:
        _stdout_tee.set_sink(None)


def _async_raise(tid, exctype):
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), ctypes.py_object(exctype))
    if res == 0:
        raise ValueError("invalid thread id")
    if res > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), None)
        raise SystemError("PyThreadState_SetAsyncExc affected more than one thread")


def _busy():
    t = _worker["thread"]
    return t is not None and t.is_alive()


def _begin_worker(kind, target):
    with _worker_lock:
        if _busy():
            return None
        _worker["stop"].clear()
        _worker["force"].clear()
        t = threading.Thread(target=target, daemon=True)
        _worker["thread"] = t
        _worker["kind"] = kind
        t.start()
        return t


def request_stop(force=False):
    t = _worker["thread"]
    if t is None or not t.is_alive():
        return {"ok": False, "error": "not_running"}
    if force:
        _worker["force"].set()
        try:
            _async_raise(t.ident, KeyboardInterrupt)
        except (ValueError, SystemError) as e:
            return {"ok": False, "error": str(e)}
    else:
        _worker["stop"].set()
    return {"ok": True}


def get_bootstrap():
    config = load_or_migrate_config()
    helper = get_helper()
    logged_in = bool(helper.cookies)
    if not logged_in:
        logged_in = _try_recover_cookies(helper, config)
    meta = {}
    try:
        meta = json.loads(resources.read_text("meta.json"))
    except Exception:
        pass
    return {
        "loggedIn": logged_in,
        "version": meta.get("version", ""),
        "settings": _settings_view(config),
        "state": load_gui_state(),
        "busy": _busy(),
        "busyKind": _worker["kind"] if _busy() else None,
    }


def get_courses(force_refresh=False):
    helper = get_helper()
    if force_refresh:
        helper.courses.zhidao = None
        helper.courses.hike = None
    out = []
    for c in helper.getZhidaoList() or []:
        out.append({"id": str(c.secret), "name": c.courseName, "type": "zhidao"})
    for c in helper.getHikeList() or []:
        out.append({"id": str(c.courseId), "name": c.courseName, "type": "hike"})
    return out


def start_login(push):
    def worker():
        try:
            helper = get_helper()
            config = load_or_migrate_config()

            def qr_cb(img_bytes):
                push("onLoginQr", _to_data_uri(img_bytes))
                push("onLoginStatus", "qr")

            def on_line(line):
                if "QR Scanned" in line:
                    push("onLoginStatus", "scanned")
                elif "One-time code" in line:
                    push("onLoginStatus", "confirming")
                elif "QR code expired" in line:
                    push("onLoginStatus", "expired")

            with _capture_stdout(on_line):
                helper.login(use_qr=True, qr_callback=qr_cb)
            _save_cookies_to_disk(helper, config)
            push("onLoginStatus", "success")
        except KeyboardInterrupt:
            push("onLoginStatus", "cancelled")
        except Exception as e:
            logger.exception(e)
            push("onLoginStatus", "failed:%s" % e)
        finally:
            push("onLoginFinished")

    t = _begin_worker("login", worker)
    if t is None:
        return {"ok": False, "error": "busy"}
    return {"ok": True}


def start_run(course_ids, options, push):
    course_ids = [str(c) for c in (course_ids or [])]
    options = options or {}
    save_gui_state({
        "speed": options.get("speed"),
        "threshold": options.get("threshold"),
        "limit": options.get("limit") or 0,
        "lastCourseIds": course_ids,
    })

    def worker():
        helper = get_helper()
        speed = options.get("speed") or None
        threshold = options.get("threshold") or None
        limit = options.get("limit") or 0
        # Replicates Helper.__init__'s own normalization; plain attribute
        # assignment would skip it since speed/end_thre/limit have no setters.
        helper.speed = speed and max(float(speed), 0.1)
        helper.end_thre = min(float(threshold) if threshold else 0.91, 1.0)
        helper.limit = abs(int(limit)) if limit else 0

        def on_line(line):
            m = PROGRESS_RE.match(line)
            if m:
                push("onRunProgress", {
                    "prefix": m.group("prefix"),
                    "percent": float(m.group("percent")),
                    "suffix": m.group("suffix"),
                })
            else:
                push("onRunLog", line)

        try:
            with _capture_stdout(on_line):
                for cid in course_ids:
                    if _worker["stop"].is_set():
                        push("onRunLog", "[已停止] 剩余课程未运行: %s" % cid)
                        break
                    push("onRunCourseStart", cid)
                    ok = True
                    try:
                        helper.studyCourse(cid)
                    except KeyboardInterrupt:
                        ok = False
                    except Exception as e:
                        logger.exception(e)
                        push("onRunLog", "[出错] %s: %s" % (cid, e))
                        ok = False
                    if _worker["force"].is_set():
                        ok = False
                    push("onRunCourseEnd", cid, ok)
                    if _worker["force"].is_set():
                        push("onRunLog", "[已强制停止]")
                        break
        finally:
            push("onRunFinished")

    t = _begin_worker("run", worker)
    if t is None:
        return {"ok": False, "error": "busy"}
    return {"ok": True}
