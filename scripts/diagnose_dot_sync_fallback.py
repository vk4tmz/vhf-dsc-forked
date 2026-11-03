#!/usr/bin/env python3
"""Offline acquisition diagnostic for shifted real DSC recordings.

Checks whether dot-pattern synchronisation suppresses a valid brute-force
timing hypothesis. Limited to three AFC offsets to cap runtime.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[1]


def load():
    path = ROOT / "dsc_decode.py"
    spec = importlib.util.spec_from_file_location("dsc_acquisition", path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = obj
    spec.loader.exec_module(obj)
    return obj


def main():
    mod = load()
    sample = ROOT / "samples/individual_call.wav"
    rate, signal = wavfile.read(sample)
    signal = signal.astype(np.float32)
    signal /= max(1.0, float(np.max(np.abs(signal))))
    with tempfile.TemporaryDirectory(prefix="dsc-acquire-") as temp:
        for drift in (-0.25, 0.25):
            moved = resample_poly(signal, 400 + int(drift * 4), 400)
            wav = Path(temp) / "shifted.wav"
            wavfile.write(wav, rate, (np.clip(moved, -1, 1) * 32767).astype(np.int16))
            samples, sample_rate = mod.read_audio(wav)
            detection = mod.detect_dsc_signal(samples, sample_rate)
            print(f"drift={drift:+.2f}% pre-screen={detection.get('has_dsc_signal')}", flush=True)
            for recovery in (False, True):
                for dot in (True, False):
                    candidates = mod.demodulate_candidates(
                        samples, sample_rate,
                        freq_offsets_hz=[-25, 0, 25],
                        offsets=16, enable_dot_sync=dot,
                        enable_clock_recovery=recovery,
                    )
                    valid = []
                    for rank, candidate in enumerate(candidates, 1):
                        calls = mod.parse_bits(candidate.bits)
                        if any(c.get("self_id") == "002275200" and
                               c.get("message", {}).get("kind") == "individual_call"
                               for c in calls):
                            valid.append(rank)
                    print(f"  recovery={recovery} dot={dot}: "
                          f"candidates={len(candidates)} valid_ranks={valid}", flush=True)


if __name__ == "__main__":
    main()
