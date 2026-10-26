# Auditable single-source editing

Approved direction: issue #1 with a deletion-only plan and a single CLI. All
unspecified content is retained in source order. No ASR/VAD deletion decisions.

`edit.py check PLAN`, `render PLAN --output NEW_DIRECTORY`, and `verify RESULT`
share standard-library Python modules inside the installable Skill. No dependency
on the repository, Whisper, GPU, or plugins.

Plan v1: schema_version=1, source (relative to plan), cuts with unique ids, numeric
second boundaries and nonblank reasons. Optional source_sha256 pins identity and
audio_stream selects an absolute stream index when multiple audio tracks exist.
Unknown fields/effects, malformed numbers, overlaps, unsorted cuts and deleting
everything fail explicitly. Cuts are half-open. Check reports the source hash.

Normalize video to its probed nominal frame rate; quantize boundaries upwards to
frame indices. Record requested decisions separately from effective frame-aligned
timeline. Audio uses the same source video start time and effective boundaries,
padding initial gaps with silence. Absent audio stays absent. Explicitly reject
HDR, non-square pixels, rotated video and multichannel audio in v1. Restrictions
apply only to this new tool. Fixed H.264/AAC profile; no resizing or decoration.

Render validates again, exclusively creates a result directory, saves plan,
timeline, source hash, versions and argument arrays, then encodes a partial MP4.
Verify before publishing output.mp4. Failure records remain readable. Standalone
verification binds media to the saved output hash and checks stream properties,
frame count, duration and complete decoding. Listening/content review stays pending.

Test with generated color/tone media, including actual retained content and audio
alignment. Skip FFmpeg integration tests only when binaries are absent. Ubuntu
and Windows CI. Existing transcribe/download behavior and dependency lock remain
unchanged. Updating an installed Skill is a separate user operation.
