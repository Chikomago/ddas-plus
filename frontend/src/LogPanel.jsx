import React,{memo,useEffect,useId,useMemo,useRef,useState,useSyncExternalStore} from 'react';
import {PanelBottom,Download,ChevronDown,ChevronUp} from 'lucide-react';
import {getLogs,subscribeLogs} from './logStore';

const categories=[['all','全部'],['http','HTTP'],['operation','操作']];

function categoryOf(text){
 if(text.startsWith('[HTTP]'))return 'http';
 return 'operation';
}

export default memo(function LogPanel({busy,onClear,onExport}){
 const logs=useSyncExternalStore(subscribeLogs,getLogs);
 const [open,setOpen]=useState(false),[category,setCategory]=useState('all');
 const contentId=useId(),ref=useRef(),follow=useRef(true);
 const matched=useMemo(()=>category==='all'?logs:logs.filter(log=>categoryOf(log.text)===category),[logs,category]);
 const filtered=category!=='all';
 const visible=matched.slice(-200);
 useEffect(()=>{
  if(open&&ref.current)ref.current.scrollTop=ref.current.scrollHeight;
 },[open,category]);
 useEffect(()=>{
  if(open&&follow.current&&ref.current)ref.current.scrollTop=ref.current.scrollHeight;
 },[matched,open]);
 const ToggleIcon=open?ChevronDown:ChevronUp;
 return <div className={'log-panel '+(!open?'collapsed':'')}>
  <div className="log-heading">
   <button className="log-title" aria-expanded={open} aria-controls={contentId} onClick={()=>setOpen(!open)}>
    <PanelBottom size={16}/>运行日志 <span>{filtered?`${matched.length}/${logs.length}`:logs.length}</span><ToggleIcon size={14}/>
   </button>
   {open&&<div className="log-tools">
    <div className="log-tabs" role="group" aria-label="日志分类">
     {categories.map(([id,label])=><button key={id} aria-pressed={category===id}
      aria-controls={contentId} onClick={()=>setCategory(id)}>{label}</button>)}
    </div>
    <button disabled={busy} onClick={onClear}>清空</button>
    <button disabled={busy} onClick={onExport}><Download size={14}/>导出</button>
   </div>}
  </div>
  <div id={contentId} hidden={!open} className="log-content" ref={ref} onScroll={event=>{
   const element=event.currentTarget;
   follow.current=element.scrollHeight-element.scrollTop-element.clientHeight<24;
  }}>
   {open&&(visible.length?visible.map(log=><div className={'log-line '+log.type} key={log.id}>
    <time>{log.time}</time><span>{log.text.replace(/^\[逐行结果\]/,'[操作]')}</span>
   </div>):<div className="empty-log">{filtered&&logs.length?'没有匹配的日志':'暂无日志'}</div>)}
  </div>
 </div>
});
