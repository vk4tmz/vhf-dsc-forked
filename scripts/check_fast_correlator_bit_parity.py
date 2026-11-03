#!/usr/bin/env python3
"""Compare *every* candidate bitstream with the longburst implementation.

The fast-correlator experiment changes NumPy's floating-point reduction order,
so report both bit-level parity and confidence changes independently of
full-message regression tests.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "noise.wav", "individual_call.wav", "individual_call_2.wav",
    "all_ships_call.wav", "distress_relay.wav",
    "distress_acknowledgement.wav",
)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def key(c):
    return (float(c.freq_offset_hz), float(c.offset))


def main():
    with tempfile.TemporaryDirectory(prefix="dsc-bit-parity-") as td:
        baseline_file = Path(td) / "longburst.py"
        baseline_file.write_bytes(subprocess.check_output(
            ["git", "show", "0666988:dsc_decode.py"], cwd=ROOT))
        old = load(baseline_file, "dsc_precomputed_baseline")
        new = load(ROOT / "dsc_decode.py", "dsc_precomputed_fast")
        mismatches = 0
        for name in NAMES:
            path = ROOT / "samples" / name
            samples, rate = old.read_audio(path)
            previous = sorted(old.demodulate_candidates(
                samples, rate, enable_clock_recovery=True), key=key)
            current = sorted(new.demodulate_candidates(
                samples, rate, enable_clock_recovery=True), key=key)
            identities_equal = [key(x) for x in previous] == [key(x) for x in current]
            bad = []
            max_conf_delta = 0.0
            if identities_equal:
                for i, (a, b) in enumerate(zip(previous, current)):
                    differing = sum(x != y for x, y in zip(a.bits, b.bits))
                    differing += abs(len(a.bits) - len(b.bits))
                    if differing:
                        bad.append((i, differing))
                    max_conf_delta = max(max_conf_delta, abs(a.confidence - b.confidence))
            print(f"{name}: candidates={len(previous)}/{len(current)} "
                  f"same_hypotheses={identities_equal} bit_differences={bad} "
                  f"max_confidence_delta={max_conf_delta:.7g}", flush=True)
            if not identities_equal or bad:
                mismatches += 1
        print(f"Candidate-level bitstream parity: {len(NAMES)-mismatches}/{len(NAMES)} files", flush=True)
        if mismatches:
            raise AssertionError("fast correlator altered candidate bits or hypotheses")


if __name__ == "__main__":
    main()
