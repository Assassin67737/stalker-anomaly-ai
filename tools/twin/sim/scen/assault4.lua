-- Штурм позиции перекатами 4×4 (24.10): как hold4 (B сидит на точке №26 и держит), но A идёт «по обстановке»
-- (g=2) и при контакте — перекатами: пара бежит, пара давит (fire.lua, sim.lua bound_step).
-- Сравнение: --set bound=false (тот же штурм без перекатов), --set sup_self=0, --set panic=false.
return {
	id = 'assault4', level = 'l07_military', limit = 600, seed = 1,
	zone = { x = 97.3, z = 305.2, r = 15 },
	sides = {
		A = { grenade = 'none', squads = { {
			comm = 'stalker', n = 4, ranks = { 9000, 7000, 8000, 6000 },
			wpn = { 'w_rifle', 'w_rifle', 'w_smg', 'w_rifle' },
			at = { x = 25.9, y = -15.1, z = 231.8 },
			orders = { { at = 0, bound = true, route = { { x = 97.3, z = 305.2, g = 2 } } } },
		} } },
		B = { grenade = 'none', squads = { {
			comm = 'stalker', n = 4, ranks = { 9000, 7000, 8000, 6000 },
			wpn = { 'w_rifle', 'w_rifle', 'w_smg', 'w_rifle' },
			at = { x = 97.3, y = -17, z = 305.2 }, free = false,
		} } },
	},
}
