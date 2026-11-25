import unittest
from deedraw.upload_state import backfill_complete,read_upload_state
from unittest.mock import Mock


class UploadStateTests(unittest.TestCase):
    def setUp(self):
        self.before={'path':'old.png','other_path':'mobile.png'}
        self.state={'present':True,'path':'new.png','other_path':'mobile.png','src':'//upload.deepdraw.biz/productField/new.png','loaded':False}

    def test_backfill_does_not_wait_for_preview_download(self):
        self.assertTrue(backfill_complete(self.before,self.state))

    def test_old_preview_and_path_cannot_pass(self):
        self.assertFalse(backfill_complete(self.before,{**self.state,'path':'old.png'}))
        self.assertFalse(backfill_complete(self.before,{**self.state,'src':'//upload.deepdraw.biz/productField/old.png'}))

    def test_icon_substring_and_untrusted_host_do_not_pass(self):
        for src in ('//resources1.deepdraw.biz/img/copy1.png','//upload.deepdraw.biz/productField/new.png.backup','https://example.com/productField/new.png',''):
            with self.subTest(src=src):self.assertFalse(backfill_complete(self.before,{**self.state,'src':src}))

    def test_wrong_platform_backfill_is_an_explicit_error(self):
        with self.assertRaisesRegex(ValueError,'另一端'):
            backfill_complete(self.before,{**self.state,'other_path':'unexpected.png'})

    def test_missing_controls_and_multiple_paths_do_not_pass(self):
        self.assertFalse(backfill_complete(self.before,{**self.state,'present':False}))
        self.assertFalse(backfill_complete(self.before,{**self.state,'path':'new.png,other.png'}))

    def test_snapshot_uses_direct_child_selector_and_explicit_platform(self):
        browser=Mock();read_upload_state(browser,'Mobile')
        script,platform=browser.run_js.call_args.args
        self.assertEqual(platform,'Mobile')
        self.assertIn('ImageDiv[sort-num="1"] > img',script)
