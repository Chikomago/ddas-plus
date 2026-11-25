import test from 'node:test';
import assert from 'node:assert/strict';
import {encodeTSV,parseTSV,pasteCells,sortRows,mergeRows,findCells,replaceCells} from '../src/sheet.js';
test('Excel clipboard preserves multiline cells, tabs and quotes',()=>{
 const rows=[['汉字','a\tb','line\nnext','"quoted"',''],['1','2','3','4','5']];
 assert.deepEqual(parseTSV(encodeTSV(rows)),rows);
 assert.deepEqual(parseTSV('a\tb\r\nc\td\r\n'),[['a','b'],['c','d']]);
});
test('paste grows rows without changing source or unrelated cells',()=>{
 const rows=[['a','b','c','d','e']];
 assert.deepEqual(pasteCells(rows,[['X'],['Y']],0,2),[['a','b','X','d','e'],['','','Y','','']]);
 assert.equal(rows[0][2],'c');
});
test('reject excess columns and malformed quotes',()=>{
 assert.throws(()=>parseTSV('1\t2\t3\t4\t5\t6'),/五列/);
 assert.throws(()=>parseTSV('"unfinished'),/引号/);
 assert.throws(()=>pasteCells([], [['a','b']],0,4),/5 列/);
});

test('column sort moves whole rows, keeps ties stable and leaves blanks last',()=>{
 const rows=[['图10','PC10'],['图2','PC2'],['图2','另一个PC2'],['','空白行']];
 assert.deepEqual(sortRows(rows,0,1),[rows[1],rows[2],rows[0],rows[3]]);
 assert.deepEqual(sortRows(rows,0,-1),rows);
 assert.deepEqual(sortRows(rows,1,1).filter(row=>row[1].startsWith('PC')),[rows[1],rows[0]]);
});

test('selected rows merge complementary values and preserve adjacent rows',()=>{
 const rows=[['红','','','pc.png',''],['','pc','移动','','mobile.png'],['蓝','','','','']];
 assert.deepEqual(mergeRows(rows,[0,1]),{
  rows:[['红','pc','移动','pc.png','mobile.png'],rows[2]],removed:1,conflicts:0
 });
});

test('merge by name keeps order and preserves conflicting and unnamed groups',()=>{
 const rows=[['红','','','pc.png',''],['蓝','v1','','',''],['红','','','','mobile.png'],['蓝','v2','','',''],['','','','','']];
 const expected=[['红','','','pc.png','mobile.png'],rows[1],rows[3],rows[4]];
 assert.deepEqual(mergeRows(rows),{rows:expected,removed:1,conflicts:1});
 assert.deepEqual(mergeRows(rows,[0,1]),{rows,removed:0,conflicts:1});
});

test('find and replace use the chosen column and treat replacement as literal text',()=>{
 const rows=[['aa','aa'],['aaa','a']];
 assert.deepEqual([...findCells(rows,'a',{left:1,right:1})],[{r:0,c:1},{r:1,c:1}]);
 assert.deepEqual(replaceCells(rows,'aa','$&',{left:1,right:1}),{rows:[['aa','$&'],['aaa','a']],count:1});
 assert.deepEqual(replaceCells(rows,'a','X',{top:1,bottom:1,left:0,right:0}),{rows:[rows[0],['XXX','a']],count:1});
 assert.deepEqual(replaceCells(rows,'','x'),{rows,count:0});
});

test('image path columns group by parent directory and preserve order within each group',()=>{
 const rows=[
  ['first','','','/set2/z.jpg','C:\\set10\\g.png'],
  ['second','','','/set10/y.jpg','C:\\set2\\z.png'],
  ['third','','','/set2/a.jpg','C:\\set2\\a.png'],
  ['blank','','','',''],
 ];
 assert.deepEqual(sortRows(rows,3,1),[rows[0],rows[2],rows[1],rows[3]]);
 assert.deepEqual(sortRows(rows,4,-1),rows);
 assert.deepEqual(sortRows(rows,4,1),[rows[1],rows[2],rows[0],rows[3]]);
});

test('wildcard replace respects the selection, escapes literals, and can cover the whole table',()=>{
 const rows=[['foo1.txt','foo2.txt'],['foo12.txt','foo*.txt']];
 const selection={top:0,bottom:0,left:1,right:1};
 assert.deepEqual(replaceCells(rows,'foo?.txt','X',selection,true).rows,[['foo1.txt','X'],rows[1]]);
 assert.deepEqual(replaceCells(rows,'foo*.txt','X',undefined,true).rows,[['X','X'],['X','X']]);
 assert.deepEqual([...findCells(rows,'foo~*.txt',undefined,true)],[{r:1,c:1}]);
 assert.equal(replaceCells([['','abc']],'*','X',undefined,true).count,1);
});

test('merge can keep a middle row for one column and a different row for another',()=>{
 const rows=[['甲','A','','/a.png',''],['乙','B','','','/b.png'],['丙','C','','','']];
 assert.deepEqual(mergeRows(rows,[0,2],{0:1,1:2}).rows,[['乙','C','','/a.png','/b.png']]);
 assert.equal(mergeRows(rows,[0,2],{0:1}).conflicts,1);
});

test('text configurations retain three columns when pasting new rows',()=>{
 assert.deepEqual(pasteCells([['a','b','c']],[['x']],2,1,3),[['a','b','c'],['','',''],['','x','']]);
 assert.throws(()=>pasteCells([], [['a','b']],0,2,3),/3 列/);
});
