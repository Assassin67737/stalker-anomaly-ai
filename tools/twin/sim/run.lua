-- run.lua — прогон сценария в двойнике.
--   luajit sim/run.lua sim/scen/m26.lua            один бой → sim/out/<id>_s<seed>.jsonl (смотреть во viewer3d)
--   luajit sim/run.lua sim/scen/m26.lua --n 100    серия на разных seed, итог в консоль
local HERE = debug.getinfo(1, 'S').source:sub(2):match('(.*/)') or './'
package.path = HERE .. '?.lua;' .. package.path
local World = require 'world'
local Sim = require 'sim'

local path, n, seed0 = arg[1], 1, nil
for i = 2, #arg do
	if arg[i] == '--n' then n = tonumber(arg[i + 1]) end
	if arg[i] == '--seed' then seed0 = tonumber(arg[i + 1]) end
end
local scen = dofile(path)
local w = World.load(scen.level)
local res = { A = 0, B = 0, draw = 0 }
local durs, hits, firsts, hd = {}, {}, {}, {}
local function med(t) table.sort(t); return t[math.max(1, math.floor(#t / 2))] or 0 end
local t0 = os.clock()
for k = 1, n do
	scen.seed = (seed0 or scen.seed or 1) + k - 1
	local file = n == 1 and (HERE .. 'out/' .. scen.id .. '_s' .. scen.seed .. '.jsonl') or '/dev/null'
	local out = assert(io.open(file, 'w'))
	local sim = Sim.new(scen, w, out)
	local reason, a, b = sim:run()
	out:close()
	local who = a > 0 and b == 0 and 'A' or b > 0 and a == 0 and 'B' or 'draw'
	res[who] = res[who] + 1
	durs[#durs + 1] = sim.t; hits[#hits + 1] = sim.nhits or 0
	if sim.first_hit then firsts[#firsts + 1] = sim.first_hit end
	for _, d in ipairs(sim.hit_d or {}) do hd[#hd + 1] = d end
	if n == 1 then
		print(('%s: %s за %.0f с, живы A %d / B %d → %s'):format(scen.id, reason, sim.t, a, b, file))
	end
end
if n > 1 then
	print(('%d боёв за %.1f с: A %d, B %d, ничьих %d'):format(n, os.clock() - t0, res.A, res.B, res.draw))
	print(('медианы: бой %.0f с, попаданий %d, первое попадание %.0f с, дистанция попадания %.0f м')
		:format(med(durs), med(hits), med(firsts), med(hd)))
end
