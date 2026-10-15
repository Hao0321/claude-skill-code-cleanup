# Game low-poly and high-to-low baking (provisional)

Use when a character must run in a game, especially PC plus mobile. Retain
source originals. User-requested low-poly delivery supersedes cosmetic dense
quad regularization; automatic reduction is not animation-ready retopology.

- `rd.lowpoly.budget`: set per-platform evaluated triangle, material, texture and
  influence budgets before work. Count the complete visible asset including
  eyes/lashes and outline passes; authoring quads or head-only partial counts
  cannot prove game cost. Provide distinct LOD/texture tiers, then profile real
  target hardware. Preserve silhouette and deforming feature loops economically.
- `rd.lowpoly.bake`: freeze low-poly topology/triangulation and UV before baking.
  Require actual high-to-low maps, not an unwrap or copied source image. Use
  explicit matched groups, cages/ray limits, active low target and bake image;
  keep nearby eyes/lashes from contaminating skin rays. Check misses, cage
  intersections, seams, padding and mip appearance with native readback. Put the
  baked UV in exported UV0. Rotate a paint atlas before baking; changing tangent
  orientation requires rebaking normals, not rotating encoded RGB as color.
- `rd.lowpoly.npr`: base color is lighting-free; AO/detail masks stay separate.
  Tangent normals are non-color data with declared green-channel convention and
  a tested engine import basis. Do not bake unwanted Tripo bumps into a clean
  NPR face or expect a normal map to restore silhouette. Material normal strength
  and authored NPR shadow normals are distinct controls.
- `rd.lowpoly.gates`: verify geometry/UV/source-image hashes, source immutability,
  exact total triangles, local anatomy, UV overlap/degeneracy and persisted image
  dimensions. Positive selected-high/active-low bake and wrong-target/UV/channel
  negatives calibrate the pipeline. Native textured/wire views are required;
  rig/morph deformation, UE 4.27.2 import and physical-mobile FPS remain separate.

User correction/evidence locator: character-game-lowpoly-bake-20260919.
Raw assets stay project-local. [Cleanup readback](../../../code-cleanup-helper/references/topics/character-retopology-audit.md)
must retain failed or unmeasured gates even after a successful bake.
