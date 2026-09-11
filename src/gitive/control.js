
function extractDeduplicationKey(text) {
  if (!text) return null;
  let m = /<!--\s*planfile:deduplication-key=([^\s>]+)\s*-->/i.exec(text);
  if (m) return m[1];
  m = /fingerprint:\s*([A-Fa-f0-9]+)/i.exec(text);
  if (m) return m[1];
  return null;
}

function extractSourceLine(text) {
  if (!text) return null;
  const m = /source:\s*(https:\/\/github\.com\/[^\s]+)/i.exec(text);
  return m ? m[1] : null;
}

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

let data = null, view = 'overview', project = '', query = '', filter = '', inflight = false, actionInFlight = false, lastRender = '', selected = null, toastTimer;
let streamSource = 'all', streamRepo = 'semcod/code2logic', streamTickets = [], streamLoading = false, streamSelected = null, lastStreamFetch = 0, streamActionInFlight = false;
let runnerData = { lines: [], events: [], state: {} }, runnerTimer = null;
let initialActionHandled = false;

const initialUrlParams = new URLSearchParams(window.location.search);
const initTab = initialUrlParams.get('tab') || initialUrlParams.get('view');
if (initTab && views[initTab]) view = initTab;
const initProj = initialUrlParams.get('project');
if (initProj) {
  project = initProj;
} else {
  try { project = localStorage.getItem('gitive-project') || ''; } catch {}
}
const initSource = initialUrlParams.get('source');
if (initSource && ['all', 'github', 'gitlab', 'local'].includes(initSource)) streamSource = initSource;
const initRepo = initialUrlParams.get('repo');
if (initRepo) streamRepo = initRepo;
const initQuery = initialUrlParams.get('q');
if (initQuery) query = initQuery.toLowerCase();
const initFilter = initialUrlParams.get('status');
if (['active', 'done', 'blocked'].includes(initFilter)) filter = initFilter;
let initialStreamHandled = false;

function updateUrl(params = {}) {
  try {
    const url = new URL(window.location.href);
    for (const [k, v] of Object.entries(params)) {
      if (v === null || v === undefined || v === '') {
        url.searchParams.delete(k);
      } else {
        url.searchParams.set(k, v);
      }
    }
    if (url.searchParams.get('tab') === 'overview') {
      url.searchParams.delete('tab');
    }
    url.searchParams.delete('view');
    const newSearch = url.searchParams.toString();
    const newPath = url.pathname + (newSearch ? '?' + newSearch : '');
    window.history.replaceState({}, '', newPath);
  } catch {}
}
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

async function fetchStreamTickets(force = false) {
  const now = Date.now();
  if (streamLoading) return;
  if (!force && now - lastStreamFetch < 15000) return;
  streamLoading = true;
  lastStreamFetch = now;
  try {
    const params = new URLSearchParams({ source: streamSource, repo: streamRepo, q: query });
    const res = await fetch('/api/integrations/tickets?' + params);
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`);
    streamTickets = (Array.isArray(payload) ? payload : []).filter(t => t && t.status === "open");
    if (!initialStreamHandled && initialUrlParams.get('ticket')) {
      const actTicket = initialUrlParams.get('ticket');
      const item = streamTickets.find(t => t.id === actTicket || String(t.number) === actTicket);
      if (item) {
        initialStreamHandled = true;
        openStreamModal(item);
      }
    }
  } catch (e) {
    if (force) {
      toast('Nie udało się pobrać zadań: ' + (e.message || 'błąd połączenia'));
    }
  } finally {
    streamLoading = false;
    if (view === 'tasks') render(true);
  }
}

function renderTasks() {
  const popularRepos = ['semcod/code2logic', 'semcod/gitive', 'subactor/doctor-agent'];
  const activeTickets = streamTickets.filter(t => {
    if (!project) return true;
    const pLow = project.toLowerCase();
    if (t.project && t.project.toLowerCase() === pLow) return true;
    if (t.repository && (t.repository.toLowerCase() === pLow || t.repository.toLowerCase().endsWith('/' + pLow))) return true;
    return false;
  });
  return `
  <div class="stream-toolbar">
    <div class="stream-source-tabs">
      <button class="${streamSource==='all'?'active':''}" data-stream-source="all">Wszystkie źródła</button>
      <button class="${streamSource==='github'?'active':''}" data-stream-source="github">GitHub</button>
      <button class="${streamSource==='gitlab'?'active':''}" data-stream-source="gitlab">GitLab</button>
      <button class="${streamSource==='local'?'active':''}" data-stream-source="local">Lokalne (otwarte)</button>
    </div>
    ${streamSource !== 'local' ? `
    <div class="stream-repo-picker">
      <label style="font-size:12px;color:var(--muted);font-weight:600;">Repozytorium:</label>
      <select id="streamRepoSelect">
        ${popularRepos.map(r => `<option value="${esc(r)}" ${r===streamRepo?'selected':''}>${esc(r)}</option>`).join('')}
        <option value="custom">Inne repozytorium…</option>
      </select>
      <input id="streamCustomRepo" placeholder="owner/repo" value="${esc(streamRepo)}" style="display:${popularRepos.includes(streamRepo)?'none':'inline-block'};width:180px;">
      <button class="quiet" id="btnStreamRefresh">↻ Pobierz na żywo</button>
    </div>` : `
    <div class="stream-repo-picker">
      <span style="font-size:12px;color:var(--muted);">${project ? `Filtr projektu: <strong>${esc(project)}</strong>` : 'Wszystkie lokalne projekty'}</span>
      <button class="quiet" id="btnStreamRefresh">↻ Odśwież lokalne tickety</button>
    </div>`}
  </div>

  ${streamLoading ? `<div class="empty"><div class="pulse-dot"></div> Ładowanie i strumieniowanie ticketów z ${esc(streamSource)}…</div>` : ''}

  ${!streamLoading && activeTickets.length === 0 ? empty(
    project ? `Brak otwartych zadań dla projektu ${project} w wybranym źródle` : 'Brak otwartych zadań w wybranym źródle',
    project ? 'Zmień filtr projektu na górze strony na „Wszystkie projekty” lub wybierz inne źródło.' : 'Wszystkie zadania w wybranym źródle są już zrealizowane lub w trakcie prac.'
  ) : ''}

  <div class="stream-grid">
    ${activeTickets.map(t => {
      const isGh = t.source === 'github', isGl = t.source === 'gitlab';
      const isLocal = t.source === 'local';
      const sourceClass = isGh ? 'github' : isGl ? 'gitlab' : t.labels?.includes('worktree') ? 'worktree' : 'local';
      const sourceLabel = isGh ? `GitHub #${t.number}` : isGl ? `GitLab #${t.number}` : t.labels?.includes('worktree') ? 'Worktree' : 'Lokalny';
      const planfileUrl = t.planfile_url || `/?tab=tickets&project=${encodeURIComponent(t.project || '')}&ticket=${encodeURIComponent(t.planfile_id || t.number || '')}&action=detail`;
      return `
      <article class="stream-card" data-stream-card="${esc(t.id)}" style="cursor:pointer;">
        <div>
          <div class="stream-card-top">
            <span class="source-tag ${sourceClass}">${esc(sourceLabel)}</span>
            <small style="color:var(--muted);">${relTime(t.updated_at || t.created_at)}</small>
          </div>
          <h4 style="margin:10px 0 6px;">
            ${t.url ? `<a href="${esc(safeUrl(t.url))}" target="_blank" rel="noopener">${esc(t.title)} ↗</a>` : isLocal ? `<a href="${esc(safeUrl(planfileUrl))}" title="Otwórz ticket w Planfile">${esc(t.title)} ↗</a>` : esc(t.title)}
          </h4>
          <p class="stream-card-desc">${esc(t.description || 'Brak dodatkowego opisu.')}</p>
        </div>
        <div class="stream-card-tags">
          <span style="font-size:11px;color:var(--muted);">${esc(t.repository || t.project)}</span>
          ${isLocal ? `<a class="link" href="${esc(safeUrl(planfileUrl))}" title="Otwórz szczegóły w Planfile">Planfile ↗</a>` : ''}
          ${(t.labels || []).slice(0, 3).map(l => `<span class="badge" style="font-size:10px;">${esc(l)}</span>`).join('')}
        </div>
        <div class="stream-card-foot">
          <button class="btn-realize" data-realize-id="${esc(t.id)}" title="Automatycznie powiąż i uruchom wykonawcę">
            ⚡ Realizuj zadanie
          </button>
          ${isLocal ? `<button class="quiet" data-close-local-id="${esc(t.id)}" title="Ustaw status done w Planfile">✓ Zamknij ticket</button>` : ''}
          <button class="quiet" data-stream-detail="${esc(t.id)}">Szczegóły</button>
        </div>
      </article>`;
    }).join('')}
  </div>`;
}

function extractTicketTargets(item) {
  const text = `${item?.title || ''}\n${item?.description || ''}\n${item?.target_repository || ''}\n${item?.repository || ''}`;
  const targets = [];
  if (item?.repository) targets.push(item.repository.toLowerCase());
  if (item?.target_repository) targets.push(item.target_repository.toLowerCase());
  const r1 = /(?:^|\n)\s*(?:source|target_repository|repository)\s*:\s*(?:https:\/\/github\.com\/|source:\/\/)?([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)/gim;
  let m;
  while ((m = r1.exec(text)) !== null) {
    targets.push(m[1].toLowerCase());
  }
  const r2 = /[—-]\s*([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)\b/gm;
  while ((m = r2.exec(item?.title || '')) !== null) {
    targets.push(m[1].toLowerCase());
  }
  return [...new Set(targets)];
}

function resolveTargetProject(item) {
  const projects = (data?.projects || []).filter(p => !p.error);
  const targets = extractTicketTargets(item);

  for (const target of targets) {
    const matched = projects.find(p => {
      const pRepo = (p.repository || (p.source || '').replace('/source/github/', '')).toLowerCase();
      return pRepo === target || pRepo.endsWith('/' + target) || target.endsWith('/' + p.name.toLowerCase()) || p.name.toLowerCase() === target;
    });
    if (matched) return matched.name;
  }

  if (targets.length > 0) {
    return '';
  }

  if (project && projects.some(p => p.name === project)) {
    return project;
  }

  const text = `${item?.title || ''} ${item?.description || ''}`.toLowerCase();
  const matchedFromContent = projects.find(p => text.includes(p.name.toLowerCase()));
  if (matchedFromContent) return matchedFromContent.name;

  const runnable = projects.find(p => !p.repair_block);
  if (runnable) return runnable.name;

  return projects[0]?.name || '';
}

function openStreamModal(t) {
  streamSelected = t;
  const projects = (data?.projects || []).filter(p => !p.error);
  const unavailableProjects = (data?.projects || []).filter(p => p.error);
  const selectedProjName = resolveTargetProject(t) || projects[0]?.name || '';
  updateUrl({ tab: view, project: selectedProjName || project || null, ticket: t.id, action: 'stream-detail' });

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
            ${projects.map(p => `<option value="${esc(p.name)}" ${p.name === selectedProjName ? 'selected' : ''}>${esc(p.title)} (${esc(p.name)})</option>`).join('')}
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
      <div id="streamTwinNotice" class="notice warning" style="margin-top:10px;" hidden>
        <p>⚠️ Ten projekt posiada odizolowane środowisko (Digital Twin). Bezpośrednie uruchomienie pętli z poziomu kontenera nadrzędnego jest zablokowane. Użyj opcji <strong>"Zapisz w Planfile"</strong> lub przejdź do testów projektu.</p>
      </div>
      <div class="dialog-actions" style="margin-top:14px;">
        <button class="btn-realize" id="btnConfirmRealize">⚡ Uruchom realizację teraz</button>
        <button class="quiet" id="btnConfirmImport">Zapisz w Planfile (bez startu)</button>
      </div>
    </div>
  `;
  const updateModalState = () => {
    const selProjName = $('#streamTargetProject')?.value;
    const targetProj = projects.find(p => p.name === selProjName);
    const targets = extractTicketTargets(t);
    const hasRepairBlock = Boolean(targetProj && (targetProj.repair_block || targetProj.error));
    const btn = $('#btnConfirmRealize');
    const notice = $('#streamTwinNotice');

    const targetMismatch = targets.length > 0 && targetProj && !targets.some(target => {
      const pRepo = (targetProj.repository || (targetProj.source || '').replace('/source/github/', '')).toLowerCase();
      return pRepo === target || target.endsWith('/' + targetProj.name.toLowerCase()) || targetProj.name.toLowerCase() === target;
    });

    if (btn) {
      const loopBusy = ['running', 'stopping'].includes(data?.loop?.status);
      btn.disabled = hasRepairBlock || targetMismatch || loopBusy;
      btn.title = targetMismatch
        ? `Ticket wskazuje ${targets.join(', ')}; projekt ${targetProj?.name} ma inne źródło.`
        : hasRepairBlock
        ? (targetProj.repair_block || targetProj.error || 'Projekt jest niedostępny')
        : loopBusy
        ? 'Pętla Gitive jest już aktywna — zaczekaj na zakończenie.'
        : '';
    }
    if (notice) {
      if (targetMismatch) {
        notice.hidden = false;
        notice.innerHTML = `<p>⚠️ Ticket wskazuje repozytorium <strong>${esc(targets.join(', '))}</strong>. Wybrany projekt <strong>${esc(targetProj?.name)}</strong> ma checkout dla innego repozytorium. Wybierz właściwy projekt lub zarejestruj go przed realizacją.</p>`;
      } else {
        notice.hidden = !hasRepairBlock;
        if (hasRepairBlock) {
          notice.innerHTML = `<p>⚠️ Ten projekt posiada odizolowane środowisko (Digital Twin). Bezpośrednie uruchomienie pętli z poziomu kontenera nadrzędnego jest zablokowane. Użyj opcji <strong>"Zapisz w Planfile"</strong> lub przejdź do testów projektu.</p>`;
        }
      }
    }
    updateUrl({ tab: view, project: selProjName || project || null, ticket: t.id, action: 'stream-detail' });
  };
  $('#streamTargetProject')?.addEventListener('change', updateModalState);
  updateModalState();
  if (unavailableProjects.length) {
    const notice = $('#streamTwinNotice');
    if (notice && !projects.length) {
      notice.hidden = false;
      notice.innerHTML = `<p>Żaden projekt nie ma dostępnej prywatnej kopii. Najpierw zarejestruj lub odtwórz projekt w Gitive.</p>`;
    }
  }
  $('#streamModal').showModal();
}

async function realizeStreamTicket(item, runNow = true, engine = 'auto', targetProj = null) {
  if (streamActionInFlight) return;
  streamActionInFlight = true;
  try {
    const proj = targetProj || resolveTargetProject(item);
    const targets = extractTicketTargets(item);
    if (!proj) {
      if (targets.length) {
        throw new Error(`Ticket wskazuje repozytorium ${targets.join(', ')}; żaden projekt w Gitive nie jest dla niego zarejestrowany.`);
      }
      throw new Error('Wybierz projekt z dostępną prywatną kopią');
    }
    const targetP = data?.projects?.find(p => p.name === proj);
    if (!targetP || targetP.error) {
      throw new Error('Wybierz projekt z dostępną prywatną kopią');
    }
    if (runNow && ['running', 'stopping'].includes(data?.loop?.status)) {
      throw new Error('Pętla Gitive jest już aktywna — zaczekaj na zakończenie.');
    }
    if (runNow && targetP?.repair_block) {
      openStreamModal(item);
      throw new Error(targetP.repair_block);
    }
    const body = {
      project: proj,
      repository: item.repository || proj,
      number: item.number,
      title: item.title,
      description: item.description,
      url: item.url,
      engine: engine,
      ticket: item.id,
      action: runNow ? 'realize-remote-ticket' : 'import-remote-ticket'
    };
    const val = await command(body);
    toast(runNow ? `Uruchomiono realizację zadania w ${proj}!` : `Zapisano ticket w ${proj}`);
    if ($('#streamModal').open) $('#streamModal').close();
    await refresh();
    if (runNow) {
      go('runner', proj);
      updateUrl({ ticket: item.id, action: 'running' });
    }
  } catch (err) {
    toast('Błąd: ' + err.message);
  } finally {
    streamActionInFlight = false;
  }
}

async function closeLocalStreamTicket(item) {
  const projectName = item.project;
  const ticketId = item.planfile_id || item.number;
  if (!projectName || !ticketId) throw Error('Brak projektu lub identyfikatora Planfile');
  await command({ action: 'update-ticket', project: projectName, ticket: ticketId, status: 'done' });
  streamTickets = streamTickets.filter(ticket => ticket.id !== item.id);
  toast(`Zamknięto ${ticketId} w Planfile projektu ${projectName}`);
  if (view === 'tasks') render(true);
  await fetchStreamTickets(true);
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
  const loop = data?.loop || {};
  const isRunning = loop.status === 'running';

  if (!lines.length) {
    if (isRunning) {
      const activeTicket = loop.ticket_id || loop.requested_ticket || '';
      const activeProj = loop.project || project || '';
      win.innerHTML = `
        <div class="log-line stage"><span class="pulse-dot"></span> [Gitive] Inicjalizacja zadania ${esc(activeTicket ? `${activeTicket} (${activeProj})` : activeProj)}...</div>
        <div class="log-line dim">Przygotowywanie kontenera, sprawdzanie stanu repozytorium i uruchamianie testów...</div>`;
    } else {
      win.innerHTML = '<div class="log-line dim">Brak zarejestrowanych logów wykonawcy. Wybierz zadanie w zakładce Zadania lub Projekty, aby uruchomić pętlę.</div>';
    }
    return;
  }
  win.innerHTML = lines.map(line => {
    let cls = '';
    if (line.startsWith('GITIVE_RESULT') || line.includes('PASSED') || line.includes('passed') || line.includes('OK')) cls = 'ok';
    else if (line.includes('FAILED') || line.includes('Error') || line.includes('error') || line.includes('Błąd') || line.includes('rejected')) cls = 'err';
    else if (line.startsWith('START') || line.startsWith('stage:') || line.startsWith('gitive:') || line.startsWith('[Gitive]')) cls = 'stage';
    else if (line.startsWith('ITERATION') || line.includes('warn')) cls = 'warn';
    return `<div class="log-line ${cls}">${esc(line)}</div>`;
  }).join('');
  win.scrollTop = win.scrollHeight;
}

function renderRunner() {
  const loop = data?.loop || {};
  const isRunning = loop.status === 'running';
  const curProj = loop.project || project || '';
  const curTicketId = loop.ticket_id || loop.requested_ticket || '';
  const curTicket = (curTicketId && data?.tickets?.find(t => (t.project === curProj || !curProj) && t.id === curTicketId))
    || (curTicketId && data?.tickets?.find(t => t.id === curTicketId))
    || null;
  const p = data?.projects?.find(proj => proj.name === curProj);
  const ticketTitle = curTicket?.title || loop.ticket_title || (curTicketId ? `Zadanie ${curTicketId}` : (p?.title || curProj ? `Projekt ${p?.title || curProj}` : ''));
  const ticketDesc = curTicket?.description || loop.ticket_desc || loop.goal || p?.goal || '';
  const ticketEngine = curTicket?.engine || loop.executor || p?.solution || 'auto';
  const ticketTarget = curTicket?.target_repository || p?.repository || '';
  const isBlocked = loop.status === 'blocked' || curTicket?.status === 'blocked';

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

  const statusBadge = isRunning
    ? `<span class="badge" style="background:rgba(124,58,237,0.15);color:#7c3aed;border-color:rgba(124,58,237,0.3);font-weight:700;"><span class="pulse-dot" style="background:#7c3aed;"></span> Pętla aktywna</span>`
    : isBlocked
    ? `<span class="badge" style="background:rgba(239,68,68,0.15);color:#dc2626;border-color:rgba(239,68,68,0.3);font-weight:700;">Zablokowana (wymaga analizy)</span>`
    : `<span class="badge" style="font-weight:600;">${esc(labels[loop.status] || loop.status || 'Bezczynny')}</span>`;

  return `
  <div class="runner-box">
    <div class="runner-header">
      <div style="max-width:75%;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
          <span class="eyebrow">AKTYWNY CYKL GITIVE · ${esc((curProj || 'Brak').toUpperCase())}</span>
          ${statusBadge}
        </div>
        <h2 style="margin:4px 0 6px 0;font-size:18px;line-height:1.35;">
          ${ticketTitle ? esc(ticketTitle) : `Projekt: ${esc(curProj || 'Brak')}`}
        </h2>
        <p class="muted" style="margin:0;font-size:12px;">
          Projekt: <strong>${esc(curProj || 'Brak')}</strong>
          ${curTicketId ? ` · Ticket: <strong>${esc(curTicketId)}</strong>` : ''}
          ${ticketTarget ? ` · Repozytorium: <strong>${esc(ticketTarget)}</strong>` : ''}
          · Silnik: <strong>${esc(labels[loop.status] || loop.status || 'Bezczynny')}</strong>
          · Wykonawca: <strong>${esc((ticketEngine || 'auto').toUpperCase())}</strong>
          · Iteracja: ${loop.cycle || 1}
        </p>
      </div>
      <div style="display:flex;gap:8px;align-items:center;">
        ${isRunning ? `<button class="quiet" id="btnStopLoop" style="color:var(--red);border-color:var(--red);">■ Zatrzymaj</button>` : ''}
        ${curTicket ? `<button class="quiet" data-project="${esc(curTicket.project || curProj)}" data-ticket="${esc(curTicket.id)}">📋 Szczegóły ticketu</button>` : ''}
        <button class="primary" data-view="tasks">Zadania projektu →</button>
      </div>
    </div>

    ${(loop.error || isBlocked || ['interrupted', 'blocked', 'failed'].includes(loop.status)) ? `
    <div class="notice warning" style="margin:10px 0;padding:10px 14px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.35);border-radius:6px;color:#fca5a5;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
      <div style="font-size:13px;line-height:1.4;">
        <strong>Stan pętli:</strong> ${esc(labels[loop.status] || loop.status || 'Błąd')}
        ${loop.error ? ` — ${esc(loop.error)}` : ''}
      </div>
      <button type="button" class="badge" id="btnResetLoop" style="cursor:pointer;border:1px solid rgba(239,68,68,0.4);background:rgba(239,68,68,0.25);color:#fff;padding:0.3rem 0.7rem;font-weight:600;">Wyczyść stan pętli (Gotowość) ↺</button>
    </div>` : ''}

    ${curTicketId ? `
    <div class="runner-ticket-card">
      <div class="runner-ticket-head">
        <div class="runner-ticket-badges">
          <span class="badge" style="font-weight:700;background:rgba(59,130,246,0.15);color:#2563eb;border-color:rgba(59,130,246,0.3);">${esc(curTicketId)}</span>
          ${curTicket?.status ? badge(curTicket.status) : ''}
          <span class="badge">${esc((ticketEngine || 'auto').toUpperCase())}</span>
          ${ticketTarget ? `<span class="badge muted">Cel: ${esc(ticketTarget)}</span>` : ''}
          ${curTicket?.priority ? `<span class="badge muted">Priorytet: ${esc(curTicket.priority)}</span>` : ''}
        </div>
        <div class="runner-ticket-actions">
          ${curTicket ? `<button class="quiet btn-sm" data-project="${esc(curTicket.project || curProj)}" data-ticket="${esc(curTicket.id)}">Otwórz cały ticket ↗</button>` : ''}
          ${curTicket?.github?.url ? `<a class="link btn-sm" href="${esc(safeUrl(curTicket.github.url))}" target="_blank" rel="noopener">GitHub Issue ↗</a>` : ''}
        </div>
      </div>
      <div class="runner-ticket-title-text">${esc(ticketTitle)}</div>
      ${ticketDesc ? `
      <div class="runner-ticket-desc">
        <p>${esc(ticketDesc.slice(0, 600))}${ticketDesc.length > 600 ? '…' : ''}</p>
      </div>` : ''}
    </div>` : `
    <div class="runner-ticket-card runner-ticket-card-empty">
      <div class="runner-ticket-head">
        <div class="runner-ticket-badges">
          <span class="badge muted">Brak aktywnego ticketu</span>
        </div>
      </div>
      <p class="muted" style="margin:0;font-size:13px;">Pętla nie realizuje w tej chwili konkretnego ticketu dla projektu <strong>${esc(curProj || 'wszystkie')}</strong>.</p>
      <div>
        <button class="primary btn-sm" data-view="tasks">Wybierz zadanie z listy →</button>
      </div>
    </div>`}

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
  updateUrl({ tab: view, project, q: query || null, status: filter || null, source: streamSource === 'all' ? null : streamSource, action: null, ticket: null });
  render(true);
  if (view === 'tasks' && !streamTickets.length) fetchStreamTickets(true);
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
    if (!initialActionHandled) {
      initialActionHandled = true;
      const act = initialUrlParams.get('action');
      const actTicket = initialUrlParams.get('ticket');
      const actProj = initialUrlParams.get('project') || project;
      if (act === 'detail' && actTicket && actProj) {
        ticketDetail(actProj, actTicket);
      } else if (act === 'new-ticket') {
        $('#create').showModal();
      }
    }
  } catch (e) {
    $('#connection').textContent = 'Brak połączenia';
    $('#errorBanner').textContent = e.message + ' — ostatni widok może być nieaktualny.';
    $('#errorBanner').hidden = false;
  } finally {
    inflight = false;
  }
}

async function command(body) {
  if (actionInFlight) throw Error('Operacja jest już wysyłana — zaczekaj na odpowiedź');
  actionInFlight = true;
  updateUrl({
    tab: view,
    project: body.project || project || null,
    ticket: body.ticket || (body.number ? String(body.number) : null),
    action: body.action || null
  });
  try {
    const r = await fetch('/api/control/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Loop-Token': token },
      body: JSON.stringify(body)
    });
    const v = await r.json();
    if (!r.ok) throw Error(v.error || 'Operacja nieudana');
    await refresh();
    return v;
  } finally {
    actionInFlight = false;
  }
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
  let t = data.tickets.find(t => t.project === name && t.id === id);
  let p = data.projects.find(p => p.name === name);
  if (!t) {
    t = data.tickets.find(tk => tk.id === id);
    if (t) {
      name = t.project;
      p = data.projects.find(proj => proj.name === name);
    }
  }
  if (!t || !p) return;

  const targetProjName = resolveTargetProject(t);
  const targetP = targetProjName ? data.projects.find(proj => proj.name === targetProjName) : null;
  const isRouted = targetProjName && targetProjName !== name;
  const activeP = isRouted && targetP ? targetP : p;
  const targetTicket = isRouted ? data.tickets.find(tk => {
    if (tk.project !== targetProjName) return false;
    if (tk.id === id) return true;
    const tDedup = extractDeduplicationKey(t.description);
    const tkDedup = extractDeduplicationKey(tk.description);
    if (tDedup && tkDedup) return tDedup === tkDedup;
    const tSrc = extractSourceLine(t.description);
    const tkSrc = extractSourceLine(tk.description);
    if (tSrc && tkSrc) return tSrc === tkSrc;
    return tk.title === t.title && !tDedup && !tkDedup;
  }) : null;

  selected = {
    project: isRouted && targetP ? targetP.name : name,
    ticket: targetTicket ? targetTicket.id : id,
    original_project: name
  };
  updateUrl({ action: 'detail', project: name, ticket: id });
  const closed = ['done', 'canceled'].includes(t.status);
  const loopBusy = ['running', 'stopping'].includes(data.loop?.status);
  const isExecuting = t.execution_state === 'running' && loopBusy && (data.loop?.ticket_id === t.id || data.loop?.requested_ticket === t.id);
  const isReviewOnly = Boolean(t.requires_human_review || (t.description && (t.description.toLowerCase().includes('assessment: review_required') || t.description.toLowerCase().includes('not repair authorization'))));
  const reason = isExecuting ? 'Ticket jest wykonywany.' : closed ? 'Ticket zakończony. Utwórz kolejne zadanie.' : isReviewOnly ? 'Ticket diagnostyczny — wymaga autoryzacji przed naprawą.' : (activeP.repair_block || (loopBusy ? 'Pętla Gitive jest już aktywna — zaczekaj na zakończenie.' : (!data.host_online ? 'Proces hosta offline' : '')));

  const routingNotice = isRouted && targetP
    ? `<div class="notice info" style="margin:0.75rem 0;padding:0.75rem 1rem;background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);border-radius:6px;color:#93c5fd;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.5rem;"><p style="margin:0;">ℹ️ Ten ticket dotyczy repozytorium <strong>${esc(targetP.repository || targetProjName)}</strong> (projekt: <strong>${esc(targetP.name)}</strong>). Zostanie automatycznie zrealizowany w powiązanym projekcie <strong>${esc(targetP.name)}</strong>.</p><button type="button" class="badge" data-switch-project="${esc(targetP.name)}" style="cursor:pointer;border:none;background:#2563eb;color:#fff;padding:0.25rem 0.6rem;">Przejdź do ${esc(targetP.name)} →</button></div>`
    : '';

  const reviewNotice = isReviewOnly
    ? `<div class="notice warning" style="margin:0.75rem 0;padding:0.75rem 1rem;background:rgba(234,179,8,0.12);border:1px solid rgba(234,179,8,0.35);border-radius:6px;color:#fde047;"><p style="margin:0 0 0.5rem 0;font-weight:600;">⚠ Zgłoszenie diagnostyczne (review_required)</p><p style="margin:0 0 0.75rem 0;font-size:13px;line-height:1.4;">To zgłoszenie jest analizą problemu i nie autoryzuje automatycznej naprawy domyślnie. Możesz autoryzować naprawę lub utworzyć osobne zadanie naprawcze.</p><div style="display:flex;gap:0.5rem;flex-wrap:wrap;"><button type="button" class="badge" id="runAuthorized" ${closed || loopBusy || busy(activeP) ? 'disabled' : ''} style="cursor:pointer;border:none;background:#eab308;color:#000;font-weight:700;padding:0.35rem 0.75rem;">⚡ Autoryzuj i napraw</button><button type="button" class="badge" id="createRepairChild" style="cursor:pointer;border:1px solid #eab308;background:transparent;color:#fde047;padding:0.35rem 0.75rem;">+ Utwórz zadanie naprawcze</button></div></div>`
    : '';

  $('#detailBody').innerHTML = `
    <h2>${esc(t.title)}</h2>
    <p class="muted">${esc(t.project)} / ${esc(t.id)} · aktualizacja ${date(t.updated)}</p>
    <div class="detail-meta">
      ${badge(t.status)}
      <span class="badge">${esc(t.engine.toUpperCase())}</span>
      ${t.parent ? `<span class="badge">↳ ${esc(t.parent)}</span>` : ''}
      ${isReviewOnly ? `<span class="badge" style="background:rgba(234,179,8,0.15);color:#ca8a04;border-color:rgba(234,179,8,0.3);font-weight:700;">Diagnostyczny (review)</span>` : ''}
    </div>
    ${routingNotice}
    ${reviewNotice}
    <div class="ticket-description">${esc(t.description || 'Brak opisu.')}</div>
    ${t.github.url ? `<a class="link" href="${esc(safeUrl(t.github.url))}" target="_blank" rel="noopener">Powiązane GitHub Issue ↗</a>` : '<p class="muted">Ticket lokalny — nie został opublikowany na GitHub.</p>'}
    <div class="detail-actions">
      <button class="primary btn-realize" id="runSelected" ${reason || busy(activeP) ? 'disabled' : ''}>${isRouted && targetP ? `▷ Uruchom w projekcie ${esc(targetP.name)}` : '▷ Uruchom ticket'}</button>
      ${runtimeButton(activeP, 'runtime-test', 'Testy projektu')}
      ${runtimeButton(activeP, 'runtime-terminal', 'Terminal')}
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
        <button id="saveStatus" ${busy(p) || isExecuting ? 'disabled' : ''}>Zapisz status</button>
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
  const streamCard = e.target.closest('[data-stream-card]');
  if (streamCard && !e.target.closest('a, button')) {
    const item = streamTickets.find(t => t.id === streamCard.dataset.streamCard);
    if (item) openStreamModal(item);
    return;
  }
  if (e.target.closest('[data-switch-project]')) {
    const sw = e.target.closest('[data-switch-project]').dataset.switchProject;
    if ($('#detail').open) $('#detail').close();
    go('tickets', sw);
    return;
  }
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
    updateUrl({ source: streamSource === 'all' ? null : streamSource });
    fetchStreamTickets(true);
    return;
  }

  // Stream Realize
  if (b.dataset.realizeId) {
    const item = streamTickets.find(t => t.id === b.dataset.realizeId);
    if (item) {
      const targetProjName = resolveTargetProject(item);
      updateUrl({ tab: view, project: targetProjName || project || null, ticket: item.id, action: 'realize' });
      const targetP = data?.projects?.find(p => p.name === targetProjName);
      if (!targetProjName || targetP?.repair_block) {
        openStreamModal(item);
      } else {
        realizeStreamTicket(item, true, 'auto', targetProjName);
      }
    }
    return;
  }
  if (b.dataset.closeLocalId) {
    const item = streamTickets.find(t => t.id === b.dataset.closeLocalId);
    if (!item) return;
    return guarded(b, async () => {
      if (!window.confirm(`Zamknąć ${item.planfile_id || item.number} w Planfile projektu ${item.project}?`)) return;
      await closeLocalStreamTicket(item);
    });
  }
  if (b.dataset.streamDetail) {
    const item = streamTickets.find(t => t.id === b.dataset.streamDetail);
    if (item) openStreamModal(item);
    return;
  }
  if (b.id === 'btnConfirmRealize' && streamSelected) {
    const proj = $('#streamTargetProject').value;
    const eng = $('#streamEngine').value;
    updateUrl({ tab: view, project: proj, ticket: streamSelected.id, action: 'realize' });
    realizeStreamTicket(streamSelected, true, eng, proj);
    return;
  }
  if (b.id === 'btnConfirmImport' && streamSelected) {
    const proj = $('#streamTargetProject').value;
    const eng = $('#streamEngine').value;
    updateUrl({ tab: view, project: proj, ticket: streamSelected.id, action: 'import' });
    realizeStreamTicket(streamSelected, false, eng, proj);
    return;
  }
  if (b.id === 'btnStreamRefresh') {
    fetchStreamTickets(true);
    return;
  }
  if (b.id === 'btnStopLoop') {
    fetch('/api/stop', { method: 'POST', headers: { 'X-Loop-Token': token } }).then(() => {
      toast('Wysłano sygnał zatrzymania pętli');
      refresh();
    });
    return;
  }
  if (b.id === 'btnResetLoop') {
    fetch('/api/reset', { method: 'POST', headers: { 'X-Loop-Token': token } }).then(async () => {
      toast('Zresetowano stan pętli (Gotowość)');
      await refresh();
    }).catch(e => toast(e.message));
    return;
  }
  if (b.id === 'runAuthorized') return guarded(b, async () => {
    const targetProj = selected.project;
    await command({ action: 'run-ticket', ...selected, authorize: true });
    toast(selected.original_project && selected.original_project !== targetProj
      ? `Zautoryzowano i uruchomiono naprawę w ${targetProj}`
      : 'Zautoryzowano i uruchomiono naprawę ticketu');
    go('runner', targetProj);
  }, '#detailError');
  if (b.id === 'createRepairChild') {
    const t = data.tickets.find(tk => tk.project === selected.project && tk.id === selected.ticket) ||
              data.tickets.find(tk => tk.id === selected.ticket);
    if ($('#detail').open) $('#detail').close();
    const f = $('#ticketForm');
    f.reset();
    f.querySelector('.form-error').textContent = '';
    f.elements.project.innerHTML = data.projects.map(p => `<option value="${esc(p.name)}">${esc(p.title)}</option>`).join('');
    f.elements.project.value = selected.project;
    parentOptions();
    f.elements.parent.value = selected.ticket;
    const cleanTitle = (t?.title || '').replace(/^\[Doctor [^\]]+\]\s*/i, '');
    f.elements.title.value = `[Naprawa] ${cleanTitle}`.slice(0, 180);
    f.elements.description.value = `Zadanie naprawcze dla zgłoszenia diagnostycznego ${t?.id || selected.ticket} (${selected.project}).

Należy zweryfikować problem i dodać testy regresyjne oraz bezpieczną obsługę błędu.

---
Oryginalne zgłoszenie:
${t?.description || ''}`.slice(0, 5000);
    $('#create').showModal();
    f.elements.title.focus();
    return;
  }

  if (b.id === 'saveStatus') return guarded(b, async () => {
    await command({ action: 'update-ticket', ...selected, status: $('#manualStatus').value });
    ticketDetail(selected.project, selected.ticket);
    toast('Zapisano status w Planfile');
  }, '#detailError');

  if (b.id === 'runSelected') return guarded(b, async () => {
    const targetProj = selected.project;
    await command({ action: 'run-ticket', ...selected });
    toast(selected.original_project && selected.original_project !== targetProj
      ? `Uruchomiono ticket w projekcie ${targetProj}`
      : 'Uruchomiono ticket');
    go('runner', targetProj);
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
      updateUrl({ repo: streamRepo });
      fetchStreamTickets(true);
    }
  }
});
document.addEventListener('keydown', e => {
  if (e.target.id === 'streamCustomRepo' && e.key === 'Enter') {
    streamRepo = e.target.value.trim();
    updateUrl({ repo: streamRepo });
    fetchStreamTickets(true);
  }
});

$('#newTicket').onclick = openCreate;
$('#refresh').onclick = refresh;
$('#projectFilter').onchange = e => go(view, e.target.value);
$('#search').oninput = e => {
  query = e.target.value.toLowerCase();
  updateUrl({ q: query || null });
  render();
  if (view === 'tasks') fetchStreamTickets();
};
$('#statusFilter').onchange = e => {
  filter = e.target.value;
  updateUrl({ status: filter || null });
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

$('dialog#detail').addEventListener('close', () => updateUrl({ action: null, ticket: null }));
$('dialog#streamModal').addEventListener('close', () => {
  streamSelected = null;
  updateUrl({ action: null, ticket: null });
});
$('dialog#create').addEventListener('close', () => updateUrl({ action: null }));
$('#newTicket').addEventListener('click', () => updateUrl({ action: 'new-ticket' }));

window.addEventListener('popstate', () => {
  const p = new URLSearchParams(window.location.search);
  const t = p.get('tab') || p.get('view') || 'overview';
  if (views[t] && view !== t) {
    view = t;
    render(true);
  }
  const proj = p.get('project') || '';
  if (project !== proj) {
    project = proj;
    $('#projectFilter').value = project;
    render(true);
  }
  const nextQuery = (p.get('q') || '').toLowerCase();
  const nextFilter = ['active', 'done', 'blocked'].includes(p.get('status')) ? p.get('status') : '';
  if (query !== nextQuery || filter !== nextFilter) {
    query = nextQuery;
    filter = nextFilter;
    $('#search').value = query;
    $('#statusFilter').value = filter;
    render(true);
    if (view === 'tasks') fetchStreamTickets(true);
  }
  const nextSource = p.get('source') || 'all';
  if (['all', 'github', 'gitlab', 'local'].includes(nextSource) && streamSource !== nextSource) {
    streamSource = nextSource;
    render(true);
    if (view === 'tasks') fetchStreamTickets(true);
  }
  const act = p.get('action');
  const actTicket = p.get('ticket');
  if (!act && !actTicket) {
    if ($('#detail')?.open) $('#detail').close();
    if ($('#streamModal')?.open) $('#streamModal').close();
    if ($('#create')?.open) $('#create').close();
  } else if (act === 'stream-detail' && actTicket) {
    const item = streamTickets.find(t => t.id === actTicket || String(t.number) === actTicket);
    if (item && !$('#streamModal')?.open) openStreamModal(item);
  } else if (act === 'detail' && actTicket && proj) {
    ticketDetail(proj, actTicket);
  } else if (act === 'new-ticket') {
    if (!$('#create')?.open) $('#create').showModal();
  }
});

// Initialization
$('#search').value = query;
$('#statusFilter').value = filter;
updateUrl({ tab: view, project: project || null, q: query || null, status: filter || null, source: streamSource === 'all' ? null : streamSource });
refresh();
if (view === 'tasks') fetchStreamTickets(true);
setInterval(() => {
  if (!document.hidden) {
    refresh();
    operationDetail();
    if (view === 'tasks') {
      fetchStreamTickets(false);
    }
  }
}, 3000);
setInterval(() => {
  if (!document.hidden && (view === 'runner' || data?.loop?.status === 'running')) {
    fetchRunnerProgress();
  }
}, 1000);
