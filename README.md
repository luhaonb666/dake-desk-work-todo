# 大可桌边 V3.6

Windows 本地桌面工作待办工具。程序显示名称为“大可桌边”；数据继续保存在 Windows 的 `%LOCALAPPDATA%\WorkTodo`，以确保旧版本升级后仍能读取已有待办，不会被安装包覆盖。

## 当前交互

- `Alt + E`、桌面快捷方式或双击桌面浮窗，均打开同一个编辑主窗。
- 编辑主窗默认显示“当日”，当天事项按时间排序；“未完成”可选择任意日期或查看全部未完成；“全部”可滚动查看所有历史事项。
- 有时间且固定钉住的待办同时按时间出现在当天事项中，并在最底部固定待办区域保留一份。
- 明日预览使用灰白色未启用状态；往下滚动可看最多两条普通明日事项和两条固定明日事项。
- 桌面浮窗支持 3–5 条倒计时待办和 0–4 条手动固定内容；超过七条时自动压缩卡片高度。
- 到期前十分钟和准点时，浮窗自动展开并以明显高亮提示；收起后才刷新已到期待办。
- 设置页支持喝水、用眼、吃饭、下班和加班提醒。喝水、用眼提醒各有两个固定时间和三个可选自定义时间。
- 鼓励语支持换行、自定义保存和删除；进入加班后浮窗顶部切换为加班状态。

## Windows 构建

首次验收时，先双击 `scripts\verify_windows.bat`，它会启动源码版并在关闭后保留错误文字。通过后再双击 `scripts\build_windows.bat`。构建脚本自动建立自己的 Python 虚拟环境、安装依赖并打包。

复制项目到 Windows 时不必复制 Mac 上的 `.venv` 文件夹；Windows 脚本会单独创建 `.venv-windows`。

- 首次如未安装 Inno Setup，会先生成 `dist\DaKeDesk.exe`。
- 安装 Inno Setup 后再运行同一脚本，生成 `release\DaKeDesk-Setup.exe`。

不要把 `data` 或数据库放在 exe 文件旁；应用自动使用 Windows 用户数据目录。

## 故障日志

程序异常日志位于 `%LOCALAPPDATA%\WorkTodo\work-todo.log`。

## GitHub 自动构建

项目已包含 `.github/workflows/build-windows.yml`。上传到**私有** GitHub 仓库后，打开仓库的 **Actions** 页面，选择 **Build Windows installer**，点击 **Run workflow**。等待绿色成功标记后，在该次运行页面的 **Artifacts** 下载 `DaKeDesk-Setup`，解压即可得到 `DaKeDesk-Setup.exe`。
