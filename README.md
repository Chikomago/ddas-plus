# DDAS PLUS

Sanka Python 插件。React 页签界面通过 pywebview 打开独立窗口，深绘和 PIM 业务仍由 Python / DrissionPage 执行。用户运行已打包插件不需要 Node.js。

## 本地运行

Python 3.10–3.12，开发构建前端需要 Node.js 22。

```sh
python3 -m pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
python3 main.py
```

Windows 使用 `python`。Windows 需要 Microsoft Edge WebView2 Runtime，macOS 使用系统 WKWebView。仅在有图形桌面的环境运行。`--debug` 开启 WebView 调试。

## 打包 Sanka 插件

先构建前端，再执行：

```sh
python3 -m unittest discover -s tests
python3 build_plugin.py
```

ZIP 保持 `plugin.json` 的 Python 运行时与 `main.py` 入口，包含 `frontend/dist`。不包含 Node.js、node_modules 或设计稿。云端插件源需与 ZIP 同步元数据。CI 会先构建 React，再测试、打包插件和桌面应用。

## 保留的交互

- 深绘：点击“开始任务”后打开浏览器，完成手动登录后按实际字段数自动并行，最多同时使用 5 个任务标签页。每个字段内逐行执行，超出上限的字段排队，同一字段的名称和编码合并到同一队列。
- 两端：选择 Excel、从图片目录生成配置、打开原文件、五列数据编辑、增删行、前三列前后缀批量修改。
- 原有 PIM 提示、校验、警告、业务确认、完成统计和深绘结果导出确认保留。确认框逐条显示，业务线程等待实际选择。
- Chrome 路径选择/测试/下载、日志/结果/配置目录、自动关闭和 PIM 图片宽度设置。
- 日志实时显示、清空、导出；任务终止后等待实际线程退出才允许再次运行或切换页。

可在 `frontend` 中运行 `npm run dev` 预览界面。执行真实任务请从 `main.py` 启动。

## 回退

旧 TTK 入口保留为 `main_tk.py`：

```sh
python3 main.py --legacy
```

该入口与 React 共用业务逻辑与用户配置。程序不再读取、填写或保存账号密码；已存在的账号文件和系统凭据不会被访问或删除。

浏览器使用本机安装的可见 Google Chrome，不下载或回退到 Chrome for Testing。独立的持久用户目录位于应用数据目录下 `browser-profile`，日常 Chrome 的个人配置不被占用；登录会话由 Chrome 自身维护。首次切换到此目录需要手动登录。深绘等待登录最多 10 分钟，期间可终止任务。登录后读取字段列表并分配任务标签页。任务停止会通知全部标签，工作线程退出后才允许再次启动。设置中的“测试”使用独立临时目录，不影响任务浏览器。

本次运行环境禁止写入原仓库 `.git`，故回滚 Git 仓库单独保存于 `.rollback/repository`，`before-react-migration` 为迁移前回滚点。可用以下命令查看：

```sh
git -C .rollback/repository log --oneline
```

原仓库中提交仍需在有 Git 写权限的终端操作。不要把 `.rollback` 或账号文件提交到远程。

## 审查修复

- 深绘/PIM 使用统一终态：成功、部分失败、失败、取消；只发送一次任务结果通知。
- 上传失败、控件缺失、字段跳过、初始化失败、提交未确认不会再计作成功。
- 执行前校验配置表头、必填项和所选图片；忽略完全空白行，保留源 Excel 行号。
- PIM 普通模式遵循浏览器自动关闭设置；预设模式保留原有继续执行和关闭浏览器确认。
- 等待可响应停止，浏览器只由工作线程清理；线程真正退出前不能开始下一次任务。
- 桥接延迟就绪/中断后自动重连；编辑器关闭时提示未保存修改。
- 已移除账号密码存储入口和 keyring 依赖，登录统一在浏览器中手动完成。

本地更新代码后先执行 `python3 -m pip install -r requirements.txt`，再运行 `python3 main.py`。

窗口使用原生窗体：macOS 保留原生三色按钮，仅隐藏标题文字并统一标题栏背景；右侧提供设置按钮和「更新」按钮，后者按版本列出更新内容并标记当前版本。运行任务时关闭窗口会保留终止提示。任务/设置操作栏固定在日志正上方，页面本身不纵向滚动。配置分页使用原生横向惯性滚动、吸附及鼠标跟手拖动。

性能：WebView 仅导出必要接口，不递归暴露原生窗口、线程或业务对象；状态获取在后台等待变化，空闲时约每秒一次心跳。确认与完成提示优先于日志发送。日志使用独立订阅和有界显示，不再让每条日志触发配置表单重绘。

深绘字段输入支持字段编码和页面显示名称，均精确匹配；同名字段需使用唯一编码。设置为独立的全窗口页面，左上角返回原工具主页，返回不丢失工具配置。文本框聚焦不再显示外部高亮边框。

关闭窗口时不再卡死：pywebview 的 JS→Python 桥调用运行在非守护线程，返回值需经 `evaluate_js()` 等待 UI 线程回调；窗口销毁时在途的长轮询可能永远等不到该回调，导致解释器退出被挂起。现在 `closing` 会唤醒在途轮询并先释放确认框，`poll` 返回 `closed` 标记让页面停止轮询，`pagehide` 也会停止轮询；`closed` 事件另装一个 1 秒守护看门狗，仅在进程未能正常退出时强制结束。

窗口右上角的「更新」按钮检查 GitHub Releases 上的正式版本，并提供前往下载的入口。更新记录按版本列出并标记当前版本，维护在 `frontend/src/changelog.js`，当前版本号由后端 `bootstrap` 返回。发布新版本时需同步 `plugin.json`、`main.py` 的 `APP_VERSION` 与该文件首条记录。
