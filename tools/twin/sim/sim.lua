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
-- Модель стрельбы — подгонка по ночному прогону 21.10 (128 боёв, night_report.py): попадание на
-- выстрел по дистанции и классу ствола, темп огня «пока видит врага», урон до смерти ~145.
-- Это отправная точка, калибровка «предсказал → сверил» — следующий шаг.

local W = require 'world'

local S = {}
S.__index = S

local DT = 0.1                 -- шаг симуляции, с
local POS_EVERY = 0.5          -- как часто писать npc_pos (как в игре)
local HP = 145                 -- урона до смерти (медиана ночи)
local SPEED = { run = 2.9, walk = 2.0, crouch = 1.2 }
local EYE = { [false] = 1.6, [true] = 1.0 }     -- высота глаз: стоя / сидя
local CHEST = { [false] = 1.25, [true] = 0.75 }
local FOV = math.cos(math.rad(75))              -- полуугол обзора 75°
local SEE_RANGE = 120

-- Попадание — модель-заместитель (21.10, после первого котла: «попадания — бред»):
--   p = pmax × доля разброса, попавшая в ВИДИМЫЙ силуэт цели
-- pmax — «умение попадать вообще» (ночь: на 0–35 м ~8% на выстрел у автомата — спрей, отдача, стрельба
-- на ходу); разброс σ — конус вокруг точки прицеливания, по классу ствола. Видимая часть силуэта —
-- три луча (ноги, грудь, голова): из-за укрытия торчит голова — попасть в 3 раза труднее.
-- Дальше max ствол не стреляет вовсе (как RANGE в varka_weapons): ПП со 100 м — не огонь, а шум.
local WPN = {
	w_rifle   = { rate = 1.5,  mag = 30, reload = 2.6, dmg = 24, pmax = 0.085, sigma = math.rad(0.30), max = 250 },
	w_smg     = { rate = 1.7,  mag = 30, reload = 2.4, dmg = 17, pmax = 0.09,  sigma = math.rad(0.45), max = 60 },
	w_pistol  = { rate = 0.65, mag = 12, reload = 1.8, dmg = 15, pmax = 0.19,  sigma = math.rad(0.66), max = 45 },
	w_shotgun = { rate = 0.28, mag = 6,  reload = 3.5, dmg = 14, pmax = 0.80,  sigma = math.rad(1.6),  max = 35 },
	w_sniper  = { rate = 0.27, mag = 10, reload = 3.0, dmg = 60, pmax = 0.15,  sigma = math.rad(0.12), max = 800 },
}
local erf
do  -- erf: в Lua 5.1 её нет; приближение Абрамовиц–Стиган 7.1.26, ошибка < 1.5e-7
	erf = function(x)
		local s = x < 0 and -1 or 1
		x = math.abs(x)
		local t = 1 / (1 + 0.3275911 * x)
		local y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * math.exp(-x * x)
		return s * y
	end
end
local SQ2 = math.sqrt(2)

local function dist2(ax, az, bx, bz) return math.sqrt((ax - bx) ^ 2 + (az - bz) ^ 2) end

-- ─── создание ───────────────────────────────────────────────────────────────────────────────
-- scen: см. scen/*.lua. out — файл trace (jsonl).
function S.new(scen, world, out)
	local self = setmetatable({ scen = scen, w = world, t = 0, out = out, fighters = {}, squads = {},
		next_id = 1000, seq = 0, claims = {} }, S)
	math.randomseed(scen.seed or 1)
	for _, side in ipairs { 'A', 'B' } do
		for _, sq in ipairs(scen.sides[side].squads) do self:spawn_squad(side, sq) end
	end
	return self
end

function S:emit(ev, t)
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
		local f = { id = self.next_id, sq = sq, side = side, comm = def.comm, rank = def.ranks and def.ranks[k] or def.rank or 5000,
			node = node, x = x, y = y, z = z, fx = 0, fz = 1, cr = false, hp = HP,
			wk = wk, wpn = WPN[wk], mag = WPN[wk].mag, reload_t = 0, fire_t = math.random() / WPN[wk].rate,
			seen = {}, mem = {}, sup = 0, act = 9004, path = nil, pi = 1, pos_t = math.random() * POS_EVERY,
			cover = nil, cover_t = 0 }
		self.next_id = self.next_id + 1
		sq.members[#sq.members + 1] = f
		self.fighters[#self.fighters + 1] = f
	end
end

-- ─── восприятие ─────────────────────────────────────────────────────────────────────────────
-- Видимость копится, а не включается: на 30 м — ~полсекунды, на 100 м — пара секунд (как в игре
-- шкала visibility_threshold). Если враг в меня стреляет — я знаю, ОТКУДА (память), но не «вижу».
function S:can_see(a, b)
	local dx, dz = b.x - a.x, b.z - a.z
	local d = math.sqrt(dx * dx + dz * dz)
	if d > SEE_RANGE then return false, d end
	if d > 3 and (dx * a.fx + dz * a.fz) / d < FOV then return false, d end
	local ex, ey, ez = a.x, a.y + EYE[a.cr], a.z
	return W.clear(ex, ey, ez, b.x, b.y + CHEST[b.cr], b.z) or W.clear(ex, ey, ez, b.x, b.y + EYE[b.cr] + 0.1, b.z), d
end

function S:perceive(f)
	for _, e in ipairs(self.fighters) do
		if e.side ~= f.side and e.hp > 0 then
			local vis, d = self:can_see(f, e)
			local s = f.seen[e.id] or 0
			if vis then
				-- набор видимости: быстро вблизи, медленно вдали. exp(−d/40) — заместитель кустов и травы
				-- (в cform их нет, в игре они режут обзор: ночью 90% боёв ближе 66 м). Стреляющего и бегущего
				-- видно лучше, сидящего — хуже.
				local k = (e.firing_t and self.t - e.firing_t < 1 and 2 or 1) * (e.path and 1.5 or 1) * (e.cr and 0.6 or 1)
				s = math.min(1.5, s + DT * 12 * k * math.exp(-d / 40) / (1 + (d / 20) ^ 2) * 4)
				if s >= 1 then f.mem[e.id] = { x = e.x, y = e.y, z = e.z, t = self.t } end
			else
				s = math.max(0, s - DT * 0.5)
			end
			f.seen[e.id] = s
		end
	end
end

function S:visible_target(f)
	local best, bd
	for _, e in ipairs(self.fighters) do
		if e.side ~= f.side and e.hp > 0 and (f.seen[e.id] or 0) >= 1 then
			local vis, d = self:can_see(f, e)
			if vis and (not bd or d < bd - (e.id == f.target and 5 or 0)) then best, bd = e, d end
		end
	end
	return best, bd
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

-- занято ли место (своими, с запасом 2.5 м — не слипаться)
function S:taken(f, x, z)
	for _, m in ipairs(self.fighters) do
		if m ~= f and m.hp > 0 and m.side == f.side then
			local tx, tz = m.x, m.z
			if m.dest then tx, tz = m.dest[1], m.dest[3] end
			if dist2(x, z, tx, tz) < 2.5 then return true end
		end
	end
end

-- Укрытие от угрозы: сидя закрыт в её сторону, стоя (выглянув) — видит её.
-- goal (если есть) — укрытие должно быть «по дороге»: путь до цели не длиннее, чем был, + slack.
function S:find_cover(f, threat, r, goal, slack)
	local w = self.w
	local tx, tz = threat.x, threat.z
	local gx, gz = goal and goal[1], goal and goal[3]
	local here_goal = goal and dist2(f.x, f.z, gx, gz)
	local best, bs
	for _, it in ipairs(w:around(f.node, r)) do
		local i, pd = it[1], it[2]
		local x, y, z = w:xyz(i)
		local dx, dz = tx - x, tz - z
		local lo = w:openness(i, dx, dz, true)
		if lo < 0.4 and not self:taken(f, x, z) and (dx * (x - f.x) + dz * (z - f.z) <= 0 or pd < 4 or goal)
			and (not goal or dist2(x, z, gx, gz) <= here_goal + slack) then
			local s = lo * 3 + pd * 0.08 + (goal and dist2(x, z, gx, gz) * 0.05 or 0)
			if not bs or s < bs then
				-- огневая точка: стоя видно угрозу (иначе это просто нора)
				if W.clear(x, y + EYE[false], z, tx, threat.y + CHEST[false], tz) then best, bs = i, s end
			end
		end
	end
	return best
end

-- ─── движение ───────────────────────────────────────────────────────────────────────────────
function S:go(f, node, how)
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
	if not f.path then return end
	local w = self.w
	local speed = SPEED[f.cr and 'crouch' or f.how or 'walk'] * DT
	while speed > 0 and f.path do
		local n = f.path[f.pi]
		if not n then self:stop(f); break end
		local nx, ny, nz = w:xyz(n)
		local dx, dz = nx - f.x, nz - f.z
		local d = math.sqrt(dx * dx + dz * dz)
		if d <= speed then
			f.x, f.y, f.z, f.node = nx, ny, nz, n
			speed = speed - d
			f.pi = f.pi + 1
			if f.pi > #f.path then self:stop(f) end
		else
			f.x, f.z = f.x + dx / d * speed, f.z + dz / d * speed
			f.y = f.y + (ny - f.y) * (speed / d)
			if not f.target_vis then f.fx, f.fz = dx / d, dz / d end
			speed = 0
		end
	end
end

-- ─── огонь ──────────────────────────────────────────────────────────────────────────────────
-- видимая доля тела цели: три луча из глаз стрелка — ноги, грудь, голова
function S:visible_frac(f, t)
	local ex, ey, ez = f.x, f.y + EYE[f.cr], f.z
	local n = 0
	for _, h in ipairs(t.cr and { 0.3, 0.75, 1.0 } or { 0.45, 1.25, 1.6 }) do
		if W.clear(ex, ey, ez, t.x, t.y + h, t.z) then n = n + 1 end
	end
	return n / 3
end

function S:p_hit(f, t, d)
	local w = f.wpn
	local vis = self:visible_frac(f, t)
	if vis == 0 then return 0 end
	local moving = f.path ~= nil
	-- на ходу: ночь 21.10 — автомат 6.2% против 7.9% стоя (×0.8), ПП ×0.6; было ×0.4 — двойник душил наступающих
	local sigma = w.sigma * (moving and 1.4 or 1) * (f.cr and 0.8 or 1) * (1.3 - 0.5 * math.min(1, f.rank / 15000))
	local hgt = (t.cr and 1.1 or 1.7) * vis
	local sd = SQ2 * sigma * math.max(d, 1)
	local frac = erf(0.25 / sd) * erf(hgt / 2 / sd)
	return w.pmax * frac * (moving and 0.85 or 1)
end

function S:fire(f, t, d)
	local w = f.wpn
	if f.reload_t > 0 or d > w.max then return end
	if f.mag <= 0 then f.reload_t = w.reload; f.act = 9005; return end
	f.fire_t = f.fire_t - DT
	if f.fire_t > 0 then return end
	f.fire_t = (0.6 + math.random() * 0.8) / w.rate
	f.mag = f.mag - 1
	f.firing_t = self.t
	local p = self:p_hit(f, t, d)
	t.sup = t.sup + 0.25                                   -- пули рядом прижимают и без попадания
	t.mem[f.id] = { x = f.x, y = f.y, z = f.z, t = self.t } -- по мне стреляют — знаю откуда
	if math.random() < p then
		local dmg = w.dmg * (0.6 + math.random() * 0.8)
		t.hp = t.hp - dmg
		t.sup = t.sup + 1
		self.nhits = (self.nhits or 0) + 1
		self.hit_d = self.hit_d or {}
		self.hit_d[#self.hit_d + 1] = d
		self.first_hit = self.first_hit or self.t
		self:emit('hit', { npc = t.id, sq = t.sq.id, who = f.id, wsq = f.sq.id, amount = dmg, d = d, saw = 1, bone = 1,
			dy = f.y - t.y })
		if t.hp <= 0 then
			self:emit('death', { npc = t.id, sq = 0, comm = t.comm, killer = f.id, ksq = f.sq.id, rank = t.rank })
			self:stop(t)
		end
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

function S:center(sq)
	local x, z, n = 0, 0, 0
	for _, m in ipairs(sq.members) do if m.hp > 0 then x, z, n = x + m.x, z + m.z, n + 1 end end
	return x / math.max(n, 1), z / math.max(n, 1)
end

-- Место бойца на точке маршрута: строй в линию поперёк движения, через 3 м (точка — центр линии).
function S:slot_for(f, seg, prev)
	local px, pz
	if prev then px, pz = prev.x, prev.z else px, pz = self:center(f.sq) end
	local dx, dz = seg.x - px, seg.z - pz
	local L = math.sqrt(dx * dx + dz * dz)
	if L < 0.1 then dx, dz, L = 0, 1, 1 end
	local rx, rz = dz / L, -dx / L
	local i, n = 0, 0
	for _, m in ipairs(f.sq.members) do
		if m.hp > 0 then n = n + 1; if m == f then i = n end end
	end
	local off = (i - (n + 1) / 2) * 3
	return seg.x + rx * off, seg.z + rz * off
end

-- ─── мозг бойца ─────────────────────────────────────────────────────────────────────────────

function S:think(f)
	local t, d = self:visible_target(f)
	f.target_vis = t
	if t then
		f.target = t.id
		local dx, dz = t.x - f.x, t.z - f.z
		local L = math.sqrt(dx * dx + dz * dz)
		if L > 1e-3 then f.fx, f.fz = dx / L, dz / L end
	end

	-- перезарядка: если есть укрытие рядом — сидя (микронавык, которого нет у ванили в поле)
	if f.reload_t > 0 then
		f.reload_t = f.reload_t - DT
		if f.reload_t <= 0 then f.mag = f.wpn.mag end
	end

	-- новый приказ (личный важнее отрядного) → маршрут сначала
	local o = f.porder or f.sq.order
	if o and not o.personal and f.skip == o then o = nil end   -- после личного приказа старый отрядный не догоняет
	if f.order ~= o then
		f.order, f.seg, f.slot_seg, f.cover, f.cr = o, 1, nil, nil, false
		self:stop(f)
	end
	local seg = o and o.route[f.seg]
	local g = seg and seg.g or 3
	if seg and f.slot_seg ~= f.seg then
		if o.personal then f.tx, f.tz = seg.x, seg.z else f.tx, f.tz = self:slot_for(f, seg, o.route[f.seg - 1]) end
		f.slot_seg = f.seg
	end

	-- отрезок маршрута пройден → следующий. Стоит (не идёт) ближе 6 м — тоже дошёл: место в строю
	-- бывает на камне или в стене, а стоять из-за этого в поле под огнём (котёл 21.10) — бред
	local reach = g == 3 and 8 or (f.path and 1.5 or 6)
	if seg and dist2(f.x, f.z, f.tx, f.tz) < reach then
		f.seg = f.seg + 1
		seg = o.route[f.seg]
		g = seg and seg.g or 3
		f.cover = nil
		if seg then
			if o.personal then f.tx, f.tz = seg.x, seg.z else f.tx, f.tz = self:slot_for(f, seg, o.route[f.seg - 1]) end
			f.slot_seg = f.seg
		else
			f.hold_x, f.hold_z = f.x, f.z
			if o.personal then
				f.porder = nil
				f.skip = f.sq.order                 -- после личного — не бежит догонять старый приказ отряда
				f.done = f.sq.order
				self:emit('order', { sq = f.sq.id, npc = f.id, route = '', code = '', state = 'done' })
			else f.done = o end
		end
	end

	-- рефлекс: прижали → в укрытие (по поводку). На g3 (замысел) хватает и того, что увидел врага:
	-- район — не точка, воевать можно отсюда
	local threat = t or self:last_threat(f)
	if t then f.vis_t = self.t end
	if threat and (f.sup > 0.8 and g >= 2 or g == 3 and t) and not f.cover then
		local goal = seg and g == 2 and { f.tx, 0, f.tz } or nil
		local c = self:find_cover(f, threat, g == 2 and 12 or 15, goal, 3)
		if c then f.cover = c; f.cover_t = self.t; self:go(f, c, 'run') end
	end

	if f.cover then
		-- в укрытии: сидя; выглядываем (встаём) стрелять, когда видим; уходим, когда отдышались
		local at = f.node == f.cover
		if at then
			f.cr = not t or f.reload_t > 0 or (self.t * 10 % 30 < 12)   -- 40% времени стоим и стреляем
			f.act = 9003
		else
			f.act = 9002
		end
		local calm = f.sup < 0.3 and self.t - f.cover_t > 2
		if seg and g == 2 and (calm or self.t - f.cover_t > 10) then f.cover = nil; f.cr = false end
		-- g3 и без приказа: врага не видно 6 с — укрытие больше не нужно (дальше к точке / к памяти)
		if g == 3 and self.t - (f.vis_t or -99) > 6 and f.sup < 0.3 then f.cover = nil; f.cr = false end
	elseif seg then
		f.cr = false
		if not self:go(f, self.w:node_at(f.tx, seg.y, f.tz), t and g >= 2 and 'walk' or 'run') then
			f.tx, f.tz = seg.x, seg.z                 -- место в строю недостижимо → к самой точке
		end
		f.act = 9001
	else
		-- без приказа: видишь — в укрытие рядом и бой; не видишь, но помнишь — к последнему месту
		if f.sq.free and threat and not t and not f.path and self.t - (f.mem_t or 0) > 8 then
			local m = self:last_mem(f)
			if m then self:go(f, self.w:node_at(m.x, m.y, m.z), 'walk'); f.act = 9007; f.mem_t = self.t end
		elseif threat and not t and not f.path and self.t - (f.mem_t or 0) > 4 then
			-- держит район, врага не видит, но знает, где он: огневая точка рядом (до 10 м от места
			-- приказа), откуда видно то место. Не сидеть вслепую (котёл 21.10).
			f.mem_t = self.t
			local hx, hz = f.hold_x or f.x, f.hold_z or f.z
			local c = self:find_cover(f, threat, 12, { hx, 0, hz }, 10)
			if c and c ~= f.node then f.cover = c; f.cover_t = self.t; self:go(f, c, 'walk'); f.act = 9008 end
		elseif not f.path then
			f.act = 9004
		end
	end

	-- огонь
	if t and f.hp > 0 then
		local fr = self:friend_in_line(f, t)
		if fr then
			-- шаг вбок — перпендикулярно линии огня, в сторону от своего; никогда не на врага
			f.act = 9006
			if not f.path then
				local px, pz = -f.fz, f.fx
				if (fr.x - f.x) * px + (fr.z - f.z) * pz > 0 then px, pz = -px, -pz end
				local n = self.w:node_at(f.x + px * 2.5, f.y, f.z + pz * 2.5)
				if n then self:go(f, n, 'walk') end
			end
		elseif not (f.cover and f.cr) then
			self:fire(f, t, d)
		end
	end
	f.sup = math.max(0, f.sup - DT * 0.5)
end

function S:last_mem(f)
	local best
	for _, m in pairs(f.mem) do if not best or m.t > best.t then best = m end end
	return best
end

function S:last_threat(f)
	local m = self:last_mem(f)
	if m and self.t - m.t < 20 then return m end
end

-- ─── шаг и прогон ───────────────────────────────────────────────────────────────────────────
function S:alive(side)
	local n = 0
	for _, f in ipairs(self.fighters) do if f.side == side and f.hp > 0 then n = n + 1 end end
	return n
end

function S:snap(f)
	self:emit('npc_pos', { npc = f.id, sq = f.sq.id, px = f.x, py = f.y, pz = f.z, dx = f.fx, dz = f.fz,
		comm = f.comm, rank = f.rank, hp = math.max(0, f.hp / HP), wk = f.wk, wpn = f.wk, mag = f.mag,
		cr = f.cr and 1 or 0, be = f.target or -1, bsee = f.target_vis and 1 or 0, aid = f.act, aid2 = -1,
		active = 1, wnd = 0 })
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
	local every = self.pos_every or POS_EVERY
	for _, f in ipairs(self.fighters) do
		if f.hp > 0 then
			self:perceive(f)
			self:think(f)
			self:step_move(f)
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
