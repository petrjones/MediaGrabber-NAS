// Render the package's JSONP wizard with Vue 2.7.14 and a mocked DSM UI host.
// This validates our form/hook logic; it is not a DSM integration test.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
// Fixture for the flat name -> string mapping used by the official install
// example, not a reimplementation/proof of DSM's closed-source parser.
function environmentValues(values){
  assert(values && typeof values==='object' && !Array.isArray(values),'wizard values must be a flat mapping');
  assert(Object.values(values).every(value=>typeof value==='string'),'wizard values must be strings');
  return JSON.parse(JSON.stringify(values));
}
assert.throws(()=>environmentValues([{wizard_admin_password:'old-array-export'}]),/flat mapping/);
assert.throws(()=>environmentValues({wizard_admin_password:{nested:'invalid'}}),/strings/);
function checkInstallerBridge(values){
  const env=environmentValues(values);
  if(!process.env.MG_TEST_SHELL)return;
  const shell=process.env.MG_TEST_SHELL;
  // Read fixture values as literal data, then export within POSIX sh. This
  // avoids Windows/Node's case folding of lower-case environment names.
  const bridge='IFS= read -r wizard_admin_password; IFS= read -r wizard_admin_password_confirm; export wizard_admin_password wizard_admin_password_confirm; SYNOPKG_PKG_STATUS=INSTALL; export SYNOPKG_PKG_STATUS; . "$1"';
  const args=[...(/busybox/i.test(path.basename(shell))?['sh']:[]),'-c',bridge,'bridge',path.join(__dirname,'../synology/scripts/preinst')];
  const result=spawnSync(shell,args,{env:process.env,input:env.wizard_admin_password+'\n'+env.wizard_admin_password_confirm+'\n',encoding:'utf8'});
  assert.equal(result.status,0,'wizard values must pass actual preinst validation: '+(result.stderr||result.error||''));
}
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.MG_TEST_CHROME||undefined});
  const page=await browser.newPage({viewport:{width:1000,height:760}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const template=fs.readFileSync(path.join(__dirname,'../synology/wizard-runtime.js'),'utf8');
  try{
    for(const cs of [true,false])for(const kind of ['install','upgrade','uninstall']){
      await page.goto('about:blank');
      await page.setContent('<!doctype html><html><head><meta charset="utf-8"><style>body{font:16px Segoe UI,sans-serif;background:#f5f7fa;margin:0}main{max-width:820px;margin:35px auto;background:white;border:1px solid #ddd;padding:30px}h1{color:#087dd3;font-size:24px}.field{display:grid;grid-template-columns:220px 1fr;gap:15px;margin:20px 0}input{padding:9px;border:1px solid #a8b9c9;border-radius:4px}button{background:#008cff;color:white;border:0;border-radius:20px;padding:10px 40px}button:disabled{opacity:.4}p{line-height:1.6;color:#435161}</style></head><body><main><h1 id="heading"></h1><div id="app"></div><button id="next">Další / Next</button></main></body></html>');
      await page.addScriptTag({path:process.env.MG_TEST_VUE});
      await page.evaluate(()=>{
        Vue.config.productionTip=false;Vue.config.devtools=false;
        window.owner={getButton:()=>({setDisabled:value=>{document.querySelector('#next').disabled=value;}})};
        const hook=props=>({getNext:()=>'',checkState:()=>{}});
        hook.props={getOwner:{type:Function,required:true}};
        window.SYNO={SDS:{PkgManApp:{Custom:{useHook:hook,JsonpLoader:{load:module=>{window.wizardModule=module;}}}}}};
        Vue.component('pkg-center-step-content',{render(h){return h('section',this.$slots.default);}});
        Vue.component('v-form',{render(h){return h('form',this.$slots.default);}});
        Vue.component('v-form-item',{props:['label'],render(h){return h('label',{class:'field'},[h('span',this.label),...(this.$slots.default||[])]);}});
        Vue.component('v-input',{props:['value','type'],render(h){return h('input',{attrs:{type:this.type},domProps:{value:this.value},on:{input:event=>this.$emit('input',event.target.value)}});}});
      });
      const code=template.replace('__KIND__',JSON.stringify(kind)).replace('__CZECH__',String(cs)).replace('__OFFLINE__','false');
      await page.addScriptTag({content:code});
      assert(await page.evaluate(()=>wizardModule.__esModule===true));
      await page.evaluate(()=>{
        const component=wizardModule.default.render;
        window.wizardVm=new (Vue.extend(component))({propsData:{getOwner:()=>owner}}).$mount('#app');
        document.querySelector('#heading').textContent=wizardVm.headline;
      });
      if(kind==='install'){
        assert(await page.locator('#next').isDisabled());
        const fields=page.locator('input');assert.equal(await fields.count(),2);
        await fields.nth(0).fill('long-password-12345');
        await fields.nth(1).fill('different-password-12345');
        assert(await page.locator('#next').isDisabled());
        await fields.nth(1).fill('long-password-12345');
        assert(await page.locator('#next').isEnabled());
        const values=await page.evaluate(()=>wizardVm.getValues());
        assert.deepEqual(environmentValues(values),{wizard_admin_password:'long-password-12345',wizard_admin_password_confirm:'long-password-12345'});
        checkInstallerBridge(values);
        await fields.nth(0).fill('české-heslo-12345');await fields.nth(1).fill('české-heslo-12345');
        assert(await page.locator('#next').isEnabled());
        checkInstallerBridge(await page.evaluate(()=>wizardVm.getValues()));
        const literalPassword='Příliš $HOME ; " & \\ dlouhé-heslo';
        await fields.nth(0).fill(literalPassword);await fields.nth(1).fill(literalPassword);
        const literalValues=environmentValues(await page.evaluate(()=>wizardVm.getValues()));
        assert.equal(literalValues.wizard_admin_password,literalPassword);
        assert.equal(literalValues.wizard_admin_password_confirm,literalPassword);
        checkInstallerBridge(literalValues);
        await fields.nth(0).fill(' leading-space-12345');await fields.nth(1).fill(' leading-space-12345');
        assert(await page.locator('#next').isDisabled());
        await fields.nth(0).fill('');await fields.nth(1).fill('');
        if(cs&&process.env.MG_TEST_SCREENSHOTS)await page.screenshot({path:path.join(process.env.MG_TEST_SCREENSHOTS,'mediagrabber-spk-wizard-local-test.png'),fullPage:true});
      }else if(kind==='uninstall'){
        assert.equal(await page.locator('input[type=checkbox]').count(),1);
        assert.deepEqual(environmentValues(await page.evaluate(()=>wizardVm.getValues())),{wizard_remove_private_data:'no'});
        await page.locator('input[type=checkbox]').check();
        assert.deepEqual(environmentValues(await page.evaluate(()=>wizardVm.getValues())),{wizard_remove_private_data:'yes'});
        assert(await page.locator('#next').isEnabled());
      }else{
        assert.equal(await page.locator('input').count(),0);
        assert.deepEqual(environmentValues(await page.evaluate(()=>wizardVm.getValues())),{});
        assert(await page.locator('#next').isEnabled());
      }
    }
    assert.deepEqual(errors,[]);
    console.log('PASS: six CZ/EN wizard variants; flat string exports, old-array rejection, UTF-8/metacharacters, validation'+(process.env.MG_TEST_SHELL?', actual preinst environment bridge':''));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
