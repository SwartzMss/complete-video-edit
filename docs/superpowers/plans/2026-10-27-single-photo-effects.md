# Single-photo effects implementation plan

**Goal:** Implement issue #7 with single-photo fade, contained slow zoom and picture-in-picture, preserving old photo-pair plans and the existing audio/timeline pipeline.

**Architecture:** Add `photo-single` to visual plan v1. Independent layout (`center`/`pip`) and motion (`none`/`ken-burns`) parameters share fade entry/exit and one reusable component. Resolve stage-specific review frames for single effects; preserve the old pair component and legacy prepared-workspace fallback. Skill rules select a suitable style before rendering and mention alternatives only after successful delivery.

**Tech Stack:** Existing Python validator, pinned Remotion/React/TypeScript, unittest and existing two-platform CI.

## Accepted parameter contract

- Existing photo-pair fields/defaults stay unchanged; new fields rejected for pairs.
- Single effects use exactly one `photos` item. Common timeline fields and non-overlap rules remain unchanged.
- Single optional fields: `layout` (center default / pip), `motion` (none default / ken-burns), `entry_frames`, `exit_frames`, `scale`, `position`, `margin`, `zoom_factor`, `layer`.
- Entry/exit each at least one frame; duration >= entry + exit + one visible frame. Default transitions adapt to short windows.
- Center scale defaults .88, allowed .1–.95. PiP scale defaults .30, allowed .1–.45; four corner positions, default bottom-right, margin .04 in [0,.2]. Position/margin only for PiP. Scale + twice margin must fit inside canvas.
- Ken Burns zoom factor defaults 1.08 in (1,1.2]; picture grows from scale/zoom_factor to scale using contain. No cropping or arbitrary pan. Zoom factor only accepted for ken-burns.
- PiP does not dim the master. Geometry checks cannot establish absence of semantic obstruction; content inspection remains required.
- Slide-in is deferred; unsupported options error. No new package, workflow job or audio pipeline.

## Steps

- [ ] Extend plan tests for defaults, one-photo count, bad parameters, minimum duration, source mapping and pair compatibility; observe failure before implementation.
- [ ] Refactor common effect parsing and implement the single-photo resolver without changing pair values. Add PhotoSingle.tsx and dispatch from Root.tsx, including old props compatibility.
- [ ] Extend keyframe extraction with single review frames; keep pair fallback. Add real short-media coverage for three styles, frame boundaries, portrait/landscape aspect ratios, PiP outside-region preservation, full audio payload and preview frame matching.
- [ ] Update Skill delivery/selection rules with concrete examples, Remotion documentation, README and visual-plan examples. Clearly distinguish technical verification from content review and one-second preview from complete delivery.
- [ ] Run full tests with rendering, TypeScript check, inspect rendered frames, independent review and diff check. Create PR closing #7 and await existing Ubuntu/Windows CI.
