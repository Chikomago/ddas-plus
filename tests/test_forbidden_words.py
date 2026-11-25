import json
import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from deedraw.forbidden_words import request_forbidden_words,is_forbidden_prompt
from deedraw.task import TaskProcessor
from common.task_models import TaskCallbacks
from common.task_runner import TaskRunner


class ForbiddenWordsTests(unittest.TestCase):
    def test_empty_contents_need_no_request(self):
        browser=Mock()
        self.assertEqual(request_forbidden_words(browser,['','']),[])
        browser.run_js.assert_not_called()

    def test_uses_current_session_and_deduplicates_contents(self):
        browser=Mock();browser.run_js.return_value=[{'ok':True,'text':''}]
        self.assertEqual(request_forbidden_words(browser,['文字','文字']),[])
        script,contents=browser.run_js.call_args.args
        self.assertIsInstance(contents, str)
        self.assertEqual(json.loads(contents), ['文字'])
        self.assertIn('JSON.parse(arguments[0])', script)
        self.assertIn("credentials:'same-origin'",script)
        self.assertIn("redirect:'error'",script)
        self.assertEqual(browser.run_js.call_args.kwargs['timeout'],12)

    def test_edit_reset_serializes_selected_fields_for_the_browser(self):
        from deedraw.page_state import reset_option_form

        browser = Mock()
        for selection in (None, [True, False, True, False, True]):
            with self.subTest(selection=selection):
                reset_option_form(browser, '原选项', selection)
                script, name, selected = browser.run_js.call_args.args
                self.assertEqual(name, '原选项')
                self.assertIsInstance(selected, str)
                self.assertEqual(json.loads(selected), selection)
                self.assertIn('JSON.parse(arguments[1])', script)

    def test_nonempty_text_is_reported_as_hits(self):
        browser=Mock();browser.run_js.return_value=[{'ok':True,'text':'词甲、词乙'},{'ok':True,'text':'词甲、词乙'}]
        self.assertEqual(request_forbidden_words(browser,['PC文字','手机文字']),['词甲、词乙'])

    def test_error_incomplete_response_and_login_html_are_not_pass(self):
        browser=Mock()
        for result in (None,[],[{'ok':False}],[{'ok':True,'text':'<html>login</html>'}],[{'ok':True,'text':False}]):
            with self.subTest(result=result):
                browser.run_js.return_value=result
                with self.assertRaises(ValueError):request_forbidden_words(browser,['文字'])

    def test_only_specific_forbidden_word_prompt_is_recognized(self):
        self.assertTrue(is_forbidden_prompt('内容包含违禁词  : 纯棉，是否继续提交？'))
        self.assertFalse(is_forbidden_prompt('是否继续提交？'))
        self.assertFalse(is_forbidden_prompt('确认删除这些选项？'))

    def test_forbidden_hits_use_default_policy_without_user_popup(self):
        confirm=Mock(return_value=False)
        processor=TaskProcessor(TaskRunner(),TaskCallbacks(lambda _:None,lambda _:None,lambda _:None,confirm=confirm))
        processor.browser=Mock();processor.browser.run_js.return_value=[{'ok':True,'text':'纯棉'}]
        self.assertEqual(processor.check_forbidden_words(['内容']),['纯棉'])
        confirm.assert_not_called()
