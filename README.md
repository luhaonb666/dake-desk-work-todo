# Work Todo V2

Windows 本地桌面待办工具，当前发布版本为 V1.3。数据保存在 Windows 的 `%LOCALAPPDATA%\WorkTodo`，不会随安装包升级被覆盖。

## 当前交互

- `Alt + E`、桌面快捷方式或双击桌面浮窗，均打开同一个编辑主窗。
- 编辑主窗默认显示“全部”，当天事项按时间排序；“未完成”仅作为筛选项。
- 固定待办显示在当天列表最底部；往下滚动可看最多两条普通明日事项和两条固定明日事项。
- 桌面浮窗最多六项：前三项自动显示近期有时间的事项，后三项可在编辑主窗中指定事项或写鼓励文字。
- 到期前十分钟仅在编辑主窗内显示十秒提示；到期仍未完成的事项为淡红色。

## Windows 构建

首次验收时，先双击 `scripts\verify_windows.bat`，它会启动源码版并在关闭后保留错误文字。通过后再双击 `scripts\build_windows.bat`。构建脚本自动建立自己的 Python 虚拟环境、安装依赖并打包。

复制项目到 Windows 时不必复制 Mac 上的 `.venv` 文件夹；Windows 脚本会单独创建 `.venv-windows`。

- 首次如未安装 Inno Setup，会先生成 `dist\WorkTodo.exe`。
- 安装 Inno Setup 后再运行同一脚本，生成 `release\WorkTodo-Setup.exe`。

不要把 `data` 或数据库放在 exe 文件旁；应用自动使用 Windows 用户数据目录。

## 故障日志

程序异常日志位于 `%LOCALAPPDATA%\WorkTodo\work-todo.log`。

## GitHub 自动构建

项目已包含 `.github/workflows/build-windows.yml`。上传到**私有** GitHub 仓库后，打开仓库的 **Actions** 页面，选择 **Build Windows installer**，点击 **Run workflow**。等待绿色成功标记后，在该次运行页面的 **Artifacts** 下载 `WorkTodo-Setup`，解压即可得到 `WorkTodo-Setup.exe`。
