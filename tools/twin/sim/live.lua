-- live.lua — двойник в реальном времени для пульта генерала (21.10.2026).
-- Запускает его server.py --twin; руками:  luajit sim/live.lua <сценарий> <trace.jsonl> <команды.txt>
--
-- Протокол тот же, что у творческого режима Anomaly: вьювер → POST /cmd → server.py дописывает строку
-- «seq\tкоманда\tаргументы…» в файл команд → здесь читаем новые строки → ответ cmd_ok/cmd_fail в trace.
-- Команды:
--   pause | resume | speed <k>                      пауза, ход, скорость (0.25…8)
--   order <отряд> <x,y,z,g;x,y,z,g;…> [A|B|C]       маршрут с поводком на каждом отрезке; с буквой — ждёт сигнала
--   go <A|B|C>                                      сигнал: все приказы с этой буквой — пошли
--   hold <отряд>                                    отменить приказ, держать место
--   order_npc <боец> <маршрут> [A|B|C] / hold_npc <боец>   то же для одного бойца (важнее приказа отряда)
--   restart [seed]                                  тот же сценарий заново (другие кубики)
local HERE = debug.getinfo(1, 'S').source:sub(2):match('(.*/)') or './'
package.path = HERE .. '?.lua;' .. package.path
local ffi = require 'ffi'
ffi.cdef [[
typedef struct { long tv_sec; long tv_nsec; } timespec;
int clock_gettime(int clk, timespec *tp);
int usleep(unsigned int us);
int getppid(void);
]]
local World = require 'world'
local Sim = require 'sim'

local SCEN, TRACE, CMDS = arg[1], arg[2], arg[3]
local scen = dofile(SCEN)
local world = World.load(scen.level)

local ts = ffi.new('timespec')
local function now() ffi.C.clock_gettime(1, ts); return tonumber(ts.tv_sec) + tonumber(ts.tv_nsec) * 1e-9 end

local sim, out, over
local paused, speed = true, 1          -- стартуем на паузе: генерал сначала осматривается
local function state() sim:emit('sim_state', { sq = 0, npc = 0, paused = paused, speed = speed, over = over or '' }) end

-- прошлый бой не затираем: в архив sim/out/<сценарий>_<дата-время>.jsonl (котлы потом обобщаем)
local function archive()
	local f = io.open(TRACE, 'r')
	if not f then return end
	local size = f:seek('end')
	f:close()
	if size > 20000 then
		os.rename(TRACE, HERE .. 'out/' .. scen.id .. '_' .. os.date('%Y%m%d_%H%M%S') .. '.jsonl')
	end
end

local function new_sim(seed)
	if out then out:close() end
	archive()
	scen.seed = seed
	out = assert(io.open(TRACE, 'w'))
	sim = Sim.new(scen, world, out)
	sim.pos_every = 0.2                -- живьём чаще, чтобы на экране не дёргалось
	sim:start()
	over = nil
	state()
	out:flush()
end
new_sim(scen.seed or 1)

local function squad(id)
	for _, s in ipairs(sim.squads) do if s.id == tonumber(id) then return s end end
end

local function parse_route(str)
	local r = {}
	for part in str:gmatch('[^;]+') do
		local x, y, z, g = part:match('([^,]+),([^,]+),([^,]+),([^,]+)')
		if not x then return nil end
		r[#r + 1] = { x = tonumber(x), y = tonumber(y), z = tonumber(z), g = math.max(1, math.min(3, tonumber(g))) }
	end
	return #r > 0 and r or nil
end

local function handle(seq, cmd, a)
	if cmd == 'pause' then paused = true
	elseif cmd == 'resume' then if not over then paused = false end
	elseif cmd == 'speed' then speed = math.max(0.25, math.min(8, tonumber(a[1]) or 1))
	elseif cmd == 'order' then
		local sq, r = squad(a[1]), parse_route(a[2] or '')
		if not (sq and r) then return 'нет отряда или маршрута' end
		sq.free = false
		local code = a[3] ~= '' and a[3] or nil
		sim:order(sq, { route = r, code = code })
	elseif cmd == 'order_npc' then
		local f, r
		for _, x in ipairs(sim.fighters) do if x.id == tonumber(a[1]) then f = x end end
		r = parse_route(a[2] or '')
		if not (f and r and f.hp > 0) then return 'нет бойца или маршрута' end
		f.sq.free = false
		sim:order_npc(f, { route = r, code = a[3] ~= '' and a[3] or nil })
	elseif cmd == 'hold_npc' then
		for _, x in ipairs(sim.fighters) do if x.id == tonumber(a[1]) and x.hp > 0 then sim:hold_npc(x); return end end
		return 'нет бойца'
	elseif cmd == 'go' then sim:release(a[1])
	elseif cmd == 'hold' then
		local sq = squad(a[1]); if not sq then return 'нет отряда' end
		sq.free = false; sim:hold(sq)
	elseif cmd == 'restart' then new_sim(tonumber(a[1]) or (scen.seed or 1) + 1)
	else return 'не знаю команду ' .. cmd end
end

-- файл команд: первая строка «#session\t<id>»; новая сессия (перезапуск сервера) — читаем с начала
local cmd_pos, session = 0, nil
local function poll_cmds()
	local f = io.open(CMDS, 'r')
	if not f then return end
	local first = f:read('*l')
	if first ~= session then session, cmd_pos = first, #(first or '') + 1 end
	f:seek('set', cmd_pos)
	for line in f:lines() do
		if line:sub(-1) ~= '\r' and line ~= '' then
			local parts = {}
			for p in (line .. '\t'):gmatch('([^\t]*)\t') do parts[#parts + 1] = p end
			local seq, cmd = parts[1], parts[2]
			local err = handle(seq, cmd, { parts[3], parts[4], parts[5] })
			sim:emit(err and 'cmd_fail' or 'cmd_ok', { sq = 0, npc = 0, cseq = tonumber(seq) or 0, cmd = cmd, why = err or '' })
			state()
		end
	end
	cmd_pos = f:seek()
	f:close()
end

local DT = 0.1
local acc, last, last_cmd = 0, now(), 0
local parent = ffi.C.getppid()
while ffi.C.getppid() == parent do          -- сервер закрыли (даже не по Ctrl+C) — уходим и мы
	local t = now()
	local dt = math.min(0.5, t - last)
	last = t
	if t - last_cmd > 0.1 then poll_cmds(); last_cmd = t end
	if not paused and not over then
		acc = acc + dt * speed
		while acc >= DT and not over do
			acc = acc - DT
			local reason = sim:tick()
			if reason then over = reason; paused = true; sim:finish(reason); state() end
		end
	else
		acc = 0
	end
	out:flush()
	ffi.C.usleep(15000)
end
