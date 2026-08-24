"""Shared background task lifecycle for Deedraw and PIM."""

import logging
import threading


class TaskRunner:
    def __init__(self):
        self.running = False
        self.task_thread = None
        self.stop_event = threading.Event()

    def start_task_thread(self, target, args=(), daemon=True):
        if self.running:
            return False
        self.stop_event.clear()

        def run():
            try:
                target(*args)
            except Exception:
                logging.exception("后台任务执行失败")
            finally:
                self.running = False

        self.running = True
        self.task_thread = threading.Thread(target=run, daemon=daemon)
        self.task_thread.start()
        return True

    def request_stop(self):
        self.stop_event.set()

    def stop_task_thread(self, task=None, callback=None, timeout=2):
        """统一终止生命周期：发信号、通知任务释放资源、等待线程退出。"""
        if not self.running:
            if callback:
                callback()
            return
        self.request_stop()

        def wait_for_stop():
            if task is not None:
                stop = getattr(task, "request_stop", None) or getattr(task, "stop_task", None)
                if stop:
                    stop()
            if self.task_thread:
                self.task_thread.join(timeout=timeout)
            if callback:
                callback()

        threading.Thread(target=wait_for_stop, daemon=True).start()

    def is_running(self):
        return self.running and self.task_thread is not None and self.task_thread.is_alive()
