# Facial retopology and efficient resume (provisional)

For generated-character edge-flow repair. Game assets follow
[low-poly/baking](character-lowpoly-bake.md), not dense quad grids; platform triangle
budgets apply. [Cleanup](../../../code-cleanup-helper/references/topics/character-retopology-audit.md)
audits the same evidence. The profile is a user requirement; mechanism lessons
remain provisional.

- `rd.retopology.intent`: new, smooth edge flow needs anatomical eye/lip loops,
  controlled poles and useful spacing. Separate native wire/clay from texture
  beauty. A relaxed old mesh, all-quad count or global edge metric is insufficient.
  Keep each eye aperture, lip shape and silhouette as named local gates.
- `rd.retopology.correspondence`: freeze the source and work on a derivative.
  New indices are not old identities. Preserve or explicitly transfer seams,
  corner normals, UVs, masks and skin/morph data. Check bidirectional surface and
  boundary distances, folds and integration interfaces. An unstitched facial
  patch is not a usable complete head or a deformation-ready rig.
- `rd.retopology.atlas`: nearest-source UVs at individual vertices can cross
  different source islands inside one new face, causing visible stripes despite
  valid barycentrics. Use chart-aware face ownership or a new-UV bake; inspect
  same-camera native flat albedo. An exact save/reload does not prove artwork.
- `rd.retopology.failure`: classify solver preflight, anatomy, mapping and art
  failures separately. Native manifold warnings may include a local edge-length
  threshold: inspect the actual installed implementation and explicit controls,
  not blanket weld/scale retries. Harmonic maps with anatomical holes can fold;
  preserving boundary count alone does not preserve an eye opening. A bounded
  whole-surface QuadriFlow test on a pinched generated head lost ocular/mouth/ear
  structure despite `preserve_boundary=True`; compare boundary topology and
  bidirectional source/low distances **plus** matched clay anatomy before any
  UV, bake or rig transfer. Fewer quads is not a promotion criterion.
- `rd.retopology.resume`: keep `.rd/character-checkpoint.json` with source,
  candidate, contract and review hashes, object, stage, rejected methods and next
  bounded step. Run `scripts/read_character_checkpoint.py --project <root>` from
  this skill. CURRENT proves file freshness only; stale/missing/malformed blocks
  reuse. Read the linked review, not the whole history. No commands are executed
  from checkpoint text. Update the checkpoint after evidence changes.
- `rd.retopology.cost`: reuse verified stage tools and cached hash-bound discovery;
  no repeated full dumps or unbounded remesh sweeps. Topology precedes new UVs,
  textures and rigging. Report actual context/latency and quality separately;
  a compact receipt is not a complete prompt or proof of faster/better repair.

Evidence IDs: character-retopology-20260919 and character-checkpoint-20260919.
Raw models/native captures remain project-local; no accepted facial retopo claim.
