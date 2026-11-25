import test from 'node:test';
import assert from 'node:assert/strict';
import {filterImages,matchSplitImages} from '../src/imageFilter.js';

test('inclusive and exclusive image filters match filenames across path formats',()=>{
 const images=[{path:'/Blue/Red.png'},{path:'C:\\Images\\BLUE.jpg'},{path:'/Images/light-blue.gif'}];
 assert.deepEqual(filterImages(images,' BLUE ','include'),images.slice(1));
 assert.deepEqual(filterImages(images,'blue','exclude'),images.slice(0,1));
 assert.deepEqual(filterImages(images,'','exclude'),images);
 assert.deepEqual(filterImages(images,'blue','all'),images);
});

test('matches unique names across directories and unique remaining entries in the same directory',()=>{
 const pc=['/pc/blue.jpg','/shared/800.png','/other/red.png'].map(path=>({path}));
 const mobile=['/shared/750.png','/mobile/blue.gif','/more/green.png'].map(path=>({path}));
 assert.deepEqual(matchSplitImages(pc,mobile),{pairs:[1,0,null],pc:new Set([2]),mobile:new Set([2])});
});

test('prefers an exact directory and name match and leaves ambiguous entries unmatched',()=>{
 const pc=['/shared/red.jpg','/pc1/red.png','/pc2/red.png','/shared2/800.png'].map(path=>({path}));
 const mobile=['/mobile/red.png','/shared/red.gif','/shared2/750.png','/shared2/750-copy.png'].map(path=>({path}));
 assert.deepEqual(matchSplitImages(pc,mobile),{pairs:[null,0,null,null],pc:new Set([1,2,3]),mobile:new Set([0,2,3])});
});
