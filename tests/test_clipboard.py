import unittest
from unittest.mock import patch, Mock
from common.clipboard import clipboard_text


class ClipboardTests(unittest.TestCase):
    @patch('common.clipboard.platform.system', return_value='Darwin')
    @patch('common.clipboard.subprocess.run')
    def test_unicode_text_is_passed_as_stdin_without_shell(self, run, system):
        run.return_value = Mock(stdout='字段\t图片\n')
        self.assertEqual(clipboard_text(), '字段\t图片\n')
        self.assertEqual(run.call_args.args[0], ['pbpaste'])
        self.assertTrue(clipboard_text('文字\t$(echo unsafe)'))
        self.assertEqual(run.call_args.args[0], ['pbcopy'])
        self.assertEqual(run.call_args.kwargs['input'], '文字\t$(echo unsafe)')
        self.assertNotIn('shell', run.call_args.kwargs)

    @patch('common.clipboard.platform.system', return_value='Linux')
    @patch('common.clipboard.shutil.which', return_value=None)
    def test_unavailable_clipboard_has_actionable_error(self, which, system):
        with self.assertRaisesRegex(RuntimeError, '快捷键'):
            clipboard_text()
