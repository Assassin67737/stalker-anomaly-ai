-- Офлайн-стенд веры v2: varka_belief.script как есть, движок подменён навмешем и лучами двойника,
-- бойцы — позиции из trace боя. Выход — события bel* в JSON-lines (склеить с trace для вьювера).
--   luajit belharness.lua <уровень> <bel.tsv> <выход.jsonl> <varka_belief.script>
local LEVEL, TSV, OUT, SCRIPT = arg[1], arg[2], arg[3], arg[4]
local TWIN = (debug.getinfo(1, 'S').source:sub(2):match('(.*/)') or './') .. '../'
package.path = TWIN .. 'sim/?.lua;' .. package.path
local ffi = require 'ffi'
local W = require('world').load(LEVEL)
local rays = ffi.load(TWIN .. 'vision/librays.so')
ffi.cdef [[ float rays_cast(float ox, float oy, float oz, float dx, float dy, float dz, float range); ]]
local INVALID = 4294967295
local NOW = 0

-- ── vector ──
local V = {}
V.__index = V
function vector() return setmetatable({ x = 0, y = 0, z = 0 }, V) end
function V:set(x, y, z)
	if type(x) == 'table' then self.x, self.y, self.z = x.x, x.y, x.z else self.x, self.y, self.z = x, y, z end
	return self
end
function V:sub(v) self.x, self.y, self.z = self.x - v.x, self.y - v.y, self.z - v.z; return self end
function V:add(v) self.x, self.y, self.z = self.x + v.x, self.y + v.y, self.z + v.z; return self end
function V:mul(k) self.x, self.y, self.z = self.x * k, self.y * k, self.z * k; return self end
function V:magnitude() return math.sqrt(self.x ^ 2 + self.y ^ 2 + self.z ^ 2) end
function V:normalize() local m = self:magnitude(); if m > 0 then self:mul(1 / m) end; return self end
function V:distance_to(v) return math.sqrt((self.x - v.x) ^ 2 + (self.y - v.y) ^ 2 + (self.z - v.z) ^ 2) end

-- ── навмеш ──
local half = W.cell / 2 + 1e-4
local function inside(i, x, z)
	local nx, _, nz = W:xyz(i)
	return math.abs(x - nx) <= half and math.abs(z - nz) <= half
end
level = {}
function level.vertex_position(vid) local x, y, z = W:xyz(vid); return vector():set(x, y, z) end
function level.vertex_id(p)
	local i = W:node_at(p.x, p.y, p.z)
	if not i then return INVALID end
	local x, _, z = W:xyz(i)
	if math.abs(x - p.x) > W.cell * 1.5 or math.abs(z - p.z) > W.cell * 1.5 then return INVALID end
	return i
end
-- как farthest_vertex_in_direction: идём по прямой по ссылкам, упёрлись — последняя нода
function level.vertex_in_direction(vid, dir, dist)
	local x0, _, z0 = W:xyz(vid)
	local l = math.sqrt(dir.x ^ 2 + dir.z ^ 2)
	if l < 1e-6 then return vid end
	local dx, dz = dir.x / l, dir.z / l
	local cur, s = vid, 0.3
	while s <= dist + 1e-6 do
		local px, pz = x0 + dx * s, z0 + dz * s
		if not inside(cur, px, pz) then
			local nxt
			for d = 0, 3 do local j = W:link(cur, d); if j and inside(j, px, pz) then nxt = j; break end end
			if not nxt then
				for d = 0, 3 do
					local j = W:link(cur, d)
					if j then
						for d2 = 0, 3 do local k = W:link(j, d2); if k and inside(k, px, pz) then nxt = k; break end end
					end
					if nxt then break end
				end
			end
			if not nxt then break end
			cur = nxt
		end
		s = s + 0.3
	end
	return cur
end
level.object_by_id = function(id) return OBJ[id] end

-- ── лучи ──
local RP = {}
RP.__index = RP
function ray_pick() return setmetatable({}, RP) end
function RP:set_flags() end
function RP:set_position(p) self.p = vector():set(p) end
function RP:set_direction(d) self.d = vector():set(d) end
function RP:set_range(r) self.r = r end
function RP:query()
	self.dist = rays.rays_cast(self.p.x, self.p.y, self.p.z, self.d.x, self.d.y, self.d.z, self.r)
	RAYS_N = (RAYS_N or 0) + 1
	return self.dist >= 0
end
function RP:get_distance() return self.dist end

-- ── бойцы из trace ──
move = { stand = 0, crouch = 1 }
OBJ = {}          -- [id] = объект (живые)
local ST = {}     -- [id] = последнее состояние из trace
local seenT = {}  -- [id][eid] = когда видел
local O = {}
O.__index = O
function O:id() return self._id end
function O:alive() return not self.dead end
function O:position() local s = ST[self._id]; return vector():set(s.px, s.py, s.pz) end
function O:direction() local s = ST[self._id]; return vector():set(s.dx, 0, s.dz) end
function O:body_state() return ST[self._id].cr == 1 and move.crouch or move.stand end
function O:level_vertex_id() local s = ST[self._id]; return level.vertex_id(self:position()) end
function O:best_enemy() local s = ST[self._id]; return s.be >= 0 and OBJ[s.be] or nil end
function O:see(e) local s = ST[self._id]; return s.be == e._id and s.bsee == 1 end
function O:memory_time(e) return seenT[self._id] and seenT[self._id][e._id] or 0 end
function O:memory_position(e) local s = ST[e._id]; return vector():set(s.px, s.py, s.pz) end
function O:wounded() return ST[self._id].wnd == 1 end
local function obj(id)
	if not OBJ[id] then OBJ[id] = setmetatable({ _id = id }, O) end
	return OBJ[id]
end

db = { storage = {} }
function IsStalker() return true end
function IsWounded(o) return o:wounded() end
function character_community(o) return ST[o._id].comm end
function time_global() return NOW end
function printf(fmt, ...) print(string.format(fmt, ...)) end
local CB = {}
function RegisterScriptCallback(name, fn) CB[name] = fn end
varka_lkp = { get_squad_key = function(o) return ST[o._id].sq end }

-- trace: копим события
local out = assert(io.open(OUT, 'w'))
local function jv(v)
	if type(v) == 'number' then return (v % 1 == 0 and math.abs(v) < 2^31) and string.format('%d', v) or string.format('%.4f', v) end
	if type(v) == 'string' then return '"' .. v .. '"' end
	return 'null'
end
varka_trace = { emit = function(sq, id, ev, f)
	local b = { string.format('{"t":%d,"sq":%s,"npc":%s,"ev":"%s"', NOW, jv(sq), jv(id), ev) }
	for k, v in pairs(f or {}) do b[#b + 1] = string.format(',"%s":%s', k, jv(v)) end
	out:write(table.concat(b) .. '}\n')
end }

-- ── скрипт ──
local env = setmetatable({}, { __index = _G })
local chunk = assert(loadfile(SCRIPT))
setfenv(chunk, env)
chunk()
env.on_game_start()

-- ── повтор ──
local t_cpu, n_upd = 0, 0
for line in io.lines(TSV) do
	local f = {}
	for x in line:gmatch('[^\t]+') do f[#f + 1] = x end
	NOW = tonumber(f[1])
	if f[2] == 'D' then
		local id = tonumber(f[3])
		if OBJ[id] then
			OBJ[id].dead = true
			CB.npc_on_death_callback(OBJ[id])
			OBJ[id] = nil
		end
	else
		local id = tonumber(f[3])
		local s = { sq = tonumber(f[4]), px = tonumber(f[5]), py = tonumber(f[6]), pz = tonumber(f[7]),
		            dx = tonumber(f[8]), dz = tonumber(f[9]), be = tonumber(f[10]), bsee = tonumber(f[11]),
		            cr = tonumber(f[12]), wnd = tonumber(f[13]), aid2 = tonumber(f[14]), comm = f[15] }
		ST[id] = s
		local o = obj(id)
		if s.bsee == 1 and s.be >= 0 then seenT[id] = seenT[id] or {}; seenT[id][s.be] = NOW end
		db.storage[id] = db.storage[id] or {}
		db.storage[id].varka_active = (s.aid2 == 34) or nil
		if s.be >= 0 and not ST[s.be] then s.be = -1 end
		local c = os.clock()
		CB.npc_on_update(o)
		t_cpu = t_cpu + os.clock() - c
		n_upd = n_upd + 1
	end
end
out:close()
print(string.format('апдейтов %d, CPU веры %.2f с (%.2f мс на апдейт), лучей %d', n_upd, t_cpu, t_cpu / n_upd * 1000, RAYS_N or 0))
