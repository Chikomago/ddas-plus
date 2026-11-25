import {filterImages,matchSplitImages} from './imageFilter';
import React,{useState,useEffect,useRef} from 'react';
import {createPortal} from 'react-dom';
import {createRoot} from 'react-dom/client';
import {Tag,Settings,ChevronLeft,ChevronRight,ChevronDown,Pencil,Plus,Play,Square,FileSpreadsheet,FolderOpen,Trash2,Check,X,Monitor,SlidersHorizontal,Info,ExternalLink} from 'lucide-react';
import SwipeViewport from './SwipeViewport';
import SpreadsheetEditor from './SpreadsheetEditor';
import LogPanel from './LogPanel';
import {appendLogs,clearLogs} from './logStore';
import {watchBridge,call,setBridgeTiming} from './bridge';
import {installUITiming} from './uiTiming';
import {CHANGELOG} from './changelog';
import './style.css';
import './window.css';

const configHeaders=['选项名','PC选项值','移动选项值','PC图路径','移动图路径'];
const labels=['上传 PC 图片','填写 PC 选项值','上传移动图片','填写移动选项值'];
const modifyLabels=['修改 PC 图片','修改 PC 选项值','修改移动图片','修改移动选项值'];
const blankField=()=>({id:crypto.randomUUID(),code:'',file:'',mode:'add',options:[false,false,false,false]});
const defaults={chrome_path:'',log_export_path:'',task_result_path:'',config_path:'',browser_settings:{auto_close:false},pim_settings:{pixel_size:'750'}};
const basename=path=>path.split(/[\\/]/).pop();

function App(){
 const [page,setPage]=useState('deedraw'),[lastPage,setLastPage]=useState('deedraw');
 const [rows,setRows]=useState(()=>[blankField()]),[fieldPage,setFieldPage]=useState(0);
 const [conflictPolicy,setConflictPolicy]=useState(null);
 const [pimFile,setPimFile]=useState(''),[pimOptions,setPimOptions]=useState([false,false,false,false]),[preset,setPreset]=useState(false);
 const [api,setApi]=useState(null),[ready,setReady]=useState(false),[busy,setBusy]=useState(false),[running,setRunning]=useState(false),[status,setStatus]=useState('就绪');
 const [messages,setMessages]=useState([]),[modal,setModal]=useState(null),[prefs,setPrefs]=useState(defaults),[version,setVersion]=useState(CHANGELOG[0].version);
 const [copiedReport,setCopiedReport]=useState(null);
 const [generation,setGeneration]=useState(null),[editor,setEditor]=useState(null);
 const previewFile=useRef(),fileTarget=useRef(),savedPrefs=useRef(defaults);
 function message(text,title='提示',level='info'){setMessages(v=>[...v,{text,title,level}])}
 async function request(name,...args){if(!api)throw new Error('当前为前端预览，请从 Sanka 或 Python 入口运行插件');return call(api,name,...args)}
 const [update,setUpdate]=useState({state:'idle'}),[updateNotice,setUpdateNotice]=useState(null);
 async function checkUpdate(bridge, startupIsActive){
  setUpdate(current=>({...current,state:'checking'}));
  try{
   const result=await call(bridge,'check_update');
   if(startupIsActive&&!startupIsActive())return;
   setUpdate({state:'ready',...result});
   if(startupIsActive&&result.available)setUpdateNotice(result.tag);
  }catch(error){
   if(!startupIsActive||startupIsActive())setUpdate(current=>({...current,state:'error',message:error.message}));
  }
 }
 function openUpdate(){
  setUpdateNotice(null);
  setModal('changelog');
 }
 async function action(fn){if(busy)return;setBusy(true);try{return await fn()}catch(e){message(e.message,'错误','error')}finally{setBusy(false)}}
 useEffect(()=>{
  let alive=true,timer,stopTiming,connecting=false,hasConnected=false;
  const acceptNotices=events=>{
   const dismissed=new Set(events.filter(e=>e.kind==='dismiss_confirm').flatMap(e=>e.ids));
   if(dismissed.size)setMessages(v=>v.filter(item=>!dismissed.has(item.id)));
   const notices=events.filter(e=>e.kind==='message'||e.kind==='confirm');
   if(notices.length)setMessages(v=>[...v,...notices.filter(n=>(!n.id||!dismissed.has(n.id))&&(!n.id||!v.some(old=>old.id===n.id)))]);
  };
  async function connect(bridge){
   if(!alive||connecting)return;connecting=true;
   async function poll(){
    if(!alive)return;
    try{
     const state=await call(bridge,'poll',1000);if(!alive)return;
     // The window is being destroyed. pywebview has to marshal every bridge
     // result back through evaluate_js() on the UI thread; starting another
     // long poll here would strand a non-daemon thread and hang process exit.
     if(state.closed){alive=false;return}
     setRunning(state.running);setStatus(state.status);
     const entries=state.events.filter(e=>e.kind==='log').map(e=>({...e,type:e.level==='warning'?'warning':e.level==='error'?'error':'info'}));
     appendLogs(entries);
     acceptNotices(state.events);
     timer=setTimeout(poll,50);
    }catch(error){
     if(!alive)return;
     setStatus('连接中断，正在重连…');setReady(false);
     connecting=false;
     timer=setTimeout(()=>connect(window.pywebview?.api||bridge),1000);
    }
   }
   try{
    const data=await call(bridge,'bootstrap');if(!alive)return;
    if(!hasConnected){
     savedPrefs.current=data.settings;
     setPrefs(data.settings);
     void checkUpdate(bridge,()=>alive);
    }
    if(data.version)setVersion(data.version);
    setBridgeTiming(data.profile_ui);
    if(data.profile_ui&&!stopTiming)stopTiming=installUITiming((stage,ms)=>call(bridge,'report_ui_timing',stage,ms));
    hasConnected=true;setApi(bridge);setReady(true);poll();
   }catch(error){
    if(!alive)return;connecting=false;setReady(false);setStatus('连接中断，正在重连…');
    timer=setTimeout(()=>connect(window.pywebview?.api||bridge),1000);
   }
  }
  const stop=()=>{alive=false;clearTimeout(timer);stopTiming?.()};
  const unwatch=watchBridge(connect,()=>{if(alive&&!hasConnected)setReady(true)});
  window.addEventListener('pagehide',stop);
  return()=>{stop();unwatch();window.removeEventListener('pagehide',stop)};
 },[]);
 function navigate(next){if(running||busy){message('请先停止当前任务，再切换页面。','任务运行中','warning');return}if(next==='settings'){setLastPage(page);setPrefs(structuredClone(savedPrefs.current));}setPage(next)}
 function updateFile(id,path){if(!path)return;if(id==='pim')setPimFile(path);else setRows(v=>v.map(r=>r.id===id?{...r,file:path}:r))}
 function pick(id){if(!api){fileTarget.current=id;previewFile.current.click();return}action(async()=>updateFile(id,await request('choose_path','excel')))}
 function generate(id){
  setGeneration({id,pc:[],mobile:[],split:false,addPrefix:false,filters:{pc:{keyword:'',mode:'all'},mobile:{keyword:'',mode:'all'}}});
  setModal('generate');
 }
 async function addSources(target,paths){
  const expanded=await request('expand_image_sources',paths);
  if(!expanded.length){message('没有找到支持的图片。');return}
  const {keyword,mode}=generation.filters[target];
  const images=filterImages(expanded,keyword,mode);
  if(!images.length){message('没有图片符合关键字筛选条件。');return}
  setGeneration(current=>current&&({...current,[target]:[...current[target],...images]}));
 }
 function pickImageSources(target){action(async()=>{
  const result=await request('choose_path','image_sources');
  if(result?.length)await addSources(target,Array.isArray(result)?result:[result]);
 })}
 useEffect(()=>{
  if(modal!=='generate'||busy)return;
  function onDrop({detail}){
   const zone=document.elementFromPoint(detail.x,detail.y)?.closest('[data-image-zone]');
   if(!zone)return;
   if(detail.paths.length)action(()=>addSources(zone.dataset.imageZone,detail.paths));
   else message('未取得本地路径，请点击添加。');
  }
  window.addEventListener('config-image-drop',onDrop);
  return()=>window.removeEventListener('config-image-drop',onDrop);
 },[modal,busy,api,generation?.filters]);
 function editGeneratedConfig(){action(async()=>{
  const {pc,mobile,split,addPrefix}=generation;
  const preview=await request('preview_image_config',pc,split?mobile:null,addPrefix,unmatched?.pairs??null);
  setEditor({headers:configHeaders,rows:preview,original:JSON.stringify(preview)});
  setModal('generated-editor');
 })}
 function editTextConfig(){
  const values=generation.text.split(/\r\n|\n|\r/).map(name=>name.trim()).filter(Boolean);
  if(!values.length)return;
  const rows=values.map(name=>[name,name,name]);
  setEditor({headers:configHeaders.slice(0,3),rows,original:JSON.stringify(rows)});
  setModal('generated-editor');
 }
 function saveGeneratedConfig(values){action(async()=>{
  const path=await request('save_image_config',values,generation.text!==undefined,generation.id==='pim'?'pim':'deedraw');
  updateFile(generation.id,path);
  setModal(null);
  setGeneration(null);
  setEditor(null);
 })}
 function editConfig(path,id){action(async()=>{
  const data=await request('load_data',path,rows.find(row=>row.id===id)?.mode==='modify');
  setEditor({...data,path,original:JSON.stringify(data.rows)});
  setModal('file-editor');
 })}
 function ask(text){return new Promise(resolve=>setMessages(v=>[...v,{kind:'decision',title:'提示',text,resolve}]))}
 function copyReport(report){action(async()=>{
  await request('write_clipboard',report.text);
  setCopiedReport(report);
 })}
 function importFieldConfig(){action(async()=>{
  const config=await request('import_field_config');
  if(!config)return;
  setRows(config.fields.map(field=>({...field,mode:field.mode??config.mode,id:crypto.randomUUID()})));
  setFieldPage(0);
  setConflictPolicy(null);
  if(config.pim){
   setPimFile(config.pim.file);
   setPimOptions(config.pim.options);
   setPreset(config.pim.preset);
  }
 })}
 function exportFieldConfig(){action(async()=>{
  const path=await request('export_field_config',{
   version:1,mode:rows.every(row=>row.mode==='modify')?'modify':'add',
   fields:rows.map(({code,file,mode,options,rename=false})=>({code,file,mode,options,rename})),
   pim:{file:pimFile,options:pimOptions,preset}
  });
  if(path)message('已导出配置\n'+path,'导出成功');
 })}
 function openTaskConfirmation(){
  if(page!=='deedraw'||rows.every(row=>row.mode==='modify')){begin();return}
  setConflictPolicy(null);
  setModal('confirm-start');
 }
 function begin(){action(async()=>{
  const payload=page==='deedraw'?{fields:rows,conflict_policy:conflictPolicy}:{file:pimFile,options:pimOptions,preset};
  await request('start_task',page,payload);setRunning(true);
 })}
 function stop(){action(async()=>{await request('stop_task');setMessages(v=>v.filter(m=>m.kind!=='confirm'));setStatus('正在终止...')})}
 async function closeMessage(answer=false){
  const item=messages[0];setCopiedReport(null);setMessages(v=>v.slice(1));
  if(item?.kind==='decision')item.resolve(answer);
  if(item?.kind==='confirm')try{await request('respond',item.id,answer)}catch(e){message(e.message,'错误','error')}
 }
 const unmatched=modal==='generate'&&generation?.split?matchSplitImages(generation.pc,generation.mobile):null;
 const locked=running||busy||!ready;
 function options(value,onChange,disabled=false){return <ExecutionOptions value={value} onChange={onChange} disabled={disabled}/>}
 const jsonConfigMenu=<FileConfigMenu disabled={locked} icon={SlidersHorizontal} label="配置导入与导出"
  items={[['导入 JSON',importFieldConfig],['导出 JSON',exportFieldConfig]]}/>;
 function fileRow(path,id){return <div className="file-row"><FileSpreadsheet size={18}/><span title={path} onDoubleClick={()=>action(()=>request('open_file',path))}>{path?basename(path):'未选择配置文件'}</span><FileConfigMenu disabled={locked} items={[
  ['选择配置文件',()=>pick(id)],
  ['从图片生成配置',()=>generate(id)],
  ['从文本生成配置',()=>{setGeneration({id,text:''});setModal('generate-text')}]
 ]}/><button className="icon-button" title="查看数据" aria-label="查看数据" onClick={()=>action(()=>request('open_file',path))}><ExternalLink size={15}/></button>{path&&<button className="icon-button" title="编辑配置" aria-label="编辑配置" onClick={()=>editConfig(path,id)}><Pencil size={15}/></button>}</div>}
 return <div className={'app desktop-app '+(page==='settings'?'settings-view':'')}>
  <input hidden type="file" accept=".xlsx" ref={previewFile} onChange={e=>{const file=e.target.files[0];if(file)updateFile(fileTarget.current,file.name);e.target.value=''}}/>
  {page==='settings'?<header className="settings-header"><button className="back-button" aria-label="返回主页" disabled={busy} onClick={()=>navigate(lastPage)}><ChevronLeft size={20}/>返回</button><h1>设置</h1></header>:<aside><div className="window-header"><div className="brand"><div>DDAS <b>PLUS</b></div></div><div className="window-controls"><button className="update-trigger" title={update.available?'更新 · 有新版本':'更新'} aria-label="更新"
   aria-description={update.available?'有新版本可用':undefined} onClick={openUpdate}>
   <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M0 0h24v24H0z" fill="none"/>
    <path fill="currentColor" d="M12.3 7.29c.2-.18.44-.29.7-.29c.27 0 .5.11.71.29c.19.21.29.45.29.71c0 .27-.1.5-.29.71c-.21.19-.44.29-.71.29c-.26 0-.5-.1-.7-.29c-.19-.21-.3-.44-.3-.71c0-.26.11-.5.3-.71m-2.5 4.68s2.17-1.72 2.96-1.79c.74-.06.59.79.52 1.23l-.01.06c-.14.53-.31 1.17-.48 1.78c-.38 1.39-.75 2.75-.66 3c.1.34.72-.09 1.17-.39c.06-.04.11-.08.16-.11c0 0 .08-.08.16.03c.02.03.04.06.06.08c.09.14.14.19.02.27l-.04.02c-.22.15-1.16.81-1.54 1.05c-.41.27-1.98 1.17-1.74-.58c.21-1.23.49-2.29.71-3.12c.41-1.5.59-2.18-.33-1.59c-.37.22-.59.36-.72.45c-.11.08-.12.08-.19-.05l-.03-.06l-.05-.08c-.07-.1-.07-.11.03-.2M22 12c0 5.5-4.5 10-10 10S2 17.5 2 12S6.5 2 12 2s10 4.5 10 10m-2 0c0-4.42-3.58-8-8-8s-8 3.58-8 8s3.58 8 8 8s8-3.58 8-8"/>
   </svg>{update.available&&<span className="update-dot" aria-hidden="true"/>}
  </button><button title="设置" aria-label="设置" className={page==='settings'?'active':''} onClick={()=>navigate(page==='settings'?lastPage:'settings')}><Settings size={17}/></button></div></div><nav>{[['deedraw','深绘'],['pim','PIM']].map(([id,label])=><button key={id} className={page===id?'active':''} onClick={()=>navigate(id)}>{label}</button>)}</nav></aside>}
  <main><div className={'workspace '+(page==='settings'?'settings-page':'')}>
   {!ready?<div className="loading">正在连接…</div>:page==='settings'?<>
    <fieldset disabled={locked}><section><SectionTitle icon={Monitor} title="浏览器"/><div className="inline"><input aria-label="浏览器路径" value={prefs.chrome_path} onChange={e=>setPrefs({...prefs,chrome_path:e.target.value})}/><button onClick={()=>action(async()=>{const path=await request('choose_path','browser');if(path)setPrefs({...prefs,chrome_path:path})})}>浏览</button><button onClick={()=>action(()=>request('test_browser',prefs.chrome_path))}>测试</button><button onClick={()=>action(()=>request('download_browser'))}>下载 Chrome</button></div><label className="checkbox settings-check"><input type="checkbox" checked={prefs.browser_settings.auto_close} onChange={e=>setPrefs({...prefs,browser_settings:{auto_close:e.target.checked}})}/>任务完成后自动关闭浏览器</label></section>
    <section><SectionTitle icon={FolderOpen} title="文件与日志"/>{[['log_export_path','日志目录'],['config_path','配置目录']].map(([key,label])=><div className="settings-row" key={key}><label htmlFor={key}>{label}</label><input id={key} value={prefs[key]} onChange={e=>setPrefs({...prefs,[key]:e.target.value})}/><button onClick={()=>action(async()=>{const path=await request('choose_path','directory');if(path)setPrefs({...prefs,[key]:path})})}>浏览</button></div>)}</section>
    <section><SectionTitle icon={SlidersHorizontal} title="PIM"/><div className="inline"><span>默认像素大小</span>{['750','790'].map(value=><label className="checkbox" key={value}><input type="radio" name="pixels" checked={prefs.pim_settings.pixel_size===value} onChange={()=>setPrefs({...prefs,pim_settings:{pixel_size:value}})}/>{value}px</label>)}</div></section></fieldset>

   </>:<>
    <fieldset disabled={locked}>
     {page==='deedraw'?<>
      <section className="task-config"><SectionTitle icon={SlidersHorizontal} title="配置" iconControl={jsonConfigMenu}
        accessory={<button type="button" className="deedraw-mode-tag"
         aria-label={rows[fieldPage]?.mode==='modify'?'修改选项，点击切换为新增':'新增选项，点击切换为修改'}
         onClick={()=>setRows(rows=>rows.map((row,index)=>index===fieldPage?{...row,mode:row.mode==='modify'?'add':'modify'}:row))}>
         {rows[fieldPage]?.mode==='modify'?'修改选项':'新增选项'}
        </button>}
        action={<div className="field-actions"><span className="field-page-number" role="status" aria-label="字段页码">{fieldPage+1}/{rows.length}</span><button className="text-button" onClick={()=>{setRows(v=>[...v,blankField()]);setFieldPage(rows.length)}}><Plus size={16}/>添加字段</button><button className="icon-button" aria-label="删除当前字段" disabled={rows.length===1} onClick={()=>{setRows(v=>v.filter((_,i)=>i!==fieldPage));setFieldPage(v=>Math.min(v,rows.length-2))}}><Trash2 size={16}/></button></div>}/>
       <div className="config-content field-carousel"><SwipeViewport page={fieldPage} count={rows.length} onPageChange={setFieldPage} disabled={locked}><div className="field-track">{rows.map((r,i)=><div className="field-card field-slide" key={r.id} inert={i!==fieldPage?true:undefined}><div className="field-top file-row field-input-row"><Tag size={18}/><input aria-label="字段名称或编码" placeholder="字段名称 / 编码" value={r.code} onChange={e=>setRows(v=>v.map(x=>x.id===r.id?{...x,code:e.target.value}:x))}/></div>{fileRow(r.file,r.id)}
       <ExecutionOptions value={r.options} optionLabels={r.mode==='modify'?modifyLabels:labels} onChange={(index,checked)=>setRows(rows=>rows.map(row=>row.id===r.id?{...row,
        options:row.options.map((value,i)=>i===index?checked:value)
       }:row))}>
        {r.mode==='modify'&&<label className="execution-option"><input type="checkbox" checked={!!r.rename}
         onChange={event=>setRows(rows=>rows.map(row=>row.id===r.id?{...row,rename:event.target.checked}:row))}/>修改选项名</label>}
       </ExecutionOptions>
       </div>)}</div></SwipeViewport>
       {rows.length>1&&<>
        <button className="field-arrow previous" type="button" aria-label="上一个字段" disabled={fieldPage===0} onClick={()=>setFieldPage(fieldPage-1)}><ChevronLeft size={18}/></button>
        <button className="field-arrow next" type="button" aria-label="下一个字段" disabled={fieldPage===rows.length-1} onClick={()=>setFieldPage(fieldPage+1)}><ChevronRight size={18}/></button>
       </>}</div>
      </section>
      {rows[fieldPage]?.mode==='modify'&&<div className="tip"><Info size={17}/><p>勾选的图片或选项值按配置文件逐行修改，对应单元格留空时清空该项。<br/>未勾选的项会跳过。</p></div>}
     </>:<><section className="task-config"><SectionTitle icon={SlidersHorizontal} title="配置" iconControl={jsonConfigMenu}/><div className="config-content">{fileRow(pimFile,'pim')}{options(pimOptions,(index,checked)=>setPimOptions(v=>v.map((x,k)=>k===index?checked:x)),preset)}<label className="preset checkbox"><input type="checkbox" checked={preset} onChange={e=>{setPreset(e.target.checked);if(e.target.checked)setPimOptions([false,false,false,false])}}/>配置预设模块</label></div></section>
      <div className="tip"><Info size={17}/><p>提示：PC图和移动图目前只能二选一，后上传的图片会覆盖先上传的图片。<br/>开始前请在 PIM 页面打开文案列表 → 配置映射 → 添加文案字段 → 选择组件类型。</p></div>
     </>}
    </fieldset>

   </>}
  </div>{page==='settings'?<div className="action-row"><div className="inline"><button className="primary" disabled={locked} onClick={()=>action(async()=>{const value=await request('save_settings',prefs);savedPrefs.current=value;setPrefs(value);setPage(lastPage)})}><Check size={15}/>保存</button></div></div>:<div className="task-footer"><div className="action-row"><div className="inline"><button disabled={!running||busy} onClick={stop}><Square size={14}/>终止</button><button className="primary" disabled={locked} onClick={openTaskConfirmation}><Play size={15}/>开始任务</button></div></div><LogPanel busy={busy} onClear={()=>action(async()=>{if(api)await request('clear_log');clearLogs()})} onExport={()=>action(()=>request('export_log'))}/></div>}</main>
  {modal==='confirm-start'&&<Overlay title="已有选项冲突处理" onClose={()=>setModal(null)}>
   <div className="conflict-policy" role="radiogroup" aria-label="已有选项冲突处理" aria-required="true">
    <label className="checkbox">
     <input type="radio" name="conflict-policy" checked={conflictPolicy==='skip'} onChange={()=>setConflictPolicy('skip')}/>
     跳过
    </label>
    <label className="checkbox">
     <input type="radio" name="conflict-policy" checked={conflictPolicy==='overwrite'} onChange={()=>setConflictPolicy('overwrite')}/>
     覆盖
    </label>
    <p>逐个覆盖同名选项。先清空原有内容，再按所选内容进行回填。</p>
   </div>
   <div className="modal-actions message-actions">
    <button type="button" onClick={()=>setModal(null)}>取消</button>
    <button type="button" className="primary" disabled={locked||!conflictPolicy}
     onClick={()=>{setModal(null);begin()}}>确认开始</button>
   </div>
  </Overlay>}
  {modal==='changelog'&&<Overlay title="更新" onClose={()=>setModal(null)}>
   <div className="update-check">
    <p>当前版本 v{version}</p>
    <p role="status">{update.state==='checking'?'正在检查 GitHub 发布版本…':
     update.state==='error'?update.message:
     update.state==='ready'?(update.available?'发现新版本 '+update.tag:'当前版本已是最新'):'检查 GitHub 上的正式版本'}</p>
    <div className="inline">
     <button disabled={!api||update.state==='checking'} onClick={()=>checkUpdate(api)}>检查更新</button>
     <button className={update.available?'primary':undefined} disabled={!api||busy}
      onClick={()=>action(()=>request('open_release',update.available?update.tag:null))}>
      <ExternalLink size={14}/>{update.available?'前往下载':'GitHub 发布页'}
     </button>
    </div>
   </div><div className="changelog">{CHANGELOG.map(entry=><section className="changelog-release" key={entry.title}><div className="changelog-version"><b>{entry.title}</b>{entry.version&&entry.version===version&&<span className="changelog-current">当前版本</span>}</div><ul>{entry.items.map((item,i)=><li key={i}>{item}</li>)}</ul></section>)}</div></Overlay>}
  {(modal==='file-editor'||modal==='generated-editor')&&<SpreadsheetEditor
   data={editor} busy={busy} title="配置编辑"
   saveLabel={modal==='generated-editor'?'生成配置':'保存'}
   onClose={()=>{setEditor(null);setModal(modal==='generated-editor'?(generation.text===undefined?'generate':'generate-text'):null)}}
   onAsk={ask} onMessage={message}
   onSave={modal==='generated-editor'?saveGeneratedConfig:values=>action(async()=>{
    await request('save_data',editor.path,values,editor.token);
    setModal(null);
    setEditor(null);
   })}
   readClipboard={()=>request('read_clipboard')} writeClipboard={value=>request('write_clipboard',value)}/>}
  {modal==='generate-text'&&<Overlay fullWindow title="从文本生成配置" onClose={()=>{setModal(null);setGeneration(null)}}>
   <div className="generation-workspace">
    <textarea className="generation-text" aria-label="选项名，每行一个" placeholder="每行输入一个选项名"
     value={generation.text} onChange={event=>setGeneration(current=>({...current,text:event.target.value}))}/>
   </div>
   <div className="modal-actions generation-actions">
    <button className="primary" disabled={!generation.text.trim()} onClick={editTextConfig}>配置编辑</button>
   </div>
  </Overlay>}
  {modal==='generate'&&generation&&<Overlay fullWindow title="从图片生成配置" onClose={()=>{if(!busy){setModal(null);setGeneration(null)}}}>
    <div className="generation-workspace">
    <div className="generation-switches">
     <label className="checkbox">
      <input type="checkbox" checked={generation.addPrefix} disabled={busy}
       onChange={e=>setGeneration({...generation,addPrefix:e.target.checked})}/>将目录名加入选项名前缀
     </label>
     <label className="checkbox">
      <input type="checkbox" role="switch" checked={generation.split} disabled={busy}
       onChange={e=>setGeneration({...generation,split:e.target.checked})}/>PC / 移动图分开选择
     </label>
    </div>
    <div className={'generation-zones '+(generation.split?'split':'')}>
     {(generation.split?['pc','mobile']:['pc']).map(target=>{
      const label=generation.split?(target==='pc'?'PC 图':'移动图'):'图片';
      const filter=generation.filters[target];
      function updateFilter(key,value){
       setGeneration(current=>({...current,filters:{...current.filters,[target]:{...current.filters[target],[key]:value}}}));
      }
      return <div className="generation-source" key={target}>
       {generation.split&&<strong className="generation-source-label">{label}</strong>}
       <div className="generation-filter">
        <ImageFilterMenu label={label} mode={filter.mode} disabled={busy}
         onChange={mode=>updateFilter('mode',mode)}/>
        <input aria-label={label+'文件名关键字'} placeholder="文件名关键字" value={filter.keyword}
         disabled={busy||filter.mode==='all'} onChange={e=>updateFilter('keyword',e.target.value)}/>
       </div>
       <div className="generation-zone" data-image-zone={target} onDragOver={e=>e.preventDefault()}
        onClick={e=>{if(!e.target.closest('button,li'))pickImageSources(target)}}>
        <div className={'generation-zone-toolbar '+(generation[target].length?'has-images':'')}>
         <button type="button" className="generation-prompt" disabled={busy}
          onClick={()=>pickImageSources(target)}>拖入图片或目录，或点击添加</button>
         {generation[target].length>0&&<button type="button" className="icon-button generation-clear"
          aria-label={'清空'+label+'列表'} disabled={busy}
          onClick={()=>setGeneration(current=>({...current,[target]:[]}))}>清空</button>}
        </div>
        <ul aria-label={label+'来源'}>{generation[target].map(({path},index)=><li key={index}>
         <span className={unmatched?.[target].has(index)?'generation-unmatched':undefined} title={unmatched?.[target].has(index)?'无法唯一配对：'+path:path}>{path}</span>
         <button className="icon-button" aria-label={'移除 '+path} disabled={busy}
          onClick={()=>setGeneration(current=>({...current,[target]:current[target].filter((_,i)=>i!==index)}))}><Trash2 size={15}/></button>
        </li>)}</ul>
       </div>
      </div>;
     })}
    </div>
    </div>
    <div className="modal-actions generation-actions">
     <button className="primary" disabled={busy||!(generation.pc.length||(generation.split&&generation.mobile.length))}
      onClick={editGeneratedConfig}>配置编辑</button>
    </div>
  </Overlay>}
  {updateNotice&&!modal&&!messages.length&&!running&&!busy&&<Overlay title="发现新版本" onClose={()=>setUpdateNotice(null)}>
   <p className="message-text">DDAS PLUS {updateNotice} 已发布。当前版本 v{version}。</p>
   <div className="modal-actions message-actions">
    <button type="button" onClick={()=>setUpdateNotice(null)}>稍后</button>
    <button type="button" className="primary" disabled={!api} onClick={()=>{
     const tag=updateNotice;
     setUpdateNotice(null);
     action(()=>request('open_release',tag));
    }}>前往下载</button>
   </div>
  </Overlay>}
  {messages[0]&&<Overlay title={messages[0].title} onClose={()=>closeMessage(false)} priority><div className="message-text">{messages[0].text}</div><div className="modal-actions message-actions">{messages[0].kind==='message'&&/(^|\n)总任务数：/.test(messages[0].text)&&
   <button type="button" disabled={busy} onClick={()=>copyReport(messages[0])}>{copiedReport===messages[0]?'已复制':'复制报告'}</button>}
   {['confirm','decision'].includes(messages[0].kind)&&<button onClick={()=>closeMessage(false)}>否</button>}<button className="primary" onClick={()=>closeMessage(true)}>{['confirm','decision'].includes(messages[0].kind)?'是':'确定'}</button></div></Overlay>}
 </div>
}
function FileConfigMenu({disabled,items,icon:Icon,label="配置数据"}){
 const trigger=useRef(null),menu=useRef(null);
 const [position,setPosition]=useState(null);
 const open=position!==null&&!disabled;
 useEffect(()=>{
  if(disabled)setPosition(null);
 },[disabled]);
 useEffect(()=>{
  if(!open)return;
  function close(){setPosition(null)}
  function closeOutside(event){
   if(!trigger.current?.contains(event.target)&&!menu.current?.contains(event.target))close();
  }
  function handleKey(event){
   if(event.key!=='Escape')return;
   event.preventDefault();
   close();
   trigger.current?.focus();
  }
  document.addEventListener('pointerdown',closeOutside);
  document.addEventListener('keydown',handleKey);
  window.addEventListener('resize',close);
  window.addEventListener('scroll',close,true);
  menu.current?.querySelector('button')?.focus({preventScroll:true});
  return()=>{
   document.removeEventListener('pointerdown',closeOutside);
   document.removeEventListener('keydown',handleKey);
   window.removeEventListener('resize',close);
   window.removeEventListener('scroll',close,true);
  };
 },[open]);
 function toggle(){
  if(open){setPosition(null);return}
  const rect=trigger.current.getBoundingClientRect();
  const above=window.innerHeight-rect.bottom<120&&rect.top>120;
  setPosition({
   left:Math.max(4,Math.min(Icon?rect.left:rect.right-156,window.innerWidth-160)),
   ...(above?{bottom:window.innerHeight-rect.top+4}:{top:rect.bottom+4})
  });
 }
 return <>
  <button ref={trigger} className={Icon?"section-icon-trigger":"file-menu-trigger"} type="button" disabled={disabled} aria-label={label}
   aria-expanded={open} onClick={toggle}>{Icon?<Icon size={16}/>:label}</button>
  {open&&createPortal(<div className="file-menu-popup" ref={menu} style={position}
   role="group" aria-label={label} onBlur={event=>{
    if(event.relatedTarget&&!menu.current?.contains(event.relatedTarget)&&event.relatedTarget!==trigger.current)setPosition(null);
   }}>
   {items.map(([label,action])=><button type="button" key={label} onClick={()=>{
    setPosition(null);
    trigger.current?.focus({preventScroll:true});
    action();
   }}>{label}</button>)}
  </div>,document.body)}
 </>;
}
const imageFilterModes=[['all','全部图片'],['include','只添加匹配图片'],['exclude','排除匹配图片']];

function ImageFilterMenu({label,mode,disabled,onChange}){
 const menu=useRef(null),trigger=useRef(null);
 const [open,setOpen]=useState(false);
 const expanded=open&&!disabled;
 const selectedLabel=imageFilterModes.find(([id])=>id===mode)[1];
 useEffect(()=>{
  if(!expanded)return;
  function closeOutside(event){
   if(!menu.current?.contains(event.target))setOpen(false);
  }
  document.addEventListener('pointerdown',closeOutside);
  return()=>document.removeEventListener('pointerdown',closeOutside);
 },[expanded]);
 useEffect(()=>{if(disabled)setOpen(false)},[disabled]);
 function close(){
  setOpen(false);
  trigger.current.focus();
 }
 return <div ref={menu} className="generation-filter-mode" onKeyDown={event=>{
  if(event.key!=='Escape'||!expanded)return;
  event.stopPropagation();
  close();
 }}>
  <button ref={trigger} className="generation-filter-trigger" type="button"
   aria-label={label+'筛选方式：'+selectedLabel} aria-expanded={expanded}
   disabled={disabled} onClick={()=>setOpen(value=>!value)}>
   {selectedLabel}<ChevronDown size={14} aria-hidden="true"/>
  </button>
  {expanded&&<div className="generation-filter-options" role="group" aria-label={label+'筛选方式'}>
   {imageFilterModes.map(([id,name])=><button type="button" key={id} aria-pressed={mode===id}
    onClick={()=>{onChange(id);close()}}>{name}{id===mode&&<Check size={13} aria-hidden="true"/>}</button>)}
  </div>}
 </div>;
}
function ExecutionOptions({value,disabled=false,onChange,optionLabels=labels,children}){
 return <div className="execution-options">{optionLabels.map((label,index)=><label className="execution-option" key={label}><input type="checkbox" disabled={disabled} checked={value[index]} onChange={event=>onChange(index,event.target.checked)}/><span>{label}</span></label>)}{children}</div>;
}
function SectionTitle({icon:Icon,title,action,accessory,iconControl}){return <div className="section-title">{iconControl??<Icon size={18}/>}<h2>{title}</h2>{accessory}{action&&<div className="section-action">{action}</div>}</div>}
function Overlay({title,onClose,children,wide=false,priority=false,fullWindow=false}){
 const ref=useRef(),close=useRef(onClose);close.current=onClose;
 useEffect(()=>{const before=document.activeElement;ref.current?.focus();return()=>{if(before?.isConnected)before.focus()}},[]);
 function keyDown(event){
  if(event.key==='Escape'){event.stopPropagation();close.current();return}
  if(event.key!=='Tab')return;
  const items=[...ref.current.querySelectorAll('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),summary:not([aria-disabled="true"]),[tabindex="0"]')].filter(item=>item.getClientRects().length);
  if(!items.length){event.preventDefault();return}
  const first=items[0],last=items[items.length-1];
  if(event.shiftKey&&(document.activeElement===first||document.activeElement===ref.current)){event.preventDefault();last.focus()}
  else if(!event.shiftKey&&(document.activeElement===last||document.activeElement===ref.current)){event.preventDefault();first.focus()}
 }
 return <div className={'overlay '+(priority?'message-overlay':'')+(fullWindow?' window-overlay':'')}><div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className={'modal '+(wide?'wide':'')} onKeyDown={keyDown}><div className="modal-header"><h2>{title}</h2><button className="icon-button" aria-label="关闭" onClick={onClose}><X size={19}/></button></div>{children}</div></div>
}
createRoot(document.getElementById('root')).render(<App/>);
