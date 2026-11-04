# DSC tone and clock recovery ablation — 2026-11-04

Branch `experiment/dsc-tone-clock-ablation` created from
`experiment/dsc-candidate-window-audit`. This is **not** deployed to
Raspberry Pi CH70. Original fast-correlator decoder settings are unchanged
when the experiment knobs remain at defaults.

## Prior-art hypotheses

SDRangel `plugins/channelrx/demoddsc/dscdemodsink.cpp` compensates for
FM pre-emphasis by dividing two *tone correlation amplitudes* by tone
frequency; it acquires clock with relatively strong transition correction
(0.2) and tracks with slower gain (0.05) once a message is acquired.

Our Python fork calculates squared tone-correlation *powers*, so the
controlled equivalent normalization scales high-frequency power by
`(1300 / 2100)**2`. This is not necessarily appropriate to the
different, already-FM-demodulated KA9Q audio path.

Our existing clock-recovery phase correction uses gain 0.1 throughout.
For a first ablation only, emulate 0.2 until bit 200, then 0.05.
**This is not the same as switching on a confirmed phasing lock.**

## Implementation

`dsc_decode.py` adds default-off independent flags:
- `EXPERIMENT_TONE_WEIGHT_POWER = 0.0`
- `EXPERIMENT_CLOCK_GAIN_EARLY = 0.1`
- `EXPERIMENT_CLOCK_GAIN_LATE = 0.1`
- `EXPERIMENT_CLOCK_SWITCH_BITS = 200`

`scripts/probe_tone_clock_ablation.py --extended` tests all four
combinations without touching live radio. Five authentic calls are
tested at zero drift/no noise and ±0.25% drift with 0.04
Gaussian noise, plus three noise-only windows per scenario.
The default-off baseline must recover all 15 and all configurations
must produce zero noise-only validated DSC calls.

## GitHub Actions results

CI run: https://github.com/vk4tmz/vhf-dsc-forked/actions/runs/41785039430

| Scenario | Valid calls from 15 conditions | Noise-only validated calls |
| --- | ---: | ---: |
| Baseline original matched powers, gain 0.1 | **15/15** | 0 |
| Tone powers normalized by frequency² | **0/15** | 0 |
| Clock gain 0.2 early then 0.05 late | **7/15** | 0 |
| Both changed | **0/15** | 0 |

Existing full DSC drift/noise matrix and regression checks passed
with the *defaults* unchanged. Experiments clearly do not improve
these fixtures; **do not promote these settings to live CH70**.

## Phasing review

Current Python `_phasing_alignment` already follows the accepted
M.493 strategy: at least two DX + one RX, two RX + one DX, or
three RX matches in expected positions. It is *not* a rigid, exact
full-preamble matcher. This is similar in spirit to SDRangel's
noise-tolerant phasing acquisition, though the implementations are
not algorithmically identical. Blindly loosening its match conditions
would risk spurious locks and unnecessary Pi CPU consumption.

## Decision / next checks

1. Retain the original baseline, not the failed ablation.
2. Examine actual amplitude asymmetry in controlled synthetic audio
   *before* retrying frequency compensation. No evidence from these
   recordings justifies the correction.
3. A genuine locked/unlocked timing-gain adaptation would require
   streaming parser-to-demodulator feedback, a larger architectural
   change. Do not implement on the live path without an independently
   demonstrated improvement.
4. More informative than further tuning against the same clean
   fixtures is **obtaining genuine CH70 DSC RF/PCM traffic**, with
   contemporaneous metadata and replayable evidence. No actual
   positive live burst has yet been verified.
