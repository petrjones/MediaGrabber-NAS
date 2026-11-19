// Execute real UI functions without a browser or network. DOM fixtures represent
// only the form values needed to check mode guidance and localized control hints.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const root=path.join(__dirname,'../mg_nas/static');
const elements={};
const context=vm.createContext({location:{pathname:'/'},localStorage:{getItem:()=>null,setItem:(key,value)=>{elements[key]=value;}},navigator:{language:'en-US'},document:{querySelector:selector=>elements[selector]}});
vm.runInContext(fs.readFileSync(path.join(root,'locales.js'),'utf8'),context);
const code=fs.readFileSync(path.join(root,'app.js'),'utf8').split("document.addEventListener('pointerover'")[0];
vm.runInContext(code,context);
for(const [input,expected] of [['cs-CZ','cs'],['en-US','en'],['es-MX','es'],['de-AT','de'],['fr-CA','fr'],['pt','pt-PT'],['pt_br','pt-BR'],['pt-AO','pt-PT'],['pl-PL','pl'],['it-CH','it'],['xx','en']]){
    assert.equal(vm.runInContext(`detectLanguage(${JSON.stringify(input)})`,context),expected);
}
const form={elements:{start_mode:{value:'new'}}};
elements['#source-form']=form;
elements['#source-mode-help']={textContent:''};
elements['#source-locked-help']={hidden:true};
elements['#start-date-field']={hidden:true};
let checks=0;
for(const language of ['cs','en','es','de','fr','pt-PT','pt-BR','pl','it']){
    vm.runInContext(`language=${JSON.stringify(language)}`,context);
    for(const [mode,key] of [['new','newExplanation'],['all','allExplanation'],['date','dateExplanation']]){
        form.elements.start_mode.value=mode;
        vm.runInContext('editingSource=null;updateSourceHelp()',context);
        assert.equal(elements['#source-mode-help'].textContent,vm.runInContext(`t('${key}')`,context));
        assert.equal(elements['#start-date-field'].hidden,mode!=='date');
        assert.equal(elements['#source-locked-help'].hidden,true);
        vm.runInContext('editingSource={};updateSourceHelp()',context);
        assert.equal(elements['#source-locked-help'].hidden,false);
        checks++;
    }
    const makeControl=(name,tagName='INPUT')=>({name,tagName,dataset:{},classList:{contains:()=>false},closest:()=>null,setAttribute(key,value){this[key]=value;}});
    const controls=['mode','quality','subtitles','folder','playlist','metadata','duplicates','subfolder','renumber','exclude','interval_minutes','start_mode','start_date','name','url','rate_kib','minimum_free_mb','max_attempts','timezone','window_start','window_end'].map(name=>makeControl(name));
    const fixture={querySelectorAll:()=>controls};context.fixture=fixture;
    vm.runInContext('applyHints(fixture)',context);
    for(const el of controls){assert.ok(el.dataset.tooltip.length>30,`${language}: ${el.name}`);assert.equal(el['aria-description'],el.dataset.tooltip);checks++;}
    assert.equal(vm.runInContext('Object.values(HINT_KEYS).every(k=>Boolean(STRINGS[language][k]))',context),true);
}
console.log(`UI runtime checks passed: ${checks} mode and control checks across 9 languages; regional language detection passed.`);

vm.runInContext('setHintsEnabled(false)',context);
assert.equal(elements['mg-nas-hints'],'off');
vm.runInContext('showHint({dataset:{tooltip:"must stay hidden"}})',context);
assert.equal(vm.runInContext('hintTarget',context),null);
vm.runInContext('setHintsEnabled(true)',context);
assert.equal(elements['mg-nas-hints'],'on');
const label={dataset:{},removeAttribute:()=>{}};
const checkbox={name:'duplicates',tagName:'INPUT',dataset:{},classList:{contains:()=>false},closest:selector=>selector==='label'?label:null,setAttribute:()=>{}};
context.labelFixture={querySelectorAll:()=>[checkbox]};
vm.runInContext('applyHints(labelFixture)',context);
assert.equal(label.dataset.tooltip,checkbox.dataset.tooltip);
assert.ok(label.dataset.tooltip.length>30);
console.log('Tooltip on/off persistence, hidden bubbles and shared label/control hints passed.');
