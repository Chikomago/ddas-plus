// Opt-in instrumentation: no labels, input values or clipboard data are recorded.
export function installUITiming(report,host=window){
 let stopped=false,last=host.performance.now();
 const send=(stage,ms)=>{if(!stopped&&ms>=100&&ms<=3600000)Promise.resolve(report(stage,ms)).catch(()=>{})};
 const click=event=>{
  const now=host.performance.now();
  // Some WebKit versions use epoch-based event timestamps; ignore those.
  if(event.timeStamp>0&&event.timeStamp<=now)send('event-delivery',now-event.timeStamp);
  host.requestAnimationFrame(()=>send('click-paint',host.performance.now()-now));
 };
 host.addEventListener('click',click,true);
 const timer=host.setInterval(()=>{const now=host.performance.now();if(host.document.visibilityState==='visible')send('event-loop',Math.max(0,now-last-250));last=now},250);
 return()=>{stopped=true;host.removeEventListener('click',click,true);host.clearInterval(timer)};
}
