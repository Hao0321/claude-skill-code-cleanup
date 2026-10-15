# Modular 3D character workflow (provisional)

Use the checkpoints below to route work. Before acting on a checkpoint, read its full rule in [character-3d-workflow-detail.md](character-3d-workflow-detail.md); every prior test, limitation and evidence reference remains there.

- `rd.character.inputs`: Lock design, scale, views, rights, budget.
- `rd.character.assembly`: Preserve source; fit is not topology repair.
- `rd.character.rig`: Actual target rest hierarchy and engine test.
- `rd.character.rig-guide-branch`: Authorized real rig guide; weights/physics separate.
- `rd.character.expression`: Morph topology or registered heads; runtime test.
- `rd.character.texture`: UV/view hashes; occlusion and native art.
- `rd.character.ue-material-readback`: Explicit UE slot structs and cold readback.
- `rd.character.uv-storage`: Stored float32 UV and reload negative.
- `rd.character.uv-fragmentation`: UV-chart count differs from mesh components.
- `rd.character.hair-uv-pilot`: Saved per-component hair UV collapse gate.
- `rd.character.hair-orientability`: Edge topology; zero fans is not orientability.
- `rd.character.user-density-override`: User density approval stops global decimation.
- `rd.character.component-hybrid-uv`: Localized source UV reuse; cold full atlas.
- `rd.character.triangle-chart-hair`: Source triangle IDs, quad split, local packing.
- `rd.character.hair-orientation-cut`: Parity cuts versus winding/pose/culling.
- `rd.character.hair-two-sided-gate`: One-sided hair coverage; separate engine costs.
- `rd.character.render-uv-channel`: Explicit source, bake and render UV channels.
- `rd.character.ai-atlas-gate`: Exact atlas resolution and registration.
- `rd.character.ai-detail-layer`: Controlled detail layer; cloth/skin masks.
- `rd.character.registered-part-space`: Original registered matrices and world bounds.
- `rd.character.ornament-reconstruction`: Matched motif recognition; reject grain-only.
- `rd.character.registered-current`: Build only from the sha-pinned registered CURRENT.
- `rd.character.head-uv-standard`: Head = front face, back of head, two ears.
- `rd.character.uv-transfer-sharpness`: Re-UV bake; eye/ornament close-up A/B.
- `rd.character.blender-batch-pitfalls`: Absolute paths, arg dashes, exit-code gates.
- `rd.character.hair-strand-albedo`: Flow-UV strands; measure contrast; engine A/B.
- `rd.character.secondary-motion`: Hair/skirt sway: read [character-secondary-motion.md](character-secondary-motion.md).
- `rd.character.locomotion`: Walk/run/sprint/jump clips and their engine blend: read [character-locomotion.md](character-locomotion.md).
- `rd.character.gates`: Stage-specific fixtures; native quality evidence.
