-- Котёл №1 (21.10): генерал (A) против Монолита (B, ИИ двойника) на месте ночного матча №26.
-- A — два отряда одиночек без приказов: стоят, пока генерал не скажет. B — два отряда Монолита
-- идут к точке (поводок 3 — «замысел»), второй — с отставанием 20 с. Генерал может приказать и им.
return {
	id = 'kotel1', level = 'l07_military', limit = 900, seed = 1,
	zone = { x = 97.3, z = 305.2, r = 15 },
	sides = {
		A = { squads = {
			{ name = 'Альфа', comm = 'stalker', n = 4, free = false, ranks = { 12669, 7490, 8695, 9000 },
			  wpn = { 'w_rifle', 'w_sniper', 'w_rifle', 'w_rifle' }, at = { x = 25.9, y = -15.1, z = 231.8 } },
			{ name = 'Браво', comm = 'stalker', n = 4, free = false, ranks = { 28102, 6000, 7000, 8000 },
			  wpn = { 'w_rifle', 'w_shotgun', 'w_smg', 'w_rifle' }, at = { x = 35, y = -15, z = 222 } },
		} },
		B = { squads = {
			{ name = 'Монолит-1', comm = 'monolith', n = 4, ranks = { 3005, 5590, 9621, 3811 }, wpn = { 'w_rifle' },
			  at = { x = 52.6, y = -18.5, z = 358.3 },
			  orders = { { at = 0, route = { { x = 97.3, z = 305.2, g = 3 } } } } },
			{ name = 'Монолит-2', comm = 'monolith', n = 4, ranks = { 6000, 7000, 4000, 9000 }, wpn = { 'w_rifle', 'w_smg' },
			  at = { x = 62, y = -18, z = 366 },
			  orders = { { at = 20, route = { { x = 97.3, z = 305.2, g = 3 } } } } },
		} },
	},
}
