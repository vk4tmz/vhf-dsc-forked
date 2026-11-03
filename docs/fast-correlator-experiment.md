# Fast correlator experiment — 2026-11-03

This branch derives from `experiment/clock-longburst-tracking` (reference
commit `0666988`) and **does not change the clock-recovery timing equations,
correction gain or phase bounds**.

## Change

`_demodulate_with_clock_recovery` computes the four mark/space reference
correlations as sliding arrays using `numpy.correlate(..., mode="valid")`.
At each nominal bit position and mid-symbol transition the existing loop
reads the corresponding precomputed results rather than invoking four new
`numpy.dot` calls over overlapping audio windows.

This is an offline performance experiment only. No Pi service, KA9Q
integration or live decoder configuration was changed.

## Automated validation

- Original fixture regression: **6/6**.
- Complete candidate-level parity against `0666988`: **6/6 files**;
  all nine candidates per file had identical frequency/offset hypotheses,
  identical bits, and **zero confidence delta**.
- Time-base and noise variants: **30/30** validated DSC messages with
  clock recovery enabled, versus **12/30** when disabled.
- 3-second noisy windows: **15/15** DSC calls with clock recovery.
- Three 3-second noise-only windows: **zero** validated DSC calls.
- On the GitHub Linux runner, the fast-correlator implementation reduced
  fixture decoding time relative to `0666988` by roughly 9–20% in the
  direct comparison (single-run measurements; runner load varies).

**Do not extrapolate x86 times to Raspberry Pi 4.** The outstanding
validation is performance on the actual Pi, using the same 3-second
window benchmark. The prior longburst experiment on Pi took about
2.81–3.15 seconds for DSC windows and 2.84–3.23 seconds for noise-only
windows; the operating objective remains comfortably under 2 seconds.

CI run: https://github.com/vk4tmz/vhf-dsc-forked/actions/runs/41603765135
