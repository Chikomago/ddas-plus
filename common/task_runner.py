"""Thread-safe worker lifecycle; stop callbacks only fire after actual exit."""
import logging
import threading
from common.task_models import TaskResult


class TaskRunner:
    def __init__(self):
        self.running = False
        self.task_thread = None
        self.stop_event = threading.Event()
        self.last_result = None
        self._lock = threading.RLock()
        self._stopping = False

    def start_task_thread(self, target, args=(), daemon=True):
        with self._lock:
            if self.running or self._stopping:
                return False
            self.stop_event.clear()
            self.last_result = None
            self.running = True
            def run():
                try:
                    result = target(*args)
                    self.last_result = result if isinstance(result, TaskResult) else None
                except Exception as error:
                    logging.exception('后台任务执行失败')
                    self.last_result = TaskResult(False, str(error))
                finally:
                    with self._lock:
                        self.running = False
            self.task_thread = threading.Thread(target=run, daemon=daemon)
            self.task_thread.start()
            return True

    def request_stop(self):
        self.stop_event.set()

    def stop_task_thread(self, task=None, callback=None, timeout=2):
        with self._lock:
            if self._stopping:
                return
            thread = self.task_thread
            if not self.running:
                if callback:
                    callback()
                return
            self._stopping = True
            self.request_stop()
        def wait_for_stop():
            try:
                if task is not None:
                    stop = getattr(task, 'request_stop', None) or getattr(task, 'stop_task', None)
                    if stop:
                        stop()
                if thread is not None:
                    # A timeout is not task completion. Keep waiting in the background.
                    thread.join()
            except Exception:
                logging.exception('终止任务失败')
                if thread is not None:
                    thread.join()
            finally:
                with self._lock:
                    self._stopping = False
                if callback:
                    callback()
        threading.Thread(target=wait_for_stop, daemon=True).start()

    def is_running(self):
        with self._lock:
            return self.running or self._stopping
