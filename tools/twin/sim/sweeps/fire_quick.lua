-- Быстрая проверка 24.10 (вечер, новый сосуд — VESSEL_AUDIT.md): переживают ли выводы fire_1024 честное тело.
--   1. наш огонь против ванили целиком (было +0.235);
--   2. перекаты против простого хода при прижатии и без (было: с прижатием перекаты лучше, без — хуже).
-- ~2600 боёв на пару → интервал ±0.03. tools/twin/sim/sweep.sh sweeps/fire_quick.lua 6
return {
	name = 'fire_quick',
	scen = { 'assault4', 'duel4' },
	pairs = {
		{ 'f_full', 'vanilla_all' },
		{ 'f_full', 'f_nobound' },
		{ 'f_nobound', 'vanilla_all' },
	},
	world = { sup_pin = { 0.7, 99 } },
	seeds = 325,
	snap = 30,
}
