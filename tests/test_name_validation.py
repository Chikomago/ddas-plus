import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlencode
from deedraw.save_confirmation import SaveConfirmation
from deedraw.task import TaskProcessor
from common.task_models import TaskCallbacks
from common.task_runner import TaskRunner


def packet(body=False,value='蓝色',field='7',status=200,failed=False):
    return SimpleNamespace(url=f'https://deepdraw.biz/authorized/merchant/setting/productField/{field}/ajaxCheckOptionValue',method='POST',request=SimpleNamespace(postData=urlencode({'id':'','value':value})),is_failed=failed,response=SimpleNamespace(status=status,body=body))


class NameValidationTests(unittest.TestCase):
    def evidence(self):
        evidence=SaveConfirmation();evidence.expect_name('7','蓝色');return evidence

    def test_only_boolean_results_are_authoritative(self):
        for body,want in [(True,True),(False,False),('true',True),('false',False),(' false\n',False),(0,None),('"false"',None),('<html>登录</html>',None),({'success':True},None)]:
            with self.subTest(body=body):
                evidence=self.evidence();evidence.on_packet(packet(body))
                self.assertTrue(evidence.name_done.is_set())
                self.assertIs(evidence.name_result,want)

    def test_other_field_or_value_does_not_reuse_previous_response(self):
        evidence=self.evidence()
        evidence.on_packet(packet(False,value='红色'));evidence.on_packet(packet(False,field='70'))
        self.assertFalse(evidence.name_done.is_set())

    def test_network_errors_are_unknown_not_false_or_true(self):
        for kwargs in ({'status':500},{'failed':True}):
            evidence=self.evidence();evidence.on_packet(packet(**kwargs))
            self.assertTrue(evidence.name_done.is_set());self.assertIsNone(evidence.name_result)

    def test_false_stops_before_upload_or_save(self):
        evidence=self.evidence();evidence.validation_monitoring=True
        processor=TaskProcessor(TaskRunner(),TaskCallbacks(lambda _:None,lambda _:None,lambda _:None))
        processor.browser=SimpleNamespace(run_js=lambda *_:evidence.on_packet(packet(False)))
        with self.assertRaisesRegex(ValueError,'接口返回false'):processor.check_option_name(evidence)

    def test_true_allows_next_stage(self):
        evidence=self.evidence();evidence.validation_monitoring=True
        processor=TaskProcessor(TaskRunner(),TaskCallbacks(lambda _:None,lambda _:None,lambda _:None))
        processor.browser=SimpleNamespace(run_js=lambda *_:evidence.on_packet(packet(True)))
        processor.check_option_name(evidence)

    def test_timeout_blocks_row_without_html_fallback(self):
        evidence=self.evidence();evidence.validation_monitoring=True
        processor=TaskProcessor(TaskRunner(),TaskCallbacks(lambda _:None,lambda _:None,lambda _:None))
        processor.browser=SimpleNamespace(run_js=Mock())
        with self.assertRaisesRegex(ValueError,'等待超时'):processor.check_option_name(evidence,timeout=0)
        self.assertIsNone(evidence.name_result)
