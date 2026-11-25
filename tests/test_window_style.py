import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from common.window_style import _apply_macos_titlebar,configure_native_titlebar


class WindowStyleTests(unittest.TestCase):
    def test_native_traffic_lights_stay_visible_while_title_text_is_hidden(self):
        native=Mock()
        appkit=SimpleNamespace(NSWindowTitleHidden=1,NSWindowCloseButton=0,
            NSWindowMiniaturizeButton=1,NSWindowZoomButton=2,NSColor=Mock(),NSTitlebarSeparatorStyleNone=0)
        buttons=[Mock(),Mock(),Mock()]
        native.standardWindowButton_.side_effect=buttons
        _apply_macos_titlebar(native,appkit)
        native.setTitleVisibility_.assert_called_once_with(1)
        native.setTitlebarAppearsTransparent_.assert_called_once_with(True)
        for button in buttons:button.setHidden_.assert_called_once_with(False)
        native.setStyleMask_.assert_not_called()

    def test_non_mac_platform_keeps_its_native_window(self):
        window=Mock()
        with patch('common.window_style.sys.platform','win32'):
            configure_native_titlebar(window)
        self.assertEqual(window.mock_calls,[])
