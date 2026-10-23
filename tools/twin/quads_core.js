// quads_core.js — квадранты: данные и расчёт трассы (23.10.2026), общие для quads.html (2D) и quads3d.html.
// Данные — quads/bake_quads.py → levels/<имя>_quads.json, _quads_nodes.bin, _quads_vis.bin.
'use strict';

// уровни, у которых есть запечка квадрантов
async function quadsLevels(){
  const idx = await (await fetch('levels/index.json')).json();
  const ok = [];
  for(const n of idx) if((await fetch(`levels/${n}_quads.json`, {method:'HEAD'})).ok) ok.push(n);
  return ok;
}

async function quadsLoad(name){
  const [meta, Q, nb, vb] = await Promise.all([
    fetch(`levels/${name}.json`).then(r => r.json()),
    fetch(`levels/${name}_quads.json`).then(r => r.json()),
    fetch(`levels/${name}_quads_nodes.bin`).then(r => r.arrayBuffer()),
    fetch(`levels/${name}_quads_vis.bin`).then(r => r.arrayBuffer())]);
  // ноды: клетка картинки уровня (i, j), площадка, граница площадки, высота (запечка 23.10: 8 байт; старая — 6, без высоты)
  const st = nb.byteLength === meta.count * 8 ? 8 : 6, dv = new DataView(nb), n = nb.byteLength / st;
  const ni = new Int16Array(n), nj = new Int16Array(n), nq = new Uint16Array(n), ne = new Uint8Array(n), ny = new Float32Array(n);
  for(let k = 0; k < n; k++){
    const o = k * st, raw = dv.getUint16(o+4, true);
    ni[k] = dv.getInt16(o, true); nj[k] = dv.getInt16(o+2, true); nq[k] = raw & 0x7fff; ne[k] = raw >> 15;
    ny[k] = st === 8 ? dv.getInt16(o+6, true) / 20 : Q.quads[nq[k]].y;
  }
  // пары «видят друг друга»: vis = сколько из samples² лучей свободны
  const vd = new DataView(vb), vis = new Map(), sees = Q.quads.map(() => []);
  for(let k = 0; k < vb.byteLength / 5; k++){
    const a = vd.getUint16(k*5, true), b = vd.getUint16(k*5+2, true);
    vis.set(a*65536 + b, vd.getUint8(k*5+4)); sees[a].push(b); sees[b].push(a);
  }
  return { name, meta, Q, quads: Q.quads, ni, nj, nq, ne, ny, vis, sees, per: Q.samples * Q.samples, W: meta.w, H: meta.h };
}

function quadsVis(LV, a, b){
  if(a === b) return LV.per;
  return LV.vis.get(a < b ? a*65536 + b : b*65536 + a) || 0;
}

// угроза точно — одна площадка с весом 1; вероятная — площадки в круге (того же уровня высоты ±6 м),
// вес спадает к краю
function quadsSources(LV, threats){
  const out = [];
  for(const t of threats){
    if(t.kind === 'threat'){ out.push([t.q, 1]); continue; }
    const y = LV.quads[t.q].y;
    LV.quads.forEach((d, q) => { const r = Math.hypot(d.x - t.x, d.z - t.z);
      if(r <= t.r && Math.abs(d.y - y) < 6) out.push([q, 0.6 * (1 - 0.5 * r / t.r)]); });
  }
  return out;
}

// угроза площадки 0…1: насколько её видно с мест врага × (1 + kh × превышение врага / 8 м) × (1 − 0.3 × укрытость)
function quadsExposure(LV, threats, kh){
  const Q = LV.quads, expo = new Float32Array(Q.length);
  for(const [s, w] of quadsSources(LV, threats)){
    expo[s] = Math.max(expo[s], w);
    for(const q of LV.sees[s]){
      const up = Math.min(1, Math.max(0, Q[s].y - Q[q].y) / 8);
      const e = w * quadsVis(LV, s, q) / LV.per * (1 + kh * up) * (1 - 0.3 * Q[q].cover_hi);
      if(e > expo[q]) expo[q] = Math.min(1, e);
    }
  }
  return expo;
}

// Дейкстра по соседству площадок: шаг = длина × (1 + K × угроза площадки, куда шагаем)
function quadsRoute(LV, expo, a, b, K){
  const Q = LV.quads, n = Q.length, dist = new Float64Array(n).fill(Infinity), prev = new Int32Array(n).fill(-1);
  const heap = [[0, a]]; dist[a] = 0;
  const push = it => { heap.push(it); let i = heap.length - 1;
    while(i){ const p = (i - 1) >> 1; if(heap[p][0] <= heap[i][0]) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p; } };
  const pop = () => { const top = heap[0], last = heap.pop();
    if(heap.length){ heap[0] = last; let i = 0;
      for(;;){ const l = 2*i + 1, r = l + 1; let m = i;
        if(l < heap.length && heap[l][0] < heap[m][0]) m = l; if(r < heap.length && heap[r][0] < heap[m][0]) m = r;
        if(m === i) break; [heap[m], heap[i]] = [heap[i], heap[m]]; i = m; } }
    return top; };
  while(heap.length){
    const [d, u] = pop(); if(d > dist[u]) continue; if(u === b) break;
    for(const [v] of Q[u].nb){
      const nd = d + Math.hypot(Q[v].x - Q[u].x, Q[v].y - Q[u].y, Q[v].z - Q[u].z) * (1 + K * expo[v]);
      if(nd < dist[v]){ dist[v] = nd; prev[v] = u; push([nd, v]); }
    }
  }
  if(!isFinite(dist[b])) return null;
  const path = []; for(let v = b; v >= 0; v = prev[v]) path.unshift(v);
  let len = 0, under = 0, climb = 0;
  for(let i = 1; i < path.length; i++){
    const u = Q[path[i-1]], v = Q[path[i]], l = Math.hypot(v.x - u.x, v.y - u.y, v.z - u.z);
    len += l; if(expo[path[i]] > 0.2) under += l; climb += Math.max(0, v.y - u.y);
  }
  return { path, len, under, climb };
}

// палитры (общие шкалы 2D и 3D)
const QR_HEAT = [[40,38,30],[120,90,40],[214,138,53],[230,80,60],[255,230,200]];
const QR_COOL = [[30,60,40],[90,140,70],[169,199,127],[230,200,120],[210,85,66]];
const QR_FLOOR = [[150,140,110],[79,195,247],[255,138,101],[217,178,90],[206,147,216],[120,200,180]];
const QR_HEIGHT = [[30,40,60],[60,110,90],[170,170,90],[230,200,150],[255,250,235]];
const QR_VIS = [[60,70,50],[169,199,127],[230,240,200]];
const QR_UNDER = [150,110,200];   // ниже земли: тоннели, подвалы
// этаж от земли (bake_quads.py, 23.10): 0 — земля (1-й), выше 1, 2…, ниже −1, −2…
function quadsFloorName(f){ return f < 0 ? `${f} (под землёй)` : f === 0 ? '1-й (земля)' : `${f + 1}-й`; }
// диапазон этажей уровня (старая запечка — только floors, от 0)
function quadsFloorRange(LV){ return [LV.Q.floor_min ?? 0, LV.Q.floor_max ?? (LV.Q.floors - 1)]; }
function quadsRamp(t, stops){
  t = Math.max(0, Math.min(1, t));
  const k = t * (stops.length - 1), i = Math.min(stops.length - 2, Math.floor(k)), f = k - i;
  return stops[i].map((c, j) => Math.round(c + (stops[i+1][j] - c) * f));
}
// своя краска каждой площадке (золотой угол по оттенку)
function quadsHue(id){
  const h = ((id * 137.508) % 360) / 360, s = 0.45, l = 0.42 + (id % 3) * 0.07;
  const f = n => { const k = (n + h*12) % 12, a = s * Math.min(l, 1 - l); return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)))); };
  return [f(0), f(8), f(4)];
}
// цвет площадки q по режиму; sel — выбранная для «кого видит»
function quadsColor(LV, q, mode, expo, sel){
  const d = LV.quads[q];
  if(sel != null){
    if(q === sel) return [255,255,255];
    const v = quadsVis(LV, sel, q); return v ? quadsRamp(v / LV.per, QR_VIS) : [38,36,30];
  }
  switch(mode){
    case 'quad': return quadsHue(q);
    case 'floor': return d.floor < 0 ? QR_UNDER : QR_FLOOR[Math.min(d.floor, QR_FLOOR.length - 1)];
    case 'height': { const b = LV.meta.box; return quadsRamp((d.y - b[1]) / (b[4] - b[1]), QR_HEIGHT); }
    case 'cover': return quadsRamp(1 - d.cover_hi, QR_COOL);
    case 'sees': return quadsRamp(Math.log1p(d.sees) / Math.log1p(1500), QR_HEAT);
    default: return expo ? quadsRamp(expo[q], QR_HEAT) : [60,57,46];
  }
}
function quadsLegendHTML(mode){
  const g = (stops, a, b) => `<div class="leg"><i style="background:linear-gradient(90deg,${stops.map(c => `rgb(${c})`).join(',')})"></i>${a} → ${b}</div>`;
  return mode === 'threat' ? g(QR_HEAT, 'не видно врагу', 'на виду') :
    mode === 'cover' ? g(QR_COOL, 'закрыто', 'голо') : mode === 'sees' ? g(QR_HEAT, 'видит мало', 'видит много') :
    mode === 'floor' ? `<div class="leg"><i style="background:rgb(${QR_UNDER})"></i>под землёй</div>` +
      QR_FLOOR.map((c, i) => `<div class="leg"><i style="background:rgb(${c})"></i>${quadsFloorName(i)}</div>`).join('') :
    mode === 'height' ? g(QR_HEIGHT, 'низ', 'верх') :
    '<div class="leg">каждая площадка — свой цвет, тёмная кромка — граница</div>';
}
// строка «под курсором»
function quadsInfoHTML(LV, q, expo, sel){
  const d = LV.quads[q];
  return `<span>площадка</span><b>#${q}</b><span>этаж</span><b>${quadsFloorName(d.floor)}${d.roof ? ', под крышей' : ''}</b>` +
    `<span>высота</span><b>${d.y.toFixed(1)} м (${d.y0.toFixed(1)}…${d.y1.toFixed(1)})</b><span>площадь</span><b>${(d.n * LV.meta.cell ** 2).toFixed(0)} м²</b>` +
    `<span>укрытость</span><b>стоя ${(d.cover_hi * 100).toFixed(0)}%, сидя ${(d.cover_lo * 100).toFixed(0)}%</b>` +
    `<span>видит</span><b>${d.sees} площадок</b><span>соседей</span><b>${d.nb.length}</b>` +
    (expo ? `<span>угроза</span><b>${(expo[q] * 100).toFixed(0)}%</b>` : '') +
    (sel != null ? `<span>видно с #${sel}</span><b>${quadsVis(LV, sel, q)} из ${LV.per} лучей</b>` : '');
}
function quadsRouteHTML(route, plain, me, goal){
  if(!me || !goal) return ['<span>путь</span><b>поставь бойца ● и цель ⚑</b>', ''];
  if(!route) return ['<span>путь</span><b>не найден (цель недостижима)</b>', ''];
  const f = r => `${r.len.toFixed(0)} м, под взглядом ${r.under.toFixed(0)} м`;
  return [`<span>трасса</span><b>${f(route)}</b><span>прямой</span><b>${f(plain)}</b>` +
    `<span>площадок</span><b>${route.path.length}</b><span>подъём</span><b>${route.climb.toFixed(1)} м</b>`,
    'трасса квадрантов: ' + route.path.join(' → ')];
}
