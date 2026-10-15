# Generated character mesh repair (provisional)

For Blender character defects before UV/rigging; not a universal remesh policy.
R&D owns implementation; [Cleanup](../../../code-cleanup-helper/references/topics/character-3d-audit.md)
independently audits evidence. Editing this guidance does not train model weights.

- `rd.mesh.classify`: inspect actual geometry, not only textures or screenshots.
  Distinguish boundary openings, multi-face edge fans, duplicate/zero-area faces,
  winding, authored corner normals and intersections. Hair cards, cuffs, necks
  and isolated polygons may intentionally be open. Size or a non-manifold count
  alone never authorizes filling every opening.
- `rd.mesh.preserve`: repair copies before skin/morphs; otherwise define explicit
  correspondence and rebind/retest. Preserve all UV layers, materials, masks,
  winding and per-corner normals with measured tolerances. Reject unsupported
  data instead of dropping it. No blanket weld/remesh/recalculate-normal fallback.
  Normal re-encoding can quantize after a topology change; bound correction and
  retain the original tolerance, rather than relaxing the gate after failure.
- `rd.mesh.operations`: splitting multi-face edges preserves surfaces but creates
  more boundary vertices; it does not remove overlaps, close holes or guarantee
  crack-free skinning. Retain source-vertex correspondence and match coincident
  seam weights before deformation. Patch only reviewed loops bound to a current
  mesh digest, winding and size limit. Reject isolated sheets, ambiguous branches
  and UV/material conflicts; new patch surfaces need explicit texture review.
- `rd.mesh.verify`: if Blender MCP is requested, verify its connected scene and
  use it for the actual operation. Background isolation is acceptable; never
  reuse an unknown user's scene or claim a failed connection performed work.
  Gate source hashes, corner preservation, intended opening controls, stale
  selection/digest, unsafe skin/morph data, rollback and save/reload. Retain native
  same-camera before/after captures. Zero fan edges proves only that stage;
  UV redesign, visible holes, animation and Unreal import remain separate gates.

Evidence locator: project-local `character-mesh-repair-20260912`; source/synthetic
Blender 5.1 measurements, not general art approval. Raw models, private paths and
logs stay local. Revalidate for Blender/API changes and different topology.
