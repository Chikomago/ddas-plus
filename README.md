# DDAS PLUS

[![Build and Release](https://github.com/Chikomago/ddas-plus/actions/workflows/build.yml/badge.svg)](https://github.com/Chikomago/ddas-plus/actions/workflows/build.yml)

DDAS PLUS 将深绘批量字段配置与 PIM CAS 自动化整合到同一个 Python/Tkinter/ttk 窗口中。

## 功能

- 使用统一窗口尺寸、顶部导航和单一 Tk 主循环。
- 启动页提供“深绘”和“PIM”两个 ttk 页面入口。
- 深绘保留动态增加、删除字段以及每个字段独立配置数据的能力。
- PIM 支持生成配置文件、填写 PC/移动值及上传图片。
- 两个页面共用配置编辑器、Chrome 设置、日志窗口和 `ddas_plus.log` 文件。
- 配置生成器和后台任务运行器由深绘与 PIM 共用。
- PIM 代码已包含在插件内，不依赖相邻的外部项目目录。

## Sanka 安装

将本目录按标准 ZIP 格式打包，确保 ZIP 根目录包含 `plugin.json`、`main.py`、`requirements.txt` 及全部 Python 模块。Sanka 安装时会创建 Python 虚拟环境并安装依赖。

推荐使用白名单打包器，避免把本地配置、日志和缓存写入插件：

```bash
python build_plugin.py
```

输出文件名会根据 `plugin.json` 版本生成。`requirements-build.txt` 仅用于制作独立桌面程序，不会安装到 Sanka 插件环境。

## 直接运行

安装 `requirements.txt` 中的依赖后运行：

```bash
python main.py
```

## 跨平台构建

GitHub Actions 会在 macOS 和 Windows 上分别运行测试并生成独立桌面程序。推送 `v*` 标签时，工作流会同时发布：

- `DDAS-PLUS-macOS.zip`
- `DDAS-PLUS.exe`（Windows 单文件程序）
- `ddas-plus-plugin.zip`（Sanka 插件）
