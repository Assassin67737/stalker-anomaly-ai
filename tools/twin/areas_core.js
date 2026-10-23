// areas_core.js — разметка ТЕРРИТОРИЙ руками (23.10.2026), общая для quads.html (2D) и quads3d.html (3D).
//
// Идея юзера: не квадраты, а гибкие площадные территории — форма по месту (вдоль стен, коридоры, дворы, крыши),
// у каждой категория; плюс линии (полоса вдоль стены, ось улицы, направление подхода) и точки (ниша, окно, угол).
// Область = набор нод навмеша любой формы (нода 0.7 м — форма какая угодно, хоть треугольник).
// Файл: levels/<уровень>_areas.json — пишет server.py (POST /areas/<уровень>), прежняя версия → levels/areas_backup/.
// Каждое изменение ещё и черновиком в браузере: сервер лёг или вкладку закрыл — нарисованное не пропадёт.
'use strict';

// категории: id, подпись, цвет, подсказка (что это тактически)
const AREA_CATS = [
  ['open',     'открытое',        [196,170,100], 'голое место: видно отовсюду, двигаться только бегом и прикрывшись'],
  ['yard',     'двор / площадка', [150,160,110], 'ограниченное открытое: стены вокруг, видно из окон и проходов'],
  ['lane',     'полоса у стены',  [110,170,210], 'прижаться и идти: укрытие с одной стороны'],
  ['corridor', 'коридор / улица', [120,140,190], 'длинное узкое: простреливается вдоль'],
  ['room',     'комната',         [180,140,200], 'закрыто со всех сторон, вход — через проходы'],
  ['choke',    'проход / дверь',  [230,90,70],   'воронка: решается бой, задерживаться нельзя'],
  ['stairs',   'лестница',        [230,170,60],  'связь этажей, уязвимо сверху и снизу'],
  ['height',   'высота / крыша',  [240,220,120], 'видит много — занять; занята врагом — не лезть в лоб'],
  ['cover',    'укрытое',         [90,160,100],  'много укрытий, можно сидеть'],
  ['dead',     'мёртвое пространство', [70,110,90], 'не простреливается с ключевых мест (под склоном, за насыпью)'],
  ['under',    'подземное',       [150,110,200], 'тоннель, подвал'],
  ['other',    'другое',          [160,160,160], ''],
];
const LINE_CATS = [
  ['wall',     'вдоль стены',     [110,170,210]],
  ['axis',     'ось / центр',     [240,220,90]],
  ['approach', 'направление подхода', [230,90,70]],
  ['sight',    'линия огня / обзора', [255,140,80]],
];
const POINT_CATS = [
  ['nook',     'ниша / укрытие',  [120,220,120]],
  ['window',   'окно / бойница',  [120,200,255]],
  ['corner',   'угол (заглянуть)', [255,210,90]],
  ['door',     'дверь / проход',  [255,110,90]],
  ['post',     'пост / огневая',  [255,255,255]],
];
const catOf = (list, id) => list.find(c => c[0] === id) || list[list.length - 1];

function areasNew(LV){
  return { LV, node: new Int32Array(LV.nq.length).fill(-1), areas: [], lines: [], points: [], undo: [], stroke: null,
           dirty: false, savedAt: 0, nextId: 1 };
}

// ─── правка ─────────────────────────────────────────────────────────────────────────
function areasCreate(AM, cat){
  const a = { id: AM.nextId++, name: '', cat: cat || 'other', note: '', n: 0, locked: false };
  AM.areas.push(a); areasTouch(AM); return AM.areas.length - 1;
}
// мазок: всё, что изменится между begin и end, отменяется одним Ctrl+Z
function areasBegin(AM){ AM.stroke = []; }
function areasEnd(AM){ if(AM.stroke && AM.stroke.length) AM.undo.push({ kind: 'paint', ops: AM.stroke }); AM.stroke = null; }
// покрасить ноды в область idx (−1 = стереть)
function areasPaint(AM, nodes, idx){
  let changed = 0;
  for(const k of nodes){
    const was = AM.node[k]; if(was === idx) continue;
    if(AM.stroke) AM.stroke.push(k, was);
    if(was >= 0) AM.areas[was].n--;
    if(idx >= 0) AM.areas[idx].n++;
    AM.node[k] = idx; changed++;
  }
  if(changed) areasTouch(AM);
  return changed;
}
function areasUndo(AM){
  const u = AM.undo.pop(); if(!u) return false;
  if(u.kind === 'paint'){
    for(let i = u.ops.length - 2; i >= 0; i -= 2){
      const k = u.ops[i], was = u.ops[i+1], now = AM.node[k];
      if(now >= 0) AM.areas[now].n--; if(was >= 0) AM.areas[was].n++;
      AM.node[k] = was;
    }
  } else if(u.kind === 'restore'){ const keep = AM.undo; Object.assign(AM, areasParse(AM.LV, u.snap)); AM.undo = keep; }
  areasTouch(AM); return true;
}
// крупные операции (склеить, удалить) — отмена через снимок
function areasSnapshot(AM){ AM.undo.push({ kind: 'restore', snap: areasSerialize(AM) }); }
function areasMerge(AM, from, into){
  if(from === into || from < 0 || into < 0) return;
  areasSnapshot(AM);
  for(let k = 0; k < AM.node.length; k++) if(AM.node[k] === from) AM.node[k] = into;
  AM.areas[into].n += AM.areas[from].n; AM.areas[from].n = 0;
  areasDrop(AM, from);
}
function areasDelete(AM, idx){
  areasSnapshot(AM);
  for(let k = 0; k < AM.node.length; k++) if(AM.node[k] === idx) AM.node[k] = -1;
  areasDrop(AM, idx);
}
// убрать область из списка и сдвинуть номера нод
function areasDrop(AM, idx){
  AM.areas.splice(idx, 1);
  for(let k = 0; k < AM.node.length; k++) if(AM.node[k] > idx) AM.node[k]--;
  for(const p of AM.points) if(p.area > idx) p.area--; else if(p.area === idx) p.area = -1;
  areasTouch(AM);
}
// черновик — не на каждый мазок (сериализация всех нод), а через 1.5 с тишины
function areasTouch(AM){ AM.dirty = true; clearTimeout(AM.draftT); AM.draftT = setTimeout(() => areasDraft(AM), 1500); }

// ─── файл ───────────────────────────────────────────────────────────────────────────
function areasSerialize(AM){
  const nodes = AM.areas.map(() => []);
  for(let k = 0; k < AM.node.length; k++) if(AM.node[k] >= 0) nodes[AM.node[k]].push(k);
  return { level: AM.LV.name, version: 1, savedAt: Date.now(), nextId: AM.nextId,
    areas: AM.areas.map((a, i) => ({ id: a.id, name: a.name, cat: a.cat, note: a.note, locked: !!a.locked, nodes: rle(nodes[i]) })),
    lines: AM.lines, points: AM.points };
}
// ноды области — отрезками [начало, длина]: соседние ноды навмеша часто идут подряд
function rle(ids){ const out = []; for(const k of ids){ const l = out[out.length - 1]; if(l && l[0] + l[1] === k) l[1]++; else out.push([k, 1]); } return out; }
function areasParse(LV, j){
  const AM = areasNew(LV);
  AM.nextId = j.nextId || 1; AM.lines = j.lines || []; AM.points = j.points || []; AM.savedAt = j.savedAt || 0;
  for(const a of j.areas || []){
    const idx = AM.areas.push({ id: a.id, name: a.name || '', cat: a.cat || 'other', note: a.note || '', n: 0, locked: !!a.locked }) - 1;
    for(const [s, l] of a.nodes || []) for(let k = s; k < s + l && k < AM.node.length; k++){ AM.node[k] = idx; AM.areas[idx].n++; }
    AM.nextId = Math.max(AM.nextId, a.id + 1);
  }
  return AM;
}
const draftKey = AM => 'varka_areas_draft_' + AM.LV.name;
function areasDraft(AM){ try{ localStorage.setItem(draftKey(AM), JSON.stringify(areasSerialize(AM))); }catch(_){} }
// какой источник смотрим: ?areas=auto — авточерновик водораздела (quads/bake_areas.py), иначе ручная разметка
const AREAS_SRC = new URLSearchParams(location.search).get('areas') === 'auto' ? 'auto' : 'hand';
// файл с сервера; черновик браузера новее — берём его (несохранённое)
async function areasLoad(LV){
  if(AREAS_SRC === 'auto'){
    // авточерновик: без черновика браузера; «сохранить» запишет его как ручную разметку — дальше править
    try{ const r = await fetch(`levels/${LV.name}_areas_auto.json?t=${Date.now()}`);
      if(r.ok){ const AM = areasParse(LV, await r.json()); AM.fromAuto = true; return AM; } }catch(_){}
    const AM = areasNew(LV); AM.fromAuto = true; AM.noAuto = true; return AM;
  }
  let file = null, draft = null;
  try{ const r = await fetch(`levels/${LV.name}_areas.json?t=${Date.now()}`); if(r.ok) file = await r.json(); }catch(_){}
  try{ draft = JSON.parse(localStorage.getItem('varka_areas_draft_' + LV.name) || 'null'); }catch(_){}
  if(draft && (!file || (draft.savedAt || 0) > (file.savedAt || 0) + 1000)){
    const AM = areasParse(LV, draft); AM.dirty = true; AM.fromDraft = true; return AM;
  }
  return file ? areasParse(LV, file) : areasNew(LV);
}
// закрепить всё, кроме правящейся сейчас (23.10, юзер: сохранил — «отныне ваниль», ластик и кисть не трогают)
function areasLockAll(AM, except){ AM.areas.forEach((a, i) => { if(i !== except) a.locked = true; }); }
// можно ли трогать ноду k кистью/ластиком: закреплённые области неприкосновенны
function areasFree(AM, k){ const a = AM.node[k]; return a < 0 || !AM.areas[a].locked; }
async function areasSave(AM){
  const body = JSON.stringify(areasSerialize(AM));
  const r = await fetch(`/areas/${AM.LV.name}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });
  const j = await r.json().catch(() => ({}));
  if(!r.ok || !j.ok) throw new Error(j.error || `сервер ответил ${r.status} — перезапусти server.py (нужен приём /areas)`);
  AM.dirty = false; AM.savedAt = JSON.parse(body).savedAt; areasDraft(AM);
  return j.bytes;
}
function areasDownload(AM){
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(areasSerialize(AM))], { type: 'application/json' }));
  a.download = `${AM.LV.name}_areas.json`; a.click();
}

// ─── линт: что «так не бывает» ───────────────────────────────────────────────────────
function areasLint(AM){
  const LV = AM.LV, floors = AM.areas.map(() => new Set());
  let free = 0;
  for(let k = 0; k < AM.node.length; k++){
    const a = AM.node[k]; if(a < 0){ free++; continue; }
    floors[a].add(LV.quads[LV.nq[k]].floor);
  }
  const out = [];
  AM.areas.forEach((a, i) => {
    const nm = (a.locked ? '🔒 ' : '') + areasLabel(AM, i);
    if(a.n === 0) out.push(['пустая', nm, i]);
    else if(a.n < 6) out.push(['крошка (меньше 6 нод)', nm, i]);
    if(floors[i].size > 1 && a.cat !== 'stairs') out.push([`на ${floors[i].size} этажах (не лестница)`, nm, i]);
  });
  return { free, total: AM.node.length, issues: out };
}
function areasLabel(AM, i){ const a = AM.areas[i]; return `#${a.id} ${a.name || catOf(AREA_CATS, a.cat)[1]}`; }
// цвет области: цвет категории, чуть разный у соседних номеров (чтобы две «комнаты» рядом различались)
function areasColor(AM, i){
  const a = AM.areas[i], c = catOf(AREA_CATS, a.cat)[2], k = 0.82 + ((a.id * 37) % 7) * 0.05;
  return [Math.min(255, c[0] * k), Math.min(255, c[1] * k), Math.min(255, c[2] * k)];
}
