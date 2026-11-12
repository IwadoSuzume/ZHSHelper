"""GUI launcher used by 打开界面.bat.

Runs the real GUI (gui/app.py) and, if anything goes wrong before/while the
window is created, writes the traceback to 启动错误.log next to this file and
shows a small message box. Without this a pythonw launch fails silently.
"""
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "startup_error.log")


def fail(exc_text):
    try:
        with open(LOG, "w", encoding="utf-8") as f:
            f.write(exc_text)
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "ZHSHelper 启动失败。\n\n详情已写入：\n%s" % LOG,
            "ZHSHelper",
            0x10,
        )
    except Exception:
        pass


def main():
    try:
        os.remove(LOG)
    except OSError:
        pass
    sys.path.insert(0, os.path.join(ROOT, "gui"))
    try:
        import app
        app.main()
    except BaseException:
        fail(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
