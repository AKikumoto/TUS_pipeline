# TUS Analysis: Overview

This directory contains scripts for TUS (Transcranial Ultrasound Stimulation) target planning and analysis.

[![TUS pipeline reference](notebook/z_references/pipeline_reference_card.png)](https://akikumoto.github.io/TUS_pipeline/notebook/z_references/pipeline_reference.html)

## Table of Contents

- [Analysis Pathways](#analysis-pathways)
- [Batch Processing, `src/` run scripts &nbsp; ⚠ UNDER TESTING](#batch-processing-src-run-scripts----under-testing)
- [Directory Structure](#directory-structure)
- [Masks](#masks)
- [Software Dependencies](#software-dependencies)
- [Resources](#resources)
- [Source and Local Modifications](#source-and-local-modifications)
- [Acknowledgements](#acknowledgements)
- [Contact](#contact)

---

## Analysis Pathways

The pipeline has multiple parallel pathways. Choose based on your site configuration (see `config/sites/`).

### Step 1: Segmentation

> [📋 Step 1 reference card](https://akikumoto.github.io/TUS_pipeline/notebook/z_references/step1_reference.html)

Two methods are available:

| Method | Notebook | Output | Use when |
|--------|----------|--------|----------|
| **SimNIBS** | `notebook/step01_segmentation_simnibs.ipynb` | `m2m_{sub_id}/final_tissues.nii.gz` | Standard T1 scan (preferred) |
| **SPM** *(optional)* | `src/z_dont_edit/TUS_segmentation_SPM.ipynb` | `c1–c6*.nii` tissue maps | When SimNIBS is unavailable, or when additional flexibility is needed (e.g. PETRA images for bone segmentation at 7T or with implants) |

SPM steps: N4 bias correction → `NewSegment` → labeling → RAS reorientation

SimNIBS steps (requires terminal):
```bash
fslorient -copysform2qform T1.nii.gz   # optional: fix sform/qform
charm [subid] T1.nii.gz
```

---

### Step 2: MNI Mask Generation

> [📋 Step 2 reference card](https://akikumoto.github.io/TUS_pipeline/notebook/z_references/step2_reference.html)

**Notebook:** `notebook/step02_prepare_masks.ipynb`

Generates target ROI masks in MNI space (`MNI152NLin2009cAsym`, 1 mm iso). Four independent method cells, run only the cell(s) needed.

| Cell | Method | Inputs | Examples |
|------|--------|--------|----------|
| **2a** | NeuroSynth z-map + bounding box | `masks/original/` z-map NIfTI | aMCC |
| **2b** | Web / nilearn atlas ROI by label name | Downloaded via nilearn at runtime | HO ACC/Insula; Juelich; BN atlas |
| **2c** | Existing file ROI reorient + resample | NIfTI in `masks/original/` | BNST, CeA, LC |
| **2d** | Coordinate sphere at MNI mm coords | MNI coordinates + radius | IFJ, FEF |

The QC cell (last) works for any output mask: verifies grid (193×229×193, 1 mm), prints voxel count, renders interactive viewer + tri-planar PNG.

**Step 2b atlas options** (`ATLAS` variable):
- `"HO_cort"` / `"HO_sub"`, Harvard-Oxford cortical / subcortical (nilearn)
- `"Juelich"`: Juelich cytoarchitectonic (nilearn)
- `"BN"`: Brainnetome 246-region atlas (local; `$NILEARN_DATA/bn/`)

All outputs land in `masks/standardized/`.

---

### Step 3: Inverse Registration (MNI → Native) + Target Coordinate

> [📋 Step 3 reference card](https://akikumoto.github.io/TUS_pipeline/notebook/z_references/step3_reference.html)

**Notebook:** `notebook/step03_inverse_registration.ipynb`

Warps any MNI-space mask into subject-native T1 space, then computes a target coordinate for TUS/TMS targeting. Covers Steps 3–5 of the overall pipeline.

#### Registration mode (`REGISTRATION_MODE`)

| Mode | When to use | Transform source |
|---|---|---|
| `"ants"` | No fmriprep; run ANTs from scratch | Computed here, saved to `ants_transforms/` |
| `"fmriprep"` | fmriprep already run; reuse its warp | `.h5` file from `fmriprep/sub-*/anat/` |

**ANTs-mode options:**

| Parameter | Options | Default |
|---|---|---|
| `INTENSITY_NORM` | `"histogram_match"` / `"imath_normalize"` / `"none"` | `"histogram_match"` (3T) |
| `REGISTRATION_TYPE` | `"SyN"` / `"SyNCC"` | `"SyN"` |

#### Target coordinate mode (`TARGET_MODE`)

| Setting | Method |
|---|---|
| `"CoM"` | Centre of mass of the thresholded native mask (`compute_com_native`) |
| `"peak_func"` | Peak voxel of a functional map within the native mask (`compute_peak_native`) |
| `"skip"` | No coordinate; output native mask only |

**Inputs:**
- Site YAML (`config/sites/`)
- Subject native T1 NIfTI (auto-located via site config)
- MNI-space mask (`masks/standardized/`), must be MNI152NLin2009cAsym 1 mm
- *fmriprep mode only*: `*_from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5`
- *peak_func mode only*: functional contrast map in MNI space

**Outputs:**
- `<sub_dir>/<sub_id>_<MASK_LABEL>_mask_native.nii.gz`
- `<sub_dir>/<sub_id>_<FUNC_MAP_LABEL>_native.nii.gz` *(peak_func only)*
- `<sub_dir>/figures/<sub_id>_<MASK_LABEL>_native_overlay.png`
- `<sub_dir>/figures/<sub_id>_MNI2native_regcheck.png` *(ANTs mode only)*

---

### Step 4: Optimizing Target Specification

> [📋 Step 4 reference card](https://akikumoto.github.io/TUS_pipeline/notebook/z_references/step4_reference.html)

**Notebook:** `notebook/step04_planTUS.ipynb`  
**Script:** `src/run_planTUS.py`

Uses the SimNIBS head mesh to find the optimal transducer placement for a given target ROI, accounting for skull geometry, beam angle, and avoidance regions. All transducer parameters are read from `config/transducers/` YAML; all paths from the site YAML.

Run via the notebook, or from the command line:

```bash
# simnibs_python = Python interpreter bundled with SimNIBS
# (set simnibs_python in your site YAML, e.g. .../SimNIBS-4.5/simnibs_env/bin/python)
# When running inside the mri conda env with SimNIBS pip-installed, use python directly.
python src/run_planTUS.py \
    --site   config/sites/site_RIKEN_AK.yaml \
    --sub    sub-S04 \
    --target aMCC_NeuroSynth112 \
    --side   _R
```

- Inspect outputs in Workbench (`scene.scene`): transducer angle, skull distance, avoidance maps
- `write_brainsight_txt()` exports Brainsight `.txt` with entry + focus coordinates for neuronavigation
- *Requires SimNIBS segmentation from Step 1*

---

### Step 5: Acoustic & Thermal Simulation (BabelBrain)

**Tool:** [BabelBrain](https://proteusmrighifu.github.io/BabelBrain/) (standalone GUI application)

**Notebook:** `notebook/step05_babelbrain.ipynb`, batch mode (no GUI). Runs domain generation (5a), acoustic simulation (5b), and thermal simulation (5c) via BabelBrain Python API.

**Install:** Download from [GitHub Releases](https://github.com/ProteusMRIgHIFU/BabelBrain/releases)
- macOS ARM64 (M1/M2/M3) or Intel X64, pick the correct DMG for your hardware
- No Python installation required (standalone app)
- Open the DMG → double-click the package installer → authorize in macOS Security settings if prompted

**Requirements:**
- GPU with Metal (macOS), OpenCL, or CUDA support
- Apple Silicon (M1+, 16 GB+ RAM) is recommended
- SimNIBS ≥ 4.0 segmentation output (`m2m_{sub_id}/`) from Step 1
- Brainsight ≥ 2.5.3 or 3DSlicer trajectory (from Step 4 output `*_brainsight.txt`)

**Inputs:**
- `m2m_{sub_id}/`: SimNIBS head mesh (from Step 1)
- Brainsight trajectory `.txt` (from Step 4), or load trajectory directly in Brainsight ≥ 2.5.3 which can call BabelBrain directly

**Outputs:**
- `pressure_*.nii.gz`: acoustic pressure field in subject space
- Thermal maps, temperature rise estimates: `*-ThermalField_{stim}_AllCombinations.h5`
  and `*-ThermalField_{stim}_Summary.csv`, where `{stim}` is the stimulation YAML's
  name without `stimulation_`, so each protocol keeps its own files

**Running:**
1. Open BabelBrain from Applications (macOS) or Start Menu (Windows)
2. Load the SimNIBS `m2m_{sub_id}/` output directory
3. Import the Brainsight trajectory (or use the Brainsight ≥ 2.5.3 direct integration)
4. Select transducer model and exposure parameters (see `config/transducers/` for lab specs)
5. Run simulation; results are saved to the output directory

**Alternative tools:**

| Tool | Acoustic | Thermal | Notes |
|------|----------|---------|-------|
| **BabelBrain** | Yes | Yes | Standalone GUI; Apple Silicon recommended |
| **Brainsight** | Yes | Yes | Integrated with neuronavigation (uses BabelBrain internally since v2.5.3) |
| **kWave** (MATLAB) | Yes | - | MATLAB-based, more flexible scripting |

BabelBrain is the primary tool for Step 5 in this pipeline.

---

## Batch Processing: `src/` run scripts &nbsp; ⚠ UNDER TESTING

Steps 1, 3, 4 and 5 can be run non-interactively from the command line using the run scripts in `src/`. These are intended for multi-subject batch jobs and automated pipelines. All scripts use the same `--site` YAML and share a common CLI structure.

> **Requires** the `mri` conda environment (`conda activate mri`) and SimNIBS 4.6+ installed in it.

| Script | Step | Description |
|--------|------|-------------|
| `src/run_prepall.py` | 1 + 3 + 4 + 5 | Master orchestrator, runs any combination of steps in sequence for one or more subjects and targets |
| `src/run_seg.py` | 1 | SimNIBS `charm` segmentation (single subject) |
| `src/run_reg.py` | 3 | ANTs inverse registration: MNI mask → native space |
| `src/run_com.py` | 4a | Centre-of-Mass targeting + BrainSight `.txt` export |
| `src/run_planTUS.py` | 4b | PlanTUS automated transducer placement |
| `src/run_sweep.py` | 5 | Solves a shortlist of candidate vertices and ranks them (`--n-shortlist`, `--sep-mm`, `--top-pct`, `--seed-vtx`) |
| `src/run_babelbrain.py` | 5 | BabelBrain acoustic and thermal simulation for one vertex (`--vtx`, `--ppw`, `--z-beyond`, `--skip-thermal`) |

> **`run_prepall.py`'s `--steps`** accepts `seg`, `reg`, `com`, `plantus`, `sweep` and
> `babel`. `sweep` and `babel` are refused in one run: a person chooses the vertex between
> them ([Choosing a placement](#choosing-a-placement-sweep-judge-then-thermal)). A failed
> step skips that target's later steps, and the exit code is 1 when any step failed.

### With Claude Code: the `tus-prepare` skill

The package carries a Claude Code skill,
[.claude/skills/tus-prepare/SKILL.md](.claude/skills/tus-prepare/SKILL.md), that runs the
scripts below in order for an experiment's pipeline YAML. Open Claude Code in this folder
and type `/tus-prepare`. Each run reads the outputs on disk and does the next stage: the
site YAML on a new machine, the T1s, then seg, reg and sweep under nohup, then the thermal
simulation for the vertices a person chose, then the adopted-placement tables. It stops
for the vertex choice and for every hardware fact, and it never judges whether a value is
safe.

### Quick start: single subject

```bash
conda activate mri
cd scripts/TUS

# Full pipeline (seg + reg + plantus) for one subject:
python src/run_prepall.py \
    --site       config/sites/site_RIKEN_AK.yaml \
    --mask       masks/standardized/aMCC_NeuroSynth112_mask_MNI.nii.gz \
    --mask-label aMCC_NeuroSynth112 \
    --subjects   sub-S04 \
    --steps      seg,reg,plantus

# Alternatively, run individual steps:
python src/run_seg.py    --site config/sites/site_RIKEN_AK.yaml --sub sub-S04
python src/run_reg.py    --site config/sites/site_RIKEN_AK.yaml --sub sub-S04 \
                         --mask masks/standardized/aMCC_NeuroSynth112_mask_MNI.nii.gz \
                         --mask-label aMCC_NeuroSynth112
python src/run_com.py    --site config/sites/site_RIKEN_AK.yaml --sub sub-S04 \
                         --mask-label aMCC_NeuroSynth112
python src/run_planTUS.py --site config/sites/site_RIKEN_AK.yaml --sub sub-S04 \
                          --target aMCC_NeuroSynth112 --side _R
```

### Multi-subject batch: pipeline YAML (recommended)

Copy [config/template_pipeline.yaml](config/template_pipeline.yaml) into your project, for
example as `analysis/configs/pipeline_TUS.yaml`, never into this package: it names your
subjects, and this package is public. The full format is in the docstring of
`src/run_prepall.py`. Paths are absolute (`~` allowed) or relative to the YAML's own folder;
`sub_list_dir` is relative to the site YAML's `data_root` and replaces the site YAML's value.

```yaml
site:           ~/TUS_pipeline/config/sites/site_RIKEN_AK.yaml
sub_list_dir:   SUB_LIST_PREP
mask:           ~/TUS_pipeline/masks/standardized/aMCC_NeuroSynth112_mask_MNI.nii.gz
mask_label:     aMCC_NeuroSynth112
target_side:    _R
steps:          [seg, reg, com, plantus]
subjects:
  - sub_id: sub-01
  - sub_id: sub-02
  - sub_id: sub-03
```

```bash
python src/run_prepall.py --config pipeline.yaml [--dry-run]
```

Use `--dry-run` to preview the commands that would be run without executing them.

For several targets in one run, replace `mask` and `mask_label` with a `targets`
list, one `mask` and `mask_label` per entry (format in the docstring), or give
several `--mask` and as many `--mask-label` on the command line, in the same
order. `seg` runs once per subject; the other steps run once per target. An entry of the
list may carry its own `additional_offset` (the gel pad), which replaces the subject's for
that target.

Every run script also takes `--sub-list-dir`, and each notebook has `SUB_LIST_DIR` in its
Settings cell. When you run a script or a notebook on its own, give it the same folder as
the pipeline YAML. Otherwise it uses the site YAML's `sub_list_dir`.

### Choosing a placement: sweep, judge, then thermal

`run_planTUS.py` ranks scalp vertices on surface metrics (beam-ROI overlap, aim
angle, distance, skin-skull angle). That ranking does not predict which vertex
focuses on the target: across the UMD targets the top-ranked candidate was the
one adopted in 6 of 22 target-sides. Treat it as a shortlist and measure the
shortlist with the acoustic solve:

```bash
# 1. Acoustic solve (5a + 5b, no thermal) for the 3 best-separated candidates,
#    about 5 min each. Builds the step-4 scene itself if the target has only
#    been registered. --stratify adds candidates when the shortlist misses.
python src/run_sweep.py \
    --site     config/sites/site_UMD_AK.yaml \
    --sub      sub-01 \
    --target   dCaExec_Tziortzi2014 \
    --side     _L \
    --stim     config/stimulation/stimulation_EC_Caudate_online_OsadaTMSTUS.yaml \
    --stratify 7

# 2. Read the table, pick one vertex per target (see below), then run the
#    thermal stage on that vertex only.
python src/run_babelbrain.py \
    --site   config/sites/site_UMD_AK.yaml \
    --sub    sub-01 \
    --target dCaExec_Tziortzi2014 \
    --side   _L \
    --stim   config/stimulation/stimulation_EC_Caudate_online_OsadaTMSTUS.yaml \
    --vtx    4583
```

Judge candidates on **efficiency and `I@target` together**, not on targeting
error. `efficiency` is the share of the achievable overlap the lobe reaches
(`coverage / ceiling`; a single-element focus cannot cover a structure larger
than itself, so coverage is read against that ceiling). `I@target` is the
intensity at the aimed point as a fraction of the brain peak. `inside` /
`OUTSIDE` refers to that one point: when the lobe is small (200-300 mm³ at
60 mm depth) a 2 mm lateral miss flips it, and a candidate reading `OUTSIDE`
with high efficiency holds more of the target than one reading `inside` with
low efficiency. `csf` is the share of the lobe in ventricle by the charm
segmentation, wasted rather than harmful; it explains low coverage next to the
frontal horn. The `entry` line gives path length and the direction the beam
comes from (elevation above the target; azimuth 0 = lateral, +90 = anterior,
−90 = posterior; `ipsi`/`contra`), so approaches can be compared across
subjects.

`--stratify N` is the fallback for targets where every shortlisted candidate
misses. The overlap ranking runs *inverse* to delivery on some targets, because a
long chord through the ROI implies an oblique approach that costs more at the
skull than it gains; three targets so far were reached only this way. It samples
N vertices across the whole overlap range, the furthest-apart vertex per
quantile bin with contralateral entries excluded, and solves those too.

Every sweep writes `VERTICES_EXPLORED.md` into the PlanTUS target folder with
one row per solved vertex, so the record survives deleting the BabelBrain output
of the candidates not adopted. Two defaults differ on purpose: `run_planTUS.py`
keeps `--top-pct 0.8`, `run_sweep.py` uses 0.5, because a sweep exists to
compare alternatives and a tight pool leaves none.

---

### Recording the adopted placements across subjects

```bash
python src/run_status.py --site config/sites/site_UMD_AK.yaml --sub-list subjects.txt
```

writes `ADOPTED_PLACEMENTS.md` (by subject), `ADOPTED_BY_TARGET.md` (by target,
subjects side by side), `.csv` and `.pdf` (the tables with each placement's
acoustic and thermal QC figures) into the data directory: one row per
placement and protocol that has a thermal summary, with the TPO focal depth and pad, the
entry geometry, the focus metrics, the standoff check, the protocol, the
derating and free-field ISPPA, the temperature rise and the MI. Every value is
read from the pipeline's own outputs, so the table is a record, not a
recomputation; regenerate it after any re-run.

## Directory Structure

```
.                          ← repo root on GitHub (AKikumoto/TUS_pipeline);
                             resources/TUS/scripts/ inside LabWiki
  .claude/skills/tus-prepare/  ← the Claude Code skill that runs the src/ scripts in order
  config/                  ← site, transducer and protocol configuration (YAML)
    template_pipeline.yaml ← the pipeline YAML to copy into a project
    sites/                 ← site_RIKEN_AK.yaml, site_UMD_AK.yaml, template_site.yaml
                             (naming: site_[SITE]_[STATION].yaml)
    transducers/           ← CTX500_RIKEN.yaml, DPX500_UMD.yaml
                             (naming: MODEL_SITE.yaml)
    stimulation/           ← one YAML per protocol; drive only, no device facts
    basics/                ← simulation_metrics.md and other reference notes
    conda/, HPC/           ← environment files
  notebook/                ← the analysis notebooks, one per step
    step01_segmentation_simnibs.ipynb   ← SimNIBS charm segmentation
    step02_prepare_masks.ipynb          ← MNI mask generation: 2a NeuroSynth,
                                          2b atlas, 2c file ROI, 2d sphere
    step03_inverse_registration.ipynb   ← MNI→native registration + target coordinate
    step04_planTUS.ipynb                ← PlanTUS transducer placement
    step05_babelbrain.ipynb             ← acoustic & thermal simulation (batch, no GUI)
    z_references/                       ← the reference cards, built by CI
  src/                     ← shared functions and the batch runners
    utils.py                            ← every function the steps call
    run_seg.py, run_reg.py, run_com.py, run_planTUS.py,
    run_sweep.py, run_babelbrain.py, run_prepall.py
    LIST_functions.md                   ← every function in utils.py, by step
    LIST_modifications.md               ← patch log for third-party tools
    z_dont_edit/                        ← superseded notebooks and scripts, kept
                                          for reference; Example(Xin)/ lives here.
                                          Not published: they hold participant data
  PlanTUS/                 ← PlanTUS wrapper and its resources
  masks/original/          ← target ROI masks in original/subject space
  masks/standardized/      ← target ROI masks in MNI standard space
  z_babelbrain_src/        ← BabelBrain reference material and GUI captures
```

---

## Masks

Standard space is `MNI152NLin2009cAsym`, 1 mm (193×229×193). The current list, with QC images,
sources and citations, is in
[masks/standardized/LIST_mask_standard.md](masks/standardized/LIST_mask_standard.md): that
file is generated alongside the masks and is the one to trust.

Naming is `{structure}_{source}[_{parameter}]_mask_MNI.nii.gz`. **Masks are bilateral and carry
no side in the name**: `run_reg.py` splits them into `_L`/`_R` in native space and everything
downstream selects with `--side`.

Set `atlases_dir` in your site config YAML to point at your own copy of the MNI atlases; they
are not tracked here.

### Citations

Examples only, any NIfTI in `MNI152NLin2009cAsym` 1 mm space can be added to
`masks/standardized/` and used as a target. Cite as applicable.

| Mask | Source | Citation |
|---|---|---|
| `aMCC_NeuroSynth112` | NeuroSynth v5 | Yarkoni et al. (2011) *Nature Methods* 8:665–670, [doi:10.1038/nmeth.1635](https://doi.org/10.1038/nmeth.1635) |
| `A13_BN`, `dIa_BN`, `dId_BN`, `dIg_BN`, `vIa_BN`, `rHipp_BN`, `cHipp_BN`, `hipp_BN` | Brainnetome atlas | Fan et al. (2016) *Cerebral Cortex* 26(8):3508–3526, [doi:10.1093/cercor/bhw157](https://doi.org/10.1093/cercor/bhw157) |
| `CeA_CIT168` | CIT168 | Pauli et al. (2018) *Scientific Data* 5:180063, [doi:10.1038/sdata.2018.63](https://doi.org/10.1038/sdata.2018.63) |
| `BNST_Blackford2022` | Blackford BNST | Avery et al. (2022) *Neuropsychopharmacology* |
| `LC_Dahl2022` | LC mask (Dahl) | Dahl et al. (2022) *Nature Human Behaviour*, [osf.io/at3ym](https://osf.io/at3ym/) |
| `IFJ_sphere8`, `FEF_sphere8` | Coordinate sphere (8 mm) | custom, no citation required |
| `alEC_Maass2015`, `pmEC_Maass2015` | Entorhinal subdivision | Maass et al. (2015) *eLife* 4:e06426, [doi:10.7554/eLife.06426](https://doi.org/10.7554/eLife.06426) |
| `aHipp_Weizhen_p01`, `aHipp_Weizhen_p05` | Anterior hippocampus | left-only; `p05` is the larger threshold |

---

## Software Dependencies

### Python environment

```bash
conda activate mri
```

Each machine has its own yml, which lists the full package set:

| Machine | yml |
|---|---|
| Mac (Apple silicon) | [config/conda/mri_environment_arm64.yml](config/conda/mri_environment_arm64.yml) |
| Brown Oscar | [config/HPC/Brown_Oscar/mri_environment_oscar.yml](config/HPC/Brown_Oscar/mri_environment_oscar.yml) |
| Windows | [config/conda/mri_environment_windows.yml](config/conda/mri_environment_windows.yml) |

| Package | Used in |
|---------|---------|
| `nibabel` | All steps, NIfTI I/O |
| `nilearn` | Steps 2–3, atlas fetching, image resampling |
| `antspy` | Step 3, SyN registration |
| `numpy`, `scipy` | All steps |
| `matplotlib` | QA plots |
| `pyyaml` | Config loading |
| `nipype` | Step 1 (SPM path), SPM12 interface |
| `pandas` | Step 4 (CoM output CSV) |
| `trimesh`, `vtk` | Step 4 (PlanTUS) |

### External tools

| Tool | Version | Used in | Notes |
|------|---------|---------|-------|
| **SimNIBS** | ≥ 4.0 | Step 1 (SimNIBS path), Step 4 (PlanTUS) | Provides `charm` binary and Python env |
| **FSL** | ≥ 6.0 | Step 1, `fslorient` | Optional: qform/sform fix |
| **SPM12** | r7771+ | Step 1 (SPM path) | Via MATLAB or standalone MCR |
| **Connectome Workbench** | ≥ 1.5 | Step 4 (PlanTUS), scene inspection | |
| **FreeSurfer** | ≥ 8.0 | Step 4 (PlanTUS) | |
| **Brainsight** | ≥ 2.5.3 | Step 4 (trajectory export), Step 5 (neuronavigation + calls BabelBrain) | |
| **BabelBrain** | ≥ 0.3.4 | Step 5, acoustic &amp; thermal simulation | **Batch/notebook mode:** git clone (see below). GUI mode: download from [GitHub Releases](https://github.com/ProteusMRIgHIFU/BabelBrain/releases) |
| **kWave** (MATLAB) | ≥ 1.4 | Step 5 (alternative) | MATLAB R2020b+ |

> **BabelBrain, batch mode setup (macOS, `mri` conda env)**
>
> `step05_babelbrain.ipynb` uses BabelBrain via its Python API (no GUI). This requires the **git clone**, not the `.app` bundle:
>
> ```bash
> git clone https://github.com/ProteusMRIgHIFU/BabelBrain.git ~/BabelBrain
> ```
>
> `mri_environment_arm64.yml` already lists BabelBrain's pip packages. An older `mri` that lacks these three adds them with:
>
> ```bash
> pip install SimpleITK linetimer==0.1.5 pwlf==2.5.2
> ```
>
> Reference: `~/BabelBrain/environment_mac_arm64-311.yml` lists the full BabelBrain dependency set.
> Set `babelbrain_dir: "~/BabelBrain"` in your site YAML (already set for UMD/RIKEN). The notebook adds this path to `sys.path` automatically at import time.

---

## Resources

| Tool / Method | Citation |
|---------------|----------|
| **Murphy et al. (2025), ITRUSST TUS guide** | Murphy KR et al. (2025). *A practical guide to transcranial ultrasonic stimulation, State of the art and opportunities.* Clin Neurophysiol 171:192–226. [doi:10.1016/j.clinph.2025.01.004](https://doi.org/10.1016/j.clinph.2025.01.004) |
| **SimNIBS / charm** | Thielscher A, Antunes A, Saturnino GB. (2015). *Field modeling for transcranial magnetic stimulation.* EMBC. [doi:10.1109/EMBC.2015.7318340](https://doi.org/10.1109/EMBC.2015.7318340) |
| **ANTs SyN registration** | Avants BB et al. (2011). *A reproducible evaluation of ANTs similarity metric performance.* NeuroImage. [doi:10.1016/j.neuroimage.2010.09.025](https://doi.org/10.1016/j.neuroimage.2010.09.025) |
| **PlanTUS** | Lueckel M et al. (2023). *PlanTUS: A software for patient-specific transcranial ultrasound stimulation planning.* [doi:10.1101/2023.04.05.535674](https://doi.org/10.1101/2023.04.05.535674) |
| **kWave** | Treeby BE, Cox BT. (2010). *k-Wave: MATLAB toolbox for the simulation of acoustic wave fields.* J Acoust Soc Am. [doi:10.1121/1.3360308](https://doi.org/10.1121/1.3360308) |

**Local resources:**
- `resources/TUS/manuals/`: hardware test reports (PDF)
- `resources/TUS/manuscripts/`: reference papers
- `src/z_dont_edit/Example(Xin)/`: reference implementation

---

## Source and Local Modifications

| File | Contents |
|------|----------|
| [src/LIST_functions.md](src/LIST_functions.md) | Every function in `src/utils.py`, grouped by pipeline step |
| [src/LIST_modifications.md](src/LIST_modifications.md) | Patch log for PlanTUS, SimNIBS and wb_view |

> Patches are not upstreamed. Re-apply after any upstream update.

### Portability Rule

**All fixes and workarounds must be portable**, i.e., they must work for any user who sets up the environment from scratch using their machine's yml (see [Python environment](#python-environment)).

- Do **not** edit files under `site-packages/`, `~/miniforge3/`, or any path outside this repository
- Third-party package bugs must be addressed via runtime patches in `src/utils.py` or a dedicated module in `src/`
- Document every patch in [src/LIST_modifications.md](src/LIST_modifications.md) with: affected package, version, symptom, and fix

---

## Acknowledgements

This pipeline was developed with contributions from the following collaborators.

| Name | Affiliation | Contribution | Links |
|------|------------|--------------|-------|
| **Takahiro Osada** | Associate Professor, Dept. of Neurophysiology, Juntendo University, Tokyo, Japan | TUS pipeline development and methodology | [ORCID 0000-0002-3743-3200](https://orcid.org/0000-0002-3743-3200) |
| **Zonghao Xin** | JSPS Postdoctoral Fellow, RIKEN CBS, Japan | Reference implementation (`src/z_dont_edit/Example(Xin)/`) | - |

---

## Contact

**Atsushi Kikumoto**  
Assistant Professor, Cognitive Flexibility Dynamics Lab, Department of Psychology, University of Maryland, College Park

- Email: akikumot [at] umd.edu
- Lab: [cfd-lab.com](https://www.cfd-lab.com/home)
- GitHub: [AKikumoto](https://github.com/AKikumoto)
- ORCID: [0000-0002-2179-2700](https://orcid.org/0000-0002-2179-2700)

For bug reports, please open a [GitHub Issue](https://github.com/AKikumoto/TUS_pipeline/issues).
