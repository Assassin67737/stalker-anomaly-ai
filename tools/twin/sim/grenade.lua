-- grenade.lua — гранаты в двойнике. Это ЭТАЛОН: сначала здесь, потом тот же замысел — в игре (varka_grenade.script).
--
-- v1 (23.10) — физика ванили из движка (engine_src/xrGame):
--   бросок   ai_stalker_fire.cpp update_throw_params: из точки над головой (+2 м) по траектории МИНИМАЛЬНОЙ скорости
--            (T = √(2·|r|/g)), потом скорость × кубик U(0.75, 1.25) → дальность ×0.56…1.56; цель — ПАМЯТЬ о враге
--            (любой давности) + нарочный промах 2–5 м (compute_throw_miss). Гравитация движка — 2 × 9.81
--            (xrPhysics/Physics.cpp default_world_gravity): 20 м граната летит 1.4 с, а не 2.
--   запал    Missile.cpp: destroy_time 2500 мс с момента, как граната ушла из руки.
--   взрыв    Explosive.cpp: волна blast × R²/(2d² + R²) в шаре blast_r (на краю — треть), гаснет на преградах;
--            осколки — frags пуль во все стороны (random_dir) по frag_hit, летят до frags_r.
--            РГД-5: blast 3, r 6, 80 осколков по 0.27 до 25 м. Ф-1: blast 3, r 8, 127 до 45 м (m_rgd5.ltx, m_f1.ltx).
--   увидеть  agent_explosive_manager.cpp: гранату замечает только тот, кто её ВИДИТ; крик — только звук.
--   запрет   ShouldThrowGrenade: стоя на месте, враг НЕ виден, ближе 10 м нельзя, личный интервал 20 с, свой ближе
--            5 м к точке — нельзя; отрядный интервал ставится ПОСЛЕ броска → трое кидают разом.
--
-- v2 (24.10, решения юзера):
--   · кубики ванили — НЕТ (остались рычагом мира g_dice для сравнения). Вместо них ошибка умения: σ дальности и вбок
--     в долях дистанции, по прямой рангов (новичок → эксперт+).
--   · запал как в жизни: УЗРГМ 3.2–4.2 с, у каждой свой. Опытный «отсчитывает»: держит с выдернутой чекой, чтобы
--     рвалась через COOK_LAND после касания; новичок кидает сразу.
--   · ВИДЕЛ гранату — у него есть информация: бежит от точки падения, какого бы ранга ни был (g_react ~0.3 с почти
--     без ранга, ранг — лишь ошибка точки g_eye_err). Обернулся по крику и УВИДЕЛ — та же цепочка «видел», только
--     позже на время оборота. Прикидка g_est_err — только тем, кто так и НЕ увидел (уточнение юзера 24.10).
--   · угроза → спринт к ближайшему месту, где сидящего не достаёт (дальше радиуса или за преградой) → присесть.
--     ЛЁЖА УБРАНО (24.10, юзер): позы лёжа в ванили не нашли; с ней точка «безопасно» была на 3–5 м ближе, чем
--     нужно стоящему/сидящему, — в игре бойцы добегали до неё и гибли в нырке, которого нет. Код лёжа (d.prone)
--     оставлен выключенным — вернуть, если поза найдётся.
--   · старт рывка не мгновенный (g_start): игра 23.10, 33 рывка — от решения до первого шага 0.3–1.2 с
--     (планировщик переключается ≤0.5 с, дальше state_mgr меняет позу/ствол и строит путь).
--
-- Единицы урона — как в trace (hit.amount, здоровье ≈ 100–145): blast 3 → 300, осколок 0.27 → 27.
-- Два слоя рычагов («информация честна абсолютно, цифры умения — регулятор»):
--   доктрина стороны (G.DOCTRINE) — РЕШЕНИЯ: когда кидать, кричать ли, бежать ли, ложиться ли. Сравниваем.
--   мир (sim.K.g_*)               — ФИЗИКА и умение: запал, ошибки, реакция, броня. Калибруем.
-- Прямая рангов: значение = lo + (hi − lo) × s, s = ранг / 14500 (плато с эксперта, как у износа);
-- K.g_skill_k умножает все ошибки и времена реакции (крутим чувствительность к «умению вообще»).

local W = require 'world'

local G = {}

local GRAV = 19.62            -- движок: 2 × 9.81
local HAND = 2.0              -- точка броска над ногами (движок: Position().y + 2)
local SUB = 0.05              -- шаг проверки траектории, с
G.GRAV = GRAV

G.TYPES = {
	rgd5 = { blast = 300, blast_r = 6, frags = 80, frags_r = 25, frag = 27 },
	f1   = { blast = 300, blast_r = 8, frags = 127, frags_r = 45, frag = 27 },
}

-- Доктрины (решения). varka — эталон v2; vanilla — решения движка; none — без гранат; no* — varka без одной части.
G.DOCTRINE = {
	varka   = { on = true, count = 1, type = 'rgd5', min_d = 10, max_d = 40, mem_age = { 15, 6 }, need_still = true,
		personal = 20, squad = 7, friend_r = 6, shout = true, dodge = true, prone = false, cook = true },
	vanilla = { on = true, count = 1, type = 'rgd5', min_d = 10, max_d = 40, mem_age = { 1e9, 1e9 }, need_still = true,
		personal = 20, squad = 0, friend_r = 5, shout = false, dodge = true, prone = false, cook = false },
	none    = { on = false, count = 0, type = 'rgd5', min_d = 10, max_d = 40, mem_age = { 0, 0 }, need_still = true,
		personal = 20, squad = 7, friend_r = 5, shout = true, dodge = true, prone = false, cook = false },
}
do
	local function variant(base, over)
		local d = {}
		for k, v in pairs(G.DOCTRINE[base]) do d[k] = v end
		for k, v in pairs(over) do d[k] = v end
		return d
	end
	G.DOCTRINE.noshout = variant('varka', { shout = false })
	G.DOCTRINE.nododge = variant('varka', { dodge = false })
	G.DOCTRINE.nocook = variant('varka', { cook = false })
	G.DOCTRINE.oldmem = variant('varka', { mem_age = { 1e9, 1e9 } })
	-- тактика огня стороны (24.10, fire.lua / sim.lua): гранаты как varka, плюс
	--   bound — при контакте на марше перекатами (поверх order.bound), sup_self — подавление «сам», с (0 — нет),
	--   sup_role — прикрывающая пара давит по знанию отряда (false — бьёт только по видимому)
	-- (сосуд 24.10: прижатие, паника, отдача по умолчанию выключены — доктрины огня включают их явно, как задумано)
	G.DOCTRINE.f_full = variant('varka', { bound = true, sup_self = 2.5, sup_role = true, pin = true, panic = true, recoil = true })
	G.DOCTRINE.f_nobound = variant('varka', { bound = false, sup_self = 2.5, sup_role = true, pin = true, panic = true, recoil = true })
	G.DOCTRINE.f_nosup = variant('varka', { bound = false, sup_self = 0, sup_role = false, pin = true, panic = true, recoil = true })
	G.DOCTRINE.f_boundnosup = variant('varka', { bound = true, sup_self = 0, sup_role = false, pin = true, panic = true, recoil = true })
	-- ВАНИЛЬ целиком — точка отсчёта (24.10): ванильные гранаты; огонь прежнего двойника (ровный темп, подогнан по
	-- ночи 21.10, где бой вёл ванильный C++) — без очередей, отдачи, паники; не прижимается под огнём; слух как в
	-- движке (шагов не слышит); без перекатов и подавления
	G.DOCTRINE.vanilla_all = variant('vanilla', { bound = false, sup_self = 0, sup_role = false, burst = false,
		panic = false, pin = false, steps = false, gate_muzzle = false })
end

-- рычаги мира по умолчанию (sim.K их дополняет). { lo, hi } — прямая рангов
G.WORLD = {
	g_fuse = { 3.2, 4.2 },        -- запал, с: U(мин, макс) у каждой гранаты (ваниль: { 2.5, 2.5 })
	g_dice = false,               -- true — ванильные кубики (скорость ×U(0.75,1.25) + промах 2–5 м) вместо ошибки умения
	g_err_range = { 0.18, 0.05 }, -- σ дальности, доля дистанции
	g_err_lat = { 0.10, 0.03 },   -- σ вбок, доля дистанции
	g_cook_max = { 0, 1.5 },      -- сколько готов держать с выдернутой чекой, с
	g_cook_land = 0.4,            -- опытный целит взрыв на столько после касания, с
	g_windup = 1.0,               -- замах: встал, не стреляет, с
	g_see = 30,                   -- дальше — летящую гранату не замечают, м
	g_react = { 0.3, 0.25 },      -- увидел → побежал, с (рефлекс: ранг почти не влияет)
	g_start = 0.5,                -- решил бежать → первый шаг, с (игра 23.10: 0.3–1.2, смена позы/ствола + путь)
	g_eye_err = { 1.0, 0.5 },     -- увидел — ошибка точки падения по дуге, м
	g_look = { 1.0, 0.5 },        -- услышал крик → уходит и ищет глазами столько, с
	g_est_err = { 4, 2 },         -- по крику (ещё не увидел) — ошибка прикидки, м
	g_down = 0.8,                 -- лечь, с (пока ложится — силуэт сидя)
	g_get_up = { 1.2, 0.6 },      -- после взрыва лежит ещё, с
	g_skill_k = 1,                -- множитель всех ошибок и времён реакции
	armor_blast = 0.8,            -- множитель урона волной (иммунитет тела × костюм; не сверено)
	armor_frag = 0.8,             -- множитель урона осколком (stalker_resist fire_wound 0.8)
}

local function d3(ax, ay, az, bx, by, bz) return math.sqrt((ax - bx) ^ 2 + (ay - by) ^ 2 + (az - bz) ^ 2) end
local function rs(f) return math.max(0, math.min(1, f.rank / 14500)) end
local function line(t, s) return t[1] + (t[2] - t[1]) * s end
G.rs, G.line = rs, line
local function gauss()
	local u = math.max(1e-9, math.random())
	return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * math.random())
end
-- время/ошибка умения бойца f по рычагу k мира (с множителем умения)
local function skill(S, f, k) return line(S.K[k], rs(f)) * S.K.g_skill_k end

local function poisson(l)
	if l <= 0 then return 0 end
	if l > 30 then return math.max(0, math.floor(l + math.sqrt(l) * (math.random() + math.random() + math.random() - 1.5) * 2 + 0.5)) end
	local L, k, p = math.exp(-l), 0, 1
	repeat k = k + 1; p = p * math.random() until p <= L
	return k - 1
end

-- скорость минимальной величины из (h) в (a): T = √(2|r|/g), v = r/T + ½gT вверх
function G.min_vel(hx, hy, hz, ax, ay, az)
	local rx, ry, rz = ax - hx, ay - hy, az - hz
	local T = math.sqrt(2 * math.sqrt(rx * rx + ry * ry + rz * rz) / GRAV)
	return rx / T, ry / T + 0.5 * GRAV * T, rz / T, T
end

-- та же цель, полёт дольше в mlt раз (дуга круче): v = r/T + ½gT вверх
G.LOBS = { 1, 1.15, 1.3, 1.5, 1.75 }
function G.vel_for(hx, hy, hz, ax, ay, az, mlt)
	local rx, ry, rz = ax - hx, ay - hy, az - hz
	local T = math.sqrt(2 * math.sqrt(rx * rx + ry * ry + rz * rz) / GRAV) * mlt
	return rx / T, ry / T + 0.5 * GRAV * T, rz / T, T
end

function G.at(g, t)
	return g.x0 + g.vx * t, g.y0 + g.vy * t - 0.5 * GRAV * t * t, g.z0 + g.vz * t
end

-- время, когда траектория упрётся в стену (nil — свободна до T)
local function first_block(x0, y0, z0, vx, vy, vz, T)
	local px, py, pz = x0, y0, z0
	local t = 0
	while t < T do
		local nt = math.min(T, t + SUB)
		local nx, ny, nz = x0 + vx * nt, y0 + vy * nt - 0.5 * GRAV * nt * nt, z0 + vz * nt
		if not W.clear(px, py, pz, nx, ny, nz) then return t end
		px, py, pz, t = nx, ny, nz, nt
	end
end

-- ─── решение бросить ────────────────────────────────────────────────────────────────────────
function G.try_throw(S, f)
	local d, K, now = S.doc[f.side], S.K, S.t
	if not d.on or f.gren <= 0 or f.windup or f.dodge or f.reload_t > 0 then return end
	if now - f.gren_t < d.personal or now - (f.sq.gren_t or -1e9) < d.squad then return end
	if d.need_still and f.path then return end
	local m = S:last_mem(f)
	if not m or now - m.t > line(d.mem_age, rs(f)) then return end
	local dist = math.sqrt((m.x - f.x) ^ 2 + (m.z - f.z) ^ 2)
	if dist < d.min_d or dist > d.max_d then return end
	for _, o in ipairs(S.fighters) do
		if o.side == f.side and o.hp > 0 and (o.x - m.x) ^ 2 + (o.z - m.z) ^ 2 < d.friend_r ^ 2 then return end
	end
	local ax, ay, az = m.x, m.y, m.z
	if K.g_dice then
		-- ваниль: нарочный промах 2–5 м по навмешу
		local r, a = 2 + math.random() * 3, math.random() * 2 * math.pi
		local n = S.w:node_at(ax + r * math.cos(a), ay, az + r * math.sin(a))
		if n then ax, ay, az = S.w:xyz(n) end
	end
	-- самая пологая дуга задевает укрытие → круче (в игре 24.10: граната отскакивала под ноги бросившему)
	local hx, hy, hz = f.x, f.y + HAND, f.z
	local lob
	for _, mlt in ipairs(G.LOBS) do
		local vx, vy, vz, T = G.vel_for(hx, hy, hz, ax, ay + 0.1, az, mlt)
		if not first_block(hx, hy, hz, vx, vy, vz, T * 0.85) then lob = mlt; break end
	end
	if not lob then return end
	S:stop(f)
	f.cr, f.prone, f.act = false, false, 9010
	f.windup = K.g_windup
	f.throw = { ax = ax, ay = ay, az = az, mx = m.x, mz = m.z, lob = lob }
	f.gren, f.gren_t, f.sq.gren_t = f.gren - 1, now, now
	return true
end

-- замах кончился → граната ушла из руки (ошибка умения или кубики ванили), полёт с отскоком от первой стены
function G.release(S, f)
	local th, K, d = f.throw, S.K, S.doc[f.side]
	f.windup, f.throw = nil, nil
	local hx, hy, hz = f.x, f.y + HAND, f.z
	local ax, ay, az, u = th.ax, th.ay, th.az, 1
	if not K.g_dice then
		local dx, dz = ax - hx, az - hz
		local dist = math.max(0.1, math.sqrt(dx * dx + dz * dz))
		local k = math.max(0.3, 1 + gauss() * skill(S, f, 'g_err_range'))
		local lat = gauss() * skill(S, f, 'g_err_lat') * dist
		local ux, uz = dx / dist, dz / dist
		ax, az = hx + ux * dist * k - uz * lat, hz + uz * dist * k + ux * lat
	end
	local vx, vy, vz, T = G.vel_for(hx, hy, hz, ax, ay + 0.1, az, th.lob or 1)
	if K.g_dice then u = 0.75 + math.random() * 0.5 end
	local typ = G.TYPES[d.type]
	local g = { id = S.gid, owner = f, side = f.side, typ = typ, x0 = hx, y0 = hy, z0 = hz,
		vx = vx * u, vy = vy * u, vz = vz * u, t0 = S.t, aware = {} }
	S.gid = S.gid + 1
	-- где коснётся земли: высота цели как «пол» (другого пола у двойника нет — только ноды)
	local a, b, c = -0.5 * GRAV, g.vy, g.y0 - ay
	local tl = (-b - math.sqrt(math.max(0, b * b - 4 * a * c))) / (2 * a)
	local tb = first_block(g.x0, g.y0, g.z0, g.vx, g.vy, g.vz, tl)
	if tb then tl = tb end
	g.land_t = tl
	local lx, ly, lz = G.at(g, tl)
	local n = S.w:node_at(lx, ly, lz)
	if n then local _, ny = S.w:xyz(n); if tb or math.abs(ny - ly) < 3 then ly = ny end end
	g.lx, g.ly, g.lz = lx, ly, lz
	-- запал: свой у каждой; опытный отсчитывает так, чтобы рвалась через cook_land после касания
	local fuse = K.g_fuse[1] + math.random() * (K.g_fuse[2] - K.g_fuse[1])
	local cook = 0
	if d.cook then cook = math.max(0, math.min(line(K.g_cook_max, rs(f)), fuse - tl - K.g_cook_land)) end
	g.boom = S.t + fuse - cook
	S.grenades[#S.grenades + 1] = g
	S.gs[f.side].thrown = S.gs[f.side].thrown + 1
	-- свои видели замах: знают, куда летит
	for _, m in ipairs(f.sq.members) do
		if m.hp > 0 then g.aware[m.id] = { phase = 'known', t = S.t, x = lx, y = ly, z = lz, src = 'own' } end
	end
	S:emit('grenade_throw', { npc = f.id, sq = f.sq.id, x = g.x0, y = g.y0, z = g.z0, tx = th.mx, ty = th.ay, tz = th.mz,
		lx = lx, ly = ly, lz = lz, fly = tl, fuse = fuse - cook, cook = cook, u = u, wall = tb and 1 or 0 })
end

function G.pos(S, g)
	local t = math.min(S.t - g.t0, g.land_t)
	if t >= g.land_t then return g.lx, g.ly + 0.1, g.lz end
	return G.at(g, t)
end

-- ─── заметить, крикнуть, понять, где ────────────────────────────────────────────────────────
local EYE_H = { [false] = 1.6, [true] = 1.0 }
local function eye_y(f) return f.y + (f.prone and 0.35 or EYE_H[f.cr]) end

-- Опасно = ближе r + 2 к тому месту, где, по его знанию, граната (правило юзера 24.10 «слышишь "граната" — меняй
-- позицию»; без «за мной укрытие» одним лучом из прикидки — в игре это врало, бой #23). Укрытие — только при выборе,
-- КУДА лечь: от каждой из точек «прикидка ± 1.5 м» дальше радиуса или за преградой.
local function in_danger(g, px, py, pz, x, y, z) return d3(x, y + 0.8, z, px, py, pz) <= g.typ.blast_r + 2 end
local OFFS = { { 0, 0 }, { 1.5, 0 }, { -1.5, 0 }, { 0, 1.5 }, { 0, -1.5 } }
local function lie_safe(g, px, py, pz, x, y, z, h)
	for _, o in ipairs(OFFS) do
		local qx, qz = px + o[1], pz + o[2]
		if d3(x, y + h * 0.5, z, qx, py, qz) <= g.typ.blast_r + 2 and W.clear(qx, py + 0.3, qz, x, y + h, z) then return false end
	end
	return true
end

-- «Граната!»: свои рядом сразу уходят от прикидки (ошибка по рангу) и g_look секунд ищут её глазами
local function shout(S, f, g, gx, gy, gz)
	if not S.doc[f.side].shout or (g.shout and g.shout[f.sq.id]) then return end
	g.shout = g.shout or {}
	g.shout[f.sq.id] = f.id
	S:emit('grenade_shout', { npc = f.id, sq = f.sq.id, g = g.id })
	for _, m in ipairs(f.sq.members) do
		if m.hp > 0 and not g.aware[m.id] and (m.x - f.x) ^ 2 + (m.z - f.z) ^ 2 < 900 then
			local e = skill(S, m, 'g_est_err')
			local k = { phase = 'look', t = S.t + skill(S, m, 'g_look'), src = 'shout',
				x = g.lx + gauss() * e, y = g.ly, z = g.lz + gauss() * e }
			g.aware[m.id] = k
			S:emit('grenade_est', { npc = m.id, sq = m.sq.id, g = g.id, err = d3(k.x, k.y, k.z, g.lx, g.ly, g.lz) })
			G.decide(S, m, g, k)
		end
	end
end

function G.perceive(S, g)
	local K = S.K
	local gx, gy, gz = G.pos(S, g)
	for _, f in ipairs(S.fighters) do
		if f.hp > 0 then
			local k = g.aware[f.id]
			local ex, ey, ez = f.x, eye_y(f), f.z
			local dd = d3(ex, ey, ez, gx, gy, gz)
			if (not k or k.phase == 'look') and dd < K.g_see then
				local hx, hz = gx - f.x, gz - f.z
				local hd = math.sqrt(hx * hx + hz * hz)
				-- ищущий по крику смотрит в ту сторону — FOV не мешает
				local in_fov = k or hd < 4 or (hx * f.fx + hz * f.fz) / hd >= S.K.fov_cos
				if in_fov and W.clear(ex, ey, ez, gx, gy, gz) then
					k = { phase = 'react', t = S.t + skill(S, f, 'g_react') }
					g.aware[f.id] = k
					S:emit('grenade_seen', { npc = f.id, sq = f.sq.id, g = g.id, d = dd })
					shout(S, f, g, gx, gy, gz)
				end
			end
			if k and k.phase == 'react' and S.t >= k.t then
				-- увидел: любой читает дугу — бежит от точки падения; ранг — только ошибка точки
				local e = skill(S, f, 'g_eye_err')
				k.phase, k.x, k.y, k.z, k.src = 'known', g.lx + gauss() * e, g.ly, g.lz + gauss() * e, 'eye'
				G.decide(S, f, g, k)
			elseif k and k.phase == 'look' and S.t >= k.t then
				k.phase = 'known'                -- так и не увидел — остаётся прикидка по крику
			elseif k and k.phase == 'known' and k.src == 'own' and not k.done then
				G.decide(S, f, g, k)
			end
		end
	end
end

-- знает, где граната → в опасности ли он и куда бежать (уже бежит — проверить, не туда ли: знание уточнилось)
function G.decide(S, f, g, k)
	k.done = true
	local d = S.doc[f.side]
	if not d.dodge then return end
	local lie = d.prone and 0.4 or 1.0
	if f.dodge then
		if f.dodge ~= g or not f.dest then return end
		if lie_safe(g, k.x, k.y, k.z, f.dest[1], f.dest[2], f.dest[3], lie) then return end
	elseif not in_danger(g, k.x, k.y, k.z, f.x, f.y, f.z) then return end
	local left = math.max(0.5, 3.0 - (S.t - g.t0))          -- сколько, по его прикидке, осталось (запала он не знает)
	local reach = math.max(3, math.min(14, 4.5 * left))
	-- к врагу и на его линию огня — хуже (в игре: отличный спринт прямо на противника, задело и добили)
	local m = S:last_mem(f)
	local best, bs
	-- безопасного нет — хоть подальше (игра, бой 225832-16: F1 в 0.3 м, лёг в 1.2 м от неё)
	local far, fd, d0 = nil, nil, d3(k.x, k.y, k.z, f.x, f.y, f.z)
	for _, it in ipairs(S.w:around(f.node, reach)) do
		local x, y, z = S.w:xyz(it[1])
		local dg = d3(k.x, k.y, k.z, x, y, z)
		if not fd or dg > fd then far, fd = it[1], dg end
		local s = it[2]
		if m then
			s = s + 1.5 * math.max(0, math.sqrt((m.x - f.x) ^ 2 + (m.z - f.z) ^ 2) - math.sqrt((m.x - x) ^ 2 + (m.z - z) ^ 2))
			if (not bs or s + 4 < bs) and W.clear(m.x, m.y + 1.6, m.z, x, y + 0.5, z) then s = s + 4 end
		end
		if (not bs or s < bs) and lie_safe(g, k.x, k.y, k.z, x, y, z, lie) then best, bs = it[1], s end
	end
	local safe = best ~= nil
	if not best and far and fd > d0 + 1 then best = far end
	if f.windup then f.windup, f.throw, f.gren = nil, nil, f.gren + 1 end
	local again = f.dodge == g
	f.dodge, f.dodge_end, f.down_t = g, nil, nil
	f.act = 9011
	if best then S:go(f, best, 'run'); f.cr, f.prone = false, false else S:stop(f) end
	if not again then f.move_at = S.t + S.K.g_start end
	if not again then S.gs[f.side].dodges = S.gs[f.side].dodges + 1 end
	S:emit(again and 'grenade_replan' or 'grenade_dodge', { npc = f.id, sq = f.sq.id, g = g.id, to = best or -1, d = bs or 0,
		src = k.src, err = d3(k.x, k.y, k.z, G.pos(S, g)), safe = safe and 1 or 0 })
end

-- шаг уклоняющегося (зовёт think): добежал → ложится (или садится, если доктрина не ложится)
function G.dodge_step(S, f)
	local d = S.doc[f.side]
	if f.path then return end
	if d.prone then
		if not f.down_t then f.down_t = S.t + S.K.g_down; f.cr = true; f.act = 9012 end
		if S.t >= f.down_t and not f.prone then
			f.prone = true
			S:emit('grenade_prone', { npc = f.id, sq = f.sq.id })
		end
	else
		f.cr = true
	end
end

-- ─── взрыв ──────────────────────────────────────────────────────────────────────────────────
local function los_frac(bx, by, bz, t)
	local n = 0
	local hs = t.prone and { 0.15, 0.3, 0.4 } or t.cr and { 0.3, 0.75, 1.0 } or { 0.45, 1.25, 1.6 }
	for _, h in ipairs(hs) do
		if W.clear(bx, by, bz, t.x, t.y + h, t.z) then n = n + 1 end
	end
	return n / 3
end

function G.boom(S, g)
	local K, typ = S.K, g.typ
	local bx, by, bz = G.pos(S, g)
	by = by + 0.3
	local hit, kill, ff = 0, 0, 0
	for _, t in ipairs(S.fighters) do
		if t.hp > 0 then
			local ch = t.prone and 0.25 or (t.cr and 0.75 or 1.0)
			local d = math.max(0.7, d3(bx, by, bz, t.x, t.y + ch, t.z))
			if d < typ.frags_r then
				local vis = los_frac(bx, by, bz, t)
				local dmg = 0
				if d < typ.blast_r then
					dmg = typ.blast * typ.blast_r ^ 2 / (2 * d * d + typ.blast_r ^ 2) * vis * K.armor_blast
				end
				-- осколки летят во все стороны: в лежащего попадают те, что ушли почти вдоль земли
				local area = 0.45 * (t.prone and 0.4 or t.cr and 1.1 or 1.75) * vis
				local nf = poisson(typ.frags * area / (4 * math.pi * d * d))
				dmg = dmg + nf * typ.frag * K.armor_frag
				if d < 12 then t.sup = t.sup + 2 end
				if dmg > 0 then
					hit = hit + 1
					if S:damage(t, g.owner, dmg, d, true) then
						kill = kill + 1
						if t.side == g.side then ff = ff + 1 end
					end
				end
			end
		end
	end
	local st = S.gs[g.side]
	st.booms, st.kills, st.ff = st.booms + 1, st.kills + kill - ff, st.ff + ff
	S:emit('grenade_boom', { npc = g.owner.id, sq = g.owner.sq.id, g = g.id, x = bx, y = by, z = bz, hit = hit, kill = kill, ff = ff })
	if S.K.h_on then require('hear').sound(S, g.owner, 'boom', bx, by, bz, S.K.h_boom[1], S.K.h_boom[2]) end
	for _, f in ipairs(S.fighters) do
		if f.dodge == g then f.dodge_end = S.t + (S.doc[f.side].prone and skill(S, f, 'g_get_up') or 0.5) end
	end
end

-- ─── шаг мира ───────────────────────────────────────────────────────────────────────────────
function G.update(S)
	local live = {}
	for _, g in ipairs(S.grenades) do
		if S.t >= g.boom then G.boom(S, g)
		else
			G.perceive(S, g)
			live[#live + 1] = g
		end
	end
	S.grenades = live
end

return G
