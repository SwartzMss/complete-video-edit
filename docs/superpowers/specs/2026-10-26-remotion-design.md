# Optional Remotion photo workflow

User-approved scope: official skill reuse and one runnable parameterized photo-pair
template, not a generic effects engine. Keep edit-plan v1 and Python edit commands
unchanged. All runtime files live inside the installable Skill.

`visual.py prepare PLAN --output NEW_WORKSPACE` validates an existing verified
edit result, resolves source/output frame anchors through its timeline, validates
two local photos per effect, and stages immutable inputs and composition props.
Source anchors must fit one retained segment; deleted/cross-cut intervals fail.
Overlapping photo effects fail. Frame rate/duration/dimensions come from the master.

`visual.py render WORKSPACE --output NEW_RESULT` renders video through the pinned
Remotion project, then copies the master AAC track via FFmpeg. Optional half-open
start/end frame bounds produce a partial preview with accurately trimmed/reencoded
audio, explicitly labeled as such. No audio remains no audio. Always verify output
parameters, frame count and full decode; full output checks compressed audio hash.
Save the rendering engine, commands, input fingerprints, frame range and technical
report. Publish output.mp4 only after passing; content/listening review stays pending.

The template shows both photos, enlarges first, transitions to second, then returns
to master. Preserve full photo aspect ratio. Props control start/duration, layer,
overview/focus size and transition frames. Animation is frame-driven, deterministic.
Studio uses the same staged props and assets; render key stills for visual review.

No submodule, vendored upstream skills, automatic skill installation, captions,
music, or local user media in Git. Explain skill discovery separately from Node,
npm dependencies and browser readiness. Keep CI to existing two jobs; only relevant
changes enable a short rendering smoke test, with lightweight validation tests.
