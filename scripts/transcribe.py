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
    started = time.monotonic()
    local_small = Path(__file__).parent / "models" / "small-local"
    model_source = str(local_small) if args.model == "small" and (local_small / "model.bin").is_file() else args.model
    model = WhisperModel(model_source, device=args.device,
                         compute_type="float16" if args.device == "cuda" else "int8",
                         download_root=str(Path(__file__).parent / "models"))
    segments, info = model.transcribe(str(args.input), language=args.language,
                                     beam_size=5, vad_filter=True,
                                     word_timestamps=True,
                                     initial_prompt="以下是普通话视频的简体中文转写。")
    records = []
    for seg in segments:
        records.append(asdict(seg))
        print(f"[{seg.start:.2f} - {seg.end:.2f}] {seg.text}", flush=True)
    if not records:
        raise RuntimeError("No speech detected; no transcript created")
    args.output.mkdir(parents=True)
    (args.output / "transcript.txt").write_text("\n".join(s["text"].strip() for s in records) + "\n", encoding="utf-8")
    srt = "\n\n".join(f'{i}\n{stamp(s["start"])} --> {stamp(s["end"])}\n{s["text"].strip()}' for i, s in enumerate(records, 1))
    (args.output / "subtitles.srt").write_text(srt + "\n", encoding="utf-8-sig")
    payload = {"input": str(args.input.resolve()), "model": args.model, "device": args.device,
               "language": info.language, "duration": info.duration,
               "elapsed_seconds": round(time.monotonic() - started, 2),
               "review_status": "automatic_unreviewed", "segments": records}
    (args.output / "transcript.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(records)} segments to {args.output}", flush=True)


if __name__ == "__main__":
    main()
