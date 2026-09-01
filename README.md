# Work Todo V2

Windows 本地桌面待办工具，当前发布版本为 V2.2.0。数据保存在 Windows 的 `%LOCALAPPDATA%\WorkTodo`，不会随安装包升级被覆盖。

## 当前交互

- `Alt + E`、桌面快捷方式或双击桌面浮窗，均打开同一个编辑主窗。
- 编辑主窗默认显示“全部”，当天事项按时间排序；“未完成”仅作为筛选项。
- 有时间且固定钉住的待办同时按时间出现在当天事项中，并在最底部固定待办区域保留一份。
- 明日预览使用灰白色未启用状态；往下滚动可看最多两条普通明日事项和两条固定明日事项。
- 桌面浮窗支持 3–5 条倒计时待办和 0–4 条手动固定内容；超过七条时自动压缩卡片高度。
- 到期前十分钟和准点时，浮窗自动展开并以明显高亮提示；收起后才刷新已到期待办。
- 设置页支持喝水、吃饭、下班和加班提醒。喝水提醒包含两个固定时间和三个可选自定义时间。
- 鼓励语支持换行、自定义保存和删除；进入加班后浮窗顶部切换为加班状态。

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
