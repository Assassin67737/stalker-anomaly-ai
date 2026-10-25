-- Author: bellyillish — Useful Idiots, https://github.com/bellyillish/useful-idiots
-- The Unlicense (public domain). Copied verbatim from v1.4.10 (7bc0636).
-- VARKA changed only: require paths illish.lib.* -> varka.illish.lib.* (to not clash with Useful Idiots itself).

local RAY = {}


function RAY.cast(pos, dir, dist, flags)
  local ray = ray_pick()

  ray:set_flags(flags or 15)
  ray:set_position(pos)
  ray:set_direction(dir)
  ray:set_range(dist)

  return ray
end


function RAY.distance(pos, dir, dist, flags, limit)
  local ray = RAY.cast(pos, dir, dist, flags)
  ray:query()

  local castDist = ray:get_distance()

  if castDist == 0 and limit ~= false then
    castDist = dist
  end

  return castDist
end


return RAY
