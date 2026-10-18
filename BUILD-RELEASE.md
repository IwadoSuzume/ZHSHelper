# ZHSHelper 发布构建说明

## 一键构建

```bat
REM 首次：安装构建依赖（装进项目自带的 venv）
venv\Scripts\pip install -r requirements-build.txt

REM 构建 dist\ZHSHelper\ + 自检 + 安装包
gui\build_exe.bat
```

还需要 Inno Setup 6（默认找 `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`，别的位置用环境变量 `ISCC=<路径>` 指定）。

`gui\build_release.py` 的参数：

| 参数 | 作用 |
| --- | --- |
| （无） | 只构建 `dist\ZHSHelper\` 并自检 |
| `--installer` | 再编译 `installer\output\ZHSHelper-Setup.exe` |
| `--test-installer` | 再编译 `ZHSHelperTest-Setup.exe`（另一个 AppId，用来试安装/卸载，不碰正式安装） |
| `--skip-selftest` | 跳过自检（不建议） |

## 构建流程

1. **资源打包**：`gui/web` 的 HTML/CSS/JS（CSS、JS 先用 rcssmin/rjsmin 压缩）、logo 和 `meta.json` 打成 zip，生成 `gui/build/stage/_bundle.py`，编译进 exe。运行时整个界面以内存中的单个 HTML 加载，磁盘上没有 web 文件。
2. **代码混淆**：GUI 用到的所有项目 `.py`（`gui/app.py`、`backend.py`、`resources.py`、`fucker.py`、`utils.py`、`ObjDict.py`、`logger.py`、`push.py`、`sign.py`、`zd_utils.py`）用 python-minifier 处理到 `gui/build/stage/`：去掉注释和文档字符串、缩短局部变量名。只打包这些副本，源码不会被改动。
3. **冻结**：PyInstaller 单目录构建（`--onedir --windowed`）。项目代码只以字节码形式存在于 `ZHSHelper.exe` 内部的压缩归档里。
4. **许可证**：`LICENSE.txt`（MIT）和 `THIRD-PARTY-NOTICES.txt`（Python 及全部打包的第三方库的许可证全文）写入构建目录。
5. **检查**：扫描构建目录，确认没有 config/cookies/日志等个人文件，也没有明文项目源码。
6. **自检**：把构建复制到临时目录运行 `ZHSHelper.exe --selftest`（不在 dist 里运行，免得生成配置/日志）。结果写入 `selftest.json`。
7. **安装包**：ISCC 编译 `installer\ZHSHelper.iss`。

不打包的内容：`main.py`（命令行版）、`decrypt\`（开发工具）、`config.json`、`cookies.json`、`gui_state.json`、`logs\`、`venv\`、`gui/web/_selftest.html`、`run.bat` 等。

## 自检

```bat
ZHSHelper.exe --selftest            REM 离线：界面、数据目录、加解密/签名与原始源码结果一致、无散落源码、真实窗口加载
ZHSHelper.exe --selftest --online   REM 另外：向智慧树请求一个登录二维码后取消；未登录时跑一次不存在的课程验证运行流程；
                                    REM 有 cookies.json 时列出课程（只读，不会刷课或提交）
```

退出码 0 = 全部通过，详细结果在 exe 同目录的 `selftest.json`。

## 安装包行为

- 中文向导：许可协议 → 选择安装位置（默认 `D:\ZHSHelper`，没有 D 盘时为 `%LOCALAPPDATA%\Programs\ZHSHelper`）→ 桌面快捷方式（可选）→ 安装 → 可选立即运行。开始菜单快捷方式总会创建。
- 按用户安装，不需要管理员权限。程序把设置、登录状态和日志写在安装目录里，所以安装目录必须可写，选到不可写的位置（如 `C:\Program Files`）会提示换一个；静默安装时直接以错误码 7 退出。
- 运行环境检查（只检查并提示，不会偷偷安装任何东西）：Windows 10+ x64；.NET Framework 4.7.2+；Microsoft Edge WebView2 运行时。缺少时询问是否打开微软官方下载页。
- 升级：同一个 AppId，原地升级，保留用户数据，自动删除旧版散落的 `.py`/`meta.json`。
- 卸载：删除程序文件、快捷方式和卸载信息；询问是否同时删除用户数据（默认“否”）；静默卸载时保留用户数据。

## 保护强度说明

混淆 + 字节码只能防止直接看到/复制源码，挡不住有决心的逆向（Python 字节码可以被反编译，只是变量名和注释已丢失）。本机没有 C 编译器，所以没用 Cython/Nuitka；PyArmor 的试用版有限制且运行时容易被杀毒软件误报，也没用。
