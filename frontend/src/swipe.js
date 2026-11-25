export const clampPage=(page,count)=>Math.max(0,Math.min(Math.max(0,count-1),page));
export function releasePage({startPage,delta,velocity,scrollLeft,width,count}){
 if(width<=0)return clampPage(startPage,count);
 const threshold=Math.min(width*.18,90);
 const flick=Math.abs(velocity)>.45&&Math.abs(delta)>12;
 return clampPage(Math.abs(delta)>threshold||flick?startPage+(delta<0?1:-1):Math.round(scrollLeft/width),count);
}

export const visiblePage=(left,width,count)=>clampPage(width>0?Math.round(left/width):0,count);
