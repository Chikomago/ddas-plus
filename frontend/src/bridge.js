let profileTiming=false;
export function setBridgeTiming(enabled){profileTiming=!!enabled}
export function watchBridge(onConnect,onPreview){
 let disposed=false,connected=false;
 const attempt=()=>{if(!disposed&&!connected&&window.pywebview?.api){connected=true;onConnect(window.pywebview.api)}};
 window.addEventListener('pywebviewready',attempt);
 const interval=setInterval(attempt,1000);
 const preview=setTimeout(()=>{if(!connected&&!disposed)onPreview()},4000);
 attempt();
 return()=>{disposed=true;clearInterval(interval);clearTimeout(preview);window.removeEventListener('pywebviewready',attempt)};
}
export async function call(api,name,...args){
 const started=performance.now();
 const result=await api[name](...args);
 if(profileTiming&&name!=='poll'&&name!=='report_ui_timing'&&api.report_ui_timing){
  const elapsed=performance.now()-started;
  if(elapsed>=300)Promise.resolve(api.report_ui_timing('bridge',elapsed)).catch(()=>{});
 }
 if(!result?.ok)throw new Error(result?.message||'操作失败');
 return result.value;
}
