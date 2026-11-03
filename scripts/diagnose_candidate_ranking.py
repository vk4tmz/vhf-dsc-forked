#!/usr/bin/env python3
"""Diagnose candidate ranking and dot-sync gate for DSC time-base changes.

Offline diagnostic only. Recreates identical WAV perturbations for stable and
experimental decoder. Reports pre-screen, dot-sync candidate ranks and whether
valid frames exist among all candidates versus the production top-eight cap.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[1]
EXPECT = ("all_ships_call", "002320014")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def valid_call(call: dict) -> bool:
    return (call.get("message", {}).get("kind") == EXPECT[0]
            and call.get("self_id") == EXPECT[1])


def diagnostic(mod, path: Path, recovery: bool):
    samples, sample_rate = mod.read_audio(path)
    detection = mod.detect_dsc_signal(samples, sample_rate)
    if not detection.get("has_dsc_signal"):
        return {"detected": False, "ranks": [], "candidates": 0}
    candidates = mod.demodulate_candidates(
        samples, sample_rate, enable_dot_sync=True,
        enable_clock_recovery=recovery,
    )
    ranks = []
    for rank, cand in enumerate(candidates, 1):
        calls = mod.parse_bits(cand.bits)
        if any(valid_call(call) for call in calls):
            ranks.append(rank)
    return {
        "detected": True,
        "candidates": len(candidates),
        "ranks": ranks,
        "top": [
            (round(c.confidence, 4), round(c.dot_sync_confidence, 4),
             c.freq_offset_hz, round(c.offset, 2))
            for c in candidates[:min(9, len(candidates))]
        ],
    }


def main():
    rate, raw = wavfile.read(ROOT / "samples/all_ships_call.wav")
    if raw.ndim != 1:
        raw = raw.mean(axis=1)
    raw = raw.astype(np.float32)
    raw /= max(1.0, float(np.max(np.abs(raw))))
    rng = np.random.default_rng(20261103)
    with tempfile.TemporaryDirectory(prefix="dsc-rank-") as td:
        td = Path(td)
        stable_path = td / "stable.py"
        stable_path.write_bytes(subprocess.check_output(
            ["git", "show", "9a8a770:dsc_decode.py"], cwd=ROOT))
        stable = load(stable_path, "dsc_rank_stable")
        revised = load(ROOT / "dsc_decode.py", "dsc_rank_revised")
        for drift in (-0.25, 0.0, 0.25):
            if drift:
                changed = resample_poly(raw, 400 + int(drift * 4), 400)
            else:
                changed = raw
            for noise in (0.0, 0.04):
                samples = changed.copy()
                if noise:
                    samples += rng.normal(0, noise, size=len(samples)).astype(np.float32)
                wav = td / "test.wav"
                wavfile.write(wav, rate, (np.clip(samples, -1, 1) * 32767).astype(np.int16))
                print(f"CASE drift={drift:+.2f}% noise={noise:.2f}", flush=True)
                for label, mod, enabled in (
                    ("stable", stable, False),
                    ("revised_off", revised, False),
                    ("revised_on", revised, True),
                ):
                    d = diagnostic(mod, wav, enabled)
                    print(f"  {label}: detected={d['detected']} candidates={d['candidates']} "
                          f"valid_ranks={d['ranks']} top={d.get('top', [])}", flush=True)


if __name__ == "__main__":
    main()
