-- Встречный бой 4×4 (23.10): поле матча №26 на Армейках, обе стороны одинаковые (ранги, стволы) — разница только
-- в доктрине, которую подставляет sweep.lua. Обе идут к точке с поводком 3 («замысел»).
return {
	id = 'duel4', level = 'l07_military', limit = 300, seed = 1,
	zone = { x = 97.3, z = 305.2, r = 15 },
	sides = {
		A = { grenade = 'none', squads = { {
			comm = 'stalker', n = 4, ranks = { 9000, 7000, 8000, 6000 },
			wpn = { 'w_rifle', 'w_rifle', 'w_smg', 'w_rifle' },
			at = { x = 25.9, y = -15.1, z = 231.8 },
			orders = { { at = 0, route = { { x = 97.3, z = 305.2, g = 3 } } } },
		} } },
		B = { grenade = 'none', squads = { {
			comm = 'monolith', n = 4, ranks = { 9000, 7000, 8000, 6000 },
			wpn = { 'w_rifle', 'w_rifle', 'w_smg', 'w_rifle' },
			at = { x = 52.6, y = -18.5, z = 358.3 },
			orders = { { at = 0, route = { { x = 97.3, z = 305.2, g = 3 } } } },
		} } },
	},
}
