import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from common.task_models import TaskCallbacks,TaskCancelled
from common.task_runner import TaskRunner
from deedraw.task import TaskProcessor
from common.browser import create_browser


class ManualLoginTests(unittest.TestCase):
    def setUp(self):
        self.status=[]
        self.processor=TaskProcessor(TaskRunner(),TaskCallbacks(lambda _:None,self.status.append,lambda _:None))
        self.browser=SimpleNamespace(url='https://www.deepdraw.biz/login',get=Mock(),wait=SimpleNamespace(doc_loaded=lambda:None))
        self.processor.browser=self.browser
        self.processor.open_field_settings=Mock(return_value=True)

    def test_manual_login_continues_after_authenticated_url(self):
        def user_login(_):
            self.browser.url='https://www.deepdraw.biz/authorized/merchant/home'
        self.processor._pause=user_login
        self.assertTrue(self.processor.login())
        self.assertIn('请在浏览器中登录深绘，登录后自动继续',self.status)
        self.processor.open_field_settings.assert_called_once()
        self.assertFalse(hasattr(self.processor,'request'))

    def test_existing_cookie_skips_login_wait(self):
        self.browser.url='https://www.deepdraw.biz/authorized/merchant/home'
        self.processor._pause=Mock()
        self.assertTrue(self.processor.login())
        self.processor._pause.assert_not_called()

    def test_manual_login_can_be_stopped_immediately(self):
        def stop(_):
            self.processor.request_stop()
            self.processor._check_stop()
        self.processor._pause=stop
        with self.assertRaises(TaskCancelled):
            self.processor.login()
        self.processor.open_field_settings.assert_not_called()

    def test_timeout_reports_failure_instead_of_success(self):
        self.assertFalse(self.processor.login(timeout=0))
        self.assertIn('等待登录超时',self.processor._login_error)
        self.processor.open_field_settings.assert_not_called()

    def test_credentials_are_absent_from_bridge_and_request_contract(self):
        from common.desktop_api import DesktopAPI
        from common.task_models import DeedrawTaskRequest
        self.assertFalse(hasattr(DesktopAPI,'save_credentials'))
        self.assertFalse(hasattr(DesktopAPI,'load_credentials'))
        self.assertNotIn('username',DeedrawTaskRequest.__dataclass_fields__)
        self.assertNotIn('password',DeedrawTaskRequest.__dataclass_fields__)
        root=Path(__file__).resolve().parent.parent
        source=(root/'frontend/src/main.jsx').read_text()
        for text in ['type="password"','save_credentials','load_credentials','setPassword']:
            self.assertNotIn(text,source)


class BrowserLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.chrome=self.root/'Google Chrome';self.chrome.touch()

    def test_installed_visible_chrome_uses_persistent_profile(self):
        with patch('common.browser.ChromiumOptions') as options,patch('common.browser.ChromiumPage') as page,patch('common.browser.app_data_dir',return_value=self.root):
            create_browser(str(self.chrome))
            options.return_value.set_browser_path.assert_called_once_with(str(self.chrome))
            options.return_value.headless.assert_called_once_with(False)
            options.return_value.set_user_data_path.assert_called_once_with(str(self.root/'browser-profile'))
            options.return_value.set_local_port.assert_called_once_with(19333)
            options.return_value.auto_port.assert_not_called()
            options.return_value.set_pref.assert_not_called()
            page.assert_called_once()

    def test_missing_chrome_never_launches_a_fallback_testing_browser(self):
        with patch('common.browser.ChromiumPage') as page:
            with self.assertRaisesRegex(ValueError,'未找到已安装'):
                create_browser(str(self.root/'missing'))
            page.assert_not_called()

    def test_testing_distribution_is_rejected(self):
        path=self.root/'Google Chrome for Testing';path.touch()
        with patch('common.browser.ChromiumPage') as page:
            with self.assertRaisesRegex(ValueError,'Chrome for Testing'):
                create_browser(str(path))
            page.assert_not_called()

    def test_browser_check_does_not_use_task_profile_or_port(self):
        with patch('common.browser.ChromiumOptions') as options,patch('common.browser.ChromiumPage'):
            create_browser(str(self.chrome),auto_port=True)
            options.return_value.auto_port.assert_called_once_with(True)
            options.return_value.set_user_data_path.assert_not_called()
            options.return_value.set_local_port.assert_not_called()
