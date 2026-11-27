const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

const code = fs.readFileSync(require('node:path').join(__dirname, '../web/creative.js'), 'utf8');
const id = 'a'.repeat(32);
async function mount(job) {
  const nodes = new Map();
  for (const key of ['creativeIdea','creativeResult','creativePlan','creativeStyle','creativeFormat']) {
    nodes.set(key, {value:'test',innerHTML:'',querySelectorAll:()=>[],append(){},focus(){}});
  }
  Object.defineProperty(nodes.get('creativeResult'), 'innerHTML', {
    get(){return this.html || '';},
    set(value){this.html=value; for(const match of value.matchAll(/id="([^"]+)"/g)) nodes.set(match[1], {});}
  });
  const requests=[];
  const context={document:{getElementById:key=>nodes.get(key),createElement:()=>({setAttribute(){}})},
    localStorage:{getItem:()=>id,setItem(){}},setTimeout:()=>1,clearTimeout(){},URL,
    fetch:async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>url==='/api/creative-voices'?{voices:[]}:url.endsWith('/telegram')?{message:'Yuborildi'}:job};}};
  vm.runInNewContext(code,context);
  await new Promise(resolve=>setImmediate(resolve));
  return {nodes,requests,html:()=>nodes.get('creativeResult').innerHTML};
}
test('ready job restores storyboard, previews, cast and explicit render action',async()=>{
  const ui=await mount({id,status:'ready',progress:60,scene_images:['/scene/1'],story:{title:'<script>bad</script>',scenes:[{voice:'Salom',speaker:'Jasur'}]}});
  assert.match(ui.html(),/Videoni yasash/);
  assert.match(ui.html(),/Eshitish/);
  assert.match(ui.html(),/data-speaker="Jasur"/);
  assert.match(ui.html(),/src="\/scene\/1"/);
  assert.match(ui.html(),/data-scene-audio="1"/);
  assert.match(ui.html(),/aistudio.google.com\/generate-speech/);
  assert.doesNotMatch(ui.html(),/<script>bad/);
  assert.equal(ui.requests.filter(r=>r.options?.method==='POST').length,0);
});
test('done job displays video and sends only on explicit Telegram click',async()=>{
  const ui=await mount({id,status:'done',video:'clip.mp4',progress:100,story:{scenes:[]}});
  assert.match(ui.html(),/download/);
  assert.match(ui.html(),/<video/);
  assert.equal(ui.requests.filter(r=>r.options?.method==='POST').length,0);
  await ui.nodes.get('creativeTelegram').onclick();
  assert.equal(ui.requests.filter(r=>r.url.endsWith('/telegram')).length,1);
  assert.equal(ui.nodes.get('creativeTelegram').disabled,true);
});
test('rendering job displays real stage progress and keeps new creation disabled',async()=>{
  const ui=await mount({id,status:'rendering',stage:'frames',progress:80,story:{scenes:[]}});
  assert.match(ui.html(),/aria-valuenow="80"/);
  assert.equal(ui.nodes.get('creativePlan').disabled,true);
});
