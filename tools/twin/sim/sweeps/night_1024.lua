-- Ночь 24.10.2026: гранаты v2 + слух (hear.lua). Запуск — только по слову юзера:
--   tools/twin/sim/sweep.sh sim/sweeps/night_1024.lua
-- Вопросы:
--   1. Гранаты (как grenades.lua): цена пакета varka против none/vanilla и по частям (лёжа, крик, отсчёт, память).
--   2. Слух: меняет ли он ответы на вопрос 1 (h_on false/true) — если пакет гранат выигрывает только «глухим»,
--      выигрыш держался на точном знании «откуда стреляют», которого в игре нет.
--   3. Перевороты по рангу, умению (g_skill_k), меткости (acc), кубикам (g_dice), запалу (g_fuse).
-- Сетка как у grenades.lua без g_see (×2 на слух вместо ×2 на g_see): 86 400 боёв, ~2.5 ч на 11 потоках.
return {
	name = 'night_1024',
	scen = { 'duel4', 'hold4' },
	pairs = {
		{ 'varka', 'none' },
		{ 'varka', 'vanilla' },
		{ 'varka', 'noshout' },
		{ 'varka', 'nocook' },
		{ 'varka', 'oldmem' },
	},
	world = {
		h_on = { false, true },
		g_dice = { false, true },
		g_fuse = { { 2.5, 2.5 }, { 3.2, 4.2 } },
		rank = { 3000, 8000, 15000 },
		g_skill_k = { 0.5, 1, 2 },
		acc = { 0.7, 1.0 },
	},
	seeds = 25,
	snap = 30,
}
