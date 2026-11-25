import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from common.task_models import DeedrawTaskRequest,DeedrawFieldRequest,TaskCallbacks
from common.task_runner import TaskRunner
from deedraw.parallel import ParallelTaskProcessor
from deedraw.page_state import SubmissionUnknown


class FieldParallelTests(unittest.TestCase):
    def manager(self,codes=('a','b','c'),concurrency=2):
        manager=ParallelTaskProcessor(TaskRunner(),TaskCallbacks(lambda _:None,lambda _:None,lambda _:None))
        manager.max_parallel_fields=concurrency
        fields=[DeedrawFieldRequest(code,'unused.xlsx',False,True,False,False) for code in codes]
        manager.request=DeedrawTaskRequest(fields,{})
        manager.settings={};manager.get_field_tabindex=lambda code:code
        manager._configs={id(f):[(2,('one-'+f.code,'','','','')),(3,('two-'+f.code,'','','',''))] for f in fields}
        tabs=[Mock(name='tab-'+str(i)) for i in range(concurrency)]
        manager.browser=SimpleNamespace(new_tab=Mock(side_effect=tabs))
        return manager,tabs

    def test_start_waits_for_login_before_opening_task_tabs(self):
        manager, tabs = self.manager(codes=('a',), concurrency=1)
        request = DeedrawTaskRequest(manager.request.fields, {'chrome_path': '/chrome'})
        login_started = threading.Event()
        login_finished = threading.Event()

        def login():
            login_started.set()
            return login_finished.wait(2)

        def run(worker, field, code, success, failed):
            success.extend((code, number, values[0]) for number, values in worker._configs[id(field)])

        manager.initialize_browser = Mock(return_value=True)
        manager.login = login
        configs = manager._configs[id(request.fields[0])]
        with patch('deedraw.task.read_config', return_value=configs), patch(
                'deedraw.parallel.TaskProcessor.process_single_field', new=run):
            self.assertTrue(manager.start(request))
            try:
                self.assertTrue(login_started.wait(2))
                manager.browser.new_tab.assert_not_called()
            finally:
                login_finished.set()
                manager.task_runner.task_thread.join(2)
        self.assertTrue(manager.task_runner.last_result.success)
        manager.browser.new_tab.assert_called_once()
        tabs[0].close.assert_called_once()

    def test_fields_run_concurrently_but_options_are_sequential_per_tab(self):
        manager,tabs=self.manager();barrier=threading.Barrier(2)
        trace=[];lock=threading.Lock()
        def run(worker,field,code,success,failed):
            if code in ('a','b'):barrier.wait(timeout=2)
            for row,values in worker._configs[id(field)]:
                with lock:trace.append((code,row,worker.browser))
                success.append((code,row,values[0]))
        with patch('deedraw.parallel.TaskProcessor.process_single_field',new=run):result=manager.process_task()
        self.assertTrue(result.success)
        self.assertEqual(result.details['succeeded'],6)
        self.assertEqual(result.details['concurrency'],2)
        for code in ('a','b','c'):
            events=[x for x in trace if x[0]==code]
            self.assertEqual([x[1] for x in events],[2,3])
            self.assertIs(events[0][2],events[1][2])
        self.assertIsNot(next(x[2] for x in trace if x[0]=='a'),next(x[2] for x in trace if x[0]=='b'))
        for tab in tabs:tab.close.assert_called_once()

    def test_aliases_for_same_field_use_one_tab(self):
        manager,tabs=self.manager(codes=('颜色','color'))
        manager.get_field_tabindex=lambda code:'7'
        seen=[]
        def run(worker,field,code,success,failed):
            seen.append((code,worker.browser))
            success.extend((code,n,v[0]) for n,v in worker._configs[id(field)])
        with patch('deedraw.parallel.TaskProcessor.process_single_field',new=run):result=manager.process_task()
        self.assertTrue(result.success);self.assertEqual(result.details['field_count'],1)
        manager.browser.new_tab.assert_called_once()
        self.assertIs(seen[0][1],seen[1][1])

    def test_unknown_save_stops_queued_fields_and_keeps_problem_tab(self):
        manager,tabs=self.manager(concurrency=1);calls=[]
        def run(worker,field,code,success,failed):
            calls.append(code);worker._uncertain_rows.append('结果未知');raise SubmissionUnknown()
        with patch('deedraw.parallel.TaskProcessor.process_single_field',new=run):result=manager.process_task()
        self.assertFalse(result.success);self.assertEqual(len(calls),1)
        self.assertEqual(result.details['pending'],6)
        tabs[0].close.assert_not_called()
        self.assertFalse(manager.task_runner.stop_event.is_set())

    def test_tab_creation_failure_closes_only_new_tabs(self):
        manager,tabs=self.manager()
        manager.browser.new_tab.side_effect=[tabs[0],RuntimeError('tab error')]
        with self.assertRaises(RuntimeError):manager.process_task()
        tabs[0].close.assert_called_once()

    def test_duplicate_names_across_aliases_fail_before_tabs(self):
        manager,_=self.manager(codes=('a','b'));manager.get_field_tabindex=lambda code:'7'
        for field in manager.request.fields:manager._configs[id(field)]=[(2,('same','','','',''))]
        with self.assertRaisesRegex(ValueError,'选项名重复'):manager.process_task()
        manager.browser.new_tab.assert_not_called()


class ParallelCancellationTests(unittest.TestCase):
    manager=FieldParallelTests.manager
    def test_stop_notifies_all_active_field_workers_and_skips_queue(self):
        manager,tabs=self.manager();barrier=threading.Barrier(2);stopped=[]
        def run(worker,field,code,success,failed):
            barrier.wait(timeout=2)
            manager.task_runner.request_stop()
            worker.task_runner.stop_event.wait(.5)
            stopped.append(code)
            worker._check_stop()
        with patch('deedraw.parallel.TaskProcessor.process_single_field',new=run):result=manager.process_task()
        self.assertEqual(set(stopped),{'a','b'})
        self.assertTrue(result.details['cancelled'])
        self.assertEqual(result.details['pending'],6)
        for tab in tabs:tab.close.assert_called_once()
