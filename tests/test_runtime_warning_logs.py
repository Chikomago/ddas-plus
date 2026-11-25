import logging
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from common.desktop_api import DesktopAPI, BridgeLogHandler
from common.task_models import TaskCallbacks
from common.task_runner import TaskRunner
from deedraw.task import TaskProcessor


class RuntimeWarningLogTests(unittest.TestCase):
    def setUp(self):
        self.api=DesktopAPI(SimpleNamespace(settings={}))
        self.handler=BridgeLogHandler(self.api)
        root=logging.getLogger();old_level=root.level
        root.setLevel(logging.INFO);root.addHandler(self.handler)
        self.addCleanup(root.setLevel,old_level)
        self.addCleanup(root.removeHandler,self.handler)
        self.processor=TaskProcessor(TaskRunner(),TaskCallbacks(lambda _:None,lambda _:None,lambda _:None))
        self.processor._current_row=('面料',4)
        self.processor.browser=Mock()

    def test_forbidden_hit_and_default_action_reach_runtime_log(self):
        self.processor.browser.run_js.return_value=[{'ok':True,'text':'纯棉'}]
        self.processor.check_forbidden_words(['测试文案'])
        events=self.api.poll()['value']['events']
        self.assertTrue(any(e['kind']=='log' and e['level']=='warning' and '纯棉' in e['text'] and '字段 面料 第 4 行' in e['text'] for e in events))
        self.assertTrue(any('默认策略继续' in e.get('text','') for e in events))
        self.assertIn('纯棉','\n'.join(self.api._log_text))

    def test_validation_error_reaches_runtime_log_with_row(self):
        self.processor.browser.run_js.return_value=[{'ok':False}]
        with self.assertRaises(ValueError):self.processor.check_forbidden_words(['测试文案'])
        logs=self.api.poll()['value']['events']
        self.assertTrue(any('字段 面料 第 4 行' in e.get('text','') and '跳过该行' in e.get('text','') for e in logs))
