# vhf-dsc

A single-file Python decoder for **VHF DSC (Digital Selective Calling)** — the
digital signalling system used on marine VHF radio for distress alerts, urgency
and safety calls, and routine ship-to-shore/ship-to-ship calling.

Feed it a WAV file of a DSC transmission (or pipe it live from an SDR) and it
prints the decoded call as JSON:

```bash
$ python3 dsc_decode.py samples/distress_relay.wav
{"ok": true, "input": "samples/distress_relay.wav", "sample_rate": 48000, "duration_seconds": 1.25, "calls": [{"raw_symbols": [116, ...], "format": {"symbol": 116, "name": "all_ships"}, "self_id": "002275300", "category": {...}, "message": {"kind": "distress_relay", ...}, ...}]}
```

No installation beyond Python + numpy/scipy. No radio hardware required to try
it — the `samples/` directory contains real off-air recordings.

---

## Table of contents

1. [What is DSC?](#what-is-dsc)
2. [What this decoder does](#what-this-decoder-does)
3. [Installation](#installation)
4. [Usage](#usage)
5. [Output format](#output-format)
6. [The sample files](#the-sample-files)
7. [Testing](#testing)
8. [Recording your own captures](#recording-your-own-captures)
9. [Feeding it live from an SDR](#feeding-it-live-from-an-sdr)
10. [Changing the output format](#changing-the-output-format)
11. [How the decoding works](#how-the-decoding-works)
12. [Known limitations](#known-limitations)
13. [License](#license)

---

## What is DSC?

DSC is the GMDSS (Global Maritime Distress and Safety System) digital calling
protocol for MF/HF/VHF radios. On VHF it is transmitted on **channel 70
(156.525 MHz)** using **AFSK** (audio frequency-shift keying) at **1200 baud**,
with the space tone at **1300 Hz** and the mark tone at **2100 Hz**.

A DSC transmission starts with a dot pattern (for synchronisation), then a
sequence of 10-bit *symbols* — 7 data bits plus 3 error-check bits per the
ITU-R M.493 standard. Each symbol is transmitted twice (a *DX* copy, then an
*RX* copy), which lets a receiver recover from errors. The last symbols carry
an error-check character (ECC) so a receiver can verify the whole frame.

Every vessel and coast station has a **9-digit MMSI** (Maritime Mobile Service
Identity, e.g. `002275100` for a UK coast station). DSC calls carry the
caller's MMSI, the destination (another MMSI, a group, or "all ships"), a
category (routine/safety/urgency/distress), and — for distress calls — your
position, time and nature of distress. That is why DSC distress calls are so
valuable to monitor: **a VHF DSC radio on channel 70 broadcasts your position
automatically when the red button is pressed.**

## What this decoder does

- Decodes all the common call types: distress, distress relay, distress
  acknowledgement, all-ships announcements, group calls, individual (point to
  point) calls, geographic-area calls and automatic service calls.
- Extracts the self MMSI, destination, category, telecommand (e.g. "switch to
  channel 16"), and for distress calls the position (lat/lon), UTC time and
  nature of distress.
- Uses the DX/RX redundancy to repair corrupted symbols and validates the ECC,
  so noise-corrupted captures still decode when possible.
- Rejects non-DSC audio (noise, voice, other digital modes) — it will not
  hallucinate a call out of static.

It is written to be read: one file, sectioned by pipeline stage, with comments
explaining the standard as it goes. It targets **ITU-R M.493-9** (the current
VHF DSC standard) — see [How the decoding works](#how-the-decoding-works).

## Installation

Requires **Python 3.9+** and two small dependencies:

```bash
pip install numpy scipy
# or:  pip install -r requirements.txt
```

That's it. `dsc_decode.py` is the whole program — copy it anywhere.

## Usage

```bash
# decode a file
python3 dsc_decode.py capture.wav

# decode audio piped on stdin (any format ffmpeg can read)
cat capture.wav | python3 dsc_decode.py -

# pretty-print (easier to read)
python3 dsc_decode.py --pretty capture.wav

# include demodulator diagnostics (bit statistics) in the output
python3 dsc_decode.py --debug capture.wav
```

Non-WAV inputs (mp3, ogg, m4a…) are handled via **ffmpeg** if you have it
installed. WAV input needs no ffmpeg.

A decode that finds nothing prints `{"ok": false, ...}` with `"calls": []` and,
if the audio was too short to possibly contain a call, a `"rejected"` reason.
DSC frames are ~0.5–1 s long, so captures under 1.5 s are rejected outright.

### Example output (pretty-printed)

```json
{
  "ok": true,
  "input": "samples/distress_relay.wav",
  "sample_rate": 48000,
  "duration_seconds": 1.25,
  "calls": [
    {
      "raw_symbols": [116, 116, 112, 0, 22, 75, 30, 0, 112, 126, 126, 126, 126, 126, 107, 14, 81, 10, 4, 36, 1, 31, 100, 127, 82],
      "format": {"symbol": 116, "name": "all_ships"},
      "category": {"symbol": 112, "name": "distress"},
      "self_id": "002275300",
      "address": null,
      "eos": {"symbol": 127, "name": "eos"},
      "ecc": {"expected": 82, "actual": 82, "valid": true},
      "symbol_validation": {"valid": 24, "invalid": 1, "valid_ratio": 0.96},
      "confidence": 0.83,
      "message": {
        "kind": "distress_relay",
        "telecommand": {"symbol": 112, "name": "distress"},
        "distress_mmsi": "002275100",
        "nature": {"symbol": 107, "name": "undesignated"},
        "position": {"lat": 50.33, "lon": 1.5, "coords": "50.3333N, 001.5000W"},
        "time": {"hour": 12, "minute": 30, "utc": "12:30"},
        "communication": {"symbol": 100, "name": "F3E/G3E simplex telephony"}
      },
      "demodulator": {"confidence": 0.83, "dot_sync": true, "freq_offset_hz": 0, ...}
    }
  ]
}
```

## Output format

Each call object contains:

| Field | Meaning |
|---|---|
| `raw_symbols` | The decoded 10-bit symbols (after DX/RX recovery), useful for debugging |
| `format` | Call format: `distress` (112), `all_ships` (116), `individual` (120), `group` (114), `geographic_area` (102), `automatic_service` (123) |
| `category` | `routine` (100), `safety` (108), `urgency` (110), `distress` (112), … |
| `self_id` | Caller's MMSI (9 digits) |
| `address` | Destination MMSI / group / box, depending on format |
| `eos` | End-of-sequence: `acknowledge_rq`, `acknowledge_bq`, `eos` (end of call) |
| `ecc` | Error-check character: expected vs actual, and whether it validated |
| `symbol_validation` | How many of the frame's symbols decoded to valid codewords |
| `confidence` | Overall confidence 0–1 (phasing quality + symbol validity) |
| `message` | Format-specific payload: kind + telecommand, channel, position, time, nature, phone number, etc. |
| `demodulator` | Only with `--debug`: raw bit statistics (valid ratio, phasing runs) |

`"message"` is where the interesting bits are. Examples:

- **distress / distress_relay / distress_acknowledgement** — `nature`,
  `position` (`{"lat": 50.33, "lon": 1.5, "coords": "50.3333N, 001.5000W"}`),
  `time` (`{"utc": "12:30"}`), and `communication` (what to switch to).
- **individual / group / all_ships** — `telecommand` plus `channel` (e.g.
  `{"symbol": 100, "name": "F3E/G3E simplex telephony", "channel": 16}`) when
  the call asks you to switch to a working channel.
- **geographic_area** — `area`: a lat/lon box (`NE 50°–51°N 001°–002°E`).

The JSON is plain data — feed it into anything. See [Changing the output
format](#changing-the-output-format) for turning it into CSV, text or MQTT.

## The sample files

All recordings in `samples/` are **real off-air VHF DSC captures** (channel 70,
UK south-coast region, received on an RTL-SDR). They were chosen because they
decode cleanly and show a variety of call types:

| File | What it is | Decodes to |
|---|---|---|
| `individual_call.wav` | Coast-station working-channel announcement | `individual_call`, self `002275200` (UK coast station) |
| `individual_call_2.wav` | Coast station calling ship `209479000` | `individual_call`, self `002275100` |
| `distress_relay.wav` | Coast station relaying a distress call (with position + time) | `distress_relay`, self `002275300` |
| `all_ships_call.wav` | Urgency announcement, switch to channel 16 | `all_ships_call`, self `002320014` |
| `distress_acknowledgement.wav` | Coast station acknowledging a distress call | `distress_acknowledgement`, self `002275200` |
| `noise.wav` | Empty-channel static (no DSC) | **nothing** — must be rejected |

Run `python3 test_samples.py` to confirm every sample decodes exactly as
expected (it also proves the decoder doesn't invent calls out of noise).

## Testing

```bash
python3 test_samples.py
```

Decodes all six samples and asserts the exact message kind + MMSI. Prints
`PASS`/`FAIL` per file and exits non-zero if anything regressed.

## Recording your own captures

Any FM receiver can hear DSC — it's just tones on channel 70. Options:

1. **A marine VHF radio** — connect its speaker/headphone output to your
   computer's line-in and record. DSC sounds like a short burst of "sewing
   machine" tones.
2. **An RTL-SDR** — dongles cost ~£25 and receive 156.525 MHz well:

   ```bash
   # NFM demodulate channel 70 to 48 kHz PCM audio, save as WAV
   rtl_fm -f 156.525M -s 48k -g 40 -F 9 | sox -t raw -r 48k -e signed -b 16 -c 1 - channel70.wav
   ```

   Then decode with `python3 dsc_decode.py channel70.wav`.
3. **Any SDR software** (SDR#, GQRX, SDRuno) — tune to 156.525 MHz, NFM mode,
   ~25–50 kHz bandwidth, and record.

DSC calls are short (~1 second), so record for a few minutes to catch one, or
run a continuous monitor (next section).

## Feeding it live from an SDR

The decoder reads WAV from stdin, so you can pipe a live demodulated stream
straight into it. Combined with a loop, this is a poor-man's DSC monitor:

```bash
#!/bin/bash
# dsc_monitor.sh — watch channel 70, print every DSC call as JSON
while true; do
  rtl_fm -f 156.525M -s 48k -g 40 -F 9 2>/dev/null |
    sox -t raw -r 48k -e signed -b 16 -c 1 - -t wav - 2>/dev/null |
    python3 dsc_decode.py - --pretty
done
```

Notes for a live feed:

- The decoder needs **≥1.5 s of audio per call**. With an always-on pipe it
  processes whatever arrives, so call the script once per ~2 s window (e.g.
  wrap it in a loop that reads a fixed number of samples), or simply let the
  pipeline above run — a DSC burst will be inside the window most of the time.
- If you use `rtl_fm` at a sample rate other than 48 kHz, the decoder
  resamples internally (48 kHz is optimal — 1200 baud divides cleanly).
- For multi-node / network setups, the author's full CoastalHub project
  (github.com/blackwellj/coastalhub) wraps this decoder with a UDP capture
  layer, a web dashboard and a map.

## Changing the output format

The decoder prints one JSON object per run. Because the JSON is plain
structured data, the easiest way to change the format is to post-process it.
A few starting points:

**CSV (one row per call):**

```python
import json, subprocess, sys

def decode_to_csv(wav: str) -> str:
    out = json.loads(subprocess.run(
        [sys.executable, "dsc_decode.py", wav], capture_output=True, text=True).stdout)
    rows = []
    for c in out.get("calls", []):
        m = c.get("message", {})
        rows.append(",".join(str(x) for x in [
            c.get("self_id"), c.get("address"),
            c.get("format", {}).get("name"), m.get("kind"),
            m.get("position", {}).get("coords", ""),
            m.get("time", {}).get("utc", ""),
        ]))
    return "\n".join(["self,address,format,kind,position,utc", *rows])

print(decode_to_csv("samples/distress_relay.wav"))
```

**Plain text (for a terminal/scroll monitor):**

```bash
python3 dsc_decode.py --pretty capture.wav | python3 -c "
import json, sys
d = json.load(sys.stdin)
for c in d.get('calls', []):
    m = c['message']
    print(f\"{m['kind'].replace('_',' ').upper()} — from {c['self_id']} \"
          f\"pos {m.get('position',{}).get('coords','?')} \"
          f\"utc {m.get('time',{}).get('utc','?')}\")
"
```

**MQTT / Home Assistant / notifications** — same idea: parse the JSON with any
MQTT client and publish `calls[0]` to a topic; or POST it to a webhook. A
distress-relay alert is then just `if call["message"]["kind"] == "distress_relay": notify()`.

If you want to change what the *decoder itself* emits, the relevant function
is `decode_file()` near the bottom of `dsc_decode.py` — it returns the dict
that becomes the JSON. The call records are built by `_frame_to_json()` in the
parser section.

## How the decoding works

The pipeline, top to bottom (each stage is a clearly-marked section in the
file):

1. **Read + preprocess** (`audio` section) — decode the WAV, resample to
   48 kHz if needed, remove DC, peak-normalise, bandpass 800–2600 Hz (the
   tone band) to reject out-of-band noise.
2. **Signal detection** — measure the energy in the 1300 Hz and 2100 Hz bands.
   If neither is present, stop: it's not DSC.
3. **Tone measurement** — find the actual space/mark frequencies (real
   receivers are never exactly 1300/2100 Hz; the decoder measures and corrects
   the offset, typically ±100 Hz).
4. **Dot-pattern sync** — correlate against the 20-bit alternating dot pattern
   to find where the transmission starts. This gives the bit clock.
5. **Bit decisions** — for each bit window, quadrature-correlate against the
   space and mark tones; the stronger wins. A Gardner timing loop corrects
   small clock drift (gated on data transitions).
6. **Symbol framing** (`symbols` section) — group every 10 bits into a symbol;
   the 7 data bits are checked against the 3 check bits (MSB-first, per
   ITU-R M.493-9 §1.1.1).
7. **Phasing + DX/RX recovery** (`parser` section) — find the DX phasing
   sequence (`125 111 125 110…`) and recover the information symbols. Because
   the standard transmits each symbol twice (DX then RX, §1.2.1), an invalid
   DX symbol can be repaired from its RX copy.
8. **ECC + frame rules** — trim at the EOS symbol, verify the error-check
   character, and enforce the per-format frame lengths (e.g. distress = 18
   symbols, individual = 23).
9. **Message decoding** — decode the information symbols per the format:
   pair-coded digits for MMSIs, 10ths-of-a-minute lat/lon for positions, etc.
10. **Validation** — check the MMSIs are structurally valid, the ECC matches,
    and the frame survived phasing; only then is the call emitted. Noise is
    rejected here — a frame that can't meet these checks never reaches output.

## Known limitations

- **Capture length**: audio under 1.5 s is rejected (a complete DSC frame with
  phasing is ~0.6–1.0 s, and the decoder needs margin for the dot pattern).
- **Signal quality**: like any AFSK decoder it needs a usable SNR. The dot
  sync, DX/RX redundancy and ECC give it substantial error tolerance, but a
  capture that's mostly static with a weak signal may not decode. Very clean
  recordings with a silent lead-in can also confuse the sync stage (a known
  quirk of the FFT bandpass filter's ringing) — adding any realistic noise or
  just recording real channel audio avoids this.
- **Non-standard transmitters**: check-bit convention is per ITU (MSB-first);
  some legacy/non-compliant hardware transmits LSB-first. The decoder tolerates
  both (the 7 data bits are the same either way) but strictness flags may
  differ.
- It decodes DSC **calls**, not DSC **acknowledgement sequences** beyond the
  basic acknowledgement message types listed above.

## License

MIT — do what you like, including commercial use; attribution appreciated.
See [LICENSE](LICENSE).

## VK4TMZ fork: experimental dot-pattern performance branch

The `perf/dot-pattern-optimisation` branch replaces repeated per-offset
standard-deviation reductions in `_find_dot_pattern()` with float64 prefix
moments and calculates the fixed reference norm only once. Search positions,
correlation thresholds, and accepted DSC frame criteria are unchanged, but
floating-point results may differ slightly. **Do not deploy without fixture
parity checks and Pi-side timing measurements.** The original
`blackwellj/vhf-dsc` repository is unchanged.

To compare the fork against its original `origin/master` implementation,
from a checkout of this fork:

```bash
python3 test_samples.py
python3 scripts/benchmark_dot_pattern.py
# Full six-fixture baseline/optimised comparison:
python3 scripts/benchmark_dot_pattern.py --all
```

This benchmark uses only bundled WAVs and does not interact with radios,
KA9Q multicast, or a running DSC listener. It checks recovered call identity,
kind, raw symbols, and ECC, and reports wall-clock speedups. A further
end-to-end trial of the KA9Q DSC integration is necessary before deployment.

### Second optimisation: precomputed 10-bit symbol results

The branch now precomputes all 1,024 possible 10-bit DSC codewords
using the original `decode_symbol` implementation. Repeated
`_decode_symbols` calls use this exact table instead of redoing
parity/count calculations. Run the exhaustive parity test and the
full fixtures before trusting performance results:

```bash
python3 -m unittest discover -s tests -v
python3 test_samples.py
python3 scripts/benchmark_dot_pattern.py --all
```

Decoder acceptance criteria and upstream's public API are unchanged.
This is not yet validated on the Raspberry Pi.
