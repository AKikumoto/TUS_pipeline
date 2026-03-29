# TUS Pipeline — Open Tasks

Pipeline overview and step details are in `README_TUS.md` and the step reference cards.

---

## 1. ROI union — validate on real data

`step03_inverse_registration.ipynb` has ROI union support (`ROI_UNION_FILE`) but it is **untested**.
Run on an existing subject, verify the combined native mask visually, and remove the ⚠️ warning in the notebook and README.

---

## 2. Pipeline decision table — confirm UMD and Iowa

| Site | Segmentation | Targeting | Acoustic sim | Thermal sim |
|------|-------------|-----------|-------------|------------|
| RIKEN | SimNIBS | PlanTUS | BabelBrain | BabelBrain |
| UMD | **TBD** | **TBD** | **TBD** | **TBD** |
| Brown (Oscar) | SimNIBS | PlanTUS | BabelBrain | BabelBrain |
| Iowa | **TBD** | **TBD** | **TBD** | **TBD** |

Confirm choices with collaborators; update `config/sites/` YAMLs accordingly.

---

## 3. Transducer calibration files (Brainbox)

Request calibration Excel from Brainbox for:
- CTX-500 SN056 (RIKEN)
- DPX-500 SN048 (UMD)

Fill in `babelbrain_calibration` field in the respective `config/transducers/` YAMLs.

---

## 4. Oscar data paths

`atlases_dir` is still TBD in `config/HPC/Brown_Oscar/oscar_setup_guide.md`. Fill in once confirmed on Oscar.

---

## 5. `run_pipeline.py` — end-to-end CLI runner

Create `src/run_pipeline.py` to chain Steps 01 → 03 → 04 for a single subject (Step 02 masks are assumed pre-built):

```bash
python src/run_pipeline.py \
    --site   config/sites/site_RIKEN_AK.yaml \
    --sub    sub-NS \
    --t1     /path/to/sub-NS_T1w.nii.gz \
    --target aMCC_NeuroSynthTopic112
```

Proposed logic:
1. **Step 01** — `src/step01_segmentation_simnibs.py` (CLI, exists)
2. **Step 03** — `src/step3_inverse_registration.py` (importable, exists)
3. **Step 04** — `src/step04_plantus_run.py` (CLI, exists)

---

## 6. Standalone repository

Move `scripts/TUS/` to an independent GitHub repo and sync with LabWiki as a git submodule or subtree.

**Rationale:** Pipeline is shared across sites (RIKEN, UMD, Brown, Iowa); should be versioned independently of the lab wiki.

**Files to exclude from pipeline repo:**
- `config/sites/site_*.yaml` — site-specific
- `masks/original/`, `masks/standardized/` — data, not code
- `z_old_scripts/` — legacy

---

## 7. BabelBrain — first simulation run

**Status:**
- ✅ BabelBrain installed (`/Applications/BabelBrain.app`)
- ✅ `site_RIKEN_AK.yaml`: `acoustic_sim: BabelBrain`, `babelbrain_dir` set
- ✅ Oscar env setup guide created (`config/HPC/Brown_Oscar/`)
- ❌ First simulation not yet attempted

**Next step:** Load an existing `m2m_{sub_id}/` + Brainsight trajectory (`.txt` from Step 4), run acoustic sim locally, verify `pressure_*.nii.gz` output.

**Notes:**
- SimNIBS must be installed (BabelBrain calls it internally)
- Brainsight ≥ 2.5.3 can call BabelBrain directly
- Apple Silicon (M1+, 16 GB+ RAM) recommended
