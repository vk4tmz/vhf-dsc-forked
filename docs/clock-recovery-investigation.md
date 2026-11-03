# Clock recovery investigation — 2026-11-03

## Scope

This is an **experiment**, isolated on `experiment/clock-recovery-transition`
and **not approved for integration into KA9Q VHF DSC**.

The stable performance branch `perf/dot-pattern-optimisation` is unchanged.

## Confirmed bug

In `_demodulate_with_clock_recovery`:

```python
bits.append(bit)
prev_bit = bits[-1]
if bit != prev_bit:
    ...
```

The expression compares the current bit with itself, so the early/late
timing adjustment is never reached. Setting `enable_clock_recovery=True`
therefore has **no effect on decoded bitstreams or confidence** in the
current implementation.

The experiment changes `prev_bit` to `bits[-2]`, enabling the previously
unreachable timing adjustment. This is not a verified Gardner timing-loop
implementation; the direction and normalisation of the error estimate
need further DSP validation.

## Evidence

The GitHub Actions `diagnose_clock_recovery.py` comparison against
baseline `9a8a770` found, on both `individual_call.wav` and
`noise.wav`, nine candidates:

- Baseline recovery disabled vs enabled: **0** changed bitstreams,
  **0** changed confidence results.
- Transition experiment disabled vs enabled: **9** changed bitstreams,
  **9** changed confidence results.

All six existing DSC fixtures retain call parity; however, they do not
prove improved weak-signal performance. The activated timing calculations
also increase runtime relative to the performance branch.

## Synthetic FSK symbol timing drift

The diagnostic `scripts/probe_clock_recovery_fsk.py` generates 300 known,
continuous-phase AFSK bits at 48 kHz/1200 baud, with seeded Gaussian noise
(standard deviation 0.08), varied source baud-rate error, and two initial
sample phases. Errors are compared against the generated bits, not inferred
from DSC message validity.

At phase 0, bit errors / decoded bits:

| Baud-rate drift | Disabled | Transition fix |
|---|---:|---:|
| -1.00% | 131/300 | 134/299 |
| -0.25% | 57/300 | 90/300 |
| 0.00% | 0/300 | 0/300 |
| +0.25% | 59/300 | 9/300 |
| +1.00% | 129/300 | 115/300 |

At phase 7, results show the same sign-dependent pattern
(-0.25%: 56->90 errors; +0.25%: 54->3 errors).

**Conclusion:** activation improves positive drift but worsens negative
drift in this controlled setup. It must not be merged as a reception fix.
The fixture checks are insufficient to assess robustness over clock error,
phase offset, SNR, fading, or adjacent interference.

## Next investigation

1. Analyze the timing-error sign/normalisation and transition gating,
   independently of performance optimisations.
2. Add bidirectional drift, phase, SNR and fading matrices with
   known-bit BER and full DSC payload validation.
3. Require no meaningful regression in weak-signal/negative-drift cases
   and preserved six-fixture message parity before promoting a correction.
4. Keep experimental timing logic off in the deployed KA9Q listener.

No services or deployed configs were changed during this investigation.
