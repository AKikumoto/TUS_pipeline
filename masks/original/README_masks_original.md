# masks/original/ — Inventory

Target ROI masks in MNI space used by the TUS pipeline (Steps 2–4).

> **Not tracked in Git** — files are too large for GitHub (some >100 MB).  
> Storage: Dropbox — `w_LABWORKS/PI/LabWiki/scripts/TUS/masks/original/`  
> Referenced by: `config/sites/` → used in `run/step04_planTUS.ipynb`

---

## Top-level masks

| File | Size | Target | Source |
|------|------|--------|--------|
| `monitoring_association-test_z_FDR_0.01.nii.gz` | 0.1 MB | aMCC (anterior midcingulate cortex) — Neurosynth "monitoring" meta-analysis, FDR q<0.01 | Neurosynth v5 |
| `v5-topics-400_112_error_errors_monitoring_association-test_z_FDR_0.01.nii.gz` | 0.1 MB | aMCC — Neurosynth topic 112 ("error/errors/monitoring"), association test FDR q<0.01 | Neurosynth v5 topics-400 |
| `Dahl_LCmax_prob_MNI05.nii` | 462 MB | Locus coeruleus — probability map at MNI 0.5 mm resolution (uncompressed) | Dahl et al. 2022 |
| `Dahl_LCmax_prob_MNI05.nii.gz` | 0.5 MB | Same as above (compressed) | Dahl et al. 2022 |
| `Neuromorphometrics_BrainStem_mask_1mm.nii` | 2.1 MB | Brainstem mask at 1 mm MNI | Neuromorphometrics |
| `Blackford_BNST_3T_ANTS_081216_2mm_6467to0_noCSF_bin_20220923.nii.gz` | — | BNST (bed nucleus of the stria terminalis), 2 mm MNI | Blackford lab |
| `CIT168_both_1mm_MNI_partial_vol_matched_2mmResize_BilatCeA.nii.gz` | — | Central amygdala (CeA), bilateral, 2 mm MNI | CIT168 atlas |

---

## Dahl2022_osf/

LC meta-mask package from Dahl et al. 2022 (downloaded from OSF).  
Source PDF: `Dahl2022_osf/source_infomation.pdf`

### LC masks (`Locus coeruleus meta mask [MNI 152 linear space; 0.5 mm resolution]/`)

| File | Size | Description |
|------|------|-------------|
| `LCmetaMask_MNI05_s01f_plus50.nii.gz` | 0.8 MB | Bilateral LC meta-mask |
| `LCmetaMask_left_MNI05_s01f_plus50.nii.gz` | 0.1 MB | Left LC |
| `LCmetaMask_right_MNI05_s01f_plus50.nii.gz` | 0.1 MB | Right LC |
| `CentralReferenceMask_MNI05.nii.gz` | 0.8 MB | Central reference mask |

### Reference brains (`Reference brains [MNI 152 linear space; 0.5 mm resolution]/`)

| File | Size | Description |
|------|------|-------------|
| `avg152T1_rs_0.5mm.nii.gz` | 132 MB | MNI152 linear average T1, 0.5 mm |
| `MPRAGE_Template_MNI05.nii.gz` | 118 MB | MPRAGE template, 0.5 mm MNI |

### Transformations (`Transformations MNI152 2009b <=> MNI152 lin/`)

| File | Size | Description |
|------|------|-------------|
| `mni_icbm152_t1_tal_nlin_asym_09b___MNIavg152T1_lin_05mm_0GenericAffine.mat` | <1 MB | Affine transform: MNI 2009b ↔ MNI152 linear |
| `mni_icbm152_t1_tal_nlin_asym_09b___MNIavg152T1_lin_05mm_1InverseWarp.nii.gz` | 978 MB | Inverse warp field |
| `mni_icbm152_t1_tal_nlin_asym_09b___MNIavg152T1_lin_05mm_1Warp.nii.gz` | 977 MB | Forward warp field |

---

## metaMask_Dahl2022/

Same LC masks as `Dahl2022_osf/` in both `.nii` (uncompressed) and `.nii.gz` formats.

| File | Size | Description |
|------|------|-------------|
| `LCmetaMask_MNI05_s01f_plus50.nii` | 462 MB | Bilateral LC meta-mask (uncompressed) |
| `LCmetaMask_MNI05_s01f_plus50.nii.gz` | 0.8 MB | Bilateral LC meta-mask (compressed) |
| `LCmetaMask_left_MNI05_s01f_plus50.nii` | 462 MB | Left LC (uncompressed) |
| `LCmetaMask_left_MNI05_s01f_plus50.nii.gz` | 0.1 MB | Left LC (compressed) |
| `LCmetaMask_right_MNI05_s01f_plus50.nii` | 58 MB | Right LC (uncompressed) |
| `LCmetaMask_right_MNI05_s01f_plus50.nii.gz` | 0.1 MB | Right LC (compressed) |
| `CentralReferenceMask_MNI05.nii` | 462 MB | Central reference mask (uncompressed) |
| `CentralReferenceMask_MNI05.nii.gz` | 0.8 MB | Central reference mask (compressed) |

---

## References

| Atlas / Dataset | Citation |
|-----------------|---------|
| **Dahl et al. 2022** | Dahl MJ et al. (2022). Noradrenergic modulation of rhythmic neural activity shapes selective attention. *Nature Human Behaviour*. [OSF: osf.io/at3ym](https://osf.io/at3ym/) |
| **Neurosynth v5** | Yarkoni T et al. (2011). Large-scale automated synthesis of human functional neuroimaging data. *Nature Methods*. [neurosynth.org](https://neurosynth.org/) |
| **CIT168** | Pauli WM et al. (2018). A high-resolution probabilistic in vivo atlas of human subcortical brain nuclei. *Scientific Data*. |
| **Neuromorphometrics** | [neuromorphometrics.com](http://www.neuromorphometrics.com/) |
