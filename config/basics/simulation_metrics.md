# Simulation Metrics: Definitions

Every metric reported by step 5 (BabelBrain) and by the placement comparison,
with the definition taken from the code rather than from the name. Source
references are given so each one can be checked.

Produced by: `src/utils.py::summarise_acoustic_BB`,
`placement_metrics_BB`, `compare_placements_BB`, `write_tpo_summary_BB`,
`plot_thermal_qc_BB`, `list_plantus_vertices`.

---

## 1. Placement geometry

| Metric | Unit | Definition | Source |
|---|---|---|---|
| **entry (x, y, z)** | mm | Scalp entry point in native scanner RAS. The PlanTUS vertex position. | `skin.surf.gii` |
| **side** | — | `contra` = entry and target lie on opposite sides of x = 0, so the beam crosses the midline. `ipsi` = same side. | `list_plantus_vertices` |
| **exit plane → ROI** | mm | Distance from the transducer **exit plane** (outer face of the coupling) to the ROI. **This is the focal-depth value dialled into the TPO.** Not the distance from skin: adding a gel pad moves the exit plane away and *increases* this. | `*_PlanTUS_depth_report_vtx*.txt` |
| **aim angle** (`angle_deg`, `aim°`) | ° | Angle between the **scalp normal** and the **scalp→target vector**. 0° = the target lies straight along the scalp normal. **This is the one PlanTUS filters on**, against `max_angle` (10° for both transducers here). | `PlanTUS_wrapper.py:305-311` → `angles_skin.func.gii` |
| **skin–skull angle** (`skin_skull_deg`, `skl°`) | ° in [0, 90] | Angle between the scalp normal and the nearest **skull** normal, how obliquely the beam meets bone. 0° = the beam hits bone square. Not a filter, but one of the three tiebreak terms in `select_best_vtx`. It is the term that tracks transmission: see §6. | `PlanTUS_wrapper.py:368-374` → `skin_skull_angles_skin.func.gii`, folded by `_fold_obliquity` |
| **ROI axis clip** (`inter`) | mm | Length over which the beam **axis** (a line, not the beam) passes through the ROI, at that one vertex. | `target_intersection_skin.func.gii` |
| **ROI axis clip ≤5 mm** (`inter_near`) | mm | Best `inter` among vertices within 5 mm. | `list_plantus_vertices` |

**Why `skl°` is folded.** PlanTUS computes it as
`arccos(skin_normal · skull_normal)`, so the raw file spans 0–180°. Above 90°
the two *surfaces* are still parallel, the nearest skull vertex's outward
normal simply points the other way, because the ray landed on the **inner**
table of the skull shell (`skull.surf.gii` covers SimNIBS tags 1007+1008, a
closed shell with both tables). Read unfolded, such a vertex looks like the
worst possible incidence when it is near-perfect: 178 of sub-z004's 4 628 safe
vertices sit above 90°. `_fold_obliquity` maps `a → min(a, 180−a)` wherever the
value is used or reported. It is idempotent, so the on-disk maps written before
this change need no migration.

**Reading `inter`.** It is knife-edge per vertex: neighbours 1–3 mm away
routinely differ by several mm. `0.00` with a nonzero `≤5 mm` means the vertex
sits at the **edge** of the intersecting patch, *not* that the beam misses, the
−3 dB focal lobe is 5–18 mm across laterally (measured: 5.1 mm for sub-z002
vtx26749 and 18.4 mm for vtx15110), far wider than that offset. Never judge a placement on
`inter` alone.

**Why −3 dB and not −6 dB.** The code thresholds at `p ≥ p_max/√2`, i.e.
`I ≥ 0.5·I_max`, the half-maximum *intensity* contour, which is −3 dB. That is
what "FLHM" (full length at half maximum) refers to. −6 dB would be
`I ≥ 0.25·I_max` (`p ≥ 0.5·p_max`), a noticeably larger region: for sub-z002
vtx26749 the main lobe grows from 649 mm³ at −3 dB to 1961 mm³ at −6 dB. Earlier
versions of this file and of `utils.py` labelled the −3 dB region as −6 dB; the
threshold in the code never changed.

---

## 2. Acoustic: focus placement

Targeting is judged on **where the −3 dB focal lobe sits** and **how large it
is**, a lobe centred on the target is worthless if it is 90 mm long. The main
lobe is the **largest** connected component above −3 dB, matching BabelBrain; see
§6 for why that distinction matters.

| Metric | Unit | Definition | Source |
|---|---|---|---|
| **FLHM centroid → target (brain only)** | mm | Distance from the target to the centre of mass of the largest −3 dB component inside brain. **Reproduces the BabelBrain GUI's "Distance target to FLHM center" exactly**, verified on sub-z002 vtx26749: GUI [1.1, 0.3, −0.7], pipeline [1.1, 0.3, −0.8]. Green < 5 mm, orange 5–10, red ≥ 10. | `summarise_acoustic_BB` |
| **I at target (norm to brain peak)** | — | Intensity at the target voxel divided by the maximum intensity anywhere in brain. 1.00 = the target *is* the brain maximum. Green ≥ 0.75, orange 0.50–0.75, red < 0.50. | same |
| **target inside the lobe** | bool | Whether the target voxel is in the main lobe. `NO` is the genuine miss condition. | same |
| **−3 dB lobe axial span** | mm – mm | The lobe's depth interval, measured from the skin along the beam. | same |
| **−3 dB lobe axial length** | mm | Length of that interval, the axial selectivity. Compare against the transducer's calibrated axial FLHM (DPX-500 at a 100 mm setting: 55 mm; CTX-500 at 30 mm: ~15 mm). Longer than calibration means the skull has smeared the focus. | same |
| **−3 dB lobe lateral width** | mm | The lobe's widest lateral extent. | same |
| **(clipped)** | flag | The lobe runs into the brain boundary along the beam axis, i.e. it is cut off by the far skull and the true extent is longer than reported. | same |
| **FLHM volume (brain only)** | mm³ | Volume of the main lobe. Followed by a warning when the brain maximum lies in a *different*, smaller component, a hotspot, not the focus. | same |
| **main lobe of −3 dB** | % | Main lobe as a fraction of all above-threshold voxels in brain. 100 % = one coherent focus; low = the field is fragmented into speckle. | same |
| **FLHM … (whole domain)** | mm / mm³ | Same computation thresholded against the **global** pressure maximum. For deep targets that maximum sits in bone, so these rows describe a skull hotspot and are **not** a targeting measure. | same |
| **peak I in brain (norm)** | — | Maximum intensity inside brain, normalised to the **whole-domain** pressure maximum. 0.20 means "the brain peak is 20 % of the global peak". | same |
| **off-target brain I** | — | Maximum intensity in brain **outside** the brain main lobe, same normalisation. Close to `peak I in brain` means comparable intensity exists away from the intended spot. | same |
| **pressure max in** | — | Tissue containing the absolute pressure maximum. `Cortical bone` means the skull, not the brain, takes the highest pressure. | same |

**Main lobe = the largest connected component** above −3 dB, following
`_BabelBaseTx.CalcVolumetricMetrics`. Taking the component that *contains the
maximum* instead reads a small distal hotspot as the focus whenever one
marginally outpeaks the true lobe, see §6.

### Outlier-resistant rows

> **`focal peak outlier` is our own name.** The phenomenon, reflection at an
> impedance boundary, is standard (Murphy et al. 2025 §1.3), but neither
> ITRUSST nor BabelBrain defines a measure for it, which is why BabelBrain does
> not notice when it breaks its own metric. Do not cite the term as if it were
> established.


A reflection at a bone/brain interface can leave a **single voxel** above the
focus itself. The threshold is taken from the maximum, so half of that outlier is
then above the whole real focus, the largest component collapses to a few voxels
and the field reads as having no focus at all, while a normal ~900 mm³ lobe is
plainly present. This is inherited from BabelBrain, which does
`ISkull /= ISkull.max()` before thresholding at 0.5; the GUI has the same
vulnerability.

| Metric | Unit | Definition | Source |
|---|---|---|---|
| **Focal peak outlier** | × | Brain maximum over the 99.99th percentile of in-brain intensity. **≥ 1.5 means a lone voxel outpeaks the focus and the ≈GUI rows are meaningless**; read the outlier-resistant ones. Measured: 1.15–1.23 where the peak is the focus, 1.9–2.8 where it is an interface artefact. | `summarise_acoustic_BB` |
| **FLHM centroid → target (outlier-resistant)** | mm | As above, thresholded from the 99.99th percentile instead of the maximum. | same |
| **FLHM volume (outlier-resistant)** | mm³ | Same. On sub-z004 pmEC left this reads 922 mm³ against 0.3 mm³ for the GUI-matching row. | same |

Both are kept because only the maximum-based rows are comparable with the GUI.

### Volumetric target exposure

`FLHM centroid → target` is a **targeting error**: it says where the focus
centre is, not how much of the structure is exposed. Murphy et al. (2025) state
the criterion as *"focal intensity is high within the structure and low in
surrounding tissue"* (Fig. 21), which is volumetric. They give **no numeric
tolerance**, only the rule of thumb that the smaller the target and focus, the
more accurate the targeting must be (§3.3.1).

| Metric | Unit | Definition | Source |
|---|---|---|---|
| **ROI coverage** | % | Fraction of the ROI volume inside the −3 dB focal volume. | `run_sweep.score_candidate` |
| **coverage ceiling** | % | `min(1, FLHM volume / ROI volume)`: the largest coverage physically available. A single-element transducer cannot cover a structure larger than its focus. | same |
| **coverage efficiency** | % | `coverage / ceiling`, i.e. the Szymkiewicz–Simpson overlap coefficient `|A∩B| / min(|A|,|B|)`. 1.0 = the smaller volume sits entirely inside the larger. Whenever the focus is smaller than the ROI this reduces to `1 − off-target`; the ceiling is what makes coverage interpretable. | same |
| **off-target fraction** | % | Fraction of the focal volume outside the ROI. | same |

**Read coverage against its ceiling, never against 100 %.** For rHipp and cHipp
(3100–4100 mm³ per side against a 860–1450 mm³ focus) the ceiling is 26–36 %, so
a coverage of 15 % is 57 % of what is achievable, not a failure.

**Coverage and exposure disagree, and both are needed.** sub-z004 cHipp right
reaches 0.95 relative exposure at the target *point* while covering only 25 % of
what its geometry allows; sub-z002 rHipp left reaches 0.84 and 57 %.

**A large FLHM volume is not good.** It means the focus is not tight. A small
volume with a low main-lobe percentage means a fragmented field. Neither is
ideal; a compact lobe coincident with the ROI is.

---

## 3. Dose and device settings

| Metric | Unit | Definition | Source |
|---|---|---|---|
| **derating ratio** | — | (max \|p\| in brain ÷ max \|p\| in the water-only run)². Equivalently **in-situ ISPPA ÷ free-field ISPPA**. 0.048 means the skull and scalp cut intensity to 4.8 %. Matches BabelBrain's "Total losses ratio using single punctual measurement". | `write_tpo_summary_BB`; cf. `CalculateTemperatureEffects.py:222` |
| **derating (dB)** | dB | `10·log10(ratio)`. | same |
| **BaseIsppa** | W/cm² | The **in-situ** ISPPA at the focal point, set in the stimulation YAML. The reference the BHTE solve scales from. | `config/stimulation/*.yaml` |
| **required free-field ISPPA** | W/cm² | `BaseIsppa ÷ derating`. **This is the number entered in the TPO's ISPPA field**, the device takes free-field, not in-situ, and computes per-channel power itself. | `write_tpo_summary_BB` |
| **required free-field ISPTA** | W/cm² | The above × duty cycle. | same |
| **calibrated reference ISPPA** | W/cm² | Mean of `calibration.isppa_w_per_cm2` in the transducer YAML, the ISPPA the vendor held constant across the steering range (CTX-500: ~30). Absent for the UMD DPX-500. | `config/transducers/*.yaml` |
| **exceeds calibrated ref** | bool | Whether the requirement is above that reference. Reported, not blocked: the TPO power limit is adjustable, though the vendor calls operating above it off-label. | `write_tpo_summary_BB` |

---

## 4. Thermal

| Metric | Unit | Definition | Source |
|---|---|---|---|
| **T at target** | °C | Peak temperature reached at the target during sonication. ΔT = this − baseline (37 °C). | `TempProfileTarget` in `*_AllCombinations.h5` |
| **Max T brain / skin / skull** | °C | Peak temperature anywhere in each tissue. For deep targets the skull is usually hottest, absorption is dominated by bone, not by the focus. | `plot_thermal_qc_BB` |
| **CEM43** | min | Thermal **dose**: cumulative equivalent minutes at 43 °C. Combines temperature and duration, so it is the quantity safety limits are written against, not ΔT. Reported per tissue. | `CEMBrain/CEMSkin/CEMSkull` in the h5 |
| **MI** | — | Mechanical index = peak brain pressure [MPa] ÷ √(frequency [MHz]). Cavitation-risk proxy, independent of DC/PRF/duration. | `CalculateTemperatureEffects.py:1068` |
| **TI / TIC / TIS** | — | Thermal indices (soft tissue / cranial / scanned) as reported by BabelBrain. | `*_AllCombinations.h5` |

### Reference thresholds

| Quantity | Guideline | Source |
|---|---|---|
| ΔT in brain | < 2 °C for non-thermal TUS | ITRUSST (Brinker et al. 2023) |
| CEM43 | < 0.25 min | ITRUSST |
| MI | < 1.9 | FDA diagnostic-ultrasound limit |

Colour coding in `summarise_acoustic_BB` follows Brinker et al. (2023),
*Brain Stimulation* 16(3):856–871, and ISO/TS 63635:2022.

---

## 5. Reading a comparison

Judge targeting on **FLHM centroid → target**, **I at target**, **target inside
the lobe**, and the **−3 dB lobe axial length**. A placement is good when the
lobe is centred on the target, the target is driven near the brain maximum, and
the lobe is no longer than the transducer's calibrated axial FLHM. Then weigh:

- **derating**: drives the required device output; strongly tied to path length
  and how much bone the beam crosses.
- **CEM43 brain**: thermal cost of the placement, and it can differ several-fold
  between placements that look similar acoustically.
- **peak I in brain**: how much of the field actually reaches brain rather than
  depositing in skull.

Use one shared cut coordinate (the target) for every column, or the panels show
different anatomy and cannot be compared.

**Two acoustic figures, two normalisations.** `plot_acoustic_qc_BB` normalises
to the **whole-domain** maximum. For a deep target that maximum is in cortical
bone, so the brain field falls below 0.2 and the entire beam renders blue:
correct, but unreadable as a beam plot, and not comparable with the GUI.
`save_acoustic_gui_BB` zeroes everything outside brain and renormalises to the
brain maximum, exactly as BabelBrain does, so the beam spans the full scale.
Use the second to compare against the GUI, the first for the ROI contour and
the anatomy.

The comparison PDF's first row is `save_acoustic_gui_BB`, a port of
`_BabelBaseTx.UpdateAcResults`, so it is the same plot the BabelBrain GUI draws
and can be checked against it directly. It is **beam-aligned**: Z is depth from
the skin along the beam, X and Y are lateral offsets from the target, the dotted
lines are `MaterialMap` boundaries, and `+` is the target. The anatomical ortho
row below it is the same field in native T1 space. The two look nothing alike;
that is the convention, not a discrepancy.

---

## 6. Questions this document exists to answer

### The two angles are not interchangeable: watch `skl°`

`aim°` says how squarely the target is aimed at; `skl°` says how obliquely the
beam meets bone. PlanTUS filters on `aim°` only, so a vertex can look ideal there
and still be a poor acoustic path. Measured on sub-z002 hippocampus:

| vtx | `aim°` | `skl°` | derating |
|---|---|---|---|
| 15110 | 2.6 | **26.7** | 0.0413 |
| 26749 | 3.4 | 3.8 | 0.0478 |
| 27604 | 3.8 | 2.4 | 0.0856 |

`aim°` is nearly identical across all three while `skl°` spans 2–27°, and
**derating tracks `skl°`, not `aim°`**, oblique incidence on bone costs
transmission, as expected. Read `skl°` when comparing placements even though the
selector ignores it.

### Why PlanTUS choosing the point does not settle the acoustics

**PlanTUS does no acoustics.** It optimises geometry only: aim angle, distance,
and whether the axis (a line) crosses the ROI. What actually sets the focus
position is the depth request plus skull refraction, which BabelBrain computes.
The two disagreeing is expected; measuring that disagreement is the point of
step 5.

### The main lobe is the *largest* component, not the one holding the maximum

An earlier version of this document reported that the focus for sub-z002
vtx26749 was 23.2 mm off target. **That was wrong**, and the cause was a
one-line definition mismatch with BabelBrain.

`_BabelBaseTx.CalcVolumetricMetrics` thresholds the brain-restricted intensity
at −3 dB, labels the connected components, and takes the **largest** one. The
pipeline used to take the component **containing the maximum** instead. Usually
the same component; here it is not:

| sub-z002 vtx26749 | volume | centroid → target |
|---|---|---|
| **largest component** (BabelBrain, and now the pipeline) | **649 mm³** | **−0.8 mm** |
| component containing the maximum (old pipeline) | 51 mm³ | +23.2 mm |

The 51 mm³ blob is a reflection hotspot pressed against the **far** skull that
outpeaks the true lobe by a few percent. The actual focus is a 649 mm³ lobe
sitting on the target. This is visible directly in the beam-aligned figure
(`save_acoustic_gui_BB`): one long lobe through the crosshair, plus a small
separate red spot at the bottom of the frame.

Verified against the GUI on the same run: GUI `[1.1, 0.3, −0.7]` mm, pipeline
`[1.1, 0.3, −0.8]`. The volume row now warns explicitly when the maximum falls
outside the main lobe.

**The GUI metric is computed on the skull field, not the water field.** An
earlier note here claimed otherwise; `CalculateDistancesTarget` uses `_ISkull`,
with everything outside brain zeroed.

Corrected results:

| case | centroid → target | I at target | −3 dB lobe length | target inside? |
|---|---|---|---|---|
| sub-CM aMCC (CTX-500) | 0.8 mm | 0.98 | 14.3 mm | yes |
| **sub-z002 vtx26749** | **1.4 mm** | **0.79** | 45.9 mm | **yes** |
| sub-z002 vtx15110 | 26.6 mm | 0.48 | 91.1 mm | **NO** |

So vtx26749 is well aimed; its limitation is **axial selectivity**, a 45.9 mm
lobe, consistent with the DPX-500 calibration (55 mm axial FLHM at a 100 mm
setting), and flagged `(clipped)` because it runs into the far skull. vtx15110
genuinely misses: the lobe is 91 mm long, the target falls outside it, and the
target is driven at less than half the brain maximum.

**Getting the sign right requires care.** Depth is `(nz-1-index)*step` in the
acoustic arrays, because `TargetLocation` is stored proximal-first while `p_amp`
and `MaterialMap` are stored distal-first, hence the `iz_f = nz-1-iz` conversion
in `summarise_acoustic_BB`. The way to confirm the convention on any dataset is
the tissue order along the beam axis: it must read
skin → cortical → trabecular → cortical → brain → far skull → water. Reading the
arrays in raw index order gives the reverse and flips every sign.

### Why steering is needed at all

An annular array cannot move its focus mechanically. The geometry fixes the
natural focus (DPX-500: 144.9 mm from the exit plane; CTX-500: 52.4 mm), and the
only way to place it elsewhere is to phase the rings. `ZSteering` is not an extra
knob to tune. It *is* the encoding of the requested depth:

```
ZSteering = requested_depth − natural_focus + correction
          = 103.0 − 144.9 + 1.7  =  −40.2 mm       (sub-z002 vtx26749)
```

So "set it to the distance from the chosen point" is exactly what happens; the
negative number just says the focus is being pulled 40 mm nearer than the
geometry wants. For vtx26749 the steering works: the −3 dB lobe is centred
1.4 mm from the target. What a ~40 mm excursion on an f/2.34 array costs is
**axial length**, not position, a 45.9 mm lobe, and the skull elongates it
further. For vtx15110, at a 114 mm request, it costs both: 91 mm long and 26.6 mm
off.

Whether extra standoff helps is **not yet established**. It would reduce the
excursion (a 17 mm pad turns −41.9 mm into −24.9 mm for a 103 mm ROI, bounded by
the 120 mm hardware maximum), and a smaller excursion should shorten the −3 dB
span. That is now a directly testable prediction: rerun with `ADDITIONAL_OFFSET`
and compare **−3 dB lobe axial length**, which is the quantity that is actually
poor for vtx26749.

### Skull thickness is not in PlanTUS: we added it

PlanTUS produces seven per-vertex maps (two angles, two distances, avoidance,
ROI intersection, best-vertex marker) and **none is skull thickness**; the only
`thickness` in its code refers to the gel pad. So nothing before the acoustic
solve distinguished a 4 mm vault from a 42 mm skull base.

`utils.skull_path_mm()` now supplies it, ray-casting each scalp vertex to the
ROI through charm's own `final_tissues.nii.gz` (label 7 compact, 8 spongy). It
is a hard veto in `select_best_vtx` at `max_skull_mm = 20`, alongside
`max_skl_deg = 30` and the exclusion of vertices below the inferior extent of
brain. That last one because PlanTUS's avoidance mask covers eyes, ears and
vessels but not the jaw, and it passed a vertex 91 mm below its own target.

**It is a veto, not a score.** Across ten measured placements it separates the
catastrophic path (42 mm, 0.2 % of peak delivered) from the rest, but does not
rank the 4–10 mm band, where delivered intensity varies threefold with no
thickness difference.

### Targeting error alone does not express the criterion

A large structure can be well covered with the centroid far off, and a small one
poorly covered with the centroid close. sub-z002 cHipp right has a targeting
error of 3.4 mm and covers 11 % of its ROI at 0.46 relative exposure; sub-z004
cHipp right has 9.3 mm and reaches 0.95. Read the volumetric rows above
alongside it.

Note also that a well-centred focus still covers only part of a compact ROI when
the two differ in *shape*: the DPX-500's focus is a ~51 × 5 mm cylinder, so on
the Weizhen hippocampus (664 mm³, ceiling 100 %) a 2.1 mm targeting error still
yields 28 % coverage. That is the shape mismatch Murphy et al. warn about
(§3.3.1.3), not a placement fault.

### CEM43 and ΔT are both required, and can disagree

ITRUSST imposes ΔT < 2 °C **and** CEM43 < 0.25 min; satisfying one is not enough.
CEM43 weights temperature exponentially around 43 °C, so at 39 °C it stays tiny
however long the sonication. Measured on sub-z002 (200 s):

| vtx | ΔT brain | CEM43 brain | verdict |
|---|---|---|---|
| 15110 | **2.086 °C** | 0.0072 (35× margin) | **ΔT over the 2 °C guideline** |
| 26749 | 1.032 °C | 0.0019 (131× margin) | both satisfied |

So "CEM43 says safe" and "ΔT says marginal" can both be true of the same run.

⚠ When computing per-tissue temperature yourself, take `MaterialMap` from the
**thermal** h5. It is proximal-first and aligned with `TempEndFUS`; the copy in
the acoustic h5 is distal-first, and using it silently swaps brain for skull.

## See also

- `parameters.md`: sonication parameters the operator sets
- `../../bookkeeping/CLAUDE_TUSPreprocess.md`: metrics that are easy to misread
- `../../src/utils.py`: the implementations referenced above
