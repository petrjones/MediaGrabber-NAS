// Real shipped JS + WSGI + nginx portal. DSM's native validator is a separate
// shell-boundary fixture, and still requires physical DSM verification.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.MG_TEST_CHROME});
  try{
    const context=await browser.newContext();
    await context.addCookies([{name:'id',value:'fixture-private-dsm-cookie',domain:'127.0.0.1',path:'/'}]);
    const page=await context.newPage(),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    const base='http://127.0.0.1:18790';
    await page.goto(base+'/mediagrabber/fixture/launch');
    await page.locator('#application').waitFor({state:'visible'});
    assert.equal(page.url(),base+'/mediagrabber/','ticket removed before any API request');
    assert.equal(await page.locator('#login').isVisible(),false);
    assert.equal(await page.locator('#language option').count(),9);
    const details=await page.evaluate(()=>fetch('fixture/received',{headers:{Authorization:'DSM fixture', 'X-MG-Bridge-Key':'forged'}}).then(r=>r.json()));
    assert(!details.cookie.includes('fixture-private-dsm-cookie'));
    assert(details.cookie.includes('mg_portal_session='));
    assert.equal(details.authorization,'');assert.equal(details.key,'');assert.equal(details.portal,'1');
    assert.equal(await page.evaluate(()=>fetch('api/dsm/issue',{method:'POST',headers:{'Content-Type':'application/json','X-MG-Bridge-Key':'a'.repeat(64)},body:'{}'}).then(r=>r.status)),403);
    assert.equal(await page.evaluate(()=>fetch('api/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.status)),403);
    await page.locator('[data-tab=settings]').click();
    await page.locator('#settings-form [name=rate_kib]').fill('123');
    await page.locator('#settings-form .primary').click();
    await page.waitForFunction(async()=>(await fetch('api/state').then(r=>r.json())).settings.rate_kib===123);
    const backup=await page.locator('a[data-t=export]').getAttribute('href');
    assert.equal(backup,'api/backup');
    assert.equal(await page.evaluate(()=>fetch('api/backup').then(r=>r.status)),200);
    await page.reload();await page.locator('#application').waitFor({state:'visible'});
    await page.locator('#logout').click();await page.locator('#login').waitFor({state:'visible'});
    assert.equal(await page.evaluate(()=>fetch('api/state').then(r=>r.status)),401);
    await page.locator('#login-form [name=password]').fill('test-only-password-83942');
    await page.locator('#login-form button').click();await page.locator('#application').waitFor({state:'visible'});
    const direct=await context.newPage();await direct.goto('http://127.0.0.1:8787/');
    await direct.locator('#login').waitFor({state:'visible'});
    await direct.locator('#login-form [name=password]').fill('test-only-password-83942');
    await direct.locator('#login-form button').click();await direct.locator('#application').waitFor({state:'visible'});
    const rejected=await browser.newPage();await rejected.goto(base+'/mediagrabber/#dsm-ticket='+'b'.repeat(64));
    await rejected.locator('#login').waitFor({state:'visible'});
    assert.equal(rejected.url(),base+'/mediagrabber/');
    assert((await rejected.locator('#login-error').innerText()).length>0);
    assert.deepEqual(errors,[]);
    console.log('DSM portal browser checks passed: one-use handoff, assets, cookie isolation, CSRF, header stripping, save, backup, reload, logout, password fallback and direct access.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
