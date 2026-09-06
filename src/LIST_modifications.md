# Local Modifications: Patch Log

All locally applied patches to third-party tools. Changes here are **not upstreamed**; re-apply after any upstream update.

---

## PlanTUS (`PlanTUS/code/PlanTUS.py`)

| Date | File | Line(s) | Change | Reason |
|------|------|---------|--------|--------|
| 2026-03-19 | `PlanTUS/code/PlanTUS.py` | 600–602 | `np.string_` → `np.bytes_` (3 occurrences in `create_kps_file_for_kPlan`) | `np.string_` was removed in NumPy 2.0; `np.bytes_` is the direct replacement |
| 2026-03-20 | `PlanTUS/code/PlanTUS.py` | 563–570 | Added `"..."` quotes around all path arguments in `transform_surface_model`'s two `os.system()` calls | `surface_model_filepath` points to `Dropbox (Personal)/...` which contains a space; unquoted paths in shell commands are split at spaces, silently producing no output file |
| 2026-03-20 | `src/utils.py` | `subprocess.Popen` in `run_plantus` | Added four Qt5 HiDPI env vars to wb_view launch: `QT_AUTO_SCREEN_SCALE_FACTOR=0`, `QT_SCALE_FACTOR=1`, `QT_ENABLE_HIGHDPI_SCALING=0`, `QT_FONT_DPI=96` | On macOS Retina displays, Qt5 double-scales the window, collapsing panels and misaligning click targets; all four variables are required to suppress this |
| 2026-03-20 | `src/utils.py` | `run_plantus` | Made `pynput` optional via `use_pynput` parameter (default `True`); falls back to direct stderr parsing when `pynput` is unavailable or Accessibility permissions are not granted | `pynput` silently drops events without Accessibility permissions; `use_pynput=False` bypasses the listener and parses wb_view FINER log directly |
| 2026-03-22 | `src/utils.py` | `write_brainsight_txt` `_row()` | Fixed rotation matrix column order: `m{col}n{row}` = `R[row, col]` → now writes column-by-column (`R[:,0]`, `R[:,1]`, `R[:,2]`) instead of row-by-row | BrainSight/BabelBrain convention is column-major; previous code wrote R^T, causing incorrect transducer beam orientation in BabelBrain acoustic simulation. Neuronavigation (XYZ only) was unaffected. Same bug existed in the original legacy notebook (`z_old_scripts/TUS_aMCCmask.ipynb`). |
| 2026-03-22 | `config/sites/site_RIKEN_AK.yaml`, `site_UMD_AK.yaml` | line 11 | `coordinate_system: "NIfTI:Scanner"` → `"NIfTI:S:Scanner"` | BabelBrain ≥ v14 validates the coordinate system header string against a known list; `"NIfTI:Scanner"` matches none and would cause `EndWithError` in Brainsight-integration mode. Version 13 files skip this check, so existing navigation was unaffected. |
| 2026-03-23 | `PlanTUS/PlanTUS_wrapper.py` | entire file | Unified the two device-specific wrapper scripts (`PlanTUS_wrapper_CTX500.py`, `PlanTUS_wrapper_DPX500.py`) into a single `argparse`-driven script. All transducer parameters (focal depth, F#, calibration) and site paths are now read from the site and transducer config YAMLs via `--site YAML`. The two original files are archived in `z_old_scripts/`. | Eliminated code duplication and hardcoded paths. One script now works with any site configuration; adding a new site or transducer requires only a new YAML, not a new wrapper. |

> These patches are not upstreamed. If PlanTUS is updated, re-apply these changes and update this table.

---

## SimNIBS (`segmentation/brain_surface.py`)

Installed in the `mri` conda env at:
`/Users/atsushikikumoto/miniforge3/envs/mri/lib/python3.11/site-packages/simnibs/`

**Root issue**: `brain_surface.py` builds external-binary commands as f-strings and then calls `cmd.split()` to tokenize them before passing to `spawn_process`. On paths containing spaces (e.g., `Dropbox (Personal)/...`), `split()` breaks the path into separate tokens, causing the binary to receive malformed arguments and silently fail.

| Date | File | Line(s) | Change | Reason |
|------|------|---------|--------|--------|
| 2026-04 | `segmentation/brain_surface.py` | ~184 | `spawn_process(cmd.split())` → `spawn_process([str(cat_surf2sphere), str(sph_map_white), str(sphere), "10"])` for the CAT_Surf2Sphere call | `cmd.split()` splits `Dropbox (Personal)/...` on the space, breaking the path into two tokens. List-based argument passing avoids shell tokenisation entirely. |
| 2026-04 | `segmentation/brain_surface.py` | ~206 | `spawn_process(cmd.split())` → `spawn_process([str(cat_warpsurf), "-steps", "2", "-avg", "-i", str(white), "-is", str(sphere), "-t", str(fsavg_white), "-ts", str(fsavg_sphere), "-ws", str(sphere_reg)])` for the CAT_WarpSurf call | Same root cause as above. |

> These patches target SimNIBS 4.6.0. If SimNIBS is updated via `pip install --upgrade simnibs`, `brain_surface.py` will be overwritten and the patches must be re-applied.
>
> Note: using a `~/Dropbox` symlink does **not** bypass this bug, Python's `Path.resolve()` follows symlinks back to the real path containing spaces before the value is ever substituted into the f-string.

---

## BabelViscoFDTD (`tools/RayleighAndBHTE.py`): on-disk dtype fix

Installed in the `mri` conda env at:
`/Users/atsushikikumoto/miniforge3/envs/mri/lib/python3.11/site-packages/BabelViscoFDTD/`

**Root issue**: `BHTE()` and `BHTEMultiplePressureFields()` build the GPU kernel parameter array `intparams` with `dtype=np.uint32` while passing `LocationMonitoring=-1` (the no-monitoring-slice sentinel), raising `OverflowError: Python integer -1 out of bounds for uint32` under numpy >= 2. numpy 1.x wrapped silently to `0xFFFFFFFF`, which is what the shader expects, so the bug only became fatal after the numpy 2 upgrade.

`uint32` is simply the wrong type. The Metal shader in the same file declares the parameter as **signed**, `constant int * intparams [[ buffer(12) ]]` with `#define SelJ intparams[7]` (line 365), so `np.int32` is correct and this is an upstream bug fix, not a workaround.

**Implementation**: the installed file **is edited**, by `src/utils.py::patch_babelvisco_BB()`. This replaces an earlier in-memory monkey-patch, which could not work: BHTE does not run in the notebook process. `CalculateThermalProcess` starts a nested `multiprocessing.Process` using the global start method (`spawn` on macOS), and a spawned child re-imports `RayleighAndBHTE` from scratch, so an in-memory patch is absent from the process that actually runs BHTE. Forcing `fork` to propagate it was worse, importing BabelViscoFDTD initialises the Metal runtime at import time, and forking that crashes Metal.

| Date | File | Line(s) | Change | Reason |
|------|------|---------|--------|--------|
| 2026-08-03 | `BabelViscoFDTD/tools/RayleighAndBHTE.py` | 1879, 1987, 2520, 2636 | `dtype=np.uint32,` → `dtype=np.int32,` on the four `intparams` constructions (Metal and MLX branches of `BHTE` and `BHTEMultiplePressureFields`) | Array includes `LocationMonitoring=-1`; numpy >= 2 raises `OverflowError`. The shader declares `constant int *`, so `int32` is the correct type. |

Not changed, and must stay `uint32`: the `MonitoringPoints = np.zeros(MaterialMap.shape, dtype=np.uint32)` arrays at lines 1566 and 2185. The shader declares `constant unsigned int *d_pointsMonitoring`, and `BHTE` asserts `MonitoringPointsMap.dtype == np.uint32` (line 1507). Shadowing the dtype module-wide broke that assert in an earlier attempt, so the change is scoped to `intparams` only.

> The original file is preserved as `RayleighAndBHTE.py.orig` in the same directory.
> `patch_babelvisco_BB()` is called at the top of Step 5c in `step05_babelbrain.ipynb`. It is idempotent. It rewrites only sites that still say `uint32` and reports when nothing is needed, so it also repairs the file automatically after a package reinstall.
> Worth reporting upstream to ProteusMRIgHIFU/BabelViscoFDTD so this local edit becomes redundant.

**Separate latent bug, found but not fixed** (not on our code path): `RayleighAndBHTE.py:2606`, in the `BHTEMultiplePressureFields` MLX branch, reads `knl = prgcl` where `prgcl` is a dict; it should be `prgcl["BHTE"]` as at line 1964. Only reached when `InputPData` is a list of more than one field.

---

## `src/utils.py`: own-code bug fixes

| Date | Function | Lines | Change | Reason |
|------|----------|-------|--------|--------|
| 2026-04-09 | `summarise_acoustic_BB` | ~3313 | Added `iz_f = nz - 1 - iz` and replaced `iz` with `iz_f` in (1) FLHM centroid `_dz` and (2) peak `dist_to_tgt` z-component | `p_amp` and `MaterialMap` in the h5 are flipped along z (index 0 = distal/brain side), but `TargetLocation[2]` is stored as a pre-flip index. Comparing the raw `iz` against `pz` / `_cz` from the flipped array produced a spurious z-offset of ~44 mm. With the fix, `Focus→target dist` matches the BabelBrain GUI value (~2–3 mm). |

---

## wb_view.app (`/Applications/workbench/macosxub_apps/wb_view.app/`)

A backup of each modified file is kept alongside the original (`.bak` suffix).

| Date | File | Change | Reason |
|------|------|--------|--------|
| 2026-03-20 | `Contents/Info.plist` | Added `NSHighResolutionCapable = false` | Without this key, macOS passes the full Retina device pixel ratio (2×) to Qt5, which then applies its own scaling on top, resulting in a double-scaled window where panels collapse and clicks are misaligned. External monitors are unaffected. To revert: `sudo cp Info.plist.bak Info.plist` |
