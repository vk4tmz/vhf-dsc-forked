# DSC candidate ranking and window-boundary investigation

Isolated branch: `experiment/dsc-candidate-window-audit`, based on
`experiment/clock-recovery-fast-correlators`.

## Scope
**No change** to `dsc_decode.py`, the live CH70 worker, the radiod
configuration, or the validated decoder baseline. Offline diagnostics use
the five bundled authentic DSC call fixtures.

## Why these experiments
1. `decode_file()` generates and sorts multiple bitstream candidates by a
   correlation-derived confidence, then passes **only the first eight** to
   `parse_bits()`. The best tone correlation need not mean best framing.
2. The KA9Q live worker decodes 3-second blocks advancing every 2 seconds.
   Only one second overlaps; a call crossing a boundary may be absent in
   complete form from *both* adjacent windows. Previous three-second
   fixture tests deliberately placed each **complete** call in a window;
   those tests do not establish arbitrary arrival-phase coverage.

## Scripts
```bash
cd ~/tools/vhf-dsc-candidate-window-audit
.venv/bin/python scripts/audit_candidates_and_windows.py
.venv/bin/python scripts/audit_candidates_and_windows.py --full
.venv/bin/python scripts/audit_candidates_and_windows.py --windows
.venv/bin/python scripts/audit_candidates_and_windows.py --full --windows
```
The script imports and calls the decoder, but **does not modify it**:
- Runs `detect_dsc_signal` and `demodulate_candidates` once per original call
- Parses every candidate for existing strict `validate_call()` results
- Emits the rank of each genuine validated call, the top-eight outcome,
  number of candidates, file duration and demodulation wall time
- Optional `--windows`: places the same fixture at controlled offsets in
  eight seconds of seeded noise; compares 3s and 5s windows on a 2s hop.
  `--full` checks all five calls with two arrival phases.
- Requires all original authentic fixtures to decode with exhaustive
  candidate parsing; never asserts that more calls must be recovered.

This is a **diagnostic, not a production decoder change**. A positive
`all_recovers` and negative `top8_recovers` would justify an opt-in
framing-aware candidate search, while preserving duplicate controls and
CPU limits. A 5s-only recovery would justify adaptive buffering or a
streaming framer. Negative results do not establish there is no problem
on live noisy CH70 data.

## Safety and interpretation
Do not feed all candidates into the live decoder by default: noisy
windows can have many more candidate bitstreams, and parsing everything
has an additional CPU cost. Do not increase production windows to 5s
without measuring Pi latency and dropped_windows. Longer windows
can introduce **more**, not less, CPU overload.

The current CH70 live listener can remain running throughout this
offline experiment. The script reads files only and uses temporary
WAV files for window experiments, which are removed automatically.

## Next checks
1. Confirm CI baseline and candidate-rank results.
2. Collect Pi 4 CPU data from this isolated branch.
3. For any detected failure, reproduce with a single deterministic
   fixture before writing new selection logic.
4. Require preserved 6/6 fixture parity, 15/15 short-window results,
   30/30 drift/noise recovery and zero false calls before proposing any
   live change.

## Measured results: GitHub Actions (2026-11-04)

CI on Linux/x86 (not a Raspberry Pi), five authentic off-air call fixtures:

| File | Candidate count | Valid expected candidate ranks | Top-8 recovery |
| --- | ---: | --- | --- |
| individual_call.wav | 9 | 1,2,4,5,8 | yes |
| individual_call_2.wav | 9 | 1,3,4,5,6,7,8 | yes |
| all_ships_call.wav | 9 | 1..9 | yes |
| distress_relay.wav | 9 | 1..9 | yes |
| distress_acknowledgement.wav | 9 | 1..9 | yes |

All five originals recover with the existing top-eight cap, as well as
with exhaustive candidate parsing. This **does not support** immediately
removing the cap; pathological noisy recordings may still differ.

Both injected arrival phases (0.25s and 1.80s) yielded the correct validated
call in **all five** fixtures with both 3s and 5s / 2s-hop windows (10/10
fixture/phase combinations for each duration). At 1.80s, the 3s
windows do not necessarily contain the entire source recording: the
decoder nevertheless recovered a valid message from at least one
partial window. This demonstrates **useful partial-burst tolerance** and
contradicts a simple assertion that arbitrary split frames always fail.

No demonstrated win for 5s windows in these data; 5s has higher
computational cost and is not justified for the live Pi service.

The preexisting full drift/noise matrix also retained **30/30** correct
recoveries. No production files changed.

### Interpretation and remaining gaps

These fixtures are 1.625–1.875s and have clean/simple signal structures.
They do **not** prove all real longer DSC calls can fit in three-second
windows. No actual real-time Pi 4 timing measurement was run for 5s
windows. To determine the 21-hour zero-call root cause, a real CH70
transmission capture or controlled RF-injected test is still needed.

Do not make the top-eight or window-length changes solely from these
measurements.
