import test from 'node:test';
import assert from 'node:assert/strict';
import {watchBridge,call} from '../src/bridge.js';

function environment(){
 const saved={window:globalThis.window,setInterval:globalThis.setInterval,clearInterval:globalThis.clearInterval,setTimeout:globalThis.setTimeout,clearTimeout:globalThis.clearTimeout};
 const listeners=new Map(),intervals=new Map(),timers=new Map();let id=0;
 globalThis.window={addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:(name,fn)=>{if(listeners.get(name)===fn)listeners.delete(name)}};
 globalThis.setInterval=fn=>{intervals.set(++id,fn);return id};globalThis.clearInterval=id=>intervals.delete(id);
 globalThis.setTimeout=fn=>{timers.set(++id,fn);return id};globalThis.clearTimeout=id=>timers.delete(id);
 return {listeners,intervals,timers,restore:()=>Object.assign(globalThis,saved)};
}

test('bridge arriving after preview timeout still connects exactly once',()=>{
 const e=environment();try{
  let connections=0,previews=0;
  const dispose=watchBridge(()=>connections++,()=>previews++);
  [...e.timers.values()][0]();assert.equal(previews,1);
  window.pywebview={api:{}};e.listeners.get('pywebviewready')();
  [...e.intervals.values()][0]();assert.equal(connections,1);dispose();
 }finally{e.restore()}
});

test('watcher cleans up pending timers and event listener',()=>{
 const e=environment();try{
  const dispose=watchBridge(()=>assert.fail('unexpected connection'),()=>{});dispose();
  assert.equal(e.listeners.size,0);assert.equal(e.intervals.size,0);assert.equal(e.timers.size,0);
 }finally{e.restore()}
});

test('bridge already present connects without waiting for an event',()=>{
 const e=environment();try{
  const api={};window.pywebview={api};let connected;
  const dispose=watchBridge(value=>connected=value,()=>{});
  assert.equal(connected,api);dispose();
 }finally{e.restore()}
});

test('backend rejection preserves the original error text',async()=>{
 await assert.rejects(()=>call({start_task:async()=>({ok:false,message:'未选择配置文件。请先生成或选择配置文件。'})},'start_task'),/未选择配置文件/);
});
