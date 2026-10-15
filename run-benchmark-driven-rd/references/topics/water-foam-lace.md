# Water: stylised foam and breaking crest (provisional)

Load only for shader foam on water (swash, shore foam, breaking crest) in a stylised (anime) look. Single workflow
owner: R&D; Cleanup measures the evidence. One-project candidate, not a universal quality claim.

- `rd.foam.no-clusters`: never draw foam as many same-size, evenly spaced round holes, dots or bubbles (Voronoi "bubble
  lace", regular pores or speckle fields). The human rejected that at first sight as trypophobia-triggering (2026-10-10,
  rolled back the same night) and clarified on 2026-10-11 that the trigger is uniform size and regular spacing, not
  materials with holes ("大小都一致還很規則型"). Check every capture for same-size regular clusters before showing it.
- `rd.foam.shapes`: stylised foam is a few large smooth shapes: noise-warped flowing bands with clean cel edges,
  long streaks that follow the flow, large soft scallops, open water between patches; it moves as a whole.
- `rd.foam.distance`: once a pattern falls under ~3 pixels, resolve it to a crisp white shape where the foam is
  substantial, never to a grey average: the stylised read is lost at distance.
- `rd.foam.density`: check shallow sand bars, where land probes succeed almost everywhere and a shore term turns
  into a sheet across the shallows.
- `rd.foam.crest`: a breaking crest reads from a solid white crown; a wide band in mesh UV space shows a coarse crest
  mesh as straight polygon edges, so keep the crown narrow and break its edge with smooth world-space shapes. Shade
  foam by the face's own light for volume, capped below 1.
- `rd.foam.hdr`: any exp(-x/k) of a signed distance must clamp x at 0; unclamped it explodes past the front and
  partial foam edges glow (bloom halos). Clipped 1.0 maxima in an otherwise 0.6 scene are a math bug, not brightness.
- `rd.foam.review`: A/B in a scratch lab with a deterministic forward-only clock (same time, same camera, original vs
  lab material swapped by parent), several wave phases, near, far and top views; keep the previous assets with
  their hashes so a rejected look rolls back byte for byte.

Evidence locator: project-local `.rd/water-reference-20260930/foam-v2` (v2-v6 rejected, PREVIOUS restore) of
2026-10-10.
