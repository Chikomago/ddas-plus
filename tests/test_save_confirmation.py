import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlencode
from deedraw.save_confirmation import SaveConfirmation
from deedraw.task import TaskProcessor
from deedraw.page_state import SubmissionUnknown
from common.task_models import TaskCallbacks
from common.task_runner import TaskRunner

URL='https://deepdraw.biz/authorized/merchant/setting/productField/39838/saveOrUpdateOption'
LOCATION='/authorized/merchant/setting/productFields?lastOperatedFieldId=39838'


def post(value='刚刚',field_url=URL,request_id='r1'):
    return {'requestId':request_id,'request':{'method':'POST','url':field_url,'postData':urlencode({'id':'','value':value})}}


def redirect(status=303,location=LOCATION,request_id='r1'):
    return {'requestId':request_id,'redirectResponse':{'url':URL,'status':status,'headers':{'Location':location}},'request':{'method':'GET','url':'https://deepdraw.biz'+LOCATION}}


class SaveConfirmationTests(unittest.TestCase):
    def test_success_capture_303_is_correlated_without_option_id(self):
        evidence=SaveConfirmation();evidence.arm('39838','刚刚')
        evidence.observe(post());self.assertFalse(evidence.confirmed.is_set())
        evidence.observe(redirect());self.assertTrue(evidence.confirmed.is_set())

    def test_edit_confirmation_requires_the_existing_option_id(self):
        evidence = SaveConfirmation()
        evidence.arm('39838', '刚刚', '215653')
        for option_id in ('', '215654', '215653'):
            event = post()
            event['request']['postData'] = urlencode({'id': option_id, 'value': '刚刚'})
            evidence.observe(event)
            evidence.observe(redirect())
            self.assertEqual(evidence.confirmed.is_set(), option_id == '215653')

    def test_wrong_request_value_field_status_and_location_cannot_confirm(self):
        for first,second in [
            (post(),redirect(request_id='different')),
            (post(value='其他选项'),redirect()),
            (post(field_url=URL.replace('39838','39839')),redirect()),
            (post(),redirect(status=200)),
            (post(),redirect(status=302)),
            (post(),redirect(location='/login')),
            (post(),redirect(location=LOCATION+'0')),
            (post(),redirect(location='https://example.com'+LOCATION)),
        ]:
            with self.subTest(first=first,second=second):
                evidence=SaveConfirmation();evidence.arm('39838','刚刚')
                evidence.observe(first);evidence.observe(second)
                self.assertFalse(evidence.confirmed.is_set())

    def test_unarmed_and_previous_row_events_do_not_confirm(self):
        evidence=SaveConfirmation();evidence.observe(post());evidence.observe(redirect())
        self.assertFalse(evidence.confirmed.is_set())
        evidence.arm('39838','刚刚');evidence.observe(post())
        evidence.arm('39838','下一行');evidence.observe(redirect())
        self.assertFalse(evidence.confirmed.is_set())

    def test_missing_post_body_is_unknown_not_assumed_success(self):
        evidence=SaveConfirmation();evidence.arm('39838','刚刚')
        event=post();event['request'].pop('postData')
        evidence.observe(event);evidence.observe(redirect())
        self.assertFalse(evidence.confirmed.is_set())

    def test_server_error_is_reported_without_resubmitting_or_waiting(self):
        evidence = SaveConfirmation()
        processor = TaskProcessor(TaskRunner(), TaskCallbacks(lambda _:None, lambda _:None, lambda _:None))

        def click():
            evidence.observe(post())
            evidence.observe_response({'requestId': 'other', 'response': {'url': URL, 'status': 500}})
            self.assertIsNone(evidence.server_error)
            evidence.observe_response({'requestId': 'r1', 'response': {'url': URL, 'status': 500}})

        button = Mock()
        button.click.side_effect = click
        processor.browser = Mock()
        processor.browser.run_js.return_value = True
        processor.browser.ele.return_value = button
        processor._pause = Mock()
        with self.assertRaisesRegex(SubmissionUnknown, 'HTTP 500'):
            processor.submit_and_verify('39838', '刚刚', set(), confirmation=evidence)
        button.click.assert_called_once()
        processor._pause.assert_not_called()
        processor.browser.get.assert_not_called()
        evidence.arm('39838', '下一行')
        self.assertIsNone(evidence.server_error)

    @patch('deedraw.task.read_options')
    def test_save_success_does_not_wait_for_delayed_html(self,read):
        evidence=SaveConfirmation()
        processor=TaskProcessor(TaskRunner(),TaskCallbacks(lambda _:None,lambda _:None,lambda _:None))
        def click():evidence.observe(post());evidence.observe(redirect())
        processor.browser=SimpleNamespace(run_js=Mock(return_value=True),ele=Mock(return_value=SimpleNamespace(click=click)),url='https://deepdraw.biz'+LOCATION)
        self.assertEqual(processor.submit_and_verify('39838','刚刚',set(),confirmation=evidence),[])
        read.assert_not_called()

class RedirectListenerAdapterTests(unittest.TestCase):
    @patch('common.execution_audit.threading.Thread')
    def test_raw_redirect_callback_preserves_original_listener_and_cleanup(self,thread):
        from common.execution_audit import HttpAudit
        evidence=SaveConfirmation();evidence.arm('39838','刚刚')
        listener=Mock(listening=False)
        with HttpAudit(SimpleNamespace(listen=listener),'row',request_observer=evidence):
            callbacks = dict(call.args for call in listener._driver.set_callback.call_args_list)
            callback = callbacks['Network.requestWillBeSent']
            self.assertIn('Network.responseReceived', callbacks)
            callback(**post());callback(**redirect())
            self.assertTrue(evidence.confirmed.is_set())
            self.assertEqual(listener._requestWillBeSent.call_count,2)
        listener.stop.assert_called_once()

    @patch('common.execution_audit.threading.Thread')
    def test_observer_error_does_not_break_existing_network_listener(self,thread):
        from common.execution_audit import HttpAudit
        listener=Mock(listening=False);observer=Mock();observer.observe.side_effect=ValueError('bad event')
        with HttpAudit(SimpleNamespace(listen=listener),'row',request_observer=observer):
            callback = dict(call.args for call in listener._driver.set_callback.call_args_list)['Network.requestWillBeSent']
            callback(**post())
            listener._requestWillBeSent.assert_called_once()
