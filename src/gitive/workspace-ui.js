const wsMessage=document.querySelector('#workspace-message');
async function workspaceAction(operation,args={}){
 try{
  const response=await fetch('/api/workspace',{method:'POST',headers:{'Content-Type':'application/json','X-Loop-Token':token},body:JSON.stringify({operation,...args})});
  const result=await response.json();if(!response.ok)throw new Error(result.error);
  wsMessage.textContent='Uruchomiono '+operation+'. Wynik pojawi się poniżej.';await workspaceRefresh();
 }catch(error){wsMessage.textContent=error.message}
}
function wsSelect(id,rows,label){const element=document.getElementById(id),old=element.value;element.replaceChildren(new Option('Wybierz…',''));for(const row of rows)element.add(new Option(label(row),row.id));if(rows.some(r=>r.id===old))element.value=old}
async function workspaceRefresh(){
 try{
  const [inventory,state]=await Promise.all(['/api/workspace','/api/workspace/state'].map(async url=>{const r=await fetch(url);if(!r.ok)throw new Error('Błąd odczytu workspace');return r.json()}));
  wsSelect('ws-snapshot-id',inventory.snapshots,r=>r.id);for(const id of ['ws-clone-id','ws-resume-id'])wsSelect(id,inventory.clones,r=>r.target+' · '+r.id.slice(0,8));
  wsSelect('ws-profile-id',inventory.profiles,r=>r.browser+' · '+r.id.slice(0,8));
  document.querySelector('#workspace-state').textContent=JSON.stringify(state,null,2);
  document.querySelector('#workspace-inventory').textContent=JSON.stringify(inventory,null,2);
 }catch(error){wsMessage.textContent=error.message}
}
function wsSnapshot(event){event.preventDefault();workspaceAction('snapshot',{name:document.querySelector('#ws-name').value,project:document.querySelector('#ws-project').value,include_sessions:document.querySelector('#ws-sessions').checked,browser:document.querySelector('#ws-pc-browser').value})}
function wsClone(event){event.preventDefault();workspaceAction('clone',{snapshot:document.querySelector('#ws-snapshot-id').value,target:document.querySelector('#ws-target').value})}
function wsSync(event){event.preventDefault();workspaceAction('resync',{clone:document.querySelector('#ws-clone-id').value,dry_run:!document.querySelector('#ws-apply').checked,include_sessions:document.querySelector('#ws-sync-sessions').checked})}
function wsResume(event){event.preventDefault();workspaceAction('resume',{clone:document.querySelector('#ws-resume-id').value,application:document.querySelector('#ws-application').value})}
function wsProfile(event){event.preventDefault();const action=document.querySelector('#ws-profile-action').value;workspaceAction('profile',{action,browser:document.querySelector('#ws-browser').value,snapshot:action==='restore'?document.querySelector('#ws-profile-id').value:null})}
workspaceRefresh();setInterval(workspaceRefresh,5000);

async function overviewRefresh(){
 const summary=document.getElementById('overview-summary'),nav=document.getElementById('overview-actions');
 try{
  const response=await fetch('/api/overview');if(!response.ok)throw new Error('HTTP '+response.status);
  const value=await response.json();summary.textContent=value.lines.join('\n');nav.replaceChildren();
  for(const action of value.actions){
   const row=document.createElement('p'),link=document.createElement('a');link.textContent=action.label;link.href='#'+action.anchor;
   link.onclick=event=>{event.preventDefault();if(action.anchor==='overview'){overviewRefresh();return}const target=document.getElementById(action.anchor);if(target){if(target.closest('details'))target.closest('details').open=true;target.scrollIntoView({behavior:'smooth'});target.querySelector('input,select')?.focus()}};
   row.append(link);nav.append(row);
  }
 }catch(error){summary.textContent='Stan niedostępny: '+error.message;nav.replaceChildren()}
}
overviewRefresh();setInterval(overviewRefresh,5000);
