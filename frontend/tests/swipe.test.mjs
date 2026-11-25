import test from 'node:test';
import assert from 'node:assert/strict';
import {releasePage,visiblePage} from '../src/swipe.js';
const base={startPage:1,delta:0,velocity:0,scrollLeft:500,width:500,count:3};
test('small slow movement stays on current field',()=>assert.equal(releasePage({...base,delta:-20,scrollLeft:520}),1));
test('deliberate left drag advances one field',()=>assert.equal(releasePage({...base,delta:-110,scrollLeft:610}),2));
test('deliberate right drag returns one field',()=>assert.equal(releasePage({...base,delta:110,scrollLeft:390}),0));
test('short fast flick advances without needing half a page',()=>assert.equal(releasePage({...base,delta:-30,velocity:-.8,scrollLeft:530}),2));
test('first and last page do not go out of range',()=>{
 assert.equal(releasePage({...base,startPage:0,delta:120,scrollLeft:0}),0);
 assert.equal(releasePage({...base,startPage:2,delta:-120,scrollLeft:1000}),2);
});
test('unmeasured viewport is safe',()=>assert.equal(releasePage({...base,width:0,delta:-100}),1));

test('indicator follows visible page before scrolling settles',()=>{
 assert.equal(visiblePage(249,500,3),0);
 assert.equal(visiblePage(251,500,3),1);
 assert.equal(visiblePage(751,500,3),2);
 assert.equal(visiblePage(749,500,3),1);
});
test('indicator is stable at the scroll boundaries',()=>{
 assert.equal(visiblePage(-50,500,3),0);
 assert.equal(visiblePage(1500,500,3),2);
 assert.equal(visiblePage(0,0,3),0);
});
