#!/usr/bin/env python3
"""Probe whether activated clock recovery improves *known* synthetic FSK bits.

Offline research diagnostic, not an ITU-R DSC protocol acceptance test.
Compare baseline and transition-fix at mismatched symbol rates and sample phases.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RATE = 48000
BAUD = 1200
COUNT = 300


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def make_signal(bits, drift_pct, phase_samples, noise_amp=0.0):
    rng = np.random.default_rng(2026)
    samples_per_bit = (RATE / BAUD) * (1 + drift_pct / 100)
    n = int((len(bits) + 2) * samples_per_bit + abs(phase_samples) + 48)
    x = np.arange(n)
    symbol_idx = np.floor((x - phase_samples) / samples_per_bit).astype(int)
    symbol_idx = np.clip(symbol_idx, 0, len(bits) - 1)
    freqs = np.where(bits[symbol_idx], 1300., 2100.)
    phase = np.cumsum(2 * np.pi * freqs / RATE)
    y = np.sin(phase).astype(np.float32)
    if noise_amp:
        y += rng.normal(0, noise_amp, size=n).astype(np.float32)
    return y


def errors(decoded, expected):
    # Report raw bit-error count at the configured sample alignment.
    n = min(len(decoded), len(expected))
    return sum(int(decoded[i] != int(expected[i])) for i in range(n)), n


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bits", type=int, default=COUNT)
    args = p.parse_args()
    rng = np.random.default_rng(417)
    bits = rng.integers(0, 2, args.bits, dtype=np.int8)
    with tempfile.TemporaryDirectory(prefix="dsc-fsk-check-") as td:
        path = Path(td) / "baseline.py"
        path.write_bytes(subprocess.check_output(
            ["git", "show", "9a8a770:dsc_decode.py"], cwd=ROOT))
        versions = [
            ("baseline", load(path, "clock_baseline")),
            ("transition_fix", load(ROOT / "dsc_decode.py", "clock_experiment")),
        ]
        print(f"Synthetic continuous-phase AFSK; {args.bits} known bits; errors/decoded bits")
        for drift in (-1.0, -0.25, 0.0, 0.25, 1.0):
            for phase in (0, 7):
                y = make_signal(bits, drift, phase, noise_amp=0.08)
                results = {}
                for name, mod in versions:
                    for enabled in (False, True):
                        decoded, confidence = mod._demodulate_with_clock_recovery(
                            y, RATE, RATE / BAUD, float(phase), enable_clock_recovery=enabled,
                        )
                        results[f"{name}:{'on' if enabled else 'off'}"] = errors(decoded, bits)
                print(f"drift={drift:+.2f}% phase={phase}: {results}", flush=True)


if __name__ == "__main__":
    main()
