"""Release build: dist\\ZHSHelper\\ and (with --installer) the setup exe.

    venv\\Scripts\\python gui\\build_release.py [--installer] [--skip-selftest]

Steps
  1. bundle   - the web UI (JS/CSS minified) and meta.json are zipped into a
                generated module, _bundle.py, so they travel inside the exe
                instead of sitting next to it as files (see resources.py).
  2. stage    - every project .py the GUI imports is run through
                python-minifier (docstrings/comments dropped, local names
                shortened) into gui\\build\\stage\\. Only these copies are
                packaged; the real sources are never touched.
  3. freeze   - PyInstaller one-folder build of the staged copies. The
                modules end up as bytecode inside the exe's archive.
  4. notices  - LICENSE.txt (MIT) and THIRD-PARTY-NOTICES.txt (the
                licence texts of every bundled package) are written into the
                build.
  5. selftest - a copy of the build is run with --selftest in a scratch
                folder (never in dist, so no config/logs end up in the build).
  6. installer - ISCC compiles installer\\ZHSHelper.iss.

What does NOT get packaged: main.py (the CLI), decrypt\\ (dev tooling),
config.json, cookies.json, gui_state.json, logs\\, execution.json, venv\\ and
everything else that isn't imported by the GUI.
"""
import argparse
import ast
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(HERE, "build")
STAGE = os.path.join(BUILD, "stage")
DIST = os.path.join(ROOT, "dist")
APP_DIR = os.path.join(DIST, "ZHSHelper")
NAME = "ZHSHelper"

sys.path.insert(0, HERE)
import resources  # noqa: E402

# project modules the GUI imports, relative to the project root
SOURCES = (
    "gui/app.py",
    "gui/backend.py",
    "gui/resources.py",
    "fucker.py",
    "utils.py",
    "ObjDict.py",
    "logger.py",
    "push.py",
    "sign.py",
    "zd_utils.py",
)

# packages whose licence texts go into THIRD-PARTY-NOTICES.txt even though no
# importable module of theirs maps back to a distribution name
EXTRA_DISTRIBUTIONS = ("pyinstaller",)


def step(title):
    print("\n== %s" % title, flush=True)


# --------------------------------------------------------------------- bundle

def minified_asset(name, data):
    if name.endswith(".js"):
        import rjsmin
        return rjsmin.jsmin(data.decode("utf-8")).encode("utf-8")
    if name.endswith(".css"):
        import rcssmin
        return rcssmin.cssmin(data.decode("utf-8")).encode("utf-8")
    if name.endswith(".json"):
        return json.dumps(json.loads(data), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return data


def build_bundle():
    step("bundle web UI + meta.json")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in resources.FILES:
            raw = resources.read(name)
            packed = minified_asset(name, raw)
            z.writestr(name, packed)
            print("  %-28s %7d -> %7d bytes" % (name, len(raw), len(packed)))
    resources.ui_html()  # fails here, not at the user's first launch, if index.html changed shape

    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    out = os.path.join(STAGE, "_bundle.py")
    with open(out, "w", encoding="ascii", newline="\n") as f:
        f.write("ARCHIVE = (\n")
        for i in range(0, len(encoded), 100):
            f.write('    "%s"\n' % encoded[i:i + 100])
        f.write(")\n")
    print("  wrote _bundle.py (%d KB)" % (os.path.getsize(out) // 1024))


# ---------------------------------------------------------------------- stage

def stage_sources():
    step("minify project sources into gui\\build\\stage")
    import python_minifier

    total_in = total_out = 0
    for rel in SOURCES:
        src_path = os.path.join(ROOT, rel)
        with open(src_path, encoding="utf-8") as f:
            source = f.read()
        out = python_minifier.minify(
            source,
            filename=rel,
            remove_literal_statements=True,  # docstrings (nothing reads __doc__)
            rename_locals=True,
            rename_globals=False,  # modules import names from each other / are patched from outside
            remove_asserts=False,
            remove_debug=False,
        )
        # the minified module must still parse and define the same public names
        before = _top_level_names(source)
        after = _top_level_names(out)
        if before - after:
            raise SystemExit("minifier dropped top-level names from %s: %s" % (rel, sorted(before - after)))
        compile(out, rel, "exec")
        dest = os.path.join(STAGE, os.path.basename(rel))
        with open(dest, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
        total_in += len(source.encode("utf-8"))
        total_out += len(out.encode("utf-8"))
        print("  %-20s %7d -> %7d bytes" % (rel, len(source.encode("utf-8")), len(out.encode("utf-8"))))
    print("  total %d -> %d bytes" % (total_in, total_out))


def _top_level_names(source):
    names = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return names


def write_version_file(version):
    parts = [int(p) for p in version.split(".")] + [0] * 4
    tup = tuple(parts[:4])
    text = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(t)r, prodvers=%(t)r, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('080404b0', [
      StringStruct('CompanyName', 'Suzume'),
      StringStruct('FileDescription', 'ZHSHelper'),
      StringStruct('FileVersion', %(v)r),
      StringStruct('InternalName', 'ZHSHelper'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 Suzume, MIT License'),
      StringStruct('OriginalFilename', 'ZHSHelper.exe'),
      StringStruct('ProductName', 'ZHSHelper'),
      StringStruct('ProductVersion', %(v)r)])]),
    VarFileInfo([VarStruct('Translation', [0x0804, 1200])])
  ]
)
""" % {"t": tup, "v": version}
    path = os.path.join(BUILD, "version_info.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


# --------------------------------------------------------------------- freeze

def freeze(version_file):
    step("PyInstaller one-folder build")
    # One folder rather than --onefile: a onefile exe unpacks itself to %TEMP%
    # on every launch, which is slower and trips antivirus heuristics more.
    cmd = [
        sys.executable, "-m", "PyInstaller", os.path.join(STAGE, "app.py"),
        "--name", NAME, "--onedir", "--windowed", "--noconfirm", "--clean",
        "--distpath", DIST, "--workpath", os.path.join(BUILD, "pyi"), "--specpath", BUILD,
        "--paths", STAGE,
        "--icon", os.path.join(HERE, "assets", "icon.ico"),
        "--version-file", version_file,
        "--hidden-import", "_bundle",
        # nothing the GUI uses; keeps stray dev packages from the venv out
        "--exclude-module", "tkinter", "--exclude-module", "pyzbar", "--exclude-module", "qrcode",
        "--exclude-module", "setuptools", "--exclude-module", "pkg_resources",
        "--exclude-module", "PyInstaller", "--exclude-module", "python_minifier",
        "--exclude-module", "rjsmin", "--exclude-module", "rcssmin",
    ]
    subprocess.run(cmd, check=True, cwd=BUILD)


# -------------------------------------------------------------------- notices

def bundled_distributions():
    """Distribution names of every third-party package that went into the
    build, worked out from the module archive and the collected files."""
    from importlib import metadata

    toc_dir = os.path.join(BUILD, "pyi", NAME)
    top = set()
    with open(os.path.join(toc_dir, "PYZ-00.toc"), encoding="utf-8") as f:
        pyz = ast.literal_eval(f.read())
    for entry in pyz[-1]:
        top.add(entry[0].split(".")[0])
    internal = os.path.join(APP_DIR, "_internal")
    for name in os.listdir(internal):
        top.add(name.split(".")[0])
    mapping = metadata.packages_distributions()
    dists = set()
    for t in top:
        for d in mapping.get(t, []):
            dists.add(d)
    dists.update(EXTRA_DISTRIBUTIONS)
    return sorted(dists, key=str.lower)


def write_notices():
    step("licence files")
    from importlib import metadata

    shutil.copyfile(os.path.join(ROOT, "LICENSE"), os.path.join(APP_DIR, "LICENSE.txt"))
    out = [
        "ZHSHelper - third-party notices",
        "=" * 72,
        "",
        "ZHSHelper - MIT License, Copyright (c) 2026 Suzume - see LICENSE.txt.",
        "",
        "This build also contains the components listed below. Each is",
        "redistributed under its own licence, reproduced in full.",
        "",
    ]

    py_license = os.path.join(sys.base_prefix, "LICENSE.txt")
    out += ["-" * 72, "Python %d.%d.%d - Python Software Foundation License" % sys.version_info[:3], "-" * 72, ""]
    with open(py_license, encoding="utf-8", errors="replace") as f:
        out.append(f.read().strip())
    out.append("")

    names = []
    for dist_name in bundled_distributions():
        try:
            dist = metadata.distribution(dist_name)
        except metadata.PackageNotFoundError:
            continue
        lic = dist.metadata.get("License-Expression") or dist.metadata.get("License") or ""
        if len(lic) > 80 or "\n" in lic:
            lic = ""
        if not lic:
            classifiers = [c.split("::")[-1].strip() for c in dist.metadata.get_all("Classifier") or [] if c.startswith("License ::")]
            lic = ", ".join(classifiers)
        files = [p for p in (dist.files or []) if _is_license_file(str(p))]
        out += ["-" * 72, "%s %s - %s" % (dist.metadata["Name"], dist.version, lic or "see below"),
                dist.metadata.get("Home-page") or _project_url(dist) or "", "-" * 72, ""]
        if files:
            for p in files:
                text = p.read_text(encoding="utf-8")
                if text:
                    out += ["[%s]" % p.name, text.strip(), ""]
        else:
            out += ["(no licence file shipped with the package; licence: %s)" % (lic or "unknown"), ""]
        names.append(dist.metadata["Name"])

    out += ["-" * 72, "Microsoft Edge WebView2 SDK (Microsoft.Web.WebView2.Core.dll,",
            "Microsoft.Web.WebView2.WinForms.dll, WebView2Loader.dll; shipped with pywebview)", "-" * 72, "",
            "Copyright (C) Microsoft Corporation. Redistributed under the Microsoft",
            "WebView2 SDK licence: https://www.nuget.org/packages/Microsoft.Web.WebView2/",
            "The WebView2 Runtime itself is not included; it is part of Windows 10/11",
            "or available from https://developer.microsoft.com/microsoft-edge/webview2/", ""]

    with open(os.path.join(APP_DIR, "THIRD-PARTY-NOTICES.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(out))
    print("  %d packages: %s" % (len(names), ", ".join(names)))


def _is_license_file(path):
    base = os.path.basename(path).upper()
    in_licenses_dir = "/licenses/" in path.replace("\\", "/").lower()
    return ".DIST-INFO" in path.upper() and (in_licenses_dir or base.startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS")))


def _project_url(dist):
    for entry in dist.metadata.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() in ("homepage", "home", "source", "repository", "source code"):
            return url.strip()
    return ""


# ------------------------------------------------------------------- selftest

def run_selftest():
    step("selftest (copy of the build, scratch folder)")
    scratch = tempfile.mkdtemp(prefix="zhs-selftest-")
    try:
        target = os.path.join(scratch, NAME)
        shutil.copytree(APP_DIR, target)
        exe = os.path.join(target, NAME + ".exe")
        proc = subprocess.run([exe, "--selftest"], timeout=180)
        with open(os.path.join(target, "selftest.json"), encoding="utf-8") as f:
            result = json.load(f)
        for name, r in result.items():
            if name.startswith("_"):
                continue
            print("  %-18s %s  %s" % (name, "ok  " if r["ok"] else "FAIL", str(r["detail"])[:90]))
        if proc.returncode != 0 or not result["_summary"]["ok"]:
            raise SystemExit("selftest failed (exit %s)" % proc.returncode)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def scan_build():
    """Nothing personal or project-source-like may be in the build folder."""
    step("scan build for stray files")
    bad = []
    for dirpath, _, filenames in os.walk(APP_DIR):
        for fn in filenames:
            low = fn.lower()
            if low in ("config.json", "cookies.json", "gui_state.json", "execution.json", "selftest.json") or low.endswith(".log"):
                bad.append(os.path.join(dirpath, fn))
    # project source text that must only exist as bytecode inside the exe
    needles = [b"class Fucker", b"def fuckCourse", b"window.__bridge", b"o6xpt3b#Qy$Z"]
    for dirpath, _, filenames in os.walk(APP_DIR):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            if os.path.getsize(p) > 64 * 1024 * 1024:
                continue
            with open(p, "rb") as f:
                data = f.read()
            for n in needles:
                if n in data:
                    bad.append("%s contains %r" % (p, n))
    if bad:
        raise SystemExit("build contains files that must not ship:\n  " + "\n  ".join(bad))
    count = sum(len(f) for _, _, f in os.walk(APP_DIR))
    size = sum(os.path.getsize(os.path.join(d, x)) for d, _, f in os.walk(APP_DIR) for x in f)
    print("  clean: %d files, %.1f MB" % (count, size / 1048576))


# ------------------------------------------------------------------ installer

def find_iscc():
    for p in (os.environ.get("ISCC", ""),
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
              r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
              r"C:\Program Files\Inno Setup 6\ISCC.exe"):
        if p and os.path.isfile(p):
            return p
    raise SystemExit("ISCC.exe (Inno Setup 6) not found - set ISCC=<path>")


def build_installer(version, test_build=False):
    step("Inno Setup installer%s" % (" (TestBuild)" if test_build else ""))
    cmd = [find_iscc(), "/Q", "/DAppVersion=" + version, "/DSrcDir=" + ROOT]
    if test_build:
        cmd.append("/DTestBuild")
    cmd.append(os.path.join(ROOT, "installer", "ZHSHelper.iss"))
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--installer", action="store_true", help="also compile the setup exe")
    ap.add_argument("--test-installer", action="store_true", help="also compile the throwaway ZHSHelperTest setup")
    ap.add_argument("--skip-selftest", action="store_true")
    args = ap.parse_args()

    version = json.loads(resources.read_text("meta.json"))["version"]
    print("ZHSHelper %s" % version)
    shutil.rmtree(STAGE, ignore_errors=True)
    os.makedirs(STAGE)

    build_bundle()
    stage_sources()
    freeze(write_version_file(version))
    write_notices()
    scan_build()
    if not args.skip_selftest:
        run_selftest()
    if args.installer:
        build_installer(version)
    if args.test_installer:
        build_installer(version, test_build=True)
    print("\nDone: %s" % APP_DIR)


if __name__ == "__main__":
    main()
