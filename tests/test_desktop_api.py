import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

import openpyxl
from common.desktop_api import DesktopAPI
from common.config_generator import generate_config_workbook
from common.config_schema import DEEDRAW_HEADERS


class DesktopAPITests(unittest.TestCase):
    def test_online_update_compares_numeric_versions_and_opens_fixed_release_url(self):
        from io import BytesIO
        from unittest.mock import patch

        for tag, available in (('v2.0.9', False), ('v2.0.10', False), ('v2.0.11', True)):
            with self.subTest(tag=tag), patch('common.desktop_api.urlopen',
                    return_value=BytesIO(json.dumps({'tag_name': tag}).encode())) as read:
                self.assertEqual(self.api.check_update()['value'], {'tag': tag, 'available': available})
                self.assertTrue(read.call_args.args[0].full_url.endswith('/Chikomago/ddas-plus/releases/latest'))
        with patch('common.desktop_api.webbrowser.open', return_value=True) as open_browser:
            self.assertTrue(self.api.open_release('v2.0.11')['ok'])
            self.assertFalse(self.api.open_release('../other')['ok'])
            open_browser.assert_called_once_with('https://github.com/Chikomago/ddas-plus/releases/tag/v2.0.11')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        settings = SimpleNamespace(settings={
            'log_export_path': str(self.directory), 'task_result_path': str(self.directory),
            'config_path': str(self.directory), 'chrome_path': '/browser',
            'pim_settings': {'pixel_size': '790'}, 'browser_settings': {'auto_close': False},
        }, settings_file=str(self.directory / 'settings.json'))
        self.api = DesktopAPI(settings)
        (self.directory / 'sample.png').write_bytes(b'image fixture')
        self.path = self.directory / 'config.xlsx'
        generate_config_workbook(self.directory, self.path, DEEDRAW_HEADERS)

    def tearDown(self):
        self.api._cancel_confirmations()
        self.temp.cleanup()

    def test_generate_deedraw_from_multiple_directories_preserves_each_scan(self):
        parent = self.directory / '来源一'
        nested = parent / '子目录'
        other = self.directory / '来源二'
        nested.mkdir(parents=True)
        other.mkdir()
        first_image = nested / '蓝色.png'
        second_image = other / '蓝色.png'
        first_image.touch()
        second_image.touch()

        result = self.api.generate_config('deedraw', [str(parent), str(other), str(nested)])
        self.assertTrue(result['ok'], result)
        workbook = openpyxl.load_workbook(result['value'], read_only=True)
        try:
            rows = list(workbook.active.values)
        finally:
            workbook.close()
        self.assertEqual(list(rows[0]), DEEDRAW_HEADERS)
        self.assertEqual([row[0] for row in rows[1:]], ['蓝色'] * 3)
        self.assertEqual([row[3] for row in rows[1:]], [
            str(first_image.resolve()), str(second_image.resolve()), str(first_image.resolve()),
        ])

    def test_selected_directory_prefix_applies_to_direct_and_nested_images(self):
        first = self.directory / '春款'
        nested = first / '棉布'
        second = self.directory / '夏款'
        nested.mkdir(parents=True)
        second.mkdir()
        (first / '白色.png').touch()
        (nested / '红色.png').touch()
        (second / '蓝色.png').touch()

        result = self.api.generate_config('deedraw', [str(first), str(second)], True)
        self.assertTrue(result['ok'], result)
        workbook = openpyxl.load_workbook(result['value'], read_only=True)
        try:
            names = {row[0] for row in list(workbook.active.values)[1:]}
        finally:
            workbook.close()
        self.assertEqual(names, {'春款-白色', '春款-棉布-红色', '夏款-蓝色'})

    def test_split_sources_fill_first_empty_cell_per_name_in_import_order(self):
        directories = [self.directory / name for name in ('PC一', 'PC二', '移动一', '移动二', '移动三')]
        for directory in directories:
            directory.mkdir()
        pc_first, pc_second, mobile_first, mobile_second, mobile_third = [
            directory / filename
            for directory, filename in zip(directories, ('红.png', '红.jpg', '红.gif', '红.png', '红.jpeg'))
        ]
        pc_other = directories[0] / '蓝.png'
        for path in (pc_first, pc_other, pc_second, mobile_first, mobile_second, mobile_third):
            path.touch()

        result = self.api.generate_config(
            'deedraw', [str(pc_first), str(pc_other), str(pc_second)], True,
            [str(mobile_first.parent), str(mobile_second), str(mobile_third)],
        )
        self.assertTrue(result['ok'], result)
        workbook = openpyxl.load_workbook(result['value'], read_only=True)
        try:
            rows = list(workbook.active.values)[1:]
        finally:
            workbook.close()
        self.assertEqual(rows, [
            ('PC一-红', '红', '红', str(pc_first.resolve()), str(mobile_first.resolve())),
            ('PC一-蓝', '蓝', None, str(pc_other.resolve()), None),
            ('PC二-红', '红', '红', str(pc_second.resolve()), str(mobile_second.resolve())),
            ('移动三-红', None, '红', None, str(mobile_third.resolve())),
        ])

    def test_pim_saves_images_from_the_shared_generator_with_pim_headers(self):
        from common.config_schema import PIM_HEADERS

        values = [['选项一', 'PC值', '移动值', '/pc.png', '/mobile.png']]
        path = self.api.save_image_config(values, False, 'pim')['value']
        data = self.api.load_data(path)['value']
        self.assertEqual(data['headers'], PIM_HEADERS)
        self.assertEqual(data['rows'], values)

    def test_text_configuration_round_trip_and_value_only_execution(self):
        from common.config_loader import read_config

        values = [['选项一', 'PC值', '移动值']]
        path = self.api.save_image_config(values, True)['value']
        data = self.api.load_data(path)['value']
        self.assertEqual(data['headers'], DEEDRAW_HEADERS[:3])
        self.assertEqual(data['rows'], values)
        self.assertTrue(self.api.save_data(path, [['选项二', '=文本', '移动值']], data['token'])['ok'])
        self.assertEqual(read_config(path, options=(False, True, False, True)),
                         [(2, ('选项二', '=文本', '移动值', '', ''))])
        with self.assertRaisesRegex(ValueError, '第 4 列不能为空'):
            read_config(path, options=(True, False, False, False))

    def test_preview_uses_explicit_pairs_for_different_filenames(self):
        pc = self.directory / '800.png'
        mobile = self.directory / '750.png'
        pc.touch()
        mobile.touch()
        entries = [[{'path': str(path)}] for path in (pc, mobile)]
        result = self.api.preview_image_config(*entries, False, [0])
        self.assertEqual(result['value'], [['800', '800', '750', str(pc.resolve()), str(mobile.resolve())]])

    def test_expanded_directories_keep_names_and_preview_edits_are_saved(self):
        source = self.directory / '春款'
        nested = source / '棉布'
        nested.mkdir(parents=True)
        image = nested / '白色.png'
        image.touch()
        (nested / '说明.txt').touch()
        images = self.api.expand_image_sources([str(source)])['value']
        self.assertEqual(images, [{'path': str(image.resolve()), 'prefixed_name': '春款-棉布-白色'}])

        rows = self.api.preview_image_config(images, None, True)['value']
        self.assertEqual(rows[0][0], '春款-棉布-白色')
        rows[0][0] = '=前缀-' + rows[0][0] + '-后缀'
        path = self.api.save_image_config(rows)['value']
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            self.assertEqual(list(workbook.active.values)[1], tuple(rows[0]))
        finally:
            workbook.close()

    def test_prefix_applies_to_every_row_for_mixed_directory_and_file_sources(self):
        folder = self.directory / '春款'
        folder.mkdir()
        (folder / '白色.png').touch()
        (folder / '蓝色.png').touch()
        other = self.directory / '夏款'
        other.mkdir()
        red = other / '红色.png'
        black = other / '黑色.png'
        red.touch()
        black.touch()

        images = self.api.expand_image_sources(list(map(str, [folder, red, black])))['value']
        prefixed = self.api.preview_image_config(images, None, True)['value']
        self.assertEqual([row[0] for row in prefixed], ['春款-白色', '春款-蓝色', '夏款-红色', '夏款-黑色'])
        plain = self.api.preview_image_config(images, None, False)['value']
        self.assertEqual([row[0] for row in plain], ['白色', '蓝色', '红色', '黑色'])

    def test_drop_uses_captured_native_directory_when_file_list_is_empty(self):
        from unittest.mock import Mock, patch
        self.api.window = Mock()
        with patch.dict('webview.dom._dnd_state', {'paths': [('目录', str(self.directory))]}):
            self.api._on_image_drop({'dataTransfer': {'files': []}, 'clientX': 80, 'clientY': 90})
        script = self.api.window.evaluate_js.call_args.args[0]
        self.assertIn(json.dumps(str(self.directory)), script)

    def await_event(self, kind):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            for event in self.api.poll()['value']['events']:
                if event['kind'] == kind:
                    return event
            threading.Event().wait(.005)
        self.fail('事件未到达: ' + kind)

    def test_confirm_waits_for_the_actual_answer(self):
        result = []
        thread = threading.Thread(target=lambda: result.append(self.api._confirm('保留原文？')))
        thread.start()
        event = self.await_event('confirm')
        self.assertEqual(event['text'], '保留原文？')
        self.assertTrue(thread.is_alive())
        self.api.respond(event['id'], True)
        thread.join(1)
        self.assertEqual(result, [True])

    def test_stop_releases_waiting_confirmation_and_keeps_runner_busy(self):
        answers = []
        finished = threading.Event()
        def worker():
            answers.append(self.api._confirm('是否继续？'))
            finished.wait(2)
        self.api.runner.start_task_thread(worker)
        self.await_event('confirm')
        self.api.stop_task()
        deadline = time.monotonic()+1
        while not answers and time.monotonic()<deadline:
            threading.Event().wait(.005)
        self.assertEqual(answers, [False])
        self.assertTrue(self.api.poll()['value']['running'])
        finished.set()
        self.api.runner.task_thread.join(1)

    def test_closing_is_blocked_until_worker_exits(self):
        done = threading.Event()
        self.api.runner.start_task_thread(lambda: done.wait(2))
        self.assertFalse(self.api.on_closing())
        self.assertEqual(self.await_event('message')['title'], '任务运行中')
        done.set()
        self.api.runner.task_thread.join(1)
        self.assertTrue(self.api.on_closing())

    def test_poll_tells_the_page_to_stop_polling_after_close(self):
        self.assertTrue(self.api.on_closing())
        self.assertTrue(self.api.poll()['value']['closed'])

    def test_pending_confirmation_is_released_before_close_marks_closed(self):
        answer = []
        thread = threading.Thread(target=lambda: answer.append(self.api._confirm('继续？')))
        thread.start()
        self.await_event('confirm')
        dismissed = []
        original_emit = self.api._emit

        def record(kind, **payload):
            if kind == 'dismiss_confirm':
                dismissed.append((self.api._closed, payload['ids']))
            return original_emit(kind, **payload)

        self.api._emit = record
        self.assertTrue(self.api.on_closing())
        thread.join(1)
        self.assertEqual(answer, [False])
        # The dismiss notice must be emitted while _closed is still False,
        # otherwise _emit drops it and the page keeps a dead confirmation modal.
        self.assertEqual(len(dismissed), 1)
        self.assertFalse(dismissed[0][0])
        self.assertEqual(len(dismissed[0][1]), 1)

    @patch('common.desktop_api.os._exit')
    @patch('common.desktop_api.threading.Timer')
    def test_closed_installs_a_daemon_watchdog_without_leaking_bridge_state(self, timer, exit_):
        self.api.on_closed()
        self.assertTrue(self.api._closed)
        self.assertTrue(self.api.poll()['value']['closed'])
        self.assertTrue(timer.return_value.daemon)
        timer.return_value.start.assert_called_once_with()
        # The exit is deferred, never immediate: normal shutdown gets a grace period.
        exit_.assert_not_called()
        self.assertEqual(timer.call_args.args[0], 1.0)

    def test_pim_options_map_to_the_correct_request_fields(self):
        with patch('pim.task.PimTask') as task:
            task.return_value.run.return_value = None
            result = self.api.start_task('pim', {'file': str(self.path), 'options': [True, False, False, True]})
            self.assertTrue(result['ok'])
            self.api.runner.task_thread.join(1)
            request = task.call_args.args[0]
            self.assertTrue(request.upload_pc_image)
            self.assertFalse(request.fill_pc_value)
            self.assertFalse(request.upload_mobile_image)
            self.assertTrue(request.fill_mobile_value)
            self.assertEqual(request.pixel_size, '790')

    def test_deedraw_starts_parallel_processor_without_credentials_or_separate_login(self):
        with patch('deedraw.parallel.ParallelTaskProcessor') as task:
            task.return_value.start.return_value = True
            result = self.api.start_task('deedraw', {'fields': [
                {'code': 'color', 'file': str(self.path), 'options': [False, True, False, False]}]})
            self.assertTrue(result['ok'])
            self.assertFalse(hasattr(task.return_value.start.call_args.args[0], 'username'))

    def test_deedraw_dispatches_each_field_using_its_own_operation(self):
        payload = {'conflict_policy': 'overwrite', 'fields': [
            {'code': '颜色', 'file': str(self.path), 'mode': 'add',
             'options': [False, True, False, False]},
            {'code': '款式', 'file': str(self.path), 'mode': 'modify', 'rename': True,
             'options': [False, False, False, False]},
        ]}
        with patch('deedraw.parallel.ParallelTaskProcessor') as task:
            task.return_value.start.return_value = True
            self.assertTrue(self.api.start_task('deedraw', payload)['ok'])
            add, modify = task.return_value.start.call_args.args[0].fields
        self.assertFalse(add.modify_only)
        self.assertTrue(add.overwrite_existing)
        self.assertTrue(modify.modify_only)
        self.assertTrue(modify.rename_option)
        self.assertFalse(modify.overwrite_existing)

    def test_pim_validation_preserves_original_messages(self):
        result = self.api.start_task('pim', {'file': str(self.path), 'preset': True, 'options': [True, False, False, False]})
        self.assertEqual(result['message'], '配置预设模块与其他功能不能同时勾选，请只选择一种功能')
        result = self.api.start_task('pim', {'file': '', 'options': [True, False, False, False]})
        self.assertEqual(result['message'], '未选择配置文件。请先生成或选择配置文件。')

    def test_task_callbacks_forward_error_warning_info_and_confirm(self):
        with patch('pim.task.PimTask') as task:
            self.api.start_task('pim', {'file': str(self.path), 'options': [True, False, False, False]})
            self.api.runner.task_thread.join(1)
            callbacks = task.call_args.args[1]
            callbacks.error('原有错误')
            callbacks.warning('原有警告')
            callbacks.info('原有结果')
            events = self.api.poll()['value']['events']
            self.assertEqual([e['text'] for e in events], ['原有错误', '原有警告', '原有结果'])
            self.assertEqual([e['title'] for e in events], ['错误', '警告', '任务完成'])

    def test_editor_roundtrip_preserves_headers_and_other_sheets(self):
        book = openpyxl.load_workbook(self.path)
        book.create_sheet('保留页')['A1'] = '不变'
        book.save(self.path)
        book.close()
        data = self.api.load_data(str(self.path))['value']
        result = self.api.save_data(str(self.path), [['蓝色', 'PC蓝', '移动蓝', '/pc.png', '/mobile.png']], data['token'])
        self.assertTrue(result['ok'])
        book = openpyxl.load_workbook(self.path)
        self.assertEqual([c.value for c in book.active[1]], DEEDRAW_HEADERS)
        self.assertEqual(book.active['C2'].value, '移动蓝')
        self.assertEqual(book['保留页']['A1'].value, '不变')
        book.close()
        self.assertEqual(self.await_event('message')['text'], '数据已保存')

    def test_editor_refuses_to_overwrite_external_changes(self):
        data = self.api.load_data(str(self.path))['value']
        self.path.write_bytes(self.path.read_bytes()+b'external')
        import os
        old=self.path.stat().st_mtime_ns
        os.utime(self.path, ns=(old+1000000,old+1000000))
        result = self.api.save_data(str(self.path), [['a']*5], data['token'])
        self.assertFalse(result['ok'])
        self.assertIn('其他程序修改', result['message'])

    def test_settings_validation_does_not_mutate_state(self):
        previous = dict(self.api.settings.settings)
        result = self.api.save_settings({})
        self.assertFalse(result['ok'])
        self.assertEqual(result['message'], '路径设置不能为空')
        self.assertEqual(previous, self.api.settings.settings)

    def test_bridge_does_not_expose_native_windows_threads_or_settings(self):
        import inspect
        bridge = self.api._bridge()
        names = [name for name in dir(bridge) if not name.startswith('_')]
        self.assertIn('start_task', names)
        for name in names:
            self.assertTrue(inspect.ismethod(getattr(bridge, name)), name)
        for name in ('window', 'runner', 'settings', 'active_task', 'configure_logging', 'on_closing'):
            self.assertFalse(hasattr(bridge, name), name)

    def test_waiting_poll_releases_lock_and_wakes_on_message(self):
        self.api.poll()
        ready, completed = threading.Event(), threading.Event()
        result = []
        def wait():
            ready.set()
            result.append(self.api.poll(1000)['value'])
            completed.set()
        thread = threading.Thread(target=wait, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(1))
        self.api._message('任务成功')
        self.assertTrue(completed.wait(.8))
        thread.join(1)
        self.assertEqual(result[0]['events'][0]['text'], '任务成功')

    def test_idle_poll_does_not_retransmit_large_task_result(self):
        from common.task_models import TaskResult
        self.api.runner.last_result = TaskResult(False, '失败', {'failure_details': ['x'*1000]*1000})
        import json
        self.assertLess(len(json.dumps(self.api.poll()['value'])), 500)

    def test_log_backlog_is_bounded_per_poll_and_messages_have_priority(self):
        for index in range(400):
            self.api._emit('log', text=str(index), time='10:00:00', level='info')
        self.api._message('是否继续？')
        first = self.api.poll()['value']['events']
        self.assertEqual(len(first), 150)
        self.assertEqual(first[0]['text'], '是否继续？')
        rest = self.api.poll()['value']['events']+self.api.poll()['value']['events']
        self.assertEqual(len(first)+len(rest), 401)

    def test_field_config_round_trip_preserves_choices_and_missing_paths(self):
        self.api.window = Mock()
        destination = self.directory / '字段模板'
        self.api.window.create_file_dialog.return_value = (str(destination),)
        config = {'version': 1, 'mode': 'modify', 'fields': [
            {'code': '品牌故事', 'file': '/尚未迁移/配置.xlsx',
             'options': [True, False, False, True], 'rename': True},
            {'code': '颜色', 'file': '', 'options': [False]*4, 'rename': False},
        ], 'pim': {'file': '/PIM/配置.xlsx', 'options': [False]*4, 'preset': True}}
        path = self.api.export_field_config(config)['value']
        self.assertEqual(Path(path).suffix, '.json')
        self.api.window.create_file_dialog.return_value = (path,)
        self.assertEqual(self.api.import_field_config()['value'], config)
        config['fields'][0]['mode'] = 'add'
        config['fields'][1]['mode'] = 'modify'
        self.assertTrue(self.api.export_field_config(config)['ok'])
        self.assertEqual(self.api.import_field_config()['value'], config)
        Path(path).write_text('{"version":1,"mode":"modify","fields":[{}]}', encoding='utf-8')
        self.assertFalse(self.api.import_field_config()['ok'])

    def test_log_export_and_clear(self):
        self.api._emit('log', text='图片上传超时', time='10:00:00', level='warning')
        self.api.window = Mock()
        self.api.window.create_file_dialog.return_value = (str(self.directory / '自选日志.txt'),)
        path = self.api.export_log()['value']
        import webview
        self.assertEqual(self.api.window.create_file_dialog.call_args.args[0], webview.FileDialog.SAVE)
        self.assertEqual(Path(path).name, '自选日志.txt')
        self.assertIn('图片上传超时', Path(path).read_text())
        self.api.clear_log()
        self.assertEqual(list(self.api._log_text), [])

    def test_cancel_log_save_does_not_write_or_notify(self):
        self.api.window = Mock()
        self.api.window.create_file_dialog.return_value = None
        before = set(self.directory.iterdir())
        self.assertEqual(self.api.export_log(), {'ok': True, 'value': ''})
        self.assertEqual(before, set(self.directory.iterdir()))
        self.assertFalse(self.api._events)

    def test_plugin_contains_react_assets_and_python_entry(self):
        from build_plugin import PLUGIN_FILES
        self.assertIn('frontend/dist/index.html', PLUGIN_FILES)
        self.assertTrue(any(name.endswith('.js') for name in PLUGIN_FILES))
        self.assertIn('common/desktop_api.py', PLUGIN_FILES)


if __name__ == '__main__':
    unittest.main()

class DesktopEntryTests(unittest.TestCase):
    def test_main_attaches_python_api_and_close_guard_to_webview(self):
        import main
        with patch('common.desktop_api.DesktopAPI') as factory, patch('webview.create_window') as create, patch('webview.start') as start, patch('sys.argv', ['main.py']):
            close_event = create.return_value.events.closing
            main.main()
            self.assertIs(create.call_args.kwargs['js_api'], factory.return_value._bridge.return_value)
            self.assertTrue(str(create.call_args.args[1]).endswith('frontend/dist/index.html'))
            self.assertIs(factory.return_value.window, create.return_value)
            close_event.__iadd__.assert_called_once_with(factory.return_value.on_closing)
            self.assertFalse(create.call_args.kwargs['frameless'])
            self.assertFalse(create.call_args.kwargs['easy_drag'])
            self.assertTrue(create.call_args.kwargs['resizable'])
            start.assert_called_once_with(debug=False)
