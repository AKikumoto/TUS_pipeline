# src/utils.py: Function Reference

All functions are in `src/utils.py`. Called from the notebooks in `notebook/`
and from the batch runners in `src/`.

---

## Step 3: Registration & Target Coordinate

| Function | Description |
|---|---|
| `load_site_config(path)` | Load site YAML; resolve all path fields relative to the YAML location |
| `resolve_data_dir(cfg, sub_id)` | Resolve subject data directory from site config |
| `normalise_sub_id(raw)` | Normalise subject ID to `sub-XXX` format |
| `find_t1(data_dir, sub_id)` | Locate T1 NIfTI in subject directory (glob-based) |
| `ants_to_nib(img)` | Convert ANTsImage → nibabel Nifti1Image (preserves affine) |
| `apply_inverse_transform(...)` | Warp MNI mask to native space; supports both ANTs and fmriprep `.h5` transforms |
| `compute_com_native(mask, z_threshold)` | Centre-of-mass of the native mask in mm (RAS) |
| `compute_peak_native(func, mask, z_threshold)` | Peak voxel of a functional map within the native mask; returns `(peak_mm, peak_vox, peak_val)` |
| `visualize_mask_native(t1, mask, ...)` | Tri-planar PNG overlay of native mask on T1 |

---

## Step 4: PlanTUS

All functions below are called from `notebook/step04_planTUS.ipynb` and from
`src/run_planTUS.py`. The "cell" column refers to the notebook.

| Function | Used in cell | Description |
|----------|-------------|-------------|
| `setup_environment(cfg)` | Cell 3 | Extends `PATH` with FSL/Workbench/FreeSurfer bins; appends SimNIBS site-packages to `sys.path`; reads from site config |
| `transducer_params(tcfg)` | Cell 3 | Extracts PlanTUS-relevant parameters from transducer config dict |
| `run_plantus(...)` | Cell 3 | Full GUI workflow: calls `prepare_plantus_scene` → prints `select_best_vtx` suggestion → launches `wb_view` with `pynput` mouse listener → prompts `yes/no` per click → calls `run_plantus_placement` for confirmed vertices |
| `select_best_vtx(target_folder, max_angle, max_distance=None, min_distance=None, top_pct=0.9)` | (called by `run_plantus`; also for `run_pipeline`) | 2-stage selection: (1) keep all safe vertices with beam–ROI intersection ≥ `top_pct × max` (Stage 1); (2) among those, pick the vertex minimising normalised angle + distance (Stage 2). **Hard limits**: avoidance mask and distance bounds (`max_distance`, `min_distance`) are never relaxed; `max_distance`/`min_distance` are optional (pass `None` to skip). **Angle is advisory only**: if the best vertex exceeds `max_angle`, a `UserWarning` is issued but the vertex is still returned. Writes `best_vtx_marker_skin.func.gii` (5 mm radius sphere, value=100) as a GIFTI template clone for overlay in wb_view. Returns `(best_vtx_idx, metrics_dict, relax_level)` where `relax_level = 1` if angle was exceeded, else 0. |
| `run_plantus_placement(...)` | (called by `run_plantus`) | Runs `PlanTUS.prepare_acoustic_simulation` for one vertex; loads `skin_target_distances.npy` from the PlanTUS output directory |
| `get_vtx_coordinates(vtx_dir, target_folder, vtx_id)` | (called by `write_brainsight_for_vtx`) | Reads `skin.surf.gii` and `focus_position_matrix_*.txt` to return entry and target RAS coordinates |
| `write_brainsight_txt(...)` | (called by `write_brainsight_for_vtx`) | Writes a BrainSight-compatible `.txt` file (entry + focus rows with rotation matrix) from a 4×4 transducer matrix and RAS coordinates |
| `write_brainsight_for_vtx(...)` | Cell 4 | Convenience wrapper: finds the PlanTUS output folder, selects the **last-modified** `vtx*` directory, extracts coordinates, and calls `write_brainsight_txt`; warns if multiple vtx directories exist |

### vtx directory selection note

`write_brainsight_for_vtx` selects the vtx directory by **most recent modification time** (`st_mtime`). If `wb_view` was clicked multiple times and multiple `vtx*` directories exist, only the last one is exported; a warning is printed listing the count.

---

## Naming and placement resolution (shared by steps 3–5)

One placement has to mean the same thing to step 4c and to step 5, or the trajectory and the depth report come from different vertices. These are the functions that decide that, and nothing downstream should re-derive what they return.

| Function | Description |
|---|---|
| `mask_suffix(target_side)` | `_mask` / `_mask-L` / `_mask-R`. PlanTUS names its output folder and every file inside it from this stem, so it propagates into the scene files too |
| `stem_for(sub_id_full, target_name, target_side)` | `{sub}_{target}[-{L\|R}]`, the stem every downstream name starts from |
| `find_plantus_target_folder(m2m_dir, sub_id_full, target_name, target_side)` | The PlanTUS output folder for a target. Matches on the suffix only, so earlier naming schemes still resolve. `sys.exit()`s on no match or on more than one |
| `find_roi_mask(plantus_target_folder)` | Native-space ROI mask copied into the PlanTUS folder by step 4a |
| `resolve_vtx(target_folder, vtx=None)` | **The single rule for which placement is in use**: `None` → the newest `vtx*` folder, `N` → vertex `N`. Steps 4c and 5 both go through it, so trajectory and depth report cannot disagree. The canonical `*_target_coordinates_Brainsight_PlanTUS.txt` is a fixed-name copy of the most recent export and must never be read to infer the vertex |
| `read_depth_report(...)` | Parses the PlanTUS depth report into a dict |
| `focal_depth_mm(plantus_target_folder, vtx, tx_cfg=None)` | Focal depth the TPO is set to, **read** from `exit_plane_to_ROI_distance_mm` rather than recomputed, plus a verdict of `ok` / `below_calibrated` / `above_hardware` / `below_hardware`. Pass the raw transducer YAML (`cfg["transducer_cfg"]`), not `transducer_params()`, which drops the calibrated bounds |
| `list_plantus_vertices(target_folder, print_table=True)` | Every placement for one target, with the metrics `select_best_vtx` ranked on. `inter` is knife-edge — read `inter_near_mm`, the best value within 5 mm, before calling a vertex a miss |
| `fig_dir_for(sub_dir, target=None, stim=None)` | Figure directory: `figures/registration/`, `figures/{target}/` for acoustic, `figures/{target}/{stim}/` for thermal |

---

## Step 5: Acoustic & Thermal Simulation (BabelBrain)

Called from `notebook/step05_babelbrain.ipynb` and from `src/run_babelbrain.py`; `src/run_sweep.py` drives 5a and 5b once per shortlisted vertex. The order below is the order `run_babelbrain.py` runs them in.

### 5a — Domain generation

| Function | Description |
|---|---|
| `load_babelbrain_tx_yaml(bb_dir, tx_system)` | Loads BabelBrain's own `default.yaml` for the transducer, so ring diameters come from the tool rather than from a copy |
| `compute_z_steering_BB(plantus_target_folder, tx_cfg, additional_offset_mm=0, ...)` | Electronic steering offset, from the depth report of the **same** vertex the trajectory came from. Getting this from another vertex is what once moved a focus by 11 mm |
| `run_domain_BB(...)` | Tissue domain from the SimNIBS mesh plus the trajectory. Starts `CalculateMaskProcess` in a `spawn` child; returns the `*_BabelViscoInput.nii.gz` path |
| `patch_trimesh_compat_BB()` | Reattaches `remove_duplicate_faces` / `remove_degenerate_faces`, removed in trimesh 4 but still called by `BabelDatasetPreps.DoIntersect`. Idempotent; see `LIST_modifications.md` |
| `read_trajectory_id_BB(trajectory_file)` | The trajectory's own ID column, which is what the step-5 output prefix is built from |

### 5b — Acoustic simulation

| Function | Description |
|---|---|
| `run_acoustic_BB(...)` | FDTD solve plus the water reference run. For ANNULAR_ARRAY transducers BabelBrain does not `put()` the result path, so it is recovered by globbing after the process exits |
| `summarise_acoustic_BB(...)` | The metrics table, written to HTML. Read the **brain-only, outlier-resistant** rows: the whole-domain maximum sits in cortical bone for deep targets |
| `score_candidate(...)` | Spike-resistant focal metrics for one solve; what `run_sweep.py` ranks candidates on |
| `save_acoustic_gui_BB(...)` | A port of `_BabelBaseTx.UpdateAcResults`, so it is the plot the GUI draws. **Beam-aligned**, not anatomical |
| `save_acoustic_ortho_BB(...)` | The interactive viewer's ortho view as a static PNG, in native T1 space. Every default reproduces the viewer; `threshold`, `draw_cross`, `roi_color` and `roi_label` exist to differ at the call site without moving the default |
| `plot_acoustic_qc_BB(...)` | Anatomical QC on the native T1 with the ROI contour. Normalises to the whole-domain maximum, which is why a deep target can come out all blue |
| `view_acoustic_interactive_BB(...)` | nilearn HTML viewer. Notebook only; it cannot export its own view, which is what `save_acoustic_ortho_BB` is for |

### 5c — Thermal simulation

| Function | Description |
|---|---|
| `patch_babelvisco_BB(force=False)` | Fixes the BabelViscoFDTD `intparams` dtype bug **on disk**, because BHTE runs in a nested `spawn` child that an in-memory patch cannot reach. Must run before any thermal solve |
| `run_thermal_BB(...)` | BHTE solve for every DC/PRF/Duration combination in the stimulation YAML |
| `write_tpo_summary_BB(...)` | Back-calculates the free-field ISPPA the TPO must deliver to reach the planned in-situ value, one row per combination, into `*_Summary.csv` |
| `plot_thermal_qc_BB(...)` | ΔT and CEM43 figures, one per combination |

### Comparing and recording placements

| Function | Description |
|---|---|
| `placement_metrics_BB(...)` | Every step-5 number for one placement, as a flat dict |
| `compare_placements_BB(...)` | Side-by-side PDF over placements: acoustic, thermal and metrics |
| `write_vertices_explored(...)` | Markdown table of every vertex solved for one target, written beside it |

### Private helpers

`_drain_queue_BB` (drains the child's queue and detects errors), `_CalculateMaskProcess_wrapped` and `_CalculateFieldProcess_wrapped` (run inside the spawned child: apply patches that cannot cross a `spawn` boundary, and forward otherwise-invisible tracebacks as `--Babel-Brain-Low-Error`), and the plotting helpers `_setup_ax_BB`, `_tissue_contours_BB`, `_crosshair_BB`, `_add_colorbar_BB`.

### A note on the `Used in:` lines

Several step-3 functions — `ants_to_nib`, `register_mni_to_native`, `apply_inverse_transform`, `compute_com_native`, `visualize_mask_native` — carry `Used in: step 05` in their docstrings. That is left over from the notebook numbering in which registration was step 05; they are step-3 functions and are listed as such above. The docstrings have not been edited, so this note is the correction.
