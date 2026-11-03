#!/usr/bin/env python3
"""Compare the fork's decoder with the unmodified Git baseline on WAV fixtures.

Read-only and offline. Does not start a receiver or transmit any signal.
Fails if validated DSC call identities, types, raw symbols or ECC disagree.
Run from the fork checkout, with its original master branch available.
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
SAMPLES = ("noise.wav", "individual_call.wav", "all_ships_call.wav",
           "individual_call_2.wav", "distress_relay.wav",
           "distress_acknowledgement.wav")


def load_decoder(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def signature(result: dict) -> list:
    """Compare actual DSC payloads, excluding measurement-only confidence."""
    calls = result.get("calls", [])
    return sorted(
        (str(call.get("self_id")),
         str(call.get("message", {}).get("kind")),
         repr(call.get("raw_symbols")),
         bool(call.get("ecc", {}).get("ok")))
        for call in calls
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", default="origin/master",
                        help="unaltered upstream ref, e.g. origin/master")
    parser.add_argument("--all", action="store_true", help="run all six fixtures")
    args = parser.parse_args()

    try:
        baseline_source = subprocess.check_output(
            ["git", "show", f"{args.baseline_ref}:dsc_decode.py"],
            cwd=ROOT, stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        parser.error(f"cannot load baseline: {exc.stderr.decode(errors='replace').strip()}")

    with tempfile.TemporaryDirectory(prefix="vhf-dsc-baseline-") as td:
        original_path = Path(td) / "baseline.py"
        original_path.write_bytes(baseline_source)
        original = load_decoder(original_path, "dsc_baseline_benchmark")
        optimised = load_decoder(ROOT / "dsc_decode.py", "dsc_optimised_benchmark")
        failures = 0
        names = SAMPLES if args.all else SAMPLES[:3]
        for name in names:
            wav = ROOT / "samples" / name
            if not wav.exists():
                print(f"MISSING fixture: {wav}")
                failures += 1
                continue
            values = []
            for version, decoder in (("baseline", original), ("optimised", optimised)):
                start = time.perf_counter()
                result = decoder.decode_file(wav)
                elapsed = time.perf_counter() - start
                values.append((result, elapsed))
                print(f"{name}: {version} {elapsed:.3f}s, "
                      f"{len(result.get('calls', []))} calls", flush=True)
            same = signature(values[0][0]) == signature(values[1][0])
            speedup = values[0][1] / max(values[1][1], 1e-9)
            print(f"  {('PASS' if same else 'FAIL')} call parity; "
                  f"speedup={speedup:.2f}x", flush=True)
            if not same:
                failures += 1
                print(f"  original: {signature(values[0][0])}")
                print(f"  changed:  {signature(values[1][0])}")

        print(f"\n{len(names) - failures}/{len(names)} fixture comparisons passed")
        return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
