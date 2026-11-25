"""Read-only text validation in the current browser session."""
import json
import re


def request_forbidden_words(browser, contents):
    values = list(dict.fromkeys(text for text in contents if text))
    if not values:
        return []
    result = browser.run_js('''
        const contents=JSON.parse(arguments[0]);
        if(location.protocol!=='https:'||!['deepdraw.biz','www.deepdraw.biz'].includes(location.hostname))
            throw Error('当前不是深绘页面');
        return Promise.all(contents.map(async content=>{
            const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
            try{
                const response=await fetch('/authorized/merchant/product/checkForbiddenWords',{
                    method:'POST',credentials:'same-origin',redirect:'error',signal:controller.signal,
                    headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','Accept':'text/plain','X-Requested-With':'XMLHttpRequest'},
                    body:new URLSearchParams({content}).toString()});
                const mime=(response.headers.get('Content-Type')||'').toLowerCase();
                if(!response.ok||!mime.startsWith('text/plain'))return {ok:false};
                return {ok:true,text:await response.text()};
            }catch(error){return {ok:false};}finally{clearTimeout(timer);}
        }));
    ''', json.dumps(values, ensure_ascii=False), timeout=12)
    if not isinstance(result, list) or len(result) != len(values):
        raise ValueError('违禁词接口响应异常，未提交该行')
    hits = []
    for item in result:
        if not isinstance(item, dict) or item.get('ok') is not True or not isinstance(item.get('text'), str):
            raise ValueError('违禁词接口超时、网络异常或响应类型错误，未提交该行')
        text = item['text'].strip()
        if '<' in text or '>' in text:
            raise ValueError('违禁词接口返回非预期内容，未提交该行')
        if text and text not in hits:
            hits.append(text)
    return hits


def is_forbidden_prompt(dialog):
    return bool(re.fullmatch(r'\s*内容包含违禁词\s*[:：]\s*.+?\s*[，,]\s*是否继续提交[?？]?\s*', dialog, re.S))
