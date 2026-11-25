import test from 'node:test';
import assert from 'node:assert/strict';
import {appendLogs,clearLogs,getLogs,subscribeLogs} from '../src/logStore.js';

test('empty log heartbeats never notify or allocate a new snapshot',()=>{
 clearLogs();const previous=getLogs();let calls=0;const off=subscribeLogs(()=>calls++);
 appendLogs([]);assert.equal(calls,0);assert.equal(getLogs(),previous);off();
});
test('streaming logs retain bounded history and stable row identities',()=>{
 clearLogs();appendLogs([{text:'first'}]);const original=getLogs()[0];
 appendLogs([{text:'second'}]);assert.equal(getLogs()[0],original);
 appendLogs(Array.from({length:1100},(_,i)=>({text:String(i)})));
 assert.equal(getLogs().length,1000);assert.equal(new Set(getLogs().map(row=>row.id)).size,1000);
});
test('unmounted log viewers stop receiving notifications',()=>{
 clearLogs();let calls=0;const off=subscribeLogs(()=>calls++);off();
 appendLogs([{text:'later'}]);assert.equal(calls,0);
});
