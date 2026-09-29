// ─── Coquille : navigation, barre du haut, feuille « Plus », rendu ───────────
const RAIL_LABEL = { accueil: 'Accueil', analyser: 'Analyser', studio: 'Studio', packs: 'Packs', lab: 'Lab', learning: 'Learning', benchmark: 'Bench', profil: 'Profil', versions: 'Versions', reglages: 'Réglages' };
function renderShell() {
  const btn = ([k, l, ic]) => `<button data-act="go" data-arg="${k}" aria-label="${esc(l)}" title="${esc(l)}">${icon(ic)}<span>${RAIL_LABEL[k] || l}</span></button>`;
  $('#nav').innerHTML = NAV_MAIN.map(btn).join('') + '<div class="group" aria-hidden="true"></div>' + NAV_SECOND.map(btn).join('');
  $('#tabbar').innerHTML = TABS.map(([k, l, ic]) => `<button data-act="${k === 'more' ? 'open-more' : 'go'}" data-arg="${k}"><svg aria-hidden="true"><use href="#${ic}"/></svg>${l}</button>`).join('');
  $('#more-sheet').innerHTML = `<div class="grab"></div>${NAV_MAIN.filter(([k]) => !TABS.some(([t]) => t === k)).concat(NAV_SECOND).map(([k, l, ic]) => `<button class="item" data-act="go" data-arg="${k}">${icon(ic)}<span class="grow">${l}</span>${icon('i-arrow')}</button>`).join('')}`;
}
function renderRail() {
  const p = S.profile; const P = Pp(); const name = P ? P.value('id.name', '') : '';
  const initials = name ? name.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase() : '?';
  const A = S.photoAssets;
  $('#rail-foot').innerHTML = `<button class="avatar" data-act="go" data-arg="profil" aria-label="Profil${p ? ` v${p.version}, ${p.validated ? 'validé' : 'à valider'}` : ' : aucun'}" title="${p ? `Profil v${p.version} · ${p.validated ? 'validé' : 'à valider'}` : 'Aucun profil'}">${A ? `<img src="${A.circle}" alt="">` : esc(initials)}<span class="st${p && p.validated ? ' ok' : ''}"></span></button>`;
}
function renderTop() {
  const p = curPack(); const run = S.run && S.run.status === 'running';
  const crumb = S.view === 'pack' && p ? `<span>Application Packs</span>${icon('i-arrow')}<b>${esc(p.analysis.job_title)}</b>` : `<b>${esc(VIEW_TITLE[S.view] || (S.view === 'onboarding' ? 'Configuration' : 'PAI'))}</b>`;
  $('#topbar').innerHTML = `<span class="mbrand">PA<em>I</em></span><span class="crumb">${crumb}</span><span class="spacer"></span>
    ${run ? `<button class="chip accent live" data-act="go" data-arg="analyser"><span class="dot"></span>Analyse · ${S.run.steps.filter((s) => s.state === 'done').length}/${S.run.steps.filter((s) => s.state !== 'skip').length}</button>` : ''}
    <span class="store-note">${S.storage === 'db' ? `${icon('i-shield')} Données privées` : S.storage === 'memory' ? 'Non conservé' : ''}</span>
    ${modeBadge(AI.mode(), true)}`;
  const tl = $('#topline'); if (tl) { const on = !!(S.run && (run || S.view === 'analyser')); tl.hidden = !on; if (on) $('i', tl).style.width = `${runPct()}%`; }
  renderRail();
}
function renderToast() {
  let el = $('#toast');
  if (!S.toast) { if (el) el.remove(); return; }
  if (!el) { el = document.createElement('div'); el.id = 'toast'; el.className = 'toast'; el.setAttribute('role', 'status'); document.body.appendChild(el); }
  el.innerHTML = `${icon(S.toast.ic)}<span>${esc(S.toast.msg)}</span>`;
}
function setMore(open) {
  S.moreOpen = open; $('#scrim').classList.toggle('open', open); $('#more-sheet').classList.toggle('open', open);
}
let lastView = null;
function doRender() {
  let view = ALIASES[S.view] || S.view; if (!V[view]) view = 'accueil'; S.view = view;
  const inMain = (k) => k === view || (view === 'pack' && k === 'packs');
  $$('#nav button').forEach((b) => b.setAttribute('aria-current', inMain(b.dataset.arg) ? 'page' : 'false'));
  const tabViews = TABS.map(([k]) => k);
  $$('#tabbar button').forEach((b) => b.setAttribute('aria-current', inMain(b.dataset.arg) || (b.dataset.arg === 'more' && !tabViews.includes(view) && view !== 'pack') ? 'page' : 'false'));
  $$('#more-sheet button').forEach((b) => b.setAttribute('aria-current', b.dataset.arg === view ? 'page' : 'false'));
  renderTop();
  const main = $('#main');
  const active = document.activeElement; const activeId = active && active.id; const sel = active && active.selectionStart; const selEnd = active && active.selectionEnd;
  const scrollY = window.scrollY;
  main.innerHTML = V[view]();
  if (activeId) { const el = document.getElementById(activeId); if (el && el !== document.body && el.tagName !== 'BUTTON') { el.focus({ preventScroll: true }); try { if (sel !== undefined && sel !== null) el.setSelectionRange(sel, selEnd); } catch (e) { /* champ sans sélection */ } } }
  if (lastView !== view) { window.scrollTo(0, 0); lastView = view; main.classList.remove('enter'); void main.offsetWidth; main.classList.add('enter'); } else if (Math.abs(window.scrollY - scrollY) > 2) window.scrollTo(0, scrollY);
  fitSheets(); PDF.hydrate(main); autoGrow();
  if (S.profileFocus) { const el = document.getElementById(S.profileFocus); S.profileFocus = null; if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
}
// Le champ de commande grandit avec le texte collé (jusqu'à une limite), sans barre de défilement inutile.
function autoGrow() {
  const t = $('#cmd-input'); if (!t) return;
  t.style.height = 'auto'; t.style.height = `${Math.min(t.classList.contains('tall') ? 420 : 320, Math.max(t.classList.contains('tall') ? 200 : 56, t.scrollHeight))}px`;
}
