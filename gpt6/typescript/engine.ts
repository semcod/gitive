/** Reference planner. Node built-ins only; external JSON is runtime-validated. */
import { createHash } from 'node:crypto';

export type Profile = {
  alpha: number; beta: number; benefit: number; cost: number; risk: number; allowed: boolean;
  diagnostic_hypothesis: string | null; effect_hypothesis: string | null;
  sensitivity: number; false_positive: number;
};
export type Fact = { id: string; text: string; source: string; status: 'observed' | 'reported' | 'disputed' };
export type Task = { id: string; title: string; profile: string; facts: string[]; depends_on: string[]; acceptance: string };
export type Ranked = { task: Task; key: string; probability: number; information_gain: number; expected_benefit: number; score: number };
export type State = {
  goal: string; budget: number; information_weight: number; max_risk: number; min_score: number;
  facts: Fact[]; hypotheses: Record<string, number>; profiles: Record<string, Profile>;
  completed_keys: string[]; completed_ids: string[]; successful_ids: string[]; seen_evidence: string[]; seen_events: string[];
  pending: Ranked | null;
};
export type Decision = { selected: Ranked | null; ranking: Ranked[]; rejected: {id: string; reason: string}[]; status: string };
export type Observation = {event_id: string; task_id: string; success: boolean; positive: boolean | null; summary: string};

export function object(x: unknown): Record<string, unknown> {
  if (x === null || typeof x !== 'object' || Array.isArray(x)) throw new Error('Expected object');
  return x as Record<string, unknown>;
}
export function number(x: unknown, label: string, lo = 0, hi = Infinity): number {
  if (typeof x !== 'number' || !Number.isFinite(x) || x < lo || x > hi) throw new Error(`${label}: invalid number`);
  return x;
}
export function text(x: unknown, label: string): string {
  if (typeof x !== 'string' || !x.trim() || x.length > 10000) throw new Error(`${label}: invalid text`);
  return x;
}
export function identifier(x: unknown, label: string): string {
  const value = text(x, label);
  if (!/^[A-Za-z0-9_:.-]{1,128}$/.test(value)) throw new Error(`${label}: invalid identifier`);
  return value;
}
export function identifiers(x: unknown, label: string): string[] {
  if (!Array.isArray(x)) throw new Error(`${label}: expected array`);
  const values = x.map(v => identifier(v, label));
  if (new Set(values).size !== values.length) throw new Error(`${label}: duplicate ID`);
  return values;
}
function exactKeys(x: Record<string, unknown>, keys: string[]): void {
  if (Object.keys(x).sort().join('|') !== keys.sort().join('|')) throw new Error('Incorrect fields');
}
export function entropy(p: number): number {
  number(p, 'probability', 0, 1);
  return p === 0 || p === 1 ? 0 : -p*Math.log2(p) - (1-p)*Math.log2(1-p);
}
export function informationGain(p: number, s: number, f: number): number {
  number(p, 'prior', 0, 1); number(s, 'sensitivity', 0, 1); number(f, 'false_positive', 0, 1);
  const q = p*s + (1-p)*f;
  return Math.max(0, entropy(q) - p*entropy(s) - (1-p)*entropy(f));
}
export function posterior(p: number, s: number, f: number, positive: boolean): number {
  number(p, 'prior', 0, 1); number(s, 'sensitivity', 0, 1); number(f, 'false_positive', 0, 1);
  if (typeof positive !== 'boolean') throw new Error('positive: expected boolean');
  const [a, b] = positive ? [s, f] : [1-s, 1-f];
  const denominator = p*a + (1-p)*b;
  if (denominator === 0) throw new Error('Observation impossible under the declared model; review the model');
  return p*a/denominator;
}
export function parseTask(raw: unknown): Task {
  const r = object(raw);
  exactKeys(r, ['id','title','profile','facts','depends_on','acceptance']);
  return {id:identifier(r.id,'id'), title:text(r.title,'title'), profile:identifier(r.profile,'profile'),
    facts:identifiers(r.facts,'facts'), depends_on:identifiers(r.depends_on,'depends_on'), acceptance:text(r.acceptance,'acceptance')};
}
export function taskKey(task: Task, goal: string): string {
  const ascii = JSON.stringify([goal, task.profile, [...task.facts].sort()])
    .replace(/[\u007f-\uffff]/g, c => '\\u'+c.charCodeAt(0).toString(16).padStart(4,'0'));
  return createHash('sha256').update(ascii).digest('hex');
}
export function parseState(raw: unknown): State {
  const r = object(raw);
  const factsRaw = r.facts;
  if (!Array.isArray(factsRaw)) throw new Error('facts: expected array');
  const facts: Fact[] = factsRaw.map(rawFact => {
    const f = object(rawFact);
    const status = f.status;
    if (status !== 'observed' && status !== 'reported' && status !== 'disputed') throw new Error('Invalid fact status');
    return {id:identifier(f.id,'fact id'), text:text(f.text,'fact text'), source:text(f.source,'fact source'), status};
  });
  identifiers(facts.map(f=>f.id), 'fact IDs');
  const hypotheses: Record<string,number> = Object.create(null);
  for (const [k,v] of Object.entries(object(r.hypotheses))) hypotheses[k] = number(v,'hypothesis',0,1);
  const profiles: Record<string,Profile> = Object.create(null);
  for (const [k,v] of Object.entries(object(r.profiles))) {
    const p = object(v);
    function hypothesis(field: string): string | null {
      if (p[field] === null) return null;
      const id = identifier(p[field],field);
      if (!Object.hasOwn(hypotheses,id)) throw new Error('Unknown profile hypothesis');
      return id;
    }
    if (typeof p.allowed !== 'boolean') throw new Error('allowed: expected boolean');
    profiles[k] = {alpha:number(p.alpha,'alpha',1e-12,1e12), beta:number(p.beta,'beta',1e-12,1e12),
      benefit:number(p.benefit,'benefit',0,1e12), cost:number(p.cost,'cost',0,1e12), risk:number(p.risk,'risk',0,1e12), allowed:p.allowed,
      diagnostic_hypothesis:hypothesis('diagnostic_hypothesis'), effect_hypothesis:hypothesis('effect_hypothesis'),
      sensitivity:number(p.sensitivity,'sensitivity',0,1), false_positive:number(p.false_positive,'false_positive',0,1)};
  }
  let pending: Ranked | null = null;
  if (r.pending !== null) {
    const p = object(r.pending);
    pending = {task:parseTask(p.task), key:identifier(p.key,'key'), probability:number(p.probability,'probability',0,1),
      information_gain:number(p.information_gain,'information_gain',0,1), expected_benefit:number(p.expected_benefit,'expected_benefit'),
      score:number(p.score,'score',-Infinity,Infinity)};
  }
  return {goal:text(r.goal,'goal'), budget:number(r.budget,'budget',0,1e12), information_weight:number(r.information_weight,'information_weight',0,1e12),
    max_risk:number(r.max_risk,'max_risk',0,1e12), min_score:number(r.min_score,'min_score',0,1e12), facts,hypotheses,profiles,
    completed_keys:identifiers(r.completed_keys,'completed_keys'), completed_ids:identifiers(r.completed_ids,'completed_ids'),
    successful_ids:identifiers(r.successful_ids,'successful_ids'), seen_evidence:identifiers(r.seen_evidence,'seen_evidence'),
    seen_events:identifiers(r.seen_events,'seen_events'), pending};
}
export function rank(rawState: unknown, rawTasks: unknown): Decision {
  const state = parseState(rawState);
  if (state.pending !== null) throw new Error('Observe or resolve pending task before another plan');
  if (!Array.isArray(rawTasks) || rawTasks.length > 8) throw new Error('Expected at most eight tasks');
  const tasks = rawTasks.map(parseTask);
  identifiers(tasks.map(t=>t.id),'task IDs');
  const knownFacts = new Set(state.facts.map(f=>f.id));
  const completed = new Set(state.completed_ids);
  const successful = new Set(state.successful_ids);
  const candidates = new Map(tasks.map(t=>[t.id,t]));
  const visiting = new Set<string>(), visited = new Set<string>();
  for (const t of tasks) {
    if (!t.facts.length || !t.facts.every(f=>knownFacts.has(f))) throw new Error(`${t.id}: missing or unknown facts`);
    if (!Object.hasOwn(state.profiles,t.profile)) throw new Error(`${t.id}: unknown profile`);
    if (t.depends_on.includes(t.id) || !t.depends_on.every(d=>completed.has(d)||candidates.has(d))) throw new Error('Invalid dependencies');
  }
  function visit(id: string): void {
    if (visiting.has(id)) throw new Error('Cyclic dependencies');
    if (visited.has(id) || !candidates.has(id)) return;
    visiting.add(id);
    for (const d of candidates.get(id)!.depends_on) visit(d);
    visiting.delete(id); visited.add(id);
  }
  for (const t of tasks) visit(t.id);
  const valid: Ranked[] = [], rejected: {id:string;reason:string}[] = [];
  const keys = new Set<string>();
  for (const task of tasks) {
    const profile = state.profiles[task.profile], key = taskKey(task,state.goal);
    let reason: string | null = null;
    if (completed.has(task.id) || state.completed_keys.includes(key) || keys.has(key)) reason='duplicate';
    else if (!task.depends_on.every(d=>successful.has(d))) reason='blocked';
    else if (!profile.allowed || profile.risk>state.max_risk) reason='policy';
    else if (profile.cost>state.budget) reason='budget';
    if (reason) {rejected.push({id:task.id,reason});continue;}
    keys.add(key);
    const p = profile.alpha/(profile.alpha+profile.beta);
    const h = profile.diagnostic_hypothesis;
    const ig = h === null ? 0 : informationGain(state.hypotheses[h],profile.sensitivity,profile.false_positive);
    const effect = profile.effect_hypothesis;
    const gain = profile.benefit*(effect === null ? 1 : state.hypotheses[effect]);
    const score = p*(gain+state.information_weight*ig)-profile.cost-profile.risk;
    valid.push({task,key,probability:p,information_gain:ig,expected_benefit:p*gain,score});
  }
  valid.sort((a,b)=>b.score-a.score || (a.task.id<b.task.id?-1:a.task.id>b.task.id?1:0));
  const selected = valid.length && valid[0].score>state.min_score ? valid[0] : null;
  return {selected,ranking:valid,rejected,status:selected?'selected':'stop_or_request_evidence'};
}
export function acceptPlan(state: State, decision: Decision): State {
  const updated = structuredClone(state); updated.pending=structuredClone(decision.selected); return updated;
}
export function observe(rawState: unknown, rawEvent: unknown, evidence: Uint8Array): State {
  const state = parseState(rawState), event = object(rawEvent);
  exactKeys(event,['event_id','task_id','success','positive','summary']);
  const eventId=identifier(event.event_id,'event_id'), summary=text(event.summary,'summary');
  if (typeof event.success !== 'boolean') throw new Error('success: expected verified boolean result');
  if (!evidence.length || evidence.length>1000000) throw new Error('Evidence must contain 1..1000000 bytes');
  const digest=createHash('sha256').update(evidence).digest('hex');
  if (state.seen_events.includes(eventId)||state.seen_evidence.includes(digest)) throw new Error('Reused evidence/event');
  const pending=state.pending;
  if (!pending||event.task_id!==pending.task.id) throw new Error('No matching pending task');
  const updated=structuredClone(state), profile=updated.profiles[pending.task.profile];
  const h=profile.diagnostic_hypothesis;
  if (h!==null && event.success) {
    if (typeof event.positive!=='boolean') throw new Error('positive: expected boolean');
    updated.hypotheses[h]=posterior(updated.hypotheses[h],profile.sensitivity,profile.false_positive,event.positive);
  } else if (event.positive!==null) throw new Error('Failed/non-diagnostic task needs positive=null');
  profile[event.success?'alpha':'beta']+=1;
  updated.budget=Math.max(0,updated.budget-profile.cost);
  updated.completed_keys.push(pending.key); updated.completed_ids.push(pending.task.id);
  if (event.success) updated.successful_ids.push(pending.task.id);
  updated.seen_events.push(eventId); updated.seen_evidence.push(digest);
  const factId='observation:'+eventId;
  if (updated.facts.some(f=>f.id===factId)) throw new Error('Duplicate observation fact ID');
  updated.facts.push({id:factId,text:summary,status:'reported',source:'evidence/'+digest+'.bin'});
  updated.pending=null; return updated;
}
