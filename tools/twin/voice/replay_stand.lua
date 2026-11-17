-- replay_stand.lua — см. replay_stand.py (17.11.2026): varka_voice.hearers на заглушках движка, луч = librays
local ffi=require'ffi'
ffi.cdef[[int rays_load(const char *path); int rays_clear(float ax,float ay,float az,float bx,float by,float bz);]]
local R=ffi.load('/home/ibra/Documents/My_Projects/AI_for_STALKER/tools/twin/vision/librays.so')
assert(R.rays_load('/home/ibra/Documents/My_Projects/AI_for_STALKER/tools/twin/levels/src/'..arg[2]..'/level.cform')==0)
local V={};V.__index=V
function vector() return setmetatable({x=0,y=0,z=0},V) end
function V:set(a,b,c) if type(a)=='table' then self.x,self.y,self.z=a.x,a.y,a.z else self.x,self.y,self.z=a,b,c end return self end
function V:sub(o) self.x,self.y,self.z=self.x-o.x,self.y-o.y,self.z-o.z return self end
function V:magnitude() return math.sqrt(self.x^2+self.y^2+self.z^2) end
function V:normalize() local m=self:magnitude() self.x,self.y,self.z=self.x/m,self.y/m,self.z/m return self end
function V:invert() self.x,self.y,self.z=-self.x,-self.y,-self.z return self end
function V:distance_to(o) return math.sqrt((self.x-o.x)^2+(self.y-o.y)^2+(self.z-o.z)^2) end
-- ray_pick: копим позицию/направление/дальность, query = rays_clear отрезка
local RP={};RP.__index=RP
function ray_pick() return setmetatable({},RP) end
function RP:set_flags() end
function RP:set_position(p) self.p=vector():set(p) end
function RP:set_direction(d) self.d=vector():set(d) end
function RP:set_range(r) self.r=r end
function RP:query() local p,d,r=self.p,self.d,self.r; return R.rays_clear(p.x,p.y,p.z,p.x+d.x*r,p.y+d.y*r,p.z+d.z*r)==0 end
function RP:get_distance() return 0 end
level={name=function() return arg[2] end}
printf=function(...) end
IsStalker=function() return true end
math.randomseed(7)
local src=io.open('/home/ibra/Documents/My_Projects/AI_for_STALKER/varka/src/varka_voice.script'):read('*a')
src=src:gsub('"%.%./appdata/varka_voice/"','"/mnt/games/ANOMALY_DEV/appdata/varka_voice/"')
local M=assert(loadstring(src..'\nreturn {hearers=hearers}'))()
local json=io.open(arg[1]):read('*a')
-- простейший разбор массива массивов
local rows={}
for r in json:gmatch('%[([^%[%]]-)%]') do local t={} for v in r:gmatch('[^,]+') do v=v:gsub('^%s*"',''):gsub('"%s*$','') t[#t+1]=tonumber(v) or v end rows[#rows+1]=t end
local function obj(id,x,y,z,v,c) return {id=function() return id end, position=function() return vector():set(x,y,z) end,
  level_vertex_id=function() return v end, alive=function() return true end, character_community=function() return c end} end
db={storage={}}
local i=1
local count={}
while i<=#rows do
  local s=rows[i]; i=i+1
  db.storage={}
  local ls={}
  while i<=#rows and rows[i][1]=='L' do local r=rows[i]; db.storage[r[2]]={object=obj(r[2],r[3],r[4],r[5],r[6],r[7])}; ls[#ls+1]=r; i=i+1 end
  -- сколько слышали по-старому
  local who=obj(0,s[3],s[4],s[5],s[6],'actor')
  local list=M.hearers(who,s[2])
  local w,h,how=0,0,{line=0,wall=0,around=0}
  for _,x in ipairs(list) do if x.level==2 then w=w+1 else h=h+1 end; how[x.how]=how[x.how]+1 end
  print(string.format('%-7s (%4.0f,%3.0f,%4.0f): было %2d слышали -> сейчас слова %2d, слышал %2d, нет %2d | line %d wall %d around %d',
    s[2],s[3],s[4],s[5],#ls,w,h,#ls-#list,how.line,how.wall,how.around))
  for _,x in ipairs(list) do if x.how~='line' then print(string.format('      %5d  %3.0f м -> звучит как %3.0f м  %-6s %s',x.id,x.d,x.d_eff,x.how,x.level==2 and 'СЛОВА' or 'слышал')) end end
end
