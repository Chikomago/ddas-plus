import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from common.task_models import TaskCallbacks
from common.task_runner import TaskRunner
from deedraw.task import TaskProcessor
from deedraw.page_state import saved_location, validate_option_name, SubmissionUnknown


class SubmissionTests(unittest.TestCase):
    def processor(self):
        p=TaskProcessor(TaskRunner(),TaskCallbacks(lambda _:None,lambda _:None,lambda _:None,confirm=lambda _:False))
        p.browser=SimpleNamespace(url='https://www.deepdraw.biz/authorized/merchant/setting/productFields?lastOperatedFieldId=7',run_js=Mock(return_value=True),ele=Mock(return_value=Mock()),get=Mock(),wait=SimpleNamespace(doc_loaded=lambda:None))
        return p

    def test_return_location_is_exact_not_substring_or_foreign_host(self):
        base='https://www.deepdraw.biz/authorized/merchant/setting/productFields'
        self.assertTrue(saved_location(base+'?lastOperatedFieldId=7','7'))
        for url in (base+'?lastOperatedFieldId=70',base+'?lastOperatedFieldId=7&lastOperatedFieldId=8',base.replace('www.deepdraw.biz','example.com')+'?lastOperatedFieldId=7'):
            self.assertFalse(saved_location(url,'7'))

    def test_page_name_rules_include_utf16_length(self):
        validate_option_name('蓝色')
        for name in ('','a'*21,'😀'*11,'<b>名称</b>'):
            with self.assertRaises(ValueError):validate_option_name(name)

    @patch('deedraw.task.form_feedback')
    def test_navigation_race_waits_for_redirect_without_resubmitting(self, feedback):
        import threading
        from DrissionPage.errors import ContextLostError

        p = self.processor()
        p.browser.url = 'https://www.deepdraw.biz/addOption'
        confirmation = SimpleNamespace(arm=Mock(), confirmed=threading.Event(), server_error=None)
        feedback.side_effect = ContextLostError()
        p._pause = lambda _: confirmation.confirmed.set()
        self.assertEqual(p.submit_and_verify('7', '蓝色', set(), timeout=1,
                                             confirmation=confirmation), [])
        p.browser.ele.return_value.click.assert_called_once()
        p.browser.get.assert_not_called()

    @patch('deedraw.task.read_options')
    def test_new_id_and_value_confirm_save(self,read):
        p=self.processor();read.return_value=[{'id':'new','value':'蓝色'}]
        self.assertEqual(p.submit_and_verify('7','蓝色',set(),timeout=.01),read.return_value)
        p.browser.ele.return_value.click.assert_called_once()

    @patch('deedraw.task.read_options')
    def test_late_save_recovered_without_second_click(self,read):
        p=self.processor();read.return_value=[{'id':'new','value':'蓝色'}]
        self.assertEqual(p.submit_and_verify('7','蓝色',set(),timeout=0),read.return_value)
        p.browser.ele.return_value.click.assert_called_once()
        p.browser.get.assert_called_once()

    @patch('deedraw.task.read_options')
    def test_old_option_does_not_prove_new_submission(self,read):
        p=self.processor();read.return_value=[{'id':'old','value':'蓝色'}]
        with self.assertRaises(SubmissionUnknown):p.submit_and_verify('7','蓝色',{'old'},timeout=0)
        p.browser.ele.return_value.click.assert_called_once()

    @patch('deedraw.task.form_feedback',return_value={'errors':['字段选项名称重复'],'dialog':'','confirm':False})
    def test_validation_error_is_not_hidden_by_generic_timeout(self,feedback):
        p=self.processor();p.browser.url='https://www.deepdraw.biz/addOption'
        with self.assertRaisesRegex(ValueError,'名称重复'):p.submit_and_verify('7','蓝色',set(),timeout=1)
        p.browser.get.assert_not_called()

    @patch('deedraw.task.form_feedback',return_value={'errors':[],'dialog':'内容包含违禁词  : 纯棉，是否继续提交？','confirm':True})
    def test_forbidden_prompt_is_confirmed_by_default_with_exact_dialog_scope(self,feedback):
        import threading
        p=self.processor();p.browser.url='https://www.deepdraw.biz/addOption'
        evidence=SimpleNamespace(arm=lambda *args:None,confirmed=threading.Event(), server_error=None)
        p.callbacks=TaskCallbacks(lambda _:None,lambda _:None,lambda _:None,confirm=Mock())
        def js(script,*args):
            if 'data-bb-handler="confirm"' in script:
                self.assertIn('.bootbox-confirm',script)
                self.assertEqual(args[0],feedback.return_value['dialog'])
                evidence.confirmed.set()
            return True
        p.browser.run_js=Mock(side_effect=js);p._pause=lambda _:None
        self.assertEqual(p.submit_and_verify('7','蓝色',set(),confirmation=evidence),[])
        p.callbacks.confirm.assert_not_called()

    @patch('deedraw.task.form_feedback',return_value={'errors':[],'dialog':'确认删除选项？','confirm':True})
    def test_unrelated_confirmation_is_never_auto_clicked(self,feedback):
        p=self.processor();p.browser.url='https://www.deepdraw.biz/addOption'
        with self.assertRaisesRegex(ValueError,'未识别的确认弹窗'):
            p.submit_and_verify('7','蓝色',set())
        self.assertEqual(p.browser.run_js.call_count,1)

    def test_empty_final_form_is_rejected_before_clicking_save(self):
        for option_id in ('', '42'):
            with self.subTest(option_id=option_id):
                p = self.processor()
                p.browser.run_js.return_value = False
                with self.assertRaisesRegex(ValueError, '手机端和PC端至少填写一个'):
                    p.submit_and_verify('7', '蓝色', set(), option_id=option_id)
                p.browser.ele.assert_not_called()

    def test_upload_uses_scoped_state_not_global_click_patch(self):
        import tempfile
        from pathlib import Path
        p=self.processor();p.settings={};p.browser.run_js.side_effect=[{'present':True,'path':'','other_path':''},None,{'present':True,'path':'new.png','other_path':'','src':'//upload.deepdraw.biz/productField/new.png','errors':[],'loaded':False}]
        with tempfile.TemporaryDirectory() as folder:
            image=Path(folder)/'a.png';image.write_bytes(b'fixture')
            self.assertTrue(p.pc_upload_file(str(image)))
        scripts=' '.join(call.args[0] for call in p.browser.run_js.call_args_list)
        self.assertNotIn('HTMLElement.prototype',scripts)
        self.assertIn('naturalWidth',scripts)
