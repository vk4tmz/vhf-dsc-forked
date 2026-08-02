#!/usr/bin/env python3
"""Verify dsc_decode.py against the bundled real off-air sample files.

Run:  python3 test_samples.py

Every sample is a real VHF DSC transmission recorded off air, except
noise.wav which is an empty-channel capture that must be rejected.
Exit code 0 = all samples decoded exactly as expected.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "dsc_decode.py"
SAMPLES = ROOT / "samples"

# (filename, expected message kind, expected self MMSI, expected call count)
EXPECTATIONS = [
    ("individual_call.wav",           "individual_call",          "002275200", 1),
    ("individual_call_2.wav",         "individual_call",          "002275100", 1),
    ("distress_relay.wav",            "distress_relay",           "002275300", 1),
    ("all_ships_call.wav",            "all_ships_call",           "002320014", 1),
    ("distress_acknowledgement.wav",  "distress_acknowledgement", "002275200", 1),
    ("noise.wav",                     None,                       None,        0),
]


def main() -> int:
    if not SCRIPT.exists():
        print(f"error: {SCRIPT.name} not found next to this script")
        return 1

    failures = 0
    for name, kind, self_id, n_calls in EXPECTATIONS:
        wav = SAMPLES / name
        if not wav.exists():
            print(f"FAIL {name}: sample file missing")
            failures += 1
            continue
        p = subprocess.run(
            [sys.executable, str(SCRIPT), str(wav)],
            capture_output=True, text=True, timeout=120,
        )
        try:
            result = json.loads(p.stdout)
        except json.JSONDecodeError:
            print(f"FAIL {name}: decoder produced no JSON "
                  f"(stderr: {p.stderr.strip()[:120]})")
            failures += 1
            continue

        calls = result.get("calls", [])
        if len(calls) != n_calls:
            print(f"FAIL {name}: expected {n_calls} call(s), got {len(calls)}")
            failures += 1
            continue
        if n_calls == 0:
            print(f"PASS {name}: rejected as expected (0 calls)")
            continue

        call = calls[0]
        msg = call.get("message", {})
        got_kind = msg.get("kind")
        got_self = call.get("self_id")
        ok = got_kind == kind and got_self == self_id
        print(f"{'PASS' if ok else 'FAIL'} {name}: kind={got_kind} self={got_self}"
              + ("" if ok else f" (expected kind={kind} self={self_id})"))
        if not ok:
            failures += 1

    print(f"\n{len(EXPECTATIONS) - failures}/{len(EXPECTATIONS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
