const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.MG_TEST_CHROME});
  try{
    const page=await browser.newPage({viewport:{width:1376,height:950}}),errors=[],requests=[];
    page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r));
    const base='http://127.0.0.1:'+(process.env.MG_TEST_PORT||18819);
    const prefix=process.env.MG_TEST_PREFIX||'';
    const requestPath=r=>new URL(r.url()).pathname.replace(prefix,'');
    await page.goto(base+prefix+'/');
    await page.locator('#login-form [name=password]').fill('test-only-password-83942');
    await page.locator('#login-form button').click();await page.locator('#application').waitFor({state:'visible'});
    await page.locator('#queue-list .job').waitFor();
    assert(!requests.some(r=>requestPath(r)==='/api/history'),'history is lazy');
    await page.locator('[data-tab=history]').click();
    await page.waitForFunction(()=>document.querySelectorAll('#history-list .job').length===50);
    assert.match(await page.locator('#history-shown').innerText(),/50 \/ 125/);
    const card=await page.locator('#history-list .job').first().boundingBox();
    assert(card.height<120,'desktop history cards should be compact');
    if(process.env.MG_TEST_SCREENSHOTS){
      await page.screenshot({path:path.join(process.env.MG_TEST_SCREENSHOTS,'history-0019-desktop.png')});
      await page.setViewportSize({width:390,height:844});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      await page.screenshot({path:path.join(process.env.MG_TEST_SCREENSHOTS,'history-0019-mobile.png')});
      await page.setViewportSize({width:1376,height:950});
    }
    await page.evaluate(()=>{window.firstHistoryNode=document.querySelector('#history-list .job');});
    await page.evaluate(()=>refresh());
    assert(await page.evaluate(()=>window.firstHistoryNode===document.querySelector('#history-list .job')),'polling must not rebuild history');
    assert(requests.filter(r=>requestPath(r)==='/api/state').every(r=>new URL(r.url()).searchParams.get('history')==='0'));
    assert(!requests.some(r=>r.method()==='GET'&&/\/api\/jobs\//.test(r.url())),'summary list must not fetch full job details');
    await page.locator('#history-list .job').first().getByRole('button',{name:'Výsledek',exact:true}).click();
    await page.locator('#result-dialog').waitFor({state:'visible'});
    assert.match(await page.locator('#result-content').innerText(),/Detailed track/);
    assert(requests.some(r=>r.method()==='GET'&&/\/api\/jobs\//.test(r.url())));
    await page.locator('#result-dialog .dialog-footer .close-dialog').click();
    await page.locator('#history-more').click();
    await page.waitForFunction(()=>document.querySelectorAll('#history-list .job').length===100);
    assert(await page.evaluate(()=>window.firstHistoryNode===document.querySelector('#history-list .job')),'loading more must append');
    await page.locator('#history-more').click();
    await page.waitForFunction(()=>document.querySelectorAll('#history-list .job').length===125);
    assert(await page.locator('#history-more').isHidden());
    const titles=await page.locator('#history-list .job-title').allTextContents();
    assert.equal(new Set(titles.map(x=>x.split('. ').slice(1).join('. '))).size,125);
    assert.match(titles[0],/History 125/);assert.match(titles[124],/History 001/);
    page.once('dialog',d=>d.dismiss());
    await page.locator('#history-clear').click();
    assert.equal(await page.locator('#history-list .job').count(),125);
    assert(!requests.some(r=>r.method()==='DELETE'&&requestPath(r)==='/api/history'));
    page.once('dialog',d=>d.accept());
    await page.locator('#history-clear').click();
    await page.waitForFunction(()=>document.querySelectorAll('#history-list .job').length===0);
    await page.waitForFunction(()=>document.querySelector('#history-clear').disabled);
    assert.match(await page.locator('#history-list').innerText(),/Historie je zatím prázdná|prázdná/);
    const state=await page.evaluate(()=>fetch(appUrl('/api/state?history=0')).then(r=>r.json()));
    assert.equal(state.job_totals.history,0);assert.equal(state.job_totals.queue,1);assert.equal(state.sources.length,1);
    // Mobile layout after explicit refresh has no horizontal overflow.
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    assert.deepEqual(errors,[]);
    console.log('PASS history UI: compact 50-row pages, stable DOM under polling/append, lazy detail, 125 unique records, cancel/confirm clear, preserved queue/source, mobile width.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
