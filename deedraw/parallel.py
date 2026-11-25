"""One field per tab; options remain sequential inside each field."""
import logging
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from common.task_models import TaskCallbacks, TaskCancelled
from common.task_results import TaskReport, report_result
from deedraw.task import TaskProcessor
from deedraw.page_state import SubmissionUnknown


class CombinedStop:
    def __init__(self,user,abort):self.user,self.abort=user,abort
    def is_set(self):return self.user.is_set() or self.abort.is_set()
    def wait(self,seconds):
        end=time.monotonic()+seconds
        while not self.is_set():
            left=end-time.monotonic()
            if left<=0:return False
            self.abort.wait(min(.05,left))
        return True


class ParallelTaskProcessor(TaskProcessor):
    max_parallel_fields = 5

    def process_task(self):
        started=time.monotonic()
        self._success_rows,self._failure_rows,self._uncertain_rows=[],[],[]
        self._http_stats={}
        self._skipped_rows,self._overwritten_rows,self._modified_rows=[],[],[]
        groups={}
        # Resolve all aliases before opening task tabs; the same server field
        # always shares a queue even if configured once by code and once by name.
        for field in self.request.fields:
            self._check_stop()
            number=self.get_field_tabindex(field.code)
            groups.setdefault(number,[]).append(field)
        for number,fields in groups.items():
            names=set()
            for field in fields:
                for row,values in self._configs[id(field)]:
                    if values[0] in names:raise ValueError(f'字段 {number} 第 {row} 行选项名重复，请合并配置')
                    names.add(values[0])
        pending=queue.Queue()
        for item in groups.items():pending.put(item)
        abort=threading.Event();stop=CombinedStop(self.task_runner.stop_event,abort)
        lock=threading.Lock();tabs=[]
        count=min(self.max_parallel_fields, len(groups))
        self.update_status(f'正在并行处理 {len(groups)} 个字段，最多 {count} 个标签页')
        logging.info('[并行任务] %s个配置，%s个实际字段，%s个标签页；字段内按行顺序执行',len(self.request.fields),len(groups),count)

        def work(tab):
            keep=False
            try:
                while not stop.is_set():
                    try:number,fields=pending.get_nowait()
                    except queue.Empty:break
                    processor=TaskProcessor(SimpleNamespace(stop_event=stop),TaskCallbacks(
                        log=logging.info,status=lambda text:None,error=logging.error,
                        confirm=self.callbacks.confirm,warning=logging.warning,info=logging.info))
                    processor.browser=tab;processor.settings=self.settings;processor._configs=self._configs
                    processor._http_stats={};processor._uncertain_rows=[]
                    processor._skipped_rows,processor._overwritten_rows,processor._modified_rows=[],[],[]
                    processor.get_field_tabindex=lambda identifier:number
                    success,failed=[],[]
                    try:
                        logging.info('[并行任务] 标签页开始处理字段 %s',number)
                        for field in fields:
                            processor._check_stop()
                            processor.process_single_field(field,field.code,success,failed)
                    except TaskCancelled:pass
                    except SubmissionUnknown:
                        keep=True;abort.set()
                    except Exception as error:
                        # Preserve rows already confirmed; unexecuted rows remain pending.
                        logging.exception('[并行任务] 字段 %s 中断：%s',number,error)
                        processor._uncertain_rows.append(f'字段 {number} 执行中断：{error}')
                        keep=True;abort.set()
                    finally:
                        with lock:
                            self._success_rows.extend(success);self._failure_rows.extend(failed)
                            self._skipped_rows.extend(processor._skipped_rows)
                            self._overwritten_rows.extend(processor._overwritten_rows)
                            self._modified_rows.extend(processor._modified_rows)
                            self._uncertain_rows.extend(processor._uncertain_rows)
                            for key,value in processor._http_stats.items():self._http_stats[key]=self._http_stats.get(key,0)+value
                        pending.task_done()
            finally:
                if not keep:
                    try:tab.close()
                    except Exception:logging.warning('[并行任务] 任务标签页关闭失败')

        try:
            # Tab creation is serialized; browser navigation and form work are not.
            for _ in range(count):
                self._check_stop();tabs.append(self.browser.new_tab(background=True))
        except Exception:
            for tab in tabs:
                try:tab.close()
                except Exception:pass
            raise
        with ThreadPoolExecutor(max_workers=count,thread_name_prefix='deepdraw-field') as pool:
            futures=[pool.submit(work,tab) for tab in tabs]
            for future in futures:future.result()
        total=sum(len(rows) for rows in self._configs.values())
        self._report=TaskReport(total,len(self._success_rows),len(self._failure_rows),time.monotonic()-started,
            [f'{field} - {row}: {value}' for field,row,value in self._success_rows],
            [f'{field} - {row}: {reason}' for field,row,reason in self._failure_rows],
            **self.conflict_report_details())
        result=report_result(self._report,cancelled=self.task_runner.stop_event.is_set())
        result.details.update(http=self._http_stats,uncertain_rows=list(self._uncertain_rows),field_count=len(groups),concurrency=count)
        if self._uncertain_rows:result.message+='\n结果待确认，已暂停后续字段：\n'+'\n'.join(self._uncertain_rows)
        logging.info('[并行任务] 完成：%s',result.message)
        return result
