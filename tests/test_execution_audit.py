import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from common.execution_audit import HttpAudit, response_summary, safe_url, forbidden_check_timeout
from common.log_policy import is_diagnostic_message


class AuditTests(unittest.TestCase):
    def test_response_redaction_and_bounds(self):
        body={'code':0,'token':'secret-value','data':{'password':'bad','items':[{'success':True}]},'message':'Bearer abc.def password=hunter email@example.com'}
        result=response_summary(body)
        for secret in ('secret-value','hunter','abc.def','email@example.com','bad'):
            self.assertNotIn(secret,result)
        self.assertEqual(json.loads(result)['code'],0)
        self.assertLessEqual(len(response_summary({'items':['x'*1000]*100})),4020)
        self.assertNotIn('private',safe_url('https://user:private@example.com/save?token=private#private'))

    def test_listener_collects_http_errors_and_stops(self):
        packet=SimpleNamespace(is_failed=False,method='POST',url='https://example.com/save?token=secret',response=SimpleNamespace(status=500,mimeType='application/json',body={'code':42,'token':'secret'},timing={'receiveHeadersEnd':12}))
        listener=Mock(listening=False)
        listener.wait.side_effect=[packet,False,False,False]
        audit=HttpAudit(SimpleNamespace(listen=listener),'第 2 行')
        # Exercise real consumer deterministically without a scheduler race.
        audit.listener=listener;audit.done.set()
        with self.assertLogs(level='INFO') as captured:audit._consume()
        self.assertEqual((audit.total,audit.failed),(1,1))
        self.assertNotIn('secret',' '.join(captured.output))
        self.assertTrue(is_diagnostic_message('[执行明细] 第 2 行完成'))

    def test_listener_failure_cannot_break_business(self):
        listener=Mock(listening=False);listener.start.side_effect=RuntimeError('unavailable')
        with HttpAudit(SimpleNamespace(listen=listener),'row'):
            pass
        listener.stop.assert_not_called()


class ForbiddenFallbackTests(unittest.TestCase):
    def test_only_transport_timeout_selects_html_fallback(self):
        url='https://deepdraw.biz/authorized/merchant/product/checkForbiddenWords'
        packet=SimpleNamespace(url=url,is_failed=True,fail_info=SimpleNamespace(errorText='net::ERR_TIMED_OUT'))
        self.assertTrue(forbidden_check_timeout(packet))
        packet.fail_info.errorText='net::ERR_ABORTED'
        self.assertFalse(forbidden_check_timeout(packet))
        packet.is_failed=False
        packet.response=SimpleNamespace(status=504)
        self.assertTrue(forbidden_check_timeout(packet))
        packet.response.status=200
        self.assertFalse(forbidden_check_timeout(packet))
        packet.url='https://deepdraw.biz/saveOrUpdateOption'
        packet.response.status=504
        self.assertFalse(forbidden_check_timeout(packet))

    def test_timeout_logs_fallback_without_interrupting_page_flow(self):
        packet=SimpleNamespace(url='https://deepdraw.biz/authorized/merchant/product/checkForbiddenWords',is_failed=True,method='POST',fail_info=SimpleNamespace(errorText='net::ERR_TIMED_OUT'))
        audit=HttpAudit(None,'测试行');audit.done.set()
        audit.listener=Mock();audit.listener.wait.side_effect=[packet,False]
        with self.assertLogs(level='INFO') as logs:audit._consume()
        self.assertIn('未通过预检不提交',' '.join(logs.output))
        self.assertEqual(audit.failed,1)
