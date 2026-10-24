-- hear.lua — слух в двойнике (24.10.2026). До него боец знал о враге только глазами (и «по мне стреляют —
-- знаю откуда» без ошибки), а в игре слух — главный источник знания: 3 серии, 3351 «услышал» (73% выстрелы).
--
-- Движок (сверено по исходнику):
--   сила у слушателя  IGame_Level.cpp SoundEvent_Register: P = (1 − d / ai) × громкость × заглушение.
--                     ai (дальность для ИИ) и громкость зашиты в .ogg (комментарий v3, oggp.py в scratchpad).
--   заглушение        SoundRender_Core_Processor.cpp get_occlusion_to: произведение коэффициентов стен по лучу
--                     из level.som. У l02/l03/l07 level.som НЕТ (распаковка 24.10) → стены не глушат: h_occ = 1.
--   порог             sound_memory_manager.cpp: слышит, если P ≥ порога; порог = max(порог, P) после КАЖДОГО звука
--                     (и своего: стрелок глохнет от своих выстрелов), спадает ×0.95 каждые 250 мс до 0.05 —
--                     оглушение: после выстрела рядом тихое ~10–15 с не слышно.
--   выстрел врага     там же: «this is fake!» — стрелок идёт в память, как будто ранил; место звука — точное.
--   шаги              step_manager.cpp: play_no_feedback → ИИ шагов НЕ слышит вообще. Юзер 24.10: «шаги сразу» —
--                     наша условность (в игру — отдельно, через Lua).
--
-- Наши решения (юзер 24.10): место «на слух» с ошибкой, растущей с дистанцией (σ = h_err × d, ранг слабо);
-- свой/чужой — как в движке (различает всегда).

local W = require 'world'

local H = {}

local EPS = 0.0001   -- EPS_S движка: тише — событие не рождается вовсе

-- Звуки: { ai = дальность для ИИ, м; vol = громкость }. Выстрелы — *_shot.ogg (ak74 110/1.45, pm 60/0.6,
-- toz34 50/0.7, svd 70/0.8, mp5 60/1.5). Какой файл берёт NPC (_shot или громкий _shoot 200/2.0) — сверить силой
-- из игры (alert_hear.p). С глушителем медиана 7.5 м.
H.WORLD = {
	h_on = true,                  -- false — как раньше: слуха нет, «по мне стреляют» = точное место стрелка
	h_th_min = 0.05,              -- минимум порога (m_min_sound_threshold, ltx sound_threshold)
	h_decay = 0.95,               -- спад порога за 250 мс (self_decrease_factor)
	h_occ = 1,                    -- множитель за преграду между звуком и ухом (1 = как в игре без level.som)
	h_err = 0.15,                 -- σ места на слух, доля дистанции (новичок; легенда — ×0.7)
	h_turn = 1.5,                 -- услышал врага и не видит — смотрит туда столько, с
	h_shot = { w_rifle = { 110, 1.45 }, w_smg = { 60, 1.5 }, w_pistol = { 60, 0.6 },
	           w_shotgun = { 50, 0.7 }, w_sniper = { 70, 0.8 } },
	h_hit = { 25, 1 },            -- пуля ударилась рядом (material/bullet/collide)
	h_boom = { 130, 2 },          -- взрыв гранаты (f1_explode)
	-- шаги — условность (в игре ИИ их не слышит); ai по походке, громкость 1 (у NPC шаг 15 м — «бег»)
	h_step = { run = 15, walk = 8, crouch = 3 },
	h_step_dt = { run = 0.35, walk = 0.5, crouch = 0.6 },   -- шаг раз в столько, с
}

local function rs(f) return math.max(0, math.min(1, f.rank / 14500)) end
local function gauss()
	local u = math.max(1e-9, math.random())
	return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * math.random())
end

-- порог слушателя на сейчас (спад с прошлого звука)
local function threshold(S, f)
	local K = S.K
	local th = f.hth or K.h_th_min
	if f.hth_t then th = th * K.h_decay ^ ((S.t - f.hth_t) / 0.25) end
	return math.max(th, K.h_th_min)
end

-- Звук: src — кто издал (может быть nil), kind — 'shot'|'hit'|'step'|'boom', (x, y, z) — где, ai/vol — параметры.
function H.sound(S, src, kind, x, y, z, ai, vol)
	local K = S.K
	for _, f in ipairs(S.fighters) do
		if f.hp > 0 and not (kind == 'step' and S.doc[f.side].steps == false) then   -- ваниль шагов не слышит
			local d = math.sqrt((f.x - x) ^ 2 + (f.y - y) ^ 2 + (f.z - z) ^ 2)
			if d < ai then
				local p = (1 - d / ai) * vol
				if K.h_occ < 1 and not W.clear(f.x, f.y + 1.6, f.z, x, y + 0.5, z) then p = p * K.h_occ end
				if p > EPS then
					local th = threshold(S, f)
					local heard = p >= th
					f.hth, f.hth_t = math.max(th, p), S.t
					if heard and src and src ~= f and src.side ~= f.side and kind ~= 'hit' then
						-- где на слух: σ растёт с дистанцией, ранг — слабо
						local s = K.h_err * d * (1 - 0.3 * rs(f))
						local ex, ez = src.x + gauss() * s, src.z + gauss() * s
						f.mem[src.id] = { x = ex, y = src.y, z = ez, t = S.t, heard = true }
						f.hear = { x = ex, z = ez, t = S.t }
						-- в trace — раз в секунду на пару «кто — кого» и вид звука
						f.hear_log = f.hear_log or {}
						local key = src.id .. kind
						if S.out and S.t - (f.hear_log[key] or -9) >= 1 then
							f.hear_log[key] = S.t
							S:emit('hear', { npc = f.id, sq = f.sq.id, who = src.id, kind = kind, d = d, p = p, th = th,
								err = math.sqrt((ex - src.x) ^ 2 + (ez - src.z) ^ 2), px = ex, pz = ez })
						end
					end
				end
			end
		end
	end
end

-- выстрел f по t: сам выстрел (все слышат стрелка) + удар пули рядом с целью
function H.shot(S, f, t)
	local K = S.K
	local s = K.h_shot[f.wk] or K.h_shot.w_rifle
	H.sound(S, f, 'shot', f.x, f.y + 1.4, f.z, s[1], s[2])
	H.sound(S, f, 'hit', t.x + (math.random() - 0.5) * 2, t.y + 0.3, t.z + (math.random() - 0.5) * 2, K.h_hit[1], K.h_hit[2])
end

-- шаги: зовёт tick после движения
function H.step(S, f)
	if not f.path then f.step_t = nil; return end
	local K = S.K
	local gait = f.cr and 'crouch' or (f.how == 'run' and 'run' or 'walk')
	f.step_t = (f.step_t or 0) - 0.1
	if f.step_t > 0 then return end
	f.step_t = K.h_step_dt[gait]
	H.sound(S, f, 'step', f.x, f.y + 0.5, f.z, K.h_step[gait], 1)
end

-- смотрит ли на услышанное (не видит врага, звук свежий)
function H.look(S, f)
	local h = f.hear
	if not h or f.target_vis or S.t - h.t > S.K.h_turn then return end
	local dx, dz = h.x - f.x, h.z - f.z
	local L = math.sqrt(dx * dx + dz * dz)
	if L > 1 then return dx / L, dz / L end
end

return H
