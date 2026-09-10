/** CAS-based Git store. Dedicated, trusted bare repository; no shell execution. */
import {spawnSync} from 'node:child_process';
import {existsSync,mkdirSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir,devNull} from 'node:os';
import {join} from 'node:path';
import {parseState} from './engine.ts';
import type {State} from './engine.ts';
export const REF='refs/heads/memory';
export function git(repo:string,args:string[],data?:Uint8Array,extraEnv:Record<string,string>={}):Buffer {
  const env: Record<string,string|undefined>={...process.env};
  for (const k of Object.keys(env)) if(k.startsWith('GIT_')) delete env[k];
  Object.assign(env,{GIT_AUTHOR_NAME:'Intuition planner',GIT_AUTHOR_EMAIL:'planner@example.invalid',
    GIT_COMMITTER_NAME:'Intuition planner',GIT_COMMITTER_EMAIL:'planner@example.invalid',
    GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:devNull},extraEnv);
  const r=spawnSync('git',['-C',repo,'-c','commit.gpgSign=false',...args],{input:data,env,timeout:20000,maxBuffer:8000000,shell:false});
  if(r.error) throw r.error;
  if(r.status!==0) throw new Error(r.stderr?.toString()||'Git failed');
  return r.stdout;
}
export function read(repo:string):{base:string;state:State} {
  const base=git(repo,['rev-parse','--verify',REF]).toString().trim();
  return {base,state:parseState(JSON.parse(git(repo,['show',base+':state.json']).toString()))};
}
export function commit(repo:string,base:string|null,state:State,record:unknown,extra:Record<string,Uint8Array>={}):string {
  if(base!==null&&!/^([0-9a-f]{40}|[0-9a-f]{64})$/.test(base)) throw new Error('Invalid base commit');
  const files:Record<string,Uint8Array>={
    'state.json':Buffer.from(JSON.stringify(state,null,2)+'\n'),
    'last-event.json':Buffer.from(JSON.stringify(record,null,2)+'\n'),...extra};
  const tmp=mkdtempSync(join(tmpdir(),'intuition-index-'));
  try {
    const env={GIT_INDEX_FILE:join(tmp,'index')};
    git(repo,['read-tree',base??'--empty'],undefined,env);
    for(const [path,content] of Object.entries(files)) {
      if(!['state.json','last-event.json'].includes(path)&&!/^evidence\/[0-9a-f]{64}\.bin$/.test(path)) throw new Error('Unapproved Git path');
      const blob=git(repo,['hash-object','-w','--stdin'],content).toString().trim();
      git(repo,['update-index','--add','--cacheinfo','100644',blob,path],undefined,env);
    }
    const tree=git(repo,['write-tree'],undefined,env).toString().trim();
    const next=git(repo,['commit-tree',tree,...(base?['-p',base]:[])],Buffer.from('Record planner event\n')).toString().trim();
    git(repo,['update-ref',REF,next,base??'0'.repeat(next.length)]);
    return next;
  } finally {rmSync(tmp,{recursive:true,force:true});}
}
export function initialize(repo:string,state:State):string {
  if(existsSync(repo)) throw new Error('Init requires a new path; existing repositories are not overwritten');
  mkdirSync(repo,{recursive:true});git(repo,['init','--bare','--quiet']);
  return commit(repo,null,state,{kind:'init'});
}
