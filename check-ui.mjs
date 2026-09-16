// Run without a browser or network: node check-ui.mjs
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {runInNewContext} from 'node:vm';
const code=await readFile(new URL('./static/app.js',import.meta.url),'utf8');
const html=await readFile(new URL('./static/index.html',import.meta.url),'utf8');

const element=()=>({
  value:'',disabled:false,hidden:false,dataset:{},style:{},events:{},children:[],
  classList:{toggle(){},add(){},remove(){}},
  addEventListener(name,handler){this.events[name]=handler;},
  setAttribute(name,value){this[name]=value;},
  pause(){},load(){},scrollIntoView(){},removeAttribute(name){delete this[name];},
  replaceChildren(){this.children=[];},append(...items){this.children.push(...items);}
});
for(const state of ['complete','failed','running','queued','ready']) {
  const elements=new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(([,id])=>[id,element()]));  const get=id=>elements.get(id);
  get('mode').value='topic';get('visuals').value='auto';get('music').value='warm';
  const id='a'.repeat(48),saved=JSON.stringify({id,time:Date.now()});
  let finish;
  const jobResponse=new Promise(resolve=>{finish=resolve;});
  runInNewContext(code,{
    document:{getElementById:get,querySelectorAll:()=>[],createElement:element},
    localStorage:{getItem:()=>saved,removeItem(){}},
    fetch:path=>path==='/api/status'?Promise.resolve(Response.json({available:true})):jobResponse,
    URL,AbortSignal,FormData,setTimeout:()=>0,clearTimeout(){},
  });
  assert.equal(get('editor-fields').disabled,true,'Restored work is locked while its status is unknown');
  finish(Response.json({id,state,aspect:'9:16',draft:{title:'待確認',scenes:[{text:'原始旁白，確認後才製作。',candidates:[{kind:'photo',provider:'pexels',url:'https://images.pexels.com/photos/1/a.jpg',page:'https://www.pexels.com/photo/1/',author:'Creator'},{kind:'photo',provider:'pexels',url:'https://images.pexels.com/photos/2/b.jpg',page:'https://www.pexels.com/photo/2/',author:'Creator'}]}]},message:state,progress:100,width:1280,height:720,duration:5,bytes:1000,expires:Date.now()/1000+1800,sources:[]}));
  await new Promise(setImmediate);
  const pending=state==='queued'||state==='running';
  assert.equal(get('editor-fields').disabled,pending,`${state}: editor remains locked`);
  assert.equal(get('generate').disabled,pending,`${state}: generate remains locked`);
  assert.equal(get('processing-cover').hidden,!pending,`${state}: loading overlay remains visible`);
  if(state==='ready') {
    assert.equal(get('story-fields').hidden,false);
    assert.equal(get('story-fields').disabled,false);
    const card=get('scene-list').children[0];
    const actions=card.children.find(e=>e.className==='scene-actions');
    const media=card.children.find(e=>e.className==='scene-media');
    assert.match(media.children[0].src,/photos\/1\//);
    actions.children[0].events.click();
    assert.match(media.children[0].src,/photos\/2\//,'Switch changes the visible selected material');
    assert.equal(card.children.find(e=>e.id==='scene-text-0').value,'原始旁白，確認後才製作。');
  }
  if(state==='complete') {
    assert.equal(get('download-video').href,`/api/jobs/${id}/video.mp4`,'Keep the completed video available');
    assert.equal(get('downloads').hidden,false);
    get('example').events.click();
    assert.match(get('script').value,/忙碌/,'The editor accepts another story');
  }
}
console.log('Passed: restored completed/failed jobs unlock editing; active jobs stay locked; completed downloads remain available.');
