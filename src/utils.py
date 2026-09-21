"""
src/utils.py: every function the TUS pipeline steps call, shared by the
notebooks in notebook/ and the batch runners in src/run_*.py.

The function reference, grouped by pipeline step, is src/LIST_functions.md;
each function also says which step uses it in its docstring. Patches applied
to third-party tools are logged in src/LIST_modifications.md.
"""

import math
import os
import re
import shutil
import subprocess
import tempfile
import sys
import threading
import traceback
from pathlib import Path

import yaml


# --- Constants ---

#: Keys required in every site config YAML. Used in: all steps.
REQUIRED_CONFIG_KEYS: list[str] = ["data_root", "sub_list_dir", "fsl_bin"]

#: Path keys whose values should have ~ expanded. Used in: all steps.
_PATH_KEYS: tuple[str, ...] = (
    "data_root",
    "sub_list_dir",
    "simnibs_python",
    "simnibs_site_packages",
    "fsl_bin",
    "workbench_bin",
    "freesurfer_home",
    "atlases_dir",
)

#: Expected output files from a successful charm run. Used in: test step 01.
CHARM_OUTPUTS: list[str] = [
    "final_tissues.nii.gz",
    "final_tissues_LUT.txt",
    "T1.nii.gz",
]


# --- Config helpers ---

def load_site_config(yaml_path: str | Path) -> dict:
    """Load and validate a site YAML config.

    Used in: all steps.

    Parameters
    ----------
    yaml_path:
        Path to a ``site_*.yaml`` file (e.g. ``config/sites/site_RIKEN_AK.yaml``).

    Returns
    -------
    dict
        Parsed config with all path values ``~``-expanded.

    Raises
    ------
    SystemExit
        If the file does not exist or required keys are missing.
    """
    yaml_path = Path(yaml_path).expanduser().resolve()
    if not yaml_path.exists():
        sys.exit(f"ERROR: site config not found: {yaml_path}")

    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)

    missing = [k for k in REQUIRED_CONFIG_KEYS if k not in cfg]
    if missing:
        sys.exit(f"ERROR: site config missing required keys: {missing}")

    for key in _PATH_KEYS:
        if key in cfg and isinstance(cfg[key], str):
            cfg[key] = str(Path(cfg[key]).expanduser())

    # Auto-load transducer YAML if specified in site config
    tx_name = cfg.get("transducer")
    if tx_name:
        tx_yaml = yaml_path.parent.parent / "transducers" / f"{tx_name}.yaml"
        if tx_yaml.exists():
            with open(tx_yaml) as _tf:
                cfg["transducer_cfg"] = yaml.safe_load(_tf)
        else:
            print(f"NOTE: transducer config not found: {tx_yaml}")

    return cfg


def load_transducer_config(cfg: dict, site_yaml_path: str | Path) -> dict:
    """Load the transducer YAML named by ``cfg['transducer']``.

    Expected at ``config/transducers/{transducer_name}.yaml`` relative to the
    directory holding the site YAML; ``sys.exit`` when the key or the file is
    missing.

    Used in: step 04, run_planTUS.py, run_sweep.py.

    Parameters
    ----------
    cfg, site_yaml_path:
        Loaded site config (:func:`load_site_config`) and the site YAML path
        that locates ``config/transducers/``.
    """
    site_yaml_path = Path(site_yaml_path).expanduser().resolve()
    transducer_name = cfg.get("transducer")
    if not transducer_name:
        sys.exit("ERROR: site config missing 'transducer' key")

    t_path = site_yaml_path.parent.parent / "transducers" / f"{transducer_name}.yaml"
    if not t_path.exists():
        sys.exit(f"ERROR: transducer config not found: {t_path}")

    with open(t_path) as f:
        return yaml.safe_load(f)


def resolve_data_dir(cfg: dict) -> Path:
    """Return the absolute path to the subject-list data directory.

    Used in: steps 01, 04.

    ``sub_list_dir`` in the config may be an absolute path or relative to
    ``data_root``.

    Raises
    ------
    SystemExit
        If the resolved directory does not exist.
    """
    data_root = Path(cfg["data_root"]).expanduser()
    sub_list_dir = cfg["sub_list_dir"]
    d = Path(sub_list_dir)
    if not d.is_absolute():
        d = data_root / sub_list_dir
    if not d.exists():
        sys.exit(f"ERROR: data directory not found: {d}")
    return d


# --- Subject ID helpers ---

def normalise_sub_id(sub_id: str) -> tuple[str, str]:
    """Return ``(sub_id_full, sub_id_bare)``.

    Used in: all steps.

    Examples
    --------
    >>> normalise_sub_id("NS")
    ('sub-NS', 'NS')
    >>> normalise_sub_id("sub-NS")
    ('sub-NS', 'NS')
    """
    if sub_id.startswith("sub-"):
        return sub_id, sub_id[4:]
    return f"sub-{sub_id}", sub_id


# --- File helpers ---

def resolve_sub_dir(data_dir: Path, sub_id_bare: str, sub_id_full: str) -> Path:
    """Return the subject directory, supporting both bare and BIDS-style naming.

    Used in: all steps.

    Search order:
    1. ``data_dir / sub_id_bare``  (e.g. ``data_dir/M3827/``)  — legacy / RIKEN style
    2. ``data_dir / sub_id_full``  (e.g. ``data_dir/sub-M3827/``)  — BIDS style

    Raises
    ------
    SystemExit
        If neither directory exists.
    """
    bare_dir = data_dir / sub_id_bare
    full_dir = data_dir / sub_id_full
    if bare_dir.exists():
        return bare_dir
    if full_dir.exists():
        print(f"NOTE: using BIDS-style subject dir: {full_dir}")
        return full_dir
    sys.exit(
        f"ERROR: subject directory not found in {data_dir}\n"
        f"  Tried: {sub_id_bare}/ and {sub_id_full}/"
    )


def find_t1(sub_dir: Path, sub_id_bare: str) -> Path:
    """Find a T1w NIfTI file in *sub_dir*.

    Used in: step 01, step 03 (run_reg.py).

    Search order:
    1. Strict BIDS: ``sub-{id}_T1w.nii.gz`` / ``.nii``
    2. Loose glob (suffix):  ``sub-{id}_T1w*.nii.gz`` / ``*.nii``
       (matches e.g. ``sub-M3827_T1w_7T.nii``)
    3. Full BIDS glob (entities before T1w):  ``sub-{id}*_T1w.nii.gz`` / ``*.nii``
       (matches e.g. ``sub-a777_ses-01_acq-memprageRMS_desc-preproc_T1w.nii.gz``)
       If multiple files match, the first (sorted) is used with a warning.

    Raises
    ------
    SystemExit
        If no T1w file is found.
    """
    stem = f"sub-{sub_id_bare}_T1w"
    # 1. Strict BIDS match
    for suffix in (".nii.gz", ".nii"):
        candidate = sub_dir / (stem + suffix)
        if candidate.exists():
            return candidate
    # 2. Loose glob fallback — T1w followed by extra suffix (e.g. sub-M3827_T1w_7T.nii)
    for pattern in (f"{stem}*.nii.gz", f"{stem}*.nii"):
        matches = sorted(sub_dir.glob(pattern))
        if matches:
            if len(matches) > 1:
                print(
                    f"WARNING: multiple T1w files found in {sub_dir}; "
                    f"using {matches[0].name}"
                )
            return matches[0]
    # 3. Full BIDS glob — BIDS entities before T1w (e.g. sub-a777_ses-01_acq-..._T1w.nii.gz)
    for pattern in (f"sub-{sub_id_bare}*_T1w.nii.gz", f"sub-{sub_id_bare}*_T1w.nii"):
        matches = sorted(sub_dir.glob(pattern))
        if matches:
            if len(matches) > 1:
                print(
                    f"WARNING: multiple T1w files found in {sub_dir}; "
                    f"using {matches[0].name}"
                )
            return matches[0]
    sys.exit(
        f"ERROR: T1w file not found in {sub_dir}\n"
        f"  Expected: {stem}.nii.gz, {stem}.nii, {stem}_*.nii[.gz], "
        f"or sub-{sub_id_bare}*_T1w.nii[.gz]"
    )


def output_exists_simnibs(sub_dir: Path, sub_id_full: str) -> bool:
    """Return True if SimNIBS charm output ``final_tissues.nii.gz`` exists.

    Used in: steps 01, test 01.
    """
    return (sub_dir / f"m2m_{sub_id_full}" / "final_tissues.nii.gz").exists()


def parse_sub_list(path: str | Path) -> list[str]:
    """Read subject IDs from a plain-text file (one ID per line).

    Used in: steps 01, test 01.

    Blank lines and lines starting with ``#`` are ignored.
    """
    lines = Path(path).expanduser().read_text().splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


# --- Step 01 — SimNIBS segmentation (charm) ---

def run_fix_qform(t1_path: Path, fsl_bin: str, dry_run: bool) -> None:
    """Run ``fslorient -copysform2qform`` to align qform to sform.

    Used in: step 01.
    """
    fslorient = str(Path(fsl_bin) / "fslorient")
    cmd = [fslorient, "-copysform2qform", str(t1_path)]
    print(f"  [fix-qform] {' '.join(cmd)}")
    if not dry_run:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stderr:
            print(result.stderr)


def run_charm(sub_id: str, t1_path: Path, sub_dir: Path, dry_run: bool) -> None:
    """Run SimNIBS ``charm`` from the subject directory.

    Used in: step 01.

    charm writes ``m2m_{sub_id}/`` into the current working directory.
    Uses Popen with line-by-line streaming to avoid pipe-buffer deadlock
    that occurs with subprocess.run() during long-running processes.
    """
    cmd = ["charm", sub_id, str(t1_path)]
    print(f"  [charm]     {' '.join(cmd)}")
    print(f"  [cwd]       {sub_dir}")
    if not dry_run:
        with subprocess.Popen(
            cmd, cwd=str(sub_dir),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        ) as proc:
            for line in proc.stdout:
                print(line, end="", flush=True)
            proc.wait()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)


def process_subject(
    sub_id: str,
    data_dir: Path,
    cfg: dict,
    fix_qform: bool,
    overwrite: bool,
    dry_run: bool,
) -> bool:
    """Orchestrate qform-fix + charm for one subject.

    Used in: step 01.

    Returns
    -------
    bool
        True on success, False if skipped.
    """
    sub_id_full, sub_id_bare = normalise_sub_id(sub_id)
    sub_dir = resolve_sub_dir(data_dir, sub_id_bare, sub_id_full)
    if not sub_dir.exists():
        print(f"  WARNING: subject directory not found: {sub_dir} — skipping")
        return False
    if output_exists_simnibs(sub_dir, sub_id_full) and not overwrite:
        print(f"  SKIP: output exists for {sub_id_full} (use --overwrite to rerun)")
        return False
    t1_path = find_t1(sub_dir, sub_id_bare)
    print(f"  T1:  {t1_path}")
    if fix_qform:
        run_fix_qform(t1_path, cfg["fsl_bin"], dry_run)
    run_charm(sub_id_full, t1_path, sub_dir, dry_run)
    return True


# --- Step 04 — PlanTUS target planning ---

# PlanTUS lives at scripts/TUS/PlanTUS/ (sibling of run/ and src/)
_PLANTUS_ROOT = Path(__file__).resolve().parent.parent / "PlanTUS"
_PLANTUS_CODE = _PLANTUS_ROOT / "code"


def setup_environment(cfg: dict) -> None:
    """Extend PATH and set environment variables from site config.

    Used in: step 04.
    """
    path_additions = []
    for key in ("fsl_bin", "workbench_bin"):
        v = cfg.get(key)
        if v:
            path_additions.append(str(Path(v).expanduser()))
    freesurfer_home = cfg.get("freesurfer_home")
    if freesurfer_home:
        fsh = str(Path(freesurfer_home).expanduser())
        os.environ["FREESURFER_HOME"] = fsh
        path_additions.append(os.path.join(fsh, "bin"))
    simnibs_sp = cfg.get("simnibs_site_packages")
    if simnibs_sp:
        p = str(Path(simnibs_sp).expanduser())
        if p not in sys.path:
            sys.path.append(p)  # append (not insert) to avoid clobbering already-loaded packages
    if path_additions:
        os.environ["PATH"] = ":".join(path_additions) + ":" + os.environ.get("PATH", "")
    print("wb_command  :", subprocess.getoutput("which wb_command"))
    print("mris_convert:", subprocess.getoutput("which mris_convert"))
    print("fslmaths    :", subprocess.getoutput("which fslmaths"))


def transducer_params(tcfg: dict) -> dict:
    """Extract PlanTUS-relevant parameters from a transducer config dict.

    Used in: step 04.

    Returns a flat dict with keys:
      ``min_distance``, ``max_distance``, ``transducer_diameter``, ``max_angle``,
      ``plane_offset``, ``focal_distance_list``, ``flhm_list``,
      ``scene_template_path``, ``placement_template_path``, ``transducer_model_path``.

    Raises
    ------
    SystemExit
        If calibration data is missing.
    """
    cal = tcfg.get("calibration", {})
    focal_distance_list = cal.get("tpo_settings_mm") or cal.get("flhm_center_mm")
    flhm_list = cal.get("axial_flhm_mm")
    if not focal_distance_list or not flhm_list:
        sys.exit("ERROR: transducer config missing calibration.tpo_settings_mm / axial_flhm_mm")

    scene_tpl_name = tcfg.get("scene_template", "TUSTransducerPlacementPlanning_TEMPLATE.scene")
    scene_tpl_path = _PLANTUS_ROOT / "resources" / "scene_templates" / scene_tpl_name
    model_name = tcfg.get("transducer_model", "")
    model_path = (
        str(_PLANTUS_ROOT / "resources" / "transducer_models" / model_name)
        if model_name else ""
    )
    return {
        "min_distance"          : tcfg.get("min_focal_depth_mm"),
        "max_distance"          : tcfg.get("max_focal_depth_mm"),
        "transducer_diameter"   : tcfg["transducer_diameter_mm"],
        "max_angle"             : tcfg.get("max_angle_deg", 10),
        "plane_offset"          : tcfg["plane_offset_mm"],
        "focal_distance_list"   : focal_distance_list,
        "flhm_list"             : flhm_list,
        "scene_template_path"   : str(scene_tpl_path),
        "transducer_model_path" : model_path,
        "placement_template_path": str(
            _PLANTUS_ROOT / "resources" / "scene_templates"
            / "TUSTransducerPlacement_TEMPLATE.scene"
        ),
    }


# --- Naming ---
# One place that builds every downstream name, so the pieces cannot drift apart
# again. What they looked like before:
#
#   sub-z002_T1w_rHipp_L_OR_rHipp_R_BN_L_target_vtx27429_DPX_500_500kHz_6PPW_DataForSim.h5
#
# `_T1w_` said nothing (there is only native space), `_target_` was filler, the
# mask label carried step 02's boolean construction, and the side was glued on
# with the same underscore the label already used, so nothing could tell where
# the label ended and the side began.
#
#   sub-z002_rHipp_BN-L_vtx27429_DPX500-500kHz-6ppw_DataForSim.h5
#
# Side is separated by a hyphen for exactly that reason. Vertex numbers are NOT
# zero-padded: PlanTUS writes its own vtx folders as "vtx" + str(n)
# (PlanTUS.py:984), and matching third-party output is worth more than sortable
# names -- the alternative is patching someone else's filenames.

def stem_for(sub_id_full: str, target_name: str, target_side: str = "") -> str:
    """`{sub}_{target}[-{L|R}]` — the stem every downstream name starts from."""
    side = target_side.lstrip("_")
    return f"{sub_id_full}_{target_name}" + (f"-{side}" if side else "")


def mask_suffix(target_side: str = "") -> str:
    """`_mask` / `_mask-L` / `_mask-R` — the native mask (and PlanTUS folder).

    PlanTUS names its own output folder and every file inside it after this
    stem, so this is what propagates into the scene files too.
    """
    side = target_side.lstrip("_")
    return "_mask" + (f"-{side}" if side else "")


def find_plantus_target_folder(
    m2m_dir: Path,
    sub_id_full: str,
    target_name: str,
    target_side: str,
) -> Path:
    """Return the PlanTUS output folder for a given target.

    Used in: step 04.

    Searches ``{m2m_dir}/PlanTUS/`` for any subdirectory whose name ends
    with ``{target_name}_mask[-{side}]``.  This tolerates
    variation in the prefix left by earlier naming schemes
    because the folder name is derived from the actual mask filename by
    ``prepare_plantus_scene``.

    Raises
    ------
    SystemExit
        If no matching folder is found or more than one match exists.
    """
    plantus_dir = m2m_dir / "PlanTUS"
    pattern = f"*{target_name}{mask_suffix(target_side)}"
    matches = [p for p in plantus_dir.glob(pattern) if p.is_dir()] if plantus_dir.exists() else []
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        sys.exit(
            f"ERROR: multiple PlanTUS target folders match '{pattern}' in {plantus_dir}:\n"
            + "\n".join(f"  {m}" for m in matches)
        )
    sys.exit(f"ERROR: PlanTUS target folder not found: {plantus_dir / pattern}")


def _fold_obliquity(a):
    """Fold a skin-skull angle into [0, 90] degrees; idempotent.

    PlanTUS computes it as ``arccos(skin_normal . skull_normal)``
    (``PlanTUS/code/PlanTUS.py:352-357``), so the raw range is 0-180. Above
    90 the surfaces are still parallel: the nearest skull vertex lies on the
    inner table of the closed skull shell (SimNIBS tags 1007+1008) and its
    normal points the other way. Obliquity on bone is what the metric is for,
    so 179 and 1 mean the same thing; unfolded, such a vertex (178 of 4 628
    safe vertices on sub-z004) normalises as the worst incidence when it is
    near-perfect. Details in ``simulation_metrics.md``.

    Used by: :func:`prepare_plantus_scene` (writing the metric),
    :func:`select_best_vtx`, :func:`list_plantus_vertices`, :func:`describe_vtx`.
    """
    import numpy as _np                                          # noqa: PLC0415

    return _np.minimum(a, 180.0 - _np.asarray(a, dtype=float))


def skull_path_mm(m2m_dir, coords, roi_cog, step_mm: float = 0.25):
    """Bone traversed by the straight line from each scalp vertex to the ROI.

    PlanTUS scores a placement from the scalp surface alone (aim angle,
    distance, skin-skull angle, beam-ROI intersection) and never looks inside
    the skull, so a vertex on the jaw scores like one on the parietal bone;
    two EC placements chosen that way delivered 0.002 and 0.021 of peak at
    the target. Reads charm's ``final_tissues.nii.gz`` (7 compact, 8 spongy
    bone), so nothing new is computed; ~1 s for a 35 000-vertex scalp.

    A veto, not a score: it separates the catastrophic paths (14 and 42 mm)
    from the rest but does not rank the 4-10 mm band, where delivered
    intensity varies threefold with no thickness difference
    (``simulation_metrics.md``).

    Used by: :func:`select_best_vtx` (``max_skull_mm``).

    Returns compact, spongy and total thickness in mm, one entry per vertex.
    """
    import nibabel as nib
    import numpy as np

    seg_path = Path(m2m_dir) / "final_tissues.nii.gz"
    if not seg_path.is_file():
        raise FileNotFoundError(
            f"SimNIBS segmentation not found: {seg_path}\n"
            "  Needed for the skull-thickness veto. Re-run step 1 (charm), or "
            "pass max_skull_mm=None to skip the check."
        )
    img = nib.load(str(seg_path))
    vol = np.squeeze(np.asanyarray(img.dataobj)).astype(np.uint8)
    inv = np.linalg.inv(img.affine)
    shape = np.array(vol.shape)

    coords = np.asarray(coords, dtype=float)
    roi_cog = np.asarray(roi_cog, dtype=float)
    vec = roi_cog[None, :] - coords
    length = np.linalg.norm(vec, axis=1)

    # One sample count for every ray, set by the longest, so the whole sweep is
    # a single array op. Shorter rays are then oversampled, which costs memory
    # but not correctness: each sample carries its own ray's step length.
    n = max(int(np.nanmax(length) / step_mm), 2)
    t = np.linspace(0.0, 1.0, n)
    pts = coords[:, None, :] + t[None, :, None] * vec[:, None, :]
    ijk = np.rint(nib.affines.apply_affine(inv, pts.reshape(-1, 3))).astype(int)
    inside = np.all((ijk >= 0) & (ijk < shape[None, :]), axis=1)

    lab = np.zeros(len(ijk), dtype=np.uint8)
    lab[inside] = vol[ijk[inside, 0], ijk[inside, 1], ijk[inside, 2]]
    lab = lab.reshape(len(coords), n)

    step = (length / n)[:, None]
    compact = ((lab == 7) * step).sum(axis=1)
    spongy = ((lab == 8) * step).sum(axis=1)
    return compact, spongy, compact + spongy


def brain_floor_z(m2m_dir) -> float:
    """Lowest z (RAS, mm) at which brain tissue exists.

    Used to reject scalp vertices below the cranial vault. PlanTUS's avoidance
    mask covers eyes, ears and superficial vessels but not the face, jaw or
    neck: it passed a vertex 91 mm below its own target, on which no transducer
    could physically be placed, and whose beam then crossed 42 mm of skull base.

    Below the inferior extent of brain there is no vault to couple through, so
    this is a geometric fact about the head rather than a tuned threshold.
    """
    import nibabel as nib
    import numpy as np

    img = nib.load(str(Path(m2m_dir) / "final_tissues.nii.gz"))
    vol = np.squeeze(np.asanyarray(img.dataobj)).astype(np.uint8)
    idx = np.array(np.nonzero(np.isin(vol, (1, 2, 3))))   # WM, GM, CSF
    return float(nib.affines.apply_affine(img.affine, idx.T)[:, 2].min())


def write_foci_file(target_folder: Path, coords, rows,
                    filename: str = "best_vtx_marker_skin.foci",
                    verbose: int = 1) -> Path | None:
    """Write a wb_view foci file marking *rows* as named, coloured spheres.

    Foci sit above the surface instead of being painted into it, so nothing
    swallows them (marks drawn as rings of vertices vanished where candidates
    were dense); they carry a name, so the identify window says
    "ADOPTED vtx4799" rather than "-2"; and they need none of the three
    overlay slots a tab has.

    Used by: :func:`select_best_vtx`.

    Parameters
    ----------
    target_folder, coords, filename:
        PlanTUS target folder (``skin.surf.gii`` in it is the projection
        target), ``(n_vertices, 3)`` scalp coordinates, output name inside
        the folder.
    rows:
        ``(name, (r, g, b), vertex_index)`` per focus, colours 0-255. Avoid the
        metric palettes underneath: red is invisible on the red end of the
        distance map. White and magenta are used.

    Returns
    -------
    Path or None
        The foci file, or None if it could not be written.
    """
    out = target_folder / filename
    wb = shutil.which("wb_command")
    if wb is None:
        if verbose > 0:
            print("[foci] wb_command not on PATH — no foci written. "
                  "Run setup_environment() first.")
        return None
    if not rows:
        return None

    # -foci-create groups by class and takes one text file per class, two lines
    # per focus: the name alone, then colour and coordinates.  The per-focus RGB
    # lands in the file's FociNameColorTable, which is what wb_view reads --
    # its coloring type defaults to FEATURE_COLORING_TYPE_NAME.  Class colours
    # are left unset and stay black; they are not used.
    with tempfile.TemporaryDirectory() as tmp:
        listing = Path(tmp) / "foci.txt"
        with open(listing, "w") as fh:
            for name, rgb, vtx in rows:
                x, y, z = coords[int(vtx)]
                fh.write(f"{name}\n{rgb[0]} {rgb[1]} {rgb[2]} "
                         f"{x:.3f} {y:.3f} {z:.3f}\n")
        out.unlink(missing_ok=True)          # -foci-create will not overwrite
        res = subprocess.run(
            [wb, "-logging", "OFF", "-foci-create", str(out),
             "-class", "placement", str(listing),
             str(target_folder / "skin.surf.gii")],
            capture_output=True, text=True)
    if res.returncode != 0 or not out.is_file():
        if verbose > 0:
            print(f"[foci] wb_command -foci-create failed: "
                  f"{res.stderr.strip()[:200]}")
        return None
    return out


_PLANTUS_MAPS = {
    "dist_thr": "distances_skin_thresholded.func.gii",
    "angle":    "angles_skin.func.gii",
    "avoid":    "avoidance_skin.func.gii",
    "inter":    "target_intersection_skin.func.gii",
    "skl":      "skin_skull_angles_skin.func.gii",
    "dist_raw": "skin_target_distances.npy",
    "coords":   "skin.surf.gii",
}


def _plantus_maps(target_folder, require=()):
    """Per-vertex PlanTUS maps of one target as a dict, ``None`` where a file is missing.

    One loader for :func:`select_best_vtx`, :func:`describe_vtx`,
    :func:`stratified_seeds` and :func:`list_plantus_vertices`, so the
    skin-skull angle is folded (:func:`_fold_obliquity`) in one place and the
    file names live in :data:`_PLANTUS_MAPS`. ``inter`` is returned as stored
    (PlanTUS leaves NaNs in it) and callers decide how to treat them;
    ``coords`` is float64. ``FileNotFoundError`` lists every missing file in
    *require*.
    """
    import numpy as np                                            # noqa: PLC0415
    import nibabel as nib                                         # noqa: PLC0415

    folder = Path(target_folder)
    paths = {k: folder / v for k, v in _PLANTUS_MAPS.items()}
    missing = [str(paths[k]) for k in require if not paths[k].exists()]
    if missing:
        raise FileNotFoundError(
            "Missing PlanTUS metric files (run prepare_plantus_scene first):\n"
            + "\n".join(f"  {m}" for m in missing)
        )
    out = {}
    for k, p in paths.items():
        if not p.is_file():
            out[k] = None
        elif p.suffix == ".npy":
            out[k] = np.load(p)
        else:
            out[k] = np.asarray(nib.load(str(p)).darrays[0].data)
    if out["skl"] is not None:
        out["skl"] = _fold_obliquity(out["skl"])
    if out["coords"] is not None:
        out["coords"] = out["coords"].astype(float)
    return out


def select_best_vtx(
    target_folder: Path,
    max_angle: float,
    max_distance: float | None = None,
    min_distance: float | None = None,
    top_pct: float = 0.8,
    weights: tuple[float, float, float, float] = (10.0, 1.0, 1.0, 1.0),
    mark_radius_mm: float = 4.0,
    mark_top_n: int = 10,
    write_marker: bool = True,
    adopted_vtx: int | None = None,
    max_skull_mm: float | None = 20.0,
    max_skl_deg: float | None = 30.0,
    exclude_below_brain: bool = True,
    n_shortlist: int = 3,
    shortlist_sep_mm: float = 10.0,
) -> tuple[int, dict, int]:
    """Select the best scalp vertex for TUS placement from PlanTUS metric maps.

    Two stages: keep the vertices that pass every hard constraint, then keep
    those whose beam-ROI intersection is at least ``top_pct`` of the best, and
    order that pool by a weighted sum of normalised aim angle, distance and
    skin-skull angle. The skin-skull term is what tracks transmission; within
    a pool the aim angle is often nearly constant, so without it the ranking is
    decided by noise.

    Hard constraints, never relaxed: avoidance mask > 0; vertex at or above the
    inferior extent of brain (cranial vault, not face or neck); bone traversed
    <= ``max_skull_mm``; skin-skull angle <= ``max_skl_deg``; PlanTUS
    thresholded distance > 0; ``min_distance`` <= dist <= ``max_distance``
    when given. The ranking predicts a shortlist, not the focus; run_sweep.py
    measures the shortlist.

    Writes ``best_vtx_marker_skin.func.gii`` (top ``mark_top_n`` candidates as
    discs of ``mark_radius_mm``, value = rank) and ``best_vtx_marker_skin.foci``
    (best three white, ``adopted_vtx`` magenta) unless ``write_marker`` is False.

    Used in: step 04 (:func:`run_plantus`, :func:`describe_vtx`), run_planTUS.py,
    run_sweep.py.

    Parameters
    ----------
    target_folder:
        PlanTUS output directory holding the ``*.func.gii`` metric maps.
    max_angle, max_distance, min_distance:
        Hard bounds; ``None`` skips a distance bound. Pass the pad-adjusted
        ``min_distance`` when a gel pad is planned.
    top_pct:
        Pool threshold as a fraction of the best intersection (0.8 default;
        run_sweep.py uses 0.5 so alternatives survive).
    weights:
        Tiebreak weights ``(intersection, aim, distance, skin_skull)``; the
        first dominates by design.
    mark_radius_mm, mark_top_n, write_marker, adopted_vtx:
        Marker file controls; see above. ``adopted_vtx`` defaults to the sole
        ``vtx*`` folder if exactly one exists, -1 suppresses it.
    max_skull_mm, max_skl_deg, exclude_below_brain:
        The path constraints PlanTUS's own maps cannot express.
    n_shortlist, shortlist_sep_mm:
        Size and minimum mutual separation of the ``shortlist`` returned in
        *metrics*.

    Returns
    -------
    best_vtx : int
    metrics : dict
        ``ranked`` (every pool vertex with its scores), ``shortlist``,
        ``n_valid``, ``n_top_candidates`` and the best vertex's own values.
    relax_level : int
        Always 0; kept for callers written when the angle bound could relax.

    Raises
    ------
    ValueError
        No vertex survives the hard constraints.
    FileNotFoundError
        A required metric file is missing (run :func:`prepare_plantus_scene`).
    """
    import warnings
    import numpy as np
    import nibabel as nib

    maps = _plantus_maps(target_folder, require=tuple(_PLANTUS_MAPS))
    dist_thr, angle, avoid, inter, skl, dist_raw, _coords = (
        maps[k] for k in ("dist_thr", "angle", "avoid", "inter", "skl", "dist_raw", "coords"))

    # -- Hard safety constraints (NEVER relaxed) --------------------------
    # avoidance mask : anatomical safety (eyes, ears, superficial vessels)
    # angle bound    : transducer incidence angle limit (hard)
    # distance bounds: transducer physical focal-depth limits (skipped if None)
    safe = (avoid > 0) & (dist_thr > 0) & (angle <= max_angle)
    # Incidence on the skull was scored but never bounded, so a vertex could
    # carry any angle into the shortlist as long as its overlap was large --
    # sub-z004 alEC right offered one at 64.1 deg, where a transducer is nearly
    # side-on to the bone. Measured placements: 2.5-6.5 deg for the ones that
    # focused on target, 21.5-24.5 for the ones that missed. 30 keeps every
    # measured failure inside the set rather than tuning the bound to them.
    if max_skl_deg is not None:
        safe = safe & (skl <= max_skl_deg)
    if min_distance is not None:
        safe = safe & (dist_raw >= min_distance)
    if max_distance is not None:
        safe = safe & (dist_raw <= max_distance)

    # Two constraints PlanTUS's own maps cannot express, both added after EC
    # placements were selected that delivered essentially nothing to target.
    # Kept as hard vetoes rather than score terms: a vertex under the jaw is not
    # a worse placement, it is not a placement.
    _skull_note = ""
    if max_skull_mm is not None or exclude_below_brain:
        _m2m = target_folder.parent.parent
        _roi = find_roi_mask(target_folder)
        _rimg = nib.load(str(_roi))
        _rdat = np.squeeze(np.asanyarray(_rimg.dataobj))
        _cog = nib.affines.apply_affine(
            _rimg.affine, np.array(np.nonzero(_rdat > 0.5)).mean(axis=1))

        if exclude_below_brain:
            _floor = brain_floor_z(_m2m)
            _below = _coords[:, 2] < _floor
            if _below.any():
                safe = safe & ~_below
                _skull_note += (f"    below cranial vault (z < {_floor:.1f} mm): "
                                f"{int(_below.sum())} vertices excluded\n")

        if max_skull_mm is not None:
            _, _, _bone = skull_path_mm(_m2m, _coords, _cog)
            _thick = _bone > max_skull_mm
            safe = safe & ~_thick
            _skull_note += (f"    skull path > {max_skull_mm:.0f} mm: "
                            f"{int(_thick.sum())} vertices excluded\n")
        if _skull_note:
            print("  [select_best_vtx] path constraints\n" + _skull_note.rstrip())

    if not safe.any():
        _dist_note = (
            f"   - No vertex within distance [{min_distance}, {max_distance}] mm of target.\n"
            if (min_distance is not None or max_distance is not None) else ""
        )
        raise ValueError(
            f"No vertices satisfy hard safety constraints in {target_folder.name}.\n"
            "  Possible causes:\n"
            "    - Avoidance mask excludes all scalp vertices.\n"
            f"    - No vertex with angle <= {max_angle}° exists (try increasing max_angle_deg in transducer YAML).\n"
            + _dist_note
            + "  Check target mask, transducer YAML distance/angle settings, and avoidance mask."
        )

    # -- Two-stage vertex selection --------------------------------------
    # Stage 1: pool = safe vertices with intersection >= top_pct * max_inter
    #
    # nanmax, and NaN treated as "no intersection". PlanTUS leaves a handful of
    # NaNs in the intersection map (1 of 33,837 for sub-z002 hippocampus, 8 of
    # 35,090 for sub-z004). With a plain .max() a single NaN inside the safe set
    # made inter_safe_max NaN, so `inter >= NaN` was False everywhere,
    # top_candidates came out empty, and _norm() then died on an empty array with
    # "zero-size array to reduction operation minimum". run_plantus catches
    # ValueError, so the whole automatic suggestion — and the marker overlay —
    # silently vanished for every hippocampus target while aMCC (no NaNs) worked.
    inter = np.nan_to_num(inter, nan=0.0)
    inter_safe_max = float(inter[safe].max())
    if inter_safe_max == 0:
        warnings.warn(
            f"[select_best_vtx] Beam-ROI intersection is 0 for all safe vertices "
            f"in {target_folder.name}.\n"
            "  Possible causes:\n"
            "    - Target mask did not register into native space correctly (check step 3).\n"
            "    - Target is too deep for this transducer's focal range.\n"
            "  Falling back to angle + distance minimisation only.",
            stacklevel=2,
        )
        print(
            f"[WARNING] [select_best_vtx] Intersection = 0 for all safe vertices.\n"
            "  Placement is based on angle + distance only — verify target registration."
        )
    top_candidates = safe & (inter >= inter_safe_max * top_pct)

    # Stage 2: tiebreak within pool — minimise normalised angle + distance
    # Normalise each to [0, 1] over the top_candidates pool only.
    if not top_candidates.any():
        # Reachable only if the pool logic above regresses; previously this fell
        # through to _norm() and surfaced as an opaque numpy reduction error.
        raise ValueError(
            f"No top candidates in {target_folder.name} despite "
            f"{int(safe.sum()):,} safe vertices (max intersection "
            f"{inter_safe_max:.2f} mm, top_pct={top_pct}).\n"
            "  This is a bug in the candidate-pool filter, not a data problem."
        )

    def _rank(arr: "np.ndarray", mask: "np.ndarray", high_is_good: bool = False):
        """Rank inside the pool, 0 = best, 1 = worst, ties averaged."""
        vals = arr[mask].astype(float)
        if high_is_good:
            vals = -vals
        order = np.argsort(vals, kind="stable")
        r = np.empty(len(vals), dtype=float)
        r[order] = np.arange(len(vals), dtype=float)
        # average the ranks of equal values so ties cannot be broken by the
        # order the vertices happen to sit in the array
        _u, _inv = np.unique(vals, return_inverse=True)
        _sum = np.bincount(_inv, weights=r)
        _cnt = np.bincount(_inv)
        r = (_sum / _cnt)[_inv]
        out = np.full(arr.shape, np.inf, dtype=float)
        out[mask] = r / max(len(vals) - 1, 1)
        return out

    # skl is 0 wherever PlanTUS masked the metric out, which would read as a
    # perfect incidence.  Those vertices are already excluded by `avoid > 0`
    # (verified: 0 exact zeros inside the safe set for both UMD subjects,
    # against ~30 % of all vertices overall), so no extra guard is needed here.
    #
    # Intersection is scored here as well as used for the cutoff. With the
    # cutoff alone at top_pct=0.5 a vertex only had to reach half the best
    # overlap to enter the pool, after which it competed on angles only: for
    # sub-z004 alEC right that selected 8.27 mm of beam-in-ROI over 16.44 mm,
    # on an aim-angle difference of one degree, and the placement failed.
    #
    # Ranks rather than min-max values, because the four metrics have no common
    # scale and a single outlier in any of them compresses the rest of that
    # term to near zero, silently handing the decision to whichever metric
    # happens to be evenly spread.
    inter_rank = _rank(inter,    top_candidates, high_is_good=True)
    angle_rank = _rank(angle,    top_candidates)
    dist_rank  = _rank(dist_raw, top_candidates)
    skl_rank   = _rank(skl,      top_candidates)
    _wi, _wa, _wd, _ws = weights
    # Score only inside the pool. _rank fills the outside with inf, and a zero
    # weight would turn that into NaN before np.where could discard it.
    score = np.full(angle.shape, np.inf, dtype=float)
    score[top_candidates] = (
        _wi * inter_rank[top_candidates]
        + _wa * angle_rank[top_candidates]
        + _wd * dist_rank[top_candidates]
        + _ws * skl_rank[top_candidates]
    )
    best_vtx = int(np.argmin(score))

    # Shortlist: the best vertex plus the next ones that sit at least
    # `shortlist_sep_mm` away, so the alternatives are genuinely different
    # approaches rather than neighbours of the winner sharing its path. The
    # surface metrics cannot say which of these will focus best -- for the eight
    # EC placements measured, beam-in-ROI ran 5.3-14.0 mm with no monotonic
    # relation to the intensity actually delivered -- so the shortlist exists to
    # be run through step 5 and judged on the result.
    _order = np.where(top_candidates)[0]
    _order = _order[np.argsort(score[_order], kind="stable")]
    _short = []
    for _v in _order:
        if all(np.linalg.norm(_coords[_v] - _coords[_q]) >= shortlist_sep_mm
               for _q in _short):
            _short.append(int(_v))
        if len(_short) >= n_shortlist:
            break
    if _short:
        print("  [select_best_vtx] shortlist (>= "
              f"{shortlist_sep_mm:.0f} mm apart):")
        for _i, _v in enumerate(_short):
            print(f"      {_i + 1}. vtx{_v:<6d} inter {inter[_v]:5.2f} mm  "
                  f"aim {angle[_v]:4.1f}°  dist {dist_raw[_v]:6.1f} mm  "
                  f"skl {skl[_v]:4.1f}°")

    angle_exceeded  = False   # angle is now a hard constraint; always satisfied
    relax_level     = 0
    effective_angle = float(angle[best_vtx])

    # -- Write the marker layer and the foci file -------------------------
    # Two objects, deliberately overlapping.  The surface layer is a *mask* of
    # the top `mark_top_n` candidates carrying their rank, and the foci file
    # marks the few that a decision actually turns on as spheres above the
    # scalp.  Best-3 appear in both; that redundancy is wanted.
    #
    # Painting all of them was the previous design and did not work.  This
    # target has 437 candidates in the pool, and 437 rank discs read as noise --
    # you cannot see a placement in them, only mottling.  Ten is enough to say
    # "the good region is here" and few enough to stay legible.
    from scipy.spatial import cKDTree as _cKDTree                # noqa: PLC0415

    _tree = _cKDTree(_coords)

    # Mask layer: rank as the value, so wb_view's hover tooltip -- which prints
    # one number from whichever layer is on top, in a format fixed inside the
    # binary -- says "this is the Nth best placement".  Painted worst-first so a
    # better rank overwrites, then each vertex re-stamped so no rank is buried.
    marker = np.full(len(dist_raw), np.nan, dtype=np.float32)
    _top = [int(v) for v in _order[:mark_top_n]]
    for _i, _v in reversed(list(enumerate(_top))):
        marker[_tree.query_ball_point(_coords[_v], mark_radius_mm)] = float(_i + 1)
    for _i, _v in enumerate(_top):
        marker[_v] = float(_i + 1)
    _disc = np.asarray(_top, dtype=int)

    # Foci: spheres, drawn above the surface rather than into it, so they cannot
    # be swallowed by a dense pool and need no overlay slot of their own.  Two
    # colours, both absent from the metric palettes underneath -- a red mark was
    # invisible against the red end of the distance map.
    # Rank of a vertex within the scored order, for the foci labels
    def _rank_of_vtx(vtx):
        hit = np.where(_order == int(vtx))[0]
        return int(hit[0]) + 1 if hit.size else "-"

    _foci_rows = [(f"BEST {_i + 1}   vtx{_v}   (rank {_rank_of_vtx(_v)})",
                   (255, 255, 255), _v) for _i, _v in enumerate(_short)]
    # Which vertex is "adopted" cannot be read from the vtx* folders: run_sweep
    # leaves one behind per candidate it solved, fifteen of them for
    # sub-z002 rHipp-R.  The only record of what was actually carried forward is
    # the thermal summary BabelBrain wrote in the m2m directory, whose name
    # carries the vertex.  Insist it be unique -- a second one means a superseded
    # placement was left on disk, and picking either by mtime would be a guess.
    if adopted_vtx is None:
        _stem = target_folder.name.replace("_mask-", "-")
        _vtxs = {int(_m.group(1)) for _f in
                 target_folder.parent.parent.glob(
                     f"{_stem}_target_vtx*-ThermalField_Summary.csv")
                 if (_m := re.search(r"_target_vtx(\d+)_", _f.name))}
        if len(_vtxs) == 1:
            adopted_vtx = _vtxs.pop()
        elif len(_vtxs) > 1:
            warnings.warn(
                f"[select_best_vtx] {len(_vtxs)} thermal summaries in "
                f"{target_folder.parent.parent.name} for {_stem} "
                f"(vtx {sorted(_vtxs)}) — cannot tell which placement is in "
                f"use, so no ADOPTED focus is written.  Delete the superseded "
                f"summary to fix.", stacklevel=2)

    if adopted_vtx is not None and 0 <= adopted_vtx < len(marker):
        _foci_rows.append(
            (f"ADOPTED   vtx{adopted_vtx}   "
             f"(rank {_rank_of_vtx(adopted_vtx)} of {len(_order)})",
             (255, 0, 255), int(adopted_vtx)))
    else:
        adopted_vtx = None

    ranked = [{
        "rank":            i + 1,
        "vtx":             int(v),
        "score":           float(score[v]),
        "angle_deg":       float(angle[v]),
        "skin_skull_deg":  float(skl[v]),
        "distance_mm":     float(dist_raw[v]),
        "intersection_mm": float(inter[v]),
        "sep_mm":          float(np.linalg.norm(_coords[v] - _coords[best_vtx])),
    } for i, v in enumerate(_order)]
    _template = nib.load(str(target_folder / _PLANTUS_MAPS["inter"]))
    # Use a minimal darray meta (Name only) — the template meta carries
    # PaletteColorMapping with MODE_AUTO_SCALE_ABSOLUTE_PERCENTAGE which
    # collapses to 0-0 when 99%+ of vertices are zero, hiding all markers.
    _darray_meta = nib.gifti.GiftiMetaData()
    _darray_meta["Name"] = "best_vtx_marker"
    _out = nib.gifti.GiftiImage(
        meta=_template.meta,
        darrays=[
            nib.gifti.GiftiDataArray(
                data=marker,
                intent=_template.darrays[0].intent,
                datatype="NIFTI_TYPE_FLOAT32",
                meta=_darray_meta,
            )
        ],
    )
    if write_marker:
        _out.to_filename(str(target_folder / "best_vtx_marker_skin.func.gii"))
        write_foci_file(target_folder, _coords, _foci_rows)

    return best_vtx, {
        "vtx_idx":           best_vtx,
        "mark_vertices":     int(_disc.size),
        "ranked":            ranked,
        "skin_skull_deg":    float(skl[best_vtx]),
        "n_valid":           int(safe.sum()),
        "shortlist":         _short,
        "n_top_candidates":  int(top_candidates.sum()),
        "distance_mm":       float(dist_raw[best_vtx]),
        "angle_deg":         float(angle[best_vtx]),
        "intersection_mm":   float(inter[best_vtx]),
        "max_inter_mm":      float(inter_safe_max),
        "top_pct":           float(top_pct),
        "angle_exceeded":    angle_exceeded,
        "max_angle_deg":     float(max_angle),
    }, relax_level


def describe_vtx(target_folder, vtx, max_angle, max_distance=None,
                 min_distance=None, top_pct=0.8,
                 weights=(10.0, 1.0, 1.0, 1.0)) -> str:
    """Return a one-line description of *vtx*: the three criteria and its rank.

    Answers the question wb_view cannot.  Its hover tooltip prints one number —
    "Top Enabled Layer" — so the vertex index is all it reliably gives; this
    turns that index into the numbers behind it.  Offered at the placement
    prompt as ``?N``, because while wb_view is open the notebook is blocked on
    that prompt and no other cell can run.

    Scoring is delegated to :func:`select_best_vtx` with ``write_marker=False``,
    so the ranking shown can never drift from the ranking that produced the
    marker.

    Used in: step 04 (the ``?N`` query inside :func:`run_plantus`).
    """
    import numpy as np                                            # noqa: PLC0415

    target_folder = Path(target_folder)
    try:
        best, m, _ = select_best_vtx(
            target_folder, max_angle=max_angle, max_distance=max_distance,
            min_distance=min_distance, top_pct=top_pct, weights=weights,
            write_marker=False)
    except (ValueError, FileNotFoundError) as _e:
        return f"  vtx{vtx}: cannot score this target — {_e}"

    by_vtx = {r["vtx"]: r for r in m["ranked"]}
    n = len(m["ranked"])
    r = by_vtx.get(int(vtx))
    if r is not None:
        return (f"  vtx{r['vtx']}   aim {r['angle_deg']:.1f}°   "
                f"skl {r['skin_skull_deg']:.1f}°   "
                f"dist {r['distance_mm']:.1f} mm   "
                f"inter {r['intersection_mm']:.2f} mm\n"
                f"             rank {r['rank']} of {n}"
                + (f"   |   {r['sep_mm']:.1f} mm from the suggestion (vtx{best})"
                   if r["rank"] > 1 else "   ← the suggestion"))

    # Outside the pool: still report the raw criteria, and say why it is out.
    try:
        maps = _plantus_maps(target_folder)
        ang, skl, dist, crd = maps["angle"], maps["skl"], maps["dist_raw"], maps["coords"]
        inter = np.nan_to_num(maps["inter"], nan=0.0)
        v = int(vtx)
        return (f"  vtx{v}   aim {ang[v]:.1f}°   skl {skl[v]:.1f}°   "
                f"dist {dist[v]:.1f} mm   inter {inter[v]:.2f} mm\n"
                f"             NOT in the candidate pool (needs inter ≥ "
                f"{m['top_pct'] * m['max_inter_mm']:.2f} mm)   |   "
                f"{np.linalg.norm(crd[v] - crd[best]):.1f} mm from the "
                f"suggestion (vtx{best})")
    except Exception as _e:
        return f"  vtx{vtx}: could not read metrics — {type(_e).__name__}: {_e}"


def stratified_seeds(target_folder, max_angle, max_distance=None,
                     min_distance=None, n_levels=7, min_sep_mm=10.0,
                     exclude=(), include_contra=False) -> list[int]:
    """Candidate vertices sampled across the whole beam-ROI overlap range.

    The shortlist takes the top of the overlap ranking, and on some targets
    that top misses while mid-ranked vertices hit: a long chord through the
    ROI implies an oblique approach that costs more at the skull than it
    gains. This is the fallback. The pool (:func:`select_best_vtx` at
    ``top_pct=0.01``) is cut into *n_levels* quantile bins of overlap and each
    bin contributes the vertex furthest from every vertex already chosen, so
    the seeds are distinct approaches. Contralateral entries are dropped
    unless *include_contra*; they cross the whole brain.

    Used in: run_sweep.py (``--stratify``).

    Parameters
    ----------
    target_folder, max_angle, max_distance, min_distance:
        As for :func:`select_best_vtx`; give the pad-adjusted minimum.
    n_levels, min_sep_mm, exclude:
        Number of bins (at most one seed each); minimum distance from any
        vertex already chosen; vertices already solved, which anchor that
        separation test.

    Returns
    -------
    list of int
        Seed vertex indices in ascending overlap order.
    """
    import numpy as np                                            # noqa: PLC0415
    import nibabel as nib                                         # noqa: PLC0415
    from scipy import ndimage                                     # noqa: PLC0415

    target_folder = Path(target_folder)
    _, m, _ = select_best_vtx(
        target_folder, max_angle=max_angle, max_distance=max_distance,
        min_distance=min_distance, top_pct=0.01, write_marker=False)
    pool = m["ranked"]
    coords = _plantus_maps(target_folder)["coords"]

    # Drop entries on the far side of the midline from the ROI
    if not include_contra:
        roi = nib.load(str(find_roi_mask(target_folder)))
        roi_x = nib.affines.apply_affine(
            roi.affine, ndimage.center_of_mass(roi.get_fdata() > 0))[0]
        pool = [r for r in pool if coords[r["vtx"], 0] * roi_x >= 0]
    if not pool:
        return []

    inter = np.array([r["intersection_mm"] for r in pool])
    vtx = np.array([r["vtx"] for r in pool])
    edges = np.quantile(inter, np.linspace(0, 1, n_levels + 1))
    chosen = [int(v) for v in exclude]
    seeds = []

    # One seed per overlap bin: the vertex furthest from everything chosen so far
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = np.where((inter >= lo) & (inter <= hi))[0]
        if not sel.size:
            continue
        if chosen:
            gap = np.min([np.linalg.norm(coords[vtx[sel]] - coords[c], axis=1)
                          for c in chosen], axis=0)
        else:
            gap = np.full(sel.size, np.inf)
        if gap.max() < min_sep_mm:
            continue
        pick = int(vtx[sel[np.argmax(gap)]])
        chosen.append(pick)
        seeds.append(pick)
    return seeds


def write_depth_report(target_folder, vtx, additional_offset, subject_id,
                       skin_to_roi_cog_mm=None):
    """Write ``{roi}_depth_vtx{N}.txt`` from what PlanTUS left in ``vtx{N}/``.

    The report copies PlanTUS's own numbers and adds the pad and two derived
    values; nothing else is recomputed. Until 2026-09-21 the writer ran before
    the placement and took the skin distance from PlanTUS's distance map,
    which is measured to the ROI centre of gravity, whereas PlanTUS aims at
    the midpoint of the beam's chord through the ROI. For elongated ROIs the
    two differ by up to 10 mm (cHipp), so the TPO setting handed to the
    operator and the standoff simulated at step 5 were both off by that much.

    Fields (definitions in ``config/basics/simulation_metrics.md``, section 1):

    - ``plantus_focal_distance_mm``: PlanTUS's planned focal distance, read
      from the name of ``focus_*_vtx{N}_{fd}.nii.gz``: scalp vertex to chord
      midpoint plus the pad
    - ``plantus_entry_ras``, ``plantus_focus_ras``: scalp vertex and focus
      position, native RAS mm, as PlanTUS wrote them
    - ``additional_offset_mm_assumed``: the pad the placement was planned with
    - ``skin_to_ROI_cog_mm``: PlanTUS's distance map at this vertex (to the
      ROI centre of gravity); what the selection bounds use, not a focal depth
    - ``exit_plane_to_ROI_distance_mm``: = ``plantus_focal_distance_mm``, the
      TPO setting; kept under this name because step 5 reads it
    - ``skin_to_target_mm``: = ``plantus_focal_distance_mm`` - pad
    - ``focus_to_entry_plus_pad_mm``: |focus - entry| + pad from PlanTUS's
      matrices; a check on the file-name value, warned about beyond 0.2 mm

    Used in: step 04 (:func:`run_plantus_placement`), :func:`rewrite_depth_reports`.
    """
    import re                                                     # noqa: PLC0415
    import warnings                                               # noqa: PLC0415
    import numpy as np                                            # noqa: PLC0415

    target_folder = Path(target_folder)
    vtx = int(vtx)
    pad = float(additional_offset)
    vtx_dir = target_folder / f"vtx{vtx}"
    focus = sorted(p for p in vtx_dir.glob(f"focus_*_vtx{vtx}_*.nii.gz")
                   if not p.name.endswith("_small.nii.gz"))
    if not focus:
        raise FileNotFoundError(f"No PlanTUS focus file in {vtx_dir}; run the placement first.")
    fd = float(re.search(r"_vtx\d+_([\d.]+)\.nii\.gz$", focus[0].name).group(1))
    entry, target = get_vtx_coordinates(vtx_dir, target_folder, vtx)
    entry, target = np.asarray(entry, float), np.asarray(target, float)
    check = float(np.linalg.norm(target - entry)) + pad
    if abs(check - fd) > 0.2:
        warnings.warn(f"vtx{vtx}: |focus - entry| + pad = {check:.2f} mm but PlanTUS "
                      f"wrote {fd:.1f} mm", stacklevel=2)
    if skin_to_roi_cog_mm is None:
        dist_file = target_folder / "skin_target_distances.npy"
        skin_to_roi_cog_mm = (float(np.load(dist_file)[vtx]) if dist_file.is_file()
                              else float("nan"))
    roi_name = target_folder.name
    out = target_folder / f"{roi_name}_depth_vtx{vtx}.txt"
    out.write_text("\n".join([
        "# PlanTUS placement: values PlanTUS wrote, copied, not recomputed",
        f"subject_id: {subject_id}",
        f"ROI: {roi_name}",
        f"vertex_index: {vtx}",
        f"plantus_focal_distance_mm: {fd:.1f}",
        f"plantus_entry_ras: {entry[0]:.3f} {entry[1]:.3f} {entry[2]:.3f}",
        f"plantus_focus_ras: {target[0]:.3f} {target[1]:.3f} {target[2]:.3f}",
        "# planning inputs",
        f"additional_offset_mm_assumed: {pad:.4f}",
        f"skin_to_ROI_cog_mm: {skin_to_roi_cog_mm:.4f}",
        "# derived; definitions in config/basics/simulation_metrics.md section 1",
        f"exit_plane_to_ROI_distance_mm: {fd:.1f}",
        f"skin_to_target_mm: {fd - pad:.1f}",
        f"focus_to_entry_plus_pad_mm: {check:.2f}",
    ]) + "\n")
    print(f"Depth report: vtx{vtx}  TPO focal distance {fd:.1f} mm "
          f"(pad {pad:.0f} mm)  -> {out.name}")
    return out


def rewrite_depth_reports(target_folder, subject_id=None):
    """Rewrite every depth report in a target folder from its PlanTUS placement.

    The pad comes from the existing report (``additional_offset_mm_assumed``),
    everything else from ``vtx{N}/``. Returns the vertices rewritten. Written
    for the 2026-09-21 change of the report's distance from the ROI centre of
    gravity to PlanTUS's own focal distance; every placement made before that
    day carries the old value until this has run.

    Used in: bookkeeping (one-off regeneration), :func:`write_vertices_explored` callers.
    """
    target_folder = Path(target_folder)
    if subject_id is None:
        subject_id = target_folder.name.split("_")[0]
    done = []
    for vtx_dir in sorted(target_folder.glob("vtx*")):
        if not vtx_dir.is_dir() or not any(vtx_dir.glob("focus_*.nii.gz")):
            continue
        vtx = int(vtx_dir.name[3:])
        try:
            pad = float(read_depth_report(target_folder, vtx=vtx)
                        .get("additional_offset_mm_assumed", 0.0))
        except (FileNotFoundError, ValueError):
            pad = 0.0
        write_depth_report(target_folder, vtx, pad, subject_id)
        done.append(vtx)
    return done


def _tpo_depth_mm(report):
    """The TPO focal-depth setting from a depth report, old or new format."""
    return report.get("exit_plane_to_ROI_distance_mm", report.get("focal_distance_fd_mm"))


def _write_plantus_metric(PlanTUS, output_path, name, values):
    """Write one per-vertex map as ``{name}_skin.func.gii`` in *output_path*.

    The three PlanTUS calls every metric needs: write the array onto
    ``skin.surf.gii``, mask it with the avoidance map, and stamp the structure
    wb_view expects.

    Used by: :func:`prepare_plantus_scene`.
    """
    out = str(output_path)
    PlanTUS.create_metric_from_pseudo_nifti(name, values, out + "/skin.surf.gii")
    PlanTUS.mask_metric(out + f"/{name}_skin.func.gii", out + "/avoidance_skin.func.gii")
    PlanTUS.add_structure_information(out + f"/{name}_skin.func.gii", "CORTEX_LEFT")


def _chord_lengths_mm(intersections):
    """Beam length inside the ROI per scalp vertex, from PlanTUS ray-mesh hits.

    Two hits are one chord, four are two (a concave ROI), more than four is
    left NaN, fewer than two is a miss (0): PlanTUS's own convention, kept so
    the map matches what the GUI shows.

    Used by: :func:`prepare_plantus_scene`.
    """
    import numpy as np                                            # noqa: PLC0415

    values = []
    for ints in intersections:
        n = len(ints)
        if n == 2:
            values.append(np.linalg.norm(np.asarray(ints[1]) - np.asarray(ints[0])))
        elif n == 4:
            values.append(np.linalg.norm(np.asarray(ints[1]) - np.asarray(ints[0]))
                          + np.linalg.norm(np.asarray(ints[3]) - np.asarray(ints[2])))
        elif n > 4:
            values.append(np.nan)
        else:
            values.append(0)
    return np.asarray(values)


def _skin_skull_angles(PlanTUS, output_path):
    """Scalp-normal against nearest skull-normal angle per vertex, folded to [0, 90].

    The scalp-normal ray is cast at the skull shell (``skull.stl``) and the
    skull vertex nearest the first hit supplies the normal; a ray that misses
    gets 0, as in PlanTUS. Folding is :func:`_fold_obliquity`, applied here so
    the wb_view overlay shows the same obliquity the selection and the reports
    use.

    Used by: :func:`prepare_plantus_scene`.
    """
    import numpy as np                                            # noqa: PLC0415

    out = str(output_path)
    skin_coordinates, skin_normals = PlanTUS.compute_surface_metrics(out + "/skin.surf.gii")
    skull_coordinates, skull_normals = PlanTUS.compute_surface_metrics(out + "/skull.surf.gii")
    skin_skull_intersections = PlanTUS.compute_vector_mesh_intersections(
        skin_coordinates, skin_normals, out + "/skull.stl", 40
    )
    indices_closest = []
    for i in np.arange(len(skin_coordinates)):
        try:
            ic = skin_skull_intersections[i][0]
            indices_closest.append(int(np.argmin(np.linalg.norm(skull_coordinates - ic, axis=1))))
        except Exception:
            indices_closest.append(0)
    skin_skull_angle_list = []
    for i in np.arange(len(skin_coordinates)):
        try:
            a = math.degrees(PlanTUS.angle_between_vectors(skin_normals[i], skull_normals[indices_closest[i]]))
            skin_skull_angle_list.append(a)
        except Exception:
            skin_skull_angle_list.append(0)
    _skl_raw    = np.asarray(skin_skull_angle_list)
    _skl_folded = _fold_obliquity(_skl_raw)
    _n_folded   = int((_skl_raw > 90.0).sum())
    if _n_folded:
        print(f"Skin-skull angle: folded {_n_folded} of {_skl_raw.size} vertices "
              f"from >90° into [0, 90] (ray hit the inner table)")
    return _skl_folded


def _write_placeholder_markers(output_path):
    """Write empty marker and foci files so the scene can always open.

    The scene names ``best_vtx_marker_skin.func.gii`` and
    ``best_vtx_marker_skin.foci``, but both are only written later, by
    :func:`select_best_vtx` inside the placement step. When that selection
    fails the files never appear and wb_view refuses the scene with "file
    cannot be loaded", permanently, since nothing revisits it; four targets
    were left that way by the NaN bug in the intersection map. An all-NaN
    marker renders transparent and an empty FociFile draws nothing, so an
    unselected target looks as before, and the real files overwrite these.

    Used by: :func:`prepare_plantus_scene`.
    """
    import nibabel as nib                                         # noqa: PLC0415
    import numpy as np                                            # noqa: PLC0415

    _marker_path = output_path / "best_vtx_marker_skin.func.gii"
    if not _marker_path.is_file():
        _tmpl = nib.load(str(output_path / "target_intersection_skin.func.gii"))
        _meta = nib.gifti.GiftiMetaData()
        _meta["Name"] = "best_vtx_marker"
        nib.gifti.GiftiImage(
            meta=_tmpl.meta,
            darrays=[nib.gifti.GiftiDataArray(
                data=np.full(np.asarray(_tmpl.darrays[0].data).shape[0],
                             np.nan, dtype=np.float32),
                intent=_tmpl.darrays[0].intent,
                datatype="NIFTI_TYPE_FLOAT32",
                meta=_meta,
            )],
        ).to_filename(str(_marker_path))
        print("Placeholder marker written → best_vtx_marker_skin.func.gii "
              "(replaced once a vertex is selected)")

    _foci_path = output_path / "best_vtx_marker_skin.foci"
    if not _foci_path.is_file():
        _foci_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<FociFile Version="2">\n'
            '   <MetaData/>\n'
            '   <FociClassColorTable>\n      <LabelTable>\n'
            '         <Label Key="0" Red="1" Green="1" Blue="1" Alpha="0"><![CDATA[???]]></Label>\n'
            '      </LabelTable>\n   </FociClassColorTable>\n'
            '   <FociNameColorTable>\n      <LabelTable>\n'
            '         <Label Key="0" Red="1" Green="1" Blue="1" Alpha="0"><![CDATA[???]]></Label>\n'
            '      </LabelTable>\n   </FociNameColorTable>\n'
            '</FociFile>\n', encoding="utf-8")
        print("Placeholder foci written → best_vtx_marker_skin.foci")


def _inject_marker_into_scene(scene_path):
    """Make the PlanTUS scene load and show the marker layer and the foci.

    Three edits to the scene XML PlanTUS wrote from its template: the marker
    METRIC and FOCI files are appended to ``dataFilesArray``; the foci display
    defaults are switched on (they load invisible otherwise); and overlay slot
    0 of the three metric tabs is retargeted from the thresholded-distance map
    to the marker, because every tab has exactly three overlay slots and all
    are taken, so a loaded marker was never drawn. Never raises: a failed
    injection is reported and the scene stays usable by hand.

    Used by: :func:`prepare_plantus_scene`.
    """
    # The template has 9 entries; we append Element Index="9" for the marker
    # METRIC file and bump the dataFilesArray Length from 9 to 10.
    try:
        scene_txt = scene_path.read_text(encoding="utf-8")
        _marker_entry = (
            '\n                                    <Element Index="9">'
            '\n                                        <Object Type="class" Class="SpecFileDataFile" Name="specFileDataFile" Version="1">'
            '\n                                            <Object Type="enumeratedType" Name="dataFileType">METRIC</Object>'
            '\n                                            <Object Type="enumeratedType" Name="structure">CORTEX_LEFT</Object>'
            '\n                                            <Object Type="pathName" Name="fileName">./best_vtx_marker_skin.func.gii</Object>'
            '\n                                            <Object Type="boolean" Name="selected">true</Object>'
            '\n                                        </Object>'
            '\n                                    </Element>'
            '\n                                    <Element Index="10">'
            '\n                                        <Object Type="class" Class="SpecFileDataFile" Name="specFileDataFile" Version="1">'
            '\n                                            <Object Type="enumeratedType" Name="dataFileType">FOCI</Object>'
            '\n                                            <Object Type="enumeratedType" Name="structure">ALL</Object>'
            '\n                                            <Object Type="pathName" Name="fileName">./best_vtx_marker_skin.foci</Object>'
            '\n                                            <Object Type="boolean" Name="selected">true</Object>'
            '\n                                        </Object>'
            '\n                                    </Element>'
            '\n                                </ObjectArray>'
        )
        # Bump only the dataFilesArray Length (not allCaretDataFiles_V2)
        scene_txt = scene_txt.replace(
            'Name="dataFilesArray" Length="9">',
            'Name="dataFilesArray" Length="11">',
        )
        # Replace the last </ObjectArray> that closes dataFilesArray
        # (identified by the Element Index="8" block ending just before it)
        _close_marker = (
            "                                    </Element>\n"
            "                                </ObjectArray>\n"
            "                            </Object>\n"
            "                            <Object Type=\"class\" Class=\"CaretDataFile\" Name=\"m_sceneAnnotationFile\""
        )
        _close_with_entry = (
            "                                    </Element>"
            + _marker_entry
            + "\n"
            "                            </Object>\n"
            "                            <Object Type=\"class\" Class=\"CaretDataFile\" Name=\"m_sceneAnnotationFile\""
        )
        if _close_marker in scene_txt:
            scene_txt = scene_txt.replace(_close_marker, _close_with_entry, 1)
        else:
            print("[warn] Could not inject marker into scene.scene (anchor not found); load manually.")

        # ── Turn the foci on ──────────────────────────────────────────────
        # Three defaults have to be overridden or the file loads and nothing is
        # drawn, which is exactly how this failed the first time it was tried:
        #
        #   m_displayStatus*   false          -> true    foci are off by default
        #   DRAW_AS_SQUARES                   -> SPHERES
        #   size 4 mm                         -> 5 mm    matches the sphere
        #                                                wb_view draws at the
        #                                                vertex you just clicked
        #                                                (m_identifcationMostRecent-
        #                                                SymbolSize, its typo)
        #
        # Confined to the DisplayPropertiesFoci block: m_displayStatusInTab and
        # friends are generic names that borders and fibre orientations use too,
        # and those are deliberately off.
        _i = scene_txt.find('Name="displayPropertiesFoci"')
        _j = scene_txt.find('Class="DisplayProperties', _i + 10)
        if _i != -1 and _j != -1:
            _blk = scene_txt[_i:_j]
            for _key in ("m_displayStatusInTab", "m_displayStatusInDisplayGroup"):
                _m = re.search(r'Name="%s"[^>]*>(.*?)</Object(?:Map|Array)>' % _key,
                               _blk, re.S)
                if _m:
                    _blk = (_blk[:_m.start(1)]
                            + _m.group(1).replace(">false<", ">true<")
                            + _blk[_m.end(1):])
            _blk = _blk.replace("DRAW_AS_SQUARES", "DRAW_AS_SPHERES")
            _blk = _blk.replace(">4<", ">5<")
            scene_txt = scene_txt[:_i] + _blk + scene_txt[_j:]
        else:
            print("[warn] displayPropertiesFoci not found in scene.scene; "
                  "enable Foci from the Features toolbox manually.")

        # ── Put the marker on a layer that is actually drawn ──────────────
        # Being in dataFilesArray only makes wb_view *load* the file.  Every
        # tab has exactly three overlay slots and all three are taken, so the
        # marker was loaded and never displayed.  Retarget slot 0 — the
        # thresholded-distance map, a binary feasibility mask — in the three
        # tabs that hold it.  Their slot 1 keeps the informative metric
        # (distances / intersection / angles), and the fourth surface tab is
        # left alone as a marker-free reference view.
        #
        # Growing the array to a fourth slot would mean synthesising a whole
        # Overlay element into all ten tabs; retargeting an existing one is far
        # less fragile.
        _n_over = 0
        for _tag, _val in (('pathName', './distances_skin_thresholded.func.gii'),
                           ('string',   'distances_skin_thresholded.func.gii')):
            _old = (f'<Object Type="{_tag}" Name="selectedMapFile'
                    f'{"NameWithPath" if _tag == "pathName" else ""}">{_val}</Object>')
            _new = _old.replace('distances_skin_thresholded', 'best_vtx_marker_skin')
            _n_over += scene_txt.count(_old)
            scene_txt = scene_txt.replace(_old, _new)

        scene_path.write_text(scene_txt, encoding="utf-8")
        if _n_over == 6:          # three overlays × two fields each
            print("Marker injected and shown on 3 overlay layers → scene.scene")
        else:
            print(f"[warn] Expected 6 overlay field replacements, made {_n_over}. "
                  f"The marker may not be visible; select "
                  f"best_vtx_marker_skin.func.gii as an overlay in wb_view.")
    except Exception as _e:
        print(f"[warn] Scene marker injection failed: {_e}; load best_vtx_marker_skin.func.gii manually.")


def prepare_plantus_scene(
    sub_id_full: str,
    sub_id_bare: str,
    m2m_dir: Path,
    target_name: str,
    target_side: str,
    tp: dict,
    dry_run: bool = False,
) -> Path:
    """Prepare PlanTUS surfaces, metric maps and the Workbench scene for one target.

    Writes to ``m2m_dir/PlanTUS/<target_roi_name>/``, including
    ``skin_target_distances.npy`` for :func:`run_plantus_placement`.

    Used in: step 04a, run_planTUS.py, run_sweep.py.

    Parameters
    ----------
    sub_id_full, sub_id_bare, m2m_dir, target_name, target_side, tp:
        ``"sub-NS"`` / ``"NS"``, the ``m2m_{sub_id_full}/`` directory, the
        PlanTUS target label (e.g. ``"aMCC_NeuroSynthTopic112"``), the side
        suffix ``"_R"`` / ``"_L"`` / ``""``, and the :func:`transducer_params`
        dict. The other step-4 functions take the same six and refer here.
    dry_run:
        Validate paths and print without running.

    Returns
    -------
    Path
        The PlanTUS output directory.
    """
    import numpy as np

    if str(_PLANTUS_CODE) not in sys.path:
        sys.path.append(str(_PLANTUS_CODE))
    _saved_cwd = os.getcwd()
    os.chdir(str(_PLANTUS_CODE))
    import PlanTUS  # noqa: PLC0415

    t1_filepath  = m2m_dir / "T1.nii.gz"
    simnibs_mesh = m2m_dir / f"{sub_id_full}.msh"

    if not t1_filepath.exists():
        sys.exit(f"ERROR: T1 not found: {t1_filepath}")
    if not simnibs_mesh.exists():
        sys.exit(f"ERROR: SimNIBS mesh not found: {simnibs_mesh}")

    subject_dir  = m2m_dir.parent
    mask_pattern = f"*_{target_name}{mask_suffix(target_side)}.nii.gz"
    matches      = list(subject_dir.rglob(mask_pattern))
    if not matches:
        sys.exit(
            f"ERROR: target mask not found under {subject_dir}\n"
            f"  Pattern: {mask_pattern}"
        )
    target_roi_filepath = str(matches[0])
    print("Target mask:", target_roi_filepath)

    target_roi_filename = os.path.basename(target_roi_filepath)
    target_roi_name     = target_roi_filename.replace(".nii.gz", "").replace(".nii", "")
    output_path         = m2m_dir / "PlanTUS" / target_roi_name
    os.makedirs(str(output_path), exist_ok=True)
    shutil.copy(target_roi_filepath, str(output_path) + "/")
    target_roi_filepath = str(output_path) + "/" + target_roi_filename

    if dry_run:
        print("[dry-run] Would prepare PlanTUS scene for:", sub_id_full, "|", target_roi_name)
        print("[dry-run] Output:", output_path)
        os.chdir(_saved_cwd)
        return output_path

    max_d     = tp["max_distance"]
    diam      = tp["transducer_diameter"]
    scene_tpl = tp["scene_template_path"]
    out       = str(output_path)
    skin_surf = out + "/skin.surf.gii"

    print("Converting SimNIBS mesh to surface files…")
    PlanTUS.convert_simnibs_mesh_to_surface(str(simnibs_mesh), [1005], "skin", out)
    PlanTUS.add_structure_information(skin_surf, "CORTEX_LEFT")
    PlanTUS.convert_simnibs_mesh_to_surface(str(simnibs_mesh), [1007, 1008], "skull", out)
    PlanTUS.add_structure_information(out + "/skull.surf.gii", "CORTEX_RIGHT")

    PlanTUS.create_avoidance_mask(str(simnibs_mesh), skin_surf, diam / 2)

    # Distance to the ROI centre, plus the copy thresholded at the transducer maximum
    target_center         = PlanTUS.roi_center_of_gravity(target_roi_filepath)
    skin_target_distances = PlanTUS.distance_between_surface_and_point(skin_surf, target_center)
    _write_plantus_metric(PlanTUS, output_path, "distances", skin_target_distances)
    PlanTUS.threshold_metric(out + "/distances_skin.func.gii", max_d)
    PlanTUS.mask_metric(out + "/distances_skin_thresholded.func.gii", out + "/avoidance_skin.func.gii")
    PlanTUS.add_structure_information(out + "/distances_skin_thresholded.func.gii", "CORTEX_LEFT")

    # Aim angle: scalp normal against the ray to the ROI centre
    _, skin_normals = PlanTUS.compute_surface_metrics(skin_surf)
    skin_target_vectors = PlanTUS.vectors_between_surface_and_point(skin_surf, target_center)
    skin_target_angles = np.abs(np.array([
        math.degrees(PlanTUS.angle_between_vectors(skin_target_vectors[i], skin_normals[i]))
        for i in np.arange(len(skin_target_vectors))
    ]))
    _write_plantus_metric(PlanTUS, output_path, "angles", skin_target_angles)

    # Beam-ROI intersection: chord of the scalp-normal ray through the ROI mesh
    PlanTUS.stl_from_nii(target_roi_filepath, 0.25)
    skin_coordinates, skin_normals = PlanTUS.compute_surface_metrics(skin_surf)
    skin_target_intersections = PlanTUS.compute_vector_mesh_intersections(
        skin_coordinates, skin_normals, out + "/" + target_roi_name + "_3Dmodel.stl", 200
    )
    _write_plantus_metric(PlanTUS, output_path, "target_intersection",
                          _chord_lengths_mm(skin_target_intersections))

    # Skin-skull angle, folded to [0, 90]
    _write_plantus_metric(PlanTUS, output_path, "skin_skull_angles",
                          _skin_skull_angles(PlanTUS, output_path))

    scene_variable_names = [
        "SKIN_SURFACE_FILENAME",  "SKIN_SURFACE_FILEPATH",
        "SKULL_SURFACE_FILENAME", "SKULL_SURFACE_FILEPATH",
        "DISTANCES_FILENAME",     "DISTANCES_FILEPATH",
        "INTERSECTION_FILENAME",  "INTERSECTION_FILEPATH",
        "ANGLES_FILENAME",        "ANGLES_FILEPATH",
        "ANGLES_SKIN_SKULL_FILENAME", "ANGLES_SKIN_SKULL_FILEPATH",
        "DISTANCES_MAX_FILENAME", "DISTANCES_MAX_FILEPATH",
        "T1_FILENAME",            "T1_FILEPATH",
        "MASK_FILENAME",          "MASK_FILEPATH",
    ]
    scene_variable_values = [
        "skin.surf.gii",  "./skin.surf.gii",
        "skull.surf.gii", "./skull.surf.gii",
        "distances_skin.func.gii",              "./distances_skin.func.gii",
        "target_intersection_skin.func.gii",    "./target_intersection_skin.func.gii",
        "angles_skin.func.gii",                 "./angles_skin.func.gii",
        "skin_skull_angles_skin.func.gii",      "./skin_skull_angles_skin.func.gii",
        "distances_skin_thresholded.func.gii",  "./distances_skin_thresholded.func.gii",
        "T1.nii.gz",         "../../T1.nii.gz",
        target_roi_filename, "./" + target_roi_filename,
    ]
    PlanTUS.create_scene(scene_tpl, out + "/scene.scene", scene_variable_names, scene_variable_values)
    print("Scene created:", out + "/scene.scene")
    print("Open in Workbench: wb_view", out + "/scene.scene")

    # The scene names the marker and foci files before select_best_vtx writes
    # them, and it must load and show them once it does.
    _write_placeholder_markers(output_path)
    _inject_marker_into_scene(output_path / "scene.scene")

    # Save distances array so step04b / run_plantus_placement can load it
    np.save(str(output_path / "skin_target_distances.npy"), skin_target_distances)
    print("Distances saved →", str(output_path / "skin_target_distances.npy"))

    os.chdir(_saved_cwd)
    return output_path


def list_plantus_vertices(target_folder, print_table: bool = True) -> list[dict]:
    """Every placement that exists for one PlanTUS target, with its metrics.

    Reads the same per-vertex maps :func:`select_best_vtx` ranks on. ``inter``
    is the axis clip at that one vertex and is knife-edge; ``inter_near_mm``
    is the best value within 5 mm and is what tells an edge vertex from a
    miss. ``angle_deg`` (aim, filtered on) and ``skin_skull_deg`` (obliquity
    at bone, what derating follows) are different angles and both are shown.

    Used in: step 04, step 05, run_sweep.py.

    Parameters
    ----------
    target_folder, print_table:
        Per-target PlanTUS directory; also print the table, newest placement
        marked.

    Returns
    -------
    list of dict
        One per vertex, sorted by index. Keys: ``vtx``, ``dist_mm``, ``fd_mm``,
        ``angle_deg``, ``skin_skull_deg``, ``inter_mm``, ``inter_near_mm``,
        ``entry``, ``side`` (``contra`` when entry and target lie on opposite
        sides of x = 0), ``path_mm``, ``elev_deg`` and ``azim_deg`` (entry
        relative to the aimed point: elevation above it; azimuth 0 = lateral,
        +90 = anterior, -90 = posterior), ``has_folder``, ``has_figure``,
        ``has_trajectory``. Vertices with a depth report but no folder are
        included with ``has_folder=False``.
    """
    import re as _re

    import numpy as _np

    folder = Path(target_folder)
    _maps  = _plantus_maps(folder)
    _dist, _ang, _sskul, _inter, _crd = (
        _maps[k] for k in ('dist_raw', 'angle', 'skl', 'inter', 'coords'))

    def _inter_near(v, radius=5.0):
        """Best axis-clip length within *radius* mm of vertex *v*.

        Distinguishes "this vertex sits at the edge of the intersecting patch"
        from "there is no intersecting scalp anywhere near it".
        """
        if _inter is None or _crd is None:
            return None
        _pos = _np.where(_np.nan_to_num(_inter) > 0)[0]
        if _pos.size == 0:
            return 0.0
        _near = _pos[_np.linalg.norm(_crd[_pos] - _crd[v], axis=1) <= radius]
        return round(float(_np.nan_to_num(_inter)[_near].max()), 2) if _near.size else 0.0

    vtx_dirs = {int(p.name.replace('vtx', '')): p
                for p in folder.glob('vtx*') if p.is_dir()}
    reports = {}
    for p in folder.glob('*_depth_vtx*.txt'):
        m = _re.search(r'vtx0*(\d+)\.txt$', p.name)
        if m:
            reports[int(m.group(1))] = p

    out = []
    for v in sorted(set(vtx_dirs) | set(reports)):
        vd = vtx_dirs.get(v)
        entry = side = path_mm = elev_deg = azim_deg = None
        if vd is not None:
            try:
                e, t = get_vtx_coordinates(vd, folder, v)
                e, t = _np.asarray(e, float), _np.asarray(t, float)
                entry   = tuple(round(float(c), 1) for c in e)
                side    = 'contra' if e[0] * t[0] < 0 else 'ipsi'
                path_mm = round(float(_np.linalg.norm(t - e)), 1)

                # Where the entry sits relative to the aimed point: elevation
                # above it, and azimuth in the axial plane with 0 = lateral,
                # +90 = anterior, -90 = posterior, lateral taken away from the
                # midline on the target's own side
                d = e - t
                lateral = d[0] if t[0] >= 0 else -d[0]
                elev_deg = round(float(_np.degrees(
                    _np.arctan2(d[2], _np.hypot(d[0], d[1])))), 1)
                azim_deg = round(float(_np.degrees(_np.arctan2(d[1], lateral))), 1)
            except Exception:
                pass
        traj = folder.glob(f'*_vtx{v}_brainsight.txt')
        out.append({
            'vtx':            v,
            'dist_mm':        None if _dist  is None else round(float(_dist[v]), 1),
            'fd_mm':          (_tpo_depth_mm(read_depth_report(folder, vtx=v))
                               if v in reports else None),
            'angle_deg':      None if _ang   is None else round(float(_ang[v]), 1),
            'skin_skull_deg': None if _sskul is None else round(float(_sskul[v]), 1),
            'inter_mm':       None if _inter is None
                              else round(float(_np.nan_to_num(_inter[v])), 2),
            'inter_near_mm':  _inter_near(v),
            'entry':          entry,
            'side':           side,
            'path_mm':        path_mm,
            'elev_deg':       elev_deg,
            'azim_deg':       azim_deg,
            'has_folder':     vd is not None,
            'has_figure':     bool(vd and (vd / f'vtx{v}_placement.png').is_file()),
            'has_trajectory': any(traj),
        })

    if print_table and out:
        newest = (max(vtx_dirs, key=lambda k: vtx_dirs[k].stat().st_mtime)
                  if vtx_dirs else None)
        print(f'{len(out)} placement(s) in {folder.name}:')
        print(f"  {'vtx':>7} {'dist':>6} {'fd':>6} {'aim°':>5} {'skl°':>5} "
              f"{'inter':>6} {'≤5mm':>6} {'elev°':>6} {'az°':>6} {'side':>6}  "
              f"{'traj':>4} {'fig':>4}  entry")
        for r in out:
            fmt = lambda v, w, p=1: (f'{v:{w}.{p}f}' if isinstance(v, float)
                                     else ' ' * (w - 1) + '-')
            print(f"  {r['vtx']:>7} {fmt(r['dist_mm'],6)} {fmt(r['fd_mm'],6)} "
                  f"{fmt(r['angle_deg'],5)} {fmt(r['skin_skull_deg'],5)} "
                  f"{fmt(r['inter_mm'],6,2)} "
                  f"{fmt(r['inter_near_mm'],6,2)} "
                  f"{fmt(r['elev_deg'],6)} {fmt(r['azim_deg'],6)} "
                  f"{(r['side'] or '-'):>6}  "
                  f"{('yes' if r['has_trajectory'] else '-'):>4} "
                  f"{('yes' if r['has_figure'] else '-'):>4}  "
                  f"{r['entry'] if r['entry'] else '(no folder)'}"
                  f"{'   <- newest' if r['vtx'] == newest else ''}")
        if any(r['inter_mm'] == 0 and (r['inter_near_mm'] or 0) > 0 for r in out):
            print('  note: inter is the axis clip at that one vertex and is '
                  'knife-edge; "≤5mm" is the best within 5 mm.')
            print('        inter 0.00 with ≤5mm > 0 means the vertex sits at the '
                  'edge of the intersecting patch, not that the beam misses —')
            print('        the −3 dB focal region is ~6-10 mm across laterally.')

    return out


def screenshot_wb_view(out_path, owner: str = 'wb_view') -> Path | None:
    """Screenshot the live ``wb_view`` window(s) to *out_path*.

    Unlike :func:`capture_plantus_scene`, which re-renders a saved scene, this
    captures what is on screen, including the clicked vertex marker and the
    metric overlay as configured at that moment, neither of which
    ``scene.scene`` stores.

    Needs macOS Screen Recording permission for the app running the kernel
    (VS Code / Terminal; System Settings > Privacy & Security, then restart
    the app). Without it ``screencapture`` exits 1 with "could not create
    image from window"; that case is detected and explained.

    Used by: :func:`run_plantus`, when a vertex is confirmed.

    Parameters
    ----------
    out_path, owner:
        PNG path (``_2``, ``_3`` ... appended for further windows); process
        name to match, as the window server reports it.

    Returns
    -------
    Path or None
        The first image written, or ``None`` if nothing usable was captured.
        Never raises: a missing screenshot must not interrupt placement.
    """
    out_path = Path(out_path)
    try:
        import Quartz
    except ImportError:
        print('[shot] Quartz (pyobjc) not available — no screenshot.')
        return None

    try:
        wins = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID) or []
    except Exception as exc:
        print(f'[shot] Could not list windows ({exc}) — no screenshot.')
        return None

    # Skip tiny windows: wb_view also owns menus/tooltips.
    hits = []
    for w in wins:
        if owner.lower() not in str(w.get('kCGWindowOwnerName', '')).lower():
            continue
        b = w.get('kCGWindowBounds') or {}
        if b.get('Width', 0) >= 300 and b.get('Height', 0) >= 300:
            hits.append(int(w['kCGWindowNumber']))
    if not hits:
        print(f'[shot] No on-screen "{owner}" window found — no screenshot.')
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    written, denied = [], False
    for i, wid in enumerate(hits, 1):
        p = out_path if i == 1 else out_path.with_name(
            f'{out_path.stem}_{i}{out_path.suffix}')
        try:
            res = subprocess.run(['screencapture', '-x', '-o', f'-l{wid}', str(p)],
                                 check=False, capture_output=True, text=True,
                                 timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f'[shot] screencapture failed ({exc}).')
            continue
        if p.is_file() and p.stat().st_size > 10_000:
            written.append(p)
        else:
            # Without Screen Recording permission screencapture exits 1 with
            # "could not create image from window" and writes nothing at all.
            if 'could not create image' in (res.stderr or ''):
                denied = True
            elif p.is_file():
                print(f'[shot] {p.name} is only {p.stat().st_size} bytes.')
            else:
                print(f'[shot] screencapture rc={res.returncode}: '
                      f'{(res.stderr or "").strip()[:80]}')

    if not written:
        if denied:
            print('[shot] Screen Recording permission is not granted, so no '
                  'screenshot was taken. Grant it to the app running this '
                  'kernel (VS Code / Terminal) in System Settings → Privacy & '
                  'Security → Screen Recording, then restart that app.')
            print('[shot] Placement continues regardless; the offscreen '
                  'placement render (vtx*_placement.png) is unaffected.')
        return None
    print(f'[shot] Saved {len(written)} wb_view screenshot(s): '
          f'{", ".join(p.name for p in written)}')
    return written[0]


def capture_plantus_scene(vtx_dir: Path, overwrite: bool = False) -> Path | None:
    """Render a PlanTUS placement scene to a PNG, without opening the GUI.

    PlanTUS shows the placement in ``wb_view`` and the window is then closed,
    leaving no image. This renders the same ``scene.scene`` offscreen with
    ``wb_command -scene-capture-image`` so the placement is kept as a figure
    beside its vertex. Limitation: the 3D view (head, transducer, focus cone)
    renders, but the three volume-slice panels stay black, because
    wb_command draws no volume layers without a real GL window; use the
    step-5 QC figures for T1 slices through the target.

    Used in: run_planTUS.py, :func:`run_plantus_placement`.

    Parameters
    ----------
    vtx_dir, overwrite:
        ``vtx{N}/`` directory holding ``scene.scene``; re-render even when the
        PNG exists.

    Returns
    -------
    Path or None
        The PNG, or ``None`` if the scene was missing or the render failed.
        Never raises: a missing figure must not lose a placement.
    """
    vtx_dir = Path(vtx_dir)
    scene = vtx_dir / 'scene.scene'
    if not scene.is_file():
        print(f'[capture] No scene.scene in {vtx_dir.name} — skipping figure.')
        return None

    out_png = vtx_dir / f'{vtx_dir.name}_placement.png'
    if out_png.is_file() and not overwrite:
        print(f'[capture] Figure already exists: {out_png.name}')
        return out_png

    _wb = shutil.which('wb_command')
    if _wb is None:
        print('[capture] wb_command not on PATH — no figure written. '
              'setup_environment(cfg) adds it from workbench_bin in the site '
              'YAML; run that cell first.')
        return None

    # cwd must be the scene's directory: the scene references T1 and the skin
    # surface by relative path (../../../T1.nii.gz, ../skin.surf.gii).
    cmd = [_wb, '-scene-capture-image', str(scene), '1', str(out_png)]
    try:
        res = subprocess.run(cmd, cwd=str(vtx_dir), capture_output=True,
                             text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f'[capture] Could not run wb_command ({exc}) — no figure written.')
        return None

    if out_png.is_file():
        print(f'[capture] Placement figure: {out_png.name}')
        return out_png
    print(f'[capture] wb_command produced no image (exit {res.returncode}).')
    if res.stderr.strip():
        print('          ' + res.stderr.strip().splitlines()[-1])
    return None


def run_plantus_placement(
    vertex_idx: int,
    sub_id_full: str,
    sub_id_bare: str,
    m2m_dir: Path,
    target_name: str,
    target_side: str,
    tp: dict,
    additional_offset: float,
    dry_run: bool = False,
) -> None:
    """Run PlanTUS's placement for one vertex, then write its depth report.

    ``PlanTUS.prepare_acoustic_simulation`` writes ``vtx{N}/`` (focus position,
    transducer matrices, scene); :func:`write_depth_report` then copies
    PlanTUS's focal distance into the report, so the report can never
    disagree with the placement.

    Used in: step 04b, step 04 (notebook).

    Parameters
    ----------
    vertex_idx:
        Vertex index selected in Workbench (from wb_view log output).
    sub_id_full, sub_id_bare, m2m_dir, target_name, target_side, tp, dry_run:
        As for :func:`prepare_plantus_scene`.
    additional_offset:
        Gel pad thickness between exit plane and skin, mm.
    """
    target_folder = find_plantus_target_folder(m2m_dir, sub_id_full, target_name, target_side)
    output_path   = str(target_folder)

    distances_file = str(target_folder / "skin_target_distances.npy")
    if not os.path.exists(distances_file):
        sys.exit(
            f"ERROR: distances file not found: {distances_file}\n"
            "  Run step04a_planTUS_prepscene.py first."
        )

    target_roi_name    = target_folder.name
    target_roi_filepath = output_path + "/" + target_roi_name + ".nii.gz"
    t1_filepath        = m2m_dir / "T1.nii.gz"

    if dry_run:
        print(f"[dry-run] Would run placement: vertex {vertex_idx} → {output_path}")
        return

    if str(_PLANTUS_CODE) not in sys.path:
        sys.path.append(str(_PLANTUS_CODE))
    _saved_cwd = os.getcwd()
    os.chdir(str(_PLANTUS_CODE))
    import PlanTUS  # noqa: PLC0415

    PlanTUS.prepare_acoustic_simulation(
        vertex_idx, output_path, target_roi_filepath,
        str(t1_filepath),
        tp["max_distance"], tp["min_distance"],
        tp["transducer_diameter"], tp["max_angle"],
        tp["plane_offset"], additional_offset,
        tp["transducer_model_path"],
        tp["focal_distance_list"], tp["flhm_list"],
        tp["placement_template_path"],
    )
    os.chdir(_saved_cwd)

    write_depth_report(target_folder, vertex_idx, additional_offset, sub_id_full)

    # PlanTUS closes its wb_view without saving anything, so re-render the same
    # scene offscreen to keep a figure of the placement that was just approved.
    capture_plantus_scene(target_folder / f"vtx{vertex_idx}")


def run_plantus(
    sub_id_full: str,
    sub_id_bare: str,
    m2m_dir: Path,
    target_name: str,
    target_side: str,
    tp: dict,
    additional_offset: float,
    dry_run: bool,
    use_pynput: bool = True,
    top_pct: float = 0.8,
    reuse_placement: bool = True,
    weights: tuple[float, float, float, float] = (10.0, 1.0, 1.0, 1.0),
    mark_radius_mm: float = 3.0,
) -> None:
    """Interactive PlanTUS placement for one target: scene, wb_view, placements.

    Builds the scene with :func:`prepare_plantus_scene`, prints the
    :func:`select_best_vtx` suggestion, opens ``wb_view``, and asks ``yes/no``
    for each clicked vertex; confirmed vertices go through
    :func:`run_plantus_placement`. ``?N`` at the prompt describes vertex N.

    With ``use_pynput`` a mouse listener gates the prompt so only a vertex
    clicked after the last prompt is offered (needs macOS Accessibility
    permission; falls back to log parsing when ``pynput`` is unavailable).
    PlanTUS opens a second, blocking wb_view during each placement; clicks in
    it are ignored and stale vertices are discarded.

    Used in: step 04 (notebook). Batch runs use run_planTUS.py instead.

    Parameters
    ----------
    sub_id_full, sub_id_bare, m2m_dir, target_name, target_side, tp, dry_run:
        As for :func:`prepare_plantus_scene`.
    additional_offset, use_pynput:
        Gel pad thickness in mm, passed to the depth report; gate prompts with
        the mouse listener.
    top_pct, weights, mark_radius_mm:
        Forwarded to :func:`select_best_vtx`.
    reuse_placement:
        When a ``vtx*`` folder already exists, report it and return without
        opening wb_view. This is what makes the notebook safe to "Run All".
    """
    # ── Reuse existing placement ──────────────────────────────────────────
    # Deliberately globs rather than calling find_plantus_target_folder, which
    # sys.exit()s when the folder does not exist yet — here a missing folder
    # simply means "nothing to reuse, go and place".
    if reuse_placement and not dry_run:
        _pdir = m2m_dir / 'PlanTUS'
        _matches = ([p for p in _pdir.glob(f'*{target_name}{mask_suffix(target_side)}')
                     if p.is_dir()] if _pdir.exists() else [])
        if len(_matches) == 1:
            _vtx = sorted(_matches[0].glob('vtx*'), key=lambda p: p.stat().st_mtime)
            if _vtx:
                print(f'[4b] Skipping placement — {len(_vtx)} existing vertex '
                      f'folder(s) in {_matches[0].name}:')
                for _v in _vtx:
                    print(f'       {_v.name}')
                print(f'[4b] Step 4c will use {_vtx[-1].name} (most recently '
                      f'modified) unless VTX pins another.')
                print('[4b] Set REUSE_PLACEMENT=False to place a new vertex instead.')
                return

    output_path = prepare_plantus_scene(
        sub_id_full, sub_id_bare, m2m_dir, target_name, target_side, tp, dry_run
    )
    if dry_run:
        return

    # ── Auto-select best vertex and display suggestion ────────────
    try:
        # Apply gel-pad adjustment to min_distance: a gel pad can add up to
        # 15 mm of coupling, so the effective lower distance limit is relaxed.
        _min_dist = tp.get("min_distance")
        if _min_dist is not None:
            _min_dist = max(0.0, _min_dist - 15.0)
        _best_vtx, _vtx_m, _relax = select_best_vtx(
            output_path,
            max_angle=tp["max_angle"],
            max_distance=tp.get("max_distance"),
            min_distance=_min_dist,
            top_pct=top_pct,
            weights=weights,
            mark_radius_mm=mark_radius_mm,
        )
        _angle_note = (
            f"  ⚠️  Angle {_vtx_m['angle_deg']:.1f}° exceeds nominal limit "
            f"({_vtx_m['max_angle_deg']:.1f}°) — verify placement\n"
        ) if _vtx_m["angle_exceeded"] else ""
        _wa, _wd, _ws = weights
        print(
            f"\n[auto vtx] Suggested best vertex: {_best_vtx}\n"
            f"  Ranked by       : aim×{_wa:g} + dist×{_wd:g} + skin-skull×{_ws:g}"
            f"   (each normalised to [0,1] across the pool; lower is better)\n"
            f"  Valid vertices  : {_vtx_m['n_valid']} safe  |  "
            f"{_vtx_m['n_top_candidates']} top candidates "
            f"(>= {_vtx_m['top_pct']*100:.0f}% of max {_vtx_m['max_inter_mm']:.1f} mm)\n"
            f"  Distance        : {_vtx_m['distance_mm']:.1f} mm\n"
            f"  Aim angle       : {_vtx_m['angle_deg']:.1f}° (limit: {_vtx_m['max_angle_deg']:.1f}°)\n"
            f"  Skin-skull angle: {_vtx_m['skin_skull_deg']:.1f}°  "
            f"(obliquity on bone — tracks transmission)\n"
            f"  Intersection    : {_vtx_m['intersection_mm']:.1f} mm\n"
            + _angle_note
            + f"  Marker written  : best_vtx_marker_skin.func.gii  "
            f"({_vtx_m['mark_vertices']} vertices, r={mark_radius_mm:g} mm)\n"
            "                    (1.0 = suggested vertex, 0.5 = candidate pool;\n"
            "                     shown as the top overlay on 3 of the 4 surface tabs)\n"
            "[auto vtx] Launching wb_view — click a different vertex, "
            "or type the suggested index when prompted.\n"
        )
    except (ValueError, FileNotFoundError) as _e:
        # Degrading to manual selection is intended, but the reason must be
        # visible: a NaN in the intersection map used to land here as an opaque
        # numpy message, silently removing the suggestion and the marker overlay
        # for every hippocampus target.
        print(f"[auto vtx] Could not compute best vertex: {_e}")
        print("[auto vtx] No suggestion and no best_vtx_marker overlay — the "
              "scene will still open, but pick the vertex yourself.")
        traceback.print_exc()
    # Attempt to use pynput if requested. pynput gates each prompt behind a
    # real mouse click, so accidental log lines (e.g. from scene load) do not
    # trigger yes/no. However pynput requires macOS Accessibility permissions
    # for the host process; without them mouse events are silently dropped and
    # no prompt ever appears. Set use_pynput=False to bypass pynput and fire
    # on every logged vertex directly.
    _pynput_ok = False
    if use_pynput:
        try:
            from pynput import mouse as _mouse  # noqa: PLC0415
            _pynput_ok = True
        except ImportError:
            print("[run_plantus] pynput not importable; falling back to direct stderr parsing.")

    command         = f"wb_view -logging FINER {output_path}/scene.scene"
    pattern         = re.compile(r"Switched vertex to triangle nearest vertex\s+(\.\d+)")
    triangle_number = None

    # Qt5 HiDPI variables — suppress all automatic scaling so wb_view opens
    # at 1:1 pixel ratio on Retina/high-DPI displays.  Without these, Qt5 may
    # double-scale the window, causing panels to collapse or be unreachable.
    wb_env = {
        **os.environ,
        "QT_AUTO_SCREEN_SCALE_FACTOR": "0",  # disable auto DPI detection
        "QT_SCALE_FACTOR":             "1",  # force logical pixel = physical pixel
        "QT_ENABLE_HIGHDPI_SCALING":   "0",  # Qt 5.14+ explicit disable
        "QT_FONT_DPI":                 "96", # standard 96 DPI fonts
    }
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        shell=True, cwd=str(output_path), text=True, env=wb_env,
    )

    # process_line gates whether a vertex log line triggers a prompt.
    # With pynput: starts False; mouse click sets it True.
    # Without pynput: always True (every logged vertex triggers prompt).
    process_line = not _pynput_ok
    # placement_busy is True while run_plantus_placement runs. PlanTUS shows the
    # result in a *second* wb_view via a blocking os.system() call, so for that
    # whole time this thread sits inside the placement and only the mouse
    # listener is live — clicks meant for the placement view would otherwise arm
    # the gate and fire a prompt from the first window.
    placement_busy = False

    if _pynput_ok:
        def on_click(x, y, button, pressed):
            nonlocal process_line
            if pressed and not placement_busy:
                process_line = True
        listener = _mouse.Listener(on_click=on_click)
        listener.start()

    def _flush_pending_log():
        """Drop log lines the first wb_view buffered during placement.

        A vertex clicked in the first window while the placement view was open
        stays in the pipe, so without this the next click would prompt for that
        stale vertex instead of the freshly clicked one.
        """
        dropped = 0
        try:
            _fd = process.stderr.fileno()
            _blocking = os.get_blocking(_fd)
        except (OSError, ValueError):
            return dropped
        try:
            os.set_blocking(_fd, False)
            while True:
                try:
                    if not process.stderr.readline():
                        break
                except (BlockingIOError, OSError, ValueError):
                    break
                dropped += 1
        finally:
            try:
                os.set_blocking(_fd, _blocking)
            except (OSError, ValueError):
                pass
        return dropped

    def read_output():
        nonlocal triangle_number, process_line, placement_busy
        while True:
            line = process.stderr.readline()
            if line == "" and process.poll() is not None:
                break
            if not process_line:
                continue
            match = pattern.search(line)
            if match:
                if _pynput_ok:
                    process_line = False  # reset; next prompt after next click
                triangle_number = int(match.group(1).replace(".", ""))
                print(f"Vertex selected: {triangle_number}")
                # ?N answers "what are this vertex's numbers?" without leaving
                # the prompt.  wb_view's hover tooltip gives an index and one
                # value; the notebook is blocked here while wb_view is open, so
                # this prompt is the only place the rest can be looked up.
                while True:
                    resp = input(
                        f"Generate placement for vertex {triangle_number}? "
                        f"(yes/no, or ?N to inspect vertex N): ").strip().lower()
                    if not resp.startswith("?"):
                        break
                    _q = resp[1:].strip() or str(triangle_number)
                    if _q.isdigit():
                        print(describe_vtx(
                            output_path, int(_q),
                            max_angle=tp["max_angle"],
                            max_distance=tp.get("max_distance"),
                            min_distance=_min_dist,
                            top_pct=top_pct, weights=weights))
                    else:
                        print(f"  '{_q}' is not a vertex index. Use ?12345, "
                              f"or ? on its own for the selected vertex.")
                if resp == "yes":
                    placement_busy = True
                    # Shoot before placement: this is the only moment the
                    # selection view exists with the clicked vertex on it, and
                    # placement opens a second window over the top of it.
                    try:
                        screenshot_wb_view(Path(output_path)
                                           / f'vtx{triangle_number}_selection.png')
                    except BaseException as _sexc:
                        print(f'[shot] Screenshot skipped: {_sexc}')
                    try:
                        run_plantus_placement(
                            vertex_idx=triangle_number,
                            sub_id_full=sub_id_full,
                            sub_id_bare=sub_id_bare,
                            m2m_dir=m2m_dir,
                            target_name=target_name,
                            target_side=target_side,
                            tp=tp,
                            additional_offset=additional_offset,
                        )
                    except BaseException as _exc:
                        if isinstance(_exc, KeyboardInterrupt):
                            raise
                        print("\n[ERROR] run_plantus_placement failed:")
                        traceback.print_exc()
                        print("[ERROR] See traceback above. wb_view remains open — select another vertex or close wb_view to exit.")
                    finally:
                        # Discard anything logged while the placement view was
                        # up, then require a fresh click before prompting again.
                        _dropped = _flush_pending_log()
                        process_line    = not _pynput_ok
                        placement_busy  = False
                        if _dropped:
                            print(f"[run_plantus] Ignored {_dropped} log line(s) "
                                  f"logged during placement.")
                        if _pynput_ok:
                            print("[run_plantus] Ready — click a vertex in the "
                                  "first wb_view window to select the next one.")
                else:
                    print("No action taken.")

    output_thread = threading.Thread(target=read_output)
    output_thread.start()
    process.wait()
    if _pynput_ok:
        listener.stop()
    output_thread.join()


def get_vtx_coordinates(
    vtx_dir: Path,
    target_folder: Path,
    vtx_id: int,
) -> tuple["np.ndarray", "np.ndarray"]:
    """Entry and target coordinates of one PlanTUS placement, in RAS mm.

    Entry is the ``skin.surf.gii`` vertex; target is the translation column
    of ``focus_position_matrix_*.txt``. SimNIBS writes both in RAS
    (NIfTI:Scanner), so unlike ANTs output (LPS) no flip is applied.

    Used by: :func:`list_plantus_vertices`, :func:`write_brainsight_for_vtx`.

    Parameters
    ----------
    vtx_dir, target_folder, vtx_id:
        ``vtx{N}/`` directory, the PlanTUS folder holding ``skin.surf.gii``,
        and the vertex index.

    Returns
    -------
    entry_ras, target_ras : np.ndarray, shape (3,)
    """
    import nibabel as nib
    import numpy as np

    scalp_path = target_folder / "skin.surf.gii"
    gii        = nib.load(str(scalp_path))
    entry_ras  = gii.darrays[0].data[vtx_id]

    focus_matrix_path = next(vtx_dir.glob("focus_position_matrix_*.txt"))
    M_focus           = np.loadtxt(focus_matrix_path)
    target_ras        = M_focus[:3, 3]

    return entry_ras, target_ras


def write_brainsight_txt(
    transducer_mat_path: str | Path,
    entry_las: "np.ndarray",
    target_las: "np.ndarray",
    out_path: str | Path,
    name: str = "TUS_Target",
    coordinate_system: str = "NIfTI:S:Scanner",
    append: bool = False,
    vtx: int | None = None,
) -> None:
    """Write, or append to, a BrainSight-compatible target file.

    Used by: :func:`write_brainsight_for_vtx`.

    Parameters
    ----------
    transducer_mat_path:
        PlanTUS ``*_transducer.txt``, a 4x4 matrix in Scanner/RAS space; only
        the rotation block is used.
    entry_las, target_las:
        Entry (skin) and focus in RAS mm, shape (3,), i.e. the two outputs of
        :func:`get_vtx_coordinates`. The ``_las`` suffix is historical; the
        values must be RAS.
    out_path, name, coordinate_system:
        Output path; label prefix of the rows; header string (default
        ``"NIfTI:S:Scanner"``).
    append:
        Append data rows to an existing file instead of writing header + rows.
    vtx:
        When given, written as a ``# Vertex: N`` header line so step 5 can
        tell which placement the file belongs to.
    """
    import numpy as np

    M = np.loadtxt(transducer_mat_path)
    if M.shape != (4, 4):
        raise ValueError(f"Expected 4×4 matrix, got {M.shape}")

    R = M[:3, :3].copy()
    R[:, 2] /= np.linalg.norm(R[:, 2])

    entry_las  = np.asarray(entry_las, float)
    target_las = np.asarray(target_las, float)

    # The vertex is recorded so downstream steps can tell which placement a
    # trajectory came from; readers skip '#' lines, so this is safe to add.
    _vtx_line = '' if vtx is None else f'# Vertex: {int(vtx)}\n'
    header = (
        "# Version: 13\n"
        f"# Coordinate system: {coordinate_system}\n"
        "# Created by: write_brainsight_txt (LabWiki scripts/TUS/src/utils.py)\n"
        + _vtx_line +
        "# Units: millimetres, degrees, milliseconds, and microvolts\n"
        "# Encoding: UTF-8\n"
        "# Notes: Each column is delimited by a tab. "
        "Each value within a column is delimited by a semicolon.\n"
        "# Target Name\tLoc. X\tLoc. Y\tLoc. Z\t"
        "m0n0\tm0n1\tm0n2\tm1n0\tm1n1\tm1n2\tm2n0\tm2n1\tm2n2\n"
    )

    def _row(label: str, loc: "np.ndarray") -> str:
        # BrainSight convention: m{col}n{row} → write column-major (R[:, col])
        return (
            f"{label}\t"
            f"{loc[0]:.4f}\t{loc[1]:.4f}\t{loc[2]:.4f}\t"
            f"{R[0,0]:.4f}\t{R[1,0]:.4f}\t{R[2,0]:.4f}\t"
            f"{R[0,1]:.4f}\t{R[1,1]:.4f}\t{R[2,1]:.4f}\t"
            f"{R[0,2]:.4f}\t{R[1,2]:.4f}\t{R[2,2]:.4f}\n"
        )

    out_path = Path(out_path)
    mode = "a" if append else "w"
    with open(out_path, mode) as f:
        if not append:
            f.write(header)
        f.write(_row(f"{name}_target", target_las))
        f.write(_row(f"{name}_entry",  entry_las))

    action = "Appended to" if append else "Saved"
    print(f"{action} BrainSight file:", out_path)
    print("  Target (Scanner):", target_las)
    print("  Entry  (Scanner):", entry_las)


def merge_brainsight_files(
    in_paths: "list[Path]",
    out_path: "Path",
) -> None:
    """Merge multiple BrainSight .txt files into a single file.

    Keeps the full header (comment lines starting with ``#``) from the first
    file; appends only the data rows from subsequent files.

    Used in: step 04 (combined L+R output).

    Parameters
    ----------
    in_paths:
        Ordered list of BrainSight files to merge (e.g. [L_file, R_file]).
    out_path:
        Output combined .txt file path.
    """
    from pathlib import Path as _Path

    out_path = _Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w") as fout:
        for i, src in enumerate(in_paths):
            with open(src) as fin:
                lines = fin.readlines()
            if i == 0:
                fout.writelines(lines)
            else:
                # Skip header comment lines from subsequent files
                fout.writelines(l for l in lines if not l.startswith("#"))

    print(f"Merged {len(in_paths)} BrainSight files → {out_path}")


def write_brainsight_for_vtx(
    m2m_dir: Path,
    sub_id_full: str,
    target_name: str,
    target_side: str,
    coordinate_system: str = "NIfTI:S:Scanner",
    vtx: int | None = None,
) -> Path:
    """Write the per-vertex Brainsight ``.txt`` for a PlanTUS placement.

    Combines :func:`find_plantus_target_folder`, :func:`resolve_vtx`,
    :func:`get_vtx_coordinates` and :func:`write_brainsight_txt`. One file per
    vertex, ``{label}_vtx{N}_brainsight.txt`` with a ``# Vertex: N`` header,
    so exports accumulate and step 5 can select a placement.

    Used in: step 04, run_planTUS.py, run_sweep.py.

    Parameters
    ----------
    m2m_dir, sub_id_full, target_name, target_side:
        ``m2m_{sub}`` directory, subject ID, target label, side suffix.
    coordinate_system:
        String written to the Brainsight header.
    vtx:
        Vertex to export; ``None`` takes the newest ``vtx*`` folder.

    Returns
    -------
    Path
        The file written.
    """
    target_folder = find_plantus_target_folder(m2m_dir, sub_id_full, target_name, target_side)

    vtx_id  = resolve_vtx(target_folder, vtx)
    vtx_dir = target_folder / f"vtx{vtx_id}"

    entry_ras, target_ras = get_vtx_coordinates(vtx_dir, target_folder, vtx_id)
    trans_mat_path       = next(vtx_dir.glob("*_transducer.txt"))

    label = stem_for(sub_id_full, target_name, target_side)

    # One file per vertex, and no fixed-name copy.  There used to be a second
    # file without the vertex in its name, on the belief that BrainSight
    # required it; the user confirmed on 2026-08-07 that it does not.  It could
    # only ever hold the most recent export, so its only real effect was to
    # make "which placement is this?" unanswerable — the question that cost
    # sub-z002 an 11 mm steering error.
    #
    # Nothing needs it: `VTX = None` resolves through resolve_vtx(), which reads
    # the vtx* folders, not this file.
    out_path = target_folder / f"{label}_vtx{vtx_id}_brainsight.txt"
    write_brainsight_txt(
        transducer_mat_path=trans_mat_path,
        entry_las=entry_ras,
        target_las=target_ras,
        out_path=out_path,
        name=label,
        coordinate_system=coordinate_system,
        vtx=vtx_id,
    )
    return out_path


# --- Step 05 helpers — inverse registration (MNI → native) ---

def ants_to_nib(ants_img: "ants.ANTsImage") -> "nib.Nifti1Image":
    """Convert an ANTs image to a :class:`nibabel.Nifti1Image`.

    This preserves origin, spacing, and direction exactly as stored in the
    ANTs object.  Useful for passing images to nilearn/nibabel functions after
    ANTs registration.

    Used in: step 03, run_reg.py.

    Parameters
    ----------
    ants_img:
        Any ANTs image (3-D or 4-D).

    Returns
    -------
    nibabel.Nifti1Image
        NIfTI image with matching affine.
    """
    import ants as _ants
    import nibabel as _nib
    import numpy as _np

    spacing   = _np.array(ants_img.spacing)
    origin    = _np.array(ants_img.origin)
    direction = _np.array(ants_img.direction).reshape(3, 3)

    affine       = _np.eye(4)
    affine[:3, :3] = direction * spacing
    affine[:3, 3]  = origin

    # ANTs/ITK stores origin and direction in LPS; NIfTI expects RAS.
    # Flip x and y to convert LPS → RAS.
    lps_to_ras   = _np.diag([-1., -1., 1., 1.])
    affine        = lps_to_ras @ affine

    return _nib.Nifti1Image(ants_img.numpy(), affine=affine)


def register_mni_to_native(
    t1_native_path: str | Path,
    t1_mni_path: str | Path,
    output_dir: str | Path,
    sub_id: str,
    type_of_transform: str = "SyN",
) -> tuple["ants.ANTsImage", "ants.ANTsImage", dict]:
    """Register the MNI152 T1 template to a subject's T1 with ANTs.

    ``fwdtransforms`` maps moving to fixed, i.e. MNI to native. ``"SyN"`` and
    ``"SyNCC"`` run an affine initialisation first; ``"Affine"`` runs alone.

    Used in: step 03, run_reg.py.

    Parameters
    ----------
    t1_native_path, t1_mni_path, output_dir, sub_id:
        Native T1, template T1, where the transforms go, filename prefix.
    type_of_transform:
        ``"Affine"``, ``"SyN"`` or ``"SyNCC"``.

    Returns
    -------
    t1_native_ras : ants.ANTsImage
        The subject T1 reoriented to RAS (fixed image).
    t1_mni_hm : ants.ANTsImage
        The template after histogram matching (moving image).
    reg : dict
        ANTs output with ``fwdtransforms`` for :func:`apply_inverse_transform`.
    """
    import ants as _ants
    import numpy as _np
    from pathlib import Path as _Path

    output_dir = _Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    t1_native = _ants.image_read(str(t1_native_path))
    t1_mni    = _ants.image_read(str(t1_mni_path))

    # Reorient native T1 to RAS for registration
    t1_native_ras = _ants.reorient_image2(t1_native, orientation="RAS")

    # Intensity normalisation of MNI template to match native T1.
    # Default (Option A): histogram_match_image — confirmed working with aMCC (3T)
    # and amygdala (3T) masks (see src/z_dont_edit/TUS_aMCCmask.ipynb,
    # TUS_amygdala_mask.ipynb).
    t1_mni_hm = _ants.histogram_match_image(
        source_image=t1_mni,
        reference_image=t1_native_ras,
        number_of_histogram_bins=256,
        number_of_match_points=128,
        use_threshold_at_mean_intensity=True,
    )
    # Option B: iMath normalize — used in TUS_LCmask.ipynb (7T) as active option:
    # t1_mni_hm = _ants.iMath(t1_mni, "Normalize")
    # Option C: no normalisation — used in TUS_LCmask.ipynb early version (Cell 27):
    # t1_mni_hm = t1_mni

    if type_of_transform in ("SyN", "SyNCC"):
        # Step 1: affine initialisation
        reg_affine = _ants.registration(
            fixed=t1_native_ras,
            moving=t1_mni_hm,
            type_of_transform="Affine",
        )
        # Step 2: nonlinear refinement
        reg = _ants.registration(
            fixed=t1_native_ras,
            moving=t1_mni_hm,
            type_of_transform=type_of_transform,
            initial_transform=reg_affine["fwdtransforms"][0],
            outprefix=str(output_dir / f"{sub_id}_MNI2native_"),
        )
    else:
        reg = _ants.registration(
            fixed=t1_native_ras,
            moving=t1_mni_hm,
            type_of_transform=type_of_transform,
            outprefix=str(output_dir / f"{sub_id}_MNI2native_"),
        )

    print(f"Registration complete. Transforms: {reg['fwdtransforms']}")
    return t1_native_ras, t1_mni_hm, reg


def apply_inverse_transform(
    mask_mni_path: str | Path,
    reg: dict | None,
    t1_native_ras: "ants.ANTsImage",
    t1_native_orig: "ants.ANTsImage",
    output_path: str | Path,
    interpolator: str = "nearestNeighbor",
    mask_brain: bool = True,
    transform_list_override: list[str] | None = None,
) -> "ants.ANTsImage":
    """Warp an MNI mask into subject-native space and save it.

    Applies the MNI-to-native transforms (ANTs ``fwdtransforms`` from
    :func:`register_mni_to_native`, or an fmriprep ``.h5`` via
    *transform_list_override*), optionally confines the result to the brain,
    and resamples it onto the original native T1 grid.

    Used in: step 03, run_reg.py.

    Parameters
    ----------
    mask_mni_path, reg, t1_native_ras, t1_native_orig, output_path:
        MNI mask; registration dict (or ``None`` with an override); the RAS
        T1 used as fixed image; the original T1 whose grid the output takes;
        where to write.
    interpolator, mask_brain, transform_list_override:
        ``"nearestNeighbor"`` / ``"linear"`` / ``"gaussian"`` / ``"bspline"``;
        restrict the result to ``ants.get_mask`` of the T1; transform list
        used instead of ``reg["fwdtransforms"]``.

    Returns
    -------
    ants.ANTsImage
        Native-space mask on the original T1 grid.
    """
    import ants as _ants
    from pathlib import Path as _Path

    if transform_list_override is not None:
        xfm_list = transform_list_override
    elif reg is not None:
        xfm_list = reg["fwdtransforms"]
    else:
        raise ValueError(
            "Either reg or transform_list_override must be provided."
        )

    mask_mni = _ants.image_read(str(mask_mni_path))

    mask_native_ras = _ants.apply_transforms(
        fixed=t1_native_ras,
        moving=mask_mni,
        transformlist=xfm_list,
        interpolator=interpolator,
    )

    if mask_brain:
        brain_mask = _ants.get_mask(t1_native_ras)
        mask_native_ras = mask_native_ras * brain_mask

    # Resample to original T1 orientation/grid
    mask_native = _ants.resample_image_to_target(mask_native_ras, t1_native_orig)

    output_path = _Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _ants.image_write(mask_native, str(output_path))
    print(f"Native mask saved: {output_path}")

    return mask_native


def compute_com_native(
    mask_native: "ants.ANTsImage | str | Path",
    z_threshold: float = 0.0,
) -> tuple["np.ndarray", tuple[float, ...]]:
    """Centre of mass of a native-space mask, in RAS mm and in voxels.

    ANTs/ITK keeps ``origin`` and ``direction`` in LPS, so the raw
    voxel-to-mm result is LPS; x and y are negated before returning, giving
    the NIfTI:Scanner (RAS) coordinates BrainSight expects.

    Used in: step 03, run_reg.py, run_com.py.

    Parameters
    ----------
    mask_native, z_threshold:
        Binary or probabilistic mask (ANTs image or NIfTI path); voxels at or
        below the threshold are excluded (``0.0`` for binary masks).

    Returns
    -------
    com_mm : np.ndarray, shape (3,)
        RAS mm, ``(x, y, z)``.
    com_vox : tuple of float
        Voxel indices ``(i, j, k)``.
    """
    import ants as _ants
    import numpy as _np
    from scipy.ndimage import center_of_mass as _com
    from nibabel.affines import apply_affine as _apply_affine
    from pathlib import Path as _Path

    if isinstance(mask_native, (_Path, str)):
        mask_native = _ants.image_read(str(mask_native))

    data   = mask_native.numpy()
    binary = (data > z_threshold).astype(_np.uint8)
    if binary.sum() == 0:
        raise ValueError(
            f"No voxels above z_threshold={z_threshold}. "
            "Check the mask or lower the threshold."
        )

    com_vox = _com(binary)  # (i, j, k)

    # Build affine from ANTs metadata.
    # ANTs uses ITK/LPS internally; .origin and .direction are in LPS.
    # Convert to RAS (NIfTI:Scanner / BrainSight) by flipping x and y.
    spacing   = _np.array(mask_native.spacing)
    origin    = _np.array(mask_native.origin)
    direction = _np.array(mask_native.direction).reshape(3, 3)
    affine       = _np.eye(4)
    affine[:3, :3] = direction * spacing
    affine[:3, 3]  = origin

    com_mm_lps = _apply_affine(affine, com_vox)
    # LPS → RAS: flip x and y
    com_mm = com_mm_lps * _np.array([-1.0, -1.0, 1.0])
    print(f"CoM (native, mm): {com_mm}")
    print(f"CoM (voxel):      {com_vox}")
    return com_mm, com_vox


def compute_peak_native(
    func_native: "ants.ANTsImage | str | Path",
    mask_native: "ants.ANTsImage | str | Path",
    z_threshold: float = 0.0,
) -> tuple["np.ndarray", tuple[int, ...], float]:
    """Peak voxel of a functional map within a native-space mask.

    Same LPS-to-RAS handling as :func:`compute_com_native`.

    Used in: step 03 (``TARGET_MODE = 'peak_func'``), run_com.py.

    Parameters
    ----------
    func_native, mask_native:
        Functional map (e.g. a warped fMRI statistic) and the mask, on the
        same voxel grid; ANTs images or NIfTI paths.
    z_threshold:
        Mask voxels at or below it are excluded from the search (``0.0`` for
        binary masks).

    Returns
    -------
    peak_mm : np.ndarray, shape (3,)
        RAS mm, ``(x, y, z)``.
    peak_vox : tuple of int
        Voxel indices ``(i, j, k)``.
    peak_val : float
        Map value at the peak.
    """
    import ants as _ants
    import numpy as _np
    from nibabel.affines import apply_affine as _apply_affine
    from pathlib import Path as _Path

    if isinstance(func_native, (_Path, str)):
        func_native = _ants.image_read(str(func_native))
    if isinstance(mask_native, (_Path, str)):
        mask_native = _ants.image_read(str(mask_native))

    mask_np   = mask_native.numpy() > z_threshold
    func_np   = func_native.numpy()

    if not mask_np.any():
        raise ValueError(
            f"No voxels above z_threshold={z_threshold}. "
            "Check the mask or lower the threshold."
        )

    func_masked = _np.where(mask_np, func_np, -_np.inf)
    peak_vox    = tuple(int(v) for v in _np.unravel_index(_np.argmax(func_masked), func_masked.shape))
    peak_val    = float(func_np[peak_vox])

    # Build affine from ANTs metadata (same convention as compute_com_native)
    spacing   = _np.array(func_native.spacing)
    origin    = _np.array(func_native.origin)
    direction = _np.array(func_native.direction).reshape(3, 3)
    affine       = _np.eye(4)
    affine[:3, :3] = direction * spacing
    affine[:3, 3]  = origin

    peak_mm_lps = _apply_affine(affine, _np.array(peak_vox, dtype=float))
    # LPS → RAS: flip x and y
    peak_mm = peak_mm_lps * _np.array([-1.0, -1.0, 1.0])
    print(f"Peak value:        {peak_val:.3f}")
    print(f"Peak (native, mm): {peak_mm}")
    print(f"Peak (voxel):      {peak_vox}")
    return peak_mm, peak_vox, peak_val


def visualize_mask_native(
    mask_native: "ants.ANTsImage | str | Path",
    t1_native: "ants.ANTsImage | str | Path",
    target_label: str,
    output_path: str | Path,
    cut_coords: tuple[float, float, float] | None = None,
    z_threshold: float = 0.0,
    cmap: str = "winter",
) -> "plt.Figure":
    """Save a tri-planar ``plot_stat_map`` overlay of a mask on the native T1.

    Used in: step 03, run_reg.py.

    Parameters
    ----------
    mask_native, t1_native:
        Native-space mask and T1 background (ANTs images or paths).
    target_label, output_path:
        Figure title text; PNG path (300 dpi).
    cut_coords, z_threshold, cmap:
        ``(x, y, z)`` mm of the cut planes, or ``None`` for the mask's centre
        of mass; display threshold on the overlay; matplotlib colormap name.

    Returns
    -------
    matplotlib.figure.Figure
    """
    import ants as _ants
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as _plt
    from nilearn import plotting as _plotting, image as _image
    from pathlib import Path as _Path

    if isinstance(mask_native, (_Path, str)):
        mask_native = _ants.image_read(str(mask_native))
    if isinstance(t1_native, (_Path, str)):
        t1_native = _ants.image_read(str(t1_native))

    mask_nib = ants_to_nib(mask_native)
    t1_nib   = ants_to_nib(t1_native)

    if cut_coords is None:
        try:
            com_mm, _ = compute_com_native(mask_native, z_threshold)
            cut_coords = tuple(float(v) for v in com_mm)
        except ValueError:
            cut_coords = (0, 0, 0)

    fig = _plotting.plot_stat_map(
        stat_map_img=mask_nib,
        bg_img=t1_nib,
        threshold=z_threshold if z_threshold > 0 else 0.01,
        display_mode="ortho",
        cut_coords=cut_coords,
        cmap=cmap,
        draw_cross=False,
        colorbar=True,
        title=f"{target_label} in Native Space",
    )

    output_path = _Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=300)
    _plt.close("all")
    print(f"Figure saved: {output_path}")
    return fig


# --- Step 05-BB — BabelBrain simulations (domain · acoustic · thermal) ---

def _drain_queue_BB(p, Q, silence_timeout=900):
    """Drain *Q* while *p* is alive; returns ``(ok, payload)``.

    ``ok`` is False once a string message carries the
    ``'--Babel-Brain-Low-Error'`` sentinel or the child exits non-zero;
    ``payload`` is the last non-string object the child put on the queue
    (``None`` if none; the acoustic stage returns its result this way).
    *silence_timeout* raises ``RuntimeError`` when *p* is alive but silent
    for that many seconds (``None`` disables it): BabelBrain's nested
    processes are awaited with a bare ``queueResult.get()``, have no
    ``try/except`` and redirect only stdout, so a child that dies loses its
    traceback and the wait never ends. Without the guard such a death looks
    like a long computation; it once cost several multi-hour "hangs" that
    were immediate crashes.

    Used by: :func:`_spawn_bb`.
    """
    import time as _time

    bNoError = True
    payload = None
    last_output = _time.time()

    while p.is_alive():
        _time.sleep(0.1)
        got_output = False
        while not Q.empty():
            msg = Q.get()
            got_output = True
            if isinstance(msg, str):
                print(msg, end='', flush=True)
                if '--Babel-Brain-Low-Error' in msg:
                    bNoError = False
            else:
                payload = msg

        if got_output:
            last_output = _time.time()
        elif silence_timeout is not None and _time.time() - last_output > silence_timeout:
            p.terminate()
            p.join()
            raise RuntimeError(
                f'No output for {silence_timeout:.0f}s while the BabelBrain '
                f'subprocess was still alive. This usually means one of '
                f"BabelBrain's own nested processes died and the parent is "
                f'blocked on an empty queue, not that the solve is slow. '
                f'Reproduce the step in-process to see the real traceback.'
            )

    p.join()

    while not Q.empty():
        msg = Q.get()
        if isinstance(msg, str):
            print(msg, end='', flush=True)
            if '--Babel-Brain-Low-Error' in msg:
                bNoError = False
        else:
            payload = msg

    if p.exitcode not in (0, None):
        bNoError = False

    return bNoError, payload


def patch_babelvisco_BB(force=False):
    """Fix the BabelViscoFDTD ``intparams`` dtype bug on disk, before any BHTE run.

    ``RayleighAndBHTE`` builds ``intparams`` as ``uint32`` while passing the
    sentinel ``LocationMonitoring = -1``; numpy >= 2 raises ``OverflowError``
    where numpy 1 silently wrapped. The Metal shader declares the buffer
    signed, so ``int32`` is the correct type and this is an upstream bug fix.

    It has to be a file edit: BHTE runs in a nested ``spawn`` child that
    re-imports the module, so an in-memory patch never reaches it, and the
    child has no ``try/except``, which is why the bug presented as a hang on
    ``queueResult.get()`` rather than an error. Idempotent, and safe after a
    reinstall restores the buggy file. Details and the exact sites are in
    ``LIST_modifications.md``.

    Used in: step 05 (5c), run_babelbrain.py.

    Parameters
    ----------
    force : bool
        Unused; the rewrite is conditional on the file's current contents.
    """
    import importlib
    import re as _re
    from pathlib import Path as _Path

    mod = importlib.import_module('BabelViscoFDTD.tools.RayleighAndBHTE')
    src_path = _Path(mod.__file__)

    text = src_path.read_text()

    # Only the standalone `dtype=np.uint32,` lines are intparams constructions.
    # The MonitoringPoints arrays use the single-line
    # `np.zeros(MaterialMap.shape, dtype=np.uint32)` form and must not match.
    pattern = _re.compile(r'^([ \t]+)dtype=np\.uint32,$', _re.MULTILINE)
    n_sites = len(pattern.findall(text))

    if n_sites == 0:
        print('[BabelViscoFDTD] intparams dtype already int32 — no change needed.')
        return

    backup = src_path.with_suffix('.py.orig')
    if not backup.exists():
        backup.write_text(text)
        print(f'[BabelViscoFDTD] backed up original to {backup.name}')

    src_path.write_text(pattern.sub(r'\1dtype=np.int32,', text))

    # Drop any stale bytecode so the next import picks up the edit.
    for pyc in (src_path.parent / '__pycache__').glob(f'{src_path.stem}.*.pyc'):
        pyc.unlink()

    print(f'[BabelViscoFDTD] intparams dtype uint32 -> int32 at {n_sites} site(s) '
          f'in {src_path.name}')
    print('[BabelViscoFDTD] fix is on disk, so spawned child processes inherit it.')


def read_trajectory_id_BB(trajectory_file):
    """Target ID of a Brainsight trajectory file, as the BabelBrain GUI reads it.

    Replicates ``ReadTrajectoryBrainsight(fname, bGetID=True)[1]``: the ID is
    the ``Target name`` column of the first non-comment data row, not the
    filename stem, and it becomes ``Config['ID']``, the prefix of every
    step-5 output.

    Used in: run_sweep.py, run_babelbrain.py, step 05.

    Parameters
    ----------
    trajectory_file:
        Brainsight-format ``.txt`` from step 4c.

    Returns
    -------
    str

    Raises
    ------
    FileNotFoundError
        Names the step-4 stage that writes the file, because a missing
        trajectory can mean 4b never ran or 4c did not export.
    ValueError
        No data rows.
    """
    from glob import glob as _glob

    if not os.path.isfile(trajectory_file):
        _folder = os.path.dirname(str(trajectory_file))
        _vtx = sorted(_glob(os.path.join(_folder, 'vtx*'))) if _folder else []
        if _vtx:
            _hint = (f'Placement (Step 4b) is done — found '
                     f'{", ".join(os.path.basename(v) for v in _vtx)} — but the '
                     f'BrainSight export is missing. Run Step 4c for this target.')
        elif os.path.isdir(_folder):
            _hint = ('No vertex folder in the target directory: run Step 4b '
                     '(placement) and then Step 4c.')
        else:
            _hint = ('The PlanTUS target folder does not exist: run Step 4 for '
                     'this subject/target, and check TARGET_NAME / TARGET_SIDE.')
        raise FileNotFoundError(
            f'Trajectory not found:\n  {trajectory_file}\n{_hint}')

    with open(trajectory_file) as _fh:
        for _line in _fh:
            _line = _line.rstrip('\n')
            if _line.startswith('#') or not _line.strip():
                continue
            # First non-comment, non-empty line: tab-separated; first field is Target name
            return _line.split('\t')[0].strip()
    raise ValueError(f'No data rows found in trajectory file: {trajectory_file}')


def resolve_vtx(target_folder, vtx=None) -> int:
    """Which placement is in use: *vtx* when given, else the newest ``vtx*``.

    The single rule for the whole pipeline; trajectory, depth report and
    output names all follow it, so the three cannot disagree. The
    fixed-name canonical trajectory (``{label}_brainsight``) is deliberately
    not consulted: it is a copy of the most recent export and cannot say
    which placement wrote it.

    Used in: run_babelbrain.py, step 05, :func:`write_brainsight_for_vtx`.

    Raises
    ------
    FileNotFoundError
        No ``vtx*`` folder, or *vtx* names one that does not exist.
    """
    target_folder = Path(target_folder)
    dirs = sorted((d for d in target_folder.glob('vtx*') if d.is_dir()),
                  key=lambda p: p.stat().st_mtime)
    if not dirs:
        raise FileNotFoundError(
            f'No placement in {target_folder.name}.\n'
            f'  Run step 4b (PlanTUS placement) for this target first.')

    available = {int(d.name.replace('vtx', '')): d for d in dirs}
    if vtx is not None:
        if vtx not in available:
            raise FileNotFoundError(
                f'VTX={vtx} has no placement folder in {target_folder.name}.\n'
                f'  available: {", ".join(str(k) for k in sorted(available))}\n'
                f'  Run step 4b to place it, or set VTX to one of the above.')
        print(f'Using pinned vertex: vtx{vtx}')
        return int(vtx)

    newest = int(dirs[-1].name.replace('vtx', ''))
    if len(dirs) > 1:
        print(f'{len(dirs)} vertex folders ({", ".join(d.name for d in dirs)}) '
              f'— using the newest: vtx{newest}.  Set VTX to pin a different one.')
    else:
        print(f'Using vertex: vtx{newest}')
    return newest


def focal_depth_mm(plantus_target_folder, vtx, tx_cfg=None):
    """Focal depth the TPO is set to, in mm, read from the depth report.

    Returns ``(depth_mm, verdict)`` with verdict ``"ok"``,
    ``"below_calibrated"``, ``"above_calibrated"``, ``"above_hardware"`` or
    ``"below_hardware"``. The value is ``exit_plane_to_ROI_distance_mm``,
    which equals ``skin_to_ROI + pad``: ``plane_offset_mm`` lies inside the
    housing and must not be added (``simulation_metrics.md``; the
    re-derivation that once added it is recorded in
    ``bookkeeping/CLAUDE_TUSPreprocess.md``).

    Pass *tx_cfg* as the raw transducer YAML, ``cfg["transducer_cfg"]``, not
    ``transducer_params()``, which drops the calibrated bounds and would
    report a depth below the calibrated minimum as "ok".

    Used in: step 04.
    """
    rep = read_depth_report(plantus_target_folder, vtx=vtx)
    depth = float(rep["exit_plane_to_ROI_distance_mm"])
    if tx_cfg is None:
        return depth, None
    if depth > tx_cfg.get("max_focal_depth_mm", float("inf")):
        return depth, "above_hardware"
    if depth < tx_cfg.get("min_focal_depth_mm", 0):
        return depth, "below_hardware"
    if depth > tx_cfg.get("calibrated_max_focal_depth_mm", float("inf")):
        return depth, "above_calibrated"
    if depth < tx_cfg.get("calibrated_min_focal_depth_mm", 0):
        return depth, "below_calibrated"
    return depth, "ok"


def read_depth_report(plantus_target_folder, vtx=None):
    """Parse a PlanTUS depth report (``*_depth_vtx*.txt``) into a dict of floats.

    Used in: step 05, :func:`compute_z_steering_BB`, :func:`focal_depth_mm`.

    Parameters
    ----------
    plantus_target_folder, vtx:
        Per-target PlanTUS directory; vertex whose report to read. *vtx* is
        required once a target has more than one placement: taking the first
        report by name once read another vertex's depth and steered the focus
        11 mm off, so ``ValueError`` is raised rather than guessing.

    Raises
    ------
    FileNotFoundError
        No report, or none for *vtx*.
    ValueError
        Several reports and ``vtx`` is ``None``.
    """
    from pathlib import Path as _Path
    import re as _re

    folder = _Path(plantus_target_folder)
    matches = sorted(folder.glob('*_depth_vtx*.txt'))
    if not matches:
        raise FileNotFoundError(
            f'No PlanTUS depth report found in: {folder}'
        )

    by_vtx = {}
    for _p in matches:
        _m = _re.search(r'vtx0*(\d+)\.txt$', _p.name)
        if _m:
            by_vtx[int(_m.group(1))] = _p

    if vtx is not None:
        if int(vtx) not in by_vtx:
            raise FileNotFoundError(
                f'No depth report for vtx={vtx} in {folder}\n'
                f'  available: {", ".join(str(k) for k in sorted(by_vtx))}'
            )
        report_file = by_vtx[int(vtx)]
    elif len(matches) == 1:
        report_file = matches[0]
    else:
        raise ValueError(
            f'{len(by_vtx)} depth reports in {folder.name} '
            f'({", ".join(str(k) for k in sorted(by_vtx))}) — pass vtx= to say '
            f'which placement to use.\n'
            f'  It must match the vertex the trajectory was exported from, '
            f'otherwise ZSteering is computed from the wrong depth.'
        )

    result = {}
    with open(report_file) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':' not in line:
                continue
            key, _, val = line.partition(':')
            key = key.strip()
            val = val.strip()
            try:
                result[key] = float(val)
            except ValueError:
                result[key] = val
    return result


def load_babelbrain_tx_yaml(bb_dir, tx_system):
    """Load BabelBrain's own ``default.yaml`` for *tx_system*.

    Resolves ``Babel_{TXSYSTEM}*/default.yaml`` under ``{bb_dir}/BabelBrain/``
    (underscores removed from *tx_system*) so ring diameters
    (``InDiameters``, ``OutDiameters``) come from the tool, not a copy.
    ``FileNotFoundError`` when nothing matches.

    Used in: step 05 (5b), run_babelbrain.py.

    Parameters
    ----------
    bb_dir, tx_system:
        Root of the BabelBrain clone (``babelbrain_dir`` in the site config,
        expanded) and the transducer identifier, e.g. ``'DPX_500'``.

    Returns
    -------
    dict
    """
    import yaml as _yaml
    from pathlib import Path as _Path

    bb_dir = _Path(bb_dir)
    pattern = f"BabelBrain/Babel_{tx_system.replace('_', '')}*/default.yaml"
    matches = sorted(bb_dir.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"Cannot find BabelBrain transducer YAML for {tx_system} "
            f"(searched: {bb_dir / pattern})"
        )
    with open(matches[0]) as _tf:
        return _yaml.safe_load(_tf)


_GEL_PAD_STANDARD_MM = [3, 5, 10]   # available gel pad thicknesses (mm)
_BASELINE_TEMPERATURE_C = 37.0       # body temperature the BHTE starts from; the
                                     # thermal QC reads it back from the h5, not from here
_THERMAL_DT_LIMIT_C = 2.0            # ITRUSST: temperature rise in brain < 2 °C (Brinker
                                     # et al. 2023); top of the thermal QC colour range


def compute_z_steering_BB(plantus_target_folder, tx_cfg, bb_tx_yaml, vtx=None):
    """ZSteering for BabelBrain, from the placement's own depth report.

    The effective depth is the report's ``exit_plane_to_ROI_distance_mm``: the
    TPO setting step 4 planned, gel pad included. The pad is defined once, when
    the placement is planned (``--additional-offset`` of run_planTUS.py and
    run_sweep.py, ``ADDITIONAL_OFFSET`` in the step-4 notebook) and recorded in
    the report as ``additional_offset_mm_assumed``; nothing downstream adds it
    again. Until 2026-09-20 this function took its own pad argument and added
    it on top of the report, so every padded placement (aMCC and CeA at 20 mm)
    was simulated with the transducer 20 mm too far from the skin.

    ``ZSteering = effective_depth - natural focus + correction`` and
    ``TxMechanicalAdjustmentZ = natural focus - effective_depth`` (metres):
    BabelBrain moves the transducer by the second and steers to ``target +
    ZSteering + TxMechanicalAdjustmentZ``, so the pair puts the exit plane at
    the effective depth and the focus on the target. When the depth falls
    below ``min_focal_depth_mm``, prints the smallest standard pad
    (:data:`_GEL_PAD_STANDARD_MM`) that would bring it into range; that pad is
    applied by re-planning step 4, not here.

    Used in: step 05 (5b), run_babelbrain.py.

    Parameters
    ----------
    plantus_target_folder, vtx:
        PlanTUS target directory and the vertex the trajectory came from;
        *vtx* is required once a target has more than one placement (see
        :func:`read_depth_report`).
    tx_cfg, bb_tx_yaml:
        ``cfg['transducer_cfg']``, used only for the focal-depth bounds
        (hardware and calibrated); BabelBrain's own ``default.yaml``
        (:func:`load_babelbrain_tx_yaml`), the sole source of the natural
        focus (``NaturalOutPlaneDistance``) and the ``Corrections``
        polynomial, applied as the GUI applies it. Nothing geometric is read
        from the site config, so the two cannot disagree.

    Returns
    -------
    tuple of (float, float)
        ``(z_steering, tx_mech_adj_z)`` in metres, both passed to
        :func:`run_acoustic_BB`.
    """
    # vtx must be the vertex the trajectory came from; read_depth_report raises
    # rather than guessing when several placements exist.
    report = read_depth_report(plantus_target_folder, vtx=vtx)
    skin_mm = report.get('skin_to_target_mm', report.get('skin_to_ROI_distance_mm'))
    pad_mm = float(report.get('additional_offset_mm_assumed', 0.0))
    roi_depth_mm = report.get('exit_plane_to_ROI_distance_mm',
                              (skin_mm if skin_mm is not None else 0.0) + pad_mm)

    min_mm      = tx_cfg.get('min_focal_depth_mm', 0)
    max_mm      = tx_cfg.get('max_focal_depth_mm', 999)
    cal_min_mm  = tx_cfg.get('calibrated_min_focal_depth_mm', min_mm)
    cal_max_mm  = tx_cfg.get('calibrated_max_focal_depth_mm', max_mm)

    import numpy as _np

    effective_depth_mm = roi_depth_mm            # pad already included at step 4
    effective_depth_m  = effective_depth_mm / 1e3

    # ── BabelBrain Corrections polynomial (matches GUI Babel_RingTx.py) ──
    _coeffs = bb_tx_yaml.get('Corrections', {}).get('Original')
    correction_m = (float(_np.polyval(_coeffs, effective_depth_m))
                    if _coeffs is not None else 0.0)
    nat_outplane_m = float(bb_tx_yaml['NaturalOutPlaneDistance'])

    # BabelBrain GUI formula (confirmed from GUI terminal log, 2026-04-09):
    #   CalculateFieldProcess parameters: ZSteering=-0.0875, TxMechanicalAdjustmentZ=0.0857
    # BabelIntegrationANNULAR_ARRAY.py line 371:
    #   center[0,2] = ZDim[FocalSpotLocation[2]] + ZSteering + TxMechanicalAdjustmentZ
    #              = 150.0 + (-87.5) + 85.7 = 148.2 mm  ← inside domain ✓
    # Both ZSteering and TxMechanicalAdjustmentZ are required.
    # See README_NOTE05_2.md §追加調査7 for full analysis.
    z_steering    = effective_depth_m - nat_outplane_m + correction_m
    tx_mech_adj_z = nat_outplane_m - effective_depth_m

    if skin_mm is not None:
        print(f"Skin → target (PlanTUS):       {skin_mm:.2f} mm")
    print(f"Gel pad (planned at step 4):   {pad_mm:.1f} mm")
    print(f"Effective depth (exit plane):  {effective_depth_mm:.2f} mm")
    print(f"Natural outplane distance:     {nat_outplane_m * 1e3:.1f} mm")
    if correction_m != 0.0:
        print(f"BabelBrain correction:         {correction_m * 1e3:+.2f} mm")
    print(f"ZSteering:                     {z_steering * 1e3:.2f} mm  ({z_steering:.4f} m)")
    print(f"TxMechanicalAdjustmentZ:       {tx_mech_adj_z * 1e3:.2f} mm  ({tx_mech_adj_z:.4f} m)")

    if not (min_mm <= effective_depth_mm <= max_mm):
        if effective_depth_mm < min_mm:
            deficit = min_mm - effective_depth_mm
            suggestion = next(
                (g for g in _GEL_PAD_STANDARD_MM if effective_depth_mm + g >= min_mm),
                None,
            )
            print(f"  ⚠ Effective depth {effective_depth_mm:.1f} mm below hardware "
                  f"minimum {min_mm} mm  (deficit: {deficit:.1f} mm)")
            if suggestion is not None:
                print(f"  → {suggestion} mm more pad would reach "
                      f"{effective_depth_mm + suggestion:.1f} mm: re-plan step 4 "
                      f"with --additional-offset {pad_mm + suggestion:g}")
        else:
            print(f"  ⚠ Effective depth {effective_depth_mm:.1f} mm above hardware "
                  f"maximum {max_mm} mm")
    elif effective_depth_mm < cal_min_mm:
        print(f"  ℹ Effective depth {effective_depth_mm:.1f} mm is within hardware range "
              f"({min_mm}–{max_mm} mm) but below calibrated minimum {cal_min_mm} mm")
    elif effective_depth_mm > cal_max_mm:
        print(f"  ℹ Effective depth {effective_depth_mm:.1f} mm is within hardware range "
              f"({min_mm}–{max_mm} mm) but above calibrated maximum {cal_max_mm} mm")
    else:
        print(f"  ✓ Effective depth within calibrated range ({cal_min_mm}–{cal_max_mm} mm)")

    return z_steering, tx_mech_adj_z


def patch_trimesh_compat_BB():
    """Restore the trimesh 3.x face-cleaning methods BabelBrain still calls.

    ``BabelDatasetPreps.DoIntersect`` calls ``remove_duplicate_faces`` and
    ``remove_degenerate_faces`` on a mesh that fails ``is_volume``; both were
    removed in trimesh 4, so that branch raised ``AttributeError`` and the
    sweep recorded the candidate as unscored. The shims follow the trimesh 4
    migration notes (``update_faces(unique_faces())`` and
    ``update_faces(nondegenerate_faces())``) and keep the 3.x contract of
    mutating in place.

    A monkeypatch suffices, unlike :func:`patch_babelvisco_BB`: the mesh code
    runs in a child this module starts, and :func:`_CalculateMaskProcess_wrapped`
    applies the shim first inside it. Idempotent. Logged in
    ``LIST_modifications.md``.

    Used in: step 05 (5a), through :func:`run_domain_BB`.
    """
    import trimesh as _trimesh

    def _remove_duplicate_faces(self):
        self.update_faces(self.unique_faces())

    def _remove_degenerate_faces(self, height=1e-8):
        self.update_faces(self.nondegenerate_faces(height=height))

    added = []
    for name, fn in (('remove_duplicate_faces', _remove_duplicate_faces),
                     ('remove_degenerate_faces', _remove_degenerate_faces)):
        if not hasattr(_trimesh.Trimesh, name):
            setattr(_trimesh.Trimesh, name, fn)
            added.append(name)

    if added:
        print(f'[trimesh {_trimesh.__version__}] restored for BabelBrain: '
              f'{", ".join(added)}')


def _CalculateMaskProcess_wrapped(Q, backend, device, **kargs):
    """Thin wrapper around BabelBrain CalculateMaskProcess.

    Runs in the spawned child, so it is the only place a monkeypatch reaches
    the code that actually builds the domain.  Applies the trimesh 4
    compatibility shim (:func:`patch_trimesh_compat_BB`) before handing over,
    and forwards any unhandled exception through the queue as a
    ``--Babel-Brain-Low-Error`` message, matching
    :func:`_CalculateFieldProcess_wrapped`.
    """
    import traceback as _tb
    try:
        patch_trimesh_compat_BB()
        from BabelBrain.CalculateMaskProcess import CalculateMaskProcess
        CalculateMaskProcess(Q, backend, device, **kargs)
    except Exception as _exc:
        Q.put(
            f'--Babel-Brain-Low-Error\n'
            f'[CalculateMaskProcess raised {type(_exc).__name__}]: {_exc}\n'
            f'{_tb.format_exc()}'
        )


def standoff_check_BB(acoustic_file, plantus_target_folder, vtx, bb_tx_yaml, tol_mm=5.0,
                      strict=True):
    """Planned versus simulated exit-plane-to-skin distance for one solve.

    Planned is the gel pad in the placement's depth report. Simulated is what
    the field was computed with: ``NaturalOutPlaneDistance -
    TxMechanicalAdjustmentZ - DistanceFromSkin`` from the h5, where
    ``DistanceFromSkin`` is BabelBrain's own skin-to-target distance and so
    independent of PlanTUS's. The two differ by the PlanTUS-vs-BabelBrain skin
    distance, within 2.5 mm on every placement measured. A pad counted twice
    showed up here as 20 mm (2026-09-20) and nowhere else: the focus is steered
    onto the target whatever the standoff, so every targeting metric stayed
    normal. Raises ``RuntimeError`` beyond *tol_mm* unless *strict* is False,
    which :func:`write_adopted_placements` uses to record the failure instead.

    Used in: step 05 (5b), run_babelbrain.py; the result feeds
    :func:`summarise_acoustic_BB`.

    Returns
    -------
    dict
        ``planned_mm``, ``simulated_mm``, ``diff_mm`` (simulated - planned)
        and ``tol_mm``.
    """
    report = read_depth_report(plantus_target_folder, vtx=vtx)
    planned = float(report.get('additional_offset_mm_assumed', 0.0))
    raw = _read_acoustic(acoustic_file).raw
    eff_sim = (float(bb_tx_yaml['NaturalOutPlaneDistance'])
               - float(raw['TxMechanicalAdjustmentZ'])) * 1e3
    simulated = eff_sim - float(raw['DistanceFromSkin']) * 1e3
    diff = simulated - planned
    print(f"[standoff] planned pad {planned:.1f} mm; simulated exit plane → skin "
          f"{simulated:.1f} mm ({diff:+.1f} mm)")
    if strict and abs(diff) > tol_mm:
        raise RuntimeError(
            f"The field was computed with a {simulated:.1f} mm standoff but the "
            f"placement plans a {planned:.1f} mm pad ({diff:+.1f} mm, tolerance "
            f"{tol_mm:.0f} mm). The effective depth handed to BabelBrain does not "
            "match the depth report; see compute_z_steering_BB.")
    return {'planned_mm': planned, 'simulated_mm': simulated,
            'diff_mm': diff, 'tol_mm': tol_mm}


def _spawn_bb(target, args, kwargs, label, silence_timeout=900):
    """Run one BabelBrain stage in a ``spawn`` child; return what it put on the queue.

    Every stage runs under an explicit ``spawn`` context: Metal is not
    fork-safe on macOS, and the thermal stage starts its own nested Process
    with the global start method, so a fork-context queue handed to a spawned
    grandchild would be a context mismatch. (The BabelViscoFDTD dtype fix
    reaches every level because :func:`patch_babelvisco_BB` edits the file on
    disk.) The child receives the queue as its first argument; strings it puts
    there are echoed, the last other object is returned (``None`` if none).
    ``RuntimeError`` when the child reports ``--Babel-Brain-Low-Error``, exits
    non-zero, or is silent for *silence_timeout* seconds
    (:func:`_drain_queue_BB`).

    Used by: :func:`run_domain_BB`, :func:`run_acoustic_BB`, :func:`run_thermal_BB`.
    """
    from multiprocessing import get_context                       # noqa: PLC0415

    ctx = get_context('spawn')
    Q = ctx.Queue()
    p = ctx.Process(target=target, args=(Q, *args), kwargs=kwargs)
    p.start()
    ok, payload = _drain_queue_BB(p, Q, silence_timeout)
    if not ok:
        raise RuntimeError(f'{label} reported an error (exitcode={p.exitcode}). '
                           'Check the output above for the full traceback.')
    return payload


def run_domain_BB(
    m2m_dir,
    t1w,
    trajectory_file,
    prefix,
    backend,
    device,
    frequency,
    ppw,
    domain_file,
    use_ct=False,
    ct_path='',
    ct_type=1,
    reuse_files=True,
    dry_run=False,
):
    """Run BabelBrain's domain step (``CalculateMaskProcess``) for one placement.

    Builds the tissue-mask NIfTI the acoustic solve reads, from the SimNIBS
    mesh and the Brainsight trajectory. Runs in a ``spawn`` child that applies
    :func:`patch_trimesh_compat_BB` first; ``RuntimeError`` when the child
    reports an error or exits non-zero.

    Used in: step 05 (5a), run_babelbrain.py.

    Parameters
    ----------
    m2m_dir, t1w, trajectory_file, prefix:
        SimNIBS directory, its ``T1.nii.gz``, the step-4 trajectory, and the
        output prefix every step-5 file starts with.
    backend, device, frequency, ppw:
        Computing backend, device name, centre frequency in Hz, points per
        wavelength (6 fast, 9 converged).
    domain_file:
        Expected ``{prefix}BabelViscoInput.nii.gz``; checked when *reuse_files*.
    use_ct, ct_path, ct_type:
        CT domain; ``ct_type`` 1 real CT, 2 ZTE, 3 PETRA.
    reuse_files, dry_run : bool

    Returns
    -------
    str
        Path to the domain file.
    """
    import os as _os
    import time as _time
    from pathlib import Path as _Path

    import numpy as _np
    from TranscranialModeling.BabelIntegrationBASE import GetSmallestSOS

    smallest_sos = GetSmallestSOS(frequency, bShear=True)
    spatial_step = round(smallest_sos / frequency / ppw * 1e3, 3)  # mm

    if reuse_files and _os.path.isfile(domain_file):
        print(f'[5a] Skipping — domain file already exists: {_Path(domain_file).name}')
        return domain_file

    if dry_run:
        print(f'[5a] DRY RUN — would generate: {_Path(domain_file).name}')
        return domain_file

    print('[5a] Domain generation started...')
    t0 = _time.time()

    # BabelBrain requires T1Conformal to be 1 mm isotropic.
    # If the charm T1 has sub-millimetre voxels, resample it once and cache.
    import nibabel as _nib
    _t1_img = _nib.load(t1w)
    _zooms  = _t1_img.header.get_zooms()[:3]
    if not _np.allclose(_zooms, _np.ones(3), rtol=1e-3):
        _t1_1mm = str(_Path(t1w).parent / 'T1_1mm.nii.gz')
        if not _os.path.isfile(_t1_1mm):
            import ants as _ants
            print(f'[5a] Resampling T1 to 1 mm isotropic for BabelBrain: {_Path(_t1_1mm).name}')
            _img_ants = _ants.image_read(t1w)
            _img_1mm  = _ants.resample_image(_img_ants, (1.0, 1.0, 1.0), use_voxels=False, interp_type=4)
            _ants.image_write(_img_1mm, _t1_1mm)
        t1w_conformal = _t1_1mm
    else:
        t1w_conformal = t1w

    kargs = {
        'SimbNIBSDir':             str(m2m_dir),
        'SimbNIBSType':            'charm',
        'CoregCT_MRI':             use_ct,
        'TrajectoryType':          'brainsight',
        'Mat4Trajectory':          trajectory_file,
        'T1Source_nii':            t1w,
        'T1Conformal_nii':         t1w_conformal,
        'SpatialStep':             spatial_step,
        'Location':                [0, 0, 0],
        'prefix':                  prefix,
        'bPlot':                   False,
        'bForceFullRecalculation': not reuse_files,
    }
    if use_ct:
        kargs['CT_or_ZTE_input'] = ct_path
        kargs['CTType']          = ct_type
        kargs['HUThreshold']     = 300.0

    _spawn_bb(_CalculateMaskProcess_wrapped, (backend, device), kargs,
              '[5a] CalculateMaskProcess')

    print(f'[5a] Done in {_time.time() - t0:.1f}s')
    print(f'     Output: {_Path(domain_file).name}')
    return domain_file


def _CalculateFieldProcess_wrapped(Q, field_targets, tx_system, **kargs):
    """Thin wrapper around BabelBrain CalculateFieldProcess.

    Catches any unhandled exception raised inside the subprocess and forwards
    it through the queue as a ``--Babel-Brain-Low-Error`` message so that
    ``run_acoustic_BB`` can display the full traceback in the notebook.
    Without this, subprocess crashes are silent (traceback goes to stderr of
    the child process and is never seen).
    """
    import traceback as _tb
    try:
        from BabelBrain.CalculateFieldProcess import CalculateFieldProcess
        CalculateFieldProcess(Q, field_targets, tx_system, **kargs)
    except Exception as _exc:
        Q.put(
            f'--Babel-Brain-Low-Error\n'
            f'[CalculateFieldProcess raised {type(_exc).__name__}]: {_exc}\n'
            f'{_tb.format_exc()}'
        )


def run_acoustic_BB(
    m2m_dir,
    field_target,
    tx_system,
    frequency,
    aperture,
    focal_length,
    in_diameters,
    out_diameters,
    backend,
    device,
    ppw,
    z_steering=0.0,
    tx_mech_adj_z=None,
    z_beyond=40e-3,
    use_ct=False,
    reuse_files=True,
    dry_run=False,
):
    """Run BabelBrain's acoustic step (``CalculateFieldProcess``) for one placement.

    Runs the skull solve and the water reference. For ANNULAR_ARRAY transducers
    BabelBrain does not ``put()`` the skull result path, so it is recovered by
    globbing after the child exits.

    Used in: step 05 (5b), run_babelbrain.py.

    Parameters
    ----------
    m2m_dir, field_target, tx_system, frequency:
        SimNIBS directory, BabelBrain job ID (``{ID}_{TX_SYSTEM}``), transducer
        identifier (e.g. ``'DPX_500'``), centre frequency in Hz.
    aperture, focal_length, in_diameters, out_diameters:
        Transducer geometry in metres, from the transducer YAML.
    backend, device, ppw:
        Computing backend, device name, points per wavelength.
    z_steering : float
        Electronic steering in metres relative to the natural focal distance,
        from :func:`compute_z_steering_BB`.
    tx_mech_adj_z : float or None
        Mechanical Z offset in metres, ``natural focus - effective depth`` from
        :func:`compute_z_steering_BB`. BabelBrain moves the transducer by it
        and steers to ``target + ZSteering + TxMechanicalAdjustmentZ``, so the
        pair places the exit plane at the effective depth and the focus on the
        target. ``None`` means 0.0.
    z_beyond : float
        Simulation depth beyond the focus in metres.
    use_ct, reuse_files, dry_run : bool
        CT domain from step 5a; skip when the skull h5 exists; validate only.

    Returns
    -------
    str
        Path to the skull ``DataForSim.h5``.

    Raises
    ------
    RuntimeError
        The child reported an error or no output file was found.
    """
    import os as _os
    import time as _time
    import numpy as _np
    from glob import glob as _glob
    from pathlib import Path as _Path

    _t1w_dir = str(m2m_dir)
    _basedir, _m2m_id = _os.path.split(_t1w_dir)
    _basedir += _os.sep

    existing = [
        f for f in _glob(_os.path.join(_t1w_dir, f'{field_target}*DataForSim.h5'))
        if '_Water_' not in f
    ]
    if reuse_files and existing:
        acoustic_file = existing[0]
        print(f'[5b] Skipping — acoustic file exists: {_Path(acoustic_file).name}')
        return acoustic_file

    if dry_run:
        print(f'[5b] DRY RUN — would generate acoustic simulation for {tx_system}')
        return ''

    print('[5b] Acoustic simulation started...')
    t0 = _time.time()

    if tx_mech_adj_z is None:
        tx_mech_adj_z = 0.0
        print(f'[5b] tx_mech_adj_z not provided; using 0.0 '
              f'(correct for ANNULAR_ARRAY / DPX / CTX transducers)')

    kargs = {
        'ID':                               _m2m_id,
        'deviceName':                       device,
        'COMPUTING_BACKEND':                backend,
        'basePPW':                          [ppw],
        'basedir':                          _basedir,
        'Frequencies':                      [frequency],
        'TxMechanicalAdjustmentX':          0.0,
        'TxMechanicalAdjustmentY':          0.0,
        'TxMechanicalAdjustmentZ':          tx_mech_adj_z,
        'bDoRefocusing':                    False,
        'bUseCT':                           use_ct,
        'bUseRayleighForWater':             True,
        'bSaveStress':                      False,
        'bSaveDisplacement':                False,
        'bForceHomogenousMedium':           False,
        'HomogenousMediumValues':           {},
        'bExtractAirRegions':               True,
        'OptimizedWeightsFile':             '',
        'ZSteering':                        z_steering,
        'ZIntoSkin':                        0.0,
        'Aperture':                         aperture,
        'FocalLength':                      focal_length,
        'InDiameters':                      _np.array(in_diameters),
        'OutDiameters':                     _np.array(out_diameters),
        'zLengthBeyonFocalPointWhenNarrow': z_beyond,
        'bPETRA':                           False,
    }

    field_out = _spawn_bb(_CalculateFieldProcess_wrapped, ([field_target], tx_system),
                          kargs, '[5b] CalculateFieldProcess')

    # ANNULAR_ARRAY transducers (CTX/DPX) never call queue.put() for the
    # skull file — only the water result goes to the queue (or nothing at all).
    # Derive acoustic_file from the output path pattern.
    if field_out is not None:
        acoustic_file = (
            field_out['FilesSkull'][0]
            if isinstance(field_out, dict) else field_out
        )
    else:
        skull_files = [
            f for f in _glob(_os.path.join(_t1w_dir, f'{field_target}*DataForSim.h5'))
            if '_Water_' not in f
        ]
        if not skull_files:
            raise RuntimeError(
                f'[5b] No DataForSim.h5 found after simulation in {_t1w_dir}'
            )
        acoustic_file = sorted(skull_files)[0]

    print(f'\n[5b] Done in {_time.time() - t0:.1f}s')
    print(f'     Skull output: {_Path(acoustic_file).name}')
    return acoustic_file


def run_thermal_BB(
    acoustic_file,
    thermal_profile,
    base_isppa,
    frequency,
    tx_system,
    backend,
    device,
    reuse_files=True,
    dry_run=False,
):
    """Run BabelBrain's thermal step (``CalculateThermalProcess``), all protocol rows.

    Solves the BHTE for every DC/PRF/Duration combination in
    *thermal_profile*. Call :func:`patch_babelvisco_BB` first. Output names
    do not carry the protocol, so never reuse files across protocols.
    ``RuntimeError`` when the child reports an error or the output is missing.

    Used in: step 05 (5c), run_babelbrain.py.

    Parameters
    ----------
    acoustic_file, base_isppa:
        Skull ``DataForSim.h5`` from step 5b; ``BaseIsppa`` from the YAML,
        in-situ W/cm2.
    thermal_profile:
        ``AllDC_PRF_Duration`` list from the stimulation YAML. Every dict needs
        all seven keys (``Duration``, ``DurationOff``, ``DC``, ``PRF``,
        ``Repetitions``, ``NumberGroupedSonications``,
        ``PauseBetweenGroupedSonications``); BabelBrain reads them without
        defaults.
    frequency, tx_system, backend, device:
        As for :func:`run_acoustic_BB`.
    reuse_files, dry_run : bool

    Returns
    -------
    str
        Path to ``*_AllCombinations.h5``, or ``''`` on dry run or missing input.
    """
    import os as _os
    import time as _time
    from pathlib import Path as _Path

    import numpy as _np
    from BabelViscoFDTD.H5pySimple import ReadFromH5py as _ReadFromH5py

    from BabelBrain.Babel_Thermal.CalculateThermalProcess import CalculateThermalProcess
    from ThermalModeling.CalculateTemperatureEffects import GetThermalOutName

    if not _os.path.isfile(acoustic_file):
        print('[5c] Skipping — acoustic file not found. Run Step 5b first.')
        return ''

    def _allcomb_path():
        base = GetThermalOutName(
            acoustic_file,
            thermal_profile[0]['Duration'],
            thermal_profile[0]['DurationOff'],
            thermal_profile[0]['DC'],
            base_isppa,
            thermal_profile[0]['PRF'],
            thermal_profile[0].get('Repetitions', 1),
        )
        return base.split('-Duration-')[0] + '_AllCombinations.h5'

    def _stored_profile_matches(path):
        """True when the file on disk was produced by the protocol requested.

        The _AllCombinations.h5 name is BabelBrain's, and GetThermalOutName
        truncates it at '-Duration-', so the protocol does not appear in it.
        Existence alone therefore said nothing: asking for the Pan regime
        (DC 10 %, 80 s) where the worst-case Draft (DC 30 %, 200 s) had already
        run returned the Draft's temperatures, silently, under the new name.

        The parameters are all inside the file, so compare them.
        """
        try:
            _stored = _ReadFromH5py(path)['AllData']
        except Exception as _e:                                  # noqa: BLE001
            print(f'[5c] Existing thermal file unreadable ({_e}) — recomputing.')
            return False
        if len(_stored) != len(thermal_profile):
            print(f'[5c] Existing thermal file has {len(_stored)} combination(s), '
                  f'{len(thermal_profile)} requested — recomputing.')
            return False
        _keys = (('DutyCycle', 'DC'), ('PRF', 'PRF'), ('DurationUS', 'Duration'),
                 ('DurationOff', 'DurationOff'), ('Repetitions', 'Repetitions'))
        for _i, (_have, _want) in enumerate(zip(_stored, thermal_profile)):
            for _hk, _wk in _keys:
                _a = float(_np.asarray(_have[_hk]).ravel()[0])
                _b = float(_want.get(_wk, 1))
                if abs(_a - _b) > 1e-6:
                    print(f'[5c] Existing thermal file was run at {_hk}={_a:g}, '
                          f'{_b:g} requested — recomputing.')
                    return False
            _a = float(_np.asarray(_have['Isppa']).ravel()[0])
            if abs(_a - float(base_isppa)) > 1e-6:
                print(f'[5c] Existing thermal file was run at Isppa={_a:g}, '
                      f'{base_isppa:g} requested — recomputing.')
                return False
        return True

    # Reuse check — the definitive marker of a successful run is _AllCombinations.h5.
    # Per-combo .h5 files may exist from a previously failed run; do not use them alone.
    if (reuse_files and _os.path.isfile(_allcomb_path())
            and _stored_profile_matches(_allcomb_path())):
        print(f'[5c] Skipping — thermal output already exists: {_Path(_allcomb_path()).name}')
        return _allcomb_path()

    if dry_run:
        print(f'[5c] DRY RUN — would run {len(thermal_profile)} thermal simulation(s)')
        return ''

    print(f'[5c] Thermal simulation started ({len(thermal_profile)} combination(s))...')
    t0 = _time.time()

    kargs = {
        'deviceName':                    device,
        'COMPUTING_BACKEND':             backend,
        'Isppa':                         base_isppa,
        'Frequency':                     frequency,
        'TxSystem':                      tx_system,
        'BaselineTemperature':           _BASELINE_TEMPERATURE_C,
        'LimitBHTEIterationsPerProcess': 100,
        'bForceHomogenousMedium':        False,
        'HomogenousMediumValues':        {},
        'bForceNoAbsorptionSkullScalp':  False,
        'sel_p':                         'p_amp',
    }

    _spawn_bb(CalculateThermalProcess,
              ([acoustic_file], thermal_profile, {'DistanceConeToFocus': 0.0}),
              kargs, '[5c] CalculateThermalProcess')

    # Wait up to 10 s for the output file to appear.  On Dropbox-backed paths
    # the filesystem can take a moment to reflect a newly written file.
    allcomb_h5 = _allcomb_path()
    for _wait in range(20):
        if _os.path.isfile(allcomb_h5):
            break
        _time.sleep(0.5)
    else:
        # Last resort: glob for any AllCombinations.h5 next to the acoustic file
        from glob import glob as _glob
        _candidates = _glob(_os.path.join(_os.path.dirname(acoustic_file), '*_AllCombinations.h5'))
        if _candidates:
            allcomb_h5 = sorted(_candidates)[0]
        else:
            raise RuntimeError(f'[5c] Thermal output not found: {allcomb_h5}')

    print(f'[5c] Done in {_time.time() - t0:.1f}s')
    print(f'     Thermal output: {_Path(allcomb_h5).name}')
    return allcomb_h5


# --- Step 05-BB — QC visualisation ---

_BB_DARK_BG   = '#1a1a1a'


def find_roi_mask(plantus_target_folder):
    """Return the path to the native-space ROI mask from Step 3, or None.

    Searches *plantus_target_folder* for ``*_mask*.nii*`` files and
    returns the first match as a string.

    Used in: step 05 notebook (Step 5b QC).

    Parameters
    ----------
    plantus_target_folder : Path or str
        PlanTUS output folder for the target ROI.

    Returns
    -------
    str or None
        Absolute path to the ROI NIfTI, or ``None`` if not found.
    """
    from pathlib import Path as _Path
    candidates = sorted(_Path(plantus_target_folder).glob('*_mask*.nii*'))
    return str(candidates[0]) if candidates else None


def fig_dir_for(sub_dir, target: str | None = None,
                stim: str | None = None) -> Path:
    """Return (and create) the figure directory for a target and protocol.

    ::

        figures/registration/        step-3 QC, one set per subject
        figures/{target}/            acoustic: depends on target and vertex
        figures/{target}/{stim}/     thermal: also depends on the protocol

    The protocol directory drops the target token the stimulation YAML
    already carries (``aMCC_.../aMCC_offline_ErrorMonitoring`` becomes
    ``aMCC_.../offline_ErrorMonitoring``). Sides share a directory, since
    ``_L`` / ``_R`` are in every filename. Acoustic figures sit above the
    protocol level because the same acoustic run feeds every thermal
    protocol; a copy under each would drift.

    Used in: step 03, step 05, run_reg.py, run_babelbrain.py.
    """
    out = Path(sub_dir) / "figures"
    out = out / "registration" if target is None else out / target
    if stim:
        out = out / _strip_target_prefix(stim, target)
    out.mkdir(parents=True, exist_ok=True)
    return out


def _strip_target_prefix(stim: str, target: str | None) -> str:
    """Drop the leading target token from a stimulation label.

    Stimulation YAMLs are named after their target, so nesting the label under
    the target directory repeated it::

        aMCC_NeuroSynthTopic112/aMCC_offline_ErrorMonitoring/

    Only the *directory* name is shortened; the label itself is untouched and
    still appears in every filename. That is safe because this is the one place
    the path is built -- writers and readers both come through fig_dir_for(),
    so they cannot disagree about where a thermal figure lives.

    Falls back to the full label whenever the first token is not part of the
    target, so an unrelated protocol keeps its name.
    """
    if not target:
        return stim
    head, _, rest = stim.partition("_")
    if rest and head.lower() in target.lower():
        return rest
    return stim


def _read_acoustic(acoustic_file, skin_first=True):
    """One reader for the step-5b h5, with the z convention decided once.

    BabelBrain stores ``p_amp`` and ``MaterialMap`` distal-first (index 0 on
    the far side of the head) but ``TargetLocation`` and ``z_vec`` skin-first.
    ``skin_first=True`` flips the two arrays so every index shares the frame
    of ``z_vec``, which is what the plots need; ``False`` leaves them as
    stored, as the metric code does, and moves the target's z index into that
    frame instead. Mixing the two frames is what once put an ROI outside the
    lobe it plainly overlapped (see :func:`roi_overlap`).

    Returns a namespace: ``p``, ``mat``, ``ix``, ``iy``, ``iz`` (in the frame
    of the returned arrays), ``tgt_stored`` (``TargetLocation`` as stored),
    ``step_mm``, ``x_mm``, ``y_mm``, ``z_mm`` and ``raw`` (the h5 dict, for
    the occasional extra key). The water companion has the same keys.
    """
    import numpy as np                                            # noqa: PLC0415
    from types import SimpleNamespace                             # noqa: PLC0415
    from BabelViscoFDTD.H5pySimple import ReadFromH5py            # noqa: PLC0415

    raw = ReadFromH5py(str(acoustic_file))
    p = np.asarray(raw['p_amp'])
    mat = np.asarray(raw['MaterialMap'])
    tgt = tuple(int(v) for v in np.asarray(raw['TargetLocation']).ravel())
    if skin_first:
        p = np.ascontiguousarray(np.flip(p, axis=2))
        mat = np.ascontiguousarray(np.flip(mat, axis=2))
        iz = tgt[2]
    else:
        iz = p.shape[2] - 1 - tgt[2]
    return SimpleNamespace(
        p=p, mat=mat, ix=tgt[0], iy=tgt[1], iz=iz, tgt_stored=tgt,
        step_mm=float(np.asarray(raw['SpatialStep']).ravel()[0]) * 1e3,
        x_mm=np.asarray(raw['x_vec']) * 1e3,
        y_mm=np.asarray(raw['y_vec']) * 1e3,
        z_mm=np.asarray(raw['z_vec']) * 1e3,
        raw=raw,
    )


def _main_lobe(above):
    """Largest connected component of a boolean field: ``(mask, n_main, n_total)``.

    The focal lobe is the largest -3 dB component, following
    ``_BabelBaseTx.CalcVolumetricMetrics``, not the component holding the
    maximum: a small distal hotspot that marginally outpeaks the true lobe
    would otherwise be read as the focus. Shared by :func:`score_candidate`
    and :func:`_flhm_metrics` so the two cannot drift apart. ``n_main`` and
    ``n_total`` are voxel counts; both are 0 when nothing is above threshold.
    """
    import numpy as np                                            # noqa: PLC0415
    from scipy import ndimage                                     # noqa: PLC0415

    lab, n = ndimage.label(above)
    if n == 0:
        return np.zeros(above.shape, dtype=bool), 0, 0
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    k = int(np.argmax(sizes))
    return lab == k, int(sizes[k]), int(above.sum())


def _map_voxels(idx, src_affine, dst_affine, dst_shape):
    """Nearest voxel on another grid for each source voxel: ``(dst_idx, inside)``.

    *idx* is ``(n, 3)`` integer indices on the source grid; the result is the
    rounded destination index of each, through RAS, and a mask of those that
    land inside *dst_shape*. Used by :func:`roi_overlap` and
    :func:`lobe_csf_fraction`, which move the ROI and the focal lobe between
    the simulation grid, the ROI mask and the charm segmentation.
    """
    import numpy as np                                            # noqa: PLC0415
    import nibabel as nib                                         # noqa: PLC0415

    ras = nib.affines.apply_affine(src_affine, np.asarray(idx, dtype=float))
    dst = np.rint(nib.affines.apply_affine(np.linalg.inv(dst_affine), ras)).astype(int)
    inside = np.all((dst >= 0) & (dst < np.array(dst_shape)[None, :]), axis=1)
    return dst, inside


def _sub_affine(acoustic_file):
    """Affine of the ``*_FullElasticSolution_Sub.nii.gz`` beside a step-5b h5, or None.

    The one grid-to-world mapping of the stored field: index order as
    ``p_amp`` is stored (distal-first), one voxel shorter than ``p_amp`` in
    each dimension but sharing its origin. The ``affine`` key inside the h5
    is the full domain's and does not map the stored arrays; used for the QC
    ROI overlay it put every ROI voxel outside the grid, so no figure showed
    an ROI contour until 2026-09-21. Used by :func:`roi_overlap`,
    :func:`lobe_csf_fraction` and :func:`_roi_on_sim_grid`.
    """
    import nibabel as nib                                         # noqa: PLC0415

    acoustic_file = Path(acoustic_file)
    sub = sorted(acoustic_file.parent.glob(
        acoustic_file.name.replace("_DataForSim.h5", "_FullElasticSolution_Sub.nii.gz")))
    return nib.load(str(sub[0])).affine if sub else None


def _roi_on_sim_grid(acoustic_file, roi_nii, shape):
    """ROI mask resampled onto the simulation grid, in the stored (distal-first) frame.

    Nearest-neighbour resampling through :func:`_sub_affine`, onto *shape*
    (that of ``p_amp``). Flip axis 2 for the skin-first frame the plots use.
    None when the Sub NIfTI is missing.
    """
    import numpy as np                                            # noqa: PLC0415
    import nibabel as nib                                         # noqa: PLC0415
    from nilearn.image import resample_img                        # noqa: PLC0415

    aff = _sub_affine(acoustic_file)
    if aff is None:
        return None
    rs = resample_img(nib.load(str(roi_nii)), target_affine=aff,
                      target_shape=tuple(shape), interpolation="nearest")
    return np.asarray(rs.get_fdata() > 0.5)


def roi_overlap(acoustic_file: Path, main_lobe, roi_nii) -> dict:
    """How much of the target the focal lobe covers, and how much spills out.

    ITRUSST (Murphy et al. 2025) gives no numeric tolerance for targeting
    error, only the criterion that intensity be high inside the structure and
    low around it. Centroid offset does not express that; these do:

        coverage    fraction of the ROI inside the -3 dB focal volume
        off_target  fraction of the focal volume outside the ROI
        ceiling     min(1, FLHM volume / ROI volume), the most coverage a lobe
                    this size can reach; coverage is read against it, not 1
        efficiency  coverage / ceiling (Szymkiewicz-Simpson overlap)

    When the focus is smaller than the ROI, efficiency equals
    ``1 - off_target``; it is reported anyway because ceiling is what makes
    coverage readable. Grids are mapped through the ``*_Sub.nii.gz`` affine,
    sparsely over ROI and lobe voxels.

    Used in: :func:`score_candidate`.
    """
    import numpy as np                                          # noqa: PLC0415
    import nibabel as nib

    aff = _sub_affine(acoustic_file)
    if aff is None or roi_nii is None:
        return {k: float("nan") for k in
                ("coverage", "off_target", "ceiling", "efficiency", "roi_mm3")}

    roi_img = nib.load(str(roi_nii))
    roi = np.squeeze(np.asanyarray(roi_img.dataobj)) > 0.5
    roi_idx = np.array(np.nonzero(roi)).T

    # No z flip here. The affine already speaks the array's own index order:
    # main_lobe is indexed the way p_amp is stored, and the target sits at
    # nz-1-TargetLocation[2] = 107 in it, which is exactly what
    # inv(affine) @ ROI-centroid returns. Flipping again sent every ROI voxel to
    # ~279 and put the whole target outside the lobe -- coverage read 0 % on a
    # placement whose target point is demonstrably inside.
    sim, ok = _map_voxels(roi_idx, roi_img.affine, aff, main_lobe.shape)
    coverage = (float(main_lobe[sim[ok, 0], sim[ok, 1], sim[ok, 2]].sum())
                / max(len(roi_idx), 1))

    back, ok = _map_voxels(np.array(np.nonzero(main_lobe)).T, aff,
                           roi_img.affine, roi.shape)
    inside = np.zeros(len(back), dtype=bool)
    inside[ok] = roi[back[ok, 0], back[ok, 1], back[ok, 2]]
    off_target = 1.0 - float(inside.sum()) / max(len(back), 1)

    # Volumes in mm3 from each grid's own voxel size.
    roi_vox = float(np.abs(np.linalg.det(roi_img.affine[:3, :3])))
    lobe_vox = float(np.abs(np.linalg.det(aff[:3, :3])))
    roi_mm3 = len(roi_idx) * roi_vox
    lobe_mm3 = int(main_lobe.sum()) * lobe_vox
    ceiling = min(1.0, lobe_mm3 / roi_mm3) if roi_mm3 > 0 else float("nan")
    return {"coverage": coverage, "off_target": off_target,
            "ceiling": ceiling,
            "efficiency": coverage / ceiling if ceiling else float("nan"),
            "roi_mm3": roi_mm3}


def lobe_csf_fraction(acoustic_file: Path, main_lobe) -> float:
    """Fraction of the focal lobe lying in CSF, by SimNIBS's own tissue labels.

    A lobe on the caudate head can sit half in the frontal horn (42 % for
    sub-M3827 dCa-R vtx21049, 2026-09-13). That volume is wasted rather than
    harmful, but it explains a low coverage that ``off_target`` alone does not,
    since ``off_target`` counts white matter and ventricle alike.

    The label is read from ``final_tissues.nii.gz`` (charm label 3 = CSF), the
    same segmentation :func:`skull_path_mm` reads, so one definition of CSF
    serves the whole pipeline. Lobe voxels are mapped to RAS through the
    ``*_Sub.nii.gz`` affine and then into the tissue grid, the way
    :func:`roi_overlap` maps the ROI. Returns NaN when either file is missing.
    """
    import numpy as np                                          # noqa: PLC0415
    import nibabel as nib

    acoustic_file = Path(acoustic_file)
    aff = _sub_affine(acoustic_file)
    tissues = acoustic_file.parent / "final_tissues.nii.gz"
    if aff is None or not tissues.is_file():
        return float("nan")

    # Lobe voxel indices -> RAS -> tissue grid indices, sparsely
    tis_img = nib.load(str(tissues))
    tis = np.squeeze(np.asanyarray(tis_img.dataobj))
    idx, ok = _map_voxels(np.array(np.nonzero(main_lobe)).T, aff,
                          tis_img.affine, tis.shape)
    if not ok.any():
        return float("nan")
    return float((tis[idx[ok, 0], idx[ok, 1], idx[ok, 2]] == 3).mean())


def score_candidate(acoustic_file: Path, roi_nii=None) -> dict:
    """Spike-resistant focal metrics for one acoustic solve.

    The threshold is taken from the 99.99th percentile of in-brain intensity
    rather than its maximum: a reflection at a bone/brain interface can leave a
    single voxel above the focus, and half of that is then above the whole real
    lobe. See summarise_acoustic_BB, which reports both.

    Besides the focal metrics the dict carries the ROI overlap figures from
    :func:`roi_overlap` and ``csf_fraction`` from :func:`lobe_csf_fraction`.
    """
    import numpy as np                                          # noqa: PLC0415
    from scipy import ndimage

    a = _read_acoustic(acoustic_file, skin_first=False)
    p, mat, step = a.p, a.mat, a.step_mm
    ix, iy, izf = a.ix, a.iy, a.iz

    inten = (p**2) * (mat == 4)
    brain = inten[mat == 4]
    ref = float(np.percentile(brain[brain > 0], 99.99))
    main, n_main, _ = _main_lobe(inten >= 0.5 * ref)
    centre = np.array(ndimage.center_of_mass(main))
    out = {
        "lobe_mm3": float(n_main) * step**3,
        "I_at_target": float(inten[ix, iy, izf] / ref),
        "target_inside": bool(main[ix, iy, izf]),
        "offset_mm": float(np.linalg.norm((centre - np.array([ix, iy, izf])) * step)),
        "focal_peak_outlier": float(brain.max() / ref),
    }
    out.update(roi_overlap(acoustic_file, main, roi_nii))
    out["csf_fraction"] = lobe_csf_fraction(acoustic_file, main)
    return out


def write_vertices_explored(plantus_target_folder, adopted_vtx=None,
                            extra_column=None, filename="VERTICES_EXPLORED.md"):
    """Record every vertex solved for one target, as a markdown table beside it.

    The sweep prints its scores and they scroll away, and only the adopted
    vertex keeps its BabelBrain output once the rest is cleared, so without
    this the reason a placement was chosen is lost with the fields it was
    chosen from. Every column comes from :func:`score_candidate` on the
    stored acoustic h5, never re-derived by hand: measuring the focal offset
    from the field maximum, where one interface-reflection voxel outranks
    the focus, is how two earlier drafts went wrong.

    Used in: run_sweep.py.

    Parameters
    ----------
    plantus_target_folder, adopted_vtx, filename:
        PlanTUS target folder (the record is written here, beside the vtx
        directories); vertex carried forward, marked in the table; output
        name.
    extra_column:
        ``(heading, {vtx: value})`` for one further column, e.g. the share of
        the focus inside a containing structure; values formatted as
        percentages.

    Returns
    -------
    Path or None
        The record written, or None if no acoustic output was found.
    """
    import re                                                   # noqa: PLC0415

    folder = Path(plantus_target_folder)
    m = re.match(r"(sub-\S+?)_(.+)_mask-([LR])$", folder.name)
    if m is None:
        return None
    sub, target, side = m.groups()
    m2m = folder.parent.parent
    roi = m2m.parent / f"{sub}_{target}_mask-{side}.nii.gz"

    # Score every vertex that reached the acoustic stage, skipping the water runs
    rows = []
    for h5 in sorted(m2m.glob(f"{sub}_{target}-{side}_target_vtx*_DataForSim.h5")):
        if "_Water_" in h5.name:
            continue
        vtx = int(re.search(r"_target_vtx(\d+)_", h5.name).group(1))
        rows.append((vtx, score_candidate(h5, roi)))
    if not rows:
        return None

    head, values = extra_column if extra_column else (None, {})
    rows.sort(key=(lambda r: -values.get(r[0], 0)) if head else
                  (lambda r: -r[1]["efficiency"]))

    cols = ["vtx", "lobe mm3", "I@target", "inside", "offset mm",
            "coverage", "ceiling", "efficiency", "off-target", "in CSF", "outlier"]
    if head:
        cols.append(head)
    lines = [f"# {sub} {target}-{side} — vertices explored", "",
             f"ROI {rows[0][1]['roi_mm3']:.0f} mm3 · {len(rows)} vertices carried through",
             "the acoustic stage."
             + (f"  Adopted: **vtx{adopted_vtx}**." if adopted_vtx else ""), "",
             "Produced by `score_candidate()` on each stored acoustic h5 — the same",
             "function run_sweep.py prints from, so these are the sweep's numbers.",
             "Only the adopted vertex keeps its BabelBrain output; any other row can be",
             "reproduced by re-running that vertex through step 5.", "",
             "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for vtx, r in rows:
        cells = [f"{vtx}" + (" **←adopted**" if vtx == adopted_vtx else ""),
                 f"{r['lobe_mm3']:.0f}", f"{r['I_at_target']:.2f}",
                 "yes" if r["target_inside"] else "**no**", f"{r['offset_mm']:.1f}",
                 f"{100 * r['coverage']:.0f}%", f"{100 * r['ceiling']:.0f}%",
                 f"{100 * r['efficiency']:.0f}%", f"{100 * r['off_target']:.0f}%",
                 ("—" if r["csf_fraction"] != r["csf_fraction"]
                  else f"{100 * r['csf_fraction']:.0f}%"),
                 f"{r['focal_peak_outlier']:.2f}"]
        if head:
            v = values.get(vtx)
            cells.append(f"{100 * v:.1f}%" if v is not None else "—")
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["",
              "`lobe` is the largest connected component above half the 99.99th percentile",
              "of in-brain intensity; `offset` is its centroid to the aimed point.",
              "`ceiling` is the most coverage a lobe this size could reach and `efficiency`",
              "is coverage over ceiling — see roi_overlap() for why coverage alone is not",
              "readable.  `in CSF` is the share of the lobe in ventricle by the charm",
              "segmentation, wasted rather than harmful.  `outlier` at 1.5 or above means",
              "a single interface-reflection voxel outranks the focus and the row stops",
              "meaning much.", ""]

    out = folder / filename
    out.write_text("\n".join(lines))
    return out


def write_adopted_placements(data_dir, sub_ids, tx_cfg, bb_tx_yaml, out_dir=None):
    """One table of every adopted placement across subjects, from saved outputs only.

    Adopted means the placement has a ``*-ThermalField_Summary.csv``, the same
    rule :func:`select_best_vtx` uses for the ADOPTED focus. Every column is
    read from files the pipeline already wrote: the depth report (TPO setting,
    pad), the Brainsight export (entry geometry), the acoustic h5
    (:func:`score_candidate`, :func:`standoff_check_BB`), the thermal h5
    (protocol, temperatures, CEM43, MI) and the TPO summary (derating,
    free-field ISPPA). Nothing is recomputed from the settings. Writes
    ``ADOPTED_PLACEMENTS.md`` (one section per subject),
    ``ADOPTED_BY_TARGET.md`` (the same rows grouped by target, subjects side
    by side, with per-target derating and free-field ranges) and
    ``ADOPTED_PLACEMENTS.csv`` (every field) in *out_dir*, default *data_dir*.

    Placements whose files are incomplete (a thermal run in progress, a target
    folder that no longer resolves) are listed with what is available and a
    ``note``. The ``standoff`` column is the tripwire of
    :func:`standoff_check_BB`; anything beyond its tolerance is flagged.

    Used in: run_status.py.

    Returns
    -------
    tuple of (Path, Path, Path)
        The by-subject markdown, the by-target markdown and the CSV.
    """
    import csv                                                    # noqa: PLC0415
    import re                                                     # noqa: PLC0415
    from datetime import date, datetime                           # noqa: PLC0415
    import numpy as np                                            # noqa: PLC0415
    from BabelViscoFDTD.H5pySimple import ReadFromH5py            # noqa: PLC0415

    data_dir = Path(data_dir)
    out_dir = Path(out_dir) if out_dir else data_dir
    rows = []
    for sub in sub_ids:
        sub_full, sub_bare = normalise_sub_id(sub)
        sub_dir = resolve_sub_dir(data_dir, sub_bare, sub_full)
        m2m = sub_dir / f"m2m_{sub_full}"
        for csv_path in sorted(m2m.glob("*-ThermalField_Summary.csv")):
            m = re.match(rf"{re.escape(sub_full)}_(.+)-([LR])_target_vtx(\d+)_(.+)_DataForSim-ThermalField_Summary\.csv$",
                         csv_path.name)
            if not m:
                continue
            target, s, vtx = m.group(1), m.group(2), int(m.group(3))
            row = {"subject": sub_full, "target": target, "side": s, "vtx": vtx, "note": ""}
            h5 = m2m / csv_path.name.replace("-ThermalField_Summary.csv", ".h5")
            allcomb = m2m / csv_path.name.replace("_Summary.csv", "_AllCombinations.h5")
            try:
                folder = find_plantus_target_folder(m2m, sub_full, target, f"_{s}")
            except SystemExit:
                row["note"] = "PlanTUS folder not found"
                rows.append(row)
                continue
            geo = {r["vtx"]: r for r in list_plantus_vertices(folder, print_table=False)}.get(vtx, {})
            row.update(entry=geo.get("side"), elev_deg=geo.get("elev_deg"), azim_deg=geo.get("azim_deg"),
                       path_mm=geo.get("path_mm"), aim_deg=geo.get("angle_deg"),
                       skin_skull_deg=geo.get("skin_skull_deg"))
            try:
                rep = read_depth_report(folder, vtx=vtx)
                depth, verdict = focal_depth_mm(folder, vtx, tx_cfg)
                row.update(tpo_mm=depth, verdict=verdict,
                           pad_mm=float(rep.get("additional_offset_mm_assumed", 0.0)),
                           skin_to_target_mm=rep.get("skin_to_target_mm"))
            except (FileNotFoundError, ValueError) as e:
                row["note"] += f"depth report: {e}; "
            if h5.is_file():
                sc = score_candidate(h5, find_roi_mask(folder))
                row.update(I_at_target=sc["I_at_target"], inside=sc["target_inside"],
                           offset_mm=sc["offset_mm"], lobe_mm3=sc["lobe_mm3"],
                           coverage=sc["coverage"], efficiency=sc["efficiency"],
                           csf_fraction=sc["csf_fraction"])
                so = standoff_check_BB(h5, folder, vtx, bb_tx_yaml, strict=False)
                row.update(standoff_diff_mm=so["diff_mm"],
                           standoff_ok=abs(so["diff_mm"]) <= so["tol_mm"])
                row["acoustic_date"] = datetime.fromtimestamp(h5.stat().st_mtime).date().isoformat()
            else:
                row["note"] += "acoustic h5 missing; "
            srow = next(iter(csv.DictReader(open(csv_path))), {})
            row.update(insitu_isppa=srow.get("planned_insitu_isppa_w_cm2"),
                       derating_dB=srow.get("derating_dB"),
                       freefield_isppa=srow.get("required_freefield_isppa_w_cm2"),
                       freefield_ispta=srow.get("required_freefield_ispta_w_cm2"))
            if allcomb.is_file():
                th = ReadFromH5py(str(allcomb))
                combos = list(th["AllData"]) if "AllData" in th else [th]
                cd = combos[0]
                g = lambda k, d=cd: float(np.asarray(d[k]).ravel()[0])          # noqa: E731
                mat = np.array(th["MaterialMap"])
                T = np.array(cd.get("TempEndFUS", th.get("TempEndFUS")))
                base = g("BaselineTemperature") if "BaselineTemperature" in cd else _BASELINE_TEMPERATURE_C
                row.update(protocol=f"DC {g('DutyCycle'):.2f}, PRF {g('PRF'):.0f} Hz, "
                                    f"{g('DurationUS'):g} s on / {g('DurationOff'):g} s off x {g('Repetitions'):.0f}",
                           dT_brain=float(T[mat == 4].max()) - base,
                           dT_skin=float(T[mat == 1].max()) - base,
                           dT_skull=float(T[(mat == 2) | (mat == 3)].max()) - base,
                           cem43_brain=float(np.asarray(cd.get("CEMBrain", th.get("CEMBrain", np.nan))).ravel()[0]),
                           MI=g("MI") if "MI" in cd else float("nan"),
                           thermal_date=datetime.fromtimestamp(allcomb.stat().st_mtime).date().isoformat())
            else:
                row["note"] += "thermal h5 missing; "
            rows.append(row)

    # ---- CSV: every field ------------------------------------------------
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["subject", "target", "side", "vtx", "entry", "elev_deg", "azim_deg", "path_mm",
              "aim_deg", "skin_skull_deg", "tpo_mm", "pad_mm", "skin_to_target_mm", "verdict",
              "I_at_target", "inside", "offset_mm", "lobe_mm3", "coverage", "efficiency",
              "csf_fraction", "standoff_diff_mm", "standoff_ok", "protocol", "insitu_isppa",
              "derating_dB", "freefield_isppa", "freefield_ispta", "dT_brain", "dT_skin",
              "dT_skull", "cem43_brain", "MI", "acoustic_date", "thermal_date", "note"]
    csv_out = out_dir / "ADOPTED_PLACEMENTS.csv"
    with open(csv_out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    # ---- markdown cells, formatted once per row ----------------------------
    def _f(v, fmt):
        return "" if v is None or v == "" or (isinstance(v, float) and np.isnan(v)) else format(float(v), fmt)

    def _cells(r):
        so = r.get("standoff_diff_mm")
        return {
            "subject": r["subject"], "target": r["target"], "S": r["side"], "vtx": str(r["vtx"]),
            "entry": (f"{r.get('entry') or '?'} {_f(r.get('elev_deg'), '.0f')}/{_f(r.get('azim_deg'), '.0f')}"
                      if r.get("entry") else ""),
            "TPO mm (pad)": (f"{_f(r.get('tpo_mm'), '.1f')} ({_f(r.get('pad_mm'), '.0f')})"
                             if r.get("tpo_mm") is not None else ""),
            "verdict": str(r.get("verdict") or ""),
            "I@target": _f(r.get("I_at_target"), ".2f"),
            "inside": "" if r.get("inside") is None else ("yes" if r["inside"] else "**no**"),
            "eff": _f(100 * r["efficiency"], ".0f") + "%" if r.get("efficiency") is not None else "",
            "CSF": _f(100 * r["csf_fraction"], ".0f") + "%" if r.get("csf_fraction") is not None else "",
            "standoff": "" if so is None else (f"{so:+.1f}" + ("" if r.get("standoff_ok") else " **FAIL**")),
            "protocol": str(r.get("protocol") or ""),
            "derating dB": _f(r.get("derating_dB"), ".1f"),
            "FF ISPPA (in-situ)": (f"{_f(r.get('freefield_isppa'), '.0f')} ({_f(r.get('insitu_isppa'), '.0f')})"
                                   if r.get("freefield_isppa") not in (None, "") else ""),
            "dT skull": _f(r.get("dT_skull"), ".2f"), "MI": _f(r.get("MI"), ".2f"),
            "note": r.get("note", "").strip("; "),
        }

    def _table(cols, rs):
        out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        out += ["| " + " | ".join(_cells(r)[c] for c in cols) + " |" for r in rs]
        return out

    legend = ["- TPO: focal depth dialled into the TPO (PlanTUS focal distance, pad included); "
              "verdict against the calibrated 60-120 mm range",
              "- standoff: simulated minus planned exit-plane-to-skin distance, mm; flagged beyond 5 mm",
              "- FF ISPPA: free-field ISPPA the TPO needs for the planned in-situ value, W/cm2",
              "- dT: peak temperature rise in skull, degrees C; MI: mechanical index", ""]

    # ---- by subject ---------------------------------------------------------
    cols_s = ["target", "S", "vtx", "entry", "TPO mm (pad)", "verdict", "I@target", "inside", "eff",
              "CSF", "standoff", "protocol", "derating dB", "FF ISPPA (in-situ)", "dT skull", "MI", "note"]
    md = [f"# Adopted placements ({date.today().isoformat()})", "",
          "One row per placement that has a thermal summary, the rule `select_best_vtx` uses "
          "for the ADOPTED focus. Every value is read from the pipeline's own outputs "
          "(depth report, Brainsight export, acoustic h5, thermal h5, TPO summary); nothing is "
          "recomputed from the settings. Written by `run_status.py`; definitions in "
          "`config/basics/simulation_metrics.md`. The same rows grouped by target are in "
          "`ADOPTED_BY_TARGET.md`.", ""] + legend
    for sub in sub_ids:
        sub_full = normalise_sub_id(sub)[0]
        md += [f"## {sub_full}", ""] + _table(cols_s, [r for r in rows if r["subject"] == sub_full]) + [""]
    md_out = out_dir / "ADOPTED_PLACEMENTS.md"
    md_out.write_text("\n".join(md), encoding="utf-8")

    # ---- by target: subjects side by side, one experiment at a time --------
    cols_t = ["subject", "S", "vtx", "entry", "TPO mm (pad)", "verdict", "I@target", "eff", "CSF",
              "derating dB", "FF ISPPA (in-situ)", "dT skull", "MI", "note"]
    by_t = [f"# Adopted placements by target ({date.today().isoformat()})", "",
            "The rows of `ADOPTED_PLACEMENTS.md` grouped by target, so the subjects of one "
            "experiment can be compared: entry approach, TPO setting, focus metrics and the dose "
            "the TPO must deliver. Written by `run_status.py`.", ""] + legend
    for target in sorted({r["target"] for r in rows}):
        t_rows = sorted([r for r in rows if r["target"] == target], key=lambda r: (r["subject"], r["side"]))
        protocols = sorted({r["protocol"] for r in t_rows if r.get("protocol")})
        by_t += [f"## {target}", "", f"protocol: {'; '.join(protocols) or 'n/a'}", ""]
        by_t += _table(cols_t, t_rows)
        der = [float(r["derating_dB"]) for r in t_rows if r.get("derating_dB") not in (None, "")]
        ff = [float(r["freefield_isppa"]) for r in t_rows if r.get("freefield_isppa") not in (None, "")]
        if der:
            by_t += ["", f"{len(t_rows)} placements; derating median {np.median(der):.1f} dB "
                         f"({min(der):.1f} to {max(der):.1f}); free-field ISPPA for the planned in-situ "
                         f"value {min(ff):.0f} to {max(ff):.0f} W/cm2; entries "
                         + ", ".join(f"{r['subject'][4:]} {r['side']} {r.get('entry') or '?'}" for r in t_rows)]
        by_t.append("")
    by_target_out = out_dir / "ADOPTED_BY_TARGET.md"
    by_target_out.write_text("\n".join(by_t), encoding="utf-8")
    print(f"[status] {len(rows)} adopted placements -> {md_out.name}, {by_target_out.name}, {csv_out.name}")
    return md_out, by_target_out, csv_out


def write_adopted_report_pdf(data_dir, csv_path, out_path=None):
    """One PDF: per target, the comparison table, then each adopted placement's QC figures.

    Reads ``ADOPTED_PLACEMENTS.csv`` (:func:`write_adopted_placements`) and the
    figures the pipeline already saved under ``{sub}/figures/{target}/``: the
    anatomical acoustic QC (:func:`plot_acoustic_qc_BB`) and the thermal QC of
    the first protocol row (:func:`plot_thermal_qc_BB`). Nothing is recomputed;
    a missing figure leaves its slot empty with a note. Landscape A4, one table
    page per target and one page per placement.

    Used in: run_status.py.
    """
    import csv                                                    # noqa: PLC0415
    from datetime import date                                     # noqa: PLC0415
    import matplotlib                                             # noqa: PLC0415
    matplotlib.use("Agg")
    import matplotlib.image as mpimg                              # noqa: PLC0415
    import matplotlib.pyplot as plt                               # noqa: PLC0415
    from matplotlib.backends.backend_pdf import PdfPages          # noqa: PLC0415

    data_dir = Path(data_dir)
    csv_path = Path(csv_path)
    out_path = Path(out_path) if out_path else data_dir / "ADOPTED_PLACEMENTS.pdf"
    rows = list(csv.DictReader(open(csv_path)))

    def _num(v, fmt, scale=1.0, suffix=""):
        try:
            return format(float(v) * scale, fmt) + suffix
        except (TypeError, ValueError):
            return ""

    def _cells(r):
        return [r["subject"], r["side"], r["vtx"],
                f"{r.get('entry', '')} {_num(r.get('elev_deg'), '.0f')}/{_num(r.get('azim_deg'), '.0f')}".strip(),
                f"{_num(r.get('tpo_mm'), '.1f')} ({_num(r.get('pad_mm'), '.0f')})",
                r.get("verdict", ""), _num(r.get("I_at_target"), ".2f"),
                _num(r.get("efficiency"), ".0f", 100, "%"), _num(r.get("csf_fraction"), ".0f", 100, "%"),
                _num(r.get("standoff_diff_mm"), "+.1f"), _num(r.get("derating_dB"), ".1f"),
                f"{_num(r.get('freefield_isppa'), '.0f')} ({_num(r.get('insitu_isppa'), '.0f')})",
                _num(r.get("dT_skull"), ".2f"), _num(r.get("MI"), ".2f")]

    headers = ["subject", "S", "vtx", "entry el/az", "TPO (pad)", "verdict", "I@target",
               "eff", "CSF", "standoff", "derat. dB", "FF (in-situ)", "dT skull", "MI"]
    targets = sorted({r["target"] for r in rows})
    missing = []
    with PdfPages(out_path) as pdf:
        # title page
        fig = plt.figure(figsize=(11.69, 8.27))
        fig.text(0.05, 0.92, f"Adopted TUS placements ({date.today().isoformat()})", fontsize=18, weight="bold")
        y = 0.85
        for line in [
            "One row per placement that has a thermal summary, the rule select_best_vtx uses for the ADOPTED focus.",
            "Every number is read from the pipeline's own outputs (depth report, Brainsight export, acoustic and",
            "thermal h5, TPO summary); the figures are the ones step 5 saved. Definitions: config/basics/simulation_metrics.md.",
            "",
            "TPO: focal depth dialled into the TPO (PlanTUS focal distance, gel pad included); verdict against the",
            "calibrated 60-120 mm range.   standoff: simulated minus planned exit-plane-to-skin distance (mm; tolerance 5).",
            "FF ISPPA: free-field ISPPA the TPO must deliver for the planned in-situ value (W/cm2).",
            "dT skull: peak temperature rise in bone (degrees C).   MI: mechanical index.",
            "",
            f"{len(rows)} placements, {len(targets)} targets, subjects {', '.join(sorted({r['subject'] for r in rows}))}.",
            "", "Per target:"]:
            fig.text(0.05, y, line, fontsize=10); y -= 0.035
        for t in targets:
            t_rows = [r for r in rows if r["target"] == t]
            der = [float(r["derating_dB"]) for r in t_rows if r.get("derating_dB")]
            ff = [float(r["freefield_isppa"]) for r in t_rows if r.get("freefield_isppa")]
            proto = next((r["protocol"] for r in t_rows if r.get("protocol")), "n/a")
            fig.text(0.07, y, f"{t}: {len(t_rows)} placements; derating {min(der):.1f} to {max(der):.1f} dB; "
                              f"free-field {min(ff):.0f} to {max(ff):.0f} W/cm2; {proto}", fontsize=9)
            y -= 0.03
        pdf.savefig(fig); plt.close(fig)

        for t in targets:
            t_rows = sorted([r for r in rows if r["target"] == t], key=lambda r: (r["subject"], r["side"]))
            # table page
            fig, ax = plt.subplots(figsize=(11.69, 8.27))
            ax.axis("off")
            proto = next((r["protocol"] for r in t_rows if r.get("protocol")), "n/a")
            ax.set_title(f"{t}   protocol: {proto}", fontsize=13, loc="left", pad=20)
            cells = [_cells(r) for r in t_rows]
            widths = [max(len(h), *(len(c[j]) for c in cells)) + 2 for j, h in enumerate(headers)]
            tbl = ax.table(cellText=cells, colLabels=headers, loc="upper center", cellLoc="center",
                           colWidths=[w / sum(widths) for w in widths])
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(7.5)
            tbl.scale(1.0, 1.6)
            for (i, j), cell in tbl.get_celld().items():
                if i == 0:
                    cell.set_text_props(weight="bold")
                elif headers[j] == "verdict" and cell.get_text().get_text() != "ok":
                    cell.set_facecolor("#ffe6cc")
                elif headers[j] == "standoff":
                    try:
                        if abs(float(cell.get_text().get_text())) > 5:
                            cell.set_facecolor("#ffcccc")
                    except ValueError:
                        pass
            pdf.savefig(fig); plt.close(fig)
            # one page per placement
            for r in t_rows:
                sub, s, vtx = r["subject"], r["side"], r["vtx"]
                run_id = f"{sub}_{t}-{s}_target_vtx{vtx}"
                fdir = data_dir / sub / "figures" / t
                ac = fdir / f"{run_id}_acoustic_qc.png"
                th = sorted(fdir.glob(f"*/{run_id}_*_combo01_thermal_qc.png"))
                fig = plt.figure(figsize=(11.69, 8.27))
                fig.suptitle(f"{sub}  {t}  {s}  vtx{vtx}", fontsize=13, weight="bold", x=0.05, ha="left")
                cap = (f"TPO {_num(r.get('tpo_mm'), '.1f')} mm (pad {_num(r.get('pad_mm'), '.0f')}), "
                       f"{r.get('verdict', '')}; entry {r.get('entry', '')}; I@target {_num(r.get('I_at_target'), '.2f')}, "
                       f"eff {_num(r.get('efficiency'), '.0f', 100, '%')}, CSF {_num(r.get('csf_fraction'), '.0f', 100, '%')}; "
                       f"derating {_num(r.get('derating_dB'), '.1f')} dB -> free-field {_num(r.get('freefield_isppa'), '.0f')} W/cm2 "
                       f"for in-situ {_num(r.get('insitu_isppa'), '.0f')}; dT skull {_num(r.get('dT_skull'), '.2f')} C, "
                       f"MI {_num(r.get('MI'), '.2f')}; standoff {_num(r.get('standoff_diff_mm'), '+.1f')} mm")
                fig.text(0.05, 0.925, cap, fontsize=8.5)
                for k, (img, label) in enumerate(((ac, "acoustic QC"), (th[0] if th else None, "thermal QC"))):
                    ax = fig.add_axes([0.03, 0.47 - 0.46 * k, 0.94, 0.43])
                    ax.axis("off")
                    if img is not None and Path(img).is_file():
                        ax.imshow(mpimg.imread(str(img)))
                    else:
                        ax.text(0.5, 0.5, f"{label}: figure not found", ha="center", va="center", fontsize=11)
                        missing.append(f"{run_id} {label}")
                pdf.savefig(fig, dpi=110); plt.close(fig)
    print(f"[status] PDF -> {out_path.name}  ({len(rows)} placements; {len(missing)} figure(s) missing)")
    for m in missing[:10]:
        print("   missing:", m)
    return out_path


# Row colours of the acoustic summary
_GREEN  = '#4caf50'
_ORANGE = '#ff9800'
_RED    = '#f44336'
_WHITE  = '#ffffff'

# "How to read these rows", saved inside every summary HTML. Definitions
# travel inside the file, not as a link to one: the HTML gets moved (attached
# to mail, dropped in a report folder, opened on another machine) and an
# absolute file:// path into the repo breaks the moment it leaves this
# filesystem. Collapsed by default so the table stays the first thing seen.
_ACOUSTIC_SUMMARY_DEFS = [
    ('main lobe',
     'the <b>largest</b> connected component above &minus;3&nbsp;dB, '
     'matching BabelBrain. Not the component holding the maximum &mdash; '
     'that reads a small distal hotspot as the focus whenever one '
     'marginally outpeaks the true lobe.'),
    ('&asymp;GUI rows',
     'thresholded from the brain <b>maximum</b>, reproducing the '
     'BabelBrain GUI so the two can be compared.'),
    ('focal peak outlier',
     'brain maximum over the 99.99th percentile of in-brain intensity. '
     '<b>&ge;&nbsp;1.5 means a single voxel &mdash; typically a '
     'reflection at a bone/brain interface &mdash; outpeaks the focus, '
     'and the &asymp;GUI rows are meaningless.</b> Read the '
     'outlier-resistant rows instead; they threshold from the percentile. '
     'Measured 1.15&ndash;1.23 where the peak is the focus, '
     '1.9&ndash;2.8 where it is an artefact.'),
    ('FLHM centroid &rarr; target',
     'a <b>targeting error</b>: where the focus centre is, not how much '
     'of the structure is exposed. A large structure can be well covered '
     'with the centroid far off, and a small one poorly covered with it '
     'close.'),
    ('I at target',
     'intensity at the target voxel over the brain maximum. A '
     '<i>point</i> measure &mdash; a placement can reach 0.95 here while '
     'covering a quarter of what its geometry allows.'),
    ('&minus;3 dB lobe axial length',
     "the axial selectivity. Compare with the transducer's calibrated "
     'axial FLHM (DPX-500 at a 100&nbsp;mm setting: 55&nbsp;mm). Longer '
     'means the skull has smeared the focus.'),
    ('FLHM volume',
     'large is not good &mdash; it means the focus is not tight. A small '
     'volume with a low main-lobe percentage means a fragmented field.'),
]
_ACOUSTIC_SUMMARY_FOOTER = (
    '<details style="color:#9e9e9e;font:12px/1.5 sans-serif;'
    'margin-top:18px;max-width:820px">'
    '<summary style="cursor:pointer;color:#64b5f6">'
    'How to read these rows</summary>'
    '<dl>' + ''.join(
        f'<dt style="color:#e0e0e0;font-weight:600;margin-top:8px">{k}</dt>'
        f'<dd style="margin:2px 0 0 16px">{v}</dd>' for k, v in _ACOUSTIC_SUMMARY_DEFS)
    + '</dl>'
    '<p>Volumetric exposure &mdash; ROI coverage, its ceiling '
    '<code>min(1, FLHM/ROI)</code>, efficiency and off-target fraction '
    '&mdash; is reported by <code>run_sweep.py</code>, not here. '
    'Coverage is read against its ceiling, never against 100&nbsp;%: a '
    'single-element transducer cannot cover a structure larger than its '
    'focus.</p>'
    '<p>Full definitions: '
    '<code>scripts/TUS/config/basics/simulation_metrics.md</code></p>'
    '</details>'
)


def _traffic_light(v, green, orange, higher_is_better=True):
    """Row colour: green past the first bound, orange past the second, else red; white for NaN."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return _WHITE
    if higher_is_better:
        return _GREEN if v >= green else (_ORANGE if v >= orange else _RED)
    return _GREEN if v < green else (_ORANGE if v < orange else _RED)


def _html_table(title, rows):
    """Two-column dark HTML table of ``(label, value[, colour])`` rows, for the acoustic summary."""
    hdr = (
        f'<table style="border-collapse:collapse;font-family:monospace;font-size:13px;">'
        f'<tr><th colspan="2" style="background:#2a2a2a;color:#aaddff;'
        f'padding:6px 12px;text-align:left;">{title}</th></tr>'
    )
    body = ''
    for i, row in enumerate(rows):
        k, v = row[0], row[1]
        vc = row[2] if len(row) > 2 else _WHITE
        bg = '#1e1e1e' if i % 2 == 0 else '#2a2a2a'
        body += (f'<tr>'
                 f'<td style="padding:4px 12px;color:#ccc;background:{bg};">{k}</td>'
                 f'<td style="padding:4px 12px;color:{vc};background:{bg};">{v}</td>'
                 f'</tr>')
    return hdr + body + '</table>'


def _flhm_metrics(field, ix, iy, iz_f, stp, restrict=None, robust=False):
    """Return (centroid_str, volume_str, dist_mm, main_lobe_mask) of the -3 dB lobe.

    Reproduces BabelBrain's own metric exactly — verified against the GUI
    on sub-z002 vtx26749: GUI [1.1, 0.3, −0.7] mm, here [1.1, 0.3, −0.8].
    See ``_BabelBaseTx.CalcVolumetricMetrics`` and
    ``_BabelBaseTx.CalculateDistancesTarget``:

    - threshold at 0.5 of the maximum *intensity* (−3 dB), i.e.
      ``p >= p_max / √2``, taken relative to the maximum inside *restrict*;
    - **main lobe = the largest connected component** (:func:`_main_lobe`),
    - the sign convention is +z away from the transducer.

    ``robust`` swaps the maximum for the 99.99th percentile as the level the
    -3 dB threshold is taken from. A reflection at a bone/brain interface can
    put a single voxel well above the focus itself: for sub-z004 pmEC left
    only ONE brain voxel is within 90 % of the maximum and half its 27
    neighbours are cortical bone, against 586 voxels sitting in pure brain
    for the hippocampus placement. Half of that outlier is then above the
    whole real focus, so the largest component collapses to 0.3 mm3 and the
    field reads as having no focus at all, when a 922 mm3 lobe is plainly
    there. A percentile ignores a lone outlier by construction.

    *field* is pressure in the stored (distal-first) frame; ``ix, iy, iz_f``
    the target in that frame; *stp* the voxel size in mm.

    Used by: :func:`_acoustic_metrics`.
    """
    import numpy as np                                            # noqa: PLC0415
    from scipy import ndimage                                     # noqa: PLC0415

    _f = field if restrict is None else np.where(restrict, field, 0.0)
    _empty = np.zeros(field.shape, dtype=bool)
    if not np.isfinite(_f.max()) or _f.max() <= 0:
        return 'n/a', 'n/a', float('nan'), _empty
    _ref = (np.percentile(_f[_f > 0], 99.99) if robust and (_f > 0).any()
            else _f.max())
    _over = (_f >= _ref / np.sqrt(2))
    _main, _nvox, _ntot = _main_lobe(_over)
    if _ntot == 0:
        return 'n/a', 'n/a', float('nan'), _empty
    _cx, _cy, _cz = ndimage.center_of_mass(_main)
    _dx = (_cx - ix) * stp
    _dy = (_cy - iy) * stp
    # p_amp is stored distal-first, so depth decreases with index: negate to
    # get the GUI's "+z is deeper" sign.
    _dz = -(_cz - iz_f) * stp
    _dist = float(np.sqrt(_dx**2 + _dy**2 + _dz**2))
    _vol = f'{_nvox * stp**3:.1f} mm³  ({_nvox} vox)'
    if _ntot != _nvox:
        _vol += (f'   |  all −3 dB: {_ntot * stp**3:.1f} mm³ ({_ntot} vox)'
                 f'  → main lobe is {100*_nvox/_ntot:.1f}% of it')
    # A maximum outside the main lobe is the case that used to be misread.
    _pk = np.unravel_index(int(np.argmax(_f)), _f.shape)
    if not _main[_pk]:
        _vol += ('   ⚠ the maximum lies in a *different*, smaller lobe '
                 f'{abs((_pk[2] - _cz) * stp):.0f} mm away — a hotspot, '
                 'not the focus')
    return (f'[{_dx:.1f}, {_dy:.1f}, {_dz:.1f}] mm'
            f'  (dist={_dist:.1f} mm from target)',
            _vol, _dist, _main)


def _acoustic_metrics(acoustic_file):
    """Every number behind the acoustic summary, from one step-5b h5, as a dict.

    Works in the stored (distal-first) frame, as the GUI's metric code does:
    ``tgt`` carries the stored target index while the lobe arithmetic uses its
    z index in that frame. The -3 dB lobe is measured three times because the
    answers differ: whole domain (where the absolute pressure maximum sits;
    in bone for deep targets, which matters for safety, not targeting),
    brain only (where the therapeutic focus lands; thresholding against the
    brain maximum is what makes this meaningful) and brain only with the
    outlier-resistant threshold. ``off_brain_I`` uses the brain-restricted
    lobe: with the global lobe it degenerates to "all of brain" whenever the
    maximum is in bone. The axial extent is reported as a range because a
    centroid is only meaningful for one compact focus: for a long,
    low-f-number beam the axial profile is nearly flat over tens of mm
    (sub-z002 vtx26749: centroid 23.2 mm off, yet the target at 79 % of the
    brain peak and 24 mm inside the -3 dB span).

    Used by: :func:`summarise_acoustic_BB`.
    """
    import numpy as np                                            # noqa: PLC0415

    a = _read_acoustic(acoustic_file, skin_first=False)
    p, mat, stp = a.p, a.mat, a.step_mm
    nx, ny, nz = p.shape
    ix, iy, iz_f = a.ix, a.iy, a.iz
    tissue_labels = {0: 'Water/Air', 1: 'Skin', 2: 'Cortical bone',
                     3: 'Trabecular bone', 4: 'Brain'}
    p2 = p ** 2
    I_norm = p2 / p2.max()
    brain_mask = (mat == 4)
    m = {
        'shape': (nx, ny, nz), 'stp': stp, 'tgt': (ix, iy, a.tgt_stored[2]),
        'p_max': float(p.max()), 'n_vox': int(mat.size),
        'tissue_counts': {tissue_labels.get(t, str(t)): int((mat == t).sum())
                          for t in np.unique(mat)},
        'peak_brain_I': (float(I_norm[brain_mask].max()) if brain_mask.any()
                         else float('nan')),
    }
    m['flhm']    = _flhm_metrics(p, ix, iy, iz_f, stp)
    m['flhm_br'] = _flhm_metrics(p, ix, iy, iz_f, stp, restrict=brain_mask)
    m['flhm_rb'] = _flhm_metrics(p, ix, iy, iz_f, stp, restrict=brain_mask, robust=True)
    main_br = m['flhm_br'][3]

    # How far the maximum stands above the rest of the brain field. Near 1 the
    # peak is the focus; the five EC placements where the metric broke sit at
    # 1.9-2.8, the intact ones at 1.15-1.23.
    _pb = p2[brain_mask]
    m['outlier'] = (float(_pb.max() / np.percentile(_pb, 99.99))
                    if _pb.size and np.percentile(_pb, 99.99) > 0 else float('nan'))

    _off = brain_mask & ~main_br
    m['off_brain_I'] = float(I_norm[_off].max()) if _off.any() else float('nan')

    _depth = lambda _i: (nz - 1 - _i) * stp     # mm from the proximal face
    _Ib = np.where(brain_mask, p, 0.0) ** 2
    if main_br.any() and _Ib.max() > 0:
        m['tgt_I_rel'] = float(_Ib[ix, iy, iz_f] / _Ib.max())
        m['inside']    = bool(main_br[ix, iy, iz_f])
        _zs = np.where(main_br.any(axis=(0, 1)))[0]
        _lo, _hi = int(_zs.min()), int(_zs.max())
        _d_near, _d_far, _d_tgt = _depth(_hi), _depth(_lo), _depth(iz_f)
        # A lobe that runs into the brain boundary along the beam axis is cut
        # off by skull, not by the beam converging, so its true extent is
        # longer.  Test the target's own column: the plane-wide brain mask
        # stays True from off-axis brain and would never fire.
        _colb = brain_mask[ix, iy, :]
        _clip = (' — reaches the brain boundary, true extent is longer'
                 if (_lo == 0 or not _colb[_lo - 1]
                     or _hi == nz - 1 or not _colb[_hi + 1]) else '')
        m['axial_str'] = (f'{_d_near:.1f} – {_d_far:.1f} mm from skin '
                          f'({_d_far - _d_near:.1f} mm long); target at {_d_tgt:.1f} mm '
                          f'{"✓ inside" if m["inside"] else "⚠ OUTSIDE"}{_clip}')
        _xs, _ys, _ = np.where(main_br)
        _lat = (max(_xs.max() - _xs.min(), _ys.max() - _ys.min()) + 1) * stp
        m['lat_str'] = f'{_lat:.1f} mm  (widest lateral extent of the lobe)'
    else:
        m['tgt_I_rel'] = float('nan')
        m['inside']    = False
        m['axial_str'] = m['lat_str'] = 'n/a'

    # Peak focus voxel location & tissue, and its distance from the target
    px, py, pz = np.unravel_index(np.argmax(p2), p.shape)
    m['peak_vox'] = (int(px), int(py), int(pz))
    m['peak_tissue'] = tissue_labels.get(int(mat[px, py, pz]), 'Unknown')
    m['dist_to_tgt'] = float(np.sqrt(((px-ix)*stp)**2 + ((py-iy)*stp)**2 + ((pz-iz_f)*stp)**2))
    return m


def summarise_acoustic_BB(acoustic_file, fig_dir=None, standoff=None):
    """Summarise a step-5b acoustic h5: geometry, tissues, peaks and focal lobe.

    Targeting is judged on where the -3 dB lobe sits and how large it is. Read
    the brain-only rows: the whole-domain maximum sits in bone for deep
    targets. The main lobe is the largest connected component above -3 dB,
    following ``_BabelBaseTx.CalcVolumetricMetrics``; taking the component
    containing the maximum instead reads a reflection hotspot as the focus.
    ``FLHM centroid -> target (brain only)`` reproduces the GUI's "Distance
    target to FLHM center".

    Colour thresholds: peak in brain green >= 0.50, orange 0.25-0.50;
    target I green >= 0.75, orange 0.50-0.75; off-target brain I green < 0.25,
    orange 0.25-0.50; centroid offset green < 5 mm, orange 5-10 mm; axial
    extent red when the target falls outside it. Reference: Brinker et al.
    (2023) Brain Stimulation 16(3):856-871; ISO/TS 63635:2022.

    Used in: step 05 (5b), run_babelbrain.py.

    Parameters
    ----------
    acoustic_file, fig_dir:
        ``*DataForSim.h5`` from step 5b (warns and returns if missing); when
        given, ``{stem}_acoustic_summary.html`` is written there.
    standoff:
        Result of :func:`standoff_check_BB`; adds the planned and simulated
        exit-plane-to-skin rows, red when they disagree.
    """
    from IPython.display import HTML as _HTML, display as _display

    acoustic_file = str(acoustic_file)
    if not os.path.isfile(acoustic_file):
        print('[5b] DataForSim.h5 not found — run Step 5b first.')
        return

    m = _acoustic_metrics(acoustic_file)
    nx, ny, nz = m['shape']
    stp = m['stp']
    ix, iy, iz = m['tgt']
    px, py, pz = m['peak_vox']
    peak_tissue = m['peak_tissue']
    _flhm_centroid_str, _flhm_vol_str, _dist_flhm, _ = m['flhm']
    _flhm_br_centroid_str, _flhm_br_vol_str, _dist_flhm_br, _ = m['flhm_br']
    _flhm_rb_centroid_str, _flhm_rb_vol_str, _dist_flhm_rb, _ = m['flhm_rb']
    _outlier, _inside = m['outlier'], m['inside']

    # rows: (label, value_str, colour)
    rows_grid = [
        ('Grid (vox)',           f'{nx} × {ny} × {nz}',                                          _WHITE),
        ('Spatial step',         f'{stp:.4f} mm',                                                 _WHITE),
        ('Domain size',          f'{nx*stp:.1f} × {ny*stp:.1f} × {nz*stp:.1f} mm',              _WHITE),
        ('Target voxel',         f'[{ix}, {iy}, {iz}]',                                          _WHITE),
        ('Target position',      f'[{ix*stp:.1f}, {iy*stp:.1f}, {iz*stp:.1f}] mm',              _WHITE),
        ('Peak p_amp',           f'{m["p_max"]:.4f} Pa',                                          _WHITE),
        ('Peak focus voxel',     f'[{px}, {py}, {pz}]',                                          _WHITE),
        ('Peak focus position',  f'[{px*stp:.1f}, {py*stp:.1f}, {pz*stp:.1f}] mm',              _WHITE),
        ('Peak focus tissue',
         f'⚠ {peak_tissue}' if peak_tissue != 'Brain' else f'✓ {peak_tissue}',
         _GREEN if peak_tissue == 'Brain' else _ORANGE),
        ('Peak→target dist',     f'{m["dist_to_tgt"]:.1f} mm   ← absolute pressure peak; bone if skull blocks', _WHITE),
        ('Peak I (norm)',         '1.000 (focus)',                                                 _WHITE),
        ('Peak I brain',
         f'{m["peak_brain_I"]:.4f}  (norm)  ← green ≥ 0.50 | orange 0.25–0.50 | red < 0.25',
         _traffic_light(m['peak_brain_I'], 0.50, 0.25)),
        ('Off-target brain I',
         (f'{m["off_brain_I"]:.4f}  (norm)  ← green < 0.25 | orange 0.25–0.50 | red ≥ 0.50'
          if not math.isnan(m['off_brain_I']) else 'n/a'),
         _traffic_light(m['off_brain_I'], 0.25, 0.50, higher_is_better=False)),
        # ── Where the focal lobe sits, and how big it is ──────────────────
        # The centroid says where; the extent says how selective.  Report both:
        # a lobe centred on the target is worthless if it is 90 mm long.
        ('Target I (norm to brain peak)',
         (f'{m["tgt_I_rel"]:.3f}   ← green ≥ 0.75 | orange 0.50–0.75 | red < 0.50'
          if not math.isnan(m['tgt_I_rel']) else 'n/a'),
         _traffic_light(m['tgt_I_rel'], 0.75, 0.50)),
        ('−3 dB lobe axial extent (brain)', m['axial_str'],
         _WHITE if _inside else _RED),
        ('−3 dB lobe lateral width (brain)', m['lat_str'], _WHITE),
        # ── FLHM centroid — matches the BabelBrain GUI exactly ────────────
        # Verified against the GUI on sub-z002 vtx26749: GUI [1.1, 0.3, −0.7],
        # here [1.1, 0.3, −0.8].  Same threshold (−3 dB), same main-lobe rule
        # (largest component), same sign convention.
        #
        # Whole-domain rows are anchored to the global pressure maximum.  When
        # "Peak focus tissue" above is bone, that maximum is in the skull, so
        # these two rows describe the skull hotspot — the GUI restricts to
        # brain, so it is the brain-only rows that correspond to it.
        ('FLHM centroid → target (whole domain)',
         _flhm_centroid_str,
         _traffic_light(_dist_flhm, 5, 10, higher_is_better=False)),
        ('FLHM volume (−3 dB I, whole domain)', _flhm_vol_str,                                   _WHITE),
        # Brain-only FLHM: thresholded against the brain maximum rather than
        # the global one.  This is the row that reproduces the GUI.
        ('FLHM centroid → target (brain only, ≈GUI)',
         _flhm_br_centroid_str,
         _traffic_light(_dist_flhm_br, 5, 10, higher_is_better=False)),
        ('FLHM volume (−3 dB I, brain only)', _flhm_br_vol_str,                                  _WHITE),
        # Same metric with the threshold taken from the 99.99th percentile
        # instead of the maximum.  Identical to the row above when the peak is
        # the focus; the two diverge exactly when a bone/brain reflection has
        # put a single voxel above it, which is when the GUI-matching row stops
        # meaning anything.  Both are shown because only the first is
        # comparable with BabelBrain.
        ('Focal peak outlier (peak / 99.99th pct in brain)',
         (f'{_outlier:.2f}×'
          + ('   ⚠ a lone voxel outpeaks the focus — read the robust rows, '
             'not the ≈GUI ones' if _outlier >= 1.5 else '   (peak is the focus)')),
         _RED if _outlier >= 1.5 else _GREEN),
        ('FLHM centroid → target (brain, outlier-resistant)',
         _flhm_rb_centroid_str,
         _traffic_light(_dist_flhm_rb, 5, 10, higher_is_better=False)),
        ('FLHM volume (−3 dB I, brain, outlier-resistant)', _flhm_rb_vol_str,   _WHITE),
    ]
    if standoff is not None:
        _d = standoff['diff_mm']
        rows_grid += [
            ('Exit plane → skin, planned (gel pad)',
             f'{standoff["planned_mm"]:.1f} mm', _WHITE),
            ('Exit plane → skin, simulated',
             f'{standoff["simulated_mm"]:.1f} mm   (planned {_d:+.1f} mm; more than '
             f'{standoff["tol_mm"]:.0f} mm apart means the field used another pad)',
             _GREEN if abs(_d) <= standoff['tol_mm'] else _RED),
        ]
    rows_tis = [(lbl, f'{cnt:,} vox  ({100*cnt/m["n_vox"]:.1f}%)', _WHITE)
                for lbl, cnt in m['tissue_counts'].items()]

    _ref = (
        '<p style="font-family:monospace;font-size:11px;color:#888;margin-top:6px;">'
        'Colour thresholds: Brinker et al. (2023) <i>Brain Stimulation</i> 16(3):856–871 '
        '(ITRUSST TUS safety consensus); ISO/TS 63635:2022.'
        '</p>'
    )
    _html_body = (
        f'<h4 style="color:#aaddff;font-family:monospace;">Acoustic simulation summary'
        f' — {Path(acoustic_file).name}</h4>'
        + _html_table('Grid & simulation geometry', rows_grid)
        + '<br>'
        + _html_table('Tissue composition (MaterialMap)', rows_tis)
        + _ref
    )

    _display(_HTML(_html_body))

    if fig_dir is not None:
        _fig_dir = Path(fig_dir)
        _fig_dir.mkdir(parents=True, exist_ok=True)
        _stem = Path(acoustic_file).name.replace('_DataForSim.h5', '')
        _html_path = _fig_dir / f'{_stem}_acoustic_summary.html'
        _full_html = (
            '<!doctype html><html><head>'
            '<meta charset="utf-8">'
            '<style>body{background:#121212;margin:16px;}</style>'
            '</head><body>'
            + _html_body
            + _ACOUSTIC_SUMMARY_FOOTER
            + '</body></html>'
        )
        _html_path.write_text(_full_html, encoding='utf-8')
        print(f'[QC] Acoustic summary saved → {_html_path.name}')


def plot_acoustic_qc_BB(acoustic_file, fig_dir, ID, tx_system, frequency, ppw,
                        roi_nii=None):
    """Anatomical acoustic QC: sagittal and coronal intensity through the target.

    ``contourf`` at 0.1 steps in ``jet``, tissue boundaries dotted, target as
    ``+``, optional cyan ROI outline. Normalises to the whole-domain maximum,
    which sits in bone for deep targets, so a deep focus can look all blue;
    that is the normalisation, not a failed solve (compare
    :func:`save_acoustic_gui_BB`).

    Used in: step 05 (QC), run_babelbrain.py.

    Parameters
    ----------
    acoustic_file, fig_dir, ID:
        Step-5b h5, output directory, label for filename and title.
    tx_system, frequency, ppw:
        Naming only.
    roi_nii:
        Native ROI NIfTI from step 3, drawn as a contour when given.

    Returns
    -------
    str
        Path to the PNG.
    """
    import numpy as _np
    import matplotlib.pyplot as _plt
    from IPython.display import Image as _IPImage, display as _display

    acoustic_file = str(acoustic_file)
    fig_dir = Path(fig_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)

    if not os.path.isfile(acoustic_file):
        print('[QC] Acoustic file not found — run Step 5b first.')
        return ''

    # Skin-first frame, so the field aligns with z_vec (see _read_acoustic).
    _a  = _read_acoustic(acoustic_file, skin_first=True)
    ac  = _a.raw
    p, mat, stp = _a.p, _a.mat, _a.step_mm
    x_mm, y_mm, z_mm = _a.x_mm, _a.y_mm, _a.z_mm
    ix, iy, iz = _a.ix, _a.iy, _a.iz
    x_tgt = x_mm[ix]
    y_tgt = y_mm[iy]
    z_tgt = z_mm[iz]

    # Normalised intensity (proportional to I_SPPA)
    I_norm = (p ** 2) / ((p ** 2).max())        # 0 → 1

    # Peak pressure voxel — slices are centred here so the focus is always visible.
    # Target crosshair (+) marks the intended target for spatial reference.
    _peak_idx = _np.unravel_index(_np.argmax(I_norm), I_norm.shape)
    px_v, py_v, pz_v = _peak_idx
    x_peak = x_mm[px_v]
    y_peak = y_mm[py_v]

    # Remap MaterialMap to match GUI boundary layer convention:
    #   0=water  1=skin  2=bone (cortical+trabecular)  3=brain
    # Then contour([0,1,2]) draws the three tissue-layer boundaries.
    mat_plot = mat.copy()
    mat_plot[mat_plot == 3] = 2
    mat_plot[mat_plot == 4] = 3

    # Z axis: depth from simulation start (transducer entry ≈ 0)
    # GUI convention: Z axis is re-centred on TargetLocation then offset by
    # DistanceSkinToTarget so the target cross appears at the true depth.
    # h5 stores DistanceSkinToTarget (metres); fall back to z_mm[iz]-z_mm[0].
    try:
        _dist_skin_to_tgt_mm = float(ac['DistanceSkinToTarget']) * 1e3
    except (KeyError, TypeError):
        _dist_skin_to_tgt_mm = z_mm[iz] - z_mm[0]

    z_plot    = z_mm - z_mm[iz] + _dist_skin_to_tgt_mm
    z_tgt_plt = _dist_skin_to_tgt_mm
    z_peak_plt = z_plot[pz_v]

    # Levels: start from 0.05 (half BabelBrain GUI minimum) to show weak brain signal
    _levels = _np.concatenate([[0.05], _np.arange(2, 22, 2) / 20])  # [0.05, 0.1, 0.2, ..., 1.0]

    # Meshgrids (rows=Z depth, cols=X or Y) — required by contourf
    _XX, _ZZX = _np.meshgrid(x_mm, z_plot)   # (nz, nx)
    _YY, _ZZY = _np.meshgrid(y_mm, z_plot)   # (nz, ny)

    # Air mask (optional field in h5)
    _has_air = 'AirMask' in ac

    # ── Optional: ROI mask on the simulation grid (Sub NIfTI affine) ─────
    roi_3d = None
    if roi_nii and os.path.isfile(str(roi_nii)):
        try:
            _grid = _roi_on_sim_grid(acoustic_file, roi_nii, p.shape)
            if _grid is None:
                print('[QC] ROI overlay skipped: no *_FullElasticSolution_Sub.nii.gz beside the h5')
            else:
                roi_3d = _np.flip(_grid, axis=2).astype(float)     # skin-first, like p
                print(f'[QC] ROI voxels in sim grid: {int(roi_3d.sum())}')
        except Exception as _e:
            print(f'[QC] ROI overlay skipped: {_e}')

    fig, (ax1, ax2) = _plt.subplots(1, 2, figsize=(14, 7))
    fig.set_facecolor('white')

    # ── Panel 1: Sagittal slice at target Y ─────────────────────────────
    # Slice through target so the + marker is in the slice plane.
    # Peak × is projected onto the same plane (X-Z at target Y).
    _field1 = I_norm[:, iy, :].T                 # (nz, nx) — target Y slice
    im1 = ax1.contourf(_XX, _ZZX, _field1, _levels, cmap=_plt.cm.jet)
    h1 = _plt.colorbar(im1, ax=ax1)
    h1.set_label(r'$I_{\mathrm{SPPA}}$ (normalized)')
    _mat1 = mat_plot[:, iy, :].T
    ax1.contour(_XX, _ZZX, _mat1, [0, 1, 2], colors='k', linestyles=':')
    if _has_air:
        _air1 = _np.flip(_np.array(ac['AirMask']), axis=2)[:, iy, :].T
        _air1 = _np.ma.masked_where(_air1 == 0, _air1)
        ax1.contourf(_XX, _ZZX, _air1, [0, 1], cmap=_plt.cm.gray_r)
    if roi_3d is not None:
        ax1.contour(_XX, _ZZX, roi_3d[:, iy, :].T, levels=[0.5],
                    colors=['#00CCFF'], linewidths=1.8, alpha=0.9)
    ax1.set_aspect('equal')
    ax1.set_xlabel('X (mm)')
    ax1.set_ylabel('Z (mm)')
    ax1.invert_yaxis()
    ax1.plot(x_tgt,  z_tgt_plt,  '+k', markersize=18, label='target')
    ax1.plot(x_peak, z_peak_plt, 'xr', markersize=14, markeredgewidth=2, label='peak (proj.)')
    ax1.legend(fontsize=8, loc='lower right')
    ax1.set_title(f'Sagittal  (Y = {y_tgt:.1f} mm, target)')

    # ── Panel 2: Coronal slice at target X ───────────────────────────────
    _field2 = I_norm[ix, :, :].T                 # (nz, ny) — target X slice
    ax2.contourf(_YY, _ZZY, _field2, _levels, cmap=_plt.cm.jet)
    h2 = _plt.colorbar(im1, ax=ax2)
    h2.set_label(r'$I_{\mathrm{SPPA}}$ (normalized)')
    _mat2 = mat_plot[ix, :, :].T
    ax2.contour(_YY, _ZZY, _mat2, [0, 1, 2], colors='k', linestyles=':')
    if _has_air:
        _air2 = _np.flip(_np.array(ac['AirMask']), axis=2)[ix, :, :].T
        _air2 = _np.ma.masked_where(_air2 == 0, _air2)
        ax2.contourf(_YY, _ZZY, _air2, [0, 1], cmap=_plt.cm.gray_r)
    if roi_3d is not None:
        ax2.contour(_YY, _ZZY, roi_3d[ix, :, :].T, levels=[0.5],
                    colors=['#00CCFF'], linewidths=1.8, alpha=0.9)
    ax2.set_aspect('equal')
    ax2.set_xlabel('Y (mm)')
    ax2.set_ylabel('Z (mm)')
    ax2.invert_yaxis()
    ax2.plot(y_tgt,  z_tgt_plt,  '+k', markersize=18, label='target')
    ax2.plot(y_peak, z_peak_plt, 'xr', markersize=14, markeredgewidth=2, label='peak (proj.)')
    ax2.legend(fontsize=8, loc='lower right')
    ax2.set_title(f'Coronal  (X = {x_tgt:.1f} mm, target)')

    fig.suptitle(
        f"Acoustic QC — {ID}\n"
        f"Tx={tx_system}  f={int(frequency/1e3)} kHz  PPW={ppw}  Δx={stp:.3f} mm  "
        f"+ target  x={x_tgt:.1f}  y={y_tgt:.1f}  Z={z_tgt_plt:.1f} mm   "
        f"× peak  x={x_peak:.1f}  y={y_peak:.1f}  Z={z_peak_plt:.1f} mm",
        fontsize=10,
    )
    _plt.tight_layout()

    out = fig_dir / f'{ID}_acoustic_qc.png'
    fig.savefig(str(out), dpi=150, facecolor='white')
    _plt.close('all')
    print(f'[QC] Acoustic figure saved → {out.name}')
    _display(_IPImage(filename=str(out)))
    return str(out)


def save_acoustic_ortho_BB(acoustic_file, t1_path, cut_coords, fig_dir,
                           roi_nii=None, title=None, suffix=None, dpi=200,
                           threshold=0.05, draw_cross=True, roi_color='cyan',
                           roi_label=None, fmt='png'):
    """Save the interactive viewer's orthogonal view as a static figure.

    The nilearn HTML viewer cannot export the view it shows, so this renders
    the same overlay (``*_FullElasticSolution_Sub_NORM.nii.gz``, same threshold
    and colour scale) at coordinates read off the viewer. Every default
    reproduces the viewer; the keyword arguments exist so a presentation
    figure can differ at the call site without moving the defaults, which is
    what keeps past figures reproducible.

    Used in: step 05 (QC), after :func:`view_acoustic_interactive_BB`.

    Parameters
    ----------
    acoustic_file, t1_path, cut_coords, fig_dir:
        Step-5b ``*DataForSim.h5`` (the NORM NIfTI sits beside it), native T1
        background, ``(x, y, z)`` in native RAS mm, output directory.
    roi_nii:
        Step-3 target mask, drawn as a contour so focus and target can be
        compared rather than eyeballed.
    title:
        ``None`` builds the automatic title, a string replaces it, ``False``
        draws none (the filename already carries it).
    suffix:
        ``None`` becomes ``ortho_x{x}y{y}z{z}`` so several positions coexist.
    threshold:
        Display threshold as a fraction of the field maximum. 0.05 matches the
        viewer; 0.2 drops the beam column for a presentation figure.
    draw_cross, roi_color, roi_label, dpi, fmt:
        Crosshair at the cut, contour colour (cyan matches the viewer but
        vanishes against ``jet``; white does not), contour caption, resolution,
        and ``'png'`` / ``'pdf'`` / ``'svg'`` (text and contours stay vector).

    Returns
    -------
    Path or None
        The file written, or ``None`` if the NORM NIfTI is missing.
    """
    import matplotlib.pyplot as _plt
    import nibabel as _nib
    from nilearn import plotting as _plotting

    acoustic_file = str(acoustic_file)
    norm_nii = acoustic_file.replace('_DataForSim.h5',
                                     '_FullElasticSolution_Sub_NORM.nii.gz')
    if not os.path.isfile(norm_nii):
        print(f'[ortho] Normalised NIfTI not found:\n  {norm_nii}')
        print('  Run Step 5b to generate it.')
        return None

    stem = Path(acoustic_file).name.replace('_DataForSim.h5', '')
    x, y, z = (float(c) for c in cut_coords)
    if suffix is None:
        suffix = f'ortho_x{x:.0f}y{y:.0f}z{z:.0f}'
    if title is None:
        title = f'{stem}  —  p/p_max   x={x:.0f} y={y:.0f} z={z:.0f}'
    elif title is False:
        title = None                      # nilearn draws no title for None

    fig = _plt.figure(figsize=(12, 4.2))
    # cmap/vmax mirror view_acoustic_interactive_BB, and so does `threshold` at
    # its default, so the static figure and the interactive viewer cannot
    # disagree unless a caller asks them to.
    disp = _plotting.plot_stat_map(
        _nib.load(norm_nii),
        bg_img=_nib.load(str(t1_path)),
        cut_coords=(x, y, z),
        display_mode='ortho',
        threshold=threshold,
        cmap='jet',
        vmax=1.0,
        colorbar=True,
        black_bg=True,
        draw_cross=draw_cross,
        title=title,
        figure=fig,
    )
    if roi_nii and os.path.isfile(str(roi_nii)):
        disp.add_contours(str(roi_nii), levels=[0.5], colors=roi_color,
                          linewidths=1.2)
        if roi_label:
            # Top-left, not bottom-left: nilearn puts the `x=…` cut label there
            # and the two overlap.
            fig.text(0.008, 0.97, f'{roi_color} outline: {roi_label}',
                     color=roi_color, fontsize=9, ha='left', va='top')

    fig_dir = Path(fig_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)
    out = fig_dir / f'{stem}_{suffix}.{fmt}'
    fig.savefig(out, dpi=dpi, bbox_inches='tight', facecolor='black')
    _plt.close(fig)
    print(f'[ortho] Saved → {out.name}   (x={x:.0f} y={y:.0f} z={z:.0f})')
    return out


def save_acoustic_gui_BB(acoustic_file, fig_dir=None, distance_to_target=None,
                         show_water=False, title=None, suffix=None, dpi=200):
    """Reproduce the BabelBrain GUI's step-2 "Ac Sim" figure offline.

    A port of ``_BabelBaseTx.UpdateAcResults``: intensity ``p²/(2ρc)`` from the
    per-voxel material, zeroed outside brain, normalised to the brain maximum,
    filled contours at 0.1 steps in ``jet``, X-Z and Y-Z planes through the
    target. Beam-aligned (Z is depth from the skin), so it is not comparable
    panel for panel with :func:`save_acoustic_ortho_BB`, which is anatomical.

    Used in: step 05 (QC), run_babelbrain.py.

    Parameters
    ----------
    acoustic_file, fig_dir:
        Step-5b h5; output directory, or ``None`` to return the figure unsaved.
    distance_to_target:
        Skin-to-target mm for the Z labels; defaults to the value measured
        along the beam column. Shifts labels only.
    show_water:
        Plot the ``*Water_DataForSim.h5`` companion instead, the GUI's "Show
        water results".
    """
    import numpy as _np
    import matplotlib.pyplot as _plt

    acoustic_file = str(acoustic_file)
    if not os.path.isfile(acoustic_file):
        print('[gui-fig] DataForSim.h5 not found — run Step 5b first.')
        return None

    # The GUI flips p_amp and MaterialMap along z so index 0 is the skin side.
    Skull = _read_acoustic(acoustic_file, skin_first=True)
    src   = Skull
    if show_water:
        wf = acoustic_file.replace('_DataForSim.h5', '_Water_DataForSim.h5')
        if not os.path.isfile(wf):
            print(f'[gui-fig] water companion not found: {Path(wf).name}')
            return None
        src = _read_acoustic(wf, skin_first=True)

    p, mat, stp = src.p, Skull.mat, Skull.step_mm
    tgt = (Skull.ix, Skull.iy, Skull.iz)

    dens = _np.asarray(src.raw['Material'])[:, 0][src.mat]
    sos  = _np.asarray(src.raw['Material'])[:, 1][src.mat]

    # 1=skin 2=cortical 3=trabecular 4=brain  →  1=skin 2=bone 3=brain
    matp = mat.copy()
    matp[matp == 3] = 2
    matp[matp == 4] = 3

    I = p ** 2 / 2 / dens / sos
    I[matp < 3] = 0                       # brain only, as the GUI does
    I /= I.max()

    if distance_to_target is None:
        col = mat[tgt[0], tgt[1], :]
        distance_to_target = float((tgt[2] - int(_np.argmax(col != 0))) * stp)

    xv, yv = Skull.x_mm, Skull.y_mm              # already centred on the target
    zv = Skull.z_mm - Skull.z_mm[tgt[2]] + distance_to_target    # 0 = skin, +Z = deeper

    XX, ZZX = _np.meshgrid(xv, zv)
    YY, ZZY = _np.meshgrid(yv, zv)
    levels  = _np.arange(2, 22, 2) / 20

    fig, (ax1, ax2) = _plt.subplots(1, 2, figsize=(13, 9))
    for ax, (AA, ZZ, plane, mplane, lab) in zip(
            (ax1, ax2),
            ((XX, ZZX, I[:, tgt[1], :].T, matp[:, tgt[1], :].T, 'X'),
             (YY, ZZY, I[tgt[0], :, :].T, matp[tgt[0], :, :].T, 'Y'))):
        cf = ax.contourf(AA, ZZ, plane, levels, cmap=_plt.cm.jet)
        ax.contour(AA, ZZ, mplane, [0, 1, 2], colors='k', linestyles=':')
        h = fig.colorbar(cf, ax=ax)
        h.set_label(r'$I_{\mathrm{SPPA}}$ (normalized)')
        ax.set_aspect('equal')
        ax.set_xlabel(f'{lab} mm')
        ax.set_ylabel('Z mm')
        ax.invert_yaxis()
        ax.plot(0, distance_to_target, '+k', markersize=18)

    if title != '':
        fig.suptitle(title or (Path(acoustic_file).name.replace('_DataForSim.h5', '')
                               + ('   [water]' if show_water else '')),
                     fontsize=9)
    fig.tight_layout()

    if fig_dir is None:
        return fig
    fig_dir = Path(fig_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(acoustic_file).name.replace('_DataForSim.h5', '')
    out  = fig_dir / (f'{stem}_'
                      f'{suffix or ("gui_field_water" if show_water else "gui_field")}.png')
    fig.savefig(out, dpi=dpi, bbox_inches='tight', facecolor='white')
    _plt.close(fig)
    print(f'[gui-fig] Saved → {out.name}   (skin→target {distance_to_target:.2f} mm)')
    try:                                                          # noqa: SIM105
        from IPython.display import Image as _IPImage, display as _display  # noqa: PLC0415
        _display(_IPImage(filename=str(out)))
    except Exception:
        pass          # not in a notebook; the PNG is on disk either way
    return out


def view_acoustic_interactive_BB(acoustic_file, t1_path, roi_nii=None, title=None,
                                  fig_dir=None):
    """Interactive nilearn viewer of normalised acoustic intensity on the native T1.

    Loads the ``*FullElasticSolution_Sub_NORM.nii.gz`` BabelBrain writes
    beside the h5; it carries ``affineSub`` (sub-volume origin in native RAS
    mm), so the overlay registers to the T1. Notebook only; it cannot export
    its own view, which is what :func:`save_acoustic_ortho_BB` is for.

    Used in: step 05 (QC), run_babelbrain.py.

    Parameters
    ----------
    acoustic_file, t1_path:
        Step-5b ``*DataForSim.h5`` (the NORM NIfTI must sit beside it) and the
        native T1.
    roi_nii, title, fig_dir:
        ROI mask for a second viewer showing its outline; title (defaults to
        the file stem); directory to save both viewers as HTML.

    Returns
    -------
    nilearn HTML view, auto-displayed in Jupyter.
    """
    import nibabel as _nib
    from nilearn import plotting as _plotting
    from IPython.display import display as _ipy_display

    acoustic_file = str(acoustic_file)
    norm_nii = acoustic_file.replace('_DataForSim.h5', '_FullElasticSolution_Sub_NORM.nii.gz')

    if not os.path.isfile(norm_nii):
        print(f'[view] Normalised NIfTI not found:\n  {norm_nii}')
        print('  Run Step 5b to generate it.')
        return None

    stat_img = _nib.load(norm_nii)
    t1_img   = _nib.load(str(t1_path))

    stem = Path(acoustic_file).name.replace('_DataForSim.h5', '')
    if title is None:
        title = f"{stem} — p/p_max  (0 = no pressure, 1 = peak)"

    view = _plotting.view_img(
        stat_img,
        bg_img=t1_img,
        threshold=0.05,
        cmap='jet',
        symmetric_cmap=False,
        vmax=1.0,
        width_view=900,
        title=title,
    )

    if fig_dir is not None:
        _fig_dir = Path(fig_dir)
        _fig_dir.mkdir(parents=True, exist_ok=True)
        _acoustic_html = _fig_dir / f"{stem}_acoustic_interactive.html"
        view.save_as_html(str(_acoustic_html))
        print(f'[view] Acoustic viewer saved → {_acoustic_html.name}')

    # If an ROI mask is provided, display a second viewer for the target outline
    if roi_nii is not None and os.path.isfile(str(roi_nii)):
        roi_stem = Path(str(roi_nii)).name.replace('.nii.gz', '').replace('.nii', '')
        roi_view = _plotting.view_img(
            str(roi_nii),
            bg_img=t1_img,
            cmap='autumn',
            symmetric_cmap=False,
            threshold=0.5,
            vmax=1.0,
            opacity=0.85,
            width_view=900,
            title=f"Target ROI — {roi_stem}",
        )
        if fig_dir is not None:
            _roi_html = _fig_dir / f"{roi_stem}_roi_interactive.html"
            roi_view.save_as_html(str(_roi_html))
            print(f'[view] ROI viewer saved → {_roi_html.name}')
        _ipy_display(view)
        return roi_view
    elif roi_nii is not None:
        print(f'[view] ROI NIfTI not found — skipping outline:\n  {roi_nii}')

    return view


def write_tpo_summary_BB(acoustic_file, allcomb_h5, tx_cfg, sub_id_full,
                         target_name, target_side, out_dir=None, display=True):
    """Back-calculate the free-field ISPPA the TPO must deliver, per protocol row.

    The stimulation YAMLs set ``BaseIsppa`` as the in-situ ISPPA; the NeuroFUS
    TPO takes free-field (in-water) ISPPA. The two differ by the skull loss, so
    ``required_freefield_isppa = BaseIsppa / derating_ratio`` with
    ``derating_ratio = (max |p| in brain / max |p| in the water run) ** 2``,
    computed exactly as BabelBrain's "Total losses ratio" (both fields
    z-flipped, brain = ``MaterialMap >= 4``).

    When the transducer YAML carries ``calibration.isppa_w_per_cm2`` (CTX-500
    has it, the UMD DPX-500 does not), the calibrated reference and the
    required/reference factor are added. Exceeding the reference is reported,
    not blocked: the TPO power limit is adjustable, though the vendor calls it
    off-label.

    Writes ``{stem}_Summary.csv`` with one row per DC/PRF/Duration combination.

    Used in: step 05 (5c), run_babelbrain.py.

    Parameters
    ----------
    acoustic_file, allcomb_h5:
        Step-5b skull h5 (its ``*_Water_*`` companion must sit beside it) and
        the step-5c ``*_AllCombinations.h5``.
    tx_cfg : dict
        Transducer config, for the optional calibrated-reference columns.
    sub_id_full, target_name, target_side:
        Naming only.
    out_dir, display:
        CSV directory (defaults beside *allcomb_h5*); also render an HTML table.

    Returns
    -------
    str
        Path to the CSV.
    """
    import csv as _csv
    import numpy as _np
    from BabelViscoFDTD.H5pySimple import ReadFromH5py

    acoustic_file = str(acoustic_file)
    allcomb_h5    = str(allcomb_h5)
    water_file    = acoustic_file.replace('DataForSim.h5', 'Water_DataForSim.h5')

    for _f in (acoustic_file, water_file, allcomb_h5):
        if not os.path.isfile(_f):
            print(f'[TPO] Missing input — skipping summary:\n  {_f}')
            return ''

    # ── derating ratio, matching BabelBrain exactly ───────────────────────
    _ac = _read_acoustic(acoustic_file, skin_first=True)
    p_tis, matmap = _ac.p, _ac.mat
    p_wat = _read_acoustic(water_file, skin_first=True).p

    brain = (matmap >= 4)
    if not brain.any() or p_wat.max() <= 0:
        print('[TPO] No brain voxels or empty water field — skipping summary.')
        return ''
    p_brain = p_tis.copy()
    p_brain[~brain] = 0.0
    ratio    = float((p_brain.max() / p_wat.max()) ** 2)
    ratio_db = float(10.0 * _np.log10(ratio)) if ratio > 0 else float('nan')

    # ── calibrated reference ISPPA (optional) ─────────────────────────────
    _cal     = (tx_cfg or {}).get('calibration') or {}
    _cal_arr = _cal.get('isppa_w_per_cm2')
    if _cal_arr:
        _cal_arr = [float(v) for v in _cal_arr]
        ref_isppa = float(_np.mean(_cal_arr))
        ref_note  = (f'{ref_isppa:.1f} W/cm² '
                     f'(measured {min(_cal_arr):.1f}–{max(_cal_arr):.1f})')
    else:
        ref_isppa = float('nan')
        ref_note  = 'not in transducer YAML'

    # ── protocol table ────────────────────────────────────────────────────
    _th   = ReadFromH5py(allcomb_h5)
    _all  = _th.get('AllData', [])
    _idx  = _np.atleast_2d(_np.asarray(_th.get('Index', [])))

    def _scalar(d, key, fallback):
        if key in d:
            try:
                return float(_np.asarray(d[key]).ravel()[0])
            except (TypeError, ValueError, IndexError):
                pass
        return fallback

    rows = []
    for i, combo in enumerate(_all):
        _row_idx = _idx[i] if i < len(_idx) else [_np.nan] * 5
        DC  = _scalar(combo, 'DutyCycle',  _row_idx[0])
        PRF = _scalar(combo, 'PRF',        _row_idx[1])
        DUR = _scalar(combo, 'DurationUS', _row_idx[2])
        OFF = _scalar(combo, 'DurationOff', _row_idx[3])
        REP = _scalar(combo, 'Repetitions', 1)
        isppa_insitu = _scalar(combo, 'MaxIsppa', _row_idx[4])

        req_isppa = isppa_insitu / ratio
        req_ispta = req_isppa * DC
        factor    = req_isppa / ref_isppa if _np.isfinite(ref_isppa) else float('nan')
        max_insitu_at_ref = (ref_isppa * ratio) if _np.isfinite(ref_isppa) else float('nan')

        rows.append({
            'subject':                        sub_id_full,
            'target':                         f'{target_name}{target_side}',
            'tx':                             tx_cfg.get('name', tx_cfg.get('id', '')),
            'combo':                          i + 1,
            'DC':                             round(DC, 4),
            'PRF_Hz':                         round(PRF, 3),
            'duration_on_s':                  round(DUR, 3),
            'duration_off_s':                 round(OFF, 3),
            'repetitions':                    int(REP) if _np.isfinite(REP) else '',
            'planned_insitu_isppa_w_cm2':     round(isppa_insitu, 4),
            'derating_ratio':                 round(ratio, 6),
            'derating_dB':                    round(ratio_db, 3),
            'required_freefield_isppa_w_cm2': round(req_isppa, 2),
            'required_freefield_ispta_w_cm2': round(req_ispta, 2),
            'calibrated_ref_isppa_w_cm2':     ('' if not _np.isfinite(ref_isppa)
                                               else round(ref_isppa, 2)),
            'factor_vs_calibrated_ref':       ('' if not _np.isfinite(factor)
                                               else round(factor, 3)),
            'exceeds_calibrated_ref':         ('' if not _np.isfinite(factor)
                                               else bool(factor > 1.0)),
            'insitu_isppa_at_ref_w_cm2':      ('' if not _np.isfinite(max_insitu_at_ref)
                                               else round(max_insitu_at_ref, 3)),
        })

    if not rows:
        print('[TPO] No combinations found in the thermal output — skipping summary.')
        return ''

    out_dir  = str(out_dir) if out_dir else os.path.dirname(allcomb_h5)
    csv_path = os.path.join(
        out_dir,
        os.path.basename(allcomb_h5).replace('_AllCombinations.h5', '_Summary.csv'))
    os.makedirs(out_dir, exist_ok=True)
    with open(csv_path, 'w', newline='') as _fh:
        w = _csv.DictWriter(_fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f'[TPO] Derating ratio {ratio:.6f} ({ratio_db:.2f} dB)   '
          f'calibrated ref ISPPA: {ref_note}')
    for r in rows:
        _flag = ('  ⚠ above calibrated reference — requires raising the TPO power '
                 'limit (vendor calls this off-label)'
                 if r['exceeds_calibrated_ref'] is True else '')
        print(f"[TPO] combo {r['combo']}: in-situ "
              f"{r['planned_insitu_isppa_w_cm2']} W/cm² needs free-field ISPPA "
              f"{r['required_freefield_isppa_w_cm2']} W/cm² "
              f"(ISPTA {r['required_freefield_ispta_w_cm2']}){_flag}")
        if r['insitu_isppa_at_ref_w_cm2'] != '':
            print(f"[TPO]   at the calibrated {r['calibrated_ref_isppa_w_cm2']} W/cm² "
                  f"reference the achievable in-situ ISPPA is "
                  f"{r['insitu_isppa_at_ref_w_cm2']} W/cm²")
    print(f'[TPO] Summary written: {os.path.basename(csv_path)}')

    if display:
        try:
            from IPython.display import HTML as _HTML, display as _display
            _hdr = ''.join(f'<th style="padding:3px 8px;text-align:left">{k}</th>'
                           for k in rows[0].keys())
            _body = ''
            for r in rows:
                _cells = ''
                for k, v in r.items():
                    _bg = ('#ffe0b2' if k == 'exceeds_calibrated_ref' and v is True
                           else '#ffffff')
                    _cells += (f'<td style="padding:3px 8px;background:{_bg}">'
                               f'{v}</td>')
                _body += f'<tr>{_cells}</tr>'
            _display(_HTML(
                f'<div style="overflow-x:auto"><table style="border-collapse:collapse;'
                f'font-size:12px"><tr>{_hdr}</tr>{_body}</table></div>'))
        except ImportError:
            pass

    return csv_path


def plot_thermal_qc_BB(allcomb_h5, field_target, m2m_dir, fig_dir, ID,
                       sub_id_full, target_name, target_side, tx_system, frequency,
                       acoustic_file=None, stim_label=None):
    """Thermal QC figures in the BabelBrain GUI's step-3 layout, one per protocol row.

    Left: ISPPA on the sagittal slice through the target (needs
    *acoustic_file*); middle: temperature at the end of sonication on the same
    slice, on one fixed colour range for every figure (baseline to baseline +
    ``_THERMAL_DT_LIMIT_C``, the ITRUSST 2 °C limit; hotter voxels saturate);
    right: maximum temperature and CEM43 per tissue and MI against the 1.9
    guideline. Axes are mm from the skin and lateral mm from the beam axis,
    with the skull boundary dashed and the target as ``+``.

    Used in: step 05 (QC), run_babelbrain.py.

    Parameters
    ----------
    allcomb_h5, field_target, m2m_dir:
        ``*_AllCombinations.h5`` from step 5c, its BabelBrain prefix, and the
        ``m2m_*`` directory; each falls back to a glob if the path is stale.
    fig_dir, ID, sub_id_full, target_name, target_side, tx_system, frequency:
        Output directory and naming.
    acoustic_file:
        Step-5b h5 for the ISPPA panel and physical axes; without it the panel
        is a placeholder and axes are voxels.
    stim_label:
        Protocol label in the figure directory and filename. The baseline
        temperature is read from the h5, where BabelBrain stores it per
        combination.

    Returns
    -------
    list[str]
        Paths to the PNGs, one per combination.
    """
    import glob as _glob
    import numpy as _np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as _plt
    from IPython.display import Image as _IPImage, display as _display
    from BabelViscoFDTD.H5pySimple import ReadFromH5py

    fig_dir = Path(fig_dir)
    m2m_dir = Path(m2m_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)

    # ── Resolve AllCombinations.h5 ────────────────────────────────────────
    _ac_path = str(allcomb_h5) if allcomb_h5 and os.path.isfile(str(allcomb_h5)) else ''
    if not _ac_path:
        _cands = _glob.glob(str(m2m_dir / f'{field_target}*_AllCombinations.h5'))
        _ac_path = _cands[0] if _cands else ''
    if not _ac_path:
        print('[QC] AllCombinations.h5 not found — run Step 5c first.')
        return []

    th  = ReadFromH5py(_ac_path)

    # Thermal h5 stores data proximal-first (skin = z_index 0).
    # No flip needed — TargetLocation is also in proximal-first coordinates.
    mat = _np.array(th['MaterialMap'])                     # (nx, ny, nz) skin-first
    tgt = _np.array(th['TargetLocation']).astype(int)     # [ix, iy, iz] skin-first
    nx, ny, nz = mat.shape
    ix, iy, iz = tgt
    iz_f = iz    # TargetLocation already in proximal-first (skin=0) coords

    # Skull contour: remap material codes
    #   0=water/air  1=skin  2=cortical  3=trabecular  4=brain
    # → contour at 0.5 (water→skin) and 2.5 (skull→brain)
    mat_plot = mat.copy()
    mat_plot[mat_plot == 3] = 2     # merge trabecular into cortical
    mat_plot[mat_plot == 4] = 3     # brain → 3

    try:
        all_data = list(th['AllData'])
    except (KeyError, TypeError):
        all_data = [th]     # single combo: top-level dict acts as combo[0]

    # ── Load acoustic file for Isppa map + physical coordinates ──────────
    _have_ac = False
    if acoustic_file and os.path.isfile(str(acoustic_file)):
        _ac   = _read_acoustic(acoustic_file, skin_first=True)   # skin-first, like th
        p_ac  = _ac.p
        stp   = _ac.step_mm                                      # mm/vox
        x_mm, y_mm, z_mm = _ac.x_mm, _ac.y_mm, _ac.z_mm
        _have_ac = True
    else:
        # Fallback: estimate from thermal h5
        stp   = float(th.get('SpatialStep', 3.675e-4)) * 1e3
        x_mm  = _np.arange(nx) * stp
        y_mm  = _np.arange(ny) * stp
        z_mm  = _np.arange(nz) * stp
        p_ac  = None

    z_depth = z_mm - z_mm[0]           # 0 = skin surface (mm from skin)
    x_rel   = x_mm - x_mm[ix]          # 0 = target lateral centre (mm)

    # Display window (matches GUI panel size).  The depth range must reach the
    # target: a fixed 90 mm cap cropped the focus out of both maps for deep
    # targets — hippocampus sits ~104 mm from the skin, so the focal region and
    # the '+' marker fell off-plot even though the reported numbers were right.
    # Shallow targets keep the familiar 90 mm window.
    _x_half   = 25.0                                  # mm lateral half-width
    _z_target = float(z_depth[iz_f])                  # target depth from skin
    _z_max    = min(max(90.0, _z_target + 15.0),      # 15 mm past the target
                    z_depth[-1])                      # never beyond the domain

    # Meshgrid for contourf — shape (nz, nx): rows=depth, cols=lateral
    _XX, _ZZ = _np.meshgrid(x_rel, z_depth)

    # Font sizes (large enough to read)
    FS_LBL  = 13
    FS_TICK = 11
    FS_TITL = 14
    FS_CB   = 12

    SKULL_COLOR  = '#FFD700'    # yellow (GUI skull contour)
    SKULL_LEVEL  = [0.5, 2.5]  # skin outer + skull-brain boundaries

    saved = []
    for ci, cd in enumerate(all_data):
        ISPPA    = float(_np.array(cd['Isppa']))
        DC       = float(_np.array(cd['DutyCycle']))
        PRF      = float(_np.array(cd['PRF']))
        DUR      = float(_np.array(cd['DurationUS']))
        DUR_OFF  = float(_np.array(cd['DurationOff']))
        REPS     = float(_np.array(cd.get('Repetitions', 1))) if isinstance(cd, dict) else 1.0
        _bt = cd.get('BaselineTemperature') if isinstance(cd, dict) else None
        baseline_t = float(_np.array(_bt)) if _bt is not None else _BASELINE_TEMPERATURE_C

        def _cem(k, _cd=cd, _th=th):
            v = _cd.get(k) if isinstance(_cd, dict) else None
            if v is None:
                v = _th.get(k, 0.0)
            return float(_np.array(v))

        CEM_brain = _cem('CEMBrain')
        CEM_skin  = _cem('CEMSkin')
        CEM_skull = _cem('CEMSkull')

        # Mechanical index — computed by BabelBrain (independent of the thermal/CEM
        # metrics above); no silent 0.0 fallback, since that would read as "safe".
        _mi_raw = cd.get('MI') if isinstance(cd, dict) else None
        if _mi_raw is None:
            _mi_raw = th.get('MI')
        MI = float(_np.array(_mi_raw)) if _mi_raw is not None else float('nan')

        # Per-combo temperature map (try cd first, fall back to th)
        _raw_T = cd.get('TempEndFUS') if isinstance(cd, dict) else None
        if _raw_T is None:
            _raw_T = th.get('TempEndFUS')
        T_abs = _np.array(_raw_T)   # (nx,ny,nz) proximal-first (skin=z0) — no flip needed

        # Sagittal slice at y=iy → (nz, nx) for contourf
        T_sl  = T_abs[:, iy, :].T          # (nz, nx)
        mat_sl = mat_plot[:, iy, :].T      # (nz, nx)

        # Isppa slice: I_norm × ISPPA → W/cm²  (normalized to water peak)
        if p_ac is not None:
            _p_max2 = float(p_ac.max() ** 2)
            I_sl = ((p_ac[:, iy, :] ** 2) / _p_max2) * ISPPA  # (nx, nz)
            I_sl = I_sl.T                                        # (nz, nx)
        else:
            I_sl = None

        # Compute scalar safety metrics from spatial arrays
        t_brain_max = float(T_abs[mat == 4].max()) if (mat == 4).any() else _np.nan
        t_skin_max  = float(T_abs[mat == 1].max()) if (mat == 1).any() else _np.nan
        t_skull_max = (float(T_abs[(mat == 2) | (mat == 3)].max())
                       if ((mat == 2) | (mat == 3)).any() else _np.nan)
        t_target    = float(T_abs[ix, iy, iz_f])

        # Temperature colour range: the same on every figure so placements and
        # protocols compare by eye: baseline to baseline + the ITRUSST limit,
        # hotter voxels saturate. Until 2026-09-21 the range followed each
        # field's own maximum, so a 0.05 °C rise looked like a 1 °C one.
        T_vmin = baseline_t
        T_vmax = baseline_t + _THERMAL_DT_LIMIT_C

        # ── Figure: 2 map panels + right summary column ───────────────
        fig = _plt.figure(figsize=(15, 6.5), facecolor='white')
        gs  = _plt.GridSpec(1, 3, figure=fig, wspace=0.42,
                            left=0.07, right=0.97, top=0.88, bottom=0.12,
                            width_ratios=[4, 4, 3])

        def _map_ax(gs_pos, title):
            ax = fig.add_subplot(gs_pos)
            ax.set_facecolor('white')
            ax.set_xlabel('Lateral (mm)', fontsize=FS_LBL)
            ax.set_ylabel('Distance from skin (mm)', fontsize=FS_LBL)
            ax.tick_params(labelsize=FS_TICK)
            ax.set_xlim(-_x_half, _x_half)
            ax.set_ylim(_z_max, 0)                # y-axis: 0=skin at top
            ax.set_title(title, fontsize=FS_TITL, pad=8)
            return ax

        # ── Left: Isppa (W/cm²) ──────────────────────────────────────
        axL = _map_ax(gs[0], 'Isppa (W/cm²)')
        if I_sl is not None:
            _levels_i = _np.linspace(0, ISPPA, 30)
            im_i = axL.contourf(_XX, _ZZ, I_sl, levels=_levels_i,
                                 cmap='jet', vmin=0, vmax=ISPPA, extend='max')
            cb_i = _plt.colorbar(im_i, ax=axL, shrink=0.9, pad=0.02,
                                 ticks=_np.linspace(0, ISPPA, 6))
            cb_i.set_label('Isppa (W/cm²)', fontsize=FS_CB)
            cb_i.ax.tick_params(labelsize=FS_TICK)
        else:
            axL.text(0.5, 0.5, 'Isppa map unavailable\n(pass acoustic_file)',
                     ha='center', va='center', transform=axL.transAxes,
                     fontsize=11, color='grey')
        axL.contour(_XX, _ZZ, mat_sl, levels=SKULL_LEVEL,
                    colors=[SKULL_COLOR], linestyles='--', linewidths=1.8)
        axL.plot(0.0, z_depth[iz_f], '+k', markersize=20, markeredgewidth=2.5)

        # ── Right: Temperature (°C) ───────────────────────────────────
        axR = _map_ax(gs[1], 'Temperature (°C)')
        _levels_t = _np.linspace(T_vmin, T_vmax, 41)          # 0.05 °C steps
        im_t = axR.contourf(_XX, _ZZ, T_sl, levels=_levels_t,
                             cmap='jet', vmin=T_vmin, vmax=T_vmax, extend='max')
        cb_t = _plt.colorbar(im_t, ax=axR, shrink=0.9, pad=0.02,
                             ticks=_np.arange(T_vmin, T_vmax + 1e-6, 0.5))
        cb_t.set_label(f'Temperature (°C)   top = baseline + '
                       f'{_THERMAL_DT_LIMIT_C:g} °C (ITRUSST)', fontsize=FS_CB)
        cb_t.ax.tick_params(labelsize=FS_TICK)
        axR.contour(_XX, _ZZ, mat_sl, levels=SKULL_LEVEL,
                    colors=[SKULL_COLOR], linestyles='--', linewidths=1.8)
        axR.plot(0.0, z_depth[iz_f], '+k', markersize=20, markeredgewidth=2.5)

        # ── Summary column ────────────────────────────────────────────
        axS = fig.add_subplot(gs[2])
        axS.axis('off')

        def _nan_str(v, fmt='.3f'):
            return f'{v:{fmt}} °C' if _np.isfinite(v) else 'n/a'

        # MI (mechanical index) — independent safety axis from the thermal/CEM
        # metrics below; not affected by DC/PRF/Duration, only by pressure & frequency.
        FDA_MI_LIMIT = 1.9
        if _np.isfinite(MI):
            _mi_str   = f'{MI:.2f}  (FDA limit {FDA_MI_LIMIT})'
            _mi_color = '#cc0000' if MI > FDA_MI_LIMIT else '#008800'
        else:
            _mi_str   = 'n/a'
            _mi_color = '#444444'

        # The summary panel is narrow, so a right-aligned value collides with the
        # left-aligned label whenever the two together exceed the axis width
        # (e.g. 'Max T brain' + '37.260 °C   CEM43: 0.0004').  Declare the rows
        # first, measure them, then lay out: long values move onto their own line
        # and the line spacing is derived from the final line count so the block
        # always fits.  CEM43 is split into its own rows to keep values short.
        FS_ROW = 11
        _SEP   = ('sep', '', '', '')
        _rows = [
            ('row', 'Subject',         sub_id_full,                          '#000000'),
            ('row', 'Target',          f'{target_name}{target_side}',        '#000000'),
            ('row', 'Tx',              f'{tx_system}  {int(frequency/1e3)} kHz', '#000000'),
            ('row', 'ISPPA',           f'{ISPPA:.2f} W/cm²',                 '#000000'),
            ('row', 'DC / PRF',        f'{DC*100:.0f}%  /  {PRF:.1f} Hz',    '#000000'),
            ('row', 'On / Off',        f'{DUR:g} s / {DUR_OFF:g} s' + (f'  x {REPS:.0f}' if REPS > 1 else ''), '#000000'),
            _SEP,
            ('row', 'Max T brain',     _nan_str(t_brain_max),                '#000000'),
            ('row', 'Max T skin',      _nan_str(t_skin_max),                 '#000000'),
            ('row', 'Max T skull',     _nan_str(t_skull_max),                '#000000'),
            ('row', 'T at target',     _nan_str(t_target),                   '#000000'),
            _SEP,
            ('row', 'CEM43 brain',     f'{CEM_brain:.4f}',                   '#000000'),
            ('row', 'CEM43 skin',      f'{CEM_skin:.4f}',                    '#000000'),
            ('row', 'CEM43 skull',     f'{CEM_skull:.4f}',                   '#000000'),
            _SEP,
            ('row', 'MI (mechanical)', _mi_str,                              _mi_color),
        ]

        try:
            _rend = fig.canvas.get_renderer()
        except Exception:
            _rend = None

        def _w_axes(s):
            """Width of *s* at FS_ROW, in axes-fraction units."""
            t = axS.text(0.0, -1.0, s, transform=axS.transAxes, fontsize=FS_ROW)
            try:
                w = (t.get_window_extent(renderer=_rend)
                      .transformed(axS.transAxes.inverted()).width)
            except Exception:
                w = 0.055 * len(s)          # fallback: rough per-glyph advance
            t.remove()
            return w

        # Pass 1 — decide which rows must stack, and count the lines needed.
        _plan   = []
        _n_line = 0
        _n_sep  = 0
        for _kind, _lbl, _val, _col in _rows:
            if _kind == 'sep':
                _plan.append((_kind, _lbl, _val, _col, False))
                _n_sep += 1
                continue
            _stacked = (_w_axes(_lbl) + _w_axes(_val)) > 0.97
            _plan.append((_kind, _lbl, _val, _col, _stacked))
            _n_line += 2 if _stacked else 1

        # Pass 2 — spacing that always fits: header 1.3 lines, separators 0.5.
        _top = 0.97
        dy   = min(0.075, (_top - 0.02) / (1.3 + 0.5 * _n_sep + _n_line))

        ys = _top
        axS.text(0.5, ys, 'Safety summary', transform=axS.transAxes,
                 fontsize=FS_TITL - 1, ha='center', va='top', fontweight='bold')
        ys -= dy * 1.3

        for _kind, _lbl, _val, _col, _stacked in _plan:
            if _kind == 'sep':
                _sy = ys + dy * 0.25
                axS.plot([0.0, 1.0], [_sy, _sy], transform=axS.transAxes,
                         color='#aaaaaa', linewidth=0.8, clip_on=False)
                ys -= dy * 0.5
                continue
            axS.text(0.0, ys, _lbl, transform=axS.transAxes,
                     fontsize=FS_ROW, color='#444444', ha='left', va='top')
            if _stacked:
                ys -= dy
            axS.text(1.0, ys, _val, transform=axS.transAxes,
                     fontsize=FS_ROW, color=_col, ha='right', va='top')
            ys -= dy

        if ci + 1 < len(all_data):
            axS.text(0.5, ys, f'Combo {ci+1} / {len(all_data)}',
                     transform=axS.transAxes, fontsize=FS_ROW,
                     ha='center', va='top', color='#666666')

        fig.suptitle(
            f"Thermal QC  —  {ID}     "
            f"ISPPA={ISPPA:.1f} W/cm²   DC={DC*100:.0f}%   "
            f"On={DUR:g}s / Off={DUR_OFF:g}s" + (f" x{REPS:.0f}" if REPS > 1 else ""),
            fontsize=FS_TITL, y=0.97,
        )

        _stim_part = f'_{stim_label}' if stim_label else ''
        out = fig_dir / f'{ID}{_stim_part}_combo{ci+1:02d}_thermal_qc.png'
        fig.savefig(str(out), dpi=150, facecolor='white')
        _plt.close('all')
        print(f'[QC] Thermal figure (combo {ci+1}) saved → {out.name}')
        if _np.isfinite(MI):
            _mi_flag = 'EXCEEDS' if MI > FDA_MI_LIMIT else 'within'
            print(f'[Safety] MI = {MI:.2f}  ({_mi_flag} FDA diagnostic-ultrasound limit of {FDA_MI_LIMIT})')
        else:
            print('[Safety] MI not found in AllCombinations.h5 (older BabelBrain output?)')
        _display(_IPImage(filename=str(out)))
        saved.append(str(out))

    return saved
