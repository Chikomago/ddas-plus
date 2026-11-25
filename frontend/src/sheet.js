import {directoryPath} from './imageFilter.js';

export const emptyRow=(width=5)=>Array(width).fill('');
export function encodeTSV(rows){return rows.map(r=>r.map(v=>/[\t\r\n"]/.test(v)?'"'+v.replaceAll('"','""')+'"':v).join('\t')).join('\n')}
export function parseTSV(text,width=5){
 const rows=[[]];let value='',quoted=false;
 for(let i=0;i<text.length;i++){
  const c=text[i];
  if(c==='"'&&(quoted||value==='')){if(quoted&&text[i+1]==='"'){value+='"';i++}else quoted=!quoted}
  else if(!quoted&&(c==='\t'||c==='\n'||c==='\r')){rows.at(-1).push(value);value='';if(c!=='\t'){if(c==='\r'&&text[i+1]==='\n')i++;rows.push([])}}else value+=c;
 }
 if(quoted)throw Error('粘贴内容的引号未闭合');
 rows.at(-1).push(value);
 if(rows.length>1&&rows.at(-1).length===1&&rows.at(-1)[0]==='')rows.pop();
 if(rows.some(r=>r.length>width))throw Error(width===5?'配置最多支持五列':`配置最多支持 ${width} 列`);
 return rows;
}
export function pasteCells(rows,grid,row,col,width=5){
 if(grid.some(r=>r.length+col>width))throw Error(`粘贴内容超出 ${width} 列`);
 const next=rows.map(r=>[...r]);while(next.length<row+grid.length)next.push(emptyRow(width));
 grid.forEach((r,i)=>r.forEach((v,j)=>next[row+i][col+j]=v));return next;
}

const cellCollator = new Intl.Collator('zh-CN', {numeric:true});
export function sortRows(rows,column,direction){
 return [...rows].sort((a,b)=>{
  const left=a[column],right=b[column];
  if(!left||!right)return Number(!left)-Number(!right);
  if(column!==3&&column!==4)return direction*cellCollator.compare(left,right);
  const aDirectory=directoryPath(left),bDirectory=directoryPath(right);
  const order=cellCollator.compare(aDirectory,bDirectory)||(aDirectory===bDirectory?0:aDirectory<bDirectory?-1:1);
  return direction*order;
 });
}

export function mergeRows(rows, range, retained={}){
 const groups=new Map();
 rows.forEach(([name],index)=>{
  if(range&&(index<range[0]||index>range[1]))return;
  if(!range&&!name.trim())return;
  const key=range?'':name.trim();
  if(!groups.has(key))groups.set(key,[]);
  groups.get(key).push(index);
 });
 const merged=new Map(),removed=new Set();
 let conflicts=0;
 for(const indices of groups.values()){
  if(indices.length<2)continue;
  const combined=emptyRow(rows[indices[0]].length);
  let conflict=false;
  for(const index of indices){
   rows[index].forEach((value,column)=>{
    if(!value.trim()||(range&&retained[column]!==undefined&&retained[column]!==index))return;
    if(combined[column]&&combined[column]!==value)conflict=true;
    else combined[column]=value;
   });
  }
  if(conflict){conflicts++;continue}
  merged.set(indices[0],combined);
  indices.slice(1).forEach(index=>removed.add(index));
 }
 return {rows:rows.flatMap((row,index)=>removed.has(index)?[]:[merged.get(index)??row]),removed:removed.size,conflicts};
}

function wildcardPattern(query){
 const tokens=query.match(/~[~*?]|\*+|[\s\S]/gu)??[];
 return tokens.map(token=>{
  if(token[0]==='*')return '[\\s\\S]*';
  if(token==='?')return '[\\s\\S]';
  return token.replace(/^~([~*?])$/,'$1').replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 }).join('');
}

export function* findCells(rows,query,range,wildcards=false){
 if(!query)return;
 const pattern=wildcards?new RegExp(wildcardPattern(query),'u'):null;
 const {top=0,bottom=rows.length-1,left=0,right=Infinity}=range??{};
 for(let r=top;r<=bottom&&r<rows.length;r++){
  const row=rows[r];
  for(let c=left;c<=right&&c<row.length;c++){
   if(pattern?Boolean(row[c]&&pattern.test(row[c])):row[c].includes(query))yield {r,c};
  }
 }
}

export function replaceCells(rows,query,replacement,range,wildcards=false){
 const next=rows.map(row=>[...row]);
 const search=wildcards?new RegExp(wildcardPattern(query),'gu'):query;
 let count=0;
 for(const {r,c} of findCells(rows,query,range,wildcards)){
  next[r][c]=rows[r][c].replaceAll(search,match=>match?replacement:match);
  count++;
 }
 return {rows:next,count};
}
