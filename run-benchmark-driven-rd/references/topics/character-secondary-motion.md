# Character secondary motion: hair, skirt, sleeve chains (provisional)

Load only for bone-chain sway (hair, skirts, sleeves, ribbons) of a rigged character. Single workflow owner: R&D;
Cleanup measures the evidence. One-project candidate, not a universal quality claim.

- `rd.secondary.visible`: judge the visible mesh, not the bones. Bones can swing while the mesh stays still when the
  chain weights are small or the anchor bone keeps most of the weight (a hair mesh 100% on the head bone never moves).
  Audit per-chain weight share and on/off vertex amplitude before tuning dynamics.
- `rd.secondary.energy`: plain follow-the-leader length projection feeds its correction into Verlet velocity and pumps
  energy (swings three times too far, settles twice as slowly). Move the previous position by the same correction
  (dynamic FTL). A spring whose goal is an end-of-step position acts on the predicted end-of-step position, or a moving
  chain leads its animation by speed x step.
- `rd.secondary.model`: angular spring to the rest direction in the parent's simulated frame (stiff root, soft tip),
  damping relative to the chain root, separate air drag for trailing, slow follow, inheritance of root movement and
  rotation, cone in the parent frame, closed rings for skirts, body colliders placed from bind-pose positions on the
  playing skeleton. A hitch slows the simulation instead of snapping to the pose.
- `rd.secondary.benchmark`: value-only solver benchmark: the same keyed input at every frame rate, metrics read on one
  common sampling grid (peak, rebounds over a threshold, settle, run trail, turn lag/back). Overshoot after a
  symmetric move is not a damping measure. A numpy port for sweeps must first reproduce the engine numbers.
- `rd.secondary.gates`: on/off video of the real character in motion plus numeric on/off amplitude, penetration and
  30/60/120 equivalence; capsule penetration 0 does not prove a clean surface.
- `rd.secondary.pipeline`: on/off difference of exactly zero means nothing ran, not a stiff solver. Read the game log
  for assets that failed to load (an FBX import that saved the mesh but not its new skeleton plays no animation in
  game while the editor session looks fine); the capture tool fails on load errors and on zero motion. UE anim graph
  node classes go in an UncookedOnly module: an uncooked game recompiles anim blueprints on load without Editor modules.
- `rd.secondary.fit`: reuse swing bones a rig already has (VRM J_Sec_*, a rig standard) by name. Order skirt rings at
  the hem, not the roots (roots often start at the hip joint). Body collider samples skip cloth hanging on chains;
  mirrored pairs that disagree take the smaller radius (clothing only inflates a body fit).

Evidence locator: project-local `modules/astra-secondary-motion` (Tests/benchmark.json) and `.rd` records of
2026-10-09.
