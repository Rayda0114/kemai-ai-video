// Run without a browser or network: node check-ui.mjs
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {runInNewContext} from 'node:vm';
const code=await readFile(new URL('./static/app.js',import.meta.url),'utf8');
const html=await readFile(new URL('./static/index.html',import.meta.url),'utf8');

for(const state of ['complete','failed','running','queued']) {
  const elements=new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(([,id])=>[id,{
    value:'',disabled:false,hidden:false,dataset:{},style:{},events:{},
    classList:{toggle(){},add(){},remove(){}},
    addEventListener(name,handler){this.events[name]=handler;},
    pause(){},load(){},removeAttribute(name){delete this[name];},replaceChildren(){},append(){}
  }]));
  const get=id=>elements.get(id);
  get('mode').value='topic';get('visuals').value='auto';get('music').value='warm';
  const id='a'.repeat(48),saved=JSON.stringify({id,time:Date.now()});
  let finish;
  const jobResponse=new Promise(resolve=>{finish=resolve;});
  runInNewContext(code,{
    document:{getElementById:get,querySelectorAll:()=>[],createElement:()=>({append(){}})},
    localStorage:{getItem:()=>saved,removeItem(){}},
    fetch:path=>path==='/api/status'?Promise.resolve(Response.json({available:true})):jobResponse,
    URL,AbortSignal,FormData,setTimeout:()=>0,clearTimeout(){},
  });
  assert.equal(get('editor-fields').disabled,true,'Restored work is locked while its status is unknown');
  finish(Response.json({state,message:state,progress:100,width:1280,height:720,duration:5,bytes:1000,expires:Date.now()/1000+1800,sources:[]}));
  await new Promise(setImmediate);
  const pending=state==='queued'||state==='running';
  assert.equal(get('editor-fields').disabled,pending,`${state}: editor remains locked`);
  assert.equal(get('generate').disabled,pending,`${state}: generate remains locked`);
  assert.equal(get('processing-cover').hidden,!pending,`${state}: loading overlay remains visible`);
  if(state==='complete') {
    assert.equal(get('download-video').href,`/api/jobs/${id}/video.mp4`,'Keep the completed video available');
    assert.equal(get('downloads').hidden,false);
    get('example').events.click();
    assert.match(get('script').value,/忙碌/,'The editor accepts another story');
  }
}
console.log('Passed: restored completed/failed jobs unlock editing; active jobs stay locked; completed downloads remain available.');
