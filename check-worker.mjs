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
