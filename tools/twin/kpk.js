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
  [[3.5,4.2,3,10.6,'g']],
  [[1.9,4.2,2.2,10.6,'g'],[5.9,4.2,2.2,10.6,'g']],
  [[4.4,4.2,1.2,10.6,'d']],
];
const STRAP_COL = { p:'#f1ead2', g:'#f2c14e', d:'#3a2a10' };
const STRAP_BODY = '#5d5641', STRAP_GOLD = '#f2c14e', STRAP_EDGE = '#0b0a07';
const STRAP_SHAPE = 'M0.5,15.5 L0.5,3.2 L2.8,0.8 L7.2,0.8 L9.5,3.2 L9.5,15.5 Z';
function strapSVG(i, h = 16){
  return `<svg class="strap" width="${h * 10 / 16}" height="${h}" viewBox="0 0 10 16" aria-label="${RANKS[i][1]}">` +
    `<path d="${STRAP_SHAPE}" fill="${i === 7 ? STRAP_GOLD : STRAP_BODY}" stroke="${STRAP_EDGE}" stroke-width=".9"/>` +
    STRAP_PARTS[i].map(([x, y, w, hh, c]) => `<rect x="${x}" y="${y}" width="${w}" height="${hh}" fill="${STRAP_COL[c]}"/>`).join('') +
    `</svg>`;
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
  9005:'двойник: перезарядка', 9006:'двойник: свой на линии → шаг вбок', 9007:'двойник: к последнему месту врага', 9008:'двойник: на огневую точку (держит район)',
};
function actName(n){
  if(n.aid == null || n.aid < 0) return '';
  const top = ACTION_NAMES[n.aid] || ('#' + n.aid);
  return n.aid2 != null && n.aid2 >= 0 ? `${top}: ${ACTION_NAMES[n.aid2] || '#' + n.aid2}` : top;
}
