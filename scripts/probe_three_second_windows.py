#!/usr/bin/env python3
"""Validate clock recovery in approximately 3-second KA9Q-style PCM windows.

Offline synthetic window construction from the five bundled off-air calls.
The leading and trailing noise is generated deterministically. The original
off-air file remains intact and unmodified.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[1]
CALLS = [
    ("individual_call.wav", "individual_call", "002275200"),
    ("individual_call_2.wav", "individual_call", "002275100"),
    ("all_ships_call.wav", "all_ships_call", "002320014"),
    ("distress_relay.wav", "distress_relay", "002275300"),
    ("distress_acknowledgement.wav", "distress_acknowledgement", "002275200"),
]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def matches(result, kind, mmsi):
    return any(
        c.get("message", {}).get("kind") == kind and c.get("self_id") == mmsi
        for c in result.get("calls", [])
    )


def decode_with_recovery(mod, path, enabled):
    func = mod.demodulate_candidates
    if not enabled:
        def disabled(*args, **kwargs):
            kwargs["enable_clock_recovery"] = False
            return func(*args, **kwargs)
        mod.demodulate_candidates = disabled
    try:
        before = time.perf_counter()
        result = mod.decode_file(path)
        return result, time.perf_counter() - before
    finally:
        mod.demodulate_candidates = func


def main():
    with tempfile.TemporaryDirectory(prefix="dsc-three-second-") as td:
        td = Path(td)
        baseline_file = td / "baseline.py"
        baseline_file.write_bytes(subprocess.check_output(
            ["git", "show", "9a8a770:dsc_decode.py"], cwd=ROOT))
        stable = load(baseline_file, "dsc_three_second_stable")
        revised = load(ROOT / "dsc_decode.py", "dsc_three_second_revised")
        tally = {"stable": 0, "clock_off": 0, "clock_on": 0}
        max_times = {"stable": 0.0, "clock_off": 0.0, "clock_on": 0.0}
        n = 0
        for name, kind, mmsi in CALLS:
            sample_rate, raw = wavfile.read(ROOT / "samples" / name)
            if raw.ndim != 1:
                raw = raw.mean(axis=1)
            raw = raw.astype(np.float32)
            raw /= max(1.0, float(np.max(np.abs(raw))))
            for drift in (-0.25, 0.0, 0.25):
                shifted = raw if drift == 0 else resample_poly(
                    raw, 400 + int(drift * 4), 400)
                # Keep the complete transmission. Extend to 3 seconds when
                # possible; report if it is inherently longer.
                lead = int(sample_rate * 0.10)
                total = max(sample_rate * 3, lead + len(shifted) + int(sample_rate * .05))
                rng = np.random.default_rng(2026)
                window = rng.normal(0, 0.025, size=total).astype(np.float32)
                window[lead:lead + len(shifted)] += shifted
                wav = td / "window.wav"
                wavfile.write(wav, sample_rate,
                              (np.clip(window, -1, 1) * 32767).astype(np.int16))
                outcome = []
                for label, mod, recovery in (
                    ("stable", stable, False),
                    ("clock_off", revised, False),
                    ("clock_on", revised, True),
                ):
                    result, duration = decode_with_recovery(mod, wav, recovery)
                    ok = matches(result, kind, mmsi)
                    tally[label] += int(ok)
                    max_times[label] = max(max_times[label], duration)
                    outcome.append(f"{label}={'PASS' if ok else 'MISS'}({duration:.3f}s)")
                n += 1
                print(f"{name} drift={drift:+.2f}% audio={total/sample_rate:.2f}s "
                      + " ".join(outcome), flush=True)
        print(f"SUMMARY: {n} windows success={tally} max_wall_s={max_times}", flush=True)
        # Unlike diagnostic-only matrices, this is a deterministic
        # regression gate for the experimental clock-recovery branch.
        if tally["clock_on"] != n:
            raise AssertionError(
                f"clock recovery lost {n - tally['clock_on']} of {n} known calls"
            )

        # Pure noise must never produce a validated DSC call. Use varied
        # seeded noise amplitudes, all as 3-second 16-bit PCM WAVs.
        for amp in (0.025, 0.05, 0.10):
            rng = np.random.default_rng(931)
            noise = rng.normal(0, amp, size=3 * 48000).astype(np.float32)
            wav = td / "noise_only.wav"
            wavfile.write(wav, 48000,
                          (np.clip(noise, -1, 1) * 32767).astype(np.int16))
            result, elapsed = decode_with_recovery(revised, wav, True)
            print(f"noise_only amplitude={amp:.3f} "
                  f"validated_calls={len(result.get('calls', []))} "
                  f"wall_s={elapsed:.3f}", flush=True)
            if result.get("calls"):
                raise AssertionError("noise-only window produced DSC calls")


if __name__ == "__main__":
    main()
