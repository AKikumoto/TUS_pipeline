# TUS Sonication Settings: Experiment Examples

This file collects sonication parameter sets per experiment/target for cross-reference.
**Add new entries as experiments are planned or run.**

Source: `config/TUS_sonification_settings.xlsx`
Parameter definitions: [parameters.md](parameters.md)
Japanese version: `resources/TUS/basics/experiment_examples_J.md`.

---

## Lab default (RIKEN CTX-500)

Baseline parameters used with the RIKEN CTX-500, from the `標準(default)` sheet.

| Parameter | Value | Notes |
|---|---|---|
| Power/Ch (max) | 8.762 W | Channel maximum |
| Pactual (W/ch) | 8.762 W | Delivered power |
| ISPPA | 16.35 W/cm² | Spatial peak pulse average intensity |
| ISPTA | 6.54 W/cm² | Spatial peak temporal average intensity |
| Frequency | 500 kHz | Fixed |
| Focus | 69.7 mm | See the note on focal-depth reference below |
| Pulse Duration (burst) | 200 ms | One pulse |
| Period (PRI) | 500 ms | Pulse cycle |
| Timer | 0 ms (externally triggered) | |
| Duty Cycle | 0.4 | = 200 / 500 ms |

---

## Parameters by experiment and target

Full data is in the `実験例` sheet of `config/TUS_sonification_settings.xlsx`.
The table below summarises the main differences.

### Comparison

| Parameter | RIKEN default | LC (Follini, monkey LC) | Ce_CeA (Haruno) | aMCC / ERROR (Xin) |
|---|---|---|---|---|
| Power/Ch (max) | 8.762 W | — | — | 5.739 W |
| Pactual (W/ch) | 8.762 W | — | — | 5.739 W |
| ISPPA | 16.35 W/cm² | 51.0 W/cm² | 30.02 W/cm² | 29.99 W/cm² |
| ISPTA | 6.54 W/cm² | 17.1 W/cm² | 9.00 W/cm² | 8.99 W/cm² |
| Frequency | 500 kHz | 250 kHz | 500 kHz | 500 kHz |
| Focus | 69.7 mm | 63.2 mm | 41–67.4 mm | 45–60 mm |
| Pulse Duration | 200 ms | 30 ms | 30 ms | 30 ms |
| Period (PRI) | 500 ms | 100 ms | 100 ms | 100 ms |
| Timer | — | 40 s | 40 s | 40 s |
| Duty Cycle | 0.4 | 0.3 | 0.3 | 0.3 |

---

## Planned experiments (in-lab)

From the `実験計画` sheet. Each row is a parameter, in the sheet's order:
Power max, Pactual, ISPPA, ISPTA, Frequency, Focus, PD, Period, Timer, DC.

### STRESS: amygdala

| Parameter | Value |
|---|---|
| Focus | 41–67.4 mm |
| Pulse Duration | 30 ms |
| Period | 100 ms |
| Timer | 40 s |
| Duty Cycle | 0.3 |

> Power / ISPPA / ISPTA not yet fixed (planning stage).

---

### ERROR: aMCC (`60 mm diameter transducer`)

| Parameter | Value |
|---|---|
| Power/Ch (max) | 5.739 W |
| Pactual (W/ch) | 5.739 W |
| ISPPA | 29.99 W/cm² |
| ISPTA | 8.99 W/cm² |
| Frequency | 500 kHz |
| Focus | `60 mm diameter transducer`: see data-quality notes |
| Pulse Duration | 30 ms |
| Period | 100 ms |
| Timer | 40 s |
| Duty Cycle | 0.3 |

---

### LS learning: LC

Uses the CTX-500 default settings unchanged.

| Parameter | Value |
|---|---|
| Power/Ch (max) | 8.762 W |
| Pactual (W/ch) | 8.762 W |
| ISPPA | 16.35 W/cm² |
| ISPTA | 6.54 W/cm² |
| Frequency | 500 kHz |
| Focus | 69.7 mm |
| Pulse Duration | 200 ms |
| Period | 500 ms |
| Timer | 40 s |
| Duty Cycle | 0.4 |

---

## Settings shared with Xin: aMCC

From the `Xinさんへ` sheet.

| Parameter | Value |
|---|---|
| Power/Ch (max) | 5.739 W |
| Pactual (W/ch) | 5.739 W |
| ISPPA | 29.99 W/cm² |
| ISPTA | 8.99 W/cm² |
| Frequency | 500 kHz (fixed) |
| Focus | 45–60 mm |
| Pulse Duration | 30 ms |
| Period | 100 ms |
| Timer | 40 s |
| Duty Cycle | 0.3 |

---

## Reference parameters from the literature

### LC: Follini et al. (monkey LC)

| Parameter | Value |
|---|---|
| ISPPA | 51.0 W/cm² |
| ISPTA | 17.1 W/cm² |
| Frequency | 250 kHz |
| Focus | 63.2 mm |
| Pulse Duration | 30 ms |
| Period | 100 ms |
| Timer | 40 s |
| Duty Cycle | 0.3 |

### IFC / daINS: Osada et al.

| Parameter | Value |
|---|---|
| ISPPA | 35.8 W/cm² |
| Frequency | 500 kHz |
| Focus | 60 mm diameter transducer |
| Pulse Duration | 30 ms |
| Period | 100 ms |
| Timer | 40 s |
| Duty Cycle | 0.3 |

> Focal distance is recorded as "not reported (±0.53 mm accuracy)".

---

## Data-quality notes

Carried over from the source spreadsheet; resolve against the XLSX before relying
on these entries.

- **What the `Focus` values are measured from is ambiguous.** The source sheet
  labels them skin-to-focus, but the TPO setting is **exit plane** to focus, and
  the two differ by the coupling offset (10.82 mm on the CTX-500). See
  `parameters.md` §1. Confirm which convention the sheet used before entering a
  value into the device.
- **`Focus` for ERROR, aMCC and for Osada et al. reads "60 mm diameter
  transducer"**, which is a transducer description in a focal-depth field. The
  actual focal depth for those entries is not recorded here.
- **Duty cycle is given as a fraction** (0.3, 0.4) whereas `parameters.md` and
  the device use percent (30 %, 40 %).
- **ISPPA here is device/free-field ISPPA**, not the in-situ value the
  stimulation YAMLs specify. The two differ by the skull loss. See
  `simulation_metrics.md` §3.
- **These entries are all CTX-500.** No DPX-500 (UMD) experiment is recorded yet.

---

## Adding a new entry

1. Fill in the `実験例` or `実験計画` sheet of
   `config/TUS_sonification_settings.xlsx`.
2. Add the matching section here, following the format above.
3. If the settings come from a paper or another lab, cite the source
   (author, year, DOI).

*Last updated: 2026-08-05.*
