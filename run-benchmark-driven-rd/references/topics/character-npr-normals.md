# NPR character normals and renderer (provisional)

Load only for character cel shading, authored normals or outline work. Single
workflow owner: R&D; Cleanup independently measures the evidence. This is scoped
process guidance, not model training or a claim of universal character quality.

- `rd.npr.contract`: define the art target before choosing shaders. NPR clean
  color/pattern reconstruction is not mandatory PBR-map generation. GPU materials
  own shading; master/MI/MID separate graphs, reusable presets and owned live swaps.
  Blueprint exposes artist controls; C++ handles bounded lifecycle,
  light/head-space synchronization and editor API gaps when justified. An Unlit
  shader needs an explicit lighting model; scene lights/shadows/GI are not implied.
- `rd.npr.normals`: separate geometric winding, authored face-corner shading
  normals, tangent basis and outline expansion directions. Audit first; preserve
  sources and masks. Never blanket-recalculate, smooth-all, weld coincident
  vertices or apply Weighted Normal to every face. Face/head-shell transfer needs
  region/distance controls; hair and hard accessories have different boundaries.
- `rd.npr.export`: state whether FBX normals/tangents are imported or recomputed;
  inspect actual LOD build/section settings. Test deliberately non-geometric
  normals plus a recompute-negative control. Test mirrored UV, triangulation,
  morphs and each LOD. Import settings alone do not prove preservation.
- `rd.npr.outline`: normal-based WPO can split at UV/hard seams. Preserve shading
  normals independently. If baking tangent-space expansion vectors, verify the
  skinned TBN, handedness and quantization; Local-to-World does not skin an
  object-space vector. Inverted hulls need correct culling and no duplicate front
  shell. T-pose sphere success is not animated-character success.
- `rd.npr.gates`: retain native front/side/back light, head rotation, blink/mouth,
  outline/LOD captures, source-preservation and re-entry/restore failure tests.
  Face SDF, hair highlights, alpha cards, cast shadows and performance require
  separate corpus gates. Compare claimed superiority under declared resolution,
  motion, lighting and hardware; do not infer it from one attractive screenshot.
- `rd.npr.received-shadow`: an Unlit toon master receives no shadow. Self
  shadow = own ortho key-light depth capture sampled in the material; drop face
  and eyes from ortho views (mask on `ViewToClip[3][3]`) so the face keeps its
  SDF shape. Stylise, then A/B every step against shadow-off: hair ignores near
  occluders (no layer greying), face lookup offset toward the crown plus a max
  occluder gap gives the bangs band, disc PCF with bilinear taps then
  smoothstep removes strand streaks. Judge under a front key light, not backlight.
  World shade: feet/head traces toward the world light, blended by height,
  trace length = the sun's shadow distance; choose review spots by trace so a
  "front light" shot is not standing in a building's shadow.

Evidence locator: project-local records `character-npr-20260908` and
`npr-character-20261008` (LEARNINGS 8); one-project
candidate, no cross-project promotion. Normals policy follows Epic FBX import
options; seam risk follows Epic Coordinates Material Expressions. Keep official
URLs, engine versions, raw assets and test receipts in the target project.
