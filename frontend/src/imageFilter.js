export function filterImages(images,keyword,mode){
 const term=keyword.trim().toLowerCase();
 if(!term||mode==='all')return images;
 return images.filter(({path})=>{
  const filename=path.split(/[\\/]/).at(-1).toLowerCase();
  return filename.includes(term)===(mode==='include');
 });
}

export const directoryPath=path=>path.replace(/[^\\/]+$/,'');

export function matchSplitImages(pc,mobile){
 const available={pc:new Set(pc.keys()),mobile:new Set(mobile.keys())};
 const pairs=mobile.map(()=>null);
 const stem=({path})=>path.split(/[\\/]/).at(-1).replace(/\.[^.]+$/,'');
 function match(key){
  function group(images,indices){
   const groups=new Map();
   for(const index of indices){
    const value=key(images[index]);
    if(!groups.has(value))groups.set(value,[]);
    groups.get(value).push(index);
   }
   return groups;
  }
  const left=group(pc,available.pc);
  for(const [key,right] of group(mobile,available.mobile)){
   const candidates=left.get(key);
   if(candidates?.length!==1||right.length!==1)continue;
   const [p]=candidates,[m]=right;
   pairs[m]=p;
   available.pc.delete(p);
   available.mobile.delete(m);
  }
 }
 match(image=>JSON.stringify([directoryPath(image.path),stem(image)]));
 match(stem);
 match(({path})=>directoryPath(path));
 return {...available,pairs};
}
