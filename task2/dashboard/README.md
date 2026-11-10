# 我的任务与成果看板

双击 [index.html](index.html) 即可离线打开。页面包含职责与成果对照、真实七天覆盖时间轴、265 个最终未覆盖点、按天查看的长三角窗口、下一步工作和成果文件入口，并支持汇报摘要复制/下载和打印。

这是 2026-11-10 验收结果的快照，依据 out/engineering_verified_20261110_final/。页面不会自动更改科学验收状态。

## 更新

修改 template.html 后，在 task2 目录运行：

~~~powershell
python dashboard/build_dashboard.py
~~~

生成器会校验输入与格点/窗口表的哈希，再把真实数据嵌入单一 HTML。仅打开页面不需要 Python、网络或额外依赖；从项目原有目录打开时，报告与场景的相对链接可用。

## 页面检查

check_dashboard.py 是可选的浏览器回归检查，需要单独安装 Playwright。默认使用本机 Edge，也可通过 --browser 指定 Chromium 系浏览器路径。

~~~powershell
python dashboard/check_dashboard.py
~~~

检查离线运行、真实覆盖数量、时间轴、职责切换、区域窗口、复制/下载、打印和手机布局。截图及检查记录写入被忽略的 out/dashboard_preview/，不会重新执行轨道仿真。
