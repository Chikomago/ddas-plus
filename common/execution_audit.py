"""Bounded, redacted business HTTP diagnostics, separate from success detection."""
import functools
import json
import logging
import re
import threading
import time
from urllib.parse import urlsplit, urlunsplit

SENSITIVE = re.compile(r'password|passwd|pwd|token|cookie|authorization|secret|session|credential|account|username|phone|email', re.I)


def sanitize(value, depth=0):
    if depth > 5:
        return "[嵌套内容省略]"
    if isinstance(value, dict):
        return {str(k): '[REDACTED]' if SENSITIVE.search(str(k)) else sanitize(v, depth+1) for k, v in list(value.items())[:30]}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, depth+1) for v in value[:30]]
    if isinstance(value, str):
        # Avoid reflecting arbitrary free text, HTML, credentials or personal data.
        text = re.sub(r'(?i)(bearer\s+)[\w.\-]+', r'\1[REDACTED]', value)
        text = re.sub(r'(?i)((?:password|passwd|pwd|token|cookie|authorization|secret|session)[\s:=]+)[^\s,;]+', r'\1[REDACTED]', text)
        text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[REDACTED]', text)
        text = re.sub(r'[A-Za-z0-9_=-]{32,}', '[REDACTED]', text)
        return text[:500]
    return value if value is None or isinstance(value, (bool, int, float)) else str(type(value).__name__)


def safe_url(url):
    parts = urlsplit(str(url))
    return urlunsplit((parts.scheme, parts.hostname or '', parts.path, '[REDACTED]' if parts.query else '', ''))


def forbidden_check_timeout(packet):
    """Transport timeout of the page's check only; never a business rejection."""
    if urlsplit(str(packet.url)).path != '/authorized/merchant/product/checkForbiddenWords':
        return False
    if packet.is_failed:
        failure = getattr(packet, 'fail_info', None)
        reason = str(getattr(failure, 'errorText', '') or '')
        return 'TIMED_OUT' in reason.upper() or 'TIMEOUT' in reason.upper()
    return packet.response.status in (408, 504)


def response_summary(body):
    if not isinstance(body, (dict, list)):
        return '[非 JSON 正文省略]'
    encoded = json.dumps(sanitize(body), ensure_ascii=False)
    return encoded[:4000] + ('…[正文截断]' if len(encoded) > 4000 else '')



class HttpAudit:
    def __init__(self, page, label, stats=None, request_observer=None):
        self.page, self.label = page, label
        self.stats = stats
        self.request_observer = request_observer
        self.started = time.monotonic()
        self.done = threading.Event()
        self.thread = None
        self.listener = None
        self.total = self.failed = self.omitted = 0
        self.success = True

    def __enter__(self):
        logging.info('[执行明细] %s 开始', self.label)
        try:
            self.listener = self.page.listen
            if self.listener.listening is True:
                self.listener = None
                logging.warning('[HTTP] %s 已有监听器，跳过以免干扰', self.label)
                return self
            self.listener.start(method=True, res_type=('XHR', 'Fetch', 'Document'))
            if self.request_observer is not None:
                # DrissionPage's completed-packet queue overwrites intermediate
                # redirects. Observe the raw redirectResponse before forwarding
                # the event to its existing listener handler.
                try:
                    original = self.listener._requestWillBeSent
                    def observe_request(**event):
                        try:
                            self.request_observer.observe(event)
                        except Exception:
                            logging.warning('[HTTP] 保存重定向解析失败，保留页面回查')
                        finally:
                            original(**event)
                    self.listener._driver.set_callback('Network.requestWillBeSent', observe_request)
                    if hasattr(self.request_observer, 'observe_response'):
                        original_response = self.listener._response_received

                        def observe_response(**event):
                            try:
                                self.request_observer.observe_response(event)
                            except Exception:
                                logging.warning('[HTTP] 保存响应解析失败')
                            finally:
                                original_response(**event)

                        self.listener._driver.set_callback('Network.responseReceived', observe_response)
                    if hasattr(self.request_observer, 'save_monitoring'):
                        self.request_observer.save_monitoring = True
                except Exception:
                    logging.warning('[HTTP] 当前浏览器库不支持重定向监听，保留页面回查')
            self.thread = threading.Thread(target=self._consume, daemon=True)
            self.thread.start()
            if self.request_observer is not None and hasattr(self.request_observer, 'validation_monitoring'):
                self.request_observer.validation_monitoring = True
        except Exception:
            self.listener = None
            logging.warning('[HTTP] %s 无法启用监听；业务继续执行', self.label)
        return self

    def _consume(self):
        while True:
            try:
                packet = self.listener.wait(timeout=.05, raise_err=False)
                if packet:
                    if self.request_observer is not None and hasattr(self.request_observer, 'on_packet'):
                        try:
                            self.request_observer.on_packet(packet)
                        except Exception:
                            logging.warning('[HTTP] 校验响应解析异常，保留HTML校验')
                    self.total += 1
                    if forbidden_check_timeout(packet):
                        logging.warning('[HTTP] %s 违禁词接口超时；以独立接口预检结果为准，未通过预检不提交', self.label)
                    failed = packet.is_failed or (packet.response.status or 0) >= 400
                    self.failed += bool(failed)
                    if self.total <= 300:
                        status = '网络失败' if packet.is_failed else packet.response.status
                        response = None if packet.is_failed else packet.response
                        mime = str(getattr(response, 'mimeType', '') or '')
                        body = '[网络失败]' if packet.is_failed else (response_summary(response.body) if 'json' in mime else '[非 JSON 正文省略]')
                        timing = getattr(response, 'timing', None) or {}
                        elapsed = timing.get('receiveHeadersEnd', -1) if isinstance(timing, dict) else -1
                        logging.info('[HTTP] %s | %s %s | HTTP %s | 响应头耗时 %s ms | %s', self.label,
                                     packet.method, safe_url(packet.url), status, elapsed, body)
                    else:
                        self.omitted += 1
                elif self.done.is_set():
                    return
            except Exception:
                logging.warning('[HTTP] %s 监听读取中断；不改变业务结果', self.label)
                return

    def __exit__(self, kind, error, trace):
        self.done.set()
        if self.thread:
            self.thread.join(timeout=1)
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                logging.warning('[HTTP] %s 监听清理失败', self.label)
        logging.info('[执行明细] %s | %s | 耗时 %.2fs | HTTP完成 %s，网络/HTTP错误 %s，超限省略 %s',
                     self.label, '失败或终止' if kind or not self.success else '完成',
                     time.monotonic()-self.started, self.total, self.failed, self.omitted)
        if self.stats is not None:
            self.stats['completed'] = self.stats.get('completed', 0)+self.total
            self.stats['errors'] = self.stats.get('errors', 0)+self.failed
            self.stats['omitted'] = self.stats.get('omitted', 0)+self.omitted
        if not self.total:
            logging.info('[HTTP] %s 本次未捕获已完成响应，不代表提交成功或失败', self.label)


def audit_http(attribute, label):
    def decorate(function):
        @functools.wraps(function)
        def wrapped(self, *args, **kwargs):
            stats = {}
            with HttpAudit(getattr(self, attribute, None), label, stats) as audit:
                result = function(self, *args, **kwargs)
                audit.success = getattr(result, 'success', True)
            if hasattr(result, 'details'):
                result.details['http'] = stats
            return result
        return wrapped
    return decorate
