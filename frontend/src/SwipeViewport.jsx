import React,{useEffect,useRef} from 'react';
import {clampPage,releasePage,visiblePage} from './swipe';

export default function SwipeViewport({page,count,onPageChange,children,disabled=false}){
 const viewport=useRef(null),gesture=useRef(null),suppressClick=useRef(false);
 const latest=useRef({page,count,onPageChange}),target=useRef(null),settleTimer=useRef(),programmatic=useRef(false);
 latest.current={page,count,onPageChange};
 const syncIndicator=()=>{
  const element=viewport.current;if(!element||!element.clientWidth)return;
  const value=visiblePage(element.scrollLeft,element.clientWidth,latest.current.count);
  // Mark a scroll-origin update so the page effect cannot start another animation.
  target.current=value;
  if(value!==latest.current.page){latest.current.page=value;latest.current.onPageChange(value)}
 };
 const finishScroll=()=>{
  if(gesture.current)return;
  programmatic.current=false;syncIndicator();
 };
 useEffect(()=>{
  const element=viewport.current;
  const next=clampPage(page,count);
  if(gesture.current||target.current===next)return;
  const initial=target.current===null;target.current=next;programmatic.current=!initial;
  element.scrollTo({left:next*element.clientWidth,behavior:initial?'instant':'smooth'});
 },[page,count]);
 useEffect(()=>{
  const element=viewport.current;let width=element.clientWidth;
  const observer=new ResizeObserver(()=>{
   if(width===element.clientWidth)return;width=element.clientWidth;
   element.scrollTo({left:latest.current.page*width,behavior:'instant'});
  });observer.observe(element);
  element.addEventListener('scrollend',finishScroll);
  return()=>{observer.disconnect();element.removeEventListener('scrollend',finishScroll);clearTimeout(settleTimer.current)};
 },[]);
 function pointerDown(event){
  programmatic.current=false;
  if(disabled||event.pointerType!=='mouse'||event.button!==0||count<2||event.target.closest('input,button,a,textarea,select,summary,label'))return;
  gesture.current={id:event.pointerId,startX:event.clientX,startY:event.clientY,lastX:event.clientX,lastTime:performance.now(),velocity:0,left:viewport.current.scrollLeft,page:visiblePage(viewport.current.scrollLeft,viewport.current.clientWidth,count)};
 }
 function pointerMove(event){
  const state=gesture.current;if(!state||state.id!==event.pointerId)return;
  const dx=event.clientX-state.startX;
  if(!state.moved){
   if(Math.abs(dx)<4||Math.abs(dx)<Math.abs(event.clientY-state.startY))return;
   state.moved=true;viewport.current.dataset.dragging='true';viewport.current.setPointerCapture(event.pointerId);
  }
  event.preventDefault();
  const now=performance.now(),elapsed=now-state.lastTime;
  if(elapsed>0)state.velocity=(event.clientX-state.lastX)/elapsed;
  state.lastX=event.clientX;state.lastTime=now;
  viewport.current.scrollLeft=state.left-dx;
 }
 function pointerUp(event,cancelled=false){
  const state=gesture.current;if(!state||state.id!==event.pointerId)return;
  gesture.current=null;const element=viewport.current;delete element.dataset.dragging;
  if(element.hasPointerCapture(event.pointerId))element.releasePointerCapture(event.pointerId);
  if(!state.moved)return;
  suppressClick.current=true;
  const next=cancelled?state.page:releasePage({startPage:state.page,delta:event.clientX-state.startX,
   velocity:performance.now()-state.lastTime>100?0:state.velocity,scrollLeft:element.scrollLeft,width:element.clientWidth,count});
  target.current=next;programmatic.current=true;onPageChange(next);
  element.scrollTo({left:next*element.clientWidth,behavior:'smooth'});
 }
 return <div ref={viewport} className="field-viewport" onScroll={()=>{if(!programmatic.current)syncIndicator();clearTimeout(settleTimer.current);settleTimer.current=setTimeout(finishScroll,160)}} onWheel={()=>{programmatic.current=false}}
  onPointerDown={event=>{suppressClick.current=false;pointerDown(event)}} onPointerMove={pointerMove}
  onPointerUp={event=>pointerUp(event)} onPointerCancel={event=>pointerUp(event,true)}
  onPointerLeave={event=>{if(gesture.current&&!gesture.current.moved)gesture.current=null}}
  onClickCapture={event=>{if(suppressClick.current){event.preventDefault();event.stopPropagation();suppressClick.current=false}}}>{children}</div>
}
