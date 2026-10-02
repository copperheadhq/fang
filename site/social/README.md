# Social renders

Images for posting about fang's work, drawn in the brand's type, mark and
palette by [`make.py`](make.py). Every number on them comes from a run made
when they are drawn, and every requirement beside a number is read from the
program that states it.

## Firmware emulation

`examples/sensor_node/`, its firmware run in Renode against the board as fang
describes it, and three deliberately broken builds run against the same board.

| File | Size | For | Shows |
| --- | --- | --- | --- |
| [`emulation-card.png`](emulation-card.png) | 1200×630 | A link preview; LinkedIn | The line, the first sensor read, the temperature printed, and the broken builds failing |
| [`emulation-run.png`](emulation-run.png) | 1200×675 | X; a post's second image | `fang verify` on the board, both questions side by side |
| [`emulation-caught.png`](emulation-caught.png) | 1200×675 | X; LinkedIn | The build that ships and each broken build: what is wrong, the measure that caught it, the value against the requirement |
| [`emulation-square.png`](emulation-square.png) | 1080×1080 | LinkedIn; Instagram | Every measure of the build that ships against its requirement, and the broken builds |

`emulation-run.png` folds each question's assumptions and coverage gaps into
one line that counts them, marked with `…`. Everything else on it is the
listing as `fang verify` prints it. The full listing, gaps and all, is
[`examples/sensor_node/out/verification.txt`](../../examples/sensor_node/out/verification.txt).

### Alt text

- **emulation-card.png:** fang: Firmware against the board. First sensor read
  at 40.0 ms, required within 200 ms. Temperature printed 25.0 °C, required
  24.95 to 25.05 °C. 3 of 3 broken builds fail, each through the gate. Run in
  Renode 1.17.0.
- **emulation-run.png:** Terminal output of fang verify on
  examples/sensor_node. The startup question measures first_read 0.0400 s,
  mux_mismatches 0, reported 25.0 degC and slow_blinks 1, and passes. The
  sensor_missing question measures fast_blinks 5 and missing_reads 0, and
  passes. Both at the behavioural level in Renode, confidence 0.8.
- **emulation-caught.png:** One board, four firmware builds. The shipping
  build meets all 6 measures and passes. wrong_address.elf never reads the
  sensor in the 2 s run, against a 200 ms requirement, and fails.
  push_pull.elf has 2 I2C pins configured otherwise than the board requires,
  though every I2C transaction still succeeds, and fails. no_timeout.elf
  blinks the fault 0 times, against at least 4, and fails.
- **emulation-square.png:** fang: Firmware against the board. The shipping
  firmware meets six requirements in Renode 1.17.0: first_read 40.0 ms,
  mux_mismatches 0, reported 25.0 °C, slow_blinks 1, fast_blinks 5,
  missing_reads 0. Three broken builds each fail.

The alt text states the numbers on the images and is written by hand; redraw
the images and read them against it.

## Redrawing

```bash
pip install pillow "fonttools[woff]"
(cd site/docs && npm run build)      # the faces are read out of the docs build
python site/social/make.py
```

It needs Renode 1.17.0 on the path, runs the five emulations (about two
minutes), and writes the images here. Renode's runs are deterministic, so an
unchanged board, firmware and brand redraw byte for byte. Redraw after
changing the board, its firmware, its questions, or the brand.
