"""Keep native window controls; only hide the macOS title text and separator."""
import logging
import sys


def _apply_macos_titlebar(native, appkit):
    native.setTitleVisibility_(appkit.NSWindowTitleHidden)
    native.setTitlebarAppearsTransparent_(True)
    native.setBackgroundColor_(appkit.NSColor.colorWithSRGBRed_green_blue_alpha_(247/255,247/255,249/255,1))
    for kind in (appkit.NSWindowCloseButton, appkit.NSWindowMiniaturizeButton, appkit.NSWindowZoomButton):
        button = native.standardWindowButton_(kind)
        if button is not None:
            button.setHidden_(False)
    if hasattr(native, 'setTitlebarSeparatorStyle_') and hasattr(appkit, 'NSTitlebarSeparatorStyleNone'):
        native.setTitlebarSeparatorStyle_(appkit.NSTitlebarSeparatorStyleNone)


def configure_native_titlebar(window):
    if sys.platform != 'darwin':
        return
    import AppKit
    from PyObjCTools import AppHelper
    def apply():
        try:
            if window.native is not None:
                _apply_macos_titlebar(window.native, AppKit)
        except Exception:
            # Leave the functional native window intact if cosmetic customization fails.
            logging.exception('设置原生窗口标题样式失败')
    AppHelper.callAfter(apply)
