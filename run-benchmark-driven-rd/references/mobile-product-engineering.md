# Shared Mobile Product Engineering Memory

Use this reference for responsive web apps, PWAs, hybrid shells, installed web apps, and mobile-first product surfaces. It is a benchmark contract, not a style trend list.

## Table of Contents

1. User task and provenance
2. Touch targets
3. Navigation and hierarchy
4. Safe areas, viewport, and keyboards
5. Responsive layout
6. Interaction performance
7. Frozen test matrix
8. Failure memory
9. Production platform architecture
10. Browser history and PWA lifecycle
11. Installation is a retained capability
12. Release identity and bounded recovery
13. Cross-major supply-chain upgrades are product migrations
14. Permanent QR device binding

## 1. Start from the user task, not a device mockup

Freeze the task, app state, viewport, orientation, build identity, input method, and expected completion path. A screenshot can reveal visual problems, but it cannot prove that controls are reachable, targets are large enough, the keyboard is safe, or the final action can be completed.

For each primary surface, record:

- the first meaningful task;
- how many fully visible actionable targets appear before persistent navigation;
- document overflow versus intentional component-local scrolling;
- every visible custom target's bounding box;
- fixed/sticky layers and their paired content insets;
- console/runtime errors;
- field metrics separately from lab diagnostics.

Do not compare baseline and candidate unless they use the same build mode, frozen data, viewport, route, and measurement implementation.

## 2. Touch-target contract

- Use `44 x 44 CSS px` as the default minimum for custom product controls. This matches WCAG 2.5.5 Target Size (Enhanced) and is a practical cross-platform mobile floor.
- Prefer `48dp`-equivalent space for primary Android actions and frequently used or destructive controls. Android recommends at least `48dp x 48dp` touch targets.
- WCAG 2.5.8 Level AA permits `24 x 24 CSS px` or a spacing exception, but that is a compliance floor, not a good default for a touch-first product.
- The hit area may be larger than the visible icon. Icon-only controls still require an accessible name.
- Measure computed bounding boxes. Declaring `min-height` is not proof when a more specific rule, inline style, transform, or parent layout makes the actual target smaller.

Sources:

- W3C WCAG 2.2 target minimum: https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum
- W3C target enhanced: https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced
- Android accessibility touch targets: https://developer.android.com/guide/topics/ui/accessibility/views/apps-views

## 3. Navigation and hierarchy

- A bottom tab bar is for stable top-level destinations, not current-page actions.
- Keep destination count low, labels short, order stable, and current state visible through more than color.
- Do not make one top-level destination look like a floating action unless it actually performs an action. This creates a false hierarchy.
- Persistent navigation must have a matching page padding/scroll-padding budget so the last task can move completely above it.
- A mobile first screen should expose the next task, not spend most of the viewport on a decorative hero. Measure first-screen task density rather than relying on aesthetic judgment.

Source: Apple HIG Tab bars: https://developer.apple.com/design/human-interface-guidelines/tab-bars

## 4. Safe areas, viewport units, and keyboards

- Use `viewport-fit=cover` only with `env(safe-area-inset-top/right/bottom/left)` on edge-to-edge fixed and sticky UI.
- Use `dvh` for current mobile viewport height with a `vh` fallback where needed. Do not assume `100vh` equals the visible area while browser chrome changes.
- An on-screen keyboard can shrink the visual viewport without shrinking the layout viewport. Avoid keyboard-critical actions that are fixed only to the layout viewport; keep a scrollable fallback and verify on real devices.
- On compact web layouts, keep text inputs at a computed font size of at least `16px` to avoid iOS focus zoom.
- Test portrait and short landscape. Width breakpoints alone miss the most common fixed-toolbar failures.

Sources:

- Apple HIG Layout and safe areas: https://developer.apple.com/design/human-interface-guidelines/layout
- MDN `env()` safe-area variables: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Values/env
- MDN VisualViewport and on-screen keyboards: https://developer.mozilla.org/en-US/docs/Web/API/VisualViewport

## 5. Responsive layout rules

- Mobile is a task-specific composition, not desktop scaled down. Reorder, collapse, or replace presentation-only regions when they delay the primary task.
- Prefer fluid layout plus a small number of semantic breakpoints. Per-page breakpoint patches without shared tokens produce cross-page drift.
- Horizontal rails are acceptable when they are explicit local scroll containers. `overflow-x: hidden` on the document is a guardrail, not evidence that nothing is clipped.
- Avoid fixed pixel heights for text-bearing controls. Use minimum size plus content-driven height.
- Prefer class-based product contracts for shared controls; extensive inline dimensions prevent responsive overrides and make regression rules brittle.

## 6. Interaction performance

- Treat responsiveness as a field metric. A good INP target is `<= 200 ms` at the 75th percentile, segmented by mobile and desktop.
- Lab interaction traces are diagnostic until field/RUM evidence exists.
- Large client-rendered DOM updates and long startup tasks can delay input. Measure before applying optimizations such as `content-visibility`.

Source: web.dev Optimize INP: https://web.dev/articles/optimize-inp

## 7. Minimum frozen matrix

Recommended web/PWA diagnostic matrix:

- `360 x 800`: narrow Android portrait;
- `390 x 844`: primary compact iPhone-like portrait;
- `430 x 932`: large phone portrait;
- `844 x 390`: short landscape guardrail.

For every primary surface, gate:

1. document `scrollWidth <= clientWidth`;
2. primary custom targets `>= 44 x 44 CSS px` unless an explicit exception is recorded;
3. no fixed/sticky layer makes the final action unreachable;
4. input computed font size `>= 16px` on compact layouts;
5. console errors `== 0`;
6. reduced-motion and keyboard/focus states remain operable;
7. build, state mutation, persistence, and existing product QCs do not regress.

Real-device safe area, virtual keyboard, thermal behavior, one-handed reach, p75 INP, and human task-completion rate remain `unmeasured` until target-device or field evidence is recorded.

## 8. Reusable failure memory

- **Media-query patchwork:** every page technically has mobile CSS, but controls and insets disagree. Prevent with shared tokens and one cross-page benchmark.
- **Visible-is-usable fallacy:** an 18px plus icon is visible but unreliable. Make the whole pill or row the target.
- **Hero-first mobile:** branding occupies the first screen while the task begins below the fold. Gate first-screen actionable targets.
- **Floating-tab confusion:** a navigation destination is styled as a primary action. Keep tab semantics consistent.
- **Fixed-layer amnesia:** toolbar safe-area padding is added but content padding is not. Treat them as one paired contract.
- **`overflow: hidden` as QA:** clipped content disappears from the metric. Compare document geometry and inspect component-local rails.
- **String-only QC:** checking that `@media` or `min-height` exists does not measure computed behavior. Use browser geometry on the frozen matrix.
- **Desktop browser as final proof:** responsive emulation is diagnostic. Keep keyboard, notch, installed PWA, field INP, and human completion claims unmeasured until real evidence exists.

## 9. Production mobile platform architecture

Once geometry is stable, promote mobile behavior into a small capability layer rather than adding page-specific listeners.

- One entry-point runtime should coalesce VisualViewport resize/scroll, window resize/orientation, standalone display mode, and coarse-pointer changes. Publish CSS variables and root datasets; keep React pages presentation-only.
- Treat keyboard detection as a guarded inference: require meaningful visual/layout viewport occlusion plus a focused editable element. Browser chrome movement alone must not hide navigation.
- Persistent bottom navigation and the focused-input lifecycle are one system. When keyboard occlusion is active, hide or relocate fixed navigation and remove pointer interception, then restore it deterministically.
- Reusable sheets need a complete lifecycle primitive: semantic dialog labelling, nested-safe body scroll lock, initial focus, Tab containment, Escape close, and focus restoration to a still-connected opener.
- Local PerformanceObserver output is diagnostic, not RUM. Label unsupported or absent field metrics `unmeasured`; never infer p75 INP from a lab event sample.
- Durable browser regression should run a production-compiled frozen harness. Gate that harness behind a dedicated build mode and verify that normal production builds cannot expose or bundle it.
- Supply-chain health is part of production hardening. Record advisory counts before and after compatible updates, rerun build/E2E, and isolate breaking dependency upgrades in their own benchmark.

Reusable failure patterns:

- **Dev-lab production mismatch:** a query-based lab works in Vite dev but silently falls through to authentication in preview. Use an explicit E2E build mode with a normal-production exclusion proof.
- **Viewport listener sprawl:** each page interprets keyboard and browser chrome differently. Centralize measurement and expose a stable state contract.
- **Modal shell duplication:** drawers look similar but disagree on focus, scroll lock, and Escape. Migrate content into one lifecycle primitive before multiplying overlays.

For commerce-specific product cards, preview-versus-purchase state, generated imagery, and normalized dialog evidence, also read [web-commerce-acceptance.md](web-commerce-acceptance.md).

## 10. Browser history and PWA lifecycle are product state

Mobile productization is incomplete when React knows the visible screen but the browser does not.

- Model primary surfaces and full-screen overlays as a small versioned state machine. Keep History state and canonical URLs synchronized through one mutation boundary.
- Use `pushState` when entering a genuinely new base destination or entering overlay mode. Use `replaceState` when one overlay supersedes another or an overlay commits to a base surface; otherwise Back becomes a replay log of obsolete UI.
- Close an overlay with `history.back()` only when the current entry is app-owned and a safe prior app entry exists. Direct deep links need a replace fallback so Close never ejects the user from the site.
- Serialize only stable, context-free identifiers. Chat targets, drafts, private room data, and transaction payloads do not belong in URLs or History. Context-dependent overlays should be excluded from deep-link restoration.
- Treat OS/browser Back as an acceptance journey: overlay Back first, surface Back second, with base content and focus restored and no document reload.
- Service-worker freshness and task continuity are competing concerns. Prefer a visible prompt before activating a waiting worker when the app contains multi-step editing, games, purchases, or forms.
- A PWA lifecycle surface should distinguish offline, reconnected, offline-ready, update-ready, applying, and registration error. Give users a safe retry or postpone action; keep touch targets at least 44px.
- Deterministic service-worker state overrides prove UI/state logic only. Installed-PWA activation timing, OS eviction, back gestures, and device cache behavior remain unmeasured until target-device testing.

Reusable failure patterns:

- **React-only navigation:** the screen changes but Back leaves the product. Centralize surface/overlay History semantics.
- **Overlay archaeology:** Back reopens every intermediate modal. Replace superseded overlay entries.
- **Unsafe restoration:** an overlay ID reloads without the context it needs. Maintain a deep-link-safe allowlist.
- **Silent worker takeover:** an update activates during an unfinished task. Prompt, explain, and let the user choose the activation moment.

## 11. Installation is a retained capability

PWA installation is a transient browser capability, not a button that any page can recreate on demand.

- Capture `beforeinstallprompt` at startup, before routed or authenticated product pages mount. Retain the event behind one external-store boundary and let UI subscribe to state.
- State precedence should be explicit: installed/standalone wins over a retained native prompt; a retained prompt wins over platform-specific manual guidance; iOS browser mode may expose Add to Home Screen instructions; absence of all capabilities is unavailable, not an error.
- `appinstalled`, `display-mode: standalone`, and legacy iOS `navigator.standalone` are related observations. Treat them as capability signals, not proof that every OS launch path was tested.
- Put install discovery in a durable product location such as Profile or Settings. Avoid global install banners that compete with editing, purchases, games, or recovery states.
- Native prompt dismissal cannot be treated as installation failure or immediate retry permission. The consumed prompt event may not be reusable; wait for the browser to offer a new event and never fake installed state.
- Test overrides must be compile-time gated to a dedicated E2E build. Query parameters that can synthesize installed state in normal production are an integrity failure.
- Manifest acceptance should include stable `id`, canonical `start_url`/scope, display fallbacks, language/theme, any and maskable icons, and shortcuts whose URLs obey the app's canonical navigation state.

Real prompt delivery, OS-specific install UI, icon cropping, standalone launch behavior, and uninstall/reinstall behavior remain unmeasured until target-device tests exist.

Reusable failure patterns:

- **Late-listener install button:** Profile mounts after the only install event fired. Retain intent at startup.
- **Install nag as navigation:** a global banner repeatedly interrupts the main task. Use a durable Profile/Settings surface.
- **Dismissed means installed:** UI optimistically marks success after calling `prompt()`. Wait for `userChoice`/`appinstalled` and keep outcomes distinct.

## 12. Release identity and bounded recovery

An installed or long-lived mobile web client needs to identify its exact build and recover stale App Shell files without treating all browser storage as disposable.

- Derive runtime version, commit/build identity, mode, and a release ID from one build object. Emit the same object as a small `release.json` receipt and assert runtime/receipt equality in a production-compiled browser test.
- Service-worker update policy must have exactly one owner. A visible prompt is meaningless if another entry point registers the same worker and auto-activates it.
- Keep a minimal pre-React boot guard because the main module itself can fail before React error boundaries exist. Its health handshake must be acknowledged after a successful React commit.
- Automatic recovery needs a release-scoped budget, reason, time window, and durable session record. One attempt per release/reason window is a conservative default; repeated failure must settle on a stable recovery surface rather than loop.
- App Shell repair uses an allowlist, such as HTML and Workbox precache caches. Never automatically clear every Cache Storage entry, LocalStorage, IndexedDB, Firebase state, uploaded work, or large art caches.
- Request a service-worker update before reload when possible. Automatic unregister is a last-resort support operation, not routine self-healing.
- A recovery surface should distinguish retry from App-file repair, return to a canonical safe route, expose a support/release code, and use touch-safe actions. Copy must not promise that cloud or user data was repaired.
- If SessionStorage or another control store is unavailable, prefer a stable manual recovery UI over unbounded automatic mutation.

Synthetic chunk errors and local cache fixtures prove policy and UI only. Crash-free session rate, OS eviction, corrupted storage, partial CDN deploys, and service-worker races require field or target-device evidence.

Reusable failure patterns:

- **Two SW owners:** update prompt says “later” while entry code activates immediately. Count registration owners in QC.
- **Blanket cache self-heal:** a timeout deletes all caches and unregisters every worker. Allowlist App Shell artifacts and cap attempts.
- **Anonymous support screen:** error UI has no version/commit identity. Emit and display a release receipt.
- **Recovery loop:** the same stale release reloads forever. Scope attempts by release and reason, then stop automatically.

## 13. Cross-major supply-chain upgrades are product migrations

A security-driven Vite, bundler, native-module, or framework upgrade changes the production system, not just `package-lock.json`.

- Establish the supported Node runtime before changing the dependency graph. Pin it in the repository and enforce the same floor in package metadata and CI/QC.
- Move tightly coupled build packages as one coherent set. When peer resolution deadlocks, remove the obsolete set and install the new compatible set cleanly; do not normalize `--force` or `--legacy-peer-deps` as the migration path.
- Require four independent gates: zero known advisories, deterministic supply-chain assertions, the full production-compiled browser journey suite, and a normal production build that excludes test-only assets.
- Compare named production chunks against a frozen baseline. A semver-compatible update can pass every functional test while materially increasing transfer size; keep or exact-pin the benchmarked release until the regression is understood.
- E2E fault injection must wait for the product lifecycle owner to report readiness. `DOMContentLoaded` proves document parsing, not that lazy application modules, service workers, history ownership, or network listeners are active.
- Source analysis must explicitly exclude generated and temporary build roots. When upgraded framework rules reveal real lifecycle findings, keep the rules enabled, fix the source set, and rerun product journeys because lint-motivated state timing changes are behavioral changes.
- Record rejected update candidates as evidence. A failed experiment is reusable architecture memory when it names the version, metric, threshold, and rollback decision.

Reusable failure patterns:

- **Runtime-floor mismatch:** a new build tool installs but the deployed CI/runtime cannot execute it. Pin and gate Node first.
- **In-place peer deadlock:** the old plugin and new bundler each constrain the other. Replace the coupled set atomically without bypassing peer checks.
- **Audit-only confidence:** advisories reach zero while product journeys or bundle budgets regress. Security, behavior, and delivery cost are separate gates.
- **Compatible-update bundle inflation:** a routine dependency update silently enlarges a named chunk. Treat the bundle budget as a release blocker and retain the measured version.

## 14. Permanent QR device binding

“Scan once” is a durable authorization claim, not a longer in-memory session. Use a short-lived, single-purpose QR bootstrap to exchange for a random per-device credential. Remove the bootstrap from browser history immediately; store only a one-way credential hash on the host, keep the raw credential in an HttpOnly／SameSite cookie or OS credential vault, and use `Secure` whenever the origin is HTTPS.

Promotion requires one same-device journey that pairs, removes the QR secret from the URL, restarts the Remote service or desktop app, reconnects without another QR, performs an authorized action, revokes that exact device, and then receives an authorization failure with the old credential. Also prove that stopping Remote preserves trust, while explicit revoke—not ordinary shutdown—removes it. Device names/IDs are labels, never authenticators.

Keep stable reachability separate from durable authorization. A remembered credential cannot reconnect to an unavailable or changed origin by itself. Prefer an owned stable HTTPS URL for cross-network use and a stable local port/hostname for LAN; if the product falls back to an ephemeral port, explain that authorization remains valid but the user may need the current link. Public tunnel ownership, TLS, background availability and real-device browser storage eviction remain separate obligations.

For different-network control, both desktop and phone should normally make outbound authenticated `wss://` connections to an owned stable relay origin; this avoids requiring inbound ports, same-LAN discovery, or exposing private file paths. LAN fallback is diagnostic availability, not cross-network completion. The permanent room identity and per-device authorization are separate: the stable room may be retained, but bootstrap secrets must expire and raw long-lived device credentials belong in an HttpOnly／Secure／SameSite cookie or OS vault, never URL, Web Storage, logs, receipts, worker source, or installer configuration. Relay messages must be bounded, origin-checked where HTTP is used, and revalidated against host-side revocation rather than trusted merely because a socket survived.

Before treating deployment failure as a product defect, preflight the actual cloud account identity, target zone/domain ownership, and write scopes required by the provider. A local Durable Object／relay smoke can close protocol behavior; it cannot close DNS, TLS, service ownership, provider availability, or real 5G-to-home-device acceptance. Quick/development tunnels with random hostnames remain test fixtures even when they happen to work across networks.

Required controls include per-device listing/rename/revoke, bounded device count, credential rotation when the same device re-pairs, fail-closed malformed store handling, atomic persistence, no plaintext credential at rest or in logs/receipts, and a lost-device recovery path. “Permanent” means until user revocation, browser/site-data deletion, host reset or policy expiry; it never means irrevocable.
