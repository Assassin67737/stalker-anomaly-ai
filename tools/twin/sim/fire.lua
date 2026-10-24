-- fire.lua — как бойцы стреляют (24.10.2026, разговор с юзером: «реализм — вдохновение, честность — эталон»).
--
-- Ваниль (spawn_sections_general.ltx, fire_queue_sim_default_*): ранг = БОЛЬШЕ огня — опытный бьёт длиннее (6–14
-- вплотную против 3–8), чаще и втрое кучнее; плюс кубики «промахнись на 0.2–2 м». Страха, отдачи, дисциплины нет.
-- Здесь — по-другому:
--   ОЧЕРЕДЬ — выбор под задачу, а не уровень. Отдача: каждый следующий патрон очереди хуже (σ × (1 + rec·i)),
--   ранг держит отдачу. Обученный на дистанции бьёт одиночными и двойками, вплотную — длинной у всех.
--   РЕЖИМЫ: прицельный (видит) · в упор (< close_d) · подавляющий (знает место, не видит) · паника.
--   ПАНИКА: прижатость (f.sup) выше выдержки → до пустого магазина почти без пауз, разброс ×panic_sigma, доворот
--   не до конца (panic_deg), бьёт и по свежему месту. Выдержка = panic_thr × (0.5 + 1.5·ранг) × лор группировки
--   (юзер: Монолит не паникует — «пусть все боятся»). Патроны — без отдельного счёта: магазин настоящий,
--   паникёр сам делает себе пустой магазин.
--   ПОДАВЛЕНИЕ (честно — только по тому, что знает): сам — коротко, по месту, где цель только что пропала
--   (sup_self с); по роли (перекаты, bound) — долго, по самому свежему месту, которое знает отряд (переклички).
--   Пули у точки прижимают тех, кто рядом (sup_near м): «держи голову ниже». Попасть можно, только если враг
--   правда там и виден хоть краем.
-- Каждый выстрел — звук (hear.lua): зажатая очередь выдаёт стрелка и глушит его самого.

local H = require 'hear'
local W = require 'world'

local F = {}

-- СОСУД (24.10, VESSEL_AUDIT.md §2.6): по умолчанию — как тело в игре: отдачи по очереди у NPC в движке нет
-- (WeaponDispersion.cpp), паники и прижатия нет (это психика из нашего замысла, не тело). recoil / panic / pin в мире
-- по умолчанию НЕ заданы: тогда решает доктрина (f_* — да, остальные — нет). Задан в мире (перебор, --set) — главнее
-- доктрины: false выключает у всех, true включает у всех, кроме доктрин с явным false (ваниль).
F.WORLD = {
	burst = true,                 -- false — как раньше (ровный темп w.rate, без очередей и отдачи)
	-- recoil — отдача по очереди (σ × (1 + rec·i)); pin — прижатие (sup > sup_pin: не высовывается и не стреляет);
	-- panic — паника. Все три — наш замысел, в игре нет; по умолчанию не заданы (см. выше, F.on)
	close_d = 10,                 -- м: ближе — «в упор», длинная у всех
	-- длина очереди по дистанции: { новичок {min, max}, легенда {min, max} } (между ними — по рангу)
	q_near = { { 3, 6 }, { 2, 4 } },        -- 10–15 м
	q_mid  = { { 3, 5 }, { 1, 3 } },        -- 15–30 м
	q_far  = { { 2, 4 }, { 1, 1 } },        -- дальше 30 м
	q_close = { 4, 10 },                    -- в упор (все)
	q_sup = { 5, 10 },                      -- подавление
	-- пауза между очередями (перенаведение после отдачи), с: { новичок {min, max}, легенда {min, max} }
	pause = { { 0.9, 1.4 }, { 0.35, 0.6 } },
	pause_close = { 0.2, 0.4 },
	pause_sup = { 0.3, 0.6 },
	pause_panic = { 0.05, 0.15 },
	-- отдача: рост σ на патрон очереди { новичок, легенда }
	rec = { w_rifle = { 0.6, 0.12 }, w_smg = { 0.4, 0.08 }, w_pistol = { 0.25, 0.05 }, w_shotgun = { 0, 0 }, w_sniper = { 0, 0 } },
	-- темп внутри очереди (выстрелов/с) и потолок очереди по классу
	cyc = { w_rifle = 10, w_smg = 13, w_pistol = 4, w_shotgun = 1.2, w_sniper = 0.9 },
	qmax = { w_shotgun = 2, w_sniper = 1 },
	acc_burst = 1.0,              -- множитель доли довёрнутых выстрелов при очередях (S:bullet); 1.0 — как в игре
	-- паника
	panic_thr = 2.5,              -- выдержка новичка ×0.5, легенды ×2 (f.sup: +0.25 за пулю рядом, +1 за попадание, −0.5/с)
	panic_out = 0.4,              -- выход из паники: sup < выдержка × это
	panic_sigma = 2.5,
	panic_deg = 50,               -- доворот в панике: жмёт, не довернувшись
	lore = { monolith = 1e9, army = 1.4, dolg = 1.3, killer = 1.3, renegade = 0.8, bandit = 0.7 },
	-- подавление
	sup_self = 2.5,               -- с: столько после пропажи цели бьёт по её месту сам
	sup_mem = 15,                 -- с: по роли — знание отряда не старше этого
	sup_near = 3,                 -- м: пули у точки прижимают тех, кто ближе
	-- прижатость за пулю: по цели и у точки подавления. Прежний двойник давал 0.25 при ровном темпе ~1.5 выстр/с;
	-- очередями огня ~вдвое больше — за пулю вдвое меньше, иначе под огнём ломается любой (24.10, первый замер)
	sup_bullet = 0.13,
	sup_pin = 0.7,                -- прижатость выше — в укрытии не высовывается (sim.lua, ветка укрытия)
	sup_add = 0.15,
	bound_leg = 8,                 -- м: перебежка в перекатах (к укрытию у этой точки)
	bound_max = 8,                -- с: дольше не бежит — меняются
}

local function lerp(a, b, s) return a + (b - a) * s end

-- включена ли у стороны психика/отдача k ('panic' | 'pin' | 'recoil'): мир (если задан) главнее доктрины
function F.on(S, side, k)
	local w, d = S.K[k], S.doc[side][k]
	if d == false or w == false then return false end
	return w == true or d == true
end
local function skill(f) return math.max(0, math.min(1, f.rank / 20000)) end
local function rnd(lo, hi) return lo + math.random() * (hi - lo) end
local function irnd(lo, hi) return math.floor(rnd(lo, hi + 0.999)) end

-- выдержка бойца (f.sup, после которой паника)
function F.nerve(S, f)
	local K = S.K
	return K.panic_thr * (0.5 + 1.5 * skill(f)) * (K.lore[f.comm] or 1)
end

-- паника: войти / выйти (с гистерезисом); зовёт think раз в шаг
function F.update_panic(S, f)
	local K = S.K
	if not F.on(S, f.side, 'panic') then f.panic = nil; return end
	local nv = F.nerve(S, f)
	if not f.panic and f.sup > nv then
		f.panic = true
		S:emit('panic', { npc = f.id, sq = f.sq.id, sup = f.sup, nerve = nv })
	elseif f.panic and f.sup < nv * K.panic_out then
		f.panic = nil
		S:emit('panic_end', { npc = f.id, sq = f.sq.id })
	end
end

-- план очереди: размер, пауза после
local function plan(S, f, mode, d)
	local K, s = S.K, skill(f)
	local size, pause
	if mode == 'panic' then
		size, pause = f.mag, rnd(K.pause_panic[1], K.pause_panic[2])
	elseif mode == 'sup' then
		size, pause = irnd(K.q_sup[1], K.q_sup[2]), rnd(K.pause_sup[1], K.pause_sup[2])
	elseif d < K.close_d then
		size, pause = irnd(K.q_close[1], K.q_close[2]), rnd(K.pause_close[1], K.pause_close[2])
	else
		local q = d < 15 and K.q_near or d < 30 and K.q_mid or K.q_far
		size = irnd(math.floor(lerp(q[1][1], q[2][1], s) + 0.5), math.floor(lerp(q[1][2], q[2][2], s) + 0.5))
		pause = rnd(lerp(K.pause[1][1], K.pause[2][1], s), lerp(K.pause[1][2], K.pause[2][2], s))
	end
	local cap = K.qmax[f.wk]
	if cap and mode ~= 'panic' then size = math.min(size, cap) end
	return math.max(1, math.min(size, f.mag)), pause
end

-- угол взгляда на точку, градусы
local function angle_to(f, x, z)
	local a = math.atan2(f.fx, f.fz) - math.atan2(x - f.x, z - f.z)
	return math.abs(math.deg((a + math.pi) % (2 * math.pi) - math.pi))
end

-- Выстрел. aim = { t = цель (если видна) | nil, x, y, z (точка), d, mode = 'aim'|'sup'|'panic' }.
-- Возвращает true, если нажал спуск в этот шаг.
function F.shoot(S, f, aim)
	local K, w = S.K, f.wpn
	local burst = K.burst and S.doc[f.side].burst ~= false      -- доктрина стороны может стрелять по-старому (ваниль)
	if f.reload_t > 0 or aim.d > w.max then return end
	if f.mag <= 0 then f.reload_t = w.reload; f.act = 9005; f.burst = 0; return end
	-- ворота: доворот (в панике — грубо), прицеливание, ствол
	local gate = aim.mode == 'panic' and K.panic_deg or K.aim_deg
	local key = aim.t and aim.t.id or 'pt'
	if f.aim_tgt ~= key or angle_to(f, aim.x, aim.z) > gate then
		f.aim_tgt, f.aim_since = key, nil
		if angle_to(f, aim.x, aim.z) > gate then return end
	end
	f.aim_since = f.aim_since or S.t
	if S.t - f.aim_since < K.aim_time then return end
	local clear = S:muzzle_clear(f, aim.t or { x = aim.x, y = aim.y - 1.25, z = aim.z, cr = false })
	-- ваниль C++ ствол не проверяет (замер: каждый пятый выстрел в препятствие ближе 10 м) — пуля в стену
	if not clear and K.gate_muzzle and S.doc[f.side].gate_muzzle ~= false then f.muzzle_wait = (f.muzzle_wait or 0) + 0.1; return end
	f.fire_t = (f.fire_t or 0) - 0.1
	if f.fire_t > 0 then return end
	-- очередь: новая — план; в очереди — следующий патрон через 1/cyc
	local smul = 1
	if burst then
		if (f.burst or 0) <= 0 then
			f.burst, f.after = plan(S, f, aim.mode, aim.d)
			f.shot_i = 0
		end
		local r = K.rec[f.wk] or K.rec.w_rifle
		local rec = F.on(S, f.side, 'recoil') and (aim.mode == 'panic' and r[1] or lerp(r[1], r[2], skill(f))) or 0
		smul = (1 + rec * f.shot_i) * (aim.mode == 'panic' and K.panic_sigma or 1)
		f.shot_i = f.shot_i + 1
		f.burst = f.burst - 1
		f.fire_t = f.burst > 0 and 1 / (K.cyc[f.wk] or 10) or f.after
	else
		f.fire_t = (0.6 + math.random() * 0.8) / w.rate
	end
	f.mag = f.mag - 1
	f.firing_t = S.t
	-- попадание: только если цель правда там (видима — aim.t; подавление — враг у точки и виден хоть краем)
	local victim, vd = aim.t, aim.d
	if not victim then
		local best
		for _, e in ipairs(S.fighters) do
			if e.side ~= f.side and e.hp > 0 then
				local dd = math.sqrt((e.x - aim.x) ^ 2 + (e.z - aim.z) ^ 2)
				if dd < 1.5 and (not best or dd < best) then victim, best = e, dd end
			end
		end
		if victim then vd = math.sqrt((victim.x - f.x) ^ 2 + (victim.z - f.z) ^ 2) end
	end
	-- ствол упёрся (ваниль стреляет и так) — пуля всё равно летит по материалам: куст и доска не стена
	local hit, zn, zk = 0, nil, nil
	if victim then hit, zn, zk = S:bullet(f, victim, vd, smul, burst and K.acc_burst or 1) end
	if S.out then S:emit('shot', { npc = f.id, sq = f.sq.id, wpn = f.wk, enemy = aim.t and aim.t.id or -1, d = aim.d,
		mc = clear and 1 or 0, ab = angle_to(f, aim.x, aim.z), cr = f.cr and 1 or 0, aid = f.act, aid2 = -1,
		ec = aim.t and (W.clear(f.x, f.y + (f.cr and 1.0 or 1.6), f.z, aim.t.x, aim.t.y + (aim.t.cr and 0.75 or 1.25), aim.t.z) and 1 or 0) or 0,
		mode = aim.mode, i = f.shot_i or 0, px = f.x, py = f.y, pz = f.z, ex = aim.x, ez = aim.z }) end
	-- пули рядом прижимают: цель (как раньше) и всех у точки подавления
	for _, e in ipairs(S.fighters) do
		if e.side ~= f.side and e.hp > 0 then
			if e == aim.t then e.sup = e.sup + (burst and K.sup_bullet or 0.25)
			elseif math.sqrt((e.x - aim.x) ^ 2 + (e.z - aim.z) ^ 2) < K.sup_near then e.sup = e.sup + K.sup_add end
		end
	end
	if K.h_on then
		H.sound(S, f, 'shot', f.x, f.y + 1.4, f.z, (K.h_shot[f.wk] or K.h_shot.w_rifle)[1], (K.h_shot[f.wk] or K.h_shot.w_rifle)[2])
		H.sound(S, f, 'hit', aim.x + (math.random() - 0.5) * 2, aim.y - 1, aim.z + (math.random() - 0.5) * 2, K.h_hit[1], K.h_hit[2])
	elseif aim.t then
		aim.t.mem[f.id] = { x = f.x, y = f.y, z = f.z, t = S.t }
	end
	if hit > 0 then S:damage(victim, f, S:bullet_dmg(f) * hit, vd, false, zn, zk) end
	return true
end

-- самое свежее место врага, которое знает отряд (переклички внутри отряда), не старше sup_mem
function F.squad_mem(S, sq)
	local best
	for _, m in ipairs(sq.members) do
		if m.hp > 0 then
			for _, e in pairs(m.mem) do
				if S.t - e.t < S.K.sup_mem and (not best or e.t > best.t) then best = e end
			end
		end
	end
	return best
end

return F
