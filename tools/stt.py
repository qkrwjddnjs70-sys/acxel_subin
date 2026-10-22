"""방송 영상/음성 → 한국어 자막 텍스트(PC 안에서만 처리, 외부 전송 없음).

출력은 `python -m hsbot paste` 가 바로 읽는 형식("MM:SS - MM:SS 문장")이라
자막 → 7개 소구축 화법 분석으로 그대로 이어진다.

설치: 프로젝트 폴더의 별도 가상환경(.venv-stt)에 faster-whisper 를 깔아 두었다.
사용:
    .venv-stt\\Scripts\\python tools\\stt.py 방송.mp4                    # 기본 모델(large-v3-turbo)
    .venv-stt\\Scripts\\python tools\\stt.py 방송.mp4 --model small      # 빠르지만 덜 정확
    .venv-stt\\Scripts\\python tools\\stt.py 방송.mp4 --start 0 --minutes 5   # 앞 5분만 시험

모델은 처음 쓸 때 한 번 내려받는다(small ≈ 0.5GB, large-v3-turbo ≈ 1.6GB).
GPU가 없으면 CPU로 돌고, 1시간 방송에 수십 분 걸릴 수 있다 — 먼저 --minutes 로 짧게 시험할 것.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time

# 홈쇼핑 어휘를 미리 알려 주면 고유명사·숫자 인식이 나아진다(Whisper initial_prompt).
HOMESHOPPING_PROMPT = (
    "홈쇼핑 생방송입니다. 지금 바로 주문하세요. 무이자 할부, 일시불 할인, 카드 청구할인, "
    "사은품, 추가 구성, 방송 중에만 드리는 혜택, 상담 예약, 매진 임박, 정상가, 할인가, "
    "ARS 주문, 모바일 주문, 쇼호스트."
)


def fmt(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def extract_audio(src: str, start: float, minutes: float | None) -> str:
    """ffmpeg로 16kHz 모노 wav를 뽑는다(영상이든 음성이든 동일하게 처리)."""
    out = os.path.join(tempfile.gettempdir(), "hsbot_stt_input.wav")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-i", src]
    if minutes:
        cmd += ["-t", str(minutes * 60)]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", out]
    subprocess.run(cmd, check=True)
    return out


def load_wav(path: str):
    """ffmpeg가 만든 16kHz 모노 16bit wav → float32 배열.
    faster-whisper 의 내장 디코더(PyAV)는 버전 궁합 문제가 있어 쓰지 않는다."""
    import wave

    import numpy as np

    with wave.open(path, "rb") as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def main() -> int:
    ap = argparse.ArgumentParser(description="방송 영상/음성 → 한국어 자막(paste 형식)")
    ap.add_argument("src", help="영상 또는 음성 파일(mp4, mkv, mp3, wav …)")
    ap.add_argument("--model", default="large-v3-turbo",
                    help="tiny/base/small/medium/large-v3/large-v3-turbo (기본 large-v3-turbo)")
    ap.add_argument("--start", type=float, default=0, help="시작 지점(초)")
    ap.add_argument("--minutes", type=float, default=None, help="앞에서부터 몇 분만 (시험용)")
    ap.add_argument("--out", default=None, help="출력 .txt (기본: 원본 옆에 _자막.txt)")
    args = ap.parse_args()

    from faster_whisper import WhisperModel

    if not os.path.exists(args.src):
        print(f"파일이 없습니다: {args.src}", file=sys.stderr)
        return 2
    out = args.out or os.path.splitext(args.src)[0] + "_자막.txt"

    t0 = time.time()
    wav = extract_audio(args.src, args.start, args.minutes)
    print(f"[1/2] 음성 추출 완료 ({time.time() - t0:.0f}초)", flush=True)

    model = WhisperModel(args.model, device="cpu", compute_type="int8",
                         cpu_threads=max(1, (os.cpu_count() or 4) - 2))
    segments, info = model.transcribe(
        load_wav(wav), language="ko", vad_filter=True, beam_size=5,
        initial_prompt=HOMESHOPPING_PROMPT, condition_on_previous_text=False,
    )
    total = info.duration or 1
    lines = []
    last_report = 0.0
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        lines.append(f"{fmt(args.start + seg.start)} - {fmt(args.start + seg.end)} {text}")
        if seg.end - last_report >= 60:  # 방송 1분 분량마다 진행 상황
            last_report = seg.end
            print(f"      … {fmt(seg.end)} / {fmt(total)}  ({time.time() - t0:.0f}초 경과)", flush=True)

    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    took = time.time() - t0
    print(f"[2/2] 완료: {len(lines)}줄 / 방송 {fmt(total)} 분량 / {took:.0f}초 걸림 "
          f"(실시간 대비 {total / took:.1f}배속)")
    print(f"저장: {out}")
    print(f"→ 분석: python -m hsbot paste --file \"{out}\" --channel gsshop --product 상품명 "
          f"--start 2026-10-19T20:40:00+09:00 --out data/x.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
