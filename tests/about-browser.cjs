// Run against the isolated tests/serve_fixture.py server. Release responses are fixtures.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.MG_TEST_CHROME});
  const dir=process.env.MG_TEST_SCREENSHOTS;
  if(dir)fs.mkdirSync(dir,{recursive:true});
  try{
    for(const prefix of ['', '/mediagrabber']){
      const context=await browser.newContext({viewport:{width:1280,height:1000},locale:'cs-CZ'});
      const page=await context.newPage(),errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      if(prefix)await page.route('**/mediagrabber/**',async route=>{
        const url=route.request().url().replace('/mediagrabber/','/');
        const response=await route.fetch({url});
        await route.fulfill({response});
      });
      let result={status:'current',version:'4.3.0',url:'https://github.com/petrjones/MediaGrabber/releases/tag/v4.3.0'},delay=1200,calls=0,abort=false;
      await page.route('**/api/windows-release',async route=>{
        calls++;
        if(abort)return route.abort();
        if(delay)await new Promise(resolve=>setTimeout(resolve,delay));
        await route.fulfill({json:result});
      });
      await page.goto('http://127.0.0.1:'+(process.env.MG_TEST_PORT||'18820')+prefix+'/');
      await page.locator('#login').waitFor({state:'visible'});
      await page.locator('[name=password]').fill('test-only-password-83942');
      await page.locator('#login-form button').click();
      await page.locator('#application').waitFor({state:'visible'});
      const started=Date.now();
      await page.locator('#about-button').click();
      assert.equal(await page.locator('#about-dialog').isVisible(),true);
      assert.ok(Date.now()-started<1100,'About must open before the delayed release response');
      assert.match(await page.locator('#windows-release').innerText(),/Ověřuji/);
      await page.locator('#windows-release').filter({hasText:'4.3.0'}).waitFor();
      await page.locator('#component-list li').first().waitFor();
      assert.equal(await page.locator('#windows-project-link').getAttribute('href'),result.url);
      assert.equal((await page.locator('#about-dialog').innerText()).includes('4.2.0'),false);
      delay=0;
      result={status:'current',version:'4.4.0',url:'https://github.com/petrjones/MediaGrabber/releases/tag/v4.4.0'};
      await page.locator('#about-dialog .dialog-footer button').click();
      await page.locator('#about-button').click();
      await page.locator('#windows-release').filter({hasText:'4.4.0'}).waitFor();
      assert.equal(calls,2,'Every opening asks the NAS, independently of the component cache');
      result={...result,status:'cached'};
      await page.locator('#about-dialog .dialog-footer button').click();
      await page.locator('#about-button').click();
      await page.locator('#windows-release').filter({hasText:'Poslední ověřená'}).waitFor();
      abort=true;
      await page.locator('#about-dialog .dialog-footer button').click();
      await page.locator('#about-button').click();
      await page.waitForFunction(()=>windowsReleaseRequest===4);
      await page.locator('#windows-release').filter({hasText:'Poslední ověřená'}).waitFor();
      abort=false;
      result={status:'unavailable',version:null,url:'https://github.com/petrjones/MediaGrabber/releases/latest'};
      await page.locator('#about-dialog .dialog-footer button').click();
      await page.locator('#about-button').click();
      await page.locator('#windows-release').filter({hasText:'Aktuální verzi Windows se nepodařilo'}).waitFor();
      assert.equal(await page.locator('#windows-project-link').getAttribute('href'),result.url);
      result={status:'current',version:'4.4.0',url:'https://github.com/petrjones/MediaGrabber/releases/tag/v4.4.0'};
      for(const language of ['cs','en','es','de','fr','pt-PT','pt-BR','pl','it']){
        await page.locator('#about-dialog .dialog-footer button').click();
        await page.locator('#language').selectOption(language);
        await page.locator('#about-button').click();
        await page.locator('#windows-release').filter({hasText:'4.4.0'}).waitFor();
        assert.equal(await page.locator('#windows-release').innerText(),await page.evaluate(()=>STRINGS[language].latestWindowsVersion.replace('{version}','4.4.0')));
        assert.equal((await page.locator('#about-dialog').innerText()).includes('4.2.0'),false);
      }
      await page.locator('#about-dialog .dialog-footer button').click();
      await page.locator('#language').selectOption('cs');
      await page.locator('#about-button').click();
      await page.locator('#windows-release').filter({hasText:'4.4.0'}).waitFor();
      if(dir)await page.screenshot({path:path.join(dir,'about'+(prefix?'-portal':'-direct')+'.png')});
      await page.setViewportSize({width:390,height:844});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      assert.equal(await page.locator('#about-dialog').evaluate(el=>el.scrollWidth>el.clientWidth),false);
      if(dir)await page.screenshot({path:path.join(dir,'about'+(prefix?'-portal':'-direct')+'-mobile.png')});
      assert.deepEqual(errors,[]);
      await context.close();
    }
    console.log('About browser checks passed: immediate dialog, refreshed/cached/unavailable versions, nine locales, desktop/mobile, direct and portal paths.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
