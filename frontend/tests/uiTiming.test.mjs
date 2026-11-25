import test from 'node:test';
import assert from 'node:assert/strict';
import {installUITiming} from '../src/uiTiming.js';
test('timing separates event delivery, paint and loop stalls; cleanup stops reports',()=>{
 let now=1000,click,tick,paint,removed=false,cleared=false;const reports=[];
 const host={performance:{now:()=>now},document:{visibilityState:'visible'},addEventListener:(_,fn)=>click=fn,removeEventListener:()=>removed=true,requestAnimationFrame:fn=>paint=fn,setInterval:fn=>{tick=fn;return 1},clearInterval:()=>cleared=true};
 const stop=installUITiming((...args)=>reports.push(args),host);
 click({timeStamp:850});now=1200;paint();now=1600;tick();
 assert.deepEqual(reports,[['event-delivery',150],['click-paint',200],['event-loop',350]]);
 stop();now=2000;tick();assert.equal(reports.length,3);assert.ok(removed&&cleared);
});
