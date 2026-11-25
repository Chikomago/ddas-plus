"""Confirm fresh per-platform upload backfill independently of image download."""
from urllib.parse import urlsplit, urljoin


def read_upload_state(browser, platform):
    return browser.run_js('''
        const pc=arguments[0]==='Pc',prefix=pc?'pc':'mobile';
        const hidden=document.getElementById(pc?'filePathOfPc':'filePathOfMobile');
        const other=document.getElementById(pc?'filePathOfMobile':'filePathOfPc');
        // Direct child only: imageReplace contains a separate copy1.png icon.
        const image=document.querySelector('.'+prefix+'Images > .'+prefix+'ImageDiv[sort-num="1"] > img');
        const errors=Array.from(document.querySelectorAll('.bootbox-alert')).filter(e=>e.getClientRects().length).map(e=>e.textContent.trim());
        return {present:!!hidden&&!!other&&!!image,path:hidden?.value||'',other_path:other?.value||'',
          src:image?.getAttribute('src')||'',loaded:!!image?.complete&&image.naturalWidth>0,errors};
    ''', platform)


def backfill_complete(before, state):
    if not state.get('present'):
        return False
    if state.get('other_path') != before.get('other_path'):
        raise ValueError('上传时另一端图片路径发生变化，请核对PC与移动端配置')
    path = str(state.get('path') or '').strip()
    if not path or path == str(before.get('path') or '').strip() or ',' in path:
        return False
    expected = urlsplit(urljoin('https://upload.deepdraw.biz/productField/', path))
    actual = urlsplit(urljoin('https://upload.deepdraw.biz', str(state.get('src') or '')))
    return (expected.scheme == actual.scheme == 'https'
            and expected.hostname == actual.hostname == 'upload.deepdraw.biz'
            and expected.path == actual.path and expected.path.startswith('/productField/')
            and expected.query == actual.query)
