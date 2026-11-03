#!/usr/bin/env python3
"""Offline full-decoder DSC fixture sensitivity under audio time-base perturbations.

Resampling a WAV changes both its symbol clock and audio tones; this is NOT
equivalent to isolated transmitter symbol-clock drift. Use alongside the known
bit synthetic test, not as a replacement.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = {
    "individual_call.wav": ("individual_call", "002275200"),
    "all_ships_call.wav": ("all_ships_call", "002320014"),
    "individual_call_2.wav": ("individual_call", "002275100"),
    "distress_relay.wav": ("distress_relay", "002275300"),
    "distress_acknowledgement.wav": ("distress_acknowledgement", "002275200"),
}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def matches(result, kind, self_id):
    return any(
        call.get("message", {}).get("kind") == kind
        and call.get("self_id") == self_id
        for call in result.get("calls", [])
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--all", action="store_true", help="test all five DSC fixtures")
    args = p.parse_args()
    fixtures = FIXTURES if args.all else {
        k: FIXTURES[k] for k in ("individual_call.wav", "all_ships_call.wav")
    }
    rng = np.random.default_rng(5271)
    with tempfile.TemporaryDirectory(prefix="dsc-timebase-") as td:
        td = Path(td)
        orig = td / "original.py"
        orig.write_bytes(subprocess.check_output(
            ["git", "show", "9a8a770:dsc_decode.py"], cwd=ROOT))
        decoders = [
            ("baseline", load(orig, "dsc_original_timebase")),
            ("revised", load(ROOT / "dsc_decode.py", "dsc_revised_timebase")),
        ]
        totals = {label: 0 for label, _ in decoders}
        trials = 0
        for name, (kind, self_id) in fixtures.items():
            sample_rate, raw = wavfile.read(ROOT / "samples" / name)
            if raw.ndim != 1:
                raw = raw.mean(axis=1)
            raw = raw.astype(np.float32)
            raw /= max(1.0, float(np.max(np.abs(raw))))
            for drift in (-0.25, 0.0, 0.25):
                # Rational factor approximates 1 +/- 0.0025, retains 48k WAV rate.
                if drift == 0:
                    changed = raw
                else:
                    changed = resample_poly(raw, 400 + int(drift * 4), 400)
                for noise in (0.0, 0.04):
                    signal = changed.copy()
                    if noise:
                        signal += rng.normal(0, noise, size=len(signal)).astype(np.float32)
                    testpath = td / "timebase.wav"
                    wavfile.write(testpath, sample_rate, signal)
                    outcomes = []
                    for label, decoder in decoders:
                        result = decoder.decode_file(testpath)
                        passed = matches(result, kind, self_id)
                        totals[label] += int(passed)
                        outcomes.append(f"{label}={'PASS' if passed else 'MISS'}")
                    trials += 1
                    print(f"{name} rate_scale={drift:+.2f}% noise={noise:.2f}: "
                          + " ".join(outcomes), flush=True)
        print(f"SUMMARY: {trials} conditions, recovered valid calls {totals}", flush=True)
        # Diagnostic: deliberately do not fail on differences; signal robustness
        # has to be measured, not assumed. The standard fixtures gate CI.


if __name__ == "__main__":
    main()
