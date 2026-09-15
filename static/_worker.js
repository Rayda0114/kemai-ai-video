export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith('/api/')) return env.ASSETS.fetch(request);
    const headers = new Headers({'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'});
    if (!env.VIDEO_BACKEND || !env.KEMAI_PROXY_SECRET) return new Response(JSON.stringify({detail:'影片主機尚未啟用，請稍後再來。'}), {status:503,headers});
    const upstream = new URL(env.VIDEO_BACKEND);
    if (upstream.protocol !== 'https:' || !upstream.hostname.endsWith('.onrender.com')) return new Response(JSON.stringify({detail:'影片主機設定無法使用。'}),{status:503,headers});
    if (!['GET','POST'].includes(request.method)) return new Response('{}',{status:405,headers});
    if (request.method==='POST' && request.headers.get('origin')!==url.origin) return new Response(JSON.stringify({detail:'請從客脈影片工坊提交影片。'}),{status:403,headers});
    if (request.method==='POST' && Number(request.headers.get('content-length')||0)>21000000) return new Response(JSON.stringify({detail:'上傳總量上限為 20 MB。'}),{status:413,headers});
    upstream.pathname=url.pathname;upstream.search='';
    const forward = new Headers();
    for (const key of ['content-type','content-length','range','origin']) if(request.headers.has(key)) forward.set(key,request.headers.get(key));
    forward.set('x-kemai-proxy',env.KEMAI_PROXY_SECRET);
    forward.set('x-kemai-ip',request.headers.get('cf-connecting-ip')||'unknown');
    try {
      const response = await fetch(upstream,{method:request.method,headers:forward,body:request.method==='POST'?request.body:undefined,redirect:'manual'});
      if (response.status>=300 && response.status<400) throw new Error('Unexpected backend redirect');
      const result = new Response(response.body,response);
      result.headers.set('Cache-Control','no-store');result.headers.set('X-Robots-Tag','noindex, nofollow');
      result.headers.set('Referrer-Policy','no-referrer');result.headers.set('X-Content-Type-Options','nosniff');
      return result;
    } catch (error) {
      console.error('Video backend connection failed:',error.name,error.message);
      return new Response(JSON.stringify({detail:'免費影片主機正在啟動或暫時離線，請約 1 分鐘後再試。'}),{status:503,headers});
    }
  }
};
