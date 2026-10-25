// kpk.js — общее для вьюверов (2D viewer.html и 3D viewer3d.html, 21.10.2026): группировки, нашивки,
// ранги и погоны, названия действий. Одно место — оба вьювера говорят одним языком и выглядят одинаково.
// Обычный скрипт (не модуль): всё ниже — глобальные имена, их видят и классический 2D, и модуль 3D.

// ─── группировки ─────────────────────────────────────────────────────────────────────────────
const FACTIONS = {
  stalker:'#4CAF50', bandit:'#FF9800', army:'#8BC34A', military:'#8BC34A',
  monolith:'#9C27B0', freedom:'#2196F3', csky:'#00BCD4',
  dolg:'#F44336', duty:'#F44336', killer:'#7986cb', zombied:'#607D8B',
  actor:'#FF6B6B', ecolog:'#26A69A', greh:'#EF9A9A', renegade:'#b0896a', isg:'#90a4ae',
};
function fcolor(comm){ return FACTIONS[comm] || '#aaa'; }
const FACTION_RU = { stalker:'Сталкеры', bandit:'Бандиты', army:'Военные', military:'Военные', monolith:'Монолит',
  freedom:'Свобода', csky:'Чистое Небо', dolg:'Долг', duty:'Долг', killer:'Наёмники', zombied:'Зомбированные',
  actor:'Ты', ecolog:'Экологи', greh:'Грех', renegade:'Ренегаты', isg:'ИИГ' };
const LEVEL_RU = { l01_escape:'Кордон', l02_garbage:'Свалка', l03_agroprom:'Агропром', l07_military:'Армейские склады',
  l09_deadcity:'Мёртвый город', l10_limansk:'Лиманск', l10_radar:'Радар', pripyat:'Припять (ЗП)' };
const levelName = n => LEVEL_RU[n] || n;
const END_RU = { eliminated:'сторона выбита', timeout:'вышло время', abort:'прерван', aborted:'прерван' };
const BEL_END = { clear:'чисто', away:'ушёл из района', seen:'увидели', dead:'убит', old:'вера устарела' };
function sqShort(sq){ return '#' + String(sq).slice(-3); }
// 26.10: ствол бойца — название из игры (АК-74М), класс — в подсказке. Названия нет (старый trace) — класс
function wpnHTML(sec, kind, name){
  const k = WEAPON_KIND[kind] || kind;
  if(!name) return `<span class="wpn" title="${sec || ''}">${k}</span>`;
  const safe = String(name).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]);
  return `<span class="wpn" title="${k} · ${sec || ''}">${safe}</span>`;
}
// 25.10: боец в списке — ник и хвост id (как у отрядов); полный id — в подсказке. Ника нет (старый trace) — id целиком
function nickHTML(id, name){
  if(!name) return `<span class="id">${id}</span>`;
  const safe = String(name).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]);
  return `<span class="nick" title="${safe} · npc ${id}">${safe}</span><span class="id short">${String(id).slice(-3)}</span>`;
}

// Нашивки группировок — из атласа игры (bake_ui.py → assets/factions/). Нет файла — цветной квадрат.
// Вьювер подписывается onPatchLoad(fn), чтобы перерисоваться, когда картинка догрузится.
const PATCH_FILE = { duty:'dolg', military:'army' };
const PATCHES = {}, patchListeners = [];
function onPatchLoad(fn){ patchListeners.push(fn); }
function patchFile(comm){ return PATCH_FILE[comm] || comm; }
function patchImg(comm){
  if(!comm) return null;
  const f = patchFile(comm);
  if(!(f in PATCHES)){
    const im = new Image();
    im.onload = () => patchListeners.forEach(fn => fn());
    im.onerror = () => { PATCHES[f] = null; };
    im.src = `assets/factions/${f}.png`;
    PATCHES[f] = im;
  }
  const im = PATCHES[f];
  return im && im.complete && im.naturalWidth ? im : null;
}
function patchHTML(comm, cls = 'patch'){
  return patchImg(comm) ? `<img class="${cls}" src="assets/factions/${patchFile(comm)}.png" alt="">`
                        : `<span class="${cls} none" style="background:${fcolor(comm)}33"></span>`;
}

// ─── ранги и погоны ──────────────────────────────────────────────────────────────────────────
// Ранги Anomaly (game_relations.ltx, rating). Погоны: лычки поперёк — младшие (бумажные),
// золото — старшие: широкая лычка, продольная, два просвета, золотой погон легенды.
const RANKS = [[3500,'новичок'],[6500,'стажёр'],[9000,'опытный'],[12000,'профессионал'],
               [14500,'ветеран'],[17500,'эксперт'],[27000,'мастер'],[Infinity,'легенда']];
const RANK_SHORT = ['нов','стаж','опыт','проф','вет','эксп','маст','лег'];
function rankIdx(r){ return RANKS.findIndex(([lim]) => (r || 0) < lim); }
function rankName(r){ return RANKS[rankIdx(r)][1]; }
function rankLetter(r){ return 'NTEPVXML'[rankIdx(r)]; }
// погон в клетке 10×16: [x, y, w, h, цвет]. Контраст (юзер 21.10: «плохо видно»): тело светлее фона панели,
// тёмный контур отделяет от светлой карты, лычки толстые — читаются и в 13 px.
const STRAP_PARTS = [
  [],
  [[1.5,11.6,7,2,'p']],
  [[1.5,11.6,7,2,'p'],[1.5,8.6,7,2,'p']],
  [[1.5,11.6,7,2,'p'],[1.5,8.6,7,2,'p'],[1.5,5.6,7,2,'p']],
  [[1.5,8.4,7,5.2,'g']],
  [[3.5,3.4,3,6.4,'g']],                         // эксперт: продольная короче — внизу мишень
  [[1.9,3.4,2.2,6.4,'g'],[5.9,3.4,2.2,6.4,'g']], // мастер: два просвета короче — внизу череп
  [[4.4,3.4,1.2,7.4,'d']],
];
const STRAP_COL = { p:'#f1ead2', g:'#f2c14e', d:'#3a2a10' };
// 24.10 юзер: золото на погоне плохо видно → тёмная обводка золотых лычек (как тень)
const STRAP_GOLD_EDGE = '#1c1406';
const STRAP_BODY = '#5d5641', STRAP_GOLD = '#f2c14e', STRAP_EDGE = '#0b0a07';
const STRAP_SHAPE = 'M0.5,15.5 L0.5,3.2 L2.8,0.8 L7.2,0.8 L9.5,3.2 L9.5,15.5 Z';
// Знаки старших (24.10 юзер): эксперт — пробитая мишень, мастер — череп, легенда — колосья опоясывают погон снизу.
// Остальным ничего. Примитивы общие для SVG (панели) и canvas (карта 2D): [вид, геометрия, заливка, обводка, толщина].
// Колосья выходят за клетку 10×16 — у svg overflow: visible, место под них — отступ в .strap.r7.
// 24.10 юзер: мишень и череп по силуэту не узнаются → эксперту скрещённые катаны «за спиной» (рукояти над плечами,
// концы снизу), мастеру — рожки сверху; ветерану — звёздочка над золотым квадратом (путали со стажёром).
// Задний слой (за погоном) — STRAP_BACK, передний — STRAP_MARKS.
const KATANA = (x0, y0, x1, y1) => {
  const dx = x1 - x0, dy = y1 - y0, L = Math.hypot(dx, dy), ux = dx / L, uy = dy / L, h = 3.2;   // h — длина рукояти
  const gx = x0 + ux * h, gy = y0 + uy * h;
  return [ ['path', `M${gx},${gy} L${x1},${y1}`, null, '#1c1406', 1.5],
           ['path', `M${gx},${gy} L${x1},${y1}`, null, '#dfe5ea', 0.85],
           ['path', `M${x0},${y0} L${gx},${gy}`, null, '#1c1406', 1.6],
           ['path', `M${x0},${y0} L${gx},${gy}`, null, '#6b1f1f', 1.0],
           ['path', `M${gx - uy * 1.1},${gy + ux * 1.1} L${gx + uy * 1.1},${gy - ux * 1.1}`, null, '#e0b23c', 0.75] ];
};
const STRAP_BACK = {
  5: [ ...KATANA(-2.6, -2.2, 11.4, 17.4), ...KATANA(12.6, -2.2, -1.4, 17.4) ],
  6: [ ['path', 'M2.2,1.9 C0.6,0.9 -0.1,-1.1 0.4,-3.4 C1.1,-1.9 2.4,-0.9 3.9,-0.4 Z', '#9b1d1d', '#1c1406', 0.4],
       ['path', 'M7.8,1.9 C9.4,0.9 10.1,-1.1 9.6,-3.4 C8.9,-1.9 7.6,-0.9 6.1,-0.4 Z', '#9b1d1d', '#1c1406', 0.4] ],
};
const STAR5 = (cx, cy, R) => 'M' + [...Array(10)].map((_, k) => {
  const r = k % 2 ? R * 0.45 : R, a = -Math.PI / 2 + k * Math.PI / 5;
  return (cx + Math.cos(a) * r).toFixed(2) + ',' + (cy + Math.sin(a) * r).toFixed(2);
}).join(' L') + ' Z';
const EAR = (x, y, a) => ['ell', [x, y, 0.55, 1.45, a], '#e8b93f', '#1c1406', 0.3];
const STRAP_MARKS = {
  4: [ ['path', STAR5(5, 5.4, 2.2), '#f2c14e', '#1c1406', 0.45] ],
  5: [ ['circ', [5, 12.6, 2.6], '#f1ead2', '#1c1406', 0.45],
       ['circ', [5, 12.6, 1.7], '#c0392b', null, 0],
       ['circ', [5, 12.6, 0.8], '#f1ead2', null, 0],
       ['path', 'M6.1,11.2 L7.3,10.3 M6.4,11.9 L7.6,12.1 M5.7,10.9 L5.9,9.7', null, '#1c1406', 0.35],
       ['circ', [5.9, 11.6, 0.55], '#120d05', null, 0] ],
  6: [ ['path', 'M2.4,12.3 C2.4,9.4 7.6,9.4 7.6,12.3 C7.6,13.4 7,13.9 6.6,14.1 L6.6,15.2 L3.4,15.2 L3.4,14.1 C3,13.9 2.4,13.4 2.4,12.3 Z',
         '#efe6cf', '#1c1406', 0.45],
       ['circ', [3.95, 12.25, 0.78], '#120d05', null, 0],
       ['circ', [6.05, 12.25, 0.78], '#120d05', null, 0],
       ['path', 'M5,12.9 L4.55,13.75 L5.45,13.75 Z', '#120d05', null, 0],
       ['path', 'M4.2,14.3 L4.2,15.2 M5,14.3 L5,15.2 M5.8,14.3 L5.8,15.2', null, '#120d05', 0.3] ],
  7: [ ['path', 'M5,17.6 C1.2,17.4 -1.6,14.6 -1.6,9.4 M5,17.6 C8.8,17.4 11.6,14.6 11.6,9.4', null, '#8a6a1c', 0.55],
       EAR(-1.9, 8.2, 4), EAR(-1.7, 10.6, -12), EAR(-1.0, 12.9, -28), EAR(0.4, 15.0, -46), EAR(2.4, 16.7, -66),
       EAR(11.9, 8.2, -4), EAR(11.7, 10.6, 12),  EAR(11.0, 12.9, 28),  EAR(9.6, 15.0, 46),  EAR(7.6, 16.7, 66) ],
};
function markSVG([k, g, fill, stroke, sw]){
  const st = `fill="${fill || 'none'}"` + (stroke ? ` stroke="${stroke}" stroke-width="${sw}"` : '');
  if(k === 'circ') return `<circle cx="${g[0]}" cy="${g[1]}" r="${g[2]}" ${st}/>`;
  if(k === 'ell') return `<ellipse cx="${g[0]}" cy="${g[1]}" rx="${g[2]}" ry="${g[3]}" transform="rotate(${g[4]} ${g[0]} ${g[1]})" ${st}/>`;
  return `<path d="${g}" ${st} stroke-linecap="round"/>`;
}
function strapSVG(i, h = 16){
  return `<svg class="strap r${i}" width="${h * 10 / 16}" height="${h}" viewBox="0 0 10 16" overflow="visible" aria-label="${RANKS[i][1]}">` +
    (STRAP_BACK[i] || []).map(markSVG).join('') +
    `<path d="${STRAP_SHAPE}" fill="${i === 7 ? STRAP_GOLD : STRAP_BODY}" stroke="${STRAP_EDGE}" stroke-width=".9"/>` +
    STRAP_PARTS[i].map(([x, y, w, hh, c]) => `<rect x="${x}" y="${y}" width="${w}" height="${hh}" fill="${STRAP_COL[c]}"` +
      (c === 'g' ? ` stroke="${STRAP_GOLD_EDGE}" stroke-width=".55"` : '') + `/>`).join('') +
    (STRAP_MARKS[i] || []).map(markSVG).join('') +
    `</svg>`;
}
// то же на canvas (карта 2D): ctx уже сдвинут/отмасштабирован в клетку погона
function drawStrapMarks(ctx, i, back){
  for(const [k, g, fill, stroke, sw] of (back ? STRAP_BACK : STRAP_MARKS)[i] || []){
    ctx.beginPath();
    let p = null;
    if(k === 'circ') ctx.arc(g[0], g[1], g[2], 0, 2 * Math.PI);
    else if(k === 'ell') ctx.ellipse(g[0], g[1], g[2], g[3], g[4] * Math.PI / 180, 0, 2 * Math.PI);
    else p = new Path2D(g);
    if(fill){ ctx.fillStyle = fill; p ? ctx.fill(p) : ctx.fill(); }
    if(stroke){ ctx.strokeStyle = stroke; ctx.lineWidth = sw; ctx.lineCap = 'round'; p ? ctx.stroke(p) : ctx.stroke(); }
  }
}
// легенда погон: все 8 в ряд с подписью
function strapLegendHTML(h = 18){
  return `<div class="straps">${RANKS.map(([, name], i) => `<span title="${name}">${strapSVG(i, h)}${RANK_SHORT[i]}</span>`).join('')}</div>`;
}

// ─── бойцы ───────────────────────────────────────────────────────────────────────────────────
// класс оружия (kind из ltx) → коротко
const WEAPON_KIND = { w_pistol:'пист', w_smg:'ПП', w_shotgun:'дробь', w_rifle:'автомат', w_sniper:'снайп',
  w_marksman:'марксм', w_launcher:'гранатомёт', w_rpg:'РПГ', w_explosive:'граната', w_knife:'нож' };
function hpColor(h){ return h > 0.6 ? '#66bb6a' : h > 0.3 ? '#ffb74d' : '#ef5350'; }
function hpBarHTML(hp, w = 24){
  const v = Math.max(0, Math.min(1, hp || 0));
  return `<span class="hp" style="width:${w}px" title="здоровье ${Math.round(v * 100)}%"><i style="width:${v * 100}%;background:${hpColor(v)}"></i></span>`;
}
// Действия GOAP по номеру (stalker_ids, xr_actions_id, моды 188xxx, наши 99x/1882xx, двойник 900x)
const ACTION_NAMES = {
  88:'симуляция', 89:'бой', 90:'аномалия', 91:'опасность', 87:'смерть', 2:'подбирает', 3:'без симуляции',
  142:'труп рядом', 147:'помогает раненому', 192:'state_mgr', 194:'state_mgr', 307:'смарт-укрытие', 442:'после боя', 452:'анимточка',
  188111:'компаньон', 188112:'добивает', 188113:'опасность (скрипт)', 188114:'костёр', 188115:'ПАНИКА', 188116:'рация', 188117:'вертолёт',
  188118:'бой из укрытия', 188120:'ящик', 188202:'приказ', 188204:'приказ сквозь бой', 188206:'перегруппировка', 188208:'достреливает лежачего',
  188210:'вера: заглянуть / держать край',
  18803:'не стреляет: свои на линии', 18815:'поворот к врагу', 18816:'поворот',
  // внутри боя / опасности
  996:'поиск по вере', 995:'глушилка', 16:'целится', 17:'готовится', 19:'стреляет', 20:'отходит', 21:'в укрытие', 22:'выглядывает',
  23:'держит позицию', 24:'сближается', 25:'обходит', 26:'ищет врага', 27:'от гранаты', 28:'внезапная атака', 29:'стреляет вслепую',
  30:'к раненому', 32:'над раненым', 33:'добивает', 34:'VARKA: поиск/глушилка', 36:'тяжело ранен', 39:'кидает гранату',
  70:'неясная опасность', 71:'опасность с направления', 72:'граната', 73:'звук', 74:'в укрытие (опасн.)', 75:'озирается',
  76:'ищет (опасн.)', 77:'в укрытие', 78:'выглядывает', 79:'держит', 80:'обходит', 81:'ищет', 82:'от гранаты', 83:'ждёт взрыва', 84:'после взрыва', 85:'озирается', 86:'ищет',
  // двойник (sim/sim.lua)
  9001:'двойник: по приказу', 9002:'двойник: в укрытие', 9003:'двойник: бой из укрытия', 9004:'двойник: держит',
  9005:'двойник: перезарядка', 9006:'двойник: свой на линии → шаг вбок', 9007:'двойник: к последнему месту врага', 9008:'двойник: на огневую точку (держит район)', 9010:'двойник: замах гранатой', 9011:'двойник: уходит от гранаты', 9012:'двойник: ложится от гранаты', 188214:'граната: обернуться / спринт / лёжа',
};
function actName(n){
  if(n.aid == null || n.aid < 0) return '';
  const top = ACTION_NAMES[n.aid] || ('#' + n.aid);
  return n.aid2 != null && n.aid2 >= 0 ? `${top}: ${ACTION_NAMES[n.aid2] || '#' + n.aid2}` : top;
}
