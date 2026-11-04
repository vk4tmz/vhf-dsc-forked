#!/usr/bin/env python3
"""Independent offline ablations for VHF DSC tone weighting and clock loop gains.

Does not use RF, multicast, or the live KA9Q listener. Every scenario restores
experimental defaults before moving to the next. Fails if baseline regresses.
"""
from __future__ import annotations
import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import dsc_decode as d

CALLS = [
    ("individual_call.wav", "individual_call", "002275200"),
    ("individual_call_2.wav", "individual_call", "002275100"),
    ("all_ships_call.wav", "all_ships_call", "002320014"),
    ("distress_relay.wav", "distress_relay", "002275300"),
    ("distress_acknowledgement.wav", "distress_acknowledgement", "002275200"),
]
SCENARIOS = {
    "baseline": (0.0, 0.1, 0.1),
    "tone_freq_normalised": (2.0, 0.1, 0.1),
    "clock_fast_early_slow_late": (0.0, 0.2, 0.05),
    "tone_and_clock": (2.0, 0.2, 0.05),
}


def matches(calls, kind, mmsi):
    return any(c.get("message", {}).get("kind") == kind and
               c.get("self_id") == mmsi for c in calls)


def run_case(wav, scenario):
    tone, early, late = SCENARIOS[scenario]
    d.EXPERIMENT_TONE_WEIGHT_POWER = tone
    d.EXPERIMENT_CLOCK_GAIN_EARLY = early
    d.EXPERIMENT_CLOCK_GAIN_LATE = late
    d.EXPERIMENT_CLOCK_SWITCH_BITS = 200
    return d.decode_file(wav)


def fixture_cases(name, *, extended):
    rate, raw = wavfile.read(ROOT / "samples" / name)
    if raw.ndim > 1:
        raw = raw.mean(axis=1)
    signal = raw.astype(np.float32)
    signal /= max(1.0, float(np.max(np.abs(signal))))
    variants = [(0.0, 0.0)]
    if extended:
        variants += [(-0.25, .04), (0.25, .04)]
    for drift, noise in variants:
        shifted = signal if drift == 0 else resample_poly(
            signal, 400 + int(drift * 4), 400
        )
        if noise:
            shifted = shifted + np.random.default_rng(20261104).normal(
                0, noise, len(shifted)
            ).astype(np.float32)
        yield rate, np.clip(shifted, -1, 1), drift, noise


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--extended", action="store_true", help="include +/-0.25%% drift with noise")
    args = ap.parse_args()
    tally = {s: {"recovered": 0, "total": 0, "false_calls": 0} for s in SCENARIOS}
    with tempfile.TemporaryDirectory(prefix="dsc-tone-clock-") as folder:
        path = Path(folder) / "case.wav"
        for name, kind, mmsi in CALLS:
            for rate, samples, drift, noise in fixture_cases(name, extended=args.extended):
                wavfile.write(path, rate, (samples * 32767).astype("<i2"))
                outcomes = {}
                for scenario in SCENARIOS:
                    result = run_case(path, scenario)
                    good = matches(result.get("calls", []), kind, mmsi)
                    tally[scenario]["total"] += 1
                    tally[scenario]["recovered"] += int(good)
                    outcomes[scenario] = {
                        "recovered": good,
                        "validated_calls": len(result.get("calls", [])),
                    }
                print(json.dumps({"file": name, "drift": drift, "noise": noise,
                                  "outcomes": outcomes}), flush=True)
        # Add synthetic noise-only trials; quantify invalid false matches.
        for amp in (0.025, 0.05, 0.10):
            rng = np.random.default_rng(931)
            samples = rng.normal(0, amp, size=3*48000).astype(np.float32)
            wavfile.write(path, 48000, (np.clip(samples, -1, 1)*32767).astype("<i2"))
            for scenario in SCENARIOS:
                result = run_case(path, scenario)
                tally[scenario]["false_calls"] += len(result.get("calls", []))
        print("SUMMARY " + json.dumps(tally, sort_keys=True), flush=True)
        n = tally["baseline"]["total"]
        if tally["baseline"]["recovered"] != n or tally["baseline"]["false_calls"]:
            raise AssertionError("experimental knob defaults regressed authentic baseline")
        if any(v["false_calls"] for v in tally.values()):
            raise AssertionError("experimental mode produced noise-only false DSC calls")


if __name__ == "__main__":
    main()
