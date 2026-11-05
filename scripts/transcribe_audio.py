#!/usr/bin/env python3
"""Transcribe local audio with timestamped, resumable evidence; no cloud upload."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path


def stamp(seconds, srt=False):
    ms = round(seconds*1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}'+((',' if srt else '.')+f'{ms:03}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('audio', type=Path)
    p.add_argument('--model', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--language')
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    from faster_whisper import WhisperModel
    # PyAV 19 removed av.open(metadata_errors=...), still passed by the
    # current faster-whisper decoder. Decode explicitly without that argument.
    import av
    import numpy as np
    resampler = av.AudioResampler(format='flt', layout='mono', rate=16000)
    chunks = []
    with av.open(str(args.audio), mode='r') as container:
        for frame in container.decode(audio=0):
            chunks.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(frame))
        chunks.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(None))
    audio = np.concatenate(chunks).astype(np.float32)
    model = WhisperModel(args.model, device='cpu', compute_type='int8', cpu_threads=8)
    segments, info = model.transcribe(audio, beam_size=5, language=args.language,
        vad_filter=True, condition_on_previous_text=True)
    metadata = dict(source=str(args.audio.resolve()),
        sha256=hashlib.sha256(args.audio.read_bytes()).hexdigest(),
        model=args.model, engine='faster-whisper '+version('faster-whisper'),
        language=info.language, language_probability=info.language_probability,
        duration_seconds=info.duration, created_utc=datetime.now(timezone.utc).isoformat(),
        status='in_progress', machine_transcript=True)
    (out/'metadata.json').write_text(json.dumps(metadata, indent=2))
    print(f'Language={info.language}; duration={info.duration:.1f}s', flush=True)
    count = 0
    with (out/'segments.jsonl').open('w') as jf,(out/'transcript.txt').open('w') as tf,(out/'transcript.srt').open('w') as sf:
        for segment in segments:
            count += 1
            jf.write(json.dumps(asdict(segment), ensure_ascii=False)+'\n');jf.flush()
            tf.write(f'[{stamp(segment.start)}–{stamp(segment.end)}] {segment.text.strip()}\n');tf.flush()
            sf.write(f'{count}\n{stamp(segment.start, True)} --> {stamp(segment.end, True)}\n{segment.text.strip()}\n\n');sf.flush()
            if count % 25 == 0:
                print(f'{stamp(segment.end)} / {stamp(info.duration)}; {count} segments', flush=True)
    metadata.update(status='complete', segments=count)
    (out/'metadata.json').write_text(json.dumps(metadata, indent=2))
    print('Transcript saved: '+str(out/'transcript.txt'), flush=True)


if __name__ == '__main__':
    main()
