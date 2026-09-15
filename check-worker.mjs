import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('./static/_worker.js',import.meta.url),'utf8');
const {default:worker}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const env={VIDEO_BACKEND:'https://kemai-ai-video.onrender.com',KEMAI_PROXY_SECRET:'test-only'};
let redirected=false,calls=0;
globalThis.fetch=async(url,options)=>{
  calls++;
  assert.equal(options.redirect,'manual'); // Workers supports manual/follow only.
  assert.equal(options.headers.get('x-kemai-proxy'),'test-only');
  assert.equal(options.headers.get('x-kemai-ip'),'192.0.2.1');
  return redirected ? new Response(null,{status:302,headers:{location:'https://example.com/'}}) : Response.json({available:true});
};
const request=()=>new Request('https://kemai-ai-video.pages.dev/api/status',{headers:{'cf-connecting-ip':'192.0.2.1','x-kemai-proxy':'forged'}});
let result=await worker.fetch(request(),env);
assert.equal(result.status,200);assert.deepEqual(await result.json(),{available:true});
redirected=true;result=await worker.fetch(request(),env);
assert.equal(result.status,503);assert.equal(calls,2); // Never forward a secret to a redirect target.
const forbidden=new Request('https://kemai-ai-video.pages.dev/api/jobs',{method:'POST',headers:{origin:'https://example.com'}});
assert.equal((await worker.fetch(forbidden,env)).status,403);assert.equal(calls,2);
console.log('Worker gateway checks passed');

const planInput={mode:'script',visuals:'auto',aspect:'9:16',title:'',script:'清晨慢慢泡一杯溫暖的熱茶。',parts:['清晨慢慢泡一杯溫暖的熱茶。']};
let aiCalls=0;env.PEXELS_API_KEY='private-pexels-test';
env.AI={run:async()=>{aiCalls++;return {response:'{"queries":["pouring tea"]}'}}};
const planRequest=(headers={})=>new Request('https://kemai-ai-video.pages.dev/api/internal/plan',{method:'POST',headers,body:JSON.stringify(planInput)});
assert.equal((await worker.fetch(planRequest(),env)).status,403);assert.equal(aiCalls,0);
globalThis.fetch=async(url,options)=>{
  assert.equal(options.redirect,'manual');assert.equal(options.headers.Authorization,'private-pexels-test');
  const video=String(url).includes('/videos/');
  return Response.json(video?{videos:[{id:12,url:'https://www.pexels.com/video/12/',duration:10,user:{name:'Tea creator'},video_files:[{file_type:'video/mp4',width:720,height:1280,link:'https://videos.pexels.com/video-files/12/test.mp4'}]}]}:{photos:[{id:13,url:'https://www.pexels.com/photo/13/',photographer:'Tea photo',src:{large:'https://images.pexels.com/photos/13/test.jpg'}}]});
};
result=await worker.fetch(planRequest({'x-kemai-proxy':'test-only'}),env);
assert.equal(result.status,200);let plan=await result.json();
assert.equal(plan.script,planInput.script);assert.equal(plan.scenes[0].candidates.length,2);assert.equal(aiCalls,1);
assert(!JSON.stringify(plan).includes(env.PEXELS_API_KEY));
planInput.parts=['不相符的文案'];
assert.equal((await worker.fetch(planRequest({'x-kemai-proxy':'test-only'}),env)).status,422);assert.equal(aiCalls,1);
planInput.parts=[planInput.script];globalThis.fetch=async()=>new Response('',{status:429});
assert.equal((await worker.fetch(planRequest({'x-kemai-proxy':'test-only'}),env)).status,503);
console.log('Worker automatic-story checks passed');
