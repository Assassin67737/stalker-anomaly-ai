-- Повтор котла 21.10 11:26 (юзер): оба отряда A — g1 к точке, затем держать. Для проверки «стоят в поле / сидят вслепую».
local s = dofile((debug.getinfo(1, 'S').source:sub(2):match('(.*/)') or './') .. 'kotel1.lua')
s.id = 'kotel1_test'
s.limit = 300
s.sides.A.squads[1].orders = { { at = 2.3, route = { { x = 87.4, y = -1.9, z = 295.8, g = 1 } } } }
s.sides.A.squads[2].orders = { { at = 2.3, route = { { x = 98.0, y = -1.3, z = 295.9, g = 1 } } } }
return s
