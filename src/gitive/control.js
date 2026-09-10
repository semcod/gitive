'use strict';
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {
  open: 'Otwarte', in_progress: 'W realizacji', review: 'Do przeglądu', done: 'Zakończone',
  blocked: 'Blokada', canceled: 'Anulowane', failed: 'Błąd', passed: 'Testy OK',
  running: 'Działa', queued: 'W kolejce', complete: 'Zakończono', interrupted: 'Przerwano',
  unknown: 'Niepotwierdzony', unavailable: 'Niedostępny', exited: 'Zatrzymany', pending: 'Brak testów'
};
const tone = s => ['done','passed','running','complete'].includes(s) ? 'good' : ['failed','blocked','unavailable','interrupted'].includes(s) ? 'bad' : ['review','queued','unknown','pending'].includes(s) ? 'warn' : '';
const badge = (s, label) => `<span class="badge ${tone(s)}">${esc(label || labels[s] || s)}</span>`;
const date = v => v ? new Date(typeof v === 'number' ? v * 1000 : v).toLocaleString('pl-PL', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '—';
const relTime = v => {
  if (!v) return '—';
  const diff = (Date.now() - new Date(v).getTime()) / 1000;
  if (diff < 60) return 'przed chwilą';
  if (diff < 3600) return Math.floor(diff / 60) + ' min temu';
  if (diff < 86400) return Math.floor(diff / 3600) + ' godz. temu';
  return Math.floor(diff / 86400) + ' dni temu';
};

const actionLabels = {'runtime-test':'Testy we własnym runtime', 'runtime-terminal':'Terminal w noVNC', 'sync-ticket':'Synchronizacja z GitHub'};
const views = {
  overview: ['Przegląd', 'Dobrze wiedzieć, co dalej.', 'Projekty, zadania i środowiska w jednym miejscu.'],
  tasks: ['Centrum Zadań & Stream', 'Strumień zadań z GitHub, GitLab i projektów lokalnych.', 'Wybierz dowolne zgłoszenie z repozytorium i uruchom realizację 1 kliknięciem.'],
  tickets: ['Tablica Kanban', 'Od pomysłu do wyniku.', 'Lokalne zadania Planfile, rozdzielone według projektu.'],
  runner: ['Konsola Live', 'Monitor wykonania w czasie rzeczywistym.', 'Obserwuj etapy generowania poprawki, logi testów oraz wyniki wykonawcy na żywo.'],
  projects: ['Projekty', 'Twoje projekty.', 'Każdy ma własny kod, Planfile i środowisko wykonania.'],
  workspaces: ['Środowiska', 'Własne miejsce do pracy.', 'Kopie środowisk PC z zachowaną ścieżką i użytkownikiem.'],
  desktop: ['Pulpit noVNC', 'Zobacz, co się dzieje.', 'Otwieraj terminale projektów w wspólnym pulpicie GUI.'],
  benchmark: ['Benchmark', 'Wybór oparty na wynikach.', 'GLM53, GPT6 i Opus5 oceniane na tych samych przykładach.']
};
const icons = {
  overview: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  tasks: 'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
  tickets: 'M5 3h14v18H5z M8 8h8 M8 12h8 M8 16h5',
  runner: 'M4 17l6-6-6-6 M12 19h8',
  projects: 'M3 6h7l2 3h9v11H3z M3 6V4h6l2 2',
  workspaces: 'M3 4h18v12H3z M8 21h8 M12 16v5',
  desktop: 'M3 4h18v13H3z M6 8l3 3-3 3 M12 14h4 M7 21h10',
  benchmark: 'M4 20V10h4v10 M10 20V4h4v16 M16 20v-7h4v7'
};

let data = null, view = 'overview', project = '', query = '', filter = '', inflight = false, lastRender = '', selected = null, toastTimer;
let streamSource = 'all', streamRepo = 'semcod/code2logic', streamTickets = [], streamLoading = false, streamSelected = null;
let runnerData = { lines: [], events: [], state: {} }, runnerTimer = null;

try { project = localStorage.getItem('gitive-project') || ''; } catch {}
$('#navigation').innerHTML = Object.entries(views).map(([k,v]) => `<button data-view="${k}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${icons[k]}"/></svg>${v[0]}</button>`).join('');

function toast(text) {
  $('#toast').textContent = text;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('#toast').hidden = true, 6000);
}
function empty(title, body = '') {
  return `<div class="empty">${esc(title)}${body ? `<p>${esc(body)}</p>` : ''}</div>`;
}

function visibleProjects() {
  return data.projects.filter(p => (!project || p.name === project) && (!query || [p.name, p.goal, p.title].join(' ').toLowerCase().includes(query) || data.tickets.some(t => t.project === p.name && [t.id, t.title, t.description].join(' ').toLowerCase().includes(query))));
}
function visibleTickets() {
  return data.tickets.filter(t => (!project || t.project === project) && (!query || [t.title, t.description, t.id, t.project].join(' ').toLowerCase().includes(query)) && (!filter || (filter === 'active' ? !['done','canceled'].includes(t.status) : filter === 'done' ? ['done','canceled'].includes(t.status) : t.status === 'blocked')));
}
function busy(p) { return p.active_jobs.length > 0; }
function runtimeReason(p) {
  return !data.host_online ? 'Proces hosta offline: gitive host start' : !p.workspace ? 'Przygotuj środowisko: gitive twin prepare ' + p.name : p.workspace.status !== 'running' ? 'Kontener nie działa lub jego stan nie jest potwierdzony' : busy(p) ? 'Poczekaj na operację tego projektu' : ['running','stopping'].includes(data.loop.status) ? 'Najpierw zatrzymaj pętlę Gitive' : '';
}
function runtimeButton(p, action, label) {
  const why = runtimeReason(p);
  return `<button data-action="${action}" data-project="${esc(p.name)}" ${why ? 'disabled' : ''} title="${esc(why || label)}">${label}</button>`;
}

function card(p, i) {
  const w = p.workspace;
  const test = w?.tests?.status || 'pending';
  return `<article class="project-card">
    <div class="card-top">
      <div class="monogram ${['','blue','purple'][i%3]}">${esc(p.title.slice(0,2).toUpperCase())}</div>
      ${p.demo ? '<span class="badge blue">DEMO · lokalne</span>' : badge(w?.status || 'unknown', w ? null : 'Bez runtime')}
    </div>
    <h3><button data-project-open="${esc(p.name)}">${esc(p.title)}</button></h3>
    <p class="description">${esc(p.goal)}</p>
    <div class="card-meta">
      <span>◉ ${p.open} otwartych / ${p.tickets} ticketów</span>
      <span>·</span>
      <span>${w ? 'Python ' + esc(w.python) : 'Kod w prywatnej kopii'}</span>
    </div>
    <div class="card-bottom">
      ${badge(test)}
      <button data-project-open="${esc(p.name)}">Otwórz projekt →</button>
    </div>
    ${p.error ? `<p class="form-error">${esc(p.error)}</p>` : ''}
  </article>`;
}

function activity() {
  const rows = data.jobs.filter(j => !project || j.project === project).slice(0, 8);
  return rows.length ? `<div class="activity">${rows.map(j => `<div class="activity-row">
    <div>
      <div class="activity-title">${esc(actionLabels[j.action] || j.action)}</div>
      <small>${esc(j.project)}${j.result?.exit_code !== undefined ? ' · exit ' + esc(j.result.exit_code) : ''}${j.error ? ' · ' + esc(j.error) : ''}</small>
    </div>
    <div class="activity-right">${badge(j.status)}<time>${date(j.finished || j.started || j.created)}</time></div>
  </div>`).join('')}</div>` : empty('Jeszcze bez operacji', 'Uruchom testy projektu — tutaj zobaczysz kolejkę i rzeczywisty wynik.');
}

function overview() {
  const ps = visibleProjects(), ts = visibleTickets();
  const active = data.jobs.filter(j => (!project || j.project === project) && ['queued','running'].includes(j.status));
  const failed = ps.filter(p => p.workspace?.tests?.status === 'failed');
  const isLoopRunning = ['running','stopping'].includes(data.loop?.status);

  return `
  ${isLoopRunning ? `<div class="notice" style="border-left: 4px solid #7c3aed; background: rgba(124,58,237,0.08);">
    <span class="symbol" style="color:#7c3aed;">⚡</span>
    <p><strong>Aktywne zadanie w pętli Gitive:</strong> projekt <em>${esc(data.loop.project)}</em>, ticket <em>${esc(data.loop.ticket_id)}</em> (${esc(data.loop.phase || 'analiza')}).
    <br><button class="btn-realize" style="margin-top:8px;" data-view="runner">Otwórz Konsolę Live →</button></p>
  </div>` : ''}
  <div class="stats">${[
    [ps.length, 'Projekty', 'Oddzielne repozytoria i tickety'],
    [ps.filter(p => p.workspace?.status === 'running').length, 'Aktywne środowiska', data.host_online ? 'Stan odczytany z Dockera' : 'Proces hosta offline'],
    [ts.filter(t => !['done','canceled'].includes(t.status)).length, 'Otwarte tickety', ts.filter(t => t.status === 'blocked').length + ' z blokadą'],
    [active.length, 'Operacje w toku', failed.length + ' projektów z błędami testów']
  ].map(([n,t,d]) => `<div class="stat"><div class="stat-label">${t}<span>↗</span></div><div class="stat-value">${n}</div><small>${esc(d)}</small></div>`).join('')}</div>
  <div class="notice ${failed.length ? 'warning' : ''}">
    <span class="symbol">${failed.length ? '◷' : '↗'}</span>
    <p><strong>${failed.length ? 'Następny krok: sprawdź nieudane testy.' : 'Szybka realizacja zadań z GitHub i źródeł lokalnych.'}</strong><br>
    Przejdź do <button class="link" data-view="tasks" style="font-weight:bold;text-decoration:underline;">Centrum Zadań & Stream</button>, aby wybrać ticket ze zdalnego lub lokalnego projektu i uruchomić go jednym kliknięciem.</p>
  </div>
  <div class="section-title"><h2>Projekty pod ręką</h2><small>${ps.length} widocznych</small></div>
  <div class="project-grid">${ps.map(card).join('') || empty('Brak projektów dla tego filtra')}</div>
  <div class="section-title"><h2>Ostatnia aktywność</h2><small>Kolejka hosta · daty lokalne</small></div>
  ${activity()}`;
}

async function fetchStreamTickets() {
  streamLoading = true;
  try {
    const params = new URLSearchParams({ source: streamSource, repo: streamRepo, q: query });
    const res = await fetch('/api/integrations/tickets?' + params);
    if (res.ok) {
      const items = await res.json();
      streamTickets = (Array.isArray(items) ? items : []).filter(t => t && t.status === "open");
    }
  } catch (e) {
    console.error('Błąd pobierania zadań:', e);
  } finally {
    streamLoading = false;
    if (view === 'tasks') render(true);
  }
}

function renderTasks() {
  const popularRepos = ['semcod/code2logic', 'semcod/gitive', 'subactor/doctor-agent'];
  return `
  <div class="stream-toolbar">
    <div class="stream-source-tabs">
      <button class="${streamSource==='all'?'active':''}" data-stream-source="all">Wszystkie źródła</button>
      <button class="${streamSource==='github'?'active':''}" data-stream-source="github">GitHub</button>
      <button class="${streamSource==='gitlab'?'active':''}" data-stream-source="gitlab">GitLab</button>
      <button class="${streamSource==='local'?'active':''}" data-stream-source="local">Lokalne (otwarte)</button>
    </div>
    <div class="stream-repo-picker">
      <label style="font-size:12px;color:var(--muted);font-weight:600;">Repozytorium:</label>
      <select id="streamRepoSelect">
        ${popularRepos.map(r => `<option value="${esc(r)}" ${r===streamRepo?'selected':''}>${esc(r)}</option>`).join('')}
        <option value="custom">Inne repozytorium…</option>
      </select>
      <input id="streamCustomRepo" placeholder="owner/repo" value="${esc(streamRepo)}" style="display:${popularRepos.includes(streamRepo)?'none':'inline-block'};width:180px;">
      <button class="quiet" id="btnStreamRefresh">↻ Pobierz na żywo</button>
    </div>
  </div>

  ${streamLoading ? `<div class="empty"><div class="pulse-dot"></div> Ładowanie i strumieniowanie ticketów z ${esc(streamSource)}…</div>` : ''}

  ${!streamLoading && streamTickets.length === 0 ? empty('Brak otwartych zadań w wybranym źródle', 'Wszystkie zadania w wybranym źródle są już zrealizowane lub w trakcie prac.') : ''}

  <div class="stream-grid">
    ${streamTickets.map(t => {
      const isGh = t.source === 'github', isGl = t.source === 'gitlab';
      const sourceClass = isGh ? 'github' : isGl ? 'gitlab' : t.labels?.includes('worktree') ? 'worktree' : 'local';
      const sourceLabel = isGh ? `GitHub #${t.number}` : isGl ? `GitLab #${t.number}` : t.labels?.includes('worktree') ? 'Worktree' : 'Lokalny';
      return `
      <article class="stream-card">
        <div>
          <div class="stream-card-top">
            <span class="source-tag ${sourceClass}">${esc(sourceLabel)}</span>
            <small style="color:var(--muted);">${relTime(t.updated_at || t.created_at)}</small>
          </div>
          <h4 style="margin:10px 0 6px;">
            ${t.url ? `<a href="${esc(safeUrl(t.url))}" target="_blank" rel="noopener">${esc(t.title)} ↗</a>` : esc(t.title)}
          </h4>
          <p class="stream-card-desc">${esc(t.description || 'Brak dodatkowego opisu.')}</p>
        </div>
        <div class="stream-card-tags">
          <span style="font-size:11px;color:var(--muted);">${esc(t.repository || t.project)}</span>
          ${(t.labels || []).slice(0, 3).map(l => `<span class="badge" style="font-size:10px;">${esc(l)}</span>`).join('')}
        </div>
        <div class="stream-card-foot">
          <button class="btn-realize" data-realize-id="${esc(t.id)}" title="Automatycznie powiąż i uruchom wykonawcę">
            ⚡ Realizuj zadanie
          </button>
          <button class="quiet" data-stream-detail="${esc(t.id)}">Szczegóły</button>
        </div>
      </article>`;
    }).join('')}
  </div>`;
}

function openStreamModal(t) {
  streamSelected = t;
  const projects = data?.projects || [];
  $('#streamEyebrow').textContent = `ŹRÓDŁO · ${t.source.toUpperCase()}`;
  $('#streamModalBody').innerHTML = `
    <h2>${esc(t.title)}</h2>
    <p class="muted">Repozytorium: <strong>${esc(t.repository || t.project)}</strong> ${t.number ? `· #${esc(t.number)}` : ''}</p>
    <div class="detail-meta">
      <span class="source-tag ${t.source}">${esc(t.source.toUpperCase())}</span>
      <span class="badge ${tone(t.status)}">${esc(labels[t.status] || t.status)}</span>
      ${t.url ? `<a class="link" href="${esc(safeUrl(t.url))}" target="_blank" rel="noopener">Otwórz na ${t.source} ↗</a>` : ''}
    </div>
    <div class="ticket-description" style="max-height:220px;overflow-y:auto;white-space:pre-wrap;">${esc(t.description || 'Brak opisu.')}</div>
    
    <div class="detail-section" style="margin-top:16px;">
      <h3>Parametry realizacji w Gitive</h3>
      <div class="form-grid">
        <label>Projekt docelowy w Gitive:
          <select id="streamTargetProject">
            ${projects.map(p => `<option value="${esc(p.name)}" ${(t.repository||'').includes(p.name)?'selected':''}>${esc(p.title)} (${esc(p.name)})</option>`).join('')}
          </select>
        </label>
        <label>Wykonawca:
          <select id="streamEngine">
            <option value="auto">Najlepszy z benchmarku (Auto)</option>
            <option value="glm53">GLM53</option>
            <option value="gpt6">GPT6</option>
            <option value="opus5">Opus5</option>
          </select>
        </label>
      </div>
      <div class="dialog-actions" style="margin-top:14px;">
        <button class="btn-realize" id="btnConfirmRealize">⚡ Uruchom realizację teraz</button>
        <button class="quiet" id="btnConfirmImport">Zapisz w Planfile (bez startu)</button>
      </div>
    </div>
  `;
  $('#streamModal').showModal();
}

async function realizeStreamTicket(item, runNow = true, engine = 'auto', targetProj = null) {
  try {
    const proj = targetProj || item.project || (data.projects.find(p => item.repository && item.repository.includes(p.name)) || data.projects[0])?.name;
    const body = {
      project: proj,
      repository: item.repository || proj,
      number: item.number,
      title: item.title,
      description: item.description,
      url: item.url,
      engine: engine,
      action: runNow ? 'realize-remote-ticket' : 'import-remote-ticket'
    };
    const res = await fetch('/api/control/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Loop-Token': token },
      body: JSON.stringify(body)
    });
    const val = await res.json();
    if (!res.ok) throw new Error(val.error || 'Operacja nie powiodła się');
    toast(runNow ? `Uruchomiono realizację zadania w ${proj}!` : `Zapisano ticket w ${proj}`);
    if ($('#streamModal').open) $('#streamModal').close();
    await refresh();
    if (runNow) go('runner');
  } catch (err) {
    toast('Błąd: ' + err.message);
  }
}

async function fetchRunnerProgress() {
  try {
    const r = await fetch('/api/progress');
    if (r.ok) {
      runnerData = await r.json();
      if (view === 'runner') renderRunnerLogs();
    }
  } catch {}
}

function renderRunnerLogs() {
  const win = $('#runnerTerminalWindow');
  if (!win) return;
  const lines = runnerData.lines || [];
  if (!lines.length) {
    win.innerHTML = '<div class="log-line dim">Oczekiwanie na pierwsze zdarzenia wykonawcy…</div>';
    return;
  }
  win.innerHTML = lines.map(line => {
    let cls = '';
    if (line.startsWith('GITIVE_RESULT') || line.includes('OK') || line.includes('passed')) cls = 'ok';
    else if (line.includes('FAILED') || line.includes('Error') || line.includes('error')) cls = 'err';
    else if (line.startsWith('START') || line.startsWith('stage:')) cls = 'stage';
    else if (line.startsWith('ITERATION')) cls = 'warn';
    return `<div class="log-line ${cls}">${esc(line)}</div>`;
  }).join('');
  win.scrollTop = win.scrollHeight;
}

function renderRunner() {
  const loop = data?.loop || {};
  const isRunning = loop.status === 'running';
  const phases = ['preparing', 'tests', 'log-reading', 'repair', 'validation', 'coding', 're-tests', 'finished'];
  const phaseLabels = {
    preparing: 'Przygotowanie',
    tests: 'Testy bazowe',
    'log-reading': 'Analiza',
    repair: 'Generowanie poprawki',
    validation: 'Walidacja kodu',
    coding: 'Aplikowanie zmian',
    're-tests': 'Weryfikacja testów',
    finished: 'Zakończono'
  };
  const curPhase = loop.phase || (isRunning ? 'preparing' : 'finished');
  const curIdx = phases.indexOf(curPhase);

  return `
  <div class="runner-box">
    <div class="runner-header">
      <div>
        <span class="eyebrow">AKTYWNY CYKL GITIVE</span>
        <h2 style="margin:6px 0;">Projekt: ${esc(loop.project || 'Brak')} · Ticket: ${esc(loop.ticket_id || 'Brak')}</h2>
        <p class="muted">Status silnika: <strong>${esc(labels[loop.status] || loop.status || 'Bezczynny')}</strong> · Iteracja: ${loop.cycle || 1}</p>
      </div>
      <div>
        ${isRunning ? `<button class="quiet" id="btnStopLoop" style="color:var(--red);border-color:var(--red);">■ Zatrzymaj pętlę</button>` : `<button class="primary" data-view="tasks">Wybierz nowe zadanie →</button>`}
      </div>
    </div>

    <div class="runner-stepper">
      ${phases.map((ph, idx) => {
        const cls = idx === curIdx ? 'active' : idx < curIdx ? 'done' : '';
        return `
        <div class="runner-step ${cls}">
          <span class="runner-dot"></span>
          <span>${esc(phaseLabels[ph] || ph)}</span>
          ${idx < phases.length - 1 ? '<span style="color:var(--line);margin-left:4px;">→</span>' : ''}
        </div>`;
      }).join('')}
    </div>

    <div class="terminal-toolbar">
      <span>Konsola wykonawcy (Gitive Live Stream)</span>
      <span>${isRunning ? '<span class="pulse-dot"></span> Rejestrowanie na żywo' : 'Zakończone / Oczekiwanie'}</span>
    </div>
    <div class="terminal-window" id="runnerTerminalWindow">
      <div class="log-line dim">Ładowanie logów…</div>
    </div>
  </div>`;
}

function projectView() {
  const ps = visibleProjects();
  const p = project && data.projects.find(p => p.name === project);
  return (p ? `
    <div class="notice">
      <span class="symbol">⌘</span>
      <p><strong>${esc(p.title)}</strong><br>${esc(p.workspace?.path || p.source)}<br>${p.workspace ? 'Użytkownik: ' + esc(p.workspace.user) + ' · Python ' + esc(p.workspace.python) : 'Prywatna kopia kodu; runtime wymaga przygotowania.'}</p>
    </div>
    <div class="inline-actions">
      <button class="primary" data-view="tickets">Tablica ticketów</button>
      ${runtimeButton(p, 'runtime-test', '▷ Uruchom testy')}
      ${runtimeButton(p, 'runtime-terminal', '▣ Terminal noVNC')}
      <button data-view="workspaces">Środowisko</button>
    </div>
    ${runtimeReason(p) ? `<p class="muted">${esc(runtimeReason(p))}</p>` : ''}
    <div class="section-title"><h2>Wyniki i operacje</h2></div>
    ${activity()}
    <div class="section-title"><h2>Informacje o projekcie</h2></div>` : '') + `
  <div class="project-grid">${ps.map(card).join('') || empty('Nie znaleziono projektu')}</div>
  <div class="section-title"><h2>Dodaj kolejny projekt</h2></div>
  <div class="notice"><p>Import wybranego folderu PC i ustawienia środowiska są dostępne w kreatorze CLI: <strong>./gitive project new</strong>. <a class="link" href="/tools">Otwórz formularze importu w WWW ↗</a></p></div>`;
}

function board() {
  const groups = [
    ['Do zrobienia', ['open']],
    ['W realizacji / blokada', ['in_progress', 'blocked', 'failed']],
    ['Do przeglądu', ['review']],
    ['Zakończone', ['done', 'canceled']]
  ];
  const ts = visibleTickets();
  return `
  <p class="muted">${ts.length} ticketów w Planfile projektu. Kliknij kartę, aby otworzyć szczegóły i synchronizację.</p>
  <div class="board">${groups.map(([title, states]) => {
    const rows = ts.filter(t => states.includes(t.status));
    return `<section class="column">
      <div class="column-head">${title}<span>${rows.length}</span></div>
      ${rows.map(t => `
        <button class="ticket-card" data-ticket="${esc(t.id)}" data-project="${esc(t.project)}">
          <div class="ticket-project">${esc(t.project)} / ${esc(t.id)}</div>
          <span class="ticket-title">${esc(t.title)}</span>
          ${t.parent ? `<span class="relation">↳ ${esc(t.parent)}</span>` : ''}
          <span class="ticket-foot">
            <span>${esc(t.engine.toUpperCase())} ${['blocked','failed'].includes(t.status) ? '· ' + esc(labels[t.status]) : ''}</span>
            <span>${t.github.url ? 'GitHub ↗' : 'Lokalny'}</span>
          </span>
        </button>`).join('') || '<p class="muted">Brak zadań</p>'}
    </section>`;
  }).join('')}</div>`;
}

function workspaces() {
  return `
  <div class="notice"><span class="symbol">▣</span><p><strong>Wspólny pulpit, niezależne środowiska projektów.</strong><br>Kontenery używają prywatnych kopii plików i runtime. Użytkownik oraz ścieżka projektu odpowiadają PC; testy mają własne wyniki.</p></div>
  <div class="workspace-grid">${visibleProjects().map(p => {
    const w = p.workspace;
    return `
    <article class="workspace-card">
      <div class="card-top">
        <h3>${esc(p.title)}</h3>
        ${badge(w?.status || 'unknown', w ? null : 'Bez runtime')}
      </div>
      ${w ? `<dl class="runtime-details">
        <dt>Użytkownik</dt><dd>${esc(w.user)}</dd>
        <dt>Ścieżka</dt><dd>${esc(w.path)}</dd>
        <dt>Python</dt><dd>${esc(w.python)}</dd>
        <dt>Node.js</dt><dd>${esc(w.node || 'Nie wybrano')}</dd>
        <dt>Testy</dt><dd>${badge(w.tests?.status || 'pending')} ${date(w.tests?.created)}</dd>
        <dt>Utworzono</dt><dd>${date(w.created)}</dd>
      </dl>` : `<p class="muted">Przygotuj runtime przez gitive twin prepare ${esc(p.name)}.</p>`}
      <div class="inline-actions">
        ${runtimeButton(p, 'runtime-test', '▷ Testy')}
        ${runtimeButton(p, 'runtime-terminal', '▣ Terminal')}
        <button data-project-open="${esc(p.name)}">Projekt →</button>
      </div>
      ${runtimeReason(p) ? `<p class="muted">${esc(runtimeReason(p))}</p>` : ''}
    </article>`;
  }).join('') || empty('Brak środowisk dla tego filtra')}</div>
  <div class="section-title"><h2>Operacje środowisk</h2></div>
  ${activity()}`;
}

function benchmark() {
  const r = data.ranking;
  return `
  <div class="notice">
    <p><strong>${r ? 'Wybrany wykonawca: ' + esc(r.solution.toUpperCase()) : 'Brak aktualnego, kompletnego rankingu.'}</strong><br>
    Automatyczny wybór wymaga pełnego benchmarku: 3 rozwiązania × 3 projekty × 3 iteracje, z porównywalnymi wejściami.</p>
  </div>
  ${r ? `<div class="activity"><div class="activity-row"><div><div class="activity-title">Zapisany raport</div><small>${esc(r.report)}</small></div>${badge('complete','Zweryfikowany ranking')}</div></div>` : ''}
  <div class="section-title"><h2>Kolejne kroki</h2></div>
  <p class="muted">Podgląd konfiguracji, budżetów i uruchomienie benchmarku znajdziesz w narzędziach zaawansowanych.</p>
  <a class="link" href="/tools">Otwórz benchmark i pętlę napraw ↗</a>`;
}

function render(force = false) {
  if (!data) return;
  const signature = JSON.stringify([data.projects, data.tickets, data.jobs, data.host_online, data.loop, data.ranking, view, project, query, filter, streamSource, streamRepo, streamTickets.length, streamLoading], (key, value) => key === 'observed' ? undefined : value);
  if (!force && signature === lastRender) return;
  lastRender = signature;

  const info = views[view];
  $('#crumb').textContent = info[0];
  $('#heading').textContent = info[1];
  $('#subtitle').textContent = info[2];
  $('#eyebrow').textContent = project || 'PRZESTRZEŃ ROBOCZA';

  document.querySelectorAll('#navigation button').forEach(b => {
    b.classList.toggle('active', b.dataset.view === view);
    b.setAttribute('aria-current', b.dataset.view === view ? 'page' : 'false');
  });

  const isRunning = data.loop?.status === 'running';
  const ind = $('#liveRunIndicator');
  if (ind) ind.style.display = isRunning ? 'inline-flex' : 'none';

  $('#statusFilterLabel').hidden = view !== 'tickets';
  $('#search').disabled = ['desktop', 'benchmark'].includes(view);
  $('#newTicket').disabled = !data.projects.length;

  const focused = document.activeElement?.dataset;
  const key = focused ? JSON.stringify({...focused}) : null;

  $('#content').innerHTML = 
    view === 'overview' ? overview() :
    view === 'tasks' ? renderTasks() :
    view === 'projects' ? projectView() :
    view === 'tickets' ? board() :
    view === 'runner' ? renderRunner() :
    view === 'workspaces' ? workspaces() :
    view === 'benchmark' ? benchmark() :
    `<div class="notice"><p>Terminal projektu uruchomisz z jego karty. <a class="link" href="${esc(safeUrl(novncUrl))}" target="_blank" rel="noopener">Otwórz noVNC w pełnym oknie ↗</a></p></div>${new URLSearchParams(location.search).has('desktop') ? empty('Panel jest już otwarty w pulpicie noVNC', 'Przełącz się na okno terminala projektu.') : `<iframe class="desktop-frame" title="Pulpit noVNC" src="${esc(safeUrl(novncUrl))}?autoconnect=true&resize=scale"></iframe>`}`;

  if (view === 'runner') renderRunnerLogs();

  if (key && key !== '{}') {
    for (const el of $('#content').querySelectorAll('button')) {
      if (JSON.stringify({...el.dataset}) === key) {
        el.focus({ preventScroll: true });
        break;
      }
    }
  }
}

function safeUrl(url) {
  try {
    const u = new URL(url, location.href);
    return ['http:', 'https:'].includes(u.protocol) ? u.href : '#';
  } catch {
    return '#';
  }
}

function go(next, name) {
  if (name !== undefined) {
    project = name;
    try { localStorage.setItem('gitive-project', project); } catch {}
    $('#projectFilter').value = project;
  }
  view = next;
  render(true);
  if (view === 'tasks' && !streamTickets.length) fetchStreamTickets();
  if (view === 'runner') fetchRunnerProgress();
}

async function refresh() {
  if (inflight) return;
  inflight = true;
  try {
    const r = await fetch('/api/control');
    if (!r.ok) throw Error('Panel chwilowo niedostępny');
    data = await r.json();
    if (project && !data.projects.some(p => p.name === project)) project = '';
    const options = '<option value="">Wszystkie projekty</option>' + data.projects.map(p => `<option value="${esc(p.name)}">${esc(p.title)}</option>`).join('');
    if ($('#projectFilter').innerHTML !== options) $('#projectFilter').innerHTML = options;
    $('#projectFilter').value = project;
    $('#connection').textContent = data.host_online ? 'Panel i host aktywne' : 'Panel online · host offline';
    $('#connection').style.color = data.host_online ? '' : 'var(--yellow)';
    $('#updated').textContent = 'Odczyt ' + date(data.at);
    $('#errorBanner').hidden = true;
    render();
  } catch (e) {
    $('#connection').textContent = 'Brak połączenia';
    $('#errorBanner').textContent = e.message + ' — ostatni widok może być nieaktualny.';
    $('#errorBanner').hidden = false;
  } finally {
    inflight = false;
  }
}

async function command(body) {
  const r = await fetch('/api/control/action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Loop-Token': token },
    body: JSON.stringify(body)
  });
  const v = await r.json();
  if (!r.ok) throw Error(v.error || 'Operacja nieudana');
  await refresh();
  return v;
}

async function operationDetail() {
  if (!selected || !$('#detail').open) return;
  const scope = { ...selected };
  try {
    const r = await fetch('/api/operations?' + new URLSearchParams({ project: scope.project, ticket: scope.ticket }));
    if (!r.ok) return;
    const value = await r.json();
    if (selected?.project !== scope.project || selected?.ticket !== scope.ticket || !$('#ticketOperation')) return;
    $('#ticketOperation').textContent = value.operation === 'idle' ? 'Brak aktywnego procesu tego ticketu.' : 'Aktualna operacja: ' + value.operation;
    const jobs = data.jobs.filter(j => j.project === scope.project).slice(0, 3);
    $('#ticketHistory').innerHTML = (value.events || []).slice(-5).map(e => `<p>${esc(e.operation)} · ${date(e.at)}</p>`).join('') + jobs.map(j => `<p>${esc(actionLabels[j.action] || j.action)} · ${esc(labels[j.status] || j.status)} · ${date(j.finished || j.created)}<br><small>Operacja projektu ${esc(scope.project)}</small></p>`).join('');
  } catch {
    if ($('#ticketOperation')) $('#ticketOperation').textContent = 'Stan procesu chwilowo niedostępny';
  }
}

function ticketDetail(name, id) {
  const t = data.tickets.find(t => t.project === name && t.id === id), p = data.projects.find(p => p.name === name);
  if (!t || !p) return;
  selected = { project: name, ticket: id };
  const closed = ['done', 'canceled'].includes(t.status);
  const reason = t.execution_state === 'running' ? 'Ticket jest wykonywany.' : closed ? 'Ticket zakończony. Utwórz kolejne zadanie.' : p.repair_block || (!data.host_online ? 'Proces hosta offline' : '');
  
  $('#detailBody').innerHTML = `
    <h2>${esc(t.title)}</h2>
    <p class="muted">${esc(t.project)} / ${esc(t.id)} · aktualizacja ${date(t.updated)}</p>
    <div class="detail-meta">
      ${badge(t.status)}
      <span class="badge">${esc(t.engine.toUpperCase())}</span>
      ${t.parent ? `<span class="badge">↳ ${esc(t.parent)}</span>` : ''}
    </div>
    <div class="ticket-description">${esc(t.description || 'Brak opisu.')}</div>
    ${t.github.url ? `<a class="link" href="${esc(safeUrl(t.github.url))}" target="_blank" rel="noopener">Powiązane GitHub Issue ↗</a>` : '<p class="muted">Ticket lokalny — nie został opublikowany na GitHub.</p>'}
    <div class="detail-actions">
      <button class="primary btn-realize" id="runSelected" ${reason || busy(p) ? 'disabled' : ''}>▷ Uruchom ticket</button>
      ${runtimeButton(p, 'runtime-test', 'Testy projektu')}
      ${runtimeButton(p, 'runtime-terminal', 'Terminal')}
    </div>
    ${reason ? `<div class="notice warning"><p>${esc(reason)}</p></div>` : ''}
    <div class="detail-section">
      <h3>Procesy i historia</h3>
      <p id="ticketOperation">Odczyt procesu…</p>
      <div id="ticketHistory"></div>
    </div>
    <div class="detail-section">
      <h3>Status zadania</h3>
      <div class="inline-actions">
        <select id="manualStatus" aria-label="Nowy status ticketu">
          ${!['open','review','done','blocked','canceled'].includes(t.status) ? `<option value="" disabled selected>${esc(labels[t.status])}</option>` : ''}
          ${['open','review','done','blocked','canceled'].map(s => `<option value="${s}" ${s === t.status ? 'selected' : ''}>${labels[s]}</option>`).join('')}
        </select>
        <button id="saveStatus" ${busy(p) || t.execution_state === 'running' ? 'disabled' : ''}>Zapisz status</button>
      </div>
      <p>Zmiana ręczna trafia do historii Planfile. Wynik testów nie zmienia automatycznie statusu ticketu.</p>
    </div>
    <div class="detail-section">
      <h3>Synchronizacja GitHub</h3>
      <input id="repository" aria-label="Repozytorium GitHub" placeholder="owner/repository" value="${esc(t.github.repository || '')}">
      <div class="detail-actions">
        <button id="pullTicket" ${!data.host_online || busy(p) ? 'disabled' : ''}>Pobierz zmiany (Pull)</button>
        <button id="pushTicket" ${!data.host_online || busy(p) ? 'disabled' : ''}>Wyślij ticket (Push)</button>
      </div>
      <p>Pobieraj istniejące Issue lub wysyłaj zmiany bez wymogu wcześniejszego publikowania.</p>
    </div>
    <p class="form-error" id="detailError" role="alert"></p>`;
  if (!$('#detail').open) $('#detail').showModal();
  operationDetail();
}

function openCreate() {
  const f = $('#ticketForm');
  f.reset();
  f.querySelector('.form-error').textContent = '';
  f.elements.project.innerHTML = data.projects.map(p => `<option value="${esc(p.name)}">${esc(p.title)}</option>`).join('');
  if (project) f.elements.project.value = project;
  parentOptions();
  $('#create').showModal();
  f.elements.title.focus();
}

function parentOptions() {
  const f = $('#ticketForm');
  f.elements.parent.innerHTML = '<option value="">Brak — nowe zadanie</option>' + data.tickets.filter(t => t.project === f.elements.project.value).map(t => `<option value="${esc(t.id)}">${esc(t.id + ' · ' + t.title)}</option>`).join('');
}

function paletteResults() {
  const q = $('#paletteSearch').value.toLowerCase();
  $('#paletteResults').innerHTML = 
    data.projects.filter(p => [p.name, p.title].join(' ').toLowerCase().includes(q)).map(p => `<button class="palette-item" data-project-open="${esc(p.name)}"><span>${esc(p.title)}</span><small>Projekt</small></button>`).join('') +
    data.tickets.filter(t => [t.project, t.id, t.title].join(' ').toLowerCase().includes(q)).slice(0, 20).map(t => `<button class="palette-item" data-ticket="${esc(t.id)}" data-project="${esc(t.project)}"><span>${esc(t.title)}</span><small>${esc(t.project)} / ${esc(t.id)}</small></button>`).join('');
  if (!$('#paletteResults').innerHTML) $('#paletteResults').innerHTML = empty('Brak wyników');
}

function palette() {
  if (!data) return;
  $('#paletteSearch').value = '';
  paletteResults();
  $('#palette').showModal();
  $('#paletteSearch').focus();
}

async function guarded(button, fn, errorTarget) {
  button.disabled = true;
  try {
    await fn();
  } catch (e) {
    if (errorTarget) $(errorTarget).textContent = e.message;
    else toast(e.message);
  } finally {
    if (button.isConnected) button.disabled = false;
  }
}

document.addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b || b.disabled) return;
  if (b.hasAttribute('data-close')) return b.closest('dialog').close();
  if (b.dataset.view) return go(b.dataset.view);
  if (b.dataset.projectOpen) {
    if ($('#palette').open) $('#palette').close();
    return go('projects', b.dataset.projectOpen);
  }
  if (b.dataset.ticket) {
    if ($('#palette').open) $('#palette').close();
    return ticketDetail(b.dataset.project, b.dataset.ticket);
  }
  if (b.dataset.action) return guarded(b, async () => {
    await command({ action: b.dataset.action, project: b.dataset.project });
    toast('Dodano do kolejki: ' + actionLabels[b.dataset.action]);
    if ($('#detail').open) ticketDetail(selected.project, selected.ticket);
  });

  // Stream Tab Switching
  if (b.dataset.streamSource) {
    streamSource = b.dataset.streamSource;
    fetchStreamTickets();
    return;
  }

  // Stream Realize
  if (b.dataset.realizeId) {
    const item = streamTickets.find(t => t.id === b.dataset.realizeId);
    if (item) realizeStreamTicket(item, true);
    return;
  }
  if (b.dataset.streamDetail) {
    const item = streamTickets.find(t => t.id === b.dataset.streamDetail);
    if (item) openStreamModal(item);
    return;
  }
  if (b.id === 'btnConfirmRealize' && streamSelected) {
    const proj = $('#streamTargetProject').value;
    const eng = $('#streamEngine').value;
    realizeStreamTicket(streamSelected, true, eng, proj);
    return;
  }
  if (b.id === 'btnConfirmImport' && streamSelected) {
    const proj = $('#streamTargetProject').value;
    const eng = $('#streamEngine').value;
    realizeStreamTicket(streamSelected, false, eng, proj);
    return;
  }
  if (b.id === 'btnStreamRefresh') {
    fetchStreamTickets();
    return;
  }
  if (b.id === 'btnStopLoop') {
    fetch('/api/stop', { method: 'POST', headers: { 'X-Loop-Token': token } }).then(() => {
      toast('Wysłano sygnał zatrzymania pętli');
      refresh();
    });
    return;
  }

  if (b.id === 'saveStatus') return guarded(b, async () => {
    await command({ action: 'update-ticket', ...selected, status: $('#manualStatus').value });
    ticketDetail(selected.project, selected.ticket);
    toast('Zapisano status w Planfile');
  }, '#detailError');

  if (b.id === 'runSelected') return guarded(b, async () => {
    await command({ action: 'run-ticket', ...selected });
    toast('Uruchomiono ticket');
    go('runner');
  }, '#detailError');

  if (['pullTicket', 'pushTicket'].includes(b.id)) return guarded(b, async () => {
    await command({
      action: 'sync-ticket',
      ...selected,
      repository: $('#repository').value.trim(),
      direction: b.id === 'pullTicket' ? 'pull' : 'push'
    });
    toast('Synchronizacja w kolejce hosta');
    ticketDetail(selected.project, selected.ticket);
  }, '#detailError');
});

document.addEventListener('change', e => {
  if (e.target.id === 'streamRepoSelect') {
    if (e.target.value === 'custom') {
      $('#streamCustomRepo').style.display = 'inline-block';
      $('#streamCustomRepo').focus();
    } else {
      $('#streamCustomRepo').style.display = 'none';
      streamRepo = e.target.value;
      fetchStreamTickets();
    }
  }
});
document.addEventListener('keydown', e => {
  if (e.target.id === 'streamCustomRepo' && e.key === 'Enter') {
    streamRepo = e.target.value.trim();
    fetchStreamTickets();
  }
});

$('#newTicket').onclick = openCreate;
$('#refresh').onclick = refresh;
$('#projectFilter').onchange = e => go(view, e.target.value);
$('#search').oninput = e => {
  query = e.target.value.toLowerCase();
  render();
  if (view === 'tasks') fetchStreamTickets();
};
$('#statusFilter').onchange = e => {
  filter = e.target.value;
  render();
};
$('#ticketForm').elements.project.onchange = parentOptions;

$('#ticketForm').onsubmit = async e => {
  e.preventDefault();
  const f = e.target;
  await guarded(f.querySelector('[type=submit]'), async () => {
    const result = await command({ action: 'create-ticket', ...Object.fromEntries(new FormData(f)) });
    $('#create').close();
    go('tickets', result.project);
    toast('Utworzono ' + result.id + ' w ' + result.project);
  }, '#ticketForm .form-error');
};

$('#paletteButton').onclick = palette;
$('#paletteSearch').oninput = paletteResults;
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    if (!document.querySelector('dialog[open]')) palette();
  }
});

// Initialization
refresh();
setInterval(() => {
  if (!document.hidden) {
    refresh();
    operationDetail();
    if (view === 'tasks') {
      fetchStreamTickets();
    }
    if (view === 'runner' || data?.loop?.status === 'running') {
      fetchRunnerProgress();
    }
  }
}, 3000);
