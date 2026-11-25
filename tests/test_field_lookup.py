import unittest
from types import SimpleNamespace
from common.task_models import TaskCallbacks
from common.task_runner import TaskRunner
from deedraw.field_lookup import resolve_field
from deedraw.task import TaskProcessor


class FieldLookupTests(unittest.TestCase):
    def setUp(self):
        self.fields=[{'id':'fieldContainer12','code':'color','name':'颜色'},
                     {'id':'fieldContainer24','code':'size','name':'尺码'}]

    def test_existing_field_codes_remain_supported(self):
        self.assertEqual(resolve_field('color',self.fields),'12')

    def test_chinese_displayed_name_matches_exactly(self):
        self.assertEqual(resolve_field('颜色',self.fields),'12')

    def test_name_matches_ignore_display_whitespace(self):
        self.fields[0]['name']='  颜色 \n 分类  '
        self.assertEqual(resolve_field('颜色 分类',self.fields),'12')

    def test_partial_names_cannot_select_an_unrelated_field(self):
        with self.assertRaisesRegex(ValueError,'未找到字段'):
            resolve_field('色',self.fields)

    def test_duplicate_names_require_a_unique_code(self):
        self.fields.append({'id':'fieldContainer36','code':'second_color','name':'颜色'})
        with self.assertRaisesRegex(ValueError,'匹配到多个字段'):
            resolve_field('颜色',self.fields)
        self.assertEqual(resolve_field('second_color',self.fields),'36')

    def test_exact_code_takes_priority_over_another_fields_name(self):
        self.fields[1]['name']='color'
        self.assertEqual(resolve_field('color',self.fields),'12')

    def test_duplicate_dom_entries_for_same_field_are_not_ambiguous(self):
        self.fields.append(dict(self.fields[0]))
        self.assertEqual(resolve_field('颜色',self.fields),'12')

    def test_invalid_page_ids_are_not_used_in_navigation_urls(self):
        self.fields[0]['id']='fieldContainer12/other'
        with self.assertRaisesRegex(ValueError,'编号格式'):
            resolve_field('颜色',self.fields)

    def test_quotes_in_field_names_are_not_interpolated_into_xpath(self):
        name='颜色 "A" 与 \'B\''
        self.fields[0]['name']=name
        self.assertEqual(resolve_field(name,self.fields),'12')

    def processor(self, snapshots):
        from unittest.mock import Mock
        processor=TaskProcessor(TaskRunner(),TaskCallbacks(lambda _:None,lambda _:None,lambda _:None))
        processor.browser=SimpleNamespace(wait=SimpleNamespace(doc_loaded=lambda:None),run_js=Mock(side_effect=snapshots))
        processor._pause=lambda _:None
        return processor

    def test_browser_reads_list_in_one_call_and_waits_for_stability(self):
        snapshot={'ready':True,'fields':self.fields}
        processor=self.processor([{'ready':False,'fields':[]},snapshot,snapshot])
        self.assertEqual(processor.get_field_tabindex('颜色'),'12')
        self.assertEqual(processor.browser.run_js.call_count,3)
        self.assertIn('td[data-pinyin]',processor.browser.run_js.call_args.args[0])
        self.assertIn('/addOption',processor.browser.run_js.call_args.args[0])

    def test_changing_list_is_not_resolved_until_stable(self):
        first={'ready':True,'fields':self.fields[:1]}
        duplicate={'ready':True,'fields':self.fields+[{'id':'fieldContainer36','code':'other','name':'颜色'}]}
        processor=self.processor([first,duplicate,duplicate])
        from unittest.mock import patch
        # A duplicate must never select the first apparent match.
        with patch('deedraw.task.time.monotonic',side_effect=[0,0,0,9]):
            with self.assertRaisesRegex(ValueError,'匹配到多个字段'):processor.get_field_tabindex('颜色')

    def test_actual_add_link_and_tabindex_must_agree(self):
        field={**self.fields[0],'tabindex':'12','add_url':'/authorized/merchant/setting/productField/12/addOption'}
        self.assertEqual(resolve_field('颜色',[field]),'12')
        for update in ({'tabindex':'13'},{'add_url':'/authorized/merchant/setting/productField/13/addOption'}, {'add_url':'https://example.com/authorized/merchant/setting/productField/12/addOption'}, {'add_url':''}):
            with self.subTest(update=update):
                with self.assertRaisesRegex(ValueError,'不一致'):resolve_field('颜色',[{**field,**update}])

    def test_never_ready_list_has_explicit_error(self):
        from unittest.mock import patch
        processor=self.processor([{'ready':False,'fields':[]}])
        with patch('deedraw.task.time.monotonic',side_effect=[0,9]):
            with self.assertRaisesRegex(ValueError,'字段列表未就绪'):processor.get_field_tabindex('颜色')
