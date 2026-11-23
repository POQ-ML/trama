const {test,after}=require('node:test');
const assert=require('node:assert/strict');
const {mkdtempSync,rmSync,symlinkSync,mkdirSync,writeFileSync}=require('node:fs');
const {tmpdir}=require('node:os');
const {join,resolve,delimiter}=require('node:path');
const {execFileSync}=require('node:child_process');
const web=resolve(__dirname,'..');
const output=mkdtempSync(join(tmpdir(),'trama-navigation-tests-'));
// Compile staged components and real adapters; output and the Next alias stay outside src.
const config=join(output,'tsconfig.json');
writeFileSync(config,JSON.stringify({compilerOptions:{target:'ES2020',module:'commonjs',moduleResolution:'node',jsx:'react-jsx',esModuleInterop:true,strict:true,skipLibCheck:true,baseUrl:web,paths:{'@/*':['./*']},outDir:join(output,'compiled')},files:['lib/projects.ts','lib/scopedDiscovery.ts','components/ProjectSourcesMap.tsx','components/DiscoveryWorkspace.tsx','components/AcademicProject.tsx','components/ProjectActivity.tsx'].map(p=>join(web,p))}));
execFileSync(join(web,'node_modules/.bin/tsc'),['-p',config],{cwd:web,stdio:'pipe'});
const base=join(output,'compiled/apps/web');
const aliases=join(output,'aliases');mkdirSync(join(aliases,'@'),{recursive:true});symlinkSync(join(base,'lib'),join(aliases,'@/lib'),'dir');
const previousNodePath=process.env.NODE_PATH;
process.env.NODE_PATH=[aliases,join(web,'node_modules'),previousNodePath].filter(Boolean).join(delimiter);
require('node:module').Module._initPaths();
const {diagnosisApi}=require(join(base,'lib/scopedDiscovery.js'));
const {projectsApi,githubRepoUrl}=require(join(base,'lib/projects.js'));
const {runHref,sourceHref,scopeIdentity}=require(join(base,'lib/projectRoutes.js'));
const React=require(join(web,'node_modules/react'));
const {renderToStaticMarkup}=require(join(web,'node_modules/react-dom/server'));
const ProjectSourcesMap=require(join(base,'components/ProjectSourcesMap.js')).default;
const DiscoveryWorkspace=require(join(base,'components/DiscoveryWorkspace.js')).default;
after(()=>{if(previousNodePath===undefined)delete process.env.NODE_PATH;else process.env.NODE_PATH=previousNodePath;require('node:module').Module._initPaths();rmSync(output,{recursive:true,force:true});});
function spyFetch(t,handler){const original=globalThis.fetch;t.after(()=>{globalThis.fetch=original;});const calls=[];globalThis.fetch=async(url,init)=>{calls.push({url:new URL(url),init});return handler?handler(url,init):new Response(JSON.stringify({id:'result'}));};return calls;}
function resourceData(t,data){const resource=require(join(base,'lib/useProjectResource.js'));const original=resource.useProjectResource;t.after(()=>{resource.useProjectResource=original;});resource.useProjectResource=()=>({data,loading:false,error:null,refresh:()=>{}});}

test('project creation and source binding persist only explicit fields, without launching analysis',async t=>{
 const calls=spyFetch(t);const signal=new AbortController().signal;
 await projectsApi.create('Meu projeto',null,signal);
 await projectsApi.addSource('p/id','https://github.com/example/repo',signal);
 assert.equal(calls.length,2);
 assert.deepEqual(JSON.parse(calls[0].init.body),{name:'Meu projeto',description:null});
 assert.equal(calls[1].url.pathname,'/api/v1/projects/p%2Fid/sources');
 assert.deepEqual(JSON.parse(calls[1].init.body),{source_type:'github',repo_url:'https://github.com/example/repo'});
 assert.ok(calls.every(c=>!c.url.pathname.includes('discoveries')));
});
test('source adapters stay independent and scoped reanalysis forwards its idempotency key',async t=>{
 const calls=spyFetch(t);const signal=new AbortController().signal;
 const a=diagnosisApi({projectId:'project-a',sourceId:'source-a'}),b=diagnosisApi({projectId:'project-b',sourceId:'source-b'});
 await Promise.all([a.read('foreign/run',signal,'cursor&limit=50'),b.read('own-run',signal)]);
 await a.start('https://github.com/ignored/replacement','stable-key',signal,'old-run');
 assert.equal(calls[0].url.pathname,'/api/v1/projects/project-a/sources/source-a/discoveries/foreign%2Frun');
 assert.equal(calls[0].url.searchParams.get('cursor'),'cursor&limit=50');assert.equal(calls[0].url.searchParams.get('limit'),'20');
 assert.equal(calls[1].url.pathname,'/api/v1/projects/project-b/sources/source-b/discoveries/own-run');
 assert.equal(calls[2].url.pathname,'/api/v1/projects/project-a/sources/source-a/discoveries');
 assert.equal(calls[2].init.method,'POST');assert.equal(calls[2].init.body,undefined);assert.equal(calls[2].init.headers['Idempotency-Key'],'stable-key');
});
test('foreign run 404 never falls back to the global diagnosis endpoint',async t=>{
 const calls=spyFetch(t,()=>new Response(JSON.stringify({error:{code:'not_found',retryable:false}}),{status:404}));
 await assert.rejects(diagnosisApi({projectId:'a',sourceId:'b'}).read('foreign-run',new AbortController().signal),e=>e.status===404 && !e.retryable);assert.equal(calls.length,1);
});
test('cancelling an old source read does not cancel another source request',async t=>{
 const calls=spyFetch(t,(url,init)=>new Promise((resolve,reject)=>{init.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true});if(String(url).includes('/new/'))resolve(new Response(JSON.stringify({id:'new-run'})));}));
 const old=new AbortController(),fresh=new AbortController();
 const pending=diagnosisApi({projectId:'p',sourceId:'old'}).read('run',old.signal);
 const latest=diagnosisApi({projectId:'p',sourceId:'new'}).read('run',fresh.signal);
 old.abort();await assert.rejects(pending,{name:'AbortError'});assert.equal((await latest).id,'new-run');assert.equal(calls[1].init.signal.aborted,false);
});
test('legacy reads remain global and latest-run links preserve encoded project/source identity',async t=>{
 const calls=spyFetch(t);await diagnosisApi().read('legacy',new AbortController().signal);
 assert.equal(calls[0].url.pathname,'/api/v1/discoveries/legacy');
 assert.equal(runHref({projectId:'p/id',sourceId:'s?x'},'r&id'),'/projects/p%2Fid/sources/s%3Fx?run=r%26id');
 assert.equal(runHref(undefined,'legacy'),'/discoveries?run=legacy');
 assert.notEqual(scopeIdentity({projectId:'a',sourceId:'same'}),scopeIdentity({projectId:'b',sourceId:'same'}));
});
test('activity consumes the existing event endpoint without a mutation',async t=>{
 const calls=spyFetch(t,()=>new Response('[]'));assert.deepEqual(await projectsApi.activity(new AbortController().signal),[]);
 assert.equal(calls[0].url.pathname,'/api/v1/projects/activity');assert.equal(calls[0].init.method,undefined);
});
test('source diagnosis never presents the legacy replacement URL form, including during recovery',()=>{
 const html=renderToStaticMarkup(React.createElement(DiscoveryWorkspace,{source:{scope:{projectId:'p',sourceId:'s'},repoUrl:'https://github.com/a/b',initialRun:null}}));
 assert.doesNotMatch(html,/id="repo-url"|id="discovery-form"/);
 assert.match(html,/Recuperando sua análise/);
 const legacy=renderToStaticMarkup(React.createElement(DiscoveryWorkspace));assert.match(legacy,/id="repo-url"/);
});
test('academic map retains full accessible names and labels only project-source affiliation',()=>{
 const name='Pesquisa acadêmica muito longa '.repeat(5).slice(0,160),label='organization/'+('repository-'.repeat(15));
 const html=renderToStaticMarkup(React.createElement(ProjectSourcesMap,{project:{id:'p',name},sources:[{id:'s',label}]}));
 assert.ok(html.includes(sourceHref({projectId:'p',sourceId:'s'})));assert.ok(html.includes(name));assert.ok(html.includes(label));
 assert.match(html,/line-clamp-4/);assert.match(html,/line-clamp-3/);assert.match(html,/Fonte vinculada/);assert.match(html,/Projeto acadêmico/);assert.doesNotMatch(html,/OpenAlex|Avaliado como relevante/);
});
test('GitHub source input rejects other services, file paths, credentials and query parameters',()=>{
 assert.equal(githubRepoUrl(' https://github.com/a/b/ '),'https://github.com/a/b');
 for(const url of ['https://openalex.org/W1','https://github.com/a/b/tree/main','https://user:password@github.com/a/b','https://github.com/a/b?x=1','http://github.com/a/b'])assert.throws(()=>githubRepoUrl(url));
});
test('Add source action is general, with a labeled selector offering only GitHub',t=>{
 resourceData(t,{id:'p',name:'Pesquisa',description:null,source_count:0,sources:[]});
 const AcademicProject=require(join(base,'components/AcademicProject.js')).default;
 const html=renderToStaticMarkup(React.createElement(AcademicProject,{projectId:'p'}));
 assert.match(html,/href="#add-source"[^>]*>Adicionar fonte →<\/a>/);
 assert.match(html,/<label[^>]*for="source-type"[^>]*>Tipo de fonte<\/label>/);
 const select=html.match(/<select[^>]*id="source-type"[\s\S]*?<\/select>/)?.[0];
 assert.ok(select);assert.equal((select.match(/<option\b/g)||[]).length,1);
 assert.match(select,/<option value="github"[^>]*>GitHub<\/option>/);assert.doesNotMatch(select,/disabled/);
 assert.match(html,/<button[^>]*type="submit"[^>]*>Adicionar fonte<\/button>/);
 assert.match(html,/URL do repositório GitHub/);assert.doesNotMatch(html,/Adicionar fonte GitHub/);
});
test('empty activity is omitted and a real event has links to its actual project and source',t=>{
 const ProjectActivity=require(join(base,'components/ProjectActivity.js')).default;
 const events=[];resourceData(t,events);assert.equal(renderToStaticMarkup(React.createElement(ProjectActivity)),'');
 events.push({id:'e',project_id:'p',source_id:'s',project_name:'Pesquisa',source_label:'a/b',observed_at:'2026-11-14T12:00:00Z',read_at:null,kind:'source_changed'});
 const html=renderToStaticMarkup(React.createElement(ProjectActivity));assert.ok(html.includes('/projects/p/sources/s'));assert.match(html,/href="\/projects\/p"/);assert.match(html,/Não lido/);
});
