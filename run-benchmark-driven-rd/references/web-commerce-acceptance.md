# Web commerce acceptance

Use this contract for storefronts, catalogues, carts, checkout, product administration, generated product imagery, and responsive commerce UI. It closes the gap between source-level tests and an interface that a buyer or operator can actually use.

## 1. Separate commercial states

Model at least these states independently:

- catalogue-visible but not purchasable;
- purchasable and in stock;
- purchasable but out of stock;
- archived or internal-only;
- blocked by external facts such as price, label truth, rights, business identity, payment, or fulfillment.

Enforce purchase readiness in the server or domain layer. Disabling a frontend button is not a gate. Re-sanitize persisted carts after the catalogue changes, and exercise idempotency, inventory reservation, cancellation, and inventory restoration with a real request journey.

Never invent price, ingredients, allergens, origin, shelf life, supplier identity, image rights, legal entity details, or public availability to make a demo look complete. Keep those obligations `blocked_external` with an owner, condition, and closing action.

## 2. Product-card interaction contract

A whole-card pointer affordance may coexist with explicit controls, but do not give a container `role=button` or keyboard activation when it contains favourite, add-to-cart, or other interactive descendants. Expose a real, named detail button or linked title; stop propagation only where the nested action requires it. Gate:

- one unambiguous keyboard path to product detail;
- icon controls with accessible names;
- no nested interactive semantics;
- preview and buy actions remain visually and behaviorally distinct;
- unavailable products cannot enter the cart through API or stale local state.

Static markup review is diagnostic. Use a browser accessibility snapshot or computed DOM journey for promotion.

## 3. Overlay and dialog lifecycle

`isVisible()` alone is not proof. A dialog may exist in the DOM behind its backdrop, outside the viewport, before an image paints, or without a usable focus lifecycle.

For every primary dialog and drawer, measure after a settled paint:

- bounding box stays within the viewport;
- dialog stacking is above the matching backdrop;
- background scroll is locked and restored;
- initial focus enters the dialog;
- Tab remains contained where modal semantics apply;
- Escape and explicit close work;
- focus returns to a still-connected opener;
- accessible name and modal semantics exist;
- desktop and compact layouts keep the final action reachable.

Record the failure as `integration`, not cosmetic polish. Centralize the overlay shell before multiplying modal implementations.

## 4. Same-build browser matrix

Use [mobile-product-engineering.md](mobile-product-engineering.md) for viewport selection and touch rules. All routes in one comparison must share build ID, dataset ID, browser/runtime identity, and measurement implementation.

Capture a project-native raw report, then validate its normalized contract:

```powershell
$env:PYTHONUTF8='1'
python scripts/web_acceptance_gate.py <web-acceptance.json> --root <project-or-evidence-root>
python scripts/web_acceptance_gate.py --self-test
```

Schema v2 requires a closed-world matrix and dialog list, document geometry, browser console results, completed primary tasks, measured controls, compact input font sizes, dialog lifecycle evidence, and an explicit non-empty list of stronger real-device or field claims that remain unmeasured. It also requires live SHA-256／byte identities for the project-native collector implementation, its raw browser capture, and every negative-control report. Paths must be repo-relative, non-symlink files below `--root`.

The normalized JSON is not a browser. A list of control names is not calibration evidence. Keep the raw browser snapshot/geometry collector and its identity beside the report. Each `negativeControls[]` entry must point to a live normalized report that the gate replays and confirms emits its expected failure code. Controls cover horizontal overflow, undersized targets, console errors, provenance drift, incomplete tasks, paint/stacking/viewport failures, background scroll, initial and contained focus, Escape, focus restoration, accessible naming, modal semantics, and compact inputs below 16px. Re-run the gate after the last collector, contract, raw-evidence, or negative-report mutation; saved stdout alone is not freshness proof.

## 5. Generated product-image contract

Keep three claims separate:

1. **Identity reference:** the source catalogue identifies the intended product.
2. **Generated advertising visual:** a model restages that product in a consistent commercial scene.
3. **Shipment truth:** actual packaging, label, size, color, and contents are verified from the deliverable product.

For every generated main image, retain a source-reference path and stable product key. Use Cleanup `artifact_set_assertions` to gate one-to-one membership, count, minimum bytes, prohibited duplicate formats, and promotion freshness. Then add content QA:

- contact-sheet review covers the entire closed-world catalogue, not a sample presented as complete;
- source lighting casts are treated as capture defects unless product identity requires that color;
- normalize implausible blue, cyan, magenta, green, or jaundiced casts to credible ingredient color;
- do not add logos, certifications, health claims, ingredients, packaging text, or serving quantity not supported by the source;
- packaged products may preserve silhouette and layout, but generated text is not label evidence;
- disclose generated imagery; source catalogue comparison belongs in an authenticated operator surface, not the public storefront when source rights are unconfirmed;
- commercial usage rights remain an external obligation until the rights owner confirms them.

Record regenerated outliers by stable product ID and reason. A count of existing files proves neither color quality nor non-misleading advertising.

Treat generated-output publication and source-reference retention as different trust zones. Promotion requires task-shaped evidence that:

- generated advertising images may live under the public web root, while supplier/reference originals live outside every public／static／upload directory;
- Cleanup still pairs public generated assets to private references by stable key and forbids any source-role file under the public root;
- public catalogue APIs omit source paths, internal keys and reference metadata rather than merely hiding the link in the frontend;
- every legacy source URL returns `404` even if a future import accidentally recreates the old public folder;
- unauthenticated source-image requests return `401／403`, while an authorized operator route returns only the intended media type with private or no-store caching;
- deployment and import workflows preserve this boundary instead of copying private references back into the served tree.

Moving references out of public closes an exposure bug; it does not grant the right to upload or use them as model input. Keep commercial usage rights `blocked_external` until the rights owner confirms that separate use.

## 6. Completion boundary

Internal commerce readiness can close when the closed-world capability ledger, server-side purchase gate, browser matrix, dialog journeys, asset pairing, correctness tests, security audit, and fresh Cleanup promotion evidence pass.

Public commerce readiness additionally needs verified business identity, product truth, image rights, customer-service channels, domain/TLS, fulfillment operations, jurisdiction-specific legal review, and a production order journey. Payment may remain intentionally deferred if the user chose cash on delivery or catalogue-only launch; record that choice instead of calling the payment module missing.
