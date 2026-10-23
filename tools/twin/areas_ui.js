// areas_ui.js — панель редактора территорий (23.10.2026), общая для quads.html и quads3d.html.
// Страница даёт: где рисовать панель, что делать при смене (перерисовать), при выборе инструмента.
// Модель и файл — areas_core.js.
'use strict';

const AE = { AM: null, active: -1, newCat: 'lane', lineCat: 'wall', pointCat: 'nook', brush: 2, onlyFree: false, wipeActive: true,
             onChange: () => {}, onTool: () => {}, el: null, msg: '' };

// кромка активной территории: пунктир из двух цветов, которых нет в категориях
const AE_DASH = [[255,47,208],[15,12,10]];

const AE_TOOLS = [
  ['paint', '✎ кисть', 'красить ноды в активную область (тянуть левой). [ ] — размер кисти'],
  ['wipe',  '◌ ластик', 'снять ноды: только с активной области (галочка ниже) или с любой незакреплённой'],
  ['fill',  '▦ площадка', 'клик — вся площадка 8 м (из запечки) в активную область: грубо и быстро'],
  ['pick',  '⚲ пипетка', 'клик по области — сделать активной'],
  ['merge', '⊕ влить', 'клик по области — влить её в активную'],
  ['line',  '╱ линия', 'клики — точки линии, Enter или двойной клик — закончить, Esc — бросить'],
  ['point', '• точка', 'клик — место, второй клик — куда смотрит'],
  ['erase_lp', '✕ линию/точку', 'клик рядом — удалить линию или точку'],
];

function aeMount(el, onChange, onTool){
  AE.el = el; AE.onChange = onChange; AE.onTool = onTool;
  const opt = (list, sel) => list.map(c => `<option value="${c[0]}"${c[0] === sel ? ' selected' : ''}>${c[1]}</option>`).join('');
  const q = new URLSearchParams(location.search), other = AREAS_SRC === 'auto' ? 'hand' : 'auto';
  q.set('areas', other);
  el.innerHTML = `
    <div class="row"><span class="muted">разметка: <b>${AREAS_SRC === 'auto' ? 'авточерновик (водораздел)' : 'ручная'}</b></span>
      <a href="?${q}" title="${other === 'auto' ? 'посмотреть, как режет автомат (quads/bake_areas.py)' : 'к ручной разметке'}">→ ${other === 'auto' ? 'авто' : 'ручная'}</a></div>
    <div class="row ae-tools">${AE_TOOLS.map(t => `<button data-t="${t[0]}" title="${t[2]}">${t[1]}</button>`).join('')}</div>
    <div class="row"><button id="ae-new" title="новая пустая область этой категории — сразу активная">＋ новая</button>
      <select id="ae-newcat" title="категория новой области">${opt(AREA_CATS, AE.newCat)}</select></div>
    <div class="row"><label title="радиус кисти, м">кисть <input type="number" id="ae-brush" value="${AE.brush}" min="0.4" max="15" step="0.4"> м</label>
      <label title="кисть не трогает ноды, уже отданные другим областям"><input type="checkbox" id="ae-free"> только пустые</label></div>
    <div class="row"><label title="ластик снимает ноды только с активной области, остальные не трогает"><input type="checkbox" id="ae-wipeact" checked> ластик — только активная</label>
      <span class="muted" title="«сохранить» закрепляет все области, кроме активной: их не трогают ни кисть, ни ластик. Открепить — в карточке">🔒 сохранить = закрепить</span></div>
    <div id="ae-active"></div>
    <div class="row"><label>линия <select id="ae-linecat">${opt(LINE_CATS, AE.lineCat)}</select></label>
      <label>точка <select id="ae-pointcat">${opt(POINT_CATS, AE.pointCat)}</select></label></div>
    <div class="row"><button id="ae-save" title="Ctrl+S — в levels/<уровень>_areas.json (прежняя — в areas_backup)">💾 сохранить</button>
      <button id="ae-dl" title="скачать файл разметки (если сервер не принимает)">⇩ файл</button>
      <button id="ae-undo" title="Ctrl+Z">↶</button></div>
    <p id="ae-status" class="muted"></p>
    <details id="ae-lint-box"><summary>Линт</summary><div id="ae-lint"></div></details>
    <details open><summary>Области</summary><div id="ae-list" class="ae-list"></div></details>`;
  el.querySelectorAll('.ae-tools button').forEach(b => b.onclick = () => AE.onTool(b.dataset.t));
  el.querySelector('#ae-new').onclick = () => { if(!AE.AM) return; AE.active = areasCreate(AE.AM, AE.newCat); AE.onTool('paint'); aeRender(true); };
  el.querySelector('#ae-newcat').onchange = e => AE.newCat = e.target.value;
  el.querySelector('#ae-brush').oninput = e => AE.brush = Math.max(0.4, +e.target.value || 2);
  el.querySelector('#ae-free').onchange = e => AE.onlyFree = e.target.checked;
  el.querySelector('#ae-wipeact').onchange = e => AE.wipeActive = e.target.checked;
  el.querySelector('#ae-linecat').onchange = e => AE.lineCat = e.target.value;
  el.querySelector('#ae-pointcat').onchange = e => AE.pointCat = e.target.value;
  el.querySelector('#ae-save').onclick = aeSave;
  el.querySelector('#ae-dl').onclick = () => AE.AM && areasDownload(AE.AM);
  el.querySelector('#ae-undo').onclick = aeUndo;
  el.querySelector('#ae-list').onclick = e => { const r = e.target.closest('[data-a]'); if(r){ AE.active = +r.dataset.a; aeRender(true); AE.onChange('select'); } };
  el.querySelector('#ae-lint').onclick = e => { const r = e.target.closest('[data-a]'); if(r){ AE.active = +r.dataset.a; aeRender(true); AE.onChange('select'); } };
}
// какие ноды под кистью можно трогать: закреплённые — нет; ластик «только активная» — только её ноды;
// кисть «только пустые» — пустые и свои
function aeFilter(nodes, wipe){
  const AM = AE.AM;
  return nodes.filter(k => {
    if(!areasFree(AM, k)) return false;
    const a = AM.node[k];
    if(wipe) return AE.wipeActive ? a === AE.active && a >= 0 : a >= 0;
    return !AE.onlyFree || a < 0 || a === AE.active;
  });
}
// активную закреплённую править нельзя — сначала открепить
function aeCanEdit(){
  const AM = AE.AM;
  if(AE.active < 0){ AE.msg = 'нет активной области: «＋ новая» или пипеткой'; aeRender(true); return false; }
  if(AM.areas[AE.active].locked){ AE.msg = 'активная закреплена 🔒 — «открепить» в карточке'; aeRender(true); return false; }
  return true;
}
function aeSetTool(t){ if(AE.el) AE.el.querySelectorAll('.ae-tools button').forEach(b => b.className = b.dataset.t === t ? 'on' : ''); }
function aeBrush(d){ AE.brush = Math.max(0.4, Math.min(15, +(AE.brush + d).toFixed(1))); const i = AE.el && AE.el.querySelector('#ae-brush'); if(i) i.value = AE.brush; }

async function aeSave(){
  if(!AE.AM) return;
  // сохранил — закрепил всё, кроме активной (её дорисовываешь дальше)
  areasLockAll(AE.AM, AE.active);
  try{ const b = await areasSave(AE.AM); AE.msg = `сохранено (${(b / 1024).toFixed(0)} КБ), всё кроме активной закреплено 🔒`; }
  catch(ex){ AE.msg = 'не сохранилось: ' + ex.message + '. Черновик цел в браузере; можно «⇩ файл».'; }
  aeRender(true);
}
function aeUndo(){ if(AE.AM && areasUndo(AE.AM)){ if(AE.active >= AE.AM.areas.length) AE.active = -1; AE.onChange('undo'); aeRender(true); } }

let aeAt = 0, aeTimer = null;
// перерисовка панели (не чаще 4 раз в секунду, если не force)
function aeRender(force){
  if(!AE.el || !AE.AM) return;
  const now = performance.now();
  if(!force && now - aeAt < 250){ if(!aeTimer) aeTimer = setTimeout(() => { aeTimer = null; aeRender(true); }, 260); return; }
  aeAt = now;
  const AM = AE.AM, $ = s => AE.el.querySelector(s);
  const L = areasLint(AM);
  $('#ae-status').textContent = (AE.msg ? AE.msg + ' · ' : '') + (AM.dirty ? 'есть несохранённое' : 'всё сохранено') +
    (AM.fromDraft ? ' (из черновика браузера)' : '') +
    (AM.noAuto ? ' · авточерновика нет: python3 quads/bake_areas.py levels/src/<ур> <ур>' : AM.fromAuto ? ' · авто: «сохранить» сделает его ручной разметкой' : '') + ` · размечено ${(100 * (1 - L.free / L.total)).toFixed(1)}% нод, областей ${AM.areas.length}, линий ${AM.lines.length}, точек ${AM.points.length}`;
  $('#ae-lint').innerHTML = L.issues.length ? L.issues.map(([t, nm, i]) => `<div class="ae-row" data-a="${i}">⚠ ${nm}: ${t}</div>`).join('')
    : '<div class="muted">замечаний нет</div>';
  $('#ae-lint-box').querySelector('summary').textContent = `Линт${L.issues.length ? ' · ' + L.issues.length : ''}`;
  const sw = i => { const c = areasColor(AM, i); return `<i class="ae-sw" style="background:rgb(${c.map(Math.round)})"></i>`; };
  $('#ae-list').innerHTML = AM.areas.map((a, i) => `<div class="ae-row${i === AE.active ? ' on' : ''}" data-a="${i}">${sw(i)}${a.locked ? '🔒 ' : ''}${areasLabel(AM, i)}<span class="muted"> · ${a.n}</span></div>`).join('')
    || '<div class="muted">пусто — «＋ новая» и кистью</div>';
  const act = $('#ae-active');
  if(AE.active < 0 || !AM.areas[AE.active]){ act.innerHTML = '<p class="muted">активной области нет</p>'; return; }
  const a = AM.areas[AE.active], cat = catOf(AREA_CATS, a.cat);
  if(act.dataset.id !== String(a.id) || act.dataset.lock !== String(!!a.locked) || force){
    act.dataset.id = a.id; act.dataset.lock = !!a.locked;
    act.innerHTML = `<div class="row">${sw(AE.active)}<b>#${a.id}</b>
        <input id="ae-name" placeholder="имя (как позывной: «Длинный», «Бойлерная»)" value="${a.name.replace(/"/g, '&quot;')}" style="flex:1;min-width:120px"></div>
      <div class="row"><select id="ae-cat">${AREA_CATS.map(c => `<option value="${c[0]}"${c[0] === a.cat ? ' selected' : ''}>${c[1]}</option>`).join('')}</select>
        <span class="muted" id="ae-n">${a.n} нод ≈ ${(a.n * 0.49).toFixed(0)} м²</span>
        <button id="ae-lock" title="закреплённую не трогают кисть, ластик, площадка и «влить»">${a.locked ? '🔓 открепить' : '🔒 закрепить'}</button>
        <button id="ae-del" title="удалить область (ноды станут пустыми; Ctrl+Z вернёт)">удалить</button></div>
      <p class="muted" id="ae-hint">${cat[3]}</p>
      <input id="ae-note" placeholder="заметка: чем место опасно / полезно" value="${a.note.replace(/"/g, '&quot;')}" style="width:100%">`;
    act.querySelector('#ae-name').oninput = e => { a.name = e.target.value; areasTouch(AM); aeRender(); };
    act.querySelector('#ae-note').oninput = e => { a.note = e.target.value; areasTouch(AM); };
    act.querySelector('#ae-cat').onchange = e => { a.cat = e.target.value; areasTouch(AM); act.querySelector('#ae-hint').textContent = catOf(AREA_CATS, a.cat)[3]; AE.onChange('cat'); aeRender(true); };
    act.querySelector('#ae-lock').onclick = () => { a.locked = !a.locked; areasTouch(AM); AE.msg = ''; aeRender(true); };
    act.querySelector('#ae-del').onclick = () => { areasDelete(AM, AE.active); AE.active = -1; AE.onChange('delete'); aeRender(true); };
  } else {
    act.querySelector('#ae-n').textContent = `${a.n} нод ≈ ${(a.n * 0.49).toFixed(0)} м²`;
  }
}

// общие стили панели (одни на обе страницы)
document.head.insertAdjacentHTML('beforeend', `<style>
  .ae-tools button{padding:3px 6px}
  .ae-list{max-height:260px;overflow-y:auto}
  .ae-row{display:flex;align-items:center;gap:6px;padding:2px 4px;cursor:pointer;color:var(--ink-2);font-size:12.5px;border-radius:2px}
  .ae-row:hover{background:var(--panel-hi)} .ae-row.on{background:var(--rust-deep);color:var(--ink)}
  .ae-sw{display:inline-block;width:10px;height:10px;border-radius:1px;flex:none}
  #ae-active input{background:var(--panel-hi);color:var(--ink);border:1px solid var(--rule-hi);border-radius:2px;font:12.5px var(--f-label);padding:2px 5px}
  #ae-active p{margin:4px 0}
</style>`);
