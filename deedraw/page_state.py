"""Read-only DOM snapshots based on Deepdraw's supplied field and option pages."""
import json
from urllib.parse import urlsplit, parse_qs
from pathlib import Path


class SubmissionUnknown(RuntimeError):
    pass


def validate_option_name(value):
    if not value or len(value.encode('utf-16-le')) // 2 > 20:
        raise ValueError('深绘选项名不能为空，且不能超过20个字符')
    if '<' in value or '>' in value:
        raise ValueError('深绘选项名不能包含HTML标记，请先修改配置')


def validate_upload_image(path):
    image = Path(path)
    if image.suffix.lower() not in ('.jpg', '.png', '.gif'):
        raise ValueError('深绘仅支持 jpg、png、gif 图片')
    if image.stat().st_size >= 3*1024*1024:
        raise ValueError('深绘图片必须小于3MB')
    return image


def saved_location(url, field_id):
    parts = urlsplit(str(url))
    return (parts.hostname in ('www.deepdraw.biz', 'deepdraw.biz') and
            parts.path == '/authorized/merchant/setting/productFields' and
            parse_qs(parts.query).get('lastOperatedFieldId') == [str(field_id)])


def option_edit_path(field_id, option_id):
    field_id, option_id = str(field_id), str(option_id)
    if not (field_id.isascii() and field_id.isdigit() and option_id.isascii() and option_id.isdigit()):
        raise ValueError('字段或选项编号无效')
    return f'/authorized/merchant/setting/productField/{field_id}/{option_id}/editOption'


def is_option_edit_url(url, field_id, option_id):
    parts = urlsplit(str(url))
    return (parts.scheme == 'https' and parts.netloc in ('www.deepdraw.biz', 'deepdraw.biz')
            and parts.path == option_edit_path(field_id, option_id)
            and not parts.query and not parts.fragment)


def read_options(browser, field_id):
    return browser.run_js('''
        const field=arguments[0];
        const container=document.getElementById('fieldContainer'+field);
        if(!container)return null;
        return Array.from(container.querySelectorAll('td[name="fieldOptionItem"][data-id]')).map(cell=>{
          const id=cell.getAttribute('data-id');
          const path='/authorized/merchant/setting/productField/'+field+'/'+id+'/editOption';
          const links=Array.from(cell.closest('tr').querySelectorAll('td a[href]')).filter(a=>
            a.textContent.trim()==='修改' && a.pathname===path && a.origin===location.origin &&
            !a.search && !a.hash);
          return {id,value:cell.textContent.trim(),edit_url:links.length===1?links[0].href:null};
        });
    ''', str(field_id))


def reset_option_form(browser, original_name, selected=None):
    """Clear the edit draft locally. Only the form submission writes to the option."""
    return browser.run_js('''
        const selected=JSON.parse(arguments[1])||[true,true,true,true,true];
        const name=document.querySelector('#mainForm #value');
        const text=['Pc','Mobile'].map(key=>document.querySelector('#mainForm #textInputOf'+key));
        const images=['Pc','Mobile'].map(key=>document.querySelector('#mainForm #filePathOf'+key));
        const slots=['pc','mobile'].map(key=>Array.from(document.querySelectorAll(
          '#mainForm .'+key+'Images > .'+key+'ImageDiv')));
        if(!name||name.value.trim()!==arguments[0]||[...text,...images].some(e=>!e)||
           slots.some(group=>!group.some(slot=>slot.getAttribute('sort-num')==='1'&&slot.querySelector(':scope > img'))))
          return false;
        const inputs=[name,text[0],text[1],images[0],images[1]];
        inputs.forEach((input,index)=>{if(selected[index])input.value=''});
        for(const [index,group] of slots.entries()){
          if(!selected[index+3])continue;
          for(const slot of group){
            if(slot.getAttribute('sort-num')!=='1'){slot.remove();continue}
            const preview=slot.querySelector(':scope > img');
            preview.removeAttribute('src');
            preview.style.display='none';
          }
        }
        inputs.forEach((input,index)=>{
          if(index&&selected[index])input.dispatchEvent(new Event('change',{bubbles:true}));
        });
        return inputs.every((input,index)=>!selected[index]||input.value==='');
    ''', original_name, json.dumps(selected))


def form_feedback(browser):
    return browser.run_js('''
        const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
        const errors=Array.from(document.querySelectorAll('#valueTipContainer .fontred,#contentInputTipContainer .fontred'))
          .filter(visible).map(e=>e.textContent.trim()).filter(Boolean);
        const dialog=Array.from(document.querySelectorAll('.bootbox')).find(visible);
        return {errors,pending:!!window.validator?.pendingRequest,dialog:dialog?(dialog.querySelector('.bootbox-body')?.textContent||'').trim():'',
          confirm:!!dialog?.querySelector('button[data-bb-handler="confirm"]')};
    ''')
