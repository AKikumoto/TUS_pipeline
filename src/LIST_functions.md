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
| `stratified_seeds(target_folder, max_angle, max_distance=None, min_distance=None, n_levels=7, min_sep_mm=10, exclude=(), include_contra=False)` | (called by `run_sweep.py --stratify`) | Candidate vertices sampled across the whole beam-ROI overlap range: the pool `select_best_vtx` ranks at `top_pct=0.01`, cut into `n_levels` quantile bins, each contributing the vertex furthest from those already chosen. Contralateral entries dropped. The fallback for targets whose overlap ranking runs inverse to delivery |
| `run_plantus_placement(...)` | (called by `run_plantus`) | Runs `PlanTUS.prepare_acoustic_simulation` for one vertex, then `write_depth_report` |
| `write_depth_report(target_folder, vtx, additional_offset, subject_id)` | (called by `run_plantus_placement`) | The depth report, written after the placement from what PlanTUS left in `vtx{N}/`: PlanTUS's own focal distance (the TPO setting), entry and focus, the pad, the centre-of-gravity distance the selection used, and two derived values. Nothing else is recomputed; before 2026-09-21 the report took the distance to the ROI centre of gravity, up to 10 mm off for elongated ROIs |
| `rewrite_depth_reports(target_folder)` | (bookkeeping) | Regenerates every report in a target folder from its placement, pad taken from the old report |
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
| `read_depth_report(...)` | Parses the PlanTUS depth report into a dict; `_tpo_depth_mm(report)` returns the TPO setting from either report format |
| `focal_depth_mm(plantus_target_folder, vtx, tx_cfg=None)` | Focal depth the TPO is set to, **read** from `exit_plane_to_ROI_distance_mm` rather than recomputed, plus a verdict of `ok` / `below_calibrated` / `above_hardware` / `below_hardware`. Pass the raw transducer YAML (`cfg["transducer_cfg"]`), not `transducer_params()`, which drops the calibrated bounds |
| `list_plantus_vertices(target_folder, print_table=True)` | Every placement for one target, with the metrics `select_best_vtx` ranked on. `inter` is knife-edge — read `inter_near_mm`, the best value within 5 mm, before calling a vertex a miss. `elev_deg` / `azim_deg` place the entry relative to the aimed point, for comparing approaches across subjects |
| `fig_dir_for(sub_dir, target=None, stim=None)` | Figure directory: `figures/registration/`, `figures/{target}/` for acoustic, `figures/{target}/{stim}/` for thermal |

---

## Step 5: Acoustic & Thermal Simulation (BabelBrain)

Called from `notebook/step05_babelbrain.ipynb` and from `src/run_babelbrain.py`; `src/run_sweep.py` drives 5a and 5b once per shortlisted vertex. The order below is the order `run_babelbrain.py` runs them in.

### 5a — Domain generation

| Function | Description |
|---|---|
| `load_babelbrain_tx_yaml(bb_dir, tx_system)` | Loads BabelBrain's own `default.yaml` for the transducer: the only source of aperture, focal length, ring diameters, natural focus and steering corrections at step 5 (2026-09-20; the site config keeps the measured calibration range and the frequency) |
| `compute_z_steering_BB(plantus_target_folder, tx_cfg, bb_tx_yaml, vtx=None)` | Electronic steering offset, from the depth report of the **same** vertex the trajectory came from. Getting this from another vertex is what once moved a focus by 11 mm. The gel pad comes from that report too (planned at step 4); until 2026-09-20 the function added its own pad argument on top, which simulated every padded placement 20 mm too far from the skin |
| `standoff_check_BB(acoustic_file, plantus_target_folder, vtx, bb_tx_yaml, tol_mm=5)` | Planned pad versus the standoff the field was computed with (natural focus − `TxMechanicalAdjustmentZ` − BabelBrain's own `DistanceFromSkin`). Raises beyond 5 mm. The 2026-09-20 double count read 20 mm here and looked normal in every focus metric; `run_babelbrain.py` runs it after every acoustic solve and the summary shows both numbers |
| `run_domain_BB(...)` | Tissue domain from the SimNIBS mesh plus the trajectory. Starts `CalculateMaskProcess` in a `spawn` child; returns the `*_BabelViscoInput.nii.gz` path |
| `patch_trimesh_compat_BB()` | Reattaches `remove_duplicate_faces` / `remove_degenerate_faces`, removed in trimesh 4 but still called by `BabelDatasetPreps.DoIntersect`. Idempotent; see `LIST_modifications.md` |
| `read_trajectory_id_BB(trajectory_file)` | The trajectory's own ID column, which is what the step-5 output prefix is built from |

### 5b — Acoustic simulation

| Function | Description |
|---|---|
| `run_acoustic_BB(...)` | FDTD solve plus the water reference run. For ANNULAR_ARRAY transducers BabelBrain does not `put()` the result path, so it is recovered by globbing after the process exits |
| `summarise_acoustic_BB(...)` | The metrics table, written to HTML. Read the **brain-only, outlier-resistant** rows: the whole-domain maximum sits in cortical bone for deep targets |
| `score_candidate(...)` | Spike-resistant focal metrics for one solve, plus the `roi_overlap` figures and `csf_fraction`; what `run_sweep.py` ranks candidates on |
| `lobe_csf_fraction(acoustic_file, main_lobe)` | Share of the focal lobe in CSF by the charm segmentation (`final_tissues` label 3). Wasted rather than harmful; explains low coverage beside a ventricle |
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
| `plot_thermal_qc_BB(...)` | Thermal QC figure per combination: Isppa map, temperature map and the safety summary (max T per tissue, CEM43, MI). The temperature colour range is the same on every figure, baseline to baseline + 2 °C (`_THERMAL_DT_LIMIT_C`, the ITRUSST limit), so placements compare by eye; a map that stays dark blue is a small rise, not a missing field (2026-09-21) |

### Comparing and recording placements

| Function | Description |
|---|---|
| `write_adopted_placements(data_dir, sub_ids, tx_cfg, bb_tx_yaml, out_dir=None)` | The cross-subject record: one row per adopted placement (has a thermal summary) with TPO depth, pad, entry geometry, focus metrics, standoff check, protocol, derating, free-field ISPPA, temperature rise and MI, all read from saved outputs. `ADOPTED_PLACEMENTS.md` (by subject), `ADOPTED_BY_TARGET.md` (by target, subjects side by side) and `.csv` in the data directory; `run_status.py` drives it (2026-09-21) |
| `write_adopted_report_pdf(data_dir, csv_path, out_path=None)` | `ADOPTED_PLACEMENTS.pdf` from the CSV and the saved QC figures: a title page with per-target ranges, then per target the comparison table and one page per placement (acoustic QC above thermal QC, key numbers as caption) |
| `write_vertices_explored(...)` | Markdown table of every vertex solved for one target, written beside it. `run_sweep.py` writes it after every sweep; it replaced the two-vertex comparison PDF (`compare_placements_BB`, removed 2026-09-18, never used after the sweep existed) |

### Private helpers

Each convention the public functions share is defined once, in a private helper (2026-09-20):

| Helper | One place for |
|---|---|
| `_plantus_maps(target_folder, require=())` | Reading the per-vertex PlanTUS maps (`_PLANTUS_MAPS` names the files); the skin-skull angle comes back folded by `_fold_obliquity`. Used by `select_best_vtx`, `describe_vtx`, `stratified_seeds`, `list_plantus_vertices` |
| `_read_acoustic(acoustic_file, skin_first)` | Reading the step-5b h5 and the z convention: the arrays are stored distal-first, `TargetLocation` and `z_vec` skin-first. Plots read skin-first; the metric code (`score_candidate`, `_acoustic_metrics`) reads as stored |
| `_main_lobe(above)` | The focal lobe as the largest connected component above threshold, for `score_candidate` and `_flhm_metrics` |
| `_map_voxels(idx, src_affine, dst_affine, dst_shape)` | Moving voxel indices between grids through RAS, for `roi_overlap` and `lobe_csf_fraction` |
| `_sub_affine(acoustic_file)`, `_roi_on_sim_grid(acoustic_file, roi_nii, shape)` | The grid-to-world mapping of the stored field (the `*_FullElasticSolution_Sub.nii.gz` affine, not the h5's `affine`, which is the full domain's) and the ROI resampled onto that grid. Until 2026-09-21 the QC figure used the h5 affine and never drew an ROI contour |
| `_spawn_bb(target, args, kwargs, label)` | Launching a BabelBrain stage in a `spawn` child; `_drain_queue_BB` echoes its queue, returns `(ok, payload)` and raises after 900 s of silence. All three `run_*_BB` stages go through it |
| `_write_plantus_metric`, `_chord_lengths_mm`, `_skin_skull_angles`, `_write_placeholder_markers`, `_inject_marker_into_scene` | The steps of `prepare_plantus_scene`: one metric file, the beam-ROI chord, the folded skin-skull angle, the placeholder marker files, the scene XML edits |
| `_acoustic_metrics`, `_flhm_metrics`, `_traffic_light`, `_html_table` | The numbers behind `summarise_acoustic_BB`, the -3 dB lobe metric, the row colours and the HTML table; `_ACOUSTIC_SUMMARY_FOOTER` is the "how to read" text saved in every summary |

`_CalculateMaskProcess_wrapped` and `_CalculateFieldProcess_wrapped` run inside the spawned child (apply patches that cannot cross a `spawn` boundary, forward otherwise-invisible tracebacks as `--Babel-Brain-Low-Error`). The step-1 environment check family, the unused plotting helpers and the two-vertex comparison PDF were removed on 2026-09-18; nothing called them.

The `Used in:` lines in the docstrings were re-derived from the actual callers on 2026-09-20 (the step-3 functions had carried `step 05` from an older notebook numbering); where a docstring and this file disagree, the docstring is the newer of the two.
