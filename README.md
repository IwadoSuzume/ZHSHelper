# ZHSHelper

智慧树网课刷课助手

![ZHSHelper](https://suzume.cloud/uploads/1790398952814-f46f7182f59b.png)

**下载**：[ZHSHelper-Setup.exe](https://suzume.cloud/downloads/ZHSHelper-Setup.exe) · 项目页：[suzume.cloud/projects/zhshelper](https://suzume.cloud/projects/zhshelper)

## 使用文档

一个帮助你节约时间的智慧树刷课程序

首次使用需要扫码登录，登录后会自动保存cookies自动登录

登录不同账号后课程列表需要手动刷新勾选再进行刷课

由于智慧树对于不同学校的监测力度不同，一般情况下不建议修改刷课倍数（最高不得超过8倍速）

刷课过程中会不定期弹出人机验证。检测到验证后，进度条下方会出现「打开验证页」按钮：程序会用内置浏览器打开智慧树登录中心，并自动填入设置里的账号和密码（仅保存在本机 config.json）；人机验证需要你手动完成，登录进入课程后会自动跳到触发验证的那门课。

界面提供浅色 / 深色两套主题，导航栏底部可切换；「日志」页可以查看本次会话的实时输出。

## 从源码构建

需要 Python 3、Inno Setup 6，步骤见 [BUILD-RELEASE.md](BUILD-RELEASE.md)

## 许可

MIT License © 2026 Sensu，见 [LICENSE](LICENSE)
