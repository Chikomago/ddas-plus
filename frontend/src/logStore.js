const MAX_LOGS=1000;
let entries=[],nextId=0;
const listeners=new Set();
export const subscribeLogs=listener=>{listeners.add(listener);return()=>listeners.delete(listener)};
export const getLogs=()=>entries;
export function appendLogs(batch){
 if(!batch.length)return;
 entries=[...entries,...batch.map(entry=>({...entry,id:++nextId}))].slice(-MAX_LOGS);
 for(const listener of listeners)listener();
}
export function clearLogs(){entries=[];for(const listener of listeners)listener()}
