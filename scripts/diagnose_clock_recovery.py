#!/usr/bin/env python3
"""Offline comparison of clock-recovery enabled vs disabled (baseline and fix).

Uses one bundled DSC fixture, and does not use a radio.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def inspect(module, wav: Path):
    samples, rate = module.read_audio(wav)
    results = {}
    for enabled in (False, True):
        started = time.perf_counter()
        candidates = module.demodulate_candidates(
            samples, rate, enable_dot_sync=True,
            enable_clock_recovery=enabled,
        )
        elapsed = time.perf_counter() - started
        results[enabled] = (candidates, elapsed)
    off, on = results[False][0], results[True][0]
    # Sort by *parameter identity*, not by signal confidence which may change.
    def key(c):
        return (float(c.freq_offset_hz), float(c.offset))
    off = sorted(off, key=key)
    on = sorted(on, key=key)
    same_ids = [key(c) for c in off] == [key(c) for c in on]
    differing_bits = sum(a.bits != b.bits for a, b in zip(off, on))
    differing_confidence = sum(a.confidence != b.confidence for a, b in zip(off, on))
    return {
        "off_s": results[False][1],
        "on_s": results[True][1],
        "candidates_off": len(off),
        "candidates_on": len(on),
        "same_candidate_parameters": same_ids,
        "changed_bitstreams": differing_bits,
        "changed_confidences": differing_confidence,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline-ref", default="9a8a770")
    p.add_argument("--wav", type=Path, default=ROOT / "samples/individual_call.wav")
    args = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="dsc-clock-check-") as td:
        before = Path(td) / "baseline.py"
        before.write_bytes(subprocess.check_output(
            ["git", "show", f"{args.baseline_ref}:dsc_decode.py"], cwd=ROOT))
        for name, path in (("baseline", before), ("transition_fix", ROOT / "dsc_decode.py")):
            outcome = inspect(load(path, f"dsc_{name}"), args.wav)
            print(f"{name}: {outcome}", flush=True)
            if name == "baseline" and (
                outcome["changed_bitstreams"] or outcome["changed_confidences"]
            ):
                raise AssertionError("baseline unexpectedly uses clock recovery")
    print("Confirmed baseline enable_clock_recovery has no effect on candidate output")


if __name__ == "__main__":
    main()
