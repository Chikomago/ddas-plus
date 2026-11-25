"""Regression scenarios from the audit. No real website or credential store is touched."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import openpyxl

from common.config_loader import read_config
from common.config_schema import DEEDRAW_HEADERS
from common.task_models import DeedrawFieldRequest, DeedrawTaskRequest, PimTaskRequest, TaskCallbacks, TaskCancelled, TaskResult
from common.task_results import TaskReport, report_result
from common.task_runner import TaskRunner
from deedraw.task import TaskProcessor
from pim.task import PimTask


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.image = self.directory/'blue.png'
        self.image.write_bytes(b'fixture')
        self.path = self.directory/'data.xlsx'
        self.write_rows([['蓝色','蓝','蓝',str(self.image),str(self.image)]])
        self.errors, self.infos, self.warnings, self.statuses = [], [], [], []
        self.callbacks = TaskCallbacks(lambda _:None, self.statuses.append, self.errors.append,
            confirm=lambda _:False, info=self.infos.append, warning=self.warnings.append)

    def write_rows(self, rows, headers=DEEDRAW_HEADERS):
        book = openpyxl.Workbook()
        book.active.append(headers)
        for row in rows:
            book.active.append(row)
        book.save(self.path)
        book.close()

    def pim(self, **kwargs):
        options = dict(config_path=str(self.path),fill_pc_value=True,fill_mobile_value=False,
                       upload_pc_image=False,upload_mobile_image=False,preset_module=False,pixel_size='750')
        options.update(kwargs)
        return PimTask(PimTaskRequest(**options),self.callbacks,settings={'browser_settings':{'auto_close':False}})

    def deep(self, upload=False):
        processor = TaskProcessor(TaskRunner(), self.callbacks)
        row = DeedrawFieldRequest('color',str(self.path),upload,not upload,False,False)
        processor.settings = {'chrome_path':'/browser','browser_settings':{'auto_close':False}}
        processor.request = DeedrawTaskRequest([row],processor.settings)
        processor._configs = {id(row):read_config(str(self.path),options=(upload,not upload,False,False))}
        processor.browser = SimpleNamespace(get=lambda _:None, wait=SimpleNamespace(doc_loaded=lambda:None),url='',run_js=lambda script,*args: (True if 'Sync page validation' in script else [{'id':'new1','value':'蓝色'}] if 'fieldOptionItem' in script and 'lastOperatedFieldId=7' in processor.browser.url else [] if 'fieldOptionItem' in script else {'errors':[],'dialog':'','confirm':False}))
        processor.get_field_tabindex=lambda _:'7'
        processor.check_option_name=lambda _:None
        processor.check_forbidden_words=lambda _:[]
        processor.handle_value=lambda _:None
        processor.handle_pc_options=lambda _:None
        return processor,row


class ConfigurationTests(Fixture):
    def test_wrong_headers_are_rejected(self):
        self.write_rows([['blue']*5], ['a','b','c','d','e'])
        with self.assertRaisesRegex(ValueError,'配置文件应包含'):
            read_config(self.path)

    def test_only_selected_image_paths_are_validated(self):
        self.write_rows([['blue','blue','blue','missing.png','missing.png']])
        self.assertEqual(len(read_config(self.path,options=(False,True,False,False))),1)
        with self.assertRaisesRegex(ValueError,'图片不存在'):
            read_config(self.path,options=(True,False,False,False))

    def test_empty_rows_are_skipped_and_excel_row_numbers_are_kept(self):
        self.write_rows([[None]*5,['blue',0,0,'','']])
        self.assertEqual(read_config(self.path,options=(False,True,False,True)),[(3,('blue','0','0','',''))])

    def test_empty_config_is_not_success(self):
        self.write_rows([])
        with self.assertRaisesRegex(ValueError,'没有可执行的数据'):
            read_config(self.path)
        self.assertFalse(TaskReport(0,0,0,0).success)

    def test_relative_image_path_is_resolved_against_workbook(self):
        self.write_rows([['blue','blue','blue','blue.png','']])
        rows=read_config(self.path,options=(True,False,False,False))
        self.assertEqual(rows[0][1][3],str(self.image.resolve()))


class DeepdrawFailures(Fixture):
    def test_failed_upload_never_clicks_save_or_counts_success(self):
        processor,row=self.deep(upload=True)
        processor.browser.ele=Mock()
        processor.pc_upload_file=lambda _:False
        success,failed=[],[]
        processor.process_single_field(row,'color',success,failed)
        self.assertEqual(success,[])
        self.assertEqual(len(failed),1)
        self.assertIn('PC图片上传失败',failed[0][2])
        processor.browser.ele.assert_not_called()

    def test_name_api_false_skips_upload_and_submit_for_actual_row(self):
        from contextlib import nullcontext
        from urllib.parse import urlencode
        processor,row=self.deep(upload=True)
        del processor.check_option_name
        observer=[]
        def audit(*args,request_observer=None,**kwargs):
            observer.append(request_observer)
            request_observer.validation_monitoring=True
            return nullcontext()
        def js(script,*args):
            if 'fieldOptionItem' in script:
                return []
            observer[-1].on_packet(SimpleNamespace(
                url='https://deepdraw.biz/authorized/merchant/setting/productField/7/ajaxCheckOptionValue',
                method='POST',request=SimpleNamespace(postData=urlencode({'id':'','value':'蓝色'})),
                is_failed=False,response=SimpleNamespace(status=200,body=False)))
        processor.browser.run_js=js
        processor.pc_upload_file=Mock()
        processor.submit_and_verify=Mock()
        success,failed=[],[]
        with patch('deedraw.task.HttpAudit',side_effect=audit):
            processor.process_single_field(row,'color',success,failed)
        self.assertEqual(success,[])
        self.assertIn('接口返回false',failed[0][2])
        processor.pc_upload_file.assert_not_called()
        processor.submit_and_verify.assert_not_called()

    def test_skip_existing_is_reported_without_upload_or_submission(self):
        from dataclasses import replace

        processor, row = self.deep()
        row = replace(row, skip_existing=True)
        processor.request = DeedrawTaskRequest([row], processor.settings)
        processor._configs = {id(row): [(2, ('蓝色', '蓝', '', '', ''))]}
        processor.submit_and_verify = Mock()
        with patch('deedraw.task.read_options', return_value=[{'id': '42', 'value': '蓝色'}]), \
             self.assertLogs(level='INFO') as logs:
            result = processor.process_task()
        processor.submit_and_verify.assert_not_called()
        self.assertTrue(result.success)
        self.assertEqual((result.details['skipped'], result.details['pending'], result.details['failed']), (1, 0, 0))
        self.assertIn('跳过任务数：1', result.message)
        self.assertTrue(any('跳过已有选项：蓝色' in line for line in logs.output))

    def test_modify_only_renames_existing_and_skips_missing(self):
        from contextlib import nullcontext
        from dataclasses import replace

        processor, row = self.deep()
        row = replace(row, modify_only=True, rename_option=True, fill_pc_value=False)
        processor._configs = {id(row): [(2, ('蓝色', '', '', '', '', '海蓝')),
                                       (3, ('不存在', '', '', '', '', '新名'))]}
        edit_url = 'https://www.deepdraw.biz/authorized/merchant/setting/productField/7/42/editOption'
        processor.browser.get = Mock(side_effect=lambda url: setattr(processor.browser, 'url', url))
        processor.submit_and_verify = Mock()
        processor.handle_value = Mock()

        def audit(*args, request_observer, **kwargs):
            request_observer.save_monitoring = True
            return nullcontext()

        success, failed = [], []
        existing = [{'id': '42', 'value': '蓝色', 'edit_url': edit_url}]
        with patch('deedraw.task.HttpAudit', side_effect=audit), \
             patch('deedraw.task.read_options', return_value=existing), \
             patch('deedraw.task.reset_option_form', return_value=True) as reset:
            processor.process_single_field(row, 'color', success, failed)
        self.assertEqual(failed, [])
        self.assertEqual(success, [('color', 2, '蓝色 → 海蓝')])
        self.assertEqual(processor._modified_rows, success)
        self.assertEqual(len(processor._skipped_rows), 1)
        self.assertEqual([call.args[0] for call in processor.browser.get.call_args_list],
                         [processor.FIELD_SETTINGS_URL, edit_url])
        reset.assert_called_once_with(processor.browser, '蓝色', [True, False, False, False, False])
        processor.handle_value.assert_called_once_with('海蓝')
        self.assertEqual(processor.submit_and_verify.call_args.args[1], '海蓝')

    def test_modify_only_clears_blank_selected_pc_fields_and_saves(self):
        from contextlib import nullcontext
        from dataclasses import replace

        processor, row = self.deep()
        row = replace(row, modify_only=True, upload_pc_image=True)
        self.write_rows([['蓝色', ' ', '不修改', None, None]])
        with self.assertRaisesRegex(ValueError, '不能为空'):
            read_config(self.path, options=(True, True, False, False))

        edit_url = 'https://www.deepdraw.biz/authorized/merchant/setting/productField/7/42/editOption'
        processor.browser.get = Mock(side_effect=lambda url: setattr(processor.browser, 'url', url))
        processor.submit_and_verify = Mock()
        processor.handle_pc_options = Mock()
        processor.handle_mobile_options = Mock()
        processor.pc_upload_file = Mock()

        def audit(*args, request_observer, **kwargs):
            request_observer.save_monitoring = True
            return nullcontext()

        success, failed = [], []
        existing = [{'id': '42', 'value': '蓝色', 'edit_url': edit_url}]
        with patch('deedraw.task.HttpAudit', side_effect=audit), \
             patch('deedraw.task.read_options', return_value=existing), \
             patch('deedraw.task.reset_option_form', return_value=True) as reset:
            processor.process_single_field(row, 'color', success, failed)

        reset.assert_called_once_with(processor.browser, '蓝色', [False, True, False, True, False])
        processor.handle_mobile_options.assert_not_called()
        processor.handle_pc_options.assert_not_called()
        processor.pc_upload_file.assert_not_called()
        processor.submit_and_verify.assert_called_once()
        self.assertEqual(processor.submit_and_verify.call_args.kwargs['option_id'], '42')
        self.assertEqual(failed, [])
        self.assertEqual(success, [('color', 2, '蓝色')])

    def test_overwrite_uses_the_matched_edit_link_and_preserves_normal_add_for_new_names(self):
        from contextlib import nullcontext
        from dataclasses import replace

        processor, row = self.deep()
        original_rows = processor._configs[id(row)]
        row = replace(row, overwrite_existing=True)
        processor._configs[id(row)] = original_rows + [(3, ('新选项', '新值', '', '', ''))]
        edit_url = 'https://www.deepdraw.biz/authorized/merchant/setting/productField/7/42/editOption'
        add_url = edit_url.rsplit('/', 2)[0] + '/addOption'
        processor.browser.get = Mock(side_effect=lambda url: setattr(processor.browser, 'url', url))
        processor.submit_and_verify = Mock(return_value=[])
        processor.check_option_name = Mock()
        processor.handle_value = Mock()
        processor.handle_pc_options = Mock()
        def audit(*args, request_observer, **kwargs):
            request_observer.save_monitoring = True
            return nullcontext()
        success, failed = [], []
        second_edit_url = edit_url.replace('/42/', '/43/')
        existing = [
            {'id': '42', 'value': '蓝色', 'edit_url': edit_url},
            {'id': '43', 'value': '蓝色', 'edit_url': second_edit_url},
        ]
        with patch('deedraw.task.HttpAudit', side_effect=audit), \
             patch('deedraw.task.read_options', return_value=existing), \
             patch('deedraw.task.reset_option_form', return_value=True) as reset:
            processor.process_single_field(row, 'color', success, failed)
        self.assertEqual(failed, [])
        self.assertEqual(processor._overwritten_rows, [('color', 2, '蓝色')])
        self.assertEqual([value for _, _, value in success], ['蓝色', '新选项'])
        self.assertEqual([call.args[0] for call in processor.browser.get.call_args_list],
                         [processor.FIELD_SETTINGS_URL, edit_url, second_edit_url, add_url])
        self.assertEqual([call.args for call in reset.call_args_list], [(processor.browser, '蓝色')]*2)
        processor.check_option_name.assert_called_once()
        self.assertEqual(processor.submit_and_verify.call_args_list[0].kwargs['option_id'], '42')
        self.assertEqual(processor.submit_and_verify.call_args_list[1].kwargs['option_id'], '43')
        self.assertNotIn('option_id', processor.submit_and_verify.call_args_list[2].kwargs)

    def test_missing_field_accounts_for_all_affected_rows(self):
        processor,row=self.deep()
        processor.get_field_tabindex=lambda _:None
        result=processor.process_task()
        self.assertFalse(result.success)
        self.assertEqual(result.details['failed'],1)
        self.assertEqual(result.details['pending'],0)
        self.assertIn('未找到字段',result.message)

    def test_success_requires_saved_url_and_new_option_id(self):
        processor,row=self.deep()
        processor.browser.ele=lambda *a,**k:SimpleNamespace(click=lambda:setattr(processor.browser,'url','https://www.deepdraw.biz/authorized/merchant/setting/productFields?lastOperatedFieldId=7'))
        result=processor.process_task()
        self.assertTrue(result.success)
        self.assertEqual(result.details['succeeded'],1)

    def test_unknown_submission_leaves_rows_pending_and_stops_further_writes(self):
        from deedraw.page_state import SubmissionUnknown
        self.write_rows([['蓝色','蓝','','',''],['红色','红','','','']])
        processor,row=self.deep()
        processor.submit_and_verify=Mock(side_effect=SubmissionUnknown('保存结果未确认'))
        result=processor.process_task()
        self.assertFalse(result.success)
        self.assertEqual(result.details['succeeded'],0)
        self.assertEqual(result.details['failed'],0)
        self.assertEqual(result.details['pending'],2)
        self.assertEqual(len(result.details['uncertain_rows']),1)
        processor.submit_and_verify.assert_called_once()

    def test_duplicate_config_names_fail_before_browser_starts(self):
        self.write_rows([['蓝色','蓝','','',''],['蓝色','蓝','','','']])
        processor,_=self.deep()
        processor.initialize_browser=Mock()
        result=processor.run_task(processor.request)
        self.assertFalse(result.success)
        self.assertIn('重复选项名',result.message)
        processor.initialize_browser.assert_not_called()

    def test_stop_does_not_close_browser_from_stop_thread(self):
        processor,_=self.deep()
        processor.browser.quit=Mock()
        processor.request_stop()
        processor.browser.quit.assert_not_called()
        with self.assertRaises(TaskCancelled):
            processor._pause(30)

    def test_preflight_fails_before_browser_initialization(self):
        processor,_=self.deep()
        self.path.unlink()
        processor.initialize_browser=Mock()
        result=processor.run_task(processor.request)
        processor.initialize_browser.assert_not_called()
        self.assertFalse(result.success)
        self.assertEqual(len(self.errors),1)

    def test_terminal_success_is_emitted_once_without_export_prompt(self):
        processor,_=self.deep()
        processor.initialize_browser=lambda _:True
        processor.login=lambda:True
        processor.cleanup_browser=lambda:None
        processor.browser.ele=lambda *a,**k:SimpleNamespace(click=lambda:setattr(processor.browser,'url','https://www.deepdraw.biz/authorized/merchant/setting/productFields?lastOperatedFieldId=7'))
        prompts=[]
        processor.callbacks=TaskCallbacks(lambda _:None,self.statuses.append,self.errors.append,
            confirm=lambda text:prompts.append(text) or False,info=self.infos.append,warning=self.warnings.append)
        result=processor.run_task(processor.request)
        self.assertTrue(result.success)
        self.assertEqual(len(self.infos),1)
        self.assertIn('任务执行成功',self.infos[0])
        self.assertEqual(prompts,[])


class PimFailures(Fixture):
    def test_initialization_false_cannot_return_success(self):
        task=self.pim()
        task.initialize_chrome_driver=lambda:False
        result=task.run()
        self.assertFalse(result.success)
        self.assertEqual(len(self.infos),0)
        self.assertEqual(len(self.errors),1)
        self.assertEqual(self.statuses[-1],'执行失败')

    def test_missing_inputs_do_not_count_success(self):
        task=self.pim();task.page=SimpleNamespace(ele=lambda *a,**k:None)
        result=task.configure_fields(task.request)
        self.assertFalse(result.success)
        self.assertEqual(result.details['succeeded'],0)
        self.assertEqual(result.details['failed'],1)
        self.assertIn('输入框',result.message)

    def test_missing_save_button_is_an_explicit_failure(self):
        task=self.pim();element=Mock()
        task.page=SimpleNamespace(ele=lambda selector,**k:None if selector=='text:确 定' else element)
        result=task.configure_fields(task.request)
        self.assertFalse(result.success)
        self.assertIn('提交未确认',result.message)

    def test_missing_add_button_aborts_instead_of_writing_into_wrong_row(self):
        self.write_rows([['blue','blue','blue','',''],['red','red','red','','']])
        task=self.pim();selectors=[];element=Mock()
        def find(selector,**kwargs):
            selectors.append(selector)
            return element if selector.startswith('#ComponentType') else None
        task.page=SimpleNamespace(ele=find)
        result=task.configure_fields(task.request)
        self.assertFalse(result.success)
        self.assertEqual(result.details['failed'],2)
        self.assertNotIn('#ComponentType_name1',selectors)
        self.assertNotIn('text:确 定',selectors)

    def test_save_requires_observed_dialog_closure(self):
        task=self.pim();element=Mock()
        task.page=SimpleNamespace(ele=lambda *a,**k:element)
        with patch.object(task,'_wait',side_effect=RuntimeError('提交未确认')):
            result=task.configure_fields(task.request)
        self.assertFalse(result.success)
        self.assertIn('提交未确认',result.message)

    def test_confirmed_save_has_success_report_and_one_completion_popup(self):
        task=self.pim();element=Mock()
        task.page=SimpleNamespace(ele=lambda selector,**k:None if selector=='css:.ant-modal-title' else element)
        task.run_task_logic=lambda request:task.configure_fields(request)
        task.close_page=Mock()
        result=task.run()
        self.assertTrue(result.success)
        self.assertEqual(len(self.infos),1)
        self.assertIn('完成任务数：1',self.infos[0])
        task.close_page.assert_called_once_with(keep_open=True)

    def test_auto_close_setting_is_honored(self):
        task=self.pim();task.settings['browser_settings']['auto_close']=True
        task.page=Mock();task.close_page=Mock()
        task.run_task_logic=lambda _:TaskResult(True,'任务成功')
        task.run()
        task.close_page.assert_called_once_with(keep_open=False)

    def test_timeout_becomes_failure_not_success(self):
        task=self.pim();task.initialize_chrome_driver=lambda:True
        task.page=SimpleNamespace(get=lambda _:None)
        with patch.object(task,'_wait',side_effect=RuntimeError('等待超时')):
            result=task.run()
        self.assertFalse(result.success)
        self.assertIn('等待超时',self.errors[0])

    def test_cancellation_has_one_warning_and_no_success_popup(self):
        task=self.pim();task.stop_flag.set()
        task.run_task_logic=lambda _:task._check_stop()
        result=task.run()
        self.assertTrue(result.details['cancelled'])
        self.assertEqual(self.infos,[])
        self.assertEqual(len(self.warnings),1)

    def test_preset_confirmation_and_browser_choice_are_preserved(self):
        task=self.pim(preset_module=True,fill_pc_value=False)
        task._rows=read_config(self.path,preset=True)
        task.page=SimpleNamespace(get=lambda _:None,url='')
        task._wait=lambda *a,**k:None
        task._required=lambda *a,**k:Mock()
        prompts=[]
        def confirm(text):
            prompts.append(text)
            return len(prompts)==1
        task.callbacks=TaskCallbacks(lambda _:None,self.statuses.append,self.errors.append,confirm=confirm)
        result=task._run_preset(task.request)
        self.assertTrue(result.success)
        self.assertIn('已检测到预设模块页面',prompts[0])
        self.assertEqual(prompts[1],'操作完成。\n是否关闭浏览器？')
        self.assertFalse(task._close_override)


class LifecycleTests(unittest.TestCase):
    def test_stop_callback_never_enables_ui_before_worker_exits(self):
        runner=TaskRunner();done=threading.Event();callback=threading.Event()
        runner.start_task_thread(lambda:done.wait(2))
        runner.stop_task_thread(callback=callback.set,timeout=.001)
        self.assertFalse(callback.wait(.03))
        self.assertTrue(runner.is_running())
        self.assertFalse(runner.start_task_thread(lambda:None))
        done.set()
        self.assertTrue(callback.wait(1))
        self.assertFalse(runner.is_running())

    def test_runner_keeps_result_instead_of_discarding_it(self):
        runner=TaskRunner();result=TaskResult(False,'部分失败',{'succeeded':1})
        runner.start_task_thread(lambda:result)
        runner.task_thread.join(1)
        self.assertIs(runner.last_result,result)

    def test_report_cannot_claim_success_when_some_rows_were_never_processed(self):
        result=report_result(TaskReport(3,1,0,0))
        self.assertFalse(result.success)
        self.assertEqual(result.details['pending'],2)
