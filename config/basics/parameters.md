# TUS Sonication Parameters: Definitions and User Control

Reference: Murphy et al. (2025), *Clinical Neurophysiology* 171:192–226 (Table 1).
See also: `config/TUS_sonification_settings.xlsx`

Japanese version: `resources/TUS/basics/parameters_J.md`.
For the metrics the *simulation* reports, see `simulation_metrics.md` in this folder.

---

## 1. Parameters the user sets directly

| Parameter | Symbol / unit | Definition | Notes |
|---|---|---|---|
| **Operating Frequency** | f₀ (kHz / MHz) | The transducer's drive frequency. Fixed on most devices (e.g. 500 kHz for both the CTX-500 and the DPX-500). | Lower frequency transmits through skull better; higher frequency gives finer spatial resolution. |
| **Pulse Duration** | PD (ms) | Duration of a single pulse. Equal to the pulse train duration under continuous sonication. | Sometimes called "burst"; Murphy et al. recommend *pulse duration* for consistency. |
| **Pulse Repetition Frequency** | PRF (Hz) | How often pulses repeat (= 1 / PRI). | |
| **Pulse Repetition Interval** | PRI (ms) | Time between the onsets of two consecutive pulses (= 1 / PRF). | Also called *period* or *IPI*. |
| **Pulse Train Duration** | PTD (s) | Total time over which a train of pulses is delivered. | Corresponds to the sonication time per trial. |
| **Pulse Train Repetition Interval** | PTRI (s) | Time between the onsets of successive pulse trains. | Corresponds to the inter-trial interval (ITI). |
| **Duty Cycle** | DC (%) | Fraction of time the beam is on = PD / PRI × 100. Defined only for rectangular pulses. | E.g. PD 30 ms with a 100 ms period → DC = 30 %. |
| **Timer** |, (s) | Total stimulation time. 0 = externally triggered. | Often set to a single ~40 s trial. |
| **Focal Depth / Focus** |, (mm) | Distance from the **exit plane** to the focus. Selectable or fixed depending on device. | See §4 for each transducer's range. Note this is measured from the exit plane, not from skin, adding a gel pad increases it. |
| **Power / Ch (max)** | W / ch | Maximum drive power per channel. | Most devices allow an upper limit to be set. |
| **Waveform Mode** | — | Continuous wave (CW) or pulsed wave (PW). Normally pulsed. | CW carries a higher thermal load. |

---

## 2. Parameters computed automatically (not directly settable)

| Parameter | Symbol / unit | Definition | Formula |
|---|---|---|---|
| **Pactual** | W / ch | Power actually delivered, controlled from the setpoint and the measured impedance. | Determined inside the device |
| **ISPPA** | W/cm² | Spatial Peak Pulse Average Intensity: intensity at the focal peak averaged over the pulse duration. The primary quantity for safety assessment. | PII / PD |
| **ISPTA** | mW/cm² or W/cm² | Spatial Peak Temporal Average Intensity: ISPPA × duty cycle. The index of thermal load. | ISPPA × DC |
| **ISPTP** | W/cm² | Spatial Peak Temporal Peak Intensity: the instantaneous peak. | max(p²sp(t)) / Z |
| **Mechanical Index** | MI (dimensionless) | Cavitation-risk index. pr.3 is the rarefactional pressure derated at 0.3 dB/cm/MHz. | pr.3 / √f₀ |
| **Thermal Index** | TI (dimensionless) | Index of thermal bioeffect risk. | Computed by the device |
| **TIC** | (dimensionless) | Cranial Thermal Index: risk of temperature rise in skull. | Output power ÷ 0.210 W |

**ISPPA is reported two ways and they are not interchangeable.** The stimulation
YAMLs specify the **in-situ** ISPPA at the focus; the TPO's input field takes
**free-field** (in-water) ISPPA. They differ by the skull loss, a factor of ~20
for a deep target. `write_tpo_summary_BB` does the conversion, see
`simulation_metrics.md` §3.

---

## 3. Pressure and intensity quantities (needed to report and interpret)

| Parameter | Symbol / unit | Definition |
|---|---|---|
| **Acoustic Pressure** | p (MPa) | Instantaneous deviation from ambient pressure. |
| **Peak Positive Pressure** | p+ (MPa) | Peak compressional pressure (also written pc). |
| **Peak Negative Pressure** | p− (MPa) | Peak rarefactional pressure (also written pr). This is what drives cavitation. |
| **Spatial Peak Pressure** | psp (MPa) | Peak pressure at the focus during the steady part of the pulse. |
| **Pulse Intensity Integral** | PII | Integral of instantaneous intensity over the pulse duration. |
| **Instantaneous Intensity** | I(t) (W/cm²) | Intensity at time t = p² / (density × sound speed) = p² / Z. |

---

## 4. Fixed parameters, by transducer

| | **CTX-500 (RIKEN)** | **DPX-500 (UMD)** |
|---|---|---|
| Serial | CTX-500-4CH-SN056 | DPX-500-4CH-SN048 |
| Frequency f₀ | 500 kHz (fixed) | 500 kHz (fixed) |
| Active diameter | 64.0 mm | 64.0 mm |
| Radius of curvature | 63.2 mm | 150.0 mm |
| **Natural focal depth** | **52.4 mm** | **144.9 mm** |
| f-number | ~0.99 | ~2.34 |
| Hardware focal range | 33.6 – 82.5 mm | 50.0 – 120.0 mm |
| Calibrated focal range | 41.4 – 69.7 mm | 60.0 – 120.0 mm |
| Coupling | solid water dome | BCS-NF10 bladder |
| Exit-plane offset | 10.82 mm | 10.0 mm |
| Max tilt | 10° | 10° |
| Max power / ch | 8.762 W (default) | — |

Source: `config/transducers/CTX500_RIKEN.yaml`, `DPX500_UMD.yaml`.

**Axial FLHM grows steeply with focal depth.** From the vendor calibration tables:

| TPO setting | CTX-500 axial FLHM | DPX-500 axial FLHM |
|---|---|---|
| ~60 mm | 23.8 mm (at 57.1) | 24.1 mm |
| ~70 mm | 36.7 mm (at 69.7, its max) | ~31 mm (at 68.0) |
| 80 mm | out of range | 38.2 mm |
| 100 mm | out of range | 55.4 mm |
| 120 mm | out of range | 71.7 mm |

At matched depth the two are comparable, the difference is the **depth each is
used at**. The DPX-500's higher f-number (2.34 vs 0.99) is what lets it reach a
100 mm target at all, and the 55 mm focal length at that setting is the price.
So a deep target driven by the DPX-500 has poor axial selectivity even when
perfectly aimed: specified behaviour, not a planning error. See
`simulation_metrics.md` §6.

**Steering is how a depth request is realised.** An annular array cannot move
its focus mechanically; the rings are phased instead:

```
ZSteering = requested_depth − natural_focal_depth + correction
```

A 103 mm request on the DPX-500 therefore means −40 mm of steering, and it is
that excursion, not a misaim, that elongates the focus.

---

## 5. Safety reference values

Values below are indicative; device specifications and regulatory documents differ.

| Quantity | Guideline | Basis |
|---|---|---|
| ISPTA | < 720 mW/cm² | FDA diagnostic-ultrasound guideline (indicative) |
| MI | < 1.9 | FDA limit for non-diagnostic ultrasound |
| TIC | < 6 | Skull heating risk (see ITRUSST guidance) |
| ΔT in brain | < 2 °C for non-thermal TUS | ITRUSST (Brinker et al. 2023) |
| CEM43 | < 0.25 min | ITRUSST |

**CEM43, not ΔT, is what the limits are written against.** ΔT is the temperature
rise above baseline and carries no time information; CEM43 (cumulative equivalent
minutes at 43 °C) combines temperature and duration. ITRUSST imposes both because
ΔT is the quick check and CEM43 is the actual dose.

> **Note:** safety standards for TUS neuromodulation are still being
> standardised. Consult the ITRUSST website and Murphy et al. (2025) for the
> current guidance.

---

## 6. A note on inconsistent terminology

Murphy et al. (2025) argue that inconsistent terminology undermines reproducibility:

| Ambiguous term | Preferred term | Meaning |
|---|---|---|
| "Burst" | Pulse Duration (PD) | Duration of one pulse |
| "Sonication" | Pulse Train Duration | Duration of the whole pulse train |
| "Stimulus" | depends on context, state it explicitly | Context-dependent |
| "Period" | Pulse Repetition Interval (PRI) | Pulse cycle including the interval |

---

*Last updated: 2026-08-05. Source: Murphy et al. 2025 Table 1;
`TUS_sonification_settings.xlsx`; `config/transducers/*.yaml`.*
