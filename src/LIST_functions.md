# src/utils.py — Function Reference

All functions are in `src/utils.py`. Called from notebooks in `run/`.

---

## Step 3 — Registration & Target Coordinate

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

## Step 4 — PlanTUS

All functions below are called from `run/TUS_segmentation_SimNINBS.ipynb` (Step 4 cells).

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
