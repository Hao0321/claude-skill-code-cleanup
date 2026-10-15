# Character locomotion: authored gaits, native blend, playground integration (provisional)

Load only for authoring or playing walk/run/sprint/jump clips on a rigged character. Single workflow owner: R&D;
Cleanup measures the evidence. One-project candidate, not a universal quality claim.

- `rd.locomotion.source`: when original authored animation is required, verify clip provenance instead of trusting an
  "original" label. Author from the rig: leg length gives Froude-scaled speeds, duty factor, stance sweep
  = speed x duty x period, heel and ball pivots, two-bone leg IK with the lateral axis as hinge. Prove no slide with a
  floor scrolled at the travel speed in the preview.
- `rd.locomotion.blender`: Blender 4.4+ layered actions animate only through `animation_data.action_slot`; rigging
  tools leave `pose_position = 'REST'`, which ignores every key. Set the scene frame rate before an FBX export: a
  24 fps scene stretched 30 fps keys by 1.25. The importer compares every clip length with the authoring report.
- `rd.locomotion.hinge`: aim limbs by frame mapping (new frame from direction and hinge, times the rest frame). A
  forearm frame built from its own direction degenerates near straight (palms flip); share the elbow hinge.
- `rd.locomotion.blend`: one gait phase for every cyclic clip, rate = speed / blended cycle distance, so each clip
  plays at its authored rate at its authored speed and strides interpolate between. A trapezoidal phase and a speed
  follower exact for linear ramps keep 30/60/120 fps feet together; test probe times must lie on every rate's grid.
- `rd.locomotion.air`: jump start only when rising at take-off, a walk-off fall keeps the gait for a short delay
  (curbs), landing weight from the touchdown speed and lower while running; lean the body about the feet toward the
  smoothed ground acceleration (starts, stops, turns), capped.
- `rd.locomotion.ue427`: a native AnimInstance proxy that overrides `Evaluate` skips the graph, so Blueprint children
  carry only class defaults (no montages). `UAnimSequenceBase::GetPlayLength()` is non-const (`SequenceLength`).
  Python: no Blueprint generated-class accessor (load `<asset>_C`); a bool UFUNCTION with an out parameter returns
  only the out value (None on failure); struct elements read from an array are copies, so edit them, collect them and
  write the whole list back (in-place edits left every material slot empty and the character grey). Read the asset
  back after saving; a remote client can land on a running `-game` process instead of the editor.
- `rd.locomotion.review-look`: an Unlit NPR character reviewed under the art loop's manual exposure went near-black
  under the game camera's default histogram exposure in the sunlit town. Give the player camera the review look before
  judging art. Launch UE from PowerShell: Git Bash rewrote the `/Game/...` map argument and the run loaded no map.
- `rd.locomotion.capture`: scripted drive (verb:seconds segments, heading turns, camera yaw offset) at fixed 60 Hz,
  stride 1, plus a labelled key-frame sheet; front three-quarter for the face, side for the gait.

Evidence: sanitized single-project workflow observations; raw clips, paths and reports remain project-local.
