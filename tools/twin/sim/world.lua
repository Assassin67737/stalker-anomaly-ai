-- world.lua — мир двойника (21.10.2026): навмеш, путь, укрытия, лучи.
--
-- Навмеш — levels/<имя>_nav.bin (bake_nav.py из level.ai), лучи — vision/librays.so (тот же код,
-- что сверен с игрой до треугольника) по levels/src/<имя>/level.cform.
-- Ноды нумеруются как в игре (vid), так что vid из trace подходят сюда без пересчёта.

local ffi = require 'ffi'
local bit = require 'bit'

ffi.cdef [[
int   rays_load(const char *path);
float rays_cast(float ox, float oy, float oz, float dx, float dy, float dz, float range);
int   rays_clear(float ax, float ay, float az, float bx, float by, float bz);
]]

local HERE = debug.getinfo(1, 'S').source:sub(2):match('(.*/)') or './'
local TWIN = HERE .. '../'

local M = {}
M.__index = M

-- направления ссылок и укрытий в level.ai (проверено bake_nav.py): 0 −x, 1 +z, 2 +x, 3 −z
local DIR = { { -1, 0 }, { 0, 1 }, { 1, 0 }, { 0, -1 } }

local rays

function M.load(name)
	local self = setmetatable({ name = name }, M)
	local f = assert(io.open(TWIN .. 'levels/' .. name .. '_nav.bin', 'rb'), 'нет навмеша — bake_nav.py')
	self.raw = f:read('*a')              -- держим строку: массивы ниже смотрят прямо в неё
	f:close()
	local p = ffi.cast('const uint8_t *', self.raw)
	assert(ffi.string(p, 4) == 'VKN1', 'не тот формат навмеша')
	local h = ffi.cast('const float *', p + 4)
	self.n = ffi.cast('const uint32_t *', p + 4)[0]
	self.cell = h[1]
	self.minx, self.minz = h[2], h[4]
	self.row = ffi.cast('const uint32_t *', p + 36)[0]
	local off = 40
	self.pos = ffi.cast('const float *', p + off); off = off + self.n * 12
	self.links = ffi.cast('const int32_t *', p + off); off = off + self.n * 16
	self.cover = ffi.cast('const uint8_t *', p + off)

	-- клетка (ix, iz) → нода; в одной клетке бывает несколько этажей → список
	self.grid = {}
	for i = 0, self.n - 1 do
		local k = self:key(self.pos[i * 3], self.pos[i * 3 + 2])
		local g = self.grid[k]
		if not g then self.grid[k] = i
		elseif type(g) == 'number' then self.grid[k] = { g, i }
		else g[#g + 1] = i end
	end

	-- рабочие массивы поиска пути: метка поколения вместо очистки 387 тысяч ячеек
	self.g = ffi.new('float[?]', self.n)
	self.came = ffi.new('int32_t[?]', self.n)
	self.stamp = ffi.new('uint32_t[?]', self.n)
	self.gen = 0

	if not rays then
		rays = ffi.load(TWIN .. 'vision/librays.so')
		assert(rays.rays_load(TWIN .. 'levels/src/' .. name .. '/level.cform') == 0)
	end
	return self
end

function M:key(x, z)
	local ix = math.floor((x - self.minx) / self.cell + 0.5)
	local iz = math.floor((z - self.minz) / self.cell + 0.5)
	return ix * self.row + iz
end

function M:xyz(i) return self.pos[i * 3], self.pos[i * 3 + 1], self.pos[i * 3 + 2] end

-- ближайшая нода к точке (y — чтобы попасть на нужный этаж; nil — любой)
function M:node_at(x, y, z)
	local best, bd = nil, 1e9
	for r = 0, 4 do
		for dx = -r, r do
			for dz = -r, r do
				if math.max(math.abs(dx), math.abs(dz)) == r then
					local g = self.grid[self:key(x + dx * self.cell, z + dz * self.cell)]
					local list = type(g) == 'number' and { g } or g
					if list then
						for _, i in ipairs(list) do
							local nx, ny, nz = self:xyz(i)
							local d = (nx - x) ^ 2 + (nz - z) ^ 2 + (y and (ny - y) ^ 2 * 4 or 0)
							if d < bd then best, bd = i, d end
						end
					end
				end
			end
		end
		if best and r >= 1 then return best end
	end
	return best
end

function M:link(i, d) local l = self.links[i * 4 + d]; return l >= 0 and l or nil end

-- открытость ноды в сторону (dx, dz): 0 — закрыто, 1 — голо. crouch — нижний ярус (сидя).
-- Смешиваем два ближайших из 4 направлений по углу.
function M:openness(i, dx, dz, crouch)
	local a = math.atan2(dz, dx)                      -- 0 = +x
	-- угол → «номер направления» по кругу: +x = 2, +z = 1, −x = 0, −z = 3
	local f = (2 - a / (math.pi / 2)) % 4
	local d0 = math.floor(f)
	local w = f - d0
	local d1 = (d0 + 1) % 4
	local base = i * 8 + (crouch and 4 or 0)
	return ((1 - w) * self.cover[base + d0] + w * self.cover[base + d1]) / 15
end

-- A* по ссылкам навмеша. Возвращает список нод от from до to (включительно) или nil.
-- limit — сколько нод раскрыть максимум (защита от «пути через весь уровень»).
function M:path(from, to, limit)
	if from == to then return { to } end
	self.gen = self.gen + 1
	local gen, g, came, stamp = self.gen, self.g, self.came, self.stamp
	local tx, ty, tz = self:xyz(to)
	local heap, hn = {}, 0                            -- двоичная куча пар {f, нода}
	local function push(f, i)
		hn = hn + 1
		local k = hn
		heap[k] = { f, i }
		while k > 1 do
			local p = bit.rshift(k, 1)
			if heap[p][1] <= f then break end
			heap[k], heap[p] = heap[p], heap[k]
			k = p
		end
	end
	local function pop()
		local top = heap[1]
		heap[1] = heap[hn]; heap[hn] = nil; hn = hn - 1
		local k = 1
		while true do
			local l, r, m = k * 2, k * 2 + 1, k
			if l <= hn and heap[l][1] < heap[m][1] then m = l end
			if r <= hn and heap[r][1] < heap[m][1] then m = r end
			if m == k then break end
			heap[k], heap[m] = heap[m], heap[k]
			k = m
		end
		return top[2]
	end
	stamp[from], g[from], came[from] = gen, 0, -1
	push(0, from)
	local opened = 0
	while hn > 0 do
		local i = pop()
		if i == to then
			local out, k = {}, to
			while k >= 0 do table.insert(out, 1, k); k = came[k] end
			return out
		end
		opened = opened + 1
		if opened > (limit or 200000) then return nil end
		local ix, iy, iz = self:xyz(i)
		for d = 0, 3 do
			local j = self:link(i, d)
			if j then
				local jx, jy, jz = self:xyz(j)
				local ng = g[i] + math.sqrt((jx - ix) ^ 2 + (jy - iy) ^ 2 + (jz - iz) ^ 2)
				if stamp[j] ~= gen or ng < g[j] then
					stamp[j], g[j], came[j] = gen, ng, i
					push(ng + math.sqrt((tx - jx) ^ 2 + (tz - jz) ^ 2), j)
				end
			end
		end
	end
end

-- Все ноды в пределах пути r метров от start: { {нода, путь_м}, … } — кандидаты в укрытия.
function M:around(start, r)
	self.gen = self.gen + 1
	local gen, g, stamp = self.gen, self.g, self.stamp
	local out, q, head = {}, { start }, 1
	stamp[start], g[start] = gen, 0
	while head <= #q do
		local i = q[head]; head = head + 1
		out[#out + 1] = { i, g[i] }
		for d = 0, 3 do
			local j = self:link(i, d)
			if j and stamp[j] ~= gen then
				local ng = g[i] + self.cell
				if ng <= r then stamp[j], g[j] = gen, ng; q[#q + 1] = j end
			end
		end
	end
	return out
end

-- линия видимости между двумя точками (в обе стороны — см. rays.c)
function M.clear(ax, ay, az, bx, by, bz) return rays.rays_clear(ax, ay, az, bx, by, bz) == 1 end

M.DIR = DIR
return M
