# Remotion photo workflow implementation plan

**Goal:** Optional, portable photo-pair composition driven by verified edit results.
**Architecture:** Python validates/stages/verifies; a pinned Node/React project
renders pictures and Studio previews. FFmpeg preserves master audio on full export.
**Stack:** Python standard library, FFmpeg, Remotion, React, TypeScript, Node test runner.

1. Add failing plan tests for source/output anchors, deleted ranges, overlaps,
   unknown fields, asset paths and phase durations. Implement editing/visual_plan.py.
2. Add prepare/render integration contracts; implement scripts/visual.py and
   editing/visual_pipeline.py using existing media verification helpers.
3. Add remotion/package.json and lock, src/Root.tsx and PhotoPair.tsx; pin all
   Remotion packages together. Add runner for Studio, silent render and stills.
4. Run short real render with synthetic master and two photos; inspect phase
   keyframes and verify original AAC payload, no-audio and preview behavior.
5. Update Skill/README/visual reference and add remotion-integration.md and sample
   visual plan. Document installation, missing runtime guidance and support limits.
6. Add conditional smoke test to the two existing CI jobs without duplicate runs.
7. Independent review; fix concrete findings, run checks, commit and create PR #2.
