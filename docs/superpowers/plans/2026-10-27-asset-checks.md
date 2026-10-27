# Asset manifest checks implementation plan

**Goal:** Implement issue #3 as a read-only, portable asset inventory and diagnostic command.

**Architecture:** Versioned asset packages contain a `files` list. Each file owns its source, storage and rights declaration. A standard-library validator and checker are independent of edit/visual pipelines. JSON reports preserve separate existence, fingerprint, probe, sample-decode, dependency and rights states. No network, installation or asset modification.

**Tech Stack:** Python 3.10+, optional FFprobe/FFmpeg, existing unittest and two-platform CI.

## Approved design and boundaries

- Keep existing media paths and all source, hash and usage records. Register video and beep separately within the color-bars package. Local outro absence is a warning.
- Relative paths resolve from the manifest directory; reject absolute, parent traversal and escaped symlinks. Reject duplicate IDs/keys and malformed structures without stopping checks of other packages.
- Probe media when FFprobe is available. `--decode` samples at most one second through FFmpeg, never claims full-file integrity, browser playback or final-render compatibility. Templates can be registered but not media-probed.
- Rights are declarations, not legal determinations. Unknown redistribution stays unknown, separate from technical checks. Missing executables mean limited checks, not damaged files.
- JSON stdout is versioned; text is the default. Exit 1 for invalid manifests, missing bundled assets, fingerprint/media failures; warnings alone exit 0. Invalid CLI arguments exit 2.

## Tasks

- [x] Add `tests/test_assets.py`: CLI cases for bundled/local missing files, checksum mismatch, missing FFprobe, malformed/path-escaping manifests, dependency and rights separation, portable default root, real probe/decode and read-only behavior. Run `python -m unittest discover -s tests -p test_assets.py -v` and confirm missing command fails.
- [x] Implement `scripts/asset_inventory.py` validation/report functions and `scripts/check_assets.py` CLI. Run the targeted tests to green. Keep executable requirements allowlisted; manifest data never becomes a command.
- [x] Migrate both `assets/*/manifest.json` files to version 1 and preserve every original fact. Verify tracked video/audio hashes and run the checker from a different working directory.
- [x] Add `references/asset-manifests.md` as the equivalent validation specification and status/exit-code contract; update README, SKILL and both resource recipes with installation and diagnostic instructions.
- [x] Run full unittest discovery (existing heavy Remotion cases remain opt-in), `git diff --check`, and review for independent states and unchanged media. Delivery: commit, push and create PR closing #3; confirm existing Windows/Ubuntu CI without workflow expansion.

## Validation

12 asset contract tests pass, including real media probing/sample decoding, non-UTF8 host output, malformed probe replies and extreme numeric metadata. Independent review findings resolved and rechecked. Full discovery: 54 tests, 52 passed and 2 optional Remotion rendering cases skipped because no rendering implementation changed. CI delivery status is recorded in the PR.
