# VFX: impact feel, mask fidelity and stepped erosion for cel combat effects (provisional)

Load for UE 4.27 combat VFX (hits, shake, flash, impact frames, hit-stop, finish), cel masks, meshes and erosion.
Owner: R&D; Cleanup measures. One-project candidate.

- `rd.vfx.mask-fidelity`: never pad non-POT masks to POT plus a cap (1254 px kept ~313 px); resample offline to POT,
  UV scale 1, TC_Grayscale; prove with a crop A/B.
- `rd.vfx.noise`: wrapped equalised lattices, 4 fBm octaves, gain 0.4, about one period per shape: dissolves break
  into a few large pieces (trypophobia = many same-size, regular holes).
- `rd.vfx.stepped-erosion`: shape minus progress plus progress-scaled noise; dissolves go rim first in three steps;
  a seed can ride in `frac(Cell+0.5)`.
- `rd.vfx.cel`: crisp flat bands that still glow: fade by erosion, not alpha; masks a few mips down so cuts follow big
  shapes, not grain; ink edge; soft coloured glow outside the cut and an HDR hot core (opaque fills alone read as paper
  cut-outs in daylight); fire = ink red, body, yellow, white-hot centre; ice and water glassy.
- `rd.vfx.uv-arc`: stretching had two causes: uneven parametric UVs (2-4x in one mesh; re-space each UV-grid piece
  by mean normalised arc length, headless Blender) and tiling (texels/m along U and V with the runtime scale
  10-20x apart): aim ~1:1 for runes and cracks, <= 3x along a flow, whole tilings on rings, flow speed scaled,
  noise in mask space.
- `rd.vfx.events`: hits are age crossings of the motion's own timings, one list at 30/60/120 Hz; holds freeze the
  age. Snap release and cancel ages to whole ms (the float clock differs per frame rate).
- `rd.vfx.screen`: one unbound post-process volume, weight 0 when idle; tints <= 0.3; impact frames opt in, <= 3/s;
  posterise a blurred luminance; a finish darkening is a vignette around the hit.
- `rd.vfx.volley`: in multi-hit patterns only the finisher flashes (three in 0.3 s strobed).
- `rd.vfx.finish-debris`: debris elongated along its motion; small rimmed round flakes read as rings.
- `rd.vfx.merge`: patch replay keeps each file's line ending; touch copied sources (copy2 mtimes fool UBT).
- `rd.vfx.ue-python`: 4.27 wraps a class without Blueprint-visible members as its parent; `load_blueprint_class`;
  no RGBA pin on vector parameters.
- `rd.vfx.review`: before/after in the user's level, deterministic, third person straight behind, before = the exact
  pre-change build; perf lock before heavy steps; judge darks on a bright plate.
- `rd.vfx.patterns`: mix staged launches, continuous strikes and sustained effects, one OnImpact per hit (single-hit
  skills read as small moves).
- `rd.vfx.mesh-kit`: crescents face the third-person camera; view-projected streaks only side-on; dense masks on wide
  bands become dark discs; crack masks in a few large tiles per shape (many = cells), translucent.
- `rd.vfx.ground`: floor from one small multi sphere sweep (WorldStatic), first hit not started inside: 4.27 single
  sweeps skip the post-filter (a dummy returns distance 0).

Evidence: project `.rd/vfx-20260930/`, `modules/astra-vfx/Tests`.
