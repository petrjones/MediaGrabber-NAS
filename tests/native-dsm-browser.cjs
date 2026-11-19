// Real loader CGI, Vue code, login CGI shell, one-use grant, WSGI and nginx.
// Only DSM SDK container widgets and native identity/group validation are mocks.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.MG_TEST_CHROME});
  const base='http://127.0.0.1:18790';
  try{
    for(const mode of ['', 'session', 'current']){
      const context=await browser.newContext();
      await context.addCookies([{name:'id',value:'fixture-private-dsm-cookie',domain:'127.0.0.1',path:'/'}]);
      assert(!(await context.cookies()).some(c=>c.name.startsWith('mg_')),'test must start without a cached app session');
      const page=await context.newPage(),errors=[],requests=[];
      page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r));
      await page.goto(base+'/mediagrabber/fixture/native-host'+(mode?'?'+mode:''));
      const frame=page.frameLocator('iframe[title="MediaGrabber NAS"]');
      await frame.locator('#application').waitFor({state:'visible'});
      assert.equal(await frame.locator('#login').isVisible(),false);
      assert((await context.cookies()).some(c=>c.name==='mg_portal_session'));
      const auth=requests.find(r=>new URL(r.url()).pathname.endsWith('/dsm-login.cgi'));
      assert(auth,'native app must call validator before entering app');
      assert.equal(auth.headers()['x-syno-token'],'fixture-dsm-token');
      assert(!auth.url().includes('SynoToken='),'login token must be a header, not an application URL parameter');
      assert(!(await page.locator('iframe').getAttribute('src')).includes('fixture-dsm-token'));
      await frame.locator('[data-tab=settings]').click();
      await frame.locator('#settings-form [name=rate_kib]').fill('77');
      await frame.locator('#settings-form .primary').click();
      const child=page.frames().find(f=>new URL(f.url()).pathname==='/mediagrabber/');
      await child.waitForFunction(async()=>(await fetch('api/state').then(r=>r.json())).settings.rate_kib===77);
      const received=await child.evaluate(()=>fetch('fixture/received').then(r=>r.json()));
      assert(!received.cookie.includes('fixture-private-dsm-cookie'));
      await frame.locator('#logout').click();await frame.locator('#login').waitFor({state:'visible'});
      assert.equal(await child.evaluate(()=>fetch('api/state').then(r=>r.status)),401);
      assert.deepEqual(errors,[]);
      await context.close();
    }
    for(const mode of ['missing','expired']){
      const context=await browser.newContext();
      await context.addCookies([{name:'id',value:mode==='expired'?'expired-cookie':'fixture-private-dsm-cookie',domain:'127.0.0.1',path:'/'}]);
      const page=await context.newPage();
      await page.goto(base+'/mediagrabber/fixture/native-host'+(mode==='missing'?'?missing':''));
      await page.getByText(mode==='missing'?'DSM-TOKEN-MISSING':'DSM-AUTH-7',{exact:false}).waitFor();
      assert.equal(await page.locator('iframe').count(),0,'unverified session must not enter application');
      assert.equal(await page.locator('a[href="/mediagrabber/"]').count(),1);
      assert(!(await context.cookies()).some(c=>c.name==='mg_portal_session'));
      await context.close();
    }
    console.log('PASS native DSM flow: fresh browser session, native loader token, SDK-session fallback/current token, real shell handoff and app login, same-origin framing, settings, logout, missing/expired session denial. Native DSM SDK and identity validator remain mocked.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
