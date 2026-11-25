"""Sanka Python entry: launch the React interface in its own desktop window."""
import logging
import sys
from pathlib import Path

APP_VERSION = "2.0.11"


def main():
    if "--legacy" in sys.argv:
        from main_tk import main as legacy_main
        legacy_main()
        return
    import webview
    from common.desktop_api import DesktopAPI
    from common.window_style import configure_native_titlebar
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    entry = root / "frontend" / "dist" / "index.html"
    if not entry.is_file():
        raise RuntimeError("缺少 React 构建文件，请先在 frontend 中执行 npm install 和 npm run build")
    api = DesktopAPI()
    api.configure_logging()
    window = webview.create_window(f"DDAS PLUS v{APP_VERSION}", str(entry), js_api=api._bridge(),
                                  width=664, height=820, min_size=(664, 820), resizable=True,
                                  frameless=False, easy_drag=False, background_color="#f7f7f9")
    api.window = window
    window.events.before_show += lambda: configure_native_titlebar(window)
    window.events.loaded += api.bind_image_drop
    window.events.closing += api.on_closing
    # closing is only a veto; closed fires once the window is really destroyed.
    # pywebview's JS bridge threads are non-daemon and can strand process exit,
    # so desktop_api installs a short watchdog there as a last resort.
    window.events.closed += api.on_closed
    logging.info("DDAS PLUS v%s 已启动", APP_VERSION)
    webview.start(debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()
