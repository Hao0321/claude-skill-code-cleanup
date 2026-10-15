# Environment town layout and stable window variation (provisional)

Load for instanced town layout, window interiors or environment art review. Single owner: R&D; Cleanup measures
coverage. These are sanitized single-project observations, not universal art acceptance or tested engine parity.

- `rd.town.diagnose`: judge fresh labelled native views with the actual map, camera, time and quality tier.
  Hide buildings once to distinguish attached dressing from ground props. Recheck cameras after layout changes.
- `rd.town.streetwall`: derive facade lines, widths and front axes from real mesh bounds; frame the landmark from
  the player start and keep walking routes open. Dense streets and a layered skyline are optional composition
  choices, not a requirement for every town.
- `rd.town.reversible`: snapshot transforms and map hashes before editing; regenerate each pass from that base.
  Preserve unknown actors and shared materials. Verify saved native data after editor automation.
- `rd.town.ue427`: check the actual engine API before scripting. Recreate actors with copied mesh/component settings
  when duplication is unavailable; do not persist temporary dynamic material instances into the level.
- `rd.town.blender_props`: thin closed shells require explicit top, underside and radial rim orientation; inspect
  exported normals and native lighting rather than accepting a successful mesh export.
- `rd.town.window-layout`: for per-pane variation, encode a stable authored integer for each pane, including
  neighbours on one house. Validate every pane vertex, shared boundaries and LOD agreement. Round interpolated IDs
  before atlas indexing; a house seed or colour variation alone does not select different rooms. Preserve common
  sky, weather and room depth. Inspect an actual adjacent pair by day/night, at oblique angles and through LODs.
- `rd.town.style`: bind acceptance to the project's art direction. For detailed NPR environments, review material
  detail, controlled light bands/softness, contact shadows, atmosphere and plant motion together. Do not flatten
  lighting merely to force bands; successful compilation or a default lit material is not art acceptance.

Evidence: sanitized workflow observations; raw screenshots, paths and measurements stay project-local. Engine
and art conclusions require native replay on the destination project before promotion.
