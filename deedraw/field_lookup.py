"""Resolve one field unambiguously by code or exact displayed name."""
import re
from urllib.parse import urlsplit


def normalized_name(value):
    return ' '.join(str(value or '').split())


def resolve_field(identifier, fields):
    value = normalized_name(identifier)
    if not value:
        raise ValueError('请输入字段名称或编码')
    code_matches = [field for field in fields if str(field['code'] or '').strip() == value]
    matches = code_matches or [field for field in fields if normalized_name(field['name']) == value]
    by_id = {str(field['id']): field for field in matches}
    if not by_id:
        raise ValueError(f'未找到字段“{value}”，请检查名称或编码是否与深绘页面一致')
    if len(by_id) > 1:
        raise ValueError(f'字段“{value}”匹配到多个字段，请使用唯一的字段编码')
    field_id = next(iter(by_id))
    match = re.fullmatch(r'fieldContainer([A-Za-z0-9_-]+)', field_id)
    if not match:
        raise ValueError(f'字段“{value}”的页面编号格式不正确')
    number = match.group(1)
    selected = by_id[field_id]
    # Browser snapshots include independent attributes from the supplied DOM.
    if 'tabindex' in selected and str(selected['tabindex']) != number:
        raise ValueError(f'字段“{value}”的容器编号与tabindex不一致')
    if 'add_url' in selected:
        link = urlsplit(selected['add_url'] or '')
        if (link.path != f'/authorized/merchant/setting/productField/{number}/addOption'
                or link.query or link.fragment
                or (link.netloc and (link.scheme != 'https' or link.hostname not in ('deepdraw.biz','www.deepdraw.biz')))):
            raise ValueError(f'字段“{value}”的新增选项链接与字段编号不一致')
    return number


def read_field_snapshot(browser):
    """One browser round trip; never confuse option names with field headings."""
    return browser.run_js("""
        const table=document.querySelector('.setting-table-container table');
        const fields=table?Array.from(table.querySelectorAll('tbody[id^="fieldContainer"]')).flatMap(container=>{
            return Array.from(container.querySelectorAll('td[data-pinyin]')).filter(cell=>cell.closest('tbody')===container)
              .map(cell=>({id:container.id,tabindex:container.getAttribute('tabindex'),
                code:cell.getAttribute('data-pinyin'),name:cell.textContent.trim(),
                add_url:container.querySelector('a[href*="/addOption"]')?.getAttribute('href')||''}));
        }):[];
        return {ready:document.readyState==='complete'&&!!table,fields};
    """)
