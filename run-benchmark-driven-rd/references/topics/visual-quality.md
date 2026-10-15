# Refined visual delivery (provisional workflow guidance)

Use for user-facing visual/UI/material/art implementation and refinement, not
backend-only work. Workflow owner: R&D; independent provider:
[visual audit](../../../code-cleanup-helper/references/topics/visual-quality-audit.md).

- `rd.visual.intent`: default to a refined, intentional result within the user's
  established art direction. Preserve an explicit prototype, minimalist style or
  performance constraint. Record project-specific preferences once in its own
  instructions/style contract; do not wait for repeated requests for polish.
- `rd.visual.polish-loop`: identify focal hierarchy, representative art, viewing
  scale, material cues, motion and budget. Implement, capture in the actual target
  renderer, inspect and fix the most visible owned defects, then recapture. Check
  silhouette/alpha, form/detail balance, lighting/depth, typography, transitions
  and small/large viewing sizes where applicable. Detail must support clarity.
- `rd.visual.evidence`: keep diagnostic fixtures, concept art, native rendering,
  internal visual review and human acceptance separate. A compile, shader count,
  higher resolution or pretty mockup cannot prove finished native appearance.
  Retain before/after artifacts and settings; mark missing art/renderer/review
  unmeasured, not PASS. Never substitute generated imagery for a runtime capture.
- `rd.visual.budget`: prefer reusable controls and scalable quality presets over
  maximum settings everywhere. Bound layers, overdraw, texture/RT memory, motion
  and effect density. Proactive polish does not authorize paid generation,
  publication, scope expansion or automatic approval. Respect required review.
- `rd.visual.domains`: arranging a town level into a game main city: read
  [environment-town-layout.md](environment-town-layout.md); stylised water foam and breaking crests: read
  [water-foam-lace.md](water-foam-lace.md); combat VFX impact feel, masks and noise erosion: read
  [vfx-impact-feel.md](vfx-impact-feel.md).

Evidence locator: visual-polish-default-20260908. Generic policy requested by the
user; comparative aesthetics remain unmeasured. Local positive/negative examples
separate native functional proof from decorative fixtures and explicit rough
prototypes. Revalidate with representative artifacts; editing instructions does
not train model weights or guarantee future subjective approval.
