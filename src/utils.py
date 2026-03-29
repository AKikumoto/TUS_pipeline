"""
scripts/TUS/src/utils.py
Common utilities shared across all TUS pipeline steps.

Rule: every function that is used by a run/ script lives here.
Each function documents which step(s) use it.

Functions
---------
Config helpers
  load_site_config            All steps — load + validate site YAML.
  try_load_site_config        Test step 01 — load site YAML returning (cfg, err).
  load_transducer_config      Step 04 — load transducer YAML referenced in site config.
  resolve_data_dir            Steps 01, 04 — resolve absolute subject-data directory.
  try_resolve_data_dir        Test step 01 — resolve data dir returning (path, err).

Subject ID helpers
  normalise_sub_id            All steps — return (sub_id_full, sub_id_bare).
  resolve_sub_dir             All steps — return subject dir, supporting bare and BIDS naming.

File helpers
  find_t1                     Step 01 — find BIDS T1w NIfTI for a subject.
  output_exists_simnibs       Steps 01, test 01 — check charm output presence.
  parse_sub_list              Steps 01, test 01 — read subject IDs from text file.

Step 01 — SimNIBS segmentation (charm)
  run_fix_qform               Step 01 — run fslorient -copysform2qform.
  run_charm                   Step 01 — run SimNIBS charm.
  process_subject             Step 01 — orchestrate fix-qform + charm for one subject.

Test helpers (step 01 validation)
  check_pass                  Test step 01 — build PASS result dict.
  check_fail                  Test step 01 — build FAIL result dict.
  check_warn                  Test step 01 — build WARN result dict.
  chk_yaml_loadable           Test step 01 — check site YAML is loadable.
  chk_required_keys           Test step 01 — check required config keys present.
  chk_data_dir                Test step 01 — check data directory exists.
  chk_charm_available         Test step 01 — check charm binary in PATH.
  chk_fslorient_available     Test step 01 — check fslorient binary accessible.
  chk_sub_dir                 Test step 01 — check subject directory exists.
  chk_t1_exists               Test step 01 — check T1w file exists.
  chk_charm_output            Test step 01 — check charm output files present.
  run_environment_checks      Test step 01 — run all environment checks.
  run_subject_checks          Test step 01 — run all per-subject checks.
  print_checks                Test step 01 — print check results, return FAIL count.

Step 04 — PlanTUS target planning
  setup_environment           Step 04 — extend PATH/env vars from site config.
  transducer_params           Step 04 — extract PlanTUS params from transducer config.
  find_plantus_target_folder  Step 04 — locate PlanTUS output folder for a target.
  get_plantus_vtx_dir         Step 04 — return (vtx_dir, vtx_id) for a PlanTUS folder.
  select_best_vtx             Step 04 — auto-select best scalp vertex from metric GIFTIs.
  report_depth_and_gel        Step 04 — print/save depth + gel thickness report.
  prepare_plantus_scene       Step 04a, notebook — mesh → surfaces, metrics, scene file.
  run_plantus_placement       Step 04b, notebook — acoustic placement for a vertex index.
  run_plantus                 Step 04 (notebook) — full GUI workflow (pynput optional).
  get_vtx_coordinates         Step 04, notebook — load entry/target coords from vtx dir.
  write_brainsight_txt        Step 04 — write BrainSight-compatible target .txt.
  write_brainsight_for_vtx    Step 04 (notebook) — full BrainSight export from vtx folder.

Step 05 — Inverse registration (MNI → native)
  ants_to_nib                 Step 05 — convert ANTs image to nibabel NIfTI1Image.
  register_mni_to_native      Step 05 — ANTs MNI→native registration (Affine/SyN/SyNCC).
  apply_inverse_transform     Step 05 — warp MNI mask into native space and save.
  compute_com_native          Steps 05, 04 (CoM) — centre-of-mass in native mm.
  compute_peak_native         Step 05 (peak_func) — peak voxel of functional map within mask.
  visualize_mask_native       Step 05 — tri-planar static mask overlay on native T1.
"""

import math
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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

#: Symbols for check result display. Used in: test step 01.
SYMBOLS: dict[str, str] = {"PASS": "✓", "FAIL": "✗", "WARN": "!"}


# ===========================================================================
# Config helpers
# ===========================================================================

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


def try_load_site_config(yaml_path: str | Path) -> tuple[dict | None, str | None]:
    """Load site YAML returning ``(cfg, err)`` instead of calling sys.exit.

    Used in: test step 01.

    Returns
    -------
    (cfg, None)  on success.
    (None, err)  on failure, where *err* is an error message string.
    """
    yaml_path_obj = Path(yaml_path).expanduser().resolve()
    if not yaml_path_obj.exists():
        return None, f"site config not found: {yaml_path_obj}"
    try:
        with open(yaml_path_obj) as f:
            cfg = yaml.safe_load(f)
        for key in _PATH_KEYS:
            if key in cfg and isinstance(cfg[key], str):
                cfg[key] = str(Path(cfg[key]).expanduser())
        return cfg, None
    except Exception as e:
        return None, str(e)


def load_transducer_config(cfg: dict, site_yaml_path: str | Path) -> dict:
    """Load the transducer YAML referenced in *cfg['transducer']*.

    Used in: step 04.

    The transducer YAML is expected at::

        config/transducers/{transducer_name}.yaml

    relative to the directory that contains the site YAML.

    Parameters
    ----------
    cfg:
        Loaded site config (from :func:`load_site_config`).
    site_yaml_path:
        Path to the site YAML, used to locate ``config/transducers/``.

    Raises
    ------
    SystemExit
        If the transducer key is missing or the file is not found.
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


def try_resolve_data_dir(cfg: dict) -> tuple[Path | None, str | None]:
    """Resolve the data directory returning ``(path, err)`` instead of sys.exit.

    Used in: test step 01.
    """
    data_root = Path(cfg["data_root"]).expanduser()
    sub_list_dir = cfg.get("sub_list_dir", "")
    d = Path(sub_list_dir)
    if not d.is_absolute():
        d = data_root / sub_list_dir
    if not d.exists():
        return None, f"data directory not found: {d}"
    return d, None


# ===========================================================================
# Subject ID helpers
# ===========================================================================

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


# ===========================================================================
# File helpers
# ===========================================================================

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


# ===========================================================================
# Step 01 — SimNIBS segmentation (charm)
# ===========================================================================

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


# ===========================================================================
# Test helpers — step 01 validation
# ===========================================================================

def check_pass(label: str, detail: str = "") -> dict:
    """Build a PASS result dict.  Used in: test step 01."""
    return {"status": "PASS", "label": label, "detail": detail}


def check_fail(label: str, detail: str = "") -> dict:
    """Build a FAIL result dict.  Used in: test step 01."""
    return {"status": "FAIL", "label": label, "detail": detail}


def check_warn(label: str, detail: str = "") -> dict:
    """Build a WARN result dict.  Used in: test step 01."""
    return {"status": "WARN", "label": label, "detail": detail}


def chk_yaml_loadable(yaml_path: str) -> dict:
    """Check that the site YAML loads without error.  Used in: test step 01."""
    cfg, err = try_load_site_config(yaml_path)
    if err:
        return check_fail("site yaml loadable", err)
    return check_pass("site yaml loadable", str(Path(yaml_path).resolve()))


def chk_required_keys(cfg: dict) -> dict:
    """Check required config keys are present.  Used in: test step 01."""
    required = ["data_root", "sub_list_dir", "fsl_bin", "segmentation"]
    missing = [k for k in required if k not in cfg]
    if missing:
        return check_fail("required config keys", f"missing: {missing}")
    if cfg.get("segmentation") != "SimNIBS":
        return check_warn(
            "segmentation method",
            f"config says '{cfg.get('segmentation')}', expected SimNIBS",
        )
    return check_pass("required config keys")


def chk_data_dir(cfg: dict) -> dict:
    """Check data directory exists.  Used in: test step 01."""
    d, err = try_resolve_data_dir(cfg)
    if err:
        return check_fail("data directory exists", err)
    return check_pass("data directory exists", str(d))


def chk_charm_available() -> dict:
    """Check charm binary is on PATH.  Used in: test step 01."""
    path = shutil.which("charm")
    if path:
        return check_pass("charm binary in PATH", path)
    return check_warn(
        "charm binary in PATH",
        "charm not found — ensure SimNIBS is activated or provide full path",
    )


def chk_fslorient_available(cfg: dict) -> dict:
    """Check fslorient binary is accessible.  Used in: test step 01."""
    fsl_bin = cfg.get("fsl_bin", "")
    fslorient = Path(fsl_bin) / "fslorient"
    if fslorient.exists():
        return check_pass("fslorient available", str(fslorient))
    if shutil.which("fslorient"):
        return check_pass("fslorient available", shutil.which("fslorient"))
    return check_warn("fslorient available", f"not found at {fslorient} or in PATH")


def chk_sub_dir(data_dir: Path, sub_id_bare: str, sub_id_full: str | None = None) -> tuple[dict, Path | None]:
    """Check subject directory exists.  Used in: test step 01.

    Supports both bare (``M3827/``) and BIDS-style (``sub-M3827/``) directories.
    """
    if sub_id_full is None:
        sub_id_full = f"sub-{sub_id_bare}"
    bare_dir = data_dir / sub_id_bare
    full_dir = data_dir / sub_id_full
    if bare_dir.exists():
        return check_pass("subject directory", str(bare_dir)), bare_dir
    if full_dir.exists():
        return check_pass("subject directory (BIDS)", str(full_dir)), full_dir
    return check_fail("subject directory", f"not found: {bare_dir} or {full_dir}"), None


def chk_t1_exists(sub_dir: Path, sub_id_bare: str) -> tuple[dict, Path | None]:
    """Check T1w file exists.  Used in: test step 01.

    Mirrors ``find_t1``: tries strict BIDS name first, then loose glob
    (e.g. ``sub-{id}_T1w_7T.nii``).
    """
    stem = f"sub-{sub_id_bare}_T1w"
    # 1. Strict BIDS match
    for suffix in (".nii.gz", ".nii"):
        candidate = sub_dir / (stem + suffix)
        if candidate.exists():
            return check_pass("T1w file", str(candidate)), candidate
    # 2. Loose glob fallback
    for pattern in (f"{stem}*.nii.gz", f"{stem}*.nii"):
        matches = sorted(sub_dir.glob(pattern))
        if matches:
            return check_pass("T1w file", str(matches[0])), matches[0]
    return check_fail("T1w file", f"not found: {sub_dir / stem}.nii[.gz] or {stem}_*.nii[.gz]"), None


def chk_charm_output(sub_dir: Path, sub_id_full: str) -> list[dict]:
    """Check charm output files exist and report sizes.  Used in: test step 01."""
    m2m_dir = sub_dir / f"m2m_{sub_id_full}"
    if not m2m_dir.exists():
        return [check_fail("m2m directory", str(m2m_dir))]
    results = [check_pass("m2m directory", str(m2m_dir))]
    for fname in CHARM_OUTPUTS:
        p = m2m_dir / fname
        if p.exists():
            size_mb = p.stat().st_size / 1e6
            results.append(check_pass(f"  {fname}", f"{size_mb:.1f} MB"))
        else:
            results.append(check_fail(f"  {fname}", "not found"))
    return results


def run_environment_checks(yaml_path: str, cfg: dict | None) -> list[dict]:
    """Run all environment-level checks.  Used in: test step 01."""
    checks = [chk_yaml_loadable(yaml_path)]
    if cfg is None:
        return checks
    checks.append(chk_required_keys(cfg))
    checks.append(chk_data_dir(cfg))
    checks.append(chk_charm_available())
    checks.append(chk_fslorient_available(cfg))
    return checks


def run_subject_checks(
    sub_id: str, data_dir: Path, check_output: bool
) -> list[dict]:
    """Run all per-subject checks.  Used in: test step 01."""
    sub_id_full, sub_id_bare = normalise_sub_id(sub_id)
    checks = []
    sub_dir_chk, sub_dir = chk_sub_dir(data_dir, sub_id_bare)
    checks.append(sub_dir_chk)
    if sub_dir is None:
        return checks
    t1_chk, _ = chk_t1_exists(sub_dir, sub_id_bare)
    checks.append(t1_chk)
    if check_output:
        checks.extend(chk_charm_output(sub_dir, sub_id_full))
    return checks


def print_checks(checks: list[dict], indent: int = 2) -> int:
    """Print check results; return number of FAILs.  Used in: test step 01."""
    pad = " " * indent
    n_fail = 0
    for c in checks:
        sym = SYMBOLS[c["status"]]
        detail = f"  →  {c['detail']}" if c["detail"] else ""
        print(f"{pad}[{sym}] {c['label']}{detail}")
        if c["status"] == "FAIL":
            n_fail += 1
    return n_fail


# ===========================================================================
# Step 04 — PlanTUS target planning
# ===========================================================================

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


def find_plantus_target_folder(
    m2m_dir: Path,
    sub_id_full: str,
    target_name: str,
    target_side: str,
) -> Path:
    """Return the PlanTUS output folder for a given target.

    Used in: step 04.

    Convention::

        {m2m_dir}/PlanTUS/{sub_id_full}_T1w_{target_name}_mask_native{target_side}/

    Raises
    ------
    SystemExit
        If the folder does not exist.
    """
    folder = (
        m2m_dir / "PlanTUS"
        / f"{sub_id_full}_T1w_{target_name}_mask_native{target_side}"
    )
    if not folder.exists():
        sys.exit(f"ERROR: PlanTUS target folder not found: {folder}")
    return folder


def get_plantus_vtx_dir(target_folder: Path) -> tuple[Path, int]:
    """Return ``(vtx_dir, vtx_id)`` for the optimised vertex in a PlanTUS folder.

    Used in: step 04.

    Expects exactly one ``vtx*`` subdirectory inside *target_folder*.

    Raises
    ------
    SystemExit
        If the number of vtx directories is not exactly one.
    """
    vtx_dirs = list(target_folder.glob("vtx*"))
    if len(vtx_dirs) != 1:
        sys.exit(
            f"ERROR: expected exactly one vtx directory in {target_folder}, "
            f"found {len(vtx_dirs)}"
        )
    vtx_dir = vtx_dirs[0]
    vtx_id = int(vtx_dir.name.replace("vtx", ""))
    return vtx_dir, vtx_id


def select_best_vtx(
    target_folder: Path,
    max_angle: float,
    max_distance: float | None = None,
    min_distance: float | None = None,
    top_pct: float = 0.9,
) -> tuple[int, dict, int]:
    """Select the best scalp vertex for TUS placement from PlanTUS metric maps.

    Selects the best scalp vertex using a two-stage approach:

    1. **Filter** unsafe vertices (avoidance mask + optional distance bounds).
    2. **Top candidates**: keep only vertices whose intersection is at least
       ``top_pct`` × the maximum intersection among safe vertices.
    3. **Tiebreak** within top candidates: minimise a normalised sum of
       angle and distance to prefer lower-angle, closer placements when
       intersection is nearly equal.

    Angle is **advisory only** after selection: a warning is issued if the
    chosen vertex exceeds ``max_angle``, but the choice stands.

    Hard constraints (NEVER relaxed):
    - Avoidance mask > 0 (anatomical safety)
    - Thresholded distance > 0 (PlanTUS feasibility)
    - dist_raw >= min_distance, if specified (focal-depth lower limit)
    - dist_raw <= max_distance, if specified (focal-depth upper limit)

    After selecting the best vertex, writes ``best_vtx_marker_skin.func.gii``
    to *target_folder* so it can be loaded as an overlay in wb_view.

    Used in: step 04, run_pipeline.

    Parameters
    ----------
    target_folder:
        Path to the PlanTUS output directory (contains ``*.func.gii``).
    max_angle:
        Advisory maximum incidence angle in degrees (``tp["max_angle"]``).
        A warning is raised if the best vertex exceeds this value.
    max_distance:
        Maximum skin-to-ROI distance in mm (``tp["max_distance"]``).
        If ``None``, no upper distance bound is applied.
    min_distance:
        Minimum skin-to-ROI distance in mm (``tp["min_distance"]``).
        If ``None``, no lower distance bound is applied.
    top_pct:
        Fraction of the maximum intersection used to define the top-candidate
        pool (default 0.9).  E.g. 0.9 keeps all vertices with intersection
        >= 90 % of the best.  Lower values broaden the pool, giving more
        weight to angle/distance.

    Returns
    -------
    best_vtx : int
        Vertex index of the selected scalp vertex.
    metrics : dict
        Keys: ``vtx_idx``, ``n_valid``, ``distance_mm``, ``angle_deg``,
        ``intersection_mm``, ``angle_exceeded``, ``max_angle_deg``.
    angle_exceeded : int
        0 = angle within nominal limit; 1 = angle advisory triggered.

    Raises
    ------
    ValueError
        If no vertices survive hard safety constraints (avoidance + distance).
    FileNotFoundError
        If any required GIFTI metric file is missing.
    """
    import warnings
    import numpy as np
    import nibabel as nib

    required = {
        "dist_thr": target_folder / "distances_skin_thresholded.func.gii",
        "angle":    target_folder / "angles_skin.func.gii",
        "avoid":    target_folder / "avoidance_skin.func.gii",
        "inter":    target_folder / "target_intersection_skin.func.gii",
        "dist_raw": target_folder / "skin_target_distances.npy",
    }
    missing = [str(p) for p in required.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing PlanTUS metric files (run prepare_plantus_scene first):\n"
            + "\n".join(f"  {m}" for m in missing)
        )

    dist_thr = nib.load(required["dist_thr"]).darrays[0].data
    angle    = nib.load(required["angle"]).darrays[0].data
    avoid    = nib.load(required["avoid"]).darrays[0].data
    inter    = nib.load(required["inter"]).darrays[0].data
    dist_raw = np.load(required["dist_raw"])

    # -- Hard safety constraints (NEVER relaxed) --------------------------
    # avoidance mask : anatomical safety (eyes, ears, superficial vessels)
    # distance bounds: transducer physical focal-depth limits (skipped if None)
    safe = (avoid > 0) & (dist_thr > 0)
    if min_distance is not None:
        safe = safe & (dist_raw >= min_distance)
    if max_distance is not None:
        safe = safe & (dist_raw <= max_distance)
    if not safe.any():
        _dist_note = (
            f"   - No vertex within distance [{min_distance}, {max_distance}] mm of target.\n"
            if (min_distance is not None or max_distance is not None) else ""
        )
        raise ValueError(
            f"No vertices satisfy hard safety constraints in {target_folder.name}.\n"
            "  Possible causes:\n"
            "    - Avoidance mask excludes all scalp vertices.\n"
            + _dist_note
            + "  Check target mask, transducer YAML distance settings, and avoidance mask."
        )

    # -- Two-stage vertex selection --------------------------------------
    # Stage 1: pool = safe vertices with intersection >= top_pct * max_inter
    inter_safe_max = inter[safe].max()
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
    def _norm(arr: "np.ndarray", mask: "np.ndarray") -> "np.ndarray":
        vals = arr[mask]
        lo, hi = vals.min(), vals.max()
        if hi == lo:
            return np.zeros_like(arr, dtype=float)
        out = np.full_like(arr, np.inf, dtype=float)
        out[mask] = (arr[mask] - lo) / (hi - lo)
        return out

    angle_norm = _norm(angle, top_candidates)
    dist_norm  = _norm(dist_raw, top_candidates)
    tiebreak   = np.where(top_candidates, -(angle_norm + dist_norm), -np.inf)
    best_vtx   = int(np.argmax(tiebreak))

    angle_exceeded = bool(angle[best_vtx] > max_angle)
    if angle_exceeded:
        msg = (
            f"[select_best_vtx] Best vertex angle {angle[best_vtx]:.1f}° "
            f"exceeds nominal limit ({max_angle}°).\n"
            "  No vertex with higher intersection satisfies the angle limit.\n"
            "  Avoidance mask and distance constraints were preserved."
        )
        warnings.warn(msg, stacklevel=2)
        print(f"[WARNING] {msg}")

    relax_level     = 1 if angle_exceeded else 0  # 1 = angle advisory triggered
    effective_angle = float(angle[best_vtx])

    # -- Write marker GIFTI -----------------------------------------------
    # Clone an existing PlanTUS .func.gii and replace data only.
    # This guarantees the same XML structure / metadata that wb_view expects,
    # avoiding the "Invalid structure" dialog caused by nibabel-generated files.
    # Mark all vertices within 3 mm of best_vtx so the spot is visible in wb_view.
    # Use value 100.0 so it stands out clearly at the top of any colormap scale.
    marker = np.zeros(len(dist_raw), dtype=np.float32)
    _surf_path = target_folder / "skin.surf.gii"
    if _surf_path.exists():
        _coords = nib.load(_surf_path).darrays[0].data  # shape (N, 3)
        _dists  = np.linalg.norm(_coords - _coords[best_vtx], axis=1)
        marker[_dists <= 3.0] = 100.0
    else:
        marker[best_vtx] = 100.0  # fallback: single vertex
    _template = nib.load(required["inter"])  # target_intersection_skin.func.gii
    _out = nib.gifti.GiftiImage(
        meta=_template.meta,
        darrays=[
            nib.gifti.GiftiDataArray(
                data=marker,
                intent=_template.darrays[0].intent,
                datatype="NIFTI_TYPE_FLOAT32",
                meta=_template.darrays[0].meta,
            )
        ],
    )
    _out.to_filename(str(target_folder / "best_vtx_marker_skin.func.gii"))

    return best_vtx, {
        "vtx_idx":           best_vtx,
        "n_valid":           int(safe.sum()),
        "n_top_candidates":  int(top_candidates.sum()),
        "distance_mm":       float(dist_raw[best_vtx]),
        "angle_deg":         float(angle[best_vtx]),
        "intersection_mm":   float(inter[best_vtx]),
        "max_inter_mm":      float(inter_safe_max),
        "top_pct":           float(top_pct),
        "angle_exceeded":    angle_exceeded,
        "max_angle_deg":     float(max_angle),
    }, relax_level


def report_depth_and_gel(
    vertex_idx: int,
    skin_target_distances: "np.ndarray",
    plane_offset: float,
    additional_offset: float,
    output_path: str | Path,
    target_roi_name: str,
    subject_id: str,
) -> None:
    """Print and save a depth / required gel thickness report for a selected vertex.

    Used in: step 04.

    Reports two quantities:
    - ``gel_needed_mm_abs``       total pad thickness needed (exit plane → focus = fd)
    - ``gel_delta_from_assumed``  delta from the currently assumed additional_offset
    """
    import numpy as np

    dist_skin_roi    = float(skin_target_distances[vertex_idx])
    exit_to_roi      = dist_skin_roi + additional_offset
    fd               = round(exit_to_roi, 1)
    gel_needed_abs   = fd - dist_skin_roi
    gel_delta        = gel_needed_abs - additional_offset

    lines = [
        "===== PlanTUS depth report =====",
        f"Subject                                       : {subject_id}",
        f"Target ROI                                    : {target_roi_name}",
        f"Vertex index                                  : {vertex_idx}",
        f"skin → ROI distance (mm)                     : {dist_skin_roi:.4f}",
        f"plane_offset_mm (radiator → exit plane)      : {plane_offset:.4f}",
        f"assumed additional_offset_mm (exit pl. → skin): {additional_offset:.4f}",
        f"exit plane → ROI (mm)                        : {exit_to_roi:.4f}",
        f"focal_distance_fd_mm                         : {fd:.4f}",
        f"gel_needed_mm_abs (total pad thickness)      : {gel_needed_abs:.4f}",
        f"gel_delta_from_assumed_mm                    : {gel_delta:.4f}",
        "================================",
    ]
    for l in lines:
        print(l)

    out_txt = (
        Path(output_path)
        / f"{target_roi_name}_PlanTUS_depth_report_vtx{vertex_idx:05d}.txt"
    )
    with open(out_txt, "w") as f:
        f.write("# gel_needed_mm_abs        : total pad thickness required (abs)\n")
        f.write("# gel_delta_from_assumed_mm: adjustment relative to assumed pad\n\n")
        f.write(f"subject_id: {subject_id}\n")
        f.write(f"ROI: {target_roi_name}\n")
        f.write(f"vertex_index: {vertex_idx}\n")
        f.write(f"skin_to_ROI_distance_mm: {dist_skin_roi:.4f}\n")
        f.write(f"plane_offset_mm: {plane_offset:.4f}\n")
        f.write(f"additional_offset_mm_assumed: {additional_offset:.4f}\n")
        f.write(f"exit_plane_to_ROI_distance_mm: {exit_to_roi:.4f}\n")
        f.write(f"focal_distance_fd_mm: {fd:.4f}\n")
        f.write(f"gel_needed_mm_abs: {gel_needed_abs:.4f}\n")
        f.write(f"gel_delta_from_assumed_mm: {gel_delta:.4f}\n")
    print("Depth report saved:", out_txt)


def prepare_plantus_scene(
    sub_id_full: str,
    sub_id_bare: str,
    m2m_dir: Path,
    target_name: str,
    target_side: str,
    tp: dict,
    dry_run: bool = False,
) -> Path:
    """Prepare PlanTUS surfaces, metric maps, and Workbench scene file.

    Outputs are written to ``m2m_dir/PlanTUS/<target_roi_name>/``.
    Also saves ``skin_target_distances.npy`` to the output directory for
    later use by :func:`run_plantus_placement`.

    Used in: step 04a, step 04 (notebook).

    Parameters
    ----------
    sub_id_full:
        Full subject ID, e.g. ``"sub-NS"``.
    sub_id_bare:
        Bare subject ID, e.g. ``"NS"``.
    m2m_dir:
        Path to ``m2m_{sub_id_full}/`` directory.
    target_name:
        PlanTUS target label, e.g. ``"aMCC_NeuroSynthTopic112"``.
    target_side:
        Side suffix: ``"_R"``, ``"_L"``, or ``""``.
    tp:
        Transducer parameter dict from :func:`transducer_params`.
    dry_run:
        If True, validate paths and print without running.

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
    mask_pattern = f"*_{target_name}_mask_native{target_side}.nii.gz"
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

    print("Converting SimNIBS mesh to surface files…")
    PlanTUS.convert_simnibs_mesh_to_surface(str(simnibs_mesh), [1005], "skin", str(output_path))
    PlanTUS.add_structure_information(str(output_path) + "/skin.surf.gii", "CORTEX_LEFT")
    PlanTUS.convert_simnibs_mesh_to_surface(str(simnibs_mesh), [1007, 1008], "skull", str(output_path))
    PlanTUS.add_structure_information(str(output_path) + "/skull.surf.gii", "CORTEX_RIGHT")

    PlanTUS.create_avoidance_mask(str(simnibs_mesh), str(output_path) + "/skin.surf.gii", diam / 2)

    target_center        = PlanTUS.roi_center_of_gravity(target_roi_filepath)
    skin_target_distances = PlanTUS.distance_between_surface_and_point(
        str(output_path) + "/skin.surf.gii", target_center
    )
    PlanTUS.create_metric_from_pseudo_nifti("distances", skin_target_distances, str(output_path) + "/skin.surf.gii")
    PlanTUS.mask_metric(str(output_path) + "/distances_skin.func.gii", str(output_path) + "/avoidance_skin.func.gii")
    PlanTUS.add_structure_information(str(output_path) + "/distances_skin.func.gii", "CORTEX_LEFT")
    PlanTUS.threshold_metric(str(output_path) + "/distances_skin.func.gii", max_d)
    PlanTUS.mask_metric(str(output_path) + "/distances_skin_thresholded.func.gii", str(output_path) + "/avoidance_skin.func.gii")
    PlanTUS.add_structure_information(str(output_path) + "/distances_skin_thresholded.func.gii", "CORTEX_LEFT")

    _, skin_normals = PlanTUS.compute_surface_metrics(str(output_path) + "/skin.surf.gii")
    skin_target_vectors = PlanTUS.vectors_between_surface_and_point(str(output_path) + "/skin.surf.gii", target_center)
    skin_target_angles = np.abs(np.array([
        math.degrees(PlanTUS.angle_between_vectors(skin_target_vectors[i], skin_normals[i]))
        for i in np.arange(len(skin_target_vectors))
    ]))
    PlanTUS.create_metric_from_pseudo_nifti("angles", skin_target_angles, str(output_path) + "/skin.surf.gii")
    PlanTUS.mask_metric(str(output_path) + "/angles_skin.func.gii", str(output_path) + "/avoidance_skin.func.gii")
    PlanTUS.add_structure_information(str(output_path) + "/angles_skin.func.gii", "CORTEX_LEFT")

    PlanTUS.stl_from_nii(target_roi_filepath, 0.25)
    skin_coordinates, skin_normals = PlanTUS.compute_surface_metrics(str(output_path) + "/skin.surf.gii")
    skin_target_intersections = PlanTUS.compute_vector_mesh_intersections(
        skin_coordinates, skin_normals,
        str(output_path) + "/" + target_roi_name + "_3Dmodel.stl", 200
    )
    skin_target_intersection_values = []
    for ints in skin_target_intersections:
        n = len(ints)
        if n == 2:
            skin_target_intersection_values.append(
                np.linalg.norm(np.asarray(ints[1]) - np.asarray(ints[0]))
            )
        elif n == 4:
            skin_target_intersection_values.append(
                np.linalg.norm(np.asarray(ints[1]) - np.asarray(ints[0]))
                + np.linalg.norm(np.asarray(ints[3]) - np.asarray(ints[2]))
            )
        elif n > 4:
            skin_target_intersection_values.append(np.nan)
        else:
            skin_target_intersection_values.append(0)
    skin_target_intersection_values = np.asarray(skin_target_intersection_values)
    PlanTUS.create_metric_from_pseudo_nifti("target_intersection", skin_target_intersection_values, str(output_path) + "/skin.surf.gii")
    PlanTUS.mask_metric(str(output_path) + "/target_intersection_skin.func.gii", str(output_path) + "/avoidance_skin.func.gii")
    PlanTUS.add_structure_information(str(output_path) + "/target_intersection_skin.func.gii", "CORTEX_LEFT")

    skin_coordinates, skin_normals = PlanTUS.compute_surface_metrics(str(output_path) + "/skin.surf.gii")
    skull_coordinates, skull_normals = PlanTUS.compute_surface_metrics(str(output_path) + "/skull.surf.gii")
    skin_skull_intersections = PlanTUS.compute_vector_mesh_intersections(
        skin_coordinates, skin_normals, str(output_path) + "/skull.stl", 40
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
    PlanTUS.create_metric_from_pseudo_nifti("skin_skull_angles", np.asarray(skin_skull_angle_list), str(output_path) + "/skin.surf.gii")
    PlanTUS.mask_metric(str(output_path) + "/skin_skull_angles_skin.func.gii", str(output_path) + "/avoidance_skin.func.gii")
    PlanTUS.add_structure_information(str(output_path) + "/skin_skull_angles_skin.func.gii", "CORTEX_LEFT")

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
    PlanTUS.create_scene(scene_tpl, str(output_path) + "/scene.scene", scene_variable_names, scene_variable_values)
    print("Scene created:", str(output_path) + "/scene.scene")
    print("Open in Workbench: wb_view", str(output_path) + "/scene.scene")

    # Save distances array so step04b / run_plantus_placement can load it
    np.save(str(output_path / "skin_target_distances.npy"), skin_target_distances)
    print("Distances saved →", str(output_path / "skin_target_distances.npy"))

    os.chdir(_saved_cwd)
    return output_path


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
    """Run acoustic simulation placement for a single selected vertex.

    Loads ``skin_target_distances.npy`` from the PlanTUS output directory
    previously written by :func:`prepare_plantus_scene`.

    Used in: step 04b, step 04 (notebook).

    Parameters
    ----------
    vertex_idx:
        Vertex index selected in Workbench (from wb_view log output).
    sub_id_full:
        Full subject ID, e.g. ``"sub-NS"``.
    sub_id_bare:
        Bare subject ID, e.g. ``"NS"``.
    m2m_dir:
        Path to ``m2m_{sub_id_full}/`` directory.
    target_name:
        PlanTUS target label.
    target_side:
        Side suffix: ``"_R"``, ``"_L"``, or ``""``.
    tp:
        Transducer parameter dict from :func:`transducer_params`.
    additional_offset:
        Extra gel/pad thickness between exit plane and skin (mm).
    dry_run:
        If True, validate paths and print without running.
    """
    import numpy as np

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

    skin_target_distances = np.load(distances_file)

    report_depth_and_gel(
        vertex_idx=vertex_idx,
        skin_target_distances=skin_target_distances,
        plane_offset=tp["plane_offset"],
        additional_offset=additional_offset,
        output_path=output_path,
        target_roi_name=target_roi_name,
        subject_id=sub_id_full,
    )

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
) -> None:
    """Run the full PlanTUS planning workflow (GUI) for one subject/target.

    Calls :func:`prepare_plantus_scene` to generate surfaces and scene, then
    launches ``wb_view`` to capture vertex selection interactively. For each
    confirmed vertex calls :func:`run_plantus_placement`.

    Two modes are available via ``use_pynput``:

    * ``True`` (default) — a ``pynput`` mouse listener gates each prompt: only
      the vertex logged *after* a mouse click triggers ``yes/no``.  Requires
      macOS Accessibility permissions for the host process (System Settings →
      Privacy & Security → Accessibility).  If ``pynput`` cannot be imported,
      the function falls back automatically to direct-parsing mode.
    * ``False`` — wb_view's FINER stderr log is parsed directly; every logged
      vertex triggers ``yes/no`` without needing Accessibility permissions.
      Use this when running inside a Jupyter kernel that has not been granted
      Accessibility access.

    Used in: step 04 (notebook).

    Parameters
    ----------
    sub_id_full:
        Full subject ID, e.g. ``"sub-NS"``.
    sub_id_bare:
        Bare subject ID, e.g. ``"NS"``.
    m2m_dir:
        Path to ``m2m_{sub_id_full}/`` directory.
    target_name:
        PlanTUS target label, e.g. ``"aMCC_NeuroSynthTopic112"``.
    target_side:
        Side suffix: ``"_R"``, ``"_L"``, or ``""``.
    tp:
        Transducer parameter dict from :func:`transducer_params`.
    additional_offset:
        Extra gel/pad thickness between exit plane and skin (mm).
    dry_run:
        If True, validate paths and print without running.
    use_pynput:
        If True, use a pynput mouse listener to gate prompts (default).
        Set False when Accessibility permissions are not available.
    """
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
        )
        _angle_note = (
            f"  ⚠️  Angle {_vtx_m['angle_deg']:.1f}° exceeds nominal limit "
            f"({_vtx_m['max_angle_deg']:.1f}°) — verify placement\n"
        ) if _vtx_m["angle_exceeded"] else ""
        print(
            f"\n[auto vtx] Suggested best vertex: {_best_vtx}\n"
            f"  Valid vertices  : {_vtx_m['n_valid']} safe  |  "
            f"{_vtx_m['n_top_candidates']} top candidates "
            f"(>= {_vtx_m['top_pct']*100:.0f}% of max {_vtx_m['max_inter_mm']:.1f} mm)\n"
            f"  Distance        : {_vtx_m['distance_mm']:.1f} mm\n"
            f"  Angle           : {_vtx_m['angle_deg']:.1f}° (limit: {_vtx_m['max_angle_deg']:.1f}°)\n"
            f"  Intersection    : {_vtx_m['intersection_mm']:.1f} mm\n"
            + _angle_note
            + "  Marker written  : best_vtx_marker_skin.func.gii\n"
            "                    (load as overlay in wb_view to highlight the point)\n"
            "[auto vtx] Launching wb_view — click a different vertex, "
            "or type the suggested index when prompted.\n"
        )
    except (ValueError, FileNotFoundError) as _e:
        print(f"[auto vtx] Could not compute best vertex: {_e}")
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

    if _pynput_ok:
        def on_click(x, y, button, pressed):
            nonlocal process_line
            if pressed:
                process_line = True
        listener = _mouse.Listener(on_click=on_click)
        listener.start()

    def read_output():
        nonlocal triangle_number, process_line
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
                resp = input(f"Generate placement for vertex {triangle_number}? (yes/no): ").strip().lower()
                if resp == "yes":
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
    """Load entry and target coordinates from a PlanTUS vtx directory.

    Used in: step 04, step 04 (notebook).

    Parameters
    ----------
    vtx_dir:
        ``vtx{NNNNN}/`` subdirectory inside the PlanTUS output folder.
    target_folder:
        PlanTUS output folder (contains ``skin.surf.gii``).
    vtx_id:
        Vertex index (integer part of the vtx directory name).

    Returns
    -------
    entry_ras:
        Entry point (skin surface vertex) in **RAS / NIfTI:Scanner** space,
        shape (3,).  Taken directly from the ``skin.surf.gii`` GIFTI vertex
        array.  SimNIBS writes GIFTI surface files in RAS convention; no
        coordinate-system conversion is applied here.
    target_ras:
        Acoustic focus in **RAS / NIfTI:Scanner** space, shape (3,).  Taken
        from the translation column of ``focus_position_matrix_*.txt``, which
        SimNIBS also writes in RAS convention.  Unlike ANTs (which uses LPS),
        SimNIBS outputs do not require an LPS→RAS flip.
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
    coordinate_system: str = "NIfTI:Scanner",
    append: bool = False,
) -> None:
    """Write (or append) a BrainSight-compatible target file from PlanTUS outputs.

    Used in: step 04.

    Parameters
    ----------
    transducer_mat_path:
        Path to a 4×4 transducer matrix (.txt) in Scanner/RAS space
        (PlanTUS ``*_transducer.txt``). Only the rotation block is used.
    entry_las:
        Entry point (skin surface) in **RAS / NIfTI:Scanner** space (mm),
        shape (3,).  The ``_las`` suffix is a historical naming artefact;
        this value must be in RAS.  Pass the ``entry_ras`` output of
        ``get_vtx_coordinates()``, which returns RAS coordinates directly
        from SimNIBS without any coordinate-system conversion.
    target_las:
        Acoustic focus in **RAS / NIfTI:Scanner** space (mm), shape (3,).
        Same convention as *entry_las* — must be RAS.  Pass
        ``target_ras`` from ``get_vtx_coordinates()``.
    out_path:
        Output .txt file path (BrainSight import format).
    name:
        Label prefix used for the BrainSight file rows.
    coordinate_system:
        String written to the BrainSight header (default ``"NIfTI:Scanner"``).
    append:
        If False (default), create a new file with header + rows.
        If True, append only data rows to an existing file (no header written).
    """
    import numpy as np

    M = np.loadtxt(transducer_mat_path)
    if M.shape != (4, 4):
        raise ValueError(f"Expected 4×4 matrix, got {M.shape}")

    R = M[:3, :3].copy()
    R[:, 2] /= np.linalg.norm(R[:, 2])

    entry_las  = np.asarray(entry_las, float)
    target_las = np.asarray(target_las, float)

    header = (
        "# Version: 13\n"
        f"# Coordinate system: {coordinate_system}\n"
        "# Created by: write_brainsight_txt (LabWiki scripts/TUS/src/utils.py)\n"
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
    coordinate_system: str = "NIfTI:Scanner",
) -> Path:
    """Locate the PlanTUS vtx folder, extract coordinates, and write BrainSight file.

    Convenience wrapper that combines :func:`find_plantus_target_folder`,
    :func:`get_plantus_vtx_dir`, :func:`get_vtx_coordinates`, and
    :func:`write_brainsight_txt`.

    Used in: step 04 (notebook).

    Parameters
    ----------
    m2m_dir:
        Path to ``m2m_{sub_id_full}/`` directory.
    sub_id_full:
        Full subject ID, e.g. ``"sub-NS"``.
    target_name:
        PlanTUS target label.
    target_side:
        Side suffix: ``"_R"``, ``"_L"``, or ``""``.
    coordinate_system:
        String written to the BrainSight header.

    Returns
    -------
    Path
        Path to the written BrainSight .txt file.
    """
    target_folder = find_plantus_target_folder(m2m_dir, sub_id_full, target_name, target_side)

    vtx_dirs = sorted(target_folder.glob("vtx*"), key=lambda p: p.stat().st_mtime)
    if not vtx_dirs:
        sys.exit(f"ERROR: no vtx directory found in {target_folder}")
    if len(vtx_dirs) > 1:
        print(
            f"WARNING: {len(vtx_dirs)} vtx directories found — "
            f"using the most recently modified: {vtx_dirs[-1].name}"
        )
    vtx_dir = vtx_dirs[-1]
    vtx_id  = int(vtx_dir.name.replace("vtx", ""))

    entry_ras, target_ras = get_vtx_coordinates(vtx_dir, target_folder, vtx_id)
    trans_mat_path       = next(vtx_dir.glob("*_transducer.txt"))

    label    = f"{sub_id_full}_T1w_{target_name}{target_side}"
    out_path = target_folder / f"{label}_target_coordinates_Brainsight_PlanTUS.txt"

    write_brainsight_txt(
        transducer_mat_path=trans_mat_path,
        entry_las=entry_ras,
        target_las=target_ras,
        out_path=out_path,
        name=label,
        coordinate_system=coordinate_system,
    )
    return out_path


# =============================================================================
# Step 05 helpers — inverse registration (MNI → native)
# =============================================================================

def ants_to_nib(ants_img: "ants.ANTsImage") -> "nib.Nifti1Image":
    """Convert an ANTs image to a :class:`nibabel.Nifti1Image`.

    This preserves origin, spacing, and direction exactly as stored in the
    ANTs object.  Useful for passing images to nilearn/nibabel functions after
    ANTs registration.

    Used in: step 05.

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

    return _nib.Nifti1Image(ants_img.numpy(), affine=affine)


def register_mni_to_native(
    t1_native_path: str | Path,
    t1_mni_path: str | Path,
    output_dir: str | Path,
    sub_id: str,
    type_of_transform: str = "SyN",
) -> tuple["ants.ANTsImage", "ants.ANTsImage", dict]:
    """Register MNI152 T1 template to subject-native T1 using ANTs.

    In ANTs terminology *fwdtransforms* maps moving → fixed, so the
    "forward" transform maps MNI → native.  Both an initial Affine step and
    the requested nonlinear step are run in sequence when *type_of_transform*
    is ``"SyN"`` or ``"SyNCC"``; for ``"Affine"`` only one step is used.

    Used in: step 05.

    Parameters
    ----------
    t1_native_path:
        Path to the subject-native T1 NIfTI.
    t1_mni_path:
        Path to the MNI152 T1 template (e.g. from templateflow).
    output_dir:
        Directory where ANTs transform files are saved.
    sub_id:
        Subject identifier used as filename prefix (e.g. ``"sub-SK"``).
    type_of_transform:
        ANTs registration type: ``"Affine"``, ``"SyN"``, or ``"SyNCC"``.
        When ``"SyN"`` or ``"SyNCC"``, an affine pre-registration is run
        automatically as initialisation.

    Returns
    -------
    t1_native_ras : ants.ANTsImage
        Subject T1 reoriented to RAS (used as registration fixed image).
    t1_mni_hm : ants.ANTsImage
        MNI template after histogram normalisation (moving image).
    reg : dict
        ANTs registration output dict, including ``fwdtransforms`` which
        are later passed directly to :func:`apply_inverse_transform`.
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
    # and amygdala (3T) masks (see z_old_scripts/TUS_aMCCmask.ipynb,
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
    """Warp a mask from MNI space into subject-native space.

    Applies the forward transforms from :func:`register_mni_to_native` (which
    map MNI → native) and optionally confines the result to the brain mask.
    The output is resampled back to the original (non-RAS) native T1 grid and
    saved.

    Used in: step 05, step3_inverse_registration.

    Parameters
    ----------
    mask_mni_path:
        NIfTI mask in MNI space to be warped.
    reg:
        Registration dict from :func:`register_mni_to_native`, or ``None``
        when *transform_list_override* is provided (e.g. fmriprep mode).
    t1_native_ras:
        Native T1 in RAS (the fixed image used during registration).
    t1_native_orig:
        Original (un-reoriented) native T1; output is resampled to this grid.
    output_path:
        Where to write the native-space mask NIfTI.
    interpolator:
        ANTs interpolation: ``"nearestNeighbor"``, ``"linear"``,
        ``"gaussian"``, or ``"bspline"``.
    mask_brain:
        If ``True``, restrict the warped mask to the brain (``ants.get_mask``).
    transform_list_override:
        When provided, use this transform list directly instead of
        ``reg["fwdtransforms"]``.  Use this for fmriprep mode where
        *reg* is ``None`` and the warp is a pre-computed ``.h5`` file.

    Returns
    -------
    ants.ANTsImage
        Native-space mask resampled to the original T1 grid.
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
    """Compute the centre of mass of a mask in native-space millimetres.

    Used in: step 05, step 04 (CoM mode).

    Parameters
    ----------
    mask_native:
        Binary or probabilistic mask in native space.  May be an ANTs image
        or a path to a NIfTI file.
    z_threshold:
        Voxels with value ≤ *z_threshold* are excluded before computing CoM.
        Use ``0.0`` for binary masks.

    Returns
    -------
    com_mm : np.ndarray, shape (3,)
        Centre-of-mass in **RAS / NIfTI:Scanner** space (mm), (x, y, z) order,
        ready for import into BrainSight.

        ANTs/ITK stores image metadata (``origin``, ``direction``) in LPS
        convention (x = Left+, y = Posterior+).  The raw voxel→mm result
        from ``apply_affine`` is therefore in LPS.  This function converts
        to RAS by multiplying the x and y components by −1 before returning,
        matching the ``NIfTI:Scanner`` coordinate system expected by BrainSight.
    com_vox : tuple of float
        Voxel-space CoM indices (i, j, k).
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
    """Return the peak voxel of a functional map within a native-space mask.

    Used in: step3_inverse_registration.ipynb (TARGET_MODE = 'peak_func').

    Parameters
    ----------
    func_native:
        Functional contrast map in native space (e.g. warped fMRI stat map).
        Must be on the same voxel grid as *mask_native*.
        May be an ANTs image or a path to a NIfTI file.
    mask_native:
        Binary or probabilistic mask in native space.  May be an ANTs image
        or a path to a NIfTI file.
    z_threshold:
        Voxels in *mask_native* with value ≤ *z_threshold* are excluded from
        the peak search.  Use ``0.0`` for binary masks.

    Returns
    -------
    peak_mm : np.ndarray, shape (3,)
        Peak-voxel coordinates in **RAS / NIfTI:Scanner** space (mm),
        (x, y, z) order, ready for import into BrainSight.

        ANTs/ITK stores image metadata (``origin``, ``direction``) in LPS
        convention (x = Left+, y = Posterior+).  The raw voxel→mm result
        from ``apply_affine`` is therefore in LPS.  This function converts
        to RAS by multiplying the x and y components by −1 before returning,
        matching the ``NIfTI:Scanner`` coordinate system expected by BrainSight.
    peak_vox : tuple of int
        Voxel-space peak indices (i, j, k).
    peak_val : float
        Functional map value at the peak voxel.
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
    """Produce and save a tri-planar static overlay of a mask on the native T1.

    Creates a ``plot_stat_map`` figure (ortho mode) and writes it to
    *output_path* at 300 dpi.

    Used in: step 05.

    Parameters
    ----------
    mask_native:
        Native-space mask (ANTs image or path).
    t1_native:
        Native T1 (ANTs image or path), used as background.
    target_label:
        String used in the figure title.
    output_path:
        Where to save the PNG figure.
    cut_coords:
        ``(x, y, z)`` in mm for the three cut planes.  If ``None`` the
        centre-of-mass of the mask is used automatically.
    z_threshold:
        Display threshold applied to the mask overlay.
    cmap:
        Matplotlib colormap name forwarded to nilearn.

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
