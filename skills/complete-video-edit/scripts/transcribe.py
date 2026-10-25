"""Local transcription: TXT, SRT and JSON with word timestamps."""
import argparse
import json
import os
import time
from pathlib import Path
from dataclasses import asdict


def stamp(seconds):
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("--output", type=Path, required=True, help="New output directory")
    p.add_argument("--model", default="small")
    p.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    p.add_argument("--language", default="zh")
    p.add_argument("--gpu-libs", type=Path, default=None)
    p.add_argument("--no-vad", action="store_true", help="Retry suspected quiet speech without VAD; review results carefully")
    args = p.parse_args()
    if not args.input.is_file():
        p.error("Input file does not exist")
    if args.output.exists():
        p.error("Output directory exists; choose a new directory to preserve previous results")
    dll_handle = None
    if args.device == "cuda" and args.gpu_libs and args.gpu_libs.is_dir():
        os.environ["PATH"] = str(args.gpu_libs) + os.pathsep + os.environ.get("PATH", "")
        dll_handle = os.add_dll_directory(str(args.gpu_libs))
    # Standard HTTPS works more reliably on this host than the Xet downloader.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    started = time.monotonic()
    def save_status(status, **extra):
        args.output.mkdir(parents=True, exist_ok=True)
        payload = {"input": str(args.input.resolve()), "model": args.model,
                   "device": args.device, "status": status,
                   "review_status": "automatic_unreviewed", "vad_enabled": not args.no_vad,
                   "elapsed_seconds": round(time.monotonic() - started, 2), **extra}
        (args.output / "transcript.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        audio = decode_audio(str(args.input), sampling_rate=16000)
    except Exception as exc:
        save_status("decode_failed", error=str(exc), segments=[])
        raise SystemExit(f"Audio decoding failed: {exc}") from exc
    local_small = Path(__file__).parent / "models" / "small-local"
    model_source = str(local_small) if args.model == "small" and (local_small / "model.bin").is_file() else args.model
    model = WhisperModel(model_source, device=args.device,
                         compute_type="float16" if args.device == "cuda" else "int8",
                         download_root=str(Path(__file__).parent / "models"))
    segments, info = model.transcribe(audio, language=args.language,
                                     beam_size=5, vad_filter=not args.no_vad,
                                     word_timestamps=True,
                                     initial_prompt="以下是普通话视频的简体中文转写。")
    records = []
    for seg in segments:
        records.append(asdict(seg))
        print(f"[{seg.start:.2f} - {seg.end:.2f}] {seg.text}", flush=True)
    if not records:
        save_status("no_speech_detected", language=info.language, duration=info.duration,
                    segments=[], next_action="Review visuals and on-site sound; if quiet speech is suspected, retry with --no-vad into a new output directory. Do not discard footage based on this result.")
        print(f"No speech detected; continue visual/audio review. Status saved to {args.output}")
        return
    save_status("transcribed", language=info.language, duration=info.duration, segments=records,
                artifacts={"text": "transcript.draft.txt", "subtitles": "subtitles.draft.srt"})
    (args.output / "transcript.draft.txt").write_text("【自动转写初稿 · 待校对，不代表已核实原话】\n\n" + "\n".join(s["text"].strip() for s in records) + "\n", encoding="utf-8")
    srt = "\n\n".join(f'{i}\n{stamp(s["start"])} --> {stamp(s["end"])}\n{s["text"].strip()}' for i, s in enumerate(records, 1))
    (args.output / "subtitles.draft.srt").write_text(srt + "\n", encoding="utf-8-sig")
    print(f"Saved {len(records)} segments to {args.output}", flush=True)


if __name__ == "__main__":
    main()
