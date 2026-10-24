-- sim.lua — бой в двойнике (21.10.2026), версия 0: песочница генерала.
--
-- Три этажа (см. разговор 21.10): генерал отдаёт приказ отряду, отряд — бойцам, а «дышит» за бойца
-- слой РЕФЛЕКСОВ, которые никто не приказывает: видишь врага — стреляй; прижали — в укрытие;
-- пусто в магазине — перезарядись; свой на линии — шаг вбок (НЕ на врага, как ванильный rx_ff);
-- не слипаться со своими.
--
-- ПОВОДОК приказа (g) — не переключатель «абсолютный/нет», а сколько рефлексу можно отклониться:
--   g=1 «любой ценой»   — рефлекс «в укрытие» молчит, стреляет на ходу;
--   g=2 «по обстановке» — прижали → укрытие ПО ДОРОГЕ к цели (не дальше от неё, чем стоял), отдышался → дальше;
--   g=3 «замысел»       — точка = район; укрытие где угодно рядом, держится, пока видит врага.
-- Поводок у каждого отрезка маршрута свой: «через дорогу — g1, дальше — g2».
--
-- Пуля — по движку (24.10, аудит сосуда doc/design/VESSEL_AUDIT.md): разброс движка + доля довёрнутых выстрелов,
-- подогнанная по 290 матчам (vessel.py); урон и hp — в единицах игры.

local W = require 'world'
local G = require 'grenade'
local H = require 'hear'
local F = require 'fire'

local S = {}
S.__index = S

local DT = 0.1                 -- шаг симуляции, с
local POS_EVERY = 0.5          -- как часто писать npc_pos (как в игре)
local HP = 111                 -- шкала hp в единицах урона (игра: урон / Δhp, медиана 111; ранг не влияет)
-- Скорость, м/с (m_stalker.ltx [stalker_movement_speeds], 24.10): настрой → поза → походка → { вперёд, вбок, назад }
-- относительно взгляда. Бой — danger: пятиться и идти боком втрое медленнее, чем бежать вперёд. free — спокойно
-- (вперёд, иначе как danger), panic — спринт 6.0 только вперёд.
local SPEED = {
	danger = { [false] = { walk = { 2.5, 2.0, 1.7 }, run = { 4.5, 2.0, 2.0 } },
	           [true]  = { walk = { 1.3, 1.2, 1.0 }, run = { 2.5, 2.0, 1.7 } } },
	free   = { [false] = { walk = { 1.1, 1.1, 1.1 }, run = { 3.0, 2.0, 2.0 } } },
	panic  = { [false] = { walk = { 2.5, 2.0, 1.7 }, run = { 6.0, 2.0, 2.0 } } },
}
local COS45 = math.sqrt(0.5)
-- скорость бойца f, идущего в сторону (dx, dz) (единичный вектор)
local function speed_of(f, dx, dz)
	local m = SPEED[f.mental or 'danger']
	local st = (m[f.cr] or SPEED.danger[f.cr])[f.how == 'run' and 'run' or 'walk']
	local c = dx * f.fx + dz * f.fz
	return st[c > COS45 and 1 or c < -COS45 and 3 or 2]
end
local EYE = { [false] = 1.6, [true] = 1.0 }     -- высота глаз: стоя / сидя
local CHEST = { [false] = 1.25, [true] = 0.75 }
-- Зрение: два режима движка (m_stalker.ltx [stalker_vision_free] / [stalker_vision_danger]). Спокойный — пока не знает
-- о враге (память пуста): дальше видит хуже, особенно краем глаза, через куст (0.7 < 0.73) — нет.
local VISION = {
	free   = { thr = 150, maxv = 1.11, minv = 0.25, lumf = 0.75, transp = 0.73, still = 0.8 },
	danger = { thr = 75,  maxv = 1.77, minv = 0.45, lumf = 0.65, transp = 0.6,  still = 0.2 },
}
local EYE_RANGE = 150
local SEE_RANGE = EYE_RANGE * 1.77            -- верхняя граница рамки (бой, без тумана)

-- Ствол: rate/mag/reload/max — как было; base — разброс ствола, ° (fire_dispersion_base: автомат 0.3–0.5,
-- СВД 0.08); dmg — медиана урона за попадание в игре (24.10, 290 матчей: автомат 39, ПП 28, пистолет 27,
-- дробовик 28 за попадание, снайперка 57); ap — бронебойность патрона (weapon_ammo.ltx k_ap: 5.45 ПС 0.4, 9×19 0.15,
-- 9×18 0.1, картечь 0.03, 7.62×54 ~0.6) — что прошьёт (материалы rays.c). Дальше max ствол не стреляет.
local WPN = {
	w_rifle   = { rate = 1.5,  mag = 30, reload = 2.6, dmg = 39, base = 0.4,  ap = 0.4, max = 250 },
	w_smg     = { rate = 1.7,  mag = 30, reload = 2.4, dmg = 28, base = 0.5,  ap = 0.15, max = 60 },
	w_pistol  = { rate = 0.65, mag = 12, reload = 1.8, dmg = 27, base = 0.6,  ap = 0.1, max = 45 },
	w_shotgun = { rate = 0.28, mag = 6,  reload = 3.5, dmg = 28, base = 1.5,  ap = 0.03, max = 35 },   -- дробь — одной «пулей», не сверено
	w_sniper  = { rate = 0.27, mag = 10, reload = 3.0, dmg = 57, base = 0.08, ap = 0.6, max = 800 },
}
-- Разброс стрелка, ° (ai_stalker_fire.cpp GetWeaponAccuracy: 1° × 0.8 (ранг зажат clamp(0,100) — у всех рангов
-- Anomaly 0.8) × (disp_* из m_stalker.ltx + 1)). Ранг на разброс НЕ влияет.
local DISP = {
	still = { [false] = 2.4,  [true] = 2.0 },     -- disp_stand_stand 2, disp_stand_crouch 1.5
	walk  = { [false] = 4.88, [true] = 3.68 },    -- disp_walk_stand 5.1, disp_walk_crouch 3.6
	run   = { [false] = 5.84, [true] = 4.64 },    -- disp_run_stand 6.3, disp_run_crouch 4.8
	zoom  = { [false] = 1.14, [true] = 0.99 },    -- снайперка с места: disp_stand_*_zoom 0.42 / 0.24
}
-- Урон за попадание относительно медианы ствола: квантили игры (p10 ≈ 0.31, p90 ≈ 1.62 у автомата; тяжёлый левый
-- хвост — конечности и броня). Линейно между узлами {доля, множитель}.
local DMG_Q = { { 0, 0.15 }, { 0.1, 0.32 }, { 0.25, 0.62 }, { 0.5, 1.0 }, { 0.75, 1.3 }, { 0.9, 1.65 }, { 1, 2.6 } }
local function dmg_mul(u)
	for i = 2, #DMG_Q do
		local a, b = DMG_Q[i - 1], DMG_Q[i]
		if u <= b[1] then return a[2] + (b[2] - a[2]) * (u - a[1]) / (b[1] - a[1]) end
	end
	return DMG_Q[#DMG_Q][2]
end
-- Анатомия (m_stalker.ltx [stalker_damage], hit_scale по костям; проверено по игре 24.10: урон / Δhp по костям даёт
-- те же множители — голова ×4.4, шея ×2.2, корпус ×1, бедро ×0.8, плечо ×0.7, голень ×0.56, кисть ×0.28, пальцы ×0.1).
-- Урон в колбэке hit игры — ДО множителя кости, поэтому dmg ствола (медиана 39 у автомата) × множитель зоны.
-- Какая кость: в игре доля зон у попавших пуль почти НЕ зависит от дистанции (290 матчей, первая кость пули):
-- корпус 37%, бедро 23%, таз/ключица 11%, плечо 9%, голень/предплечье 9%, пальцы 3%, голова 2.3%, кисть/стопа 1.4%,
-- шея 0.7%, прочие (default 0.75) 3.4% — пуля, попавшая в силуэт, ложится по костям «по площади». Берём зону по этой
-- таблице и проверяем лучом высоту зоны: закрыта укрытием — пуля ушла в укрытие. { доля, множитель, высота стоя, м }
local ZONES = {
	{ 'torso', 37.1, 1.0, 1.2 }, { 'thigh', 22.7, 0.8, 0.7 }, { 'pelvis', 11.2, 0.9, 0.95 }, { 'upperarm', 9.2, 0.7, 1.3 },
	{ 'calf', 9.1, 0.55, 0.35 }, { 'fingers', 3.0, 0.1, 1.1 }, { 'head', 2.3, 4.0, 1.65 }, { 'hand', 1.4, 0.25, 0.1 },
	{ 'neck', 0.7, 2.0, 1.5 }, { 'other', 3.4, 0.75, 1.0 },
}
local ZONE_SUM = 0
for _, z in ipairs(ZONES) do ZONE_SUM = ZONE_SUM + z[2] end
local function pick_zone()
	local r = math.random() * ZONE_SUM
	for _, z in ipairs(ZONES) do r = r - z[2]; if r <= 0 then return z end end
	return ZONES[1]
end

local function gauss()
	local u = math.max(1e-9, math.random())
	return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * math.random())
end

local function dist2(ax, az, bx, bz) return math.sqrt((ax - bx) ^ 2 + (az - bz) ^ 2) end

-- ─── создание ───────────────────────────────────────────────────────────────────────────────
-- scen: см. scen/*.lua. out — файл trace (jsonl).
function S.new(scen, world, out)
	local self = setmetatable({ scen = scen, w = world, t = 0, out = out, fighters = {}, squads = {},
		next_id = 1000, seq = 0, claims = {}, grenades = {}, gid = 1, gs = {} }, S)
	math.randomseed(scen.seed or 1)
	-- рычаги мира (физика и умение — калибруются): fov — полуугол обзора, see — скорость набора видимости,
	-- acc — множитель попадания, hp — урона до смерти; g_* и armor_* — гранаты (grenade.lua G.WORLD); h_* — слух (hear.lua)
	-- Цепочка огня (24.10, движок): голова в бою 270°/с (stalker_movement_manager_base m_danger_head_speed = 3π/2),
	-- огонь только в 22.5° (ai_aim_fire_angle), до первой очереди — прицеливание 0.5 с (g_ai_aim_inertia_time);
	-- ворота ствола (наши, varka_aim v2): препятствие у ствола ближе 8 м — не стрелять (gate_muzzle=false — стрелять,
	-- пуля в стену). Игра: от «увидел» до выстрела медиана 0.8 с, p75 2.3–2.6, без выстрела за 10 с 13–20%
	-- (ваниль C++ 0.3–0.4, наши действия 1–2.7). Сверка 60 боёв: aim_time 0 → 0.7 / 2.5 / 16% (ближе всего),
	-- 0.15 → 0.9 / 3.5, 0.5 → 1.6 / 6.0. Движок наводится по памяти и звуку, пока копится видимость, — в двойнике
	-- эту задержку уже даёт набор видимости, поэтому отдельного прицеливания после «увидел» нет (рычаг остаётся).
	local K = { fov = 80, see = 1, acc = 1, hp = HP, turn = 270, aim_deg = 22.5, aim_time = 0, gate_muzzle = true,
		lum = 0.08, fog = 0.9,                                  -- зрение: свет цели (подгонка по обнаружению), туман (w_*.ltx ~0.9)
		aim_q = 0.22, disp_k_still = 0.4, disp_k_move = 0.6,    -- пуля: S:bullet
		-- раненый (24.10, игра: xr_wounded hp_state 20|…, 330 ранений в 290 матчах): ниже wnd_hp доли hp — лежит, не
		-- ходит, не стреляет. Встаёт с шансом wnd_up через ~wnd_up_t с (игра: 17%, медиана 78 с — уже после боя),
		-- иначе истекает кровью за ~wnd_bleed с (лог-норма; не сверено отдельно от добивания — четверть смертей
		-- раненых в игре с убийцей дальше 24 м). Добивание — решение мозга (S:finish_wounded).
		-- Падение: wnd_fall с после ранения ещё стоит во весь рост и остаётся целью (оценщик + анимация падения) —
		-- очередь добивает (игра: 802 из 1127 погибших на последнем замере имели hp > 0.2).
		wnd_hp = 0.2, wnd_up = 0.2, wnd_up_t = 78, wnd_bleed = 30, wnd_fall = 2.5, kw = true }   -- wnd_fall: подгонка под 23% «ранен перед смертью», сверить стендом
	for k, v in pairs(G.WORLD) do K[k] = v end
	for k, v in pairs(H.WORLD) do K[k] = v end
	for k, v in pairs(F.WORLD) do K[k] = v end
	for k, v in pairs(scen.world or {}) do K[k] = v end
	K.fov_cos = math.cos(math.rad(K.fov))
	self.K = K
	-- доктрина гранат стороны: имя из G.DOCTRINE или { base = имя, поле = значение, … }
	self.doc = {}
	for _, side in ipairs { 'A', 'B' } do
		local spec = scen.sides[side].grenade or 'none'
		if type(spec) == 'string' then spec = { base = spec } end
		local d = {}
		for k, v in pairs(G.DOCTRINE[spec.base or 'none']) do d[k] = v end
		for k, v in pairs(spec) do if k ~= 'base' then d[k] = v end end
		self.doc[side] = d
		self.gs[side] = { thrown = 0, booms = 0, kills = 0, ff = 0, dodges = 0 }
	end
	-- мозг стороны: модуль с think(S, f) (brain_default — «как ваниль + VARKA в игре»; наученец — свой модуль)
	self.brain = {}
	for _, side in ipairs { 'A', 'B' } do
		local b = scen.sides[side].brain or 'brain_default'
		self.brain[side] = type(b) == 'table' and b or require(b)
	end
	for _, side in ipairs { 'A', 'B' } do
		for _, sq in ipairs(scen.sides[side].squads) do self:spawn_squad(side, sq) end
	end
	return self
end

function S:emit(ev, t)
	if not self.out then return end            -- серии без trace (sweep.lua): строки не собираем
	self.seq = self.seq + 1
	t.seq, t.t, t.ev = self.seq, math.floor(self.t * 1000 + 0.5), ev
	local parts = {}
	for k, v in pairs(t) do
		if v ~= v then v = 0 end                      -- NaN в JSON не бывает
		local s = type(v) == 'string' and ('"' .. v .. '"') or (math.type and math.type(v) == 'integer' and tostring(v))
			or (type(v) == 'number' and (v == math.floor(v) and string.format('%d', v) or string.format('%.4f', v)))
			or (type(v) == 'boolean' and (v and '1' or '0')) or 'null'
		parts[#parts + 1] = '"' .. k .. '": ' .. s
	end
	self.out:write('{' .. table.concat(parts, ', ') .. '}\n')
end

function S:spawn_squad(side, def)
	local w = self.w
	-- orders — расписание сценария ({at, route}); free — «ничейный» отряд сам гоняется за памятью о враге,
	-- отряд генерала (после первого приказа) держит место, пока не прикажут
	local sq = { id = self.next_id, side = side, comm = def.comm, members = {}, orders = def.orders or {}, oi = 0,
		free = def.free ~= false, name = def.name }
	self.next_id = self.next_id + 1
	self.squads[#self.squads + 1] = sq
	local c = w:node_at(def.at.x, def.at.y, def.at.z)
	local cand = w:around(c, 6)
	for k = 1, def.n do
		-- места в отряде — через 2.5 м друг от друга (не слипаться с рождения)
		local node
		for _, it in ipairs(cand) do
			local ok = true
			local x, _, z = w:xyz(it[1])
			for _, m in ipairs(sq.members) do if dist2(x, z, m.x, m.z) < 2.5 then ok = false; break end end
			if ok then node = it[1]; break end
		end
		node = node or c
		local x, y, z = w:xyz(node)
		local wk = def.wpn[(k - 1) % #def.wpn + 1]
		local f = { id = self.next_id, sq = sq, side = side, comm = def.comm,
			rank = self.K.rank or def.ranks and def.ranks[k] or def.rank or 5000, prone = false,
			node = node, x = x, y = y, z = z, fx = 0, fz = 1, cr = false, hp = self.K.hp,
			gren = self.doc[side].count, gren_t = -1e9,
			wk = wk, wpn = WPN[wk], mag = WPN[wk].mag, reload_t = 0, fire_t = math.random() / WPN[wk].rate,
			seen = {}, mem = {}, sup = 0, act = 9004, path = nil, pi = 1, pos_t = math.random() * POS_EVERY,
			cover = nil, cover_t = 0 }
		self.next_id = self.next_id + 1
		sq.members[#sq.members + 1] = f
		self.fighters[#self.fighters + 1] = f
	end
end

-- ─── восприятие ─────────────────────────────────────────────────────────────────────────────
-- Зрение — как движок (24.10, VESSEL_AUDIT.md §8 шаг 6; visual_memory_manager.cpp + наш override зрения):
--   рамка:   полуугол fov (eye_fov 160 → 80°), дальность 265 м (бой: eye_range 150 × max_view_distance 1.77);
--   луч:     по материалам, проницаемость выше порога режима (кусты — rays.c);
--   набор:   +Δt(мс) × свет^0.65 × (1 + скорость цели) × (D − d)/D × ранг (0.55 новичок … 1.9 легенда), где D — дальность
--            зрения под этим углом: от 265 м в центре до 67.5 м на краю (min_view_distance 0.45); видно с порога 75;
--   потерял: набор обнуляется сразу, но видимый ещё still с режима остаётся видимым (still_visible_time 200 / 800 мс).
-- Травы в cform нет, зрение движка её не видит — заместитель «трава режет обзор» убран. Свет цели (lum) — рычаг:
-- день/ночь двойник не знает (подгонка по дистанциям обнаружения игры).
local function rank_mult(r)
	return r < 3500 and 0.55 or r < 6500 and 0.70 or r < 9000 and 0.90 or r < 12000 and 1.10 or r < 14500 and 1.25
		or r < 17500 and 1.45 or r < 27000 and 1.65 or 1.90
end

-- режим зрения бойца: бой, если знает о враге (память, слух, попадание), иначе спокойный
function S:vision(f) return (next(f.mem) or f.sup > 0) and VISION.danger or VISION.free end

function S:can_see(a, b)
	local V = self:vision(a)
	local dx, dz = b.x - a.x, b.z - a.z
	local d = math.sqrt(dx * dx + dz * dz)
	-- рамка: дальность режима, туман погоды (update_range_fov: × 1 / (1 + fog_density_factor 0.25 × fog))
	if d > EYE_RANGE * V.maxv / (1 + 0.25 * self.K.fog) then return false, d end
	if d > 3 and (dx * a.fx + dz * a.fz) / d < self.K.fov_cos then return false, d end
	local ex, ey, ez = a.x, a.y + EYE[a.cr], a.z
	-- лучи по материалам, как движок (Feel_Vision: проницаемость перемножается, видно выше порога режима): в бою куст
	-- 0.7 — видно (порог 0.6), спокойно — нет (0.73); два куста 0.49 — нет; рабица 0.95 — видно
	local th = V.transp
	if b.prone then return W.vis(ex, ey, ez, b.x, b.y + 0.3, b.z, th) > 0, d end
	return W.vis(ex, ey, ez, b.x, b.y + CHEST[b.cr], b.z, th) > 0 or W.vis(ex, ey, ez, b.x, b.y + EYE[b.cr] + 0.1, b.z, th) > 0, d
end

-- видит ли f врага e сейчас (для мозга): набор видимости дошёл до порога и луч есть — или ещё «видим» по
-- still_visible_time. Ответ: видно?, дистанция
function S:sees(f, e)
	if (f.seen[e.id] or 0) < 1 then return false, nil end
	local vis, d = self:can_see(f, e)
	if not vis and self.t - (f.seen_t and f.seen_t[e.id] or -99) <= self:vision(f).still then vis = true end
	return vis, d
end

function S:perceive(f)
	local K = self.K
	local V = self:vision(f)
	local lum = K.lum ^ V.lumf
	local rk = rank_mult(f.rank)
	local fog = 1 / (1 + 0.25 * K.fog)                         -- туман режет и рамку, и дальность под углом
	local maxv, minv = EYE_RANGE * V.maxv * fog, EYE_RANGE * V.minv * fog
	f.seen_t = f.seen_t or {}
	for _, e in ipairs(self.fighters) do
		if e.side ~= f.side and e.hp > 0 then
			local vis, d = self:can_see(f, e)
			local s = f.seen[e.id] or 0
			if vis then
				if s < 1 then
					local c = math.max(-1, math.min(1, ((e.x - f.x) * f.fx + (e.z - f.z) * f.fz) / math.max(d, 1e-3)))
					local D = (1 - math.acos(c) / math.rad(K.fov)) * (maxv - minv) + minv
					if D > d then
						s = math.min(1, s + DT * 1000 * lum * (1 + (e.v or 0)) * (D - d) / D * rk * K.see / V.thr)
					end
				end
				if s >= 1 then
					f.seen_t[e.id] = self.t
					f.mem[e.id] = { x = e.x, y = e.y, z = e.z, t = self.t }
				end
			elseif s >= 1 and self.t - (f.seen_t[e.id] or -99) <= V.still then
				-- ещё «видим» (still_visible_time): движок целится в настоящую кость
				f.mem[e.id] = { x = e.x, y = e.y, z = e.z, t = self.t }
			else
				s = 0
			end
			f.seen[e.id] = s
		end
	end
end


-- ─── рефлексы ───────────────────────────────────────────────────────────────────────────────
-- свой на линии огня: ближе цели и в пределах 1 м от луча (или вплотную, < 1.5 м)
function S:friend_in_line(f, t)
	local ax, az = t.x - f.x, t.z - f.z
	local L = math.sqrt(ax * ax + az * az)
	if L < 0.1 then return end
	for _, m in ipairs(self.fighters) do
		if m ~= f and m.side == f.side and m.hp > 0 then
			local px, pz = m.x - f.x, m.z - f.z
			local along = (px * ax + pz * az) / L
			if along > 0 and along < L and math.abs(px * az - pz * ax) / L < 1.0 then return m end
		end
	end
end



-- ─── движение ───────────────────────────────────────────────────────────────────────────────
function S:go(f, node, how)
	if not node then return false end                                 -- точка вне навмеша (node_at → nil)
	if f.dest_node == node and f.path then return true end
	if f.nopath == node and self.t < f.nopath_t then return false end   -- не долбить A* каждый шаг
	local p = self.w:path(f.node, node, 250000)
	if not p then f.nopath, f.nopath_t = node, self.t + 3; return false end
	f.path, f.pi, f.dest_node, f.how = p, 2, node, how
	f.dest = { self.w:xyz(node) }
	return true
end

function S:stop(f) f.path, f.dest, f.dest_node = nil, nil, nil end

function S:step_move(f)
	f.v = 0
	if not f.path then return end
	local x0, z0 = f.x, f.z
	if f.move_at then if self.t < f.move_at then return end; f.move_at = nil end   -- рывок от гранаты ещё не стартовал
	local w = self.w
	local left = DT                                  -- время шага, с (скорость зависит от направления — считаем по отрезкам)
	while left > 1e-6 and f.path do
		local n = f.path[f.pi]
		if not n then self:stop(f); break end
		local nx, ny, nz = w:xyz(n)
		local dx, dz = nx - f.x, nz - f.z
		local d = math.sqrt(dx * dx + dz * dz)
		local speed = d > 1e-6 and speed_of(f, dx / d, dz / d) * left or 0
		if d <= speed then
			f.x, f.y, f.z, f.node = nx, ny, nz, n
			left = left - (d > 1e-6 and left * d / speed or 0)
			f.pi = f.pi + 1
			if f.pi > #f.path then self:stop(f) end
		else
			f.x, f.z = f.x + dx / d * speed, f.z + dz / d * speed
			f.y = f.y + (ny - f.y) * (speed / d)
			if not f.target_vis and not f.look_hear then f.wx, f.wz = dx / d, dz / d end
			left = 0
		end
	end
	f.v = math.sqrt((f.x - x0) ^ 2 + (f.z - z0) ^ 2) / DT
end

-- доворот: взгляд (fx, fz) идёт к желаемому (wx, wz) не быстрее K.turn градусов в секунду
function S:turn(f)
	if not f.wx then return end
	local a0, a1 = math.atan2(f.fx, f.fz), math.atan2(f.wx, f.wz)
	local da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
	local step = math.rad(self.K.turn) * DT
	if math.abs(da) > step then da = da > 0 and step or -step end
	local a = a0 + da
	f.fx, f.fz = math.sin(a), math.cos(a)
end

-- ствол свободен у стрелка: первые 8 м (не дальше полпути) к груди цели — как varka_aim v2 в игре
function S:muzzle_clear(f, t)
	local hy = f.y + (f.cr and 1.0 or 1.5)
	local ty = t.y + (t.prone and 0.3 or CHEST[t.cr])
	local dx, dy, dz = t.x - f.x, ty - hy, t.z - f.z
	local d = math.sqrt(dx * dx + dy * dy + dz * dz)
	if d < 0.5 then return true end
	local k = math.min(8, d * 0.5) / d
	return W.clear(f.x, hy, f.z, f.x + dx * k, hy + dy * k, f.z + dz * k)
end

-- ─── огонь ──────────────────────────────────────────────────────────────────────────────────
-- Пуля (24.10, по движку + подгонка по игре, VESSEL_AUDIT.md §8 шаг 1):
--   1. довёрнут ли выстрел: с вероятностью aim_q (игра: 0.22) голова смотрит точно в цель; остальные — мимо при
--      любой дистанции (стреляет на довороте, цель уходит из-под прицела; движок жмёт, пока голова в 22.5°).
--   2. разброс движка (WeaponFire.cpp random_dir): угол α ~ N(0, разброс/3), обрезан ±3σ, в случайную сторону θ ∈ [0, π)
--      → плотность у центра ∝ 1/r, попадание падает как 1/d, а не 1/d². Разброс = ствол + стрелок (DISP) × disp_k
--      (подгонка: с места 0.4, на ходу 0.6 — σ 0.39° / 1.08°).
--   3. точка на силуэте (прицел — грудь): мимо силуэта (±0.22 м, рост 1.75 / сидя 1.1) — промах; на силуэте —
--      пуля из глаз в эту точку по материалам (rays_bullet): куст насквозь, доску автомат прошьёт, бетон — нет.
-- Игра (290 матчей, чистые выстрелы): с места 23–25% до 17 м, 18% к 30 м, 14% к 60 м, 10% к 87 м; на ходу 32 → 4%.
-- Ответ — множитель урона (доля скорости пули у цели × множитель кости), 0 — мимо или застряла; вторым — зона.
-- smul — множитель разброса (отдача, паника), accm — множитель доли довёрнутых (рычаги acc, acc_burst).
function S:bullet(f, t, d, smul, accm)
	local K, w = self.K, f.wpn
	if math.random() > K.aim_q * K.acc * (accm or 1) then return 0 end
	local moving = f.path ~= nil and (f.how or 'walk')
	local disp = w.base + (moving and DISP[moving][f.cr] or (f.wk == 'w_sniper' and DISP.zoom or DISP.still)[f.cr])
	local sig = math.rad(disp / 3 * (moving and K.disp_k_move or K.disp_k_still) * (smul or 1))
	local a = math.max(-3, math.min(3, gauss())) * sig
	local th = math.random() * math.pi
	local r = math.tan(a) * math.max(d, 0.5)
	local x, y = r * math.sin(th), (t.prone and 0.2 or CHEST[t.cr]) + r * math.cos(th)
	if math.abs(x) > 0.22 or y < 0 or y > (t.prone and 0.4 or t.cr and 1.1 or 1.75) then return 0 end
	if t.prone then return W.bullet(f.x, f.y + EYE[f.cr], f.z, t.x, t.y + y, t.z, w.ap), 'body', 1 end
	local z = pick_zone()
	local zy = z[4] * (t.cr and 0.63 or 1)       -- сидя силуэт 1.1 из 1.75
	return W.bullet(f.x, f.y + EYE[f.cr], f.z, t.x, t.y + zy, t.z, w.ap) * z[3], z[1], z[3]
end

-- урон пули: медиана ствола × квантиль игры
function S:bullet_dmg(f) return f.wpn.dmg * dmg_mul(math.random()) end

-- прицельный огонь по видимой цели (в панике — паника): очереди, отдача, ворота — fire.lua
function S:fire(f, t, d)
	return F.shoot(self, f, { t = t, x = t.x, y = t.y + CHEST[t.cr], z = t.z, d = d, mode = f.panic and 'panic' or 'aim' })
end

-- огонь по точке (подавление; в панике — паника): точка из знания, не из правды
function S:fire_at(f, pt, mode)
	local d = math.sqrt((pt.x - f.x) ^ 2 + (pt.z - f.z) ^ 2)
	if d < 1 then return end
	local dx, dz = (pt.x - f.x) / d, (pt.z - f.z) / d
	f.wx, f.wz = dx, dz
	if self:friend_in_line(f, pt) then return end
	return F.shoot(self, f, { x = pt.x, y = (pt.y or f.y) + 1.25, z = pt.z, d = d, mode = f.panic and 'panic' or mode })
end

-- урон по t от f (пуля или граната); true — убит
function S:damage(t, f, dmg, d, gren, zn, zk)
	if t.prone_wnd and not gren then dmg = math.max(dmg, 1000) end   -- движок: по лежачему раненому hit_power = 1000
	t.hp = t.hp - dmg
	t.sup = t.sup + 1
	-- hit-память движка: по мне попали — знаю кто и где он был (точно)
	if f ~= t and f.side ~= t.side then t.mem[f.id] = { x = f.x, y = f.y, z = f.z, t = self.t, hit = true } end
	if not gren then
		self.nhits = (self.nhits or 0) + 1
		self.hit_d = self.hit_d or {}
		self.hit_d[#self.hit_d + 1] = d
		self.first_hit = self.first_hit or self.t
	end
	-- amount — как в игре: ДО множителя кости (колбэк hit движка); потеря здоровья — dmg
	self:emit('hit', { npc = t.id, sq = t.sq.id, who = f.id, wsq = f.sq.id, amount = dmg / (zk or 1), d = d, saw = 1, bone = zn or 'body',
		dy = f.y - t.y, gren = gren and 1 or 0 })
	if t.hp > 0 and not t.wounded and t.hp <= self.K.wnd_hp * self.K.hp then self:wound(t) end
	if t.hp <= 0 then
		self:emit('death', { npc = t.id, sq = 0, comm = t.comm, killer = f.id, ksq = f.sq.id, rank = t.rank,
			gren = gren and 1 or 0, wnd = t.wounded and 1 or 0 })
		self:stop(t)
		t.dodge, t.windup, t.throw, t.prone, t.wounded, t.prone_wnd = nil, nil, nil, false, nil, nil
		self.first_death = self.first_death or self.t
		return true
	end
end

-- ─── раненый ────────────────────────────────────────────────────────────────────────────────
local function lognorm(med, s) return med * math.exp(s * gauss()) end

function S:wound(t)
	self:stop(t)
	t.wounded, t.wnd_t, t.cr = true, self.t, false            -- лёжа — после падения (wounded_step)
	t.dodge, t.windup, t.throw, t.burst, t.panic = nil, nil, nil, 0, nil
	if math.random() < self.K.wnd_up then t.wnd_up_at = self.t + lognorm(self.K.wnd_up_t, 0.3); t.wnd_die_at = nil
	else t.wnd_die_at = self.t + lognorm(self.K.wnd_bleed, 0.8); t.wnd_up_at = nil end
	self:emit('wounded', { npc = t.id, sq = t.sq.id, hp = t.hp / self.K.hp })
end

-- шаг раненого: истёк кровью / встал
function S:wounded_step(f)
	if not f.prone_wnd and self.t - f.wnd_t >= self.K.wnd_fall then
		f.prone_wnd, f.prone = true, true
		self:emit('wounded_down', { npc = f.id, sq = f.sq.id })
	end
	if f.wnd_die_at and self.t >= f.wnd_die_at then
		f.hp = 0
		self:emit('death', { npc = f.id, sq = 0, comm = f.comm, killer = f.id, ksq = f.sq.id, rank = f.rank, gren = 0, wnd = 1, bleed = 1 })
		f.prone, f.wounded, f.prone_wnd = false, nil, nil
		self.first_death = self.first_death or self.t
	elseif f.wnd_up_at and self.t >= f.wnd_up_at then
		f.wounded, f.prone, f.prone_wnd, f.wnd_up_at = nil, false, nil, nil
		f.hp = math.max(f.hp, 0.3 * self.K.hp)
		self:emit('wounded_up', { npc = f.id, sq = f.sq.id })
	end
end


-- ─── приказы отряду ─────────────────────────────────────────────────────────────────────────
-- Приказ = маршрут { {x, y, z, g}, … } (поводок g на каждом отрезке) + сигнал code (A/B/C или nil).
-- С сигналом приказ ждёт, пока генерал не скажет «A — пошли» (S:release).
local function route_str(r)
	local p = {}
	for _, s in ipairs(r) do p[#p + 1] = string.format('%.1f,%.1f,%.1f,%d', s.x, s.y or 0, s.z, s.g) end
	return table.concat(p, ';')
end

function S:order(sq, o)
	if o.code and not o.released then
		sq.waiting = o
		self:emit('order', { sq = sq.id, npc = 0, route = route_str(o.route), code = o.code, state = 'wait' })
		return
	end
	if sq.waiting == o then sq.waiting = nil end
	sq.order = o
	self:emit('order', { sq = sq.id, npc = 0, route = route_str(o.route), code = o.code or '', state = 'go' })
end

function S:release(code)
	for _, sq in ipairs(self.squads) do
		local o = sq.waiting
		if o and o.code == code then o.released = true; self:order(sq, o) end
	end
	for _, f in ipairs(self.fighters) do
		local o = f.pwait
		if o and o.code == code then o.released = true; self:order_npc(f, o) end
	end
end

-- Личный приказ бойцу: важнее приказа отряда, пока не выполнен; место — сама точка, без строя.
-- Выполнил — снова живёт приказом отряда (или держит, где стоит, если у отряда приказа нет).
function S:order_npc(f, o)
	o.personal = true
	if o.code and not o.released then
		f.pwait = o
		self:emit('order', { sq = f.sq.id, npc = f.id, route = route_str(o.route), code = o.code, state = 'wait' })
		return
	end
	if f.pwait == o then f.pwait = nil end
	f.porder = o
	self:emit('order', { sq = f.sq.id, npc = f.id, route = route_str(o.route), code = o.code or '', state = 'go' })
end

function S:hold_npc(f)
	f.porder, f.pwait = nil, nil
	f.hold_x, f.hold_z = f.x, f.z
	f.skip = f.sq.order                         -- приказ отряда для него снят: стоит, где поставили
	f.done = f.sq.order
	self:emit('order', { sq = f.sq.id, npc = f.id, route = '', code = '', state = 'hold' })
end

function S:hold(sq)
	sq.order, sq.waiting = nil, nil
	self:emit('order', { sq = sq.id, npc = 0, route = '', code = '', state = 'hold' })
end

function S:squad_tick(sq)
	while sq.orders[sq.oi + 1] and (sq.orders[sq.oi + 1].at or 0) <= self.t do
		sq.oi = sq.oi + 1
		self:order(sq, sq.orders[sq.oi])
	end
	-- приказ выполнен, когда все живые дошли до конца маршрута
	local o = sq.order
	if o then
		local all = true
		for _, m in ipairs(sq.members) do if m.hp > 0 and m.done ~= o then all = false end end
		if all then
			sq.order = nil
			self:emit('order', { sq = sq.id, npc = 0, route = '', code = '', state = 'done' })
		end
	end
end



-- ─── мозг бойца ─────────────────────────────────────────────────────────────────────────────




function S:last_mem(f)
	local best
	for _, m in pairs(f.mem) do if not best or m.t > best.t then best = m end end
	return best
end


-- ─── тело в шаге ────────────────────────────────────────────────────────────────────────────
-- Что тело делает само, без мозга: перезарядка идёт, замах гранаты доводится до броска (решил кинуть — тело
-- исполняет), прижатость затухает. true — тело занято (мозг в этот шаг не думает).
function S:body_step(f)
	if f.reload_t > 0 then
		f.reload_t = f.reload_t - DT
		if f.reload_t <= 0 then f.mag = f.wpn.mag end
	end
	f.sup = math.max(0, f.sup - DT * 0.5)
	if f.windup then
		f.windup = f.windup - DT
		if f.windup <= 0 then G.release(self, f) end
		return true
	end
end

-- ─── шаг и прогон ───────────────────────────────────────────────────────────────────────────
function S:alive(side)
	local n = 0
	for _, f in ipairs(self.fighters) do if f.side == side and f.hp > 0 then n = n + 1 end end
	return n
end

function S:snap(f)
	self:emit('npc_pos', { npc = f.id, sq = f.sq.id, px = f.x, py = f.y, pz = f.z, dx = f.fx, dz = f.fz,
		comm = f.comm, rank = f.rank, hp = math.max(0, f.hp / self.K.hp), wk = f.wk, wpn = f.wk, mag = f.mag,
		cr = f.cr and 1 or 0, prone = f.prone and 1 or 0, be = f.target or -1, bsee = f.target_vis and 1 or 0, aid = f.act, aid2 = -1,
		active = 1, wnd = f.prone_wnd and 1 or 0 })
end

-- Прогон по шагам: start → tick … (пока не вернёт причину конца) → finish. Живой режим (live.lua)
-- зовёт tick сам, в своём темпе и с паузами; run — всё разом, для серий.
function S:start()
	local sc = self.scen
	local sq = { A = {}, B = {} }
	for _, s in ipairs(self.squads) do sq[s.side][#sq[s.side] + 1] = s.id end
	self:emit('match_start', { id = sc.id, level = sc.level, limit = sc.limit, zx = sc.zone.x, zz = sc.zone.z,
		zr = sc.zone.r, a = table.concat(sq.A, ','), b = table.concat(sq.B, ','), sq = 0, npc = 0 })
	for _, s in ipairs(self.squads) do
		self:emit('squad', { sq = s.id, npc = 0, side = s.side, comm = s.comm, name = s.name or '', n = #s.members })
	end
	for _, f in ipairs(self.fighters) do self:snap(f) end
end

function S:tick()
	self.t = self.t + DT
	for _, s in ipairs(self.squads) do self:squad_tick(s) end
	if #self.grenades > 0 then G.update(self) end
	local every = self.pos_every or POS_EVERY
	for _, f in ipairs(self.fighters) do
		if f.hp > 0 and f.wounded then
			self:wounded_step(f)
			f.pos_t = f.pos_t - DT
			if f.pos_t <= 0 then f.pos_t = every; self:snap(f) end
		elseif f.hp > 0 then
			self:perceive(f)
			if not self:body_step(f) then self.brain[f.side].think(self, f) end
			self:step_move(f)
			self:turn(f)
			if self.K.h_on then H.step(self, f) end
			f.pos_t = f.pos_t - DT
			if f.pos_t <= 0 then f.pos_t = every; self:snap(f) end
		end
	end
	if self:alive('A') == 0 or self:alive('B') == 0 then return 'eliminated' end
	if self.t >= self.scen.limit then return 'timeout' end
end

function S:finish(reason)
	local sc = self.scen
	self:emit('match_end', { id = sc.id, reason = reason, dur = self.t, alive_a = self:alive('A'),
		alive_b = self:alive('B'), ctrl_a = 0, ctrl_b = 0, sq = 0, npc = 0 })
	return reason, self:alive('A'), self:alive('B')
end

function S:run()
	self:start()
	local reason
	repeat reason = self:tick() until reason
	return self:finish(reason)
end

return S
