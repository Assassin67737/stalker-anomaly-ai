-- sweep.lua — перебор рычагов в двойнике (23.10.2026): «тысячи прогонов за ночь → обобщённая картина».
--
--   luajit sim/sweep.lua sim/sweeps/grenades.lua --part 3 --of 11     кусок перебора (sweep.sh запускает все куски)
--   luajit sim/sweep.lua sim/sweeps/grenades.lua --count              сколько боёв в переборе
--   luajit sim/sweep.lua sim/sweeps/grenades.lua --replay 12345       бой №12345 → sim/out/sweep_<имя>_12345.jsonl
--                                                                     (тот же бой до выстрела — двойник детерминирован)
-- Спек перебора (sim/sweeps/*.lua): сценарии × пары доктрин × сетка рычагов мира (полный перебор) × seed,
-- и каждая пара играется дважды — доктрины меняются сторонами (swap), чтобы карта не подыгрывала.
-- Строка итога на бой: что за бой (номер, сценарий, пара, swap, рычаги) и чем кончился для доктрины X (первой в паре):
--   lx/ly — потери X/Y, win 1/−1/0, dur, fd — время первой потери (−1 — без потерь), gx/gy — гранаты {брошено,
--   убито, своих, уклонений}, snap — потери [X, Y] каждые spec.snap (30) с: исход на любом лимите из одного прогона.
local HERE = debug.getinfo(1, 'S').source:sub(2):match('(.*/)') or './'
package.path = HERE .. '?.lua;' .. package.path
local World = require 'world'
local Sim = require 'sim'

local spec_path = arg[1]
local part, of, count_only, replay = 0, 1, false, nil
for i = 2, #arg do
	if arg[i] == '--part' then part = tonumber(arg[i + 1]) end
	if arg[i] == '--of' then of = tonumber(arg[i + 1]) end
	if arg[i] == '--count' then count_only = true end
	if arg[i] == '--replay' then replay = tonumber(arg[i + 1]) end
end
local spec = dofile(spec_path)
local SNAP = spec.snap or 30     -- шаг срезов, с

-- сетка рычагов: имена по алфавиту (порядок не зависит от pairs), значения — как в спеке
local knames = {}
for k in pairs(spec.world) do knames[#knames + 1] = k end
table.sort(knames)
local grid = { {} }
for _, k in ipairs(knames) do
	local nx = {}
	for _, cell in ipairs(grid) do
		for vi = 1, #spec.world[k] do
			local c = {}
			for kk, vv in pairs(cell) do c[kk] = vv end
			c[k] = vi
			nx[#nx + 1] = c
		end
	end
	grid = nx
end

-- бой №n → (сценарий, пара, клетка сетки, swap, seed); порядок: seed — самый внутренний, чтобы куски были ровными
local NS, NP, NG, SEEDS = #spec.scen, #spec.pairs, #grid, spec.seeds
local TOTAL = NS * NP * NG * 2 * SEEDS
local function job(n)
	local r = n
	local seed = r % SEEDS; r = (r - seed) / SEEDS
	local sw = r % 2; r = (r - sw) / 2
	local gi = r % NG; r = (r - gi) / NG
	local pi = r % NP; r = (r - pi) / NP
	return r + 1, pi + 1, gi + 1, sw, seed + 1
end

-- meta.json — для sweep_report.py: что за рычаги, пары, сценарии (значения рычага — строкой, как в спеке)
local function lua2json(v)
	if type(v) == 'table' then
		local p = {}
		for _, x in ipairs(v) do p[#p + 1] = lua2json(x) end
		return '[' .. table.concat(p, ',') .. ']'
	elseif type(v) == 'string' then return '"' .. v .. '"' end
	return tostring(v)
end
local function write_meta(dir)
	local p = {}
	for _, k in ipairs(knames) do p[#p + 1] = '"' .. k .. '":' .. lua2json(spec.world[k]) end
	local f = assert(io.open(dir .. '/meta.json', 'w'))
	f:write(('{"name":"%s","total":%d,"seeds":%d,"snap":%d,"scen":%s,"pairs":%s,"world":{%s}}\n'):format(spec.name, TOTAL,
		SEEDS, SNAP, lua2json(spec.scen), lua2json(spec.pairs), table.concat(p, ',')))
	f:close()
end
local dir = HERE .. 'out/sweep_' .. spec.name

if count_only then
	os.execute('mkdir -p "' .. dir .. '"')
	write_meta(dir)
	print(('%d боёв: сценариев %d × пар %d × клеток %d × swap 2 × seed %d'):format(TOTAL, NS, NP, NG, SEEDS))
	return
end

local scens, worlds = {}, nil
for i, name in ipairs(spec.scen) do
	scens[i] = dofile(HERE .. 'scen/' .. name .. '.lua')
	assert(scens[i].level == scens[1].level, 'один уровень на перебор (лучи грузятся один раз)')
end
worlds = World.load(scens[1].level)

local function run_one(n, out)
	local si, pi, gi, sw, seed = job(n)
	local base = scens[si]
	local x, y = spec.pairs[pi][1], spec.pairs[pi][2]
	local sc = { id = base.id, level = base.level, limit = base.limit, zone = base.zone, seed = seed * 7919 + si,
		sides = { A = {}, B = {} }, world = {} }
	for _, side in ipairs { 'A', 'B' } do
		for k, v in pairs(base.sides[side]) do sc.sides[side][k] = v end
	end
	local xs, ys = sw == 0 and 'A' or 'B', sw == 0 and 'B' or 'A'
	sc.sides[xs].grenade, sc.sides[ys].grenade = x, y
	local kv = {}
	for _, k in ipairs(knames) do
		local vi = grid[gi][k]
		sc.world[k] = spec.world[k][vi]
		kv[#kv + 1] = '"' .. k .. '":' .. (vi - 1)
	end
	local sim = Sim.new(sc, worlds, out)
	-- срезы: потери X и Y каждые SNAP с — исход на любом лимите из одного прогона (таймаут не теряет меру)
	local n_of = function(side) local c = 0; for _, f in ipairs(sim.fighters) do if f.side == side then c = c + 1 end end; return c end
	local nx, ny = n_of(xs), n_of(ys)
	local snaps, next_snap = {}, SNAP
	sim:start()
	local reason
	repeat
		reason = sim:tick()
		if sim.t >= next_snap then
			snaps[#snaps + 1] = ('[%d,%d]'):format(nx - sim:alive(xs), ny - sim:alive(ys))
			next_snap = next_snap + SNAP
		end
	until reason
	local _, a, b = sim:finish(reason)
	local alive = { A = a, B = b }
	local lx, ly = nx - alive[xs], ny - alive[ys]
	local win = (alive[xs] > 0 and alive[ys] == 0) and 1 or (alive[ys] > 0 and alive[xs] == 0) and -1 or 0
	local function gs(side)
		local g = sim.gs[side]
		return ('[%d,%d,%d,%d]'):format(g.thrown, g.kills, g.ff, g.dodges)
	end
	return ('{"n":%d,"s":%d,"p":%d,"sw":%d,"seed":%d,"k":{%s},"lx":%d,"ly":%d,"win":%d,"dur":%.1f,"fd":%.1f,"gx":%s,"gy":%s,"snap":[%s]}')
		:format(n, si - 1, pi - 1, sw, seed, table.concat(kv, ','), lx, ly, win, sim.t, sim.first_death or -1, gs(xs), gs(ys),
			table.concat(snaps, ','))
end

if replay then
	local file = HERE .. 'out/sweep_' .. spec.name .. '_' .. replay .. '.jsonl'
	local out = assert(io.open(file, 'w'))
	local line = run_one(replay, out)
	out:close()
	print(line)
	print('trace → ' .. file)
	return
end

-- кусок перебора: бои n ≡ part (mod of); итоги дописываются — перезапуск продолжает с места
os.execute('mkdir -p "' .. dir .. '"')
local path = ('%s/part_%02d.jsonl'):format(dir, part)
local done = {}
do  -- готовые бои из ВСЕХ кусков: перезапуск с другим числом потоков не гоняет их второй раз
	local ls = io.popen('ls "' .. dir .. '"/part_*.jsonl 2>/dev/null')
	for p in ls:lines() do
		local f = io.open(p, 'r')
		for l in f:lines() do local n = l:match('"n":(%d+)'); if n and l:sub(-1) == '}' then done[tonumber(n)] = true end end
		f:close()
	end
	ls:close()
end
local res = assert(io.open(path, 'a+'))
do  -- прошлый запуск убит посреди строки → начать с новой строки, чтобы не склеить две записи
	local size = res:seek('end')
	if size > 0 then res:seek('set', size - 1); if res:read(1) ~= '\n' then res:seek('end'); res:write('\n') end end
	res:seek('end')
end
local t0, k = os.time(), 0
for n = part, TOTAL - 1, of do
	if not done[n] then
		res:write(run_one(n, nil), '\n')
		k = k + 1
		if k % 50 == 0 then res:flush() end
	end
end
res:close()
io.stderr:write(('кусок %d/%d: %d боёв за %d с\n'):format(part, of, k, os.time() - t0))
