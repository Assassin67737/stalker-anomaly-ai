-- Быстрая проверка 24.10 (вечер, новый сосуд): переживают ли выводы night_1024 честное тело (встречный бой, мир по умолчанию:
-- слух вкл, запал 3.2–4.2, без кубиков). Было: гранаты вообще +0.39 в duel4; v2 против ванили ≈ 0; отсчёт +0.06;
-- крик и память ≈ 0. ~2600 боёв на пару → ±0.03. tools/twin/sim/sweep.sh sweeps/night_quick.lua 5
return {
	name = 'night_quick',
	scen = { 'duel4' },
	pairs = {
		{ 'varka', 'none' },
		{ 'varka', 'vanilla' },
		{ 'varka', 'nocook' },
		{ 'varka', 'noshout' },
		{ 'varka', 'oldmem' },
	},
	world = { h_on = { true } },
	seeds = 1300,
	snap = 30,
}
