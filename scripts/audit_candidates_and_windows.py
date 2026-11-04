#!/usr/bin/env python3
"""Offline audit of top-eight DSC candidate filtering and overlapping-window loss.

Uses only bundled off-air WAV fixtures; never opens an SDR, multicast or live service.
No decoder source is patched. Candidate demodulation is computed once per fixture.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import time

import numpy as np
from scipy.io import wavfile

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import dsc_decode as decoder

CASES = (
    ("individual_call.wav", "individual_call", "002275200"),
    ("individual_call_2.wav", "individual_call", "002275100"),
    ("all_ships_call.wav", "all_ships_call", "002320014"),
    ("distress_relay.wav", "distress_relay", "002275300"),
    ("distress_acknowledgement.wav", "distress_acknowledgement", "002275200"),
)


def is_expected(calls, kind, mmsi):
    return any(c.get("message", {}).get("kind") == kind
               and c.get("self_id") == mmsi for c in calls)


def find_valid(candidates, limit=None):
    found = []
    for rank, candidate in enumerate(candidates if limit is None else candidates[:limit], 1):
        calls = decoder.parse_bits(candidate.bits)
        if calls:
            found.append({"rank": rank, "calls": calls})
    return found


def candidate_audit(path, kind, mmsi):
    samples, rate = decoder.read_audio(path)
    detection = decoder.detect_dsc_signal(samples, rate)
    before = time.perf_counter()
    candidates = (decoder.demodulate_candidates(samples, rate)
                  if detection.get("has_dsc_signal") else [])
    demod_seconds = round(time.perf_counter() - before, 3)
    # Do not demodulate twice; compare exact candidate streams.
    hits = find_valid(candidates)
    matching = [hit["rank"] for hit in hits
                if is_expected(hit["calls"], kind, mmsi)]
    return {
        "file": path.name,
        "duration_s": round(len(samples) / rate, 3),
        "detected": bool(detection.get("has_dsc_signal")),
        "candidate_count": len(candidates),
        "demod_seconds": demod_seconds,
        "matching_ranks": matching,
        "top8_recovers": any(x <= 8 for x in matching),
        "all_recovers": bool(matching),
        "other_validated_ranks": [h["rank"] for h in hits
                                  if not is_expected(h["calls"], kind, mmsi)],
    }


def window_audit(path, kind, mmsi, lead_s):
    rate, raw = wavfile.read(path)
    if raw.ndim > 1:
        raw = raw.mean(axis=1)
    source = raw.astype(np.float32)
    # Preserve source shape and relative amplitude; deterministic, modest
    # noise ensures non-empty padding resembles a live no-squelch channel.
    peak = max(1.0, float(np.max(np.abs(source))))
    source /= peak
    lead = round(lead_s * rate)
    total = max(8 * rate, lead + len(source) + rate)
    noise = np.random.default_rng(20261104).normal(0, .025, total).astype(np.float32)
    noise[lead:lead + len(source)] += source
    timeline = np.clip(noise, -1, 1)
    results = {}
    with tempfile.TemporaryDirectory(prefix="dsc-win-audit-") as tmp:
        for size, starts in ((3, (0, 2, 4)), (5, (0, 2, 4))):
            recovered = []
            spans = []
            for start in starts:
                stop = start + size
                if stop > len(timeline) / rate:
                    continue
                wav = Path(tmp) / "window.wav"
                wavfile.write(wav, rate, (timeline[start*rate:stop*rate]*32767).astype("<i2"))
                outcome = decoder.decode_file(wav)
                if is_expected(outcome.get("calls", []), kind, mmsi):
                    recovered.append(start)
                spans.append([start, stop])
            results[str(size) + "s"] = {"starts_with_call": recovered, "tested_windows": spans,
                                        "recovered": bool(recovered)}
    return {"lead_s": lead_s, "source_duration_s": round(len(source)/rate, 3),
            "window_results": results}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full", action="store_true", help="check all five call fixtures and both window phases")
    ap.add_argument("--windows", action="store_true", help="also run computationally heavier 3s/5s window audit")
    args = ap.parse_args()
    selected = CASES if args.full else CASES[:2]
    for name, kind, mmsi in selected:
        path = ROOT / "samples" / name
        report = {"candidate": candidate_audit(path, kind, mmsi)}
        if args.windows:
            report["windows"] = [
                window_audit(path, kind, mmsi, lead)
                for lead in ((0.25, 1.80) if args.full else (1.80,))
            ]
        print(json.dumps(report, sort_keys=True), flush=True)
        if not report["candidate"]["all_recovers"]:
            raise AssertionError(f"full-candidate audit lost known fixture: {name}")
    print("PASS: known authentic fixtures recover with exhaustive candidate parsing", flush=True)


if __name__ == "__main__":
    main()
