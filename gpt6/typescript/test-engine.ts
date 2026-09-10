import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {entropy,informationGain,posterior,rank,acceptPlan,observe,parseState,parseTask,taskKey} from './engine.ts';
import {initialize,read,commit,git,REF} from './gitstore.ts';
function fixtures(){
  const load=(name:string)=>JSON.parse(readFileSync(new URL('../examples/'+name,import.meta.url),'utf8'));
  return {state:parseState(load('state.json')),tasks:(load('tasks.json') as unknown[]).map(parseTask),event:load('event.json')};
}
function near(a:number,b:number){assert.ok(Math.abs(a-b)<1e-12,`${a} != ${b}`);}
test('entropy',()=>{assert.equal(entropy(0),0);assert.equal(entropy(1),0);assert.equal(entropy(.5),1);});
test('perfect test',()=>near(informationGain(.6,1,0),entropy(.6)));
test('useless test',()=>near(informationGain(.6,.8,.8),0));
test('Bayes',()=>{near(posterior(.6,.9,.1,true),27/29);near(posterior(.6,.9,.1,false),1/7);});
test('invalid numbers',()=>{for(const p of [NaN,Infinity,-.1,1.1])assert.throws(()=>entropy(p));});
test('impossible observation',()=>assert.throws(()=>posterior(0,1,0,true)));
test('information bounds',()=>{for(const p of [0,.1,.5,.9,1])for(const s of [0,.1,.5,.9,1])for(const f of [0,.1,.5,.9,1]){
  const ig=informationGain(p,s,f);assert.ok(ig>=-1e-12&&ig<=entropy(p)+1e-12);
}});
test('ranking',()=>{const {state,tasks}=fixtures(),r=rank(state,tasks);assert.deepEqual(r.ranking.map(v=>v.task.id),['T1','T3','T2']);near(r.ranking[2].score,.102);});
test('input not mutated',()=>{const {state,tasks,event}=fixtures(),before=JSON.stringify(state);observe(acceptPlan(state,rank(state,tasks)),event,Buffer.from('evidence'));assert.equal(JSON.stringify(state),before);});
test('positive observation changes decision',()=>{const {state,tasks,event}=fixtures(),next=observe(acceptPlan(state,rank(state,tasks)),event,Buffer.from('evidence'));
  near(next.hypotheses.H1,27/29);assert.equal(next.profiles.diagnose_cache.alpha,10);assert.equal(rank(next,tasks).selected?.task.id,'T2');near(next.budget,2.88);
});
test('failure not false hypothesis; dependencies remain blocked',()=>{const {state,tasks,event}=fixtures();event.success=false;event.positive=null;
  const next=observe(acceptPlan(state,rank(state,tasks)),event,Buffer.from('evidence'));assert.equal(next.hypotheses.H1,.6);assert.equal(next.profiles.diagnose_cache.beta,2);
  assert.equal(rank(next,[{...tasks[1],depends_on:['T1']}]).rejected[0].reason,'blocked');
});
test('unknown fact',()=>{const {state,tasks}=fixtures();tasks[0].facts=['invented'];assert.throws(()=>rank(state,tasks));});
test('injected score or command',()=>{const {state,tasks}=fixtures();for(const key of ['score','command'])assert.throws(()=>rank(state,[{...tasks[0],[key]:999}]));});
test('duplicate IDs',()=>{const {state,tasks}=fixtures();assert.throws(()=>rank(state,[tasks[0],tasks[0]]));});
test('cycle',()=>{const {state,tasks}=fixtures();tasks[0].depends_on=['T2'];tasks[1].depends_on=['T1'];assert.throws(()=>rank(state,tasks));});
test('unknown dependency',()=>{const {state,tasks}=fixtures();tasks[0].depends_on=['unknown'];assert.throws(()=>rank(state,tasks));});
test('policy, budget and stop',()=>{const {state,tasks}=fixtures();state.profiles.diagnose_cache.allowed=false;state.budget=0;const r=rank(state,tasks);
  assert.equal(r.selected,null);assert.deepEqual(new Set(r.rejected.map(v=>v.reason)),new Set(['policy','budget']));
});
test('risk gate',()=>{const {state,tasks}=fixtures();state.profiles.diagnose_cache.risk=.3;assert.equal(rank(state,tasks).rejected[0].reason,'policy');});
test('threshold',()=>{const {state,tasks}=fixtures();state.min_score=1;assert.equal(rank(state,tasks).selected,null);});
test('duplicate paraphrase',()=>{const {state,tasks}=fixtures();const r=rank(state,[tasks[0],{...tasks[0],id:'T4',title:'Different wording'}]);assert.equal(r.ranking.length,1);assert.equal(r.rejected[0].reason,'duplicate');});
test('reused evidence',()=>{const {state,tasks,event}=fixtures();let next=observe(acceptPlan(state,rank(state,tasks)),event,Buffer.from('evidence'));
  next=acceptPlan(next,rank(next,tasks));assert.throws(()=>observe(next,{...event,event_id:'E2',task_id:'T2',positive:null},Buffer.from('evidence')));
});
test('pending rejects another plan',()=>{const {state,tasks}=fixtures();assert.throws(()=>rank(acceptPlan(state,rank(state,tasks)),tasks));});
test('empty candidates',()=>{const {state}=fixtures();assert.equal(rank(state,[]).selected,null);});
test('Unicode key',()=>{const {tasks}=fixtures();assert.equal(taskKey(tasks[0],'Cel: pamięć 🧠'),'691e1e1f11152dbc278a9b4fba9bda502169720afa49b3f8557abacec25b3d51');});
test('Git roundtrip and stale writer',()=>{const {state,tasks}=fixtures(),tmp=mkdtempSync(join(tmpdir(),'intuition-test-')),repo=join(tmp,'memory.git');
  try {const base=initialize(repo,state);assert.equal(read(repo).base,base);assert.equal(JSON.stringify(read(repo).state),JSON.stringify(state));
    const updated=acceptPlan(state,rank(state,tasks)),next=commit(repo,base,updated,{kind:'plan'});assert.equal(read(repo).base,next);
    assert.throws(()=>commit(repo,base,state,{kind:'stale'}));assert.equal(read(repo).base,next);assert.equal(git(repo,['rev-list','--count',REF]).toString().trim(),'2');git(repo,['fsck','--no-reflogs']);
  } finally {rmSync(tmp,{recursive:true,force:true});}
});
