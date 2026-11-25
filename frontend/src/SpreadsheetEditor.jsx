import React,{useEffect,useRef,useState} from 'react';
import {X,Plus,Undo2,Redo2,Check,ArrowUp,ArrowDown,ArrowDownUp,Search,ChevronDown} from 'lucide-react';
import {emptyRow,encodeTSV,parseTSV,pasteCells,sortRows,mergeRows,findCells,replaceCells} from './sheet';
export default function SpreadsheetEditor({data,busy,title,saveLabel,onClose,onAsk,onMessage,onSave,readClipboard,writeClipboard}){
 const [rows,setRows]=useState(data.rows),[selection,setSelection]=useState({a:0,b:0,c:0,d:0,whole:false}),[editing,setEditing]=useState(null),[menu,setMenu]=useState(null),[prefix,setPrefix]=useState(''),[suffix,setSuffix]=useState(''),[columns,setColumns]=useState([true,false,false]),[scroll,setScroll]=useState(0);
 const [sort,setSort]=useState(null);
 const [tool,setTool]=useState(null);
 const searchOpen=tool==='search';
 const [query,setQuery]=useState(''),[replacement,setReplacement]=useState(''),[match,setMatch]=useState(null);
 const [wildcards,setWildcards]=useState(false);
 const [rememberedRows,setRememberedRows]=useState(()=>{
  try{return JSON.parse(localStorage.getItem('ddas.merge.selectedRows'))??{}}
  catch{return {}}
 });
 const [feedback,setFeedback]=useState('');
 const root=useRef(),viewport=useRef(),undo=useRef([]),redo=useRef([]),selectionDrag=useRef(null);
 useEffect(()=>{const previous=document.activeElement;root.current.focus();return()=>previous?.isConnected&&previous.focus()},[]);
 const width=data.headers.length;
 const wholeRows=selection.whole==='row'||selection.whole==='all';
 const wholeColumns=selection.whole==='column'||selection.whole==='all';
 const lastRow=Math.max(0,rows.length-1);
 const top=wholeColumns?0:Math.min(lastRow,selection.a,selection.b);
 const bottom=wholeColumns?lastRow:Math.min(lastRow,Math.max(selection.a,selection.b));
 const left=wholeRows?0:Math.min(selection.c,selection.d),right=wholeRows?width-1:Math.max(selection.c,selection.d);
 const searchRange=wholeRows||wholeColumns||top!==bottom||left!==right?{top,bottom,left,right}:undefined;
 const canMerge=!wholeColumns&&top<bottom&&bottom<rows.length;
 const mergeConflicts=tool==='merge'&&canMerge?data.headers.flatMap((header,column)=>{
  const options=[];
  for(let row=top;row<=bottom;row++){
   const value=rows[row][column];
   if(value.trim())options.push([value,row]);
  }
  return new Set(options.map(([value])=>value)).size>1?[{header,column,options}]:[];
 }):[];
 const retained=Object.fromEntries(mergeConflicts.flatMap(({column,options})=>{
  const offset=rememberedRows[column];
  const row=Number.isInteger(offset)?top+offset:-1;
  return options.some(([,candidate])=>candidate===row)?[[column,row]]:[];
 }));
 function rememberRow(column,row){
  const next={...rememberedRows,[column]:row-top};
  setRememberedRows(next);
  try{localStorage.setItem('ddas.merge.selectedRows',JSON.stringify(next))}catch{}
 }
 function change(next){if(busy)return;setMatch(null);setFeedback('');setSort(null);undo.current.push(rows);if(undo.current.length>50)undo.current.shift();redo.current=[];setRows(next)}
 function history(back){const source=back?undo:redo,target=back?redo:undo;if(!source.current.length||busy)return;target.current.push(rows);setMatch(null);setFeedback('');setSort(null);setRows(source.current.pop());setEditing(null)}
 async function close(){if(busy)return;if(JSON.stringify(rows)!==data.original&&!await onAsk('数据尚未保存，是否放弃修改？'))return;onClose()}
 function choose(r,c,whole=false,extend=false){setMatch(null);setSelection(v=>extend&&v.whole===whole?{...v,b:r,d:c,whole}:{a:r,b:r,c,d:c,whole});setMenu(null);setEditing(null);root.current.focus()}
 function selectHeader(event,axis,index){
  if(event.button!==0||busy)return;
  event.preventDefault();
  viewport.current.setPointerCapture(event.pointerId);
  selectionDrag.current={id:event.pointerId,axis,index};
  choose(axis==='row'?index:0,axis==='column'?index:0,axis,event.shiftKey);
 }
 function startCellSelection(event,r,c){
  if(event.button!==0||busy||event.target.closest('input'))return;
  selectionDrag.current={id:event.pointerId,axis:'cell',r,c};
  choose(r,c,false,event.shiftKey);
 }
 function moveSelection(event){
  const drag=selectionDrag.current;
  if(!drag||drag.id!==event.pointerId)return;
  const header=document.elementFromPoint(event.clientX,event.clientY)?.closest('[data-sheet-axis]');
  if(header?.dataset.sheetAxis!==drag.axis||!viewport.current.contains(header))return;
  if(drag.axis==='cell'){
   const r=Number(header.dataset.sheetRow),c=Number(header.dataset.sheetIndex);
   if(r===drag.r&&c===drag.c)return;
   if(!viewport.current.hasPointerCapture(event.pointerId))viewport.current.setPointerCapture(event.pointerId);
   drag.r=r;
   drag.c=c;
   choose(r,c,false,true);
   return;
  }
  const index=Number(header.dataset.sheetIndex);
  if(index===drag.index)return;
  drag.index=index;
  choose(drag.axis==='row'?index:0,drag.axis==='column'?index:0,drag.axis,true);
 }
 function stopSelection(event){
  if(selectionDrag.current?.id===event.pointerId)selectionDrag.current=null;
 }
 function clear(){change(rows.map((r,i)=>r.map((v,j)=>i>=top&&i<=bottom&&j>=left&&j<=right?'':v)))}
 const copied=()=>encodeTSV(rows.slice(top,bottom+1).map(r=>r.slice(left,right+1)));
 async function copy(cut=false){try{await writeClipboard(copied());if(cut)clear();setMenu(null)}catch(e){onMessage(e.message,'错误')}}
 function paste(text,replace=false){try{const grid=parseTSV(text,width);if(grid.some(row=>row.length>width))throw Error(`粘贴内容超出 ${width} 列`);change(replace?[...rows.slice(0,top),...grid.map(r=>[...r,...emptyRow(width)].slice(0,width)),...rows.slice(bottom+1)]:pasteCells(rows,grid,top,wholeRows?0:left,width));setMenu(null)}catch(e){onMessage(e.message,'错误')}}
 async function fromClipboard(replace=false){try{paste(await readClipboard(),replace)}catch(e){onMessage(e.message,'错误')}}
 function key(event){
  if(event.key==='Escape'){if(editing){setEditing(null);root.current.focus()}else if(menu)setMenu(null);else close();event.preventDefault();return}
  if(editing||event.target!==root.current)return;
  const mod=event.metaKey||event.ctrlKey;
  if(mod&&event.key.toLowerCase()==='a'){event.preventDefault();choose(0,0,'all');return}
  if(mod&&event.key.toLowerCase()==='z'){event.preventDefault();history(!event.shiftKey);return}
  if(mod&&event.key.toLowerCase()==='s'){event.preventDefault();if(rows.length&&!busy)onSave(rows);return}
  if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();clear();return}
  if(event.key==='Enter'||event.key==='F2'){event.preventDefault();setEditing({r:top,c:left,value:rows[top]?.[left]||''});return}
  const delta={ArrowDown:[1,0],ArrowUp:[-1,0],ArrowLeft:[0,-1],ArrowRight:[0,1],Tab:[0,event.shiftKey?-1:1]}[event.key];
  if(delta){event.preventDefault();const r=Math.max(0,Math.min(rows.length-1,selection.b+delta[0])),c=Math.max(0,Math.min(width-1,selection.d+delta[1]));choose(r,c,false,event.shiftKey&&event.key!=='Tab');const box=viewport.current;if(r*32<box.scrollTop)box.scrollTop=r*32;else if(r*32>box.scrollTop+box.clientHeight-96)box.scrollTop=r*32-box.clientHeight+96;return}
  if(!mod&&!event.altKey&&event.key.length===1){event.preventDefault();setEditing({r:top,c:left,value:event.key})}
 }
 function merge(byName){
  const result=mergeRows(rows,byName?undefined:[top,bottom],retained);
  if(result.removed){
   change(result.rows);
   choose(0,0);
   viewport.current.scrollTop=0;
  }
  const details=[];
  if(result.removed)details.push(`已合并，减少 ${result.removed} 行`);
  if(result.conflicts)details.push(`${result.conflicts} 组有不同的非空内容，已保留原行`);
  setFeedback(details.join(' · ')||'没有可合并的行');
 }
 function findNext(){
  if(!query)return;
  let first,next;
  for(const cell of findCells(rows,query,searchRange,wildcards)){
   first??=cell;
   if(!match||cell.r>match.r||(cell.r===match.r&&cell.c>match.c)){next=cell;break}
  }
  const found=next??first;
  if(!found){setFeedback('未找到匹配内容');return}
  setMatch(found);
  const box=viewport.current;
  box.scrollTop=found.r*32;
  const table=box.querySelector('table');
  const header=table.tHead.rows[1].cells[found.c+1];
  if(header.offsetLeft<box.scrollLeft||header.offsetLeft+header.offsetWidth>box.scrollLeft+box.clientWidth){
   box.scrollLeft=header.offsetLeft;
  }
  setFeedback(`找到 ${String.fromCharCode(65+found.c)}${found.r+1}`);
 }
 function replace(inSelection){
  const range=inSelection?{top,bottom,left,right}:undefined;
  const result=replaceCells(rows,query,replacement,range,wildcards);
  if(result.count)change(result.rows);
  setFeedback(result.count?`已替换 ${result.count} 个单元格`:'未找到匹配内容');
 }
 function sortColumn(column){
  const direction=sort?.column===column?-sort.direction:1;
  change(sortRows(rows,column,direction));
  setSort({column,direction});
  choose(0,column);
  viewport.current.scrollTop=0;
 }
 function commit(){if(!editing)return;change(pasteCells(rows,[[editing.value]],editing.r,editing.c,width));setEditing(null);root.current.focus()}
 const start=Math.max(0,Math.floor(scroll/32)-8),end=Math.min(rows.length,start+Math.ceil((viewport.current?.clientHeight||700)/32)+18);
 return <div className="sheet-overlay"><div className="sheet-editor" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={root} onKeyDown={key} onClick={()=>menu&&setMenu(null)} onCopy={e=>{if(e.target.tagName==='INPUT')return;e.preventDefault();e.clipboardData.setData('text/plain',copied())}} onCut={e=>{if(e.target.tagName==='INPUT')return;e.preventDefault();e.clipboardData.setData('text/plain',copied());clear()}} onPaste={e=>{if(e.target.tagName==='INPUT')return;e.preventDefault();paste(e.clipboardData.getData('text/plain'))}}>
 <header className="sheet-header"><h2>{title}</h2><span>{data.path?.split(/[\\/]/).pop()}</span><button className="icon-button" aria-label={data.path?'关闭编辑':'返回图片选择'} disabled={busy} onClick={close}><X size={19}/></button></header>
 <fieldset disabled={busy} className="sheet-tools">
  <div className="sheet-tool-row sheet-toolbar">
   <div className="sheet-tool-group">
   <button title="撤销 ⌘Z" aria-label="撤销" onClick={()=>history(true)}><Undo2 size={16}/></button>
   <button title="重做 ⇧⌘Z" aria-label="重做" onClick={()=>history(false)}><Redo2 size={16}/></button>
   <button onClick={()=>change([...rows,emptyRow(width)])}><Plus size={15}/>添加行</button>
   </div>
   <div className="sheet-tool-group">
    <button aria-expanded={tool==='merge'} onClick={()=>setTool(tool==='merge'?null:'merge')}>合并<ChevronDown size={13}/></button>
   </div>
   <div className="sheet-tool-group">
    <button aria-expanded={tool==='affixes'} onClick={()=>setTool(tool==='affixes'?null:'affixes')}>前后缀<ChevronDown size={13}/></button>
    <button aria-expanded={searchOpen} onClick={()=>setTool(searchOpen?null:'search')}><Search size={14}/>查找替换</button>
   </div>
  </div>
  {tool==='affixes'&&<div className="sheet-tool-row sheet-affixes sheet-tool-panel">
   <input placeholder="前缀" aria-label="前缀" value={prefix} onChange={e=>setPrefix(e.target.value)}/>
   <input placeholder="后缀" aria-label="后缀" value={suffix} onChange={e=>setSuffix(e.target.value)}/>
   {data.headers.slice(0,3).map((h,i)=><label className="checkbox" key={i}>
    <input type="checkbox" checked={columns[i]} onChange={e=>setColumns(v=>v.map((x,j)=>i===j?e.target.checked:x))}/>{i===0?'选项名':h}
   </label>)}
   <button disabled={(!prefix&&!suffix)||!columns.some(Boolean)}
    onClick={()=>change(rows.map(r=>r.map((v,i)=>columns[i]&&v?prefix+v+suffix:v)))}>应用</button>
  </div>}
  {searchOpen&&<div className="sheet-tool-row sheet-search sheet-tool-panel">
   <input placeholder="查找" aria-label="查找内容" value={query} onChange={e=>{setQuery(e.target.value);setMatch(null);setFeedback('')}}
    onKeyDown={e=>{if(e.key==='Enter')findNext()}}/>
   <input placeholder="替换为" aria-label="替换内容" value={replacement} onChange={e=>setReplacement(e.target.value)}/>
   <button disabled={!query} onClick={findNext}>查找下一个</button>
   <label className="checkbox" title="* 匹配任意字符，? 匹配一个字符，~ 用于转义">
    <input type="checkbox" checked={wildcards} onChange={e=>{setWildcards(e.target.checked);setMatch(null);setFeedback('')}}/>通配符
   </label>
   <button disabled={!query||!rows.length} onClick={()=>replace(true)}>替换选区</button>
   <button disabled={!query||!rows.length} onClick={()=>replace(false)}>全部替换</button>
  </div>}
  {tool==='merge'&&<div className="sheet-merge sheet-tool-panel">
   <div className="sheet-tool-row sheet-merge-actions">
    <button type="button" disabled={!canMerge||mergeConflicts.some(({column})=>retained[column]===undefined)}
     onClick={()=>merge(false)}>合并所选行</button>
    <button type="button" disabled={rows.length<2} onClick={()=>merge(true)}>合并同名项</button>
   </div>
   <div className="sheet-merge-conflicts">
    {mergeConflicts.map(({header,column,options})=><div className="sheet-merge-conflict" key={column}
     role="group" aria-label={header+'保留值'}>
     <span>{header}</span>
     <div className="sheet-merge-values">
      {options.map(([value,row])=><button type="button" key={row} title={value}
       aria-pressed={retained[column]===row}
       onClick={()=>rememberRow(column,row)}>
       <small>第 {row+1} 行</small><span>{value}</span>
      </button>)}
     </div>
    </div>)}
   </div>
  </div>}
 </fieldset>
 <div className="sheet-grid" ref={viewport} onPointerMove={moveSelection} onPointerUp={stopSelection} onPointerCancel={stopSelection} onLostPointerCapture={e=>{if(e.target===viewport.current)stopSelection(e)}} onPointerLeave={e=>{if(!viewport.current.hasPointerCapture(e.pointerId))stopSelection(e)}} onScroll={e=>setScroll(e.currentTarget.scrollTop)}><table role="grid"><colgroup><col style={{width:48}}/>{data.headers.map((_,i)=><col key={i} style={{width:width===3?'33.33%':i<3?'16%':'22%'}}/>)}</colgroup><thead><tr><th className="sheet-corner" aria-selected={selection.whole==='all'}><button aria-label="全选表格" title="全选表格" disabled={busy||!rows.length} onClick={()=>choose(0,0,'all')}>◩</button></th>{data.headers.map((_,c)=>{
  const letter=String.fromCharCode(65+c);
  return <th scope="col" key={c} data-sheet-axis="column" data-sheet-index={c}
   aria-label={`选择 ${letter} 列`} aria-selected={wholeColumns&&c>=left&&c<=right}
   onPointerDown={e=>selectHeader(e,'column',c)}>{letter}</th>;
 })}</tr><tr><th>#</th>{data.headers.map((h,i)=>{
  const direction=sort?.column===i?sort.direction:0;
  const SortIcon=direction===1?ArrowUp:direction===-1?ArrowDown:ArrowDownUp;
  return <th scope="col" key={i} aria-sort={direction===1?'ascending':direction===-1?'descending':undefined}>
   <button className="sheet-sort" disabled={busy||rows.length<2} title={((i===3||i===4)?'按目录':'')+(direction===1?'降序排列':'升序排列')} aria-label={h+((i===3||i===4)?'按目录':'')+(direction===1?'降序排列':'升序排列')} onClick={()=>sortColumn(i)}>{h}<SortIcon size={13}/></button>
  </th>
 })}</tr></thead><tbody>{start>0&&<tr aria-hidden="true" style={{height:start*32}}><td colSpan={width+1}/></tr>}{rows.slice(start,end).map((row,index)=>{const r=start+index;return <tr key={r}><th scope="row" data-sheet-axis="row" data-sheet-index={r} aria-selected={wholeRows&&r>=top&&r<=bottom} aria-label={`选择第 ${r+1} 行`} onPointerDown={e=>selectHeader(e,'row',r)} onContextMenu={e=>{e.preventDefault();if(!wholeRows||r<top||r>bottom)choose(r,0,'row');setMenu({x:Math.min(e.clientX,window.innerWidth-200),y:Math.min(e.clientY,window.innerHeight-290)})}}>{r+1}</th>{row.map((value,c)=><td key={c} data-sheet-axis="cell" data-sheet-row={r} data-sheet-index={c} aria-selected={r>=top&&r<=bottom&&c>=left&&c<=right} className={r>=top&&r<=bottom&&c>=left&&c<=right?'sheet-selected':''} data-search-match={searchOpen&&match?.r===r&&match.c===c?true:undefined} onPointerDown={e=>startCellSelection(e,r,c)} onDoubleClick={()=>{if(!busy)setEditing({r,c,value})}}>{editing?.r===r&&editing?.c===c?<input autoFocus aria-label={`${data.headers[c]} 第 ${r+1} 行`} value={editing.value} onChange={e=>setEditing({...editing,value:e.target.value})} onBlur={commit} onKeyDown={e=>{if(e.key==='Enter'||e.key==='Tab'){e.preventDefault();commit()}}}/>:<span title={value}>{value}</span>}</td>)}</tr>})}{end<rows.length&&<tr aria-hidden="true" style={{height:(rows.length-end)*32}}><td colSpan={width+1}/></tr>}</tbody></table></div>
 <div className="sheet-footer"><span>{rows.length} 行 · {selection.whole==='all'?'已全选':wholeRows?`已选 ${bottom-top+1} 行`:wholeColumns?`已选 ${right-left+1} 列`:`${String.fromCharCode(65+left)}${top+1}${searchRange?`:${String.fromCharCode(65+right)}${bottom+1}`:""}`}</span><span className="sheet-feedback" role="status">{feedback}</span><button className="primary" disabled={busy||!rows.length} onClick={()=>onSave(rows)}><Check size={16}/>{saveLabel}</button></div>
 {menu&&<div className="sheet-menu" style={{left:menu.x,top:menu.y}} onClick={e=>e.stopPropagation()}>{[['复制行',()=>copy()],['剪切行',()=>copy(true)],['粘贴',()=>fromClipboard()],['替换选中行',()=>fromClipboard(true)],['插入行',()=>{change([...rows.slice(0,top),emptyRow(width),...rows.slice(top)]);setMenu(null)}],['删除选中行',()=>{change(rows.filter((_,i)=>i<top||i>bottom));setSelection({a:0,b:0,c:0,d:0,whole:false});setMenu(null)}]].map(([label,fn])=><button disabled={busy} key={label} onClick={fn}>{label}</button>)}</div>}
 </div></div>
}
