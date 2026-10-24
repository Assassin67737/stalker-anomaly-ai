-- brain_default.lua — мозг по умолчанию (24.10.2026, «опустошение сосуда», VESSEL_AUDIT.md §5).
--
-- Сосуд (sim.lua) — тело: зрение и память, движение, огонь и пуля, раненые, гранаты как физика. Решения — здесь:
-- выбор цели, взгляд на звук, укрытия, строй и поводок приказа, перекаты, подавление, прижатие и паника, добивание,
-- гранаты (решения — в grenade.lua: G.try_throw, G.decide/dodge_step). Задача этого мозга — быть «как ваниль + VARKA
-- в игре», чтобы сверка тела (vessel.py) не путалась с разницей мозгов, и быть соперником/мерилом для наученца.
--
-- Контракт мозга: B.think(S, f) раз в шаг для живого, не раненого, не занятого телом бойца (тело занято: замах гранаты).
-- Что мозгу можно (API тела, sim.lua):
--   смотреть  S:sees(f, e) → видно?, d (набор видимости + still_visible), S:can_see(f, e) — рамка и луч сейчас,
--             f.mem / S:last_mem(f) — память (видел, слышал, по мне попали), f.hear — последнее услышанное,
--             S:friend_in_line(f, t), свои hp / mag / reload_t / cr / wounded, S.w — навмеш и укрытость нод, W.clear;
--   делать    S:go(f, node, 'walk'|'run'), S:stop(f), f.wx/f.wz — куда смотреть (голова 270°/с), f.cr — сидеть,
--             S:fire(f, t, d) — по цели, S:fire_at(f, point, mode) — по точке (перезарядка — сама, когда пусто),
--             G.try_throw(S, f) — граната;
--   приказы   f.porder / f.sq.order (их отдаёт генерал: сценарий, live.lua) — для мозга это вход, не закон.
-- Наученец подключается так же: модуль с think(S, f), имя — scen.sides[A|B].brain.

local W = require 'world'
local G = require 'grenade'
local H = require 'hear'
local F = require 'fire'

local B = {}

local DT = 0.1
local EYE = { [false] = 1.6, [true] = 1.0 }
local CHEST = { [false] = 1.25, [true] = 0.75 }
local function dist2(ax, az, bx, bz) return math.sqrt((ax - bx) ^ 2 + (az - bz) ^ 2) end

function B.target(S, f)
	local best, bd
	for _, e in ipairs(S.fighters) do
		-- раненый, пока падает (wnd_fall), — ещё цель; лёг — нет
		if e.side ~= f.side and e.hp > 0 and not e.prone_wnd then
			local vis, d = S:sees(f, e)
			if vis and (not bd or d < bd - (e.id == f.target and 5 or 0)) then best, bd = e, d end
		end
	end
	return best, bd
end

-- занято ли место (своими, с запасом 2.5 м — не слипаться)
function B.taken(S, f, x, z)
	for _, m in ipairs(S.fighters) do
		if m ~= f and m.hp > 0 and m.side == f.side then
			local tx, tz = m.x, m.z
			if m.dest then tx, tz = m.dest[1], m.dest[3] end
			if dist2(x, z, tx, tz) < 2.5 then return true end
		end
	end
end

-- Укрытие от угрозы: сидя закрыт в её сторону, стоя (выглянув) — видит её.
-- goal (если есть) — укрытие должно быть «по дороге»: путь до цели не длиннее, чем был, + slack.
function B.find_cover(S, f, threat, r, goal, slack)
	local w = S.w
	local tx, tz = threat.x, threat.z
	local gx, gz = goal and goal[1], goal and goal[3]
	local here_goal = goal and dist2(f.x, f.z, gx, gz)
	local best, bs
	for _, it in ipairs(w:around(f.node, r)) do
		local i, pd = it[1], it[2]
		local x, y, z = w:xyz(i)
		local dx, dz = tx - x, tz - z
		local lo = w:openness(i, dx, dz, true)
		if lo < 0.4 and not B.taken(S, f, x, z) and (dx * (x - f.x) + dz * (z - f.z) <= 0 or pd < 4 or goal)
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

-- Добивание (мозг-по-умолчанию, как ванильный xrs_kill_wounded с правкой VARKA): живой угрозы не видно, а раненый
-- враг виден и ближе 40 м — подойти на 3–5 м, постоять 0.45–1.35 с, выстрел в упор = смерть. true — занят этим.
function B.finish_wounded(S, f)
	if not S.K.kw then return false end
	local v = f.kw_victim
	if v and (v.hp <= 0 or not v.wounded) then v, f.kw_victim, f.kw_at = nil, nil, nil end
	if not v then
		local bd
		for _, e in ipairs(S.fighters) do
			if e.side ~= f.side and e.hp > 0 and e.prone_wnd and (f.seen[e.id] or 0) >= 1 then
				local d = dist2(f.x, f.z, e.x, e.z)
				if d < 40 and (not bd or d < bd) then v, bd = e, d end
			end
		end
		if not v then return false end
		for _, m in ipairs(f.sq.members) do if m ~= f and m.kw_victim == v then return false end end   -- палач один
		f.kw_victim = v
	end
	local d = dist2(f.x, f.z, v.x, v.z)
	f.act, f.cr = 9020, false
	if d > 5 then
		f.kw_at = nil
		if not f.path then
			local k = (d - 4) / d
			S:go(f, S.w:node_at(f.x + (v.x - f.x) * k, v.y, f.z + (v.z - f.z) * k), d > 8 and 'run' or 'walk')
		end
		return true
	end
	S:stop(f)
	local L = math.max(d, 1e-3)
	f.wx, f.wz = (v.x - f.x) / L, (v.z - f.z) / L
	f.kw_at = f.kw_at or S.t + 0.45 + math.random() * 0.9
	if S.t >= f.kw_at then
		S:emit('kw_fire', { npc = f.id, sq = f.sq.id, victim = v.id })
		S:damage(v, f, v.hp + 1, d)
		f.kw_victim, f.kw_at = nil, nil
	end
	return true
end

function B.center(S, sq)
	local x, z, n = 0, 0, 0
	for _, m in ipairs(sq.members) do if m.hp > 0 then x, z, n = x + m.x, z + m.z, n + 1 end end
	return x / math.max(n, 1), z / math.max(n, 1)
end

-- Место бойца на точке маршрута: строй в линию поперёк движения, через 3 м (точка — центр линии).
function B.slot_for(S, f, seg, prev)
	local px, pz
	if prev then px, pz = prev.x, prev.z else px, pz = B.center(S, f.sq) end
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

function B.think(S, f)
	local t, d = B.target(S, f)
	f.target_vis = t
	-- услышал врага, не видит — смотрит туда (глаза получают шанс; на ходу тоже — шаг не разворачивает)
	local lx, lz = H.look(S, f)
	f.look_hear = lx ~= nil
	if lx then f.wx, f.wz = lx, lz end
	F.update_panic(S, f)
	if t then
		f.last_vis = { x = t.x, y = t.y, z = t.z, t = S.t }   -- для подавления «сам»: где цель пропала
		f.target = t.id
		local dx, dz = t.x - f.x, t.z - f.z
		local L = math.sqrt(dx * dx + dz * dz)
		if L > 1e-3 then f.wx, f.wz = dx / L, dz / L end
	end

	-- граната: убегает (рефлекс главнее приказа) → замахнулся → решил кинуть (grenade.lua)
	if f.dodge then
		if f.dodge_end and S.t >= f.dodge_end then
			f.dodge, f.dodge_end, f.down_t, f.prone, f.cr = nil, nil, nil, false, false
		else
			G.dodge_step(S, f)
			return
		end
	end
	if not t and G.try_throw(S, f) then return end
	if not t and f.reload_t <= 0 and B.finish_wounded(S, f) then return end

	-- новый приказ (личный важнее отрядного) → маршрут сначала
	local o = f.porder or f.sq.order
	if o and not o.personal and f.skip == o then o = nil end   -- после личного приказа старый отрядный не догоняет
	if f.order ~= o then
		f.order, f.seg, f.slot_seg, f.cover, f.cr = o, 1, nil, nil, false
		S:stop(f)
	end
	local seg = o and o.route[f.seg]
	local g = seg and seg.g or 3
	if seg and f.slot_seg ~= f.seg then
		if o.personal then f.tx, f.tz = seg.x, seg.z else f.tx, f.tz = B.slot_for(S, f, seg, o.route[f.seg - 1]) end
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
			if o.personal then f.tx, f.tz = seg.x, seg.z else f.tx, f.tz = B.slot_for(S, f, seg, o.route[f.seg - 1]) end
			f.slot_seg = f.seg
		else
			f.hold_x, f.hold_z = f.x, f.z
			if o.personal then
				f.porder = nil
				f.skip = f.sq.order                 -- после личного — не бежит догонять старый приказ отряда
				f.done = f.sq.order
				S:emit('order', { sq = f.sq.id, npc = f.id, route = '', code = '', state = 'done' })
			else f.done = o end
		end
	end

	-- перекаты (o.bound или рычаг bound): при контакте отряд — две пары, одна бежит, другая давит
	-- кто решает: рычаг мира (K.bound, если задан) > доктрина стороны (doc.bound) > приказ (o.bound)
	local K, D = S.K, S.doc[f.side]
	local bound = K.bound
	if bound == nil then bound = D.bound end
	if bound == nil then bound = o and o.bound end
	if o and seg and bound and B.bound_step(S, f, o, seg, t, d) then
		return
	end

	-- рефлекс: прижали → в укрытие (по поводку). На g3 (замысел) хватает и того, что увидел врага:
	-- район — не точка, воевать можно отсюда
	local threat = t or B.last_threat(S, f)
	if t then f.vis_t = S.t end
	if threat and (f.sup > 0.8 and g >= 2 or g == 3 and t) and not f.cover then
		local goal = seg and g == 2 and { f.tx, 0, f.tz } or nil
		local c = B.find_cover(S, f, threat, g == 2 and 12 or 15, goal, 3)
		if c then f.cover = c; f.cover_t = S.t; S:go(f, c, 'run') end
	end

	if f.cover then
		-- в укрытии: сидя; выглядываем (встаём) стрелять, когда видим; уходим, когда отдышались
		local at = f.node == f.cover
		if at then
			-- 40% времени стоим и стреляем; прижали (пули бьют рядом, sup > sup_pin) — не высовывается: в этом и есть
			-- подавление (24.10: без этого перекаты с подавлением не лучше простого хода — давили, а он выглядывал)
			f.cr = not t or f.reload_t > 0 or B.pinned(S, f, 99) or (S.t * 10 % 30 < 12)
			f.act = 9003
		else
			f.act = 9002
		end
		local calm = f.sup < 0.3 and S.t - f.cover_t > 2
		if seg and g == 2 and (calm or S.t - f.cover_t > 10) then f.cover = nil; f.cr = false end
		-- g3 и без приказа: врага не видно 6 с — укрытие больше не нужно (дальше к точке / к памяти)
		if g == 3 and S.t - (f.vis_t or -99) > 6 and f.sup < 0.3 then f.cover = nil; f.cr = false end
	elseif seg then
		f.cr = false
		-- к точке приказа — шагом, как мягкий приказ игры (varka_cmd: состояние raid = шаг, danger); g1 «любой ценой» — бегом
		if not S:go(f, S.w:node_at(f.tx, seg.y, f.tz), g == 1 and 'run' or 'walk') then
			f.tx, f.tz = seg.x, seg.z                 -- место в строю недостижимо → к самой точке
		end
		f.act = 9001
	else
		-- без приказа: видишь — в укрытие рядом и бой; не видишь, но помнишь — к последнему месту
		if f.sq.free and threat and not t and not f.path and S.t - (f.mem_t or 0) > 8 then
			local m = S:last_mem(f)
			if m then S:go(f, S.w:node_at(m.x, m.y, m.z), 'walk'); f.act = 9007; f.mem_t = S.t end
		elseif threat and not t and not f.path and S.t - (f.mem_t or 0) > 4 then
			-- держит район, врага не видит, но знает, где он: огневая точка рядом (до 10 м от места
			-- приказа), откуда видно то место. Не сидеть вслепую (котёл 21.10).
			f.mem_t = S.t
			local hx, hz = f.hold_x or f.x, f.hold_z or f.z
			local c = B.find_cover(S, f, threat, 12, { hx, 0, hz }, 10)
			if c and c ~= f.node then f.cover = c; f.cover_t = S.t; S:go(f, c, 'walk'); f.act = 9008 end
		elseif not f.path then
			f.act = 9004
		end
	end

	-- огонь
	if t and f.hp > 0 then
		local fr = S:friend_in_line(f, t)
		if fr then
			-- шаг вбок — перпендикулярно линии огня, в сторону от своего; никогда не на врага
			f.act = 9006
			if not f.path then
				local px, pz = -f.fz, f.fx
				if (fr.x - f.x) * px + (fr.z - f.z) * pz > 0 then px, pz = -px, -pz end
				local n = S.w:node_at(f.x + px * 2.5, f.y, f.z + pz * 2.5)
				if n then S:go(f, n, 'walk') end
			end
		elseif B.pinned(S, f, d) then
			f.cr = true                                 -- прижали: пригнулся, не стреляет (кроме паники и упора)
		elseif not (f.cover and f.cr) then
			S:fire(f, t, d)
		end
	elseif f.hp > 0 and not B.pinned(S, f, 99) and not (f.cover and f.cr) and f.reload_t <= 0 then
		-- не видит: подавление «сам» — коротко по месту, где цель только что пропала; в панике — по свежей памяти
		local lv, pt = f.last_vis, nil
		local ss = S.doc[f.side].sup_self or S.K.sup_self
		if lv and S.t - lv.t < ss then pt = lv
		elseif f.panic then
			local m = S:last_mem(f)
			if m and S.t - m.t < 3 then pt = m end
		end
		if pt and S:fire_at(f, pt, 'sup') then f.act = f.panic and 9014 or 9013 end
	end
end

-- прижат ли: пули бьют рядом (sup > sup_pin) — не высовывается и не стреляет. Паника — палит (fire.lua);
-- враг ближе close_d — отстреливается. Это и делает подавление подавлением.
function B.pinned(S, f, d)
	if not F.on(S, f.side, 'pin') then return false end   -- сосуд и ваниль: под огнём не пригибается (fire.lua F.on)
	return f.sup > S.K.sup_pin and not f.panic and d >= S.K.close_d
end

-- Перекаты с подавлением (24.10, юзер: «роли для манёвра при перекатах наконец станут иметь смысл»).
-- Отряд при контакте — две пары по номеру в отряде. Бежит одна (перебежка bound_leg к цели отрезка, не стреляет;
-- добежал — присел), другая стоит и давит: видит — прицельно, не видит — по самому свежему месту, которое знает
-- отряд. Все бегущие добежали (или bound_max с) — меняются. Контакта нет — обычный ход по приказу.
function B.bound_step(S, f, o, seg, t, d)
	local K, sq = S.K, f.sq
	local m = F.squad_mem(S, sq)
	if not (t or m) then return false end
	if f.bteam == nil then
		for k, x in ipairs(sq.members) do if x == f then f.bteam = k % 2 end end
	end
	local ph = sq.bphase
	if not ph or ph.o ~= o then ph = { o = o, team = 1, t0 = S.t }; sq.bphase = ph end
	if ph.tick ~= S.t then
		ph.tick = S.t
		local any, moving = false, false
		for _, x in ipairs(sq.members) do
			if x.hp > 0 and x.bteam == ph.team then any = true; if not x.bdone then moving = true end end
		end
		if not any or not moving or S.t - ph.t0 > K.bound_max then
			ph.team, ph.t0 = 1 - ph.team, S.t
			for _, x in ipairs(sq.members) do x.bleg, x.bdone = nil, nil end
			S:emit('bound_swap', { sq = sq.id, npc = 0, team = ph.team })
		end
	end
	if f.bteam == ph.team then
		if not f.bleg then
			f.bleg, f.cr = true, false
			local dx, dz = f.tx - f.x, f.tz - f.z
			local L = math.max(1e-3, math.sqrt(dx * dx + dz * dz))
			local k = math.min(1, K.bound_leg / L)
			local n = S.w:node_at(f.x + dx * k, seg.y or f.y, f.z + dz * k)
			if not (n and S:go(f, n, 'run')) then f.bdone = true end
		elseif not f.path then
			f.bdone, f.cr = true, true
		end
		f.act = 9015
		if t and f.bdone and not S:friend_in_line(f, t) then S:fire(f, t, d) end
	else
		S:stop(f)
		f.cr, f.act = false, 9016
		if t then
			if not S:friend_in_line(f, t) then S:fire(f, t, d) end
		elseif m and S.doc[f.side].sup_role ~= false then
			S:fire_at(f, m, 'sup')
		end
	end
	return true
end

function B.last_threat(S, f)
	local m = S:last_mem(f)
	if m and S.t - m.t < 20 then return m end
end

return B
