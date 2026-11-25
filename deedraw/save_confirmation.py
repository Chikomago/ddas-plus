"""Correlate a form POST with its observed 303 redirect, for the expected option and operation."""
import logging
import json
import threading
from urllib.parse import urlsplit, urljoin, parse_qs
from deedraw.page_state import saved_location


class SaveConfirmation:
    def __init__(self):
        self._lock = threading.Lock()
        self.confirmed = threading.Event()
        self.server_error = None
        self._expected = None
        self._requests = {}
        self.validation_monitoring = False
        self.save_monitoring = False
        self.name_done = threading.Event()
        self.name_result = None
        self._name_expected = None

    def expect_name(self, field_id, value):
        with self._lock:
            self._name_expected = (str(field_id), str(value))
            self.name_result = None
            self.name_done.clear()

    def on_packet(self, packet):
        with self._lock:
            if self._name_expected is None:
                return
            field_id, value = self._name_expected
            parts = urlsplit(str(packet.url))
            if (parts.scheme != 'https' or parts.hostname not in ('deepdraw.biz','www.deepdraw.biz')
                    or parts.path != f'/authorized/merchant/setting/productField/{field_id}/ajaxCheckOptionValue'
                    or packet.method != 'POST'):
                return
            data = packet.request.postData
            if isinstance(data, str):
                data = parse_qs(data, keep_blank_values=True)
            elif isinstance(data, dict):
                data = {k: v if isinstance(v,list) else [str(v)] for k,v in data.items()}
            else:
                return
            if data.get('value') != [value] or data.get('id') != ['']:
                return
            result = None
            if not packet.is_failed and packet.response.status == 200:
                body = packet.response.body
                if isinstance(body, str):
                    try:
                        body = json.loads(body.strip())
                    except (ValueError, TypeError):
                        body = None
                if type(body) is bool:
                    result = body
            self.name_result = result
            self.name_done.set()

    def arm(self, field_id, value, option_id=""):
        with self._lock:
            self.confirmed.clear()
            self.server_error = None
            self._requests.clear()
            self._expected = (str(field_id), str(value), str(option_id))

    def observe_response(self, event):
        response = event.get('response') or {}
        status = response.get('status')
        if not isinstance(status, int) or not 500 <= status < 600:
            return
        with self._lock:
            request_url = self._requests.get(event.get('requestId'))
            if request_url and response.get('url') == request_url:
                self.server_error = status

    def observe(self, event):
        with self._lock:
            if self._expected is None:
                return
            field_id, value, option_id = self._expected
            request_id = event.get('requestId')
            previous = self._requests.pop(request_id, None)
            redirect = event.get('redirectResponse') or {}
            if previous and redirect.get('url') == previous and redirect.get('status') == 303:
                headers = {str(k).lower(): str(v) for k,v in redirect.get('headers', {}).items()}
                location = urljoin(previous, headers.get('location', ''))
                if headers.get('location') and saved_location(location, field_id):
                    self.confirmed.set()
                    logging.info('[逐行结果] 字段 %s 保存POST返回303，Location已匹配当前字段（%s）', field_id, '编辑' if option_id else '新增')
            request = event.get('request') or {}
            parts = urlsplit(request.get('url', ''))
            if (request_id and request.get('method') == 'POST' and parts.scheme == 'https'
                    and parts.hostname in ('deepdraw.biz','www.deepdraw.biz')
                    and parts.path == f'/authorized/merchant/setting/productField/{field_id}/saveOrUpdateOption'):
                data = parse_qs(request.get('postData', ''), keep_blank_values=True)
                if data.get('value') == [value] and data.get('id') == [option_id]:
                    self._requests[request_id] = request['url']
