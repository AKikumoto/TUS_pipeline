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
  list_plantus_vertices       Step 04/05 — summarise the placements available for a target.
  screenshot_wb_view          Step 04 — screenshot the live wb_view window on confirmation.
  capture_plantus_scene       Step 04 — render a placement scene to PNG (offscreen).
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

Step 05-BB — BabelBrain simulations (domain · acoustic · thermal · QC)
  patch_babelvisco_BB         Step 05-BB — on-disk fix: BabelViscoFDTD intparams dtype bug.
  read_depth_report           Step 05-BB (5b) — parse PlanTUS depth report for skin-to-ROI distance.
  load_babelbrain_tx_yaml     Step 05-BB (5b) — load BabelBrain transducer default.yaml.
  compute_z_steering_BB       Step 05-BB (5b) — compute ZSteering from depth report + tx config.
  run_domain_BB               Step 05-BB (5a) — domain generation (CalculateMaskProcess).
  run_acoustic_BB             Step 05-BB (5b) — acoustic simulation (CalculateFieldProcess).
  run_thermal_BB              Step 05-BB (5c) — thermal simulation (CalculateThermalProcess).
  summarise_acoustic_BB       Step 05-BB (5b) — print acoustic h5 summary table.
  write_tpo_summary_BB        Step 05-BB (5c) — free-field ISPPA needed for the planned in-situ ISPPA.
  plot_acoustic_qc_BB         Step 05-BB (QC) — acoustic intensity QC figure.
  view_acoustic_interactive_BB Step 05-BB (QC) — interactive nilearn viewer on T1.
  save_acoustic_ortho_BB      Step 05-BB (QC) — save that view statically at chosen coords.
  plot_thermal_qc_BB          Step 05-BB (QC) — thermal ΔT + safety QC figure(s).
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


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------
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


def device_tag(tx_system: str, frequency_hz: float, ppw: int) -> str:
    """`DPX_500_500kHz_6PPW` — the acoustic settings.

    NOT renamed. BabelBrain rebuilds this suffix internally from field_target
    and loads the domain by the resulting path, so a tidier form here makes
    step 5b look for a file step 5a never wrote. The prefix up to the
    transducer is ours; everything after it belongs to BabelBrain.
    """
    return f"{tx_system}_{int(frequency_hz / 1e3)}kHz_{ppw}PPW"


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


def regenerate_best_vtx_marker(
    m2m_dir: Path,
    sub_id_full: str,
    target_name: str,
    target_side: str,
    tp: dict,
    top_pct: float = 0.8,
) -> tuple[int, dict]:
    """Re-run vertex selection and rewrite ``best_vtx_marker_skin.func.gii``.

    Useful when you want to update the wb_view marker overlay without
    running the full PlanTUS interactive session.  All metric GIFTI files
    produced by ``prepare_plantus_scene`` must already exist in the target
    folder.

    Used in: step 04.

    Parameters
    ----------
    m2m_dir:
        SimNIBS m2m directory for the subject.
    sub_id_full:
        Full subject identifier (e.g. ``"sub-NS"``).
    target_name:
        Target label (e.g. ``"aMCC_NeuroSynthTopic112"``).
    target_side:
        Side suffix: ``"_L"``, ``"_R"``, or ``""`` for bilateral.
    tp:
        Transducer parameter dict (from ``transducer_params()``).
    top_pct:
        Fraction of max intersection defining the top-candidate pool.

    Returns
    -------
    best_vtx : int
        Selected vertex index.
    metrics : dict
        Selection metrics (angle_deg, distance_mm, etc.).
    """
    target_folder = find_plantus_target_folder(
        m2m_dir, sub_id_full, target_name, target_side
    )
    best_vtx, metrics, _ = select_best_vtx(
        target_folder=target_folder,
        max_angle=tp.get("max_angle", 30.0),
        max_distance=tp.get("max_distance"),
        min_distance=tp.get("min_distance"),
        top_pct=top_pct,
    )
    print(f"  Marker rewritten → {target_folder / 'best_vtx_marker_skin.func.gii'}")
    print(f"  best_vtx={best_vtx}  angle={metrics['angle_deg']:.1f}°  dist={metrics['distance_mm']:.1f} mm")
    return best_vtx, metrics


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


def _fold_obliquity(a):
    """Fold a skin–skull angle into [0, 90] degrees.

    PlanTUS computes it as ``arccos(skin_normal · skull_normal)``
    (``PlanTUS/code/PlanTUS.py:352-357``), so the raw range is 0–180.  Above 90
    the two *surfaces* are still parallel — the nearest skull vertex's outward
    normal simply points the other way, which happens when the ray lands on the
    inner table of the skull shell (``skull.surf.gii`` is built from SimNIBS
    tags 1007+1008, a closed shell with both tables).

    Obliquity on bone is what the metric is for, so 179° and 1° mean the same
    thing.  Unfolded, such a vertex normalises as the *worst* possible
    incidence when it is in fact near-perfect: 178 of sub-z004's 4 628 safe
    vertices sit above 90°.

    Idempotent, so it is safe to apply both when writing the metric and when
    reading it back.

    Used by: :func:`run_plantus`, :func:`select_best_vtx`,
    :func:`list_plantus_vertices`.
    """
    import numpy as _np                                          # noqa: PLC0415

    return _np.minimum(a, 180.0 - _np.asarray(a, dtype=float))


def skull_path_mm(m2m_dir, coords, roi_cog, step_mm: float = 0.25):
    """Bone traversed by the straight line from each scalp vertex to the ROI.

    PlanTUS scores a placement entirely from the scalp surface — aim angle,
    distance, skin-skull angle, beam-ROI intersection — and never looks inside
    the skull. Nothing before the acoustic solve can tell a 4 mm vault from a
    41 mm skull base, so a vertex on the jaw scores as well as one on the
    parietal bone. Two EC placements were selected that way and delivered
    almost nothing to the target (in-brain intensity at target 0.002 and 0.021
    of peak, against 0.21-0.67 for the rest).

    Uses SimNIBS's own segmentation, so nothing new has to be computed: charm
    already writes final_tissues.nii.gz with label 7 = compact bone and
    8 = spongy bone.

    Returns compact, spongy and total thickness in mm, one entry per vertex.
    Vectorised over vertices; ~1 s for a 35 000-vertex scalp.

    Caveat worth keeping in mind when using the result: across our ten measured
    placements this separates the catastrophic paths (14 and 42 mm) from the
    rest, but does NOT rank the 4-10 mm band — the best and worst of those
    differ threefold in delivered intensity with no thickness difference. Treat
    it as a veto, not a score.
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

    Used in: step 04.

    Foci sit above the surface instead of being painted into it, which is why
    they are used here rather than more values in the metric layer.  Nothing can
    swallow them -- an earlier design drew the marks as rings of vertices and
    they vanished wherever candidates were dense -- they carry a *name* rather
    than a number, so wb_view's identify window says "ADOPTED vtx4799" instead
    of "-2", and they need no overlay slot, of which every tab has only three.

    Parameters
    ----------
    target_folder:
        PlanTUS target folder; ``skin.surf.gii`` in it is the projection target.
    coords:
        ``(n_vertices, 3)`` scalp coordinates.
    rows:
        ``(name, (r, g, b), vertex_index)`` per focus.  Colours are 0-255 and
        should avoid the metric palettes underneath: a red mark is invisible
        against the red end of the distance map.  White and magenta are used.
    filename:
        Output name inside *target_folder*.

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

    Selects the best scalp vertex using a two-stage approach:

    1. **Filter** unsafe vertices (avoidance mask + optional distance bounds).
    2. **Top candidates**: keep only vertices whose intersection is at least
       ``top_pct`` × the maximum intersection among safe vertices.
    3. **Tiebreak** within top candidates: minimise a weighted sum of the
       normalised aim angle, distance and **skin-skull angle**, to prefer
       placements that are on-axis, close, and meet bone squarely when
       intersection is nearly equal.

    The skin-skull angle used to be computed by PlanTUS and then ignored here.
    It is the term that tracks transmission: on sub-z002 the aim angle spanned
    only 2.6-3.8 deg across placements while the skin-skull angle spanned
    2.4-26.7 deg, and the measured derating followed the latter (0.0478 at
    3.8 deg vs 0.0413 at 26.7 deg).  Within a top-candidate pool the aim angle
    is often nearly constant -- for sub-z004 hippocampus the four pool members
    differ by 0.9 deg in aim and share an identical distance -- so without this
    term the ranking is decided by noise.

    Angle is **advisory only** after selection: a warning is issued if the
    chosen vertex exceeds ``max_angle``, but the choice stands.

    Hard constraints (NEVER relaxed):
    - Avoidance mask > 0 (anatomical safety)
    - Scalp vertex at or above the inferior extent of brain, so the transducer
      sits on the cranial vault rather than the face, jaw or neck
    - Bone traversed on the way to the ROI <= ``max_skull_mm``
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
        Hard maximum incidence angle in degrees (``tp["max_angle"]``).
        Vertices exceeding this angle are excluded from the safe set.
    max_distance:
        Maximum skin-to-ROI distance in mm (``tp["max_distance"]``).
        If ``None``, no upper distance bound is applied.
    min_distance:
        Minimum skin-to-ROI distance in mm (``tp["min_distance"]``).
        If ``None``, no lower distance bound is applied.
    top_pct:
        Fraction of the maximum intersection used to define the top-candidate
        pool (default 0.8).  E.g. 0.8 keeps all vertices with intersection
        >= 80 % of the best.  Lower values broaden the pool, giving more
        weight to the tiebreak terms.
    weights:
        Relative weights ``(aim_angle, distance, skin_skull_angle)`` in the
        tiebreak, applied to each term after normalising it to [0, 1] over the
        pool.  Equal by default.  Raise the third if transmission matters more
        than reaching the exact centre of the ROI.
    mark_radius_mm:
        Radius of the blob written into ``best_vtx_marker_skin.func.gii`` around
        the chosen vertex.  Scalp vertices sit ~1.8 mm apart, so a single-vertex
        mark is a sub-2 mm dot on a whole head and cannot be seen at any useful
        zoom, nor hit with the mouse; 3 mm covers ~8 vertices, about 5 mm
        across.  Applied to **every** candidate, in rank order onto unclaimed
        vertices, so a better rank always wins an overlap.
    mark_top_n:
        How many ranked candidates the surface mask shows.  Not a cap on the
        pool -- scoring and `ranked` are unaffected, this is only what gets
        drawn.
    adopted_vtx:
        Vertex actually in use, marked as a magenta sphere in the foci file.  Defaults to the index of the sole ``vtx*``
        placement folder if there is exactly one; pass explicitly to override,
        or pass -1 to suppress.  The ranks are *surface-metric* order and need
        not agree with it — see the note in the marker block.
    write_marker:
        Write ``best_vtx_marker_skin.func.gii``.  Set False to score and rank
        without touching the file — :func:`describe_vtx` does that to answer a
        query mid-placement.

    Returns
    -------
    best_vtx : int
        Vertex index of the selected scalp vertex.
    metrics : dict
        Keys: ``vtx_idx``, ``n_valid``, ``distance_mm``, ``angle_deg``,
        ``skin_skull_deg``, ``intersection_mm``, ``angle_exceeded``,
        ``max_angle_deg``.
    angle_exceeded : int
        Always 0 (angle is a hard constraint; exceeded vertices are excluded).

    Raises
    ------
    ValueError
        If no vertices survive hard safety constraints (avoidance + distance + angle).
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
        "skl":      target_folder / "skin_skull_angles_skin.func.gii",
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
    skl      = _fold_obliquity(nib.load(required["skl"]).darrays[0].data)
    dist_raw = np.load(required["dist_raw"])

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
        _coords = np.asarray(
            nib.load(str(target_folder / "skin.surf.gii")).darrays[0].data, dtype=float)
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

    _coords_sl = np.asarray(
        nib.load(str(target_folder / "skin.surf.gii")).darrays[0].data, dtype=float)

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
        if all(np.linalg.norm(_coords_sl[_v] - _coords_sl[_q]) >= shortlist_sep_mm
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

    _coords = np.asarray(
        nib.load(str(target_folder / "skin.surf.gii")).darrays[0].data)
    _order = np.where(top_candidates)[0]
    _order = _order[np.argsort(score[_order], kind="stable")]
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
    _template = nib.load(required["inter"])  # target_intersection_skin.func.gii
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
    import nibabel as nib                                         # noqa: PLC0415

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
        g = lambda f: np.asarray(nib.load(str(target_folder / f)).darrays[0].data)
        ang = g("angles_skin.func.gii")
        skl = _fold_obliquity(g("skin_skull_angles_skin.func.gii"))
        inter = np.nan_to_num(g("target_intersection_skin.func.gii"), nan=0.0)
        dist = np.load(target_folder / "skin_target_distances.npy")
        crd = g("skin.surf.gii")
        v = int(vtx)
        return (f"  vtx{v}   aim {ang[v]:.1f}°   skl {skl[v]:.1f}°   "
                f"dist {dist[v]:.1f} mm   inter {inter[v]:.2f} mm\n"
                f"             NOT in the candidate pool (needs inter ≥ "
                f"{m['top_pct'] * m['max_inter_mm']:.2f} mm)   |   "
                f"{np.linalg.norm(crd[v] - crd[best]):.1f} mm from the "
                f"suggestion (vtx{best})")
    except Exception as _e:
        return f"  vtx{vtx}: could not read metrics — {type(_e).__name__}: {_e}"


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
        / f"{target_roi_name}_depth_vtx{vertex_idx}.txt"
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
    # arccos gives 0-180; fold to [0, 90] so the wb_view overlay shows the same
    # obliquity the selection and the reports use.  See _fold_obliquity().
    _skl_raw    = np.asarray(skin_skull_angle_list)
    _skl_folded = _fold_obliquity(_skl_raw)
    _n_folded   = int((_skl_raw > 90.0).sum())
    if _n_folded:
        print(f"Skin-skull angle: folded {_n_folded} of {_skl_raw.size} vertices "
              f"from >90° into [0, 90] (ray hit the inner table)")
    PlanTUS.create_metric_from_pseudo_nifti("skin_skull_angles", _skl_folded, str(output_path) + "/skin.surf.gii")
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

    # ── Guarantee the marker file exists before the scene points at it ────
    # The scene entry is injected here, but the file itself is only written
    # later, by select_best_vtx() inside run_plantus_placement().  When that
    # selection fails the file never appears, and wb_view then refuses to open
    # the scene with "file cannot be loaded" — permanently, since nothing
    # revisits the scene.  Four targets were left in that state by the NaN bug
    # in the intersection map (sub-CM aMCC_R, sub-MO aMCC_L, sub-TT aMCC_R,
    # sub-z002 aMCC_R).
    #
    # Write an all-NaN marker now: NaN renders fully transparent, so an
    # unselected target looks exactly as it did before, and select_best_vtx
    # overwrites it with the real one.  The scene reference always resolves.
    import nibabel as _nib_m                                    # noqa: PLC0415

    _marker_path = output_path / "best_vtx_marker_skin.func.gii"
    if not _marker_path.is_file():
        _tmpl = _nib_m.load(str(output_path / "target_intersection_skin.func.gii"))
        _meta = _nib_m.gifti.GiftiMetaData()
        _meta["Name"] = "best_vtx_marker"
        _nib_m.gifti.GiftiImage(
            meta=_tmpl.meta,
            darrays=[_nib_m.gifti.GiftiDataArray(
                data=np.full(np.asarray(_tmpl.darrays[0].data).shape[0],
                             np.nan, dtype=np.float32),
                intent=_tmpl.darrays[0].intent,
                datatype="NIFTI_TYPE_FLOAT32",
                meta=_meta,
            )],
        ).to_filename(str(_marker_path))
        print("Placeholder marker written → best_vtx_marker_skin.func.gii "
              "(replaced once a vertex is selected)")

    # Same for the foci file, and for the same reason: the scene names it, so
    # it has to exist or wb_view refuses to open the scene at all.  An empty
    # FociFile is valid and draws nothing.
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

    # ── Inject best_vtx_marker into scene.scene ───────────────────────────
    # The template has 9 entries; we append Element Index="9" for the marker
    # METRIC file and bump the dataFilesArray Length from 9 to 10.
    scene_path = output_path / "scene.scene"
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

    # Save distances array so step04b / run_plantus_placement can load it
    np.save(str(output_path / "skin_target_distances.npy"), skin_target_distances)
    print("Distances saved →", str(output_path / "skin_target_distances.npy"))

    os.chdir(_saved_cwd)
    return output_path


def list_plantus_vertices(target_folder, print_table: bool = True) -> list[dict]:
    """Summarise every placement that exists for one PlanTUS target.

    Used in: step 04 and step 05, to see and choose between placements.

    Reads the same per-vertex maps :func:`select_best_vtx` ranks on, so the
    numbers shown are the ones the automatic choice was based on.

    ``inter`` is how far the beam *axis* through that one vertex clips the ROI.
    It is knife-edge: neighbouring vertices 1–3 mm away routinely differ by
    several mm, so a vertex can read 0.00 while sitting just inside the red patch
    wb_view draws. Do **not** read 0.00 as "the beam misses the target" — the
    −3 dB focal region is ~6–10 mm across laterally, far wider than that offset.
    ``inter_near_mm``
    gives the best value within 5 mm, which is what makes an edge case visible.

    ``side`` is ``contra`` when entry and target sit on opposite sides of x=0,
    i.e. the beam crosses the midline.

    Parameters
    ----------
    target_folder:
        Per-target PlanTUS directory, e.g.
        ``m2m_dir / "PlanTUS" / "sub-z002_aHipp_Weizhen_p05_mask-L"``.
    print_table:
        Also print a table, newest placement last.

    Returns
    -------
    list of dict
        One record per vertex, sorted by index.  Keys: ``vtx``, ``dist_mm``,
        ``fd_mm``, ``angle_deg``, ``skin_skull_deg``, ``inter_mm``,
        ``inter_near_mm``, ``entry``, ``side``, ``path_mm``, ``has_folder``,
        ``has_figure``, ``has_trajectory``.

        The two angles measure different things and the table shows both:

        ``angle_deg`` (``aim°``, from ``angles_skin.func.gii``) is scalp normal
        vs the scalp→target vector — **how squarely the target is aimed at**.
        This is the one PlanTUS filters on, against ``max_angle`` (10°).

        ``skin_skull_deg`` (``skl°``, from ``skin_skull_angles_skin.func.gii``)
        is scalp normal vs the nearest **skull** normal — how obliquely the beam
        meets bone.  PlanTUS computes it but does not use it, even though oblique
        incidence on bone is what drives reflection loss and refraction, so it is
        worth watching alongside the derating ratio.
        Vertices with a depth report but no folder are included with
        ``has_folder=False`` — a deleted folder leaves the report behind.
    """
    import re as _re

    import nibabel as _nib
    import numpy as _np

    folder = Path(target_folder)

    def _metric(name):
        p = folder / name
        return _nib.load(str(p)).darrays[0].data if p.is_file() else None

    _dist  = (_np.load(folder / 'skin_target_distances.npy')
              if (folder / 'skin_target_distances.npy').is_file() else None)
    _ang   = _metric('angles_skin.func.gii')
    _sskul = _metric('skin_skull_angles_skin.func.gii')
    _inter = _metric('target_intersection_skin.func.gii')
    _surf  = (folder / 'skin.surf.gii')
    _crd   = _nib.load(str(_surf)).darrays[0].data if _surf.is_file() else None

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

    def _fd(path):
        for line in open(path):
            if line.startswith('focal_distance_fd_mm:'):
                return float(line.split(':')[1])
        return None

    out = []
    for v in sorted(set(vtx_dirs) | set(reports)):
        vd = vtx_dirs.get(v)
        entry = side = path_mm = None
        if vd is not None:
            try:
                e, t = get_vtx_coordinates(vd, folder, v)
                e, t = _np.asarray(e, float), _np.asarray(t, float)
                entry   = tuple(round(float(c), 1) for c in e)
                side    = 'contra' if e[0] * t[0] < 0 else 'ipsi'
                path_mm = round(float(_np.linalg.norm(t - e)), 1)
            except Exception:
                pass
        traj = folder.glob(f'*_vtx{v}_brainsight.txt')
        out.append({
            'vtx':            v,
            'dist_mm':        None if _dist  is None else round(float(_dist[v]), 1),
            'fd_mm':          _fd(reports[v]) if v in reports else None,
            'angle_deg':      None if _ang   is None else round(float(_ang[v]), 1),
            'skin_skull_deg': None if _sskul is None
                              else round(float(_fold_obliquity(_sskul[v])), 1),
            'inter_mm':       None if _inter is None
                              else round(float(_np.nan_to_num(_inter[v])), 2),
            'inter_near_mm':  _inter_near(v),
            'entry':          entry,
            'side':           side,
            'path_mm':        path_mm,
            'has_folder':     vd is not None,
            'has_figure':     bool(vd and (vd / f'vtx{v}_placement.png').is_file()),
            'has_trajectory': any(traj),
        })

    if print_table and out:
        newest = (max(vtx_dirs, key=lambda k: vtx_dirs[k].stat().st_mtime)
                  if vtx_dirs else None)
        print(f'{len(out)} placement(s) in {folder.name}:')
        print(f"  {'vtx':>7} {'dist':>6} {'fd':>6} {'aim°':>5} {'skl°':>5} "
              f"{'inter':>6} {'≤5mm':>6} {'side':>6}  {'traj':>4} {'fig':>4}  entry")
        for r in out:
            fmt = lambda v, w, p=1: (f'{v:{w}.{p}f}' if isinstance(v, float)
                                     else ' ' * (w - 1) + '-')
            print(f"  {r['vtx']:>7} {fmt(r['dist_mm'],6)} {fmt(r['fd_mm'],6)} "
                  f"{fmt(r['angle_deg'],5)} {fmt(r['skin_skull_deg'],5)} "
                  f"{fmt(r['inter_mm'],6,2)} "
                  f"{fmt(r['inter_near_mm'],6,2)} "
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

    Used in: step 04, at the moment a vertex is confirmed.

    Unlike :func:`capture_plantus_scene`, which re-renders a saved scene, this
    captures what is actually on screen — including the clicked vertex marker and
    the metric overlay as it was configured at that moment, neither of which is
    stored in ``scene.scene``.

    Requires macOS **Screen Recording** permission for the app running the kernel
    (VS Code / Terminal), granted in System Settings → Privacy & Security →
    Screen Recording, followed by restarting that app.  Without it
    ``screencapture`` exits 1 with "could not create image from window" and
    writes nothing; that case is detected and explained rather than passed over.

    Parameters
    ----------
    out_path:
        PNG path.  With several matching windows, ``_2``, ``_3`` … are appended.
    owner:
        Process name to match, as reported by the window server.

    Returns
    -------
    Path or None
        The first image written, or ``None`` if no window matched or the capture
        produced nothing usable.  Never raises — a missing screenshot must not
        interrupt placement.
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

    PlanTUS shows the chosen placement in ``wb_view`` and the window is then
    closed, leaving no image behind.  This renders the same ``scene.scene``
    offscreen with ``wb_command -scene-capture-image`` so the placement is kept
    as a reviewable figure next to the vertex it belongs to.

    Used in: step 04 (after each placement).

    Known limitation
    ----------------
    Offscreen rendering draws the **3D surface view** — head, transducer and
    focus cone, which is the part that documents the choice — but leaves the
    three volume-slice panels black: wb_command does not draw volume layers
    without a real GL window.  For T1 slices through the target, use the step 5
    QC figures instead.

    Parameters
    ----------
    vtx_dir:
        ``vtx{N}/`` directory written by ``prepare_acoustic_simulation``, which
        contains ``scene.scene``.
    overwrite:
        Re-render even when the PNG already exists.

    Returns
    -------
    Path or None
        Path to the PNG, or ``None`` if the scene was missing or the render
        failed (never raises — a missing figure must not lose a placement).
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

    While a placement runs, PlanTUS opens a **second** wb_view to show the
    transducer position, via a blocking ``os.system`` call.  Clicks in that
    window are ignored, and any vertex logged by the first window meanwhile is
    discarded, so the next prompt always refers to a vertex clicked *after* the
    placement view was closed rather than a stale one.

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
    top_pct:
        Fraction of the maximum intersection used to define the top-candidate
        pool for :func:`select_best_vtx` (default 0.8).  Lower values broaden
        the pool, giving more weight to angle/distance in tiebreaking.
    reuse_placement:
        If True (default) and a ``vtx*`` folder already exists for this target,
        report it and return without opening ``wb_view``.  This is what makes
        the step-4 notebook safe to "Run All": placement is the one interactive
        stage, so without this it would block on a vertex click every time.
        Set False to force a fresh placement.
    weights:
        Tiebreak weighting ``(aim_angle, distance, skin_skull_angle)`` passed to
        :func:`select_best_vtx`, and echoed in the ``[auto vtx]`` block so the
        rule behind the suggestion is visible in the notebook.  ``(1, 1, 0)``
        reproduces the behaviour before the skin-skull term was added.
    mark_radius_mm:
        Radius of the blob drawn at the suggested vertex in wb_view.  A single
        vertex is invisible at ~1.8 mm scalp spacing; the blob never overwrites
        another candidate's rank.
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
    coordinate_system: str = "NIfTI:S:Scanner",
    append: bool = False,
    vtx: int | None = None,
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
        String written to the BrainSight header (default ``"NIfTI:S:Scanner"``).
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
    vtx:
        Vertex index to use, e.g. ``9037``.  ``None`` (default) uses the newest
        ``vtx*`` folder by modification time — the intended behaviour both when
        only one placement exists and when none is specified.  Pin an index only
        to override that, e.g. to compare two placements of the same target.

    Returns
    -------
    Path
        Path to the per-vertex BrainSight .txt file.

    Notes
    -----
    Writes one file per vertex,
    ``{label}_vtx{N}_brainsight.txt``, carrying a
    ``# Vertex: N`` header line.  Exports therefore accumulate instead of
    overwriting, and step 5 can select a placement rather than inheriting
    whichever was written last.
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


# ===========================================================================
# Step 05-BB — BabelBrain simulations (domain · acoustic · thermal)
# ===========================================================================

def _drain_queue_BB(p, Q, silence_timeout=900):
    """Drain *Q* while *p* is alive; return ``True`` if no errors detected.

    Prints all string messages from the queue and checks for the
    ``'--Babel-Brain-Low-Error'`` sentinel.  Also treats a non-zero process
    exit code as an error.

    Parameters
    ----------
    silence_timeout : float or None
        Raise ``RuntimeError`` if *p* is still alive but has produced no output
        for this many seconds.  ``None`` disables the guard.

        BabelBrain starts nested processes and waits on them with a bare
        ``queueResult.get()`` and no liveness check
        (``Babel_Thermal/CalculateThermalProcess.py``,
        ``ThermalModeling/CalculateTemperatureEffects.py``).  Those inner
        processes have no ``try/except`` and redirect stdout only, so if one dies
        the traceback is lost and the wait never ends.  Without this guard such a
        death is indistinguishable from a long computation; it previously cost
        several multi-hour "hangs" that were actually immediate crashes.

    Private helper used by run_domain_BB, run_acoustic_BB, run_thermal_BB.
    """
    import time as _time

    bNoError = True
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

    if p.exitcode not in (0, None):
        bNoError = False

    return bNoError


def patch_babelvisco_BB(force=False):
    """Correct the BabelViscoFDTD ``intparams`` dtype bug, on disk.

    Must be called before any thermal simulation (Step 5c / :func:`run_thermal_BB`).

    Background
    ----------
    ``BabelViscoFDTD.tools.RayleighAndBHTE`` builds the GPU kernel parameter
    array ``intparams`` with ``dtype=np.uint32`` while passing
    ``LocationMonitoring = -1`` (the "no monitoring slice" sentinel, set in
    ``ThermalModeling/CalculateTemperatureEffects.py``).  Under numpy >= 2 that
    raises ``OverflowError: Python integer -1 out of bounds for uint32`` on the
    first BHTE timestep.  numpy 1.x wrapped silently to ``0xFFFFFFFF``, which is
    what the shader expects, so the bug only became fatal after the numpy 2
    upgrade.

    ``uint32`` is simply the wrong type: the Metal shader in that same file
    declares the parameter as **signed** —
    ``constant int * intparams [[ buffer(12) ]]`` with ``#define SelJ intparams[7]``
    — so the wrapped value is read back as ``-1`` and the monitoring branch is
    correctly skipped.  ``np.int32`` is therefore the correct dtype, and writing
    it is an upstream bug fix rather than a workaround.

    Why the fix must be on disk, not a monkeypatch
    ----------------------------------------------
    BHTE does not run in this process.  ``CalculateThermalProcess`` starts a
    nested ``multiprocessing.Process`` using the *global* start method, which on
    macOS is ``spawn``.  A spawned child is a fresh interpreter that re-imports
    ``RayleighAndBHTE``, so any in-memory patch applied here is absent from the
    process that actually runs BHTE.  Editing the installed file is the only fix
    that reaches every nesting level, and it removes the previous need to force
    the ``fork`` start method globally (which crashed Metal, since importing
    BabelViscoFDTD initialises the Metal runtime at import time).

    That nested child has no ``try/except`` and redirects **stdout only**, so an
    exception there is invisible and the parent blocks forever on
    ``queueResult.get()`` — which is why this bug presented as a multi-hour hang
    with no output rather than as an error.

    This function is idempotent: it rewrites only the sites that still say
    ``uint32``, and does nothing once they are correct.  It is also safe after a
    package reinstall, which would restore the buggy file.

    Affected
    --------
    ``BabelViscoFDTD/tools/RayleighAndBHTE.py`` — the four ``intparams``
    constructions (two in ``BHTE``, two in ``BHTEMultiplePressureFields``;
    Metal and MLX branches of each).  The ``MonitoringPoints`` arrays in the same
    file must stay ``uint32``: the shader declares
    ``constant unsigned int *d_pointsMonitoring`` and ``BHTE`` asserts
    ``MonitoringPointsMap.dtype == np.uint32``.

    Parameters
    ----------
    force : bool
        Unused; retained for call-site compatibility.  The rewrite is already
        conditional on the file's current contents.

    Used in: step 05 notebook (Step 5c).
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
    """Read the target ID from a Brainsight trajectory file.

    Replicates the logic used by the BabelBrain GUI
    (``BabelBrain.py`` → ``ReadTrajectoryBrainsight(fname, bGetID=True)[1]``):
    the ID is the value in the ``Target name`` column of the first non-comment
    data row, **not** the filename stem.

    Example: for a trajectory file whose first data row starts with
    ``sub-M3827_CeA_CIT168-L``, this function returns exactly that
    string — which the GUI uses as ``Config['ID']``.

    Parameters
    ----------
    trajectory_file : str or Path
        Path to the Brainsight-format ``.txt`` trajectory file produced by
        Step 4 (PlanTUS).

    Returns
    -------
    str
        The target name string from the first data row.

    Raises
    ------
    FileNotFoundError
        If the trajectory does not exist, with the Step-4 stage that produces it
        named — a bare open() error here is hard to act on, because the missing
        file can mean either that placement (4b) never ran or that it ran but the
        BrainSight export (4c) did not.
    ValueError
        If no data rows are found in the file.
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
    """Return which placement to use: *vtx* when given, else the newest.

    The single rule for the whole pipeline::

        vtx is None  ->  the newest vtx* folder (most recently placed)
        vtx = N      ->  vertex N

    Whatever it returns then determines *everything* — the trajectory file, the
    depth report, and the output names — so the three cannot disagree.

    The canonical trajectory (``{label}_brainsight``)
    is deliberately not consulted: it is a fixed-name copy of the most recent
    export, so it cannot say which placement wrote it.  (The name is a
    convention of this pipeline, not a BrainSight requirement.)

    Used in: :func:`write_brainsight_for_vtx`, step 05 (Step 5-0).

    Raises
    ------
    FileNotFoundError
        If no ``vtx*`` folder exists, or if *vtx* names one that does not.
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

    Returns ``(depth_mm, verdict)`` where verdict is ``"ok"``,
    ``"below_calibrated"``, ``"above_hardware"`` or ``"below_hardware"``.

    Pass *tx_cfg* -- the raw transducer YAML, ``cfg["transducer_cfg"]`` -- not
    ``transducer_params()``, which drops the calibrated bounds: it exposes only
    min_distance and max_distance, so a depth inside the hardware range but
    below the calibrated one would come back "ok".

    Use this rather than deriving the depth. It is one field the pipeline
    already writes -- ``exit_plane_to_ROI_distance_mm`` -- and recomputing it
    is how I produced a false alarm: I formed it as
    ``skin_to_ROI + plane_offset + gel`` and reported that four placements
    exceeded the transducer's 120 mm limit, that select_best_vtx had a
    systematic 10 mm error, and that the constraint should be rewritten. All
    three were wrong, and the fix would have broken correct behaviour.

    ``plane_offset_mm`` is the distance from the radiating surface to the exit
    plane -- inside the housing. The exit plane is the outer face of the
    coupling (BCS-NF10), and that is what rests on the scalp. So

        exit_plane_to_ROI = skin_to_ROI + pad

    with no plane_offset term. The report states this directly:
    sub-z002 alEC left reads skin 113.07, plane_offset 10.00, pad 0.00, and
    exit_plane_to_ROI 113.07 -- not 123.07.
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
    """Parse the PlanTUS depth report and return its fields as a dict.

    Reads the ``*_depth_vtx*.txt`` report written during placement
    and returns a dictionary of all key–value entries, with numeric values
    cast to ``float``.

    Used in: step 05 notebook (Step 5b), to obtain ``skin_to_ROI_distance_mm``
    for computing the electronic steering offset (ZSteering).

    Parameters
    ----------
    plantus_target_folder:
        Path to the per-target PlanTUS output directory,
        e.g. ``m2m_dir / "PlanTUS" / "sub-M3827_CeA_CIT168_mask-L"``.
    vtx:
        Vertex index whose report to read, e.g. ``26749``.  Required once more
        than one placement exists for the target.

        This argument exists because the previous behaviour — take
        ``sorted(glob(...))[0]``, the alphabetically first report — silently read
        a *different* vertex than the one the trajectory came from as soon as a
        second placement was made, so ZSteering was derived from the wrong depth.
        Measured on sub-z002: reports for 15110/26749/27604 present, trajectory
        exported from 26749 (103.0 mm), report read 15110 (114.1 mm) — an 11 mm
        error, on the same scale as the focus displacement being investigated.

    Returns
    -------
    dict
        Parsed key–value pairs from the depth-report file.
        All numeric values are returned as ``float``.

    Raises
    ------
    FileNotFoundError
        If no depth-report file is found, or if *vtx* has no report.
    ValueError
        If several reports exist and *vtx* is ``None``.  Failing here is
        deliberate: guessing is what caused the bug above.
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
    """Load the BabelBrain transducer default.yaml for *tx_system*.

    Resolves the path pattern
    ``{bb_dir}/BabelBrain/Babel_{tx_system_no_underscores}*/default.yaml``
    and returns the parsed dict.

    Used in: step 05 notebook (Step 5b).

    Parameters
    ----------
    bb_dir : str | Path
        Root of the BabelBrain git clone (value of ``babelbrain_dir`` in site
        config after path expansion).
    tx_system : str
        BabelBrain transducer identifier, e.g. ``'DPX_500'``.

    Returns
    -------
    dict
        Parsed YAML content (includes ``InDiameters``, ``OutDiameters``, etc.).

    Raises
    ------
    FileNotFoundError
        If no matching YAML is found.
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


def compute_z_steering_BB(plantus_target_folder, tx_cfg, additional_offset_mm=0,
                          bb_tx_yaml=None, vtx=None):
    """Compute BabelBrain ZSteering offset from PlanTUS depth report.

    ZSteering steers the annular-array focus from the transducer's natural
    outplane focal distance to the effective skin-to-ROI depth::

        effective_depth = exit_plane_to_ROI_distance + additional_offset_mm
        ZSteering       = effective_depth - geometric_focal_depth  (metres)

    A negative value steers the focus closer (shallower) than the natural
    focal distance; positive steers deeper.

    ``additional_offset_mm`` matches the PlanTUS / transducer-YAML field of
    the same name: extra physical spacing (gel pad) placed between the coupling
    bladder and the participant's head.  It is intentionally **not** applied at
    Step 4 (PlanTUS), so that the placement optimisation is independent of the
    pad choice; it is applied here only to correctly steer the acoustic focus.

    When ``additional_offset_mm=0`` and the ROI depth falls below
    ``min_focal_depth_mm``, this function prints a ⚠ warning and suggests the
    minimum standard gel pad thickness (from :data:`_GEL_PAD_STANDARD_MM`)
    needed to bring the effective depth into the calibrated range.

    Note on depth source: The PlanTUS depth report value (``exit_plane_to_ROI_distance_mm``)
    may differ from the BabelBrain GUI's internal ``DistanceFromSkin`` by ~0.1 mm.
    The GUI computes distance from its beam-aligned internal numpy array, whereas
    this function reads from the text depth report.  The resulting ZSteering
    difference (< 0.1 mm) is scientifically negligible.

    Used in: step 05 notebook (Step 5b).

    Parameters
    ----------
    plantus_target_folder : Path | str
        Per-target PlanTUS output directory containing the depth-report txt.
    tx_cfg : dict
        Transducer config dict (from ``cfg['transducer_cfg']``).  Must contain
        ``geometric_focal_depth_mm``; may contain ``min_focal_depth_mm`` and
        ``max_focal_depth_mm`` for range validation.
    additional_offset_mm : float
        Extra physical spacing (gel pad) in mm added between the coupling
        bladder and the participant's head.  Increases effective focal depth.
        Matches the ``additional_offset_mm`` field in transducer YAMLs and
        PlanTUS depth reports.  Set ``ADDITIONAL_OFFSET_MM`` in the notebook
        Settings cell.  Defaults to 0.
    vtx : int or None
        Vertex the trajectory was exported from.  Forwarded to
        :func:`read_depth_report`, which requires it once a target has more than
        one placement — reading another vertex's report would silently steer to
        the wrong depth.

    Returns
    -------
    tuple of (float, float)
        ``(z_steering, tx_mech_adj_z)`` both in metres.

        ``z_steering`` is the electronic steering offset passed as
        ``ZSteering`` to ``run_acoustic_BB``.  Negative for targets shallower
        than the natural focal distance.

        ``tx_mech_adj_z`` is always **0.0** for ANNULAR_ARRAY transducers
        (DPX/CTX).  ``BabelIntegrationANNULAR_ARRAY.py`` adds
        ``TxMechanicalAdjustmentZ`` directly to the Rayleigh focal-centre
        position (``center[0,2]``), so passing a non-zero value displaces the
        acoustic focus by the same amount.  The BabelBrain GUI (Babel_RingTx)
        never sets this parameter — it always remains at its default of 0.0.
        The second return value is kept for API compatibility but must not be
        changed from 0.0 for ANNULAR_ARRAY transducers.
    """
    # vtx must be the vertex the trajectory came from; read_depth_report raises
    # rather than guessing when several placements exist.
    report = read_depth_report(plantus_target_folder, vtx=vtx)
    roi_depth_mm = report.get(
        'exit_plane_to_ROI_distance_mm',
        report.get('skin_to_ROI_distance_mm'),
    )

    nat_focus_mm = tx_cfg.get('geometric_focal_depth_mm',
                              tx_cfg.get('radius_of_curvature_mm', 0))
    min_mm      = tx_cfg.get('min_focal_depth_mm', 0)
    max_mm      = tx_cfg.get('max_focal_depth_mm', 999)
    cal_min_mm  = tx_cfg.get('calibrated_min_focal_depth_mm', min_mm)
    cal_max_mm  = tx_cfg.get('calibrated_max_focal_depth_mm', max_mm)

    import numpy as _np

    effective_depth_mm = roi_depth_mm + additional_offset_mm
    effective_depth_m  = effective_depth_mm / 1e3

    # ── BabelBrain Corrections polynomial (matches GUI Babel_RingTx.py) ──
    correction_m = 0.0
    if bb_tx_yaml is not None:
        _corrections = bb_tx_yaml.get('Corrections', {})
        _coeffs = _corrections.get('Original')
        if _coeffs is not None:
            correction_m = float(_np.polyval(_coeffs, effective_depth_m))

    # NaturalOutPlaneDistance from BabelBrain YAML takes priority over
    # geometric_focal_depth_mm from tx_cfg (the two may differ slightly).
    nat_outplane_m = (
        bb_tx_yaml['NaturalOutPlaneDistance']
        if (bb_tx_yaml is not None and 'NaturalOutPlaneDistance' in bb_tx_yaml)
        else nat_focus_mm / 1e3
    )

    # BabelBrain GUI formula (confirmed from GUI terminal log, 2026-04-09):
    #   CalculateFieldProcess parameters: ZSteering=-0.0875, TxMechanicalAdjustmentZ=0.0857
    # BabelIntegrationANNULAR_ARRAY.py line 371:
    #   center[0,2] = ZDim[FocalSpotLocation[2]] + ZSteering + TxMechanicalAdjustmentZ
    #              = 150.0 + (-87.5) + 85.7 = 148.2 mm  ← inside domain ✓
    # Both ZSteering and TxMechanicalAdjustmentZ are required.
    # See README_NOTE05_2.md §追加調査7 for full analysis.
    z_steering    = effective_depth_m - nat_outplane_m + correction_m
    tx_mech_adj_z = nat_outplane_m - effective_depth_m

    print(f"ROI depth (exit plane → ROI):  {roi_depth_mm:.2f} mm")
    if additional_offset_mm > 0:
        print(f"Additional offset (gel pad):   +{additional_offset_mm:.1f} mm")
        print(f"Effective depth:               {effective_depth_mm:.2f} mm")
    print(f"Natural outplane distance:     {nat_outplane_m * 1e3:.1f} mm")
    if correction_m != 0.0:
        print(f"BabelBrain correction:         {correction_m * 1e3:+.2f} mm")
    print(f"ZSteering:                     {z_steering * 1e3:.2f} mm  ({z_steering:.4f} m)")
    print(f"TxMechanicalAdjustmentZ:       {tx_mech_adj_z * 1e3:.2f} mm  ({tx_mech_adj_z:.4f} m)")

    if not (min_mm <= effective_depth_mm <= max_mm):
        if effective_depth_mm < min_mm:
            deficit = min_mm - roi_depth_mm
            suggestion = next(
                (g for g in _GEL_PAD_STANDARD_MM if roi_depth_mm + g >= min_mm),
                None,
            )
            print(f"  ⚠ Effective depth {effective_depth_mm:.1f} mm below hardware "
                  f"minimum {min_mm} mm  (deficit: {deficit:.1f} mm)")
            if additional_offset_mm == 0 and suggestion is not None:
                print(f"  → Add a {suggestion} mm gel pad to reach "
                      f"{roi_depth_mm + suggestion:.1f} mm  "
                      f"(set ADDITIONAL_OFFSET_MM = {suggestion} in Settings)")
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
    """Run BabelBrain domain-generation step (CalculateMaskProcess).

    Generates the tissue-mask NIfTI used as input to the acoustic simulation.

    Used in: step 05 notebook (Step 5a).

    Parameters
    ----------
    m2m_dir:
        Path to the ``m2m_{sub_id}`` SimNIBS output directory.
    t1w:
        Path to ``T1.nii.gz`` inside *m2m_dir*.
    trajectory_file:
        BrainSight-format trajectory ``.txt`` from Step 4 (PlanTUS).
    prefix:
        Output filename prefix, e.g.
        ``sub-M3827_Ce_CeA_L_DPX_500_500kHz_6PPW_``.
    backend:
        BabelBrain computing backend string, e.g. ``'Metal'``.
    device:
        Device name passed to BabelBrain, e.g. ``'M2Pro'``.
    frequency:
        Transducer centre frequency in Hz.
    ppw:
        Points per wavelength (6 = fast, 9 = converged).
    domain_file:
        Expected output path, e.g.
        ``{m2m_dir}/{prefix}BabelViscoInput.nii.gz``.
        Checked for existence when *reuse_files* is ``True``.
        The underlying BabelBrain call is ``CalculateMaskProcess``.
    use_ct : bool
        Whether a CT scan is available.
    ct_path : str
        Path to CT NIfTI (required when *use_ct* is ``True``).
    ct_type : int
        ``1`` real CT, ``2`` ZTE, ``3`` PETRA.
    reuse_files : bool
        Skip if *domain_file* already exists.
    dry_run : bool
        Validate paths only; do not run the simulation.

    Returns
    -------
    str
        Absolute path to the domain file.

    Raises
    ------
    RuntimeError
        If the process reports an error or exits non-zero.
    """
    import os as _os
    import time as _time
    from multiprocessing import get_context as _get_context
    from pathlib import Path as _Path

    import numpy as _np
    from BabelBrain.CalculateMaskProcess import CalculateMaskProcess
    from TranscranialModeling.BabelIntegrationBASE import GetSmallestSOS

    # Metal is not fork-safe on macOS; always spawn explicitly.
    _mp_ctx = _get_context('spawn')

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

    Q = _mp_ctx.Queue()
    p = _mp_ctx.Process(
        target=CalculateMaskProcess,
        args=(Q, backend, device),
        kwargs=kargs,
    )
    p.start()
    bNoError = _drain_queue_BB(p, Q)

    if not bNoError:
        raise RuntimeError('[5a] CalculateMaskProcess reported an error.')

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
    """Run BabelBrain acoustic-simulation step (CalculateFieldProcess).

    Supports ANNULAR_ARRAY (CTX/DPX) transducers.  Because BabelBrain does
    not call ``queue.put()`` for ANNULAR_ARRAY skull outputs, the result h5
    path is derived by globbing after the process exits rather than reading
    from the queue.

    Used in: step 05 notebook (Step 5b).

    Parameters
    ----------
    m2m_dir:
        Path to the ``m2m_{sub_id}`` SimNIBS output directory.
    field_target:
        Job-ID string built as ``{ID}_{TX_SYSTEM}``,
        e.g. ``'sub-M3827_Ce_CeA_L_DPX_500'``.
    tx_system:
        BabelBrain transducer identifier, e.g. ``'DPX_500'``.
    frequency:
        Centre frequency in Hz.
    aperture:
        Total transducer aperture (TxDiam) in metres.
    focal_length:
        Focal length in metres.
    in_diameters:
        Array of element inner diameters from the transducer YAML.
    out_diameters:
        Array of element outer diameters from the transducer YAML.
    backend:
        Computing backend string.
    device:
        Device name.
    ppw:
        Points per wavelength.
    z_steering : float
        Electronic focal steering in metres relative to the natural focal
        distance.  ``ZSteering = skin_to_ROI_distance - natural_outplane_distance``
        (both in metres).  For DPX-500 targeting CeA at ~59 mm depth with
        NaturalOutPlaneDistance = 144.9 mm this is approximately -0.086 m.
        Defaults to 0.0 (no steering; focus at the natural outplane distance).
    tx_mech_adj_z : float or None
        Transducer mechanical Z position offset in metres.  For ANNULAR_ARRAY
        transducers (DPX/CTX), **always pass 0.0**.
        ``BabelIntegrationANNULAR_ARRAY`` adds this value directly to the
        Rayleigh focal-centre z position (``center[0,2]``), so any non-zero
        value physically displaces the acoustic focus by the same amount.
        The BabelBrain GUI (Babel_RingTx) never sets this parameter; it stays
        at the default of 0.0.  :func:`compute_z_steering_BB` now always
        returns 0.0 as the second value.  If ``None``, defaults to 0.0.
        See README_NOTE05_2.md §追加調査4 for root-cause analysis.
    z_beyond : float
        Simulation depth beyond the target focal point in metres.
    use_ct : bool
        Whether a CT scan was used in Step 5a.
    reuse_files : bool
        Skip if ``*DataForSim.h5`` (non-water) already exists.
    dry_run : bool
        Validate paths only; do not run the simulation.

    Returns
    -------
    str
        Path to the skull ``DataForSim.h5`` file.

    Raises
    ------
    RuntimeError
        If the process errors or no output file is found.
    """
    import os as _os
    import time as _time
    import numpy as _np
    from glob import glob as _glob
    from multiprocessing import get_context as _get_context
    from pathlib import Path as _Path

    _mp_ctx = _get_context('spawn')

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

    Q = _mp_ctx.Queue()
    p = _mp_ctx.Process(
        target=_CalculateFieldProcess_wrapped,
        args=(Q, [field_target], tx_system),
        kwargs=kargs,
    )
    p.start()

    bNoError = True
    field_out = None
    while p.is_alive():
        _time.sleep(0.1)
        while not Q.empty():
            msg = Q.get()
            if isinstance(msg, str):
                print(msg, end='')
                if '--Babel-Brain-Low-Error' in msg:
                    bNoError = False
            else:
                field_out = msg

    p.join()
    while not Q.empty():
        msg = Q.get()
        if isinstance(msg, str):
            print(msg, end='')
            if '--Babel-Brain-Low-Error' in msg:
                bNoError = False
        else:
            field_out = msg

    if p.exitcode not in (0, None):
        bNoError = False

    if not bNoError:
        raise RuntimeError(
            f'[5b] CalculateFieldProcess reported an error '
            f'(exitcode={p.exitcode}).  '
            f'Check the output above for the full traceback.'
        )

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
    """Run BabelBrain thermal simulation step (CalculateThermalProcess).

    Solves the Bio-heat Thermal Equation (BHTE) for all DC/PRF/Duration
    combinations in *thermal_profile*.

    .. important::
        Call :func:`patch_babelvisco_BB` before this function to work
        around the BabelViscoFDTD ``dtype=uint32`` / ``LocationMonitoring=-1``
        ``OverflowError`` on Metal and other strict backends.

    Used in: step 05 notebook (Step 5c).

    Parameters
    ----------
    acoustic_file:
        Path to the skull ``DataForSim.h5`` from Step 5b.
    thermal_profile:
        List of dicts from the stimulation YAML ``AllDC_PRF_Duration`` key.
        Each dict must contain ``Duration``, ``DurationOff``, ``DC``, ``PRF``,
        ``Repetitions``, ``NumberGroupedSonications``, and
        ``PauseBetweenGroupedSonications``.  All seven keys are required —
        BabelBrain's CalculateThermalProcess accesses them without defaults.
    base_isppa:
        Baseline ISPPA in W/cm² (``BaseIsppa`` key in stimulation YAML).
    frequency:
        Centre frequency in Hz.
    tx_system:
        BabelBrain transducer identifier.
    backend:
        Computing backend string.
    device:
        Device name.
    reuse_files : bool
        Skip all combinations if every output file already exists.
    dry_run : bool
        Validate paths only; do not run the simulation.

    Returns
    -------
    str
        Path to the ``_AllCombinations.h5`` output file,
        or ``''`` when *dry_run* is ``True`` or the acoustic file is missing.

    Raises
    ------
    RuntimeError
        If the process errors or the output file is not found.
    """
    import os as _os
    import time as _time
    from multiprocessing import get_context as _get_context
    from pathlib import Path as _Path

    import numpy as _np
    from BabelViscoFDTD.H5pySimple import ReadFromH5py as _ReadFromH5py

    from BabelBrain.Babel_Thermal.CalculateThermalProcess import CalculateThermalProcess
    from ThermalModeling.CalculateTemperatureEffects import GetThermalOutName

    # spawn, matching domain/acoustic. BabelBrain starts its own nested Process
    # for the code that actually runs BHTE, using the global start method (spawn
    # on macOS), so this level must be spawn too -- a fork-context Queue handed
    # to a spawned grandchild is a context mismatch. The BabelViscoFDTD dtype fix
    # reaches every level because patch_babelvisco_BB() edits the file on disk.
    _mp_ctx = _get_context('spawn')

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
        'BaselineTemperature':           37.0,
        'LimitBHTEIterationsPerProcess': 100,
        'bForceHomogenousMedium':        False,
        'HomogenousMediumValues':        {},
        'bForceNoAbsorptionSkullScalp':  False,
        'sel_p':                         'p_amp',
    }

    Q = _mp_ctx.Queue()
    p = _mp_ctx.Process(
        target=CalculateThermalProcess,
        args=(Q, [acoustic_file], thermal_profile, {'DistanceConeToFocus': 0.0}),
        kwargs=kargs,
    )
    p.start()
    bNoError = _drain_queue_BB(p, Q)

    if not bNoError:
        raise RuntimeError('[5c] CalculateThermalProcess reported an error.')

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


# ===========================================================================
# Step 05-BB — QC visualisation
# ===========================================================================

_BB_DARK_BG   = '#1a1a1a'
_BB_DARK_CELL = '#2a2a2a'
_BB_CMAP_I    = 'inferno'
_BB_CMAP_T    = 'RdYlBu_r'


def _setup_ax_BB(ax):
    ax.set_facecolor(_BB_DARK_BG)
    ax.tick_params(colors='white', labelsize=7)
    for sp in ax.spines.values():
        sp.set_color('#555555')


def _tissue_contours_BB(ax, mat2d, x=None, y=None):
    """Overlay skull (grey) and skin (tan) contour lines.

    Parameters
    ----------
    ax : Axes
    mat2d : (nrows, ncols) array
        Tissue MaterialMap slice (already transposed to match imshow orientation).
    x : 1-D array, optional
        Column coordinate values (e.g. x_vec_mm or y_vec_mm). Must have
        length == mat2d.shape[1].  When provided together with ``y``, contours
        are drawn in physical units matching an ``imshow(..., extent=...)`` call.
    y : 1-D array, optional
        Row coordinate values (e.g. z_vec_mm). Must have length == mat2d.shape[0].
    """
    import numpy as _np
    _m = _np.array(mat2d)
    skull = ((_m == 2) | (_m == 3)).astype(float)
    skin  = (_m == 1).astype(float)
    _kw = dict(linewidths=1.5, alpha=0.9)
    if x is not None and y is not None:
        ax.contour(x, y, skull, levels=[0.5], colors=['#999999'], **_kw)
        ax.contour(x, y, skin,  levels=[0.5], colors=['#C8A064'], **_kw)
    else:
        ax.contour(skull, levels=[0.5], colors=['#999999'], **_kw)
        ax.contour(skin,  levels=[0.5], colors=['#C8A064'], **_kw)


def _crosshair_BB(ax, row, col, color='lime', lw=0.8, alpha=0.75):
    ax.axvline(col, color=color, lw=lw, alpha=alpha)
    ax.axhline(row, color=color, lw=lw, alpha=alpha)


def _add_colorbar_BB(fig, img, ax, label):
    cb = fig.colorbar(img, ax=ax, fraction=0.05, pad=0.02)
    cb.set_label(label, color='white', fontsize=8)
    cb.ax.tick_params(colors='white', labelsize=7)


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

    One flat ``figures/`` stopped scaling once six targets, both sides, several
    placements and more than one stimulation protocol were in play::

        figures/registration/        step-3 QC, one set per subject
        figures/{target}/            acoustic — depends on target and vertex
        figures/{target}/{stim}/     thermal  — also depends on the protocol

    The protocol directory drops the target token the stimulation YAML already
    carries, so ``aMCC_NeuroSynthTopic112/aMCC_offline_ErrorMonitoring`` becomes
    ``aMCC_NeuroSynthTopic112/offline_ErrorMonitoring``.

    Sides share a directory: ``_L`` / ``_R`` are already in every filename, and
    keeping them together makes the two easy to compare.

    Acoustic figures deliberately sit *above* the protocol level, because they
    do not depend on it — the same acoustic run feeds every thermal protocol,
    and filing a copy under each would invite them to drift apart.

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


def roi_overlap(acoustic_file: Path, main_lobe, roi_nii) -> dict:
    """How much of the target the focal lobe covers, and how much spills out.

    The ITRUSST practical guide (Murphy et al. 2025, Clin Neurophysiol
    171:192-226) gives no numeric tolerance for targeting error. What it gives
    is a criterion -- Fig. 21, "focal intensity is high within the structure and
    low in surrounding tissue" -- and a rule of thumb, that the smaller the
    target and the focus, the more accurate the targeting must be (3.3.1). It
    also warns that for small targets "the elongated focus of a single
    transducer is typically several centimeters and may extend considerably
    beyond the target structure, causing undesired off-target stimulation".

    Centroid offset alone does not express that criterion: a large target can be
    well covered with the centroid far off, and a small one poorly covered with
    the centroid close. These two do:

        coverage    fraction of the ROI inside the -3 dB focal volume
        off_target  fraction of the focal volume outside the ROI
        ceiling     the largest coverage physically available here,
                    min(1, FLHM volume / ROI volume) -- a single-element
                    transducer cannot cover a structure larger than its focus,
                    so coverage has to be read against this and not against 1.
                    For rHipp and cHipp (~4300-4800 mm3 per side against a
                    900-1400 mm3 focus) the ceiling is 20-30 %.
        efficiency  coverage / ceiling, i.e. the Szymkiewicz-Simpson overlap
                    coefficient |A n B| / min(|A|, |B|). 1.0 means the smaller
                    of the two volumes sits entirely inside the larger.

    Note the identity: whenever the focus is smaller than the ROI, efficiency
    reduces to 1 - off_target. It is reported anyway because ceiling is what
    makes coverage interpretable, and the two are read together.

    Mapping between grids: *_FullElasticSolution_Sub.nii.gz carries the affine
    for the simulation grid, and it applies to the z-FLIPPED index, the same
    nz-1-iz convention the rest of this file uses -- verified on sub-z004
    hippocampus, where [94, 94, 106] maps to [-20.9, 21.1, 13.9] against an ROI
    centroid of [-20.5, 21.4, 14.0]. The unflipped index lands 45 mm away.

    Both directions are computed sparsely, over ROI voxels and lobe voxels
    rather than the whole 13.8 M-voxel grid.
    """
    import numpy as np                                          # noqa: PLC0415
    import nibabel as nib

    sub = sorted(acoustic_file.parent.glob(
        acoustic_file.name.replace("_DataForSim.h5", "_FullElasticSolution_Sub.nii.gz")))
    if not sub or roi_nii is None:
        return {k: float("nan") for k in
                ("coverage", "off_target", "ceiling", "efficiency", "roi_mm3")}
    aff = nib.load(str(sub[0])).affine

    roi_img = nib.load(str(roi_nii))
    roi = np.squeeze(np.asanyarray(roi_img.dataobj)) > 0.5
    roi_idx = np.array(np.nonzero(roi)).T
    roi_ras = nib.affines.apply_affine(roi_img.affine, roi_idx.astype(float))

    # No z flip here. The affine already speaks the array's own index order:
    # main_lobe is indexed the way p_amp is stored, and the target sits at
    # nz-1-TargetLocation[2] = 107 in it, which is exactly what
    # inv(affine) @ ROI-centroid returns. Flipping again sent every ROI voxel to
    # ~279 and put the whole target outside the lobe -- coverage read 0 % on a
    # placement whose target point is demonstrably inside.
    sim = np.rint(nib.affines.apply_affine(np.linalg.inv(aff), roi_ras)).astype(int)
    ok = np.all((sim >= 0) & (sim < np.array(main_lobe.shape)[None, :]), axis=1)
    coverage = (float(main_lobe[sim[ok, 0], sim[ok, 1], sim[ok, 2]].sum())
                / max(len(roi_idx), 1))

    lobe_ras = nib.affines.apply_affine(
        aff, np.array(np.nonzero(main_lobe)).T.astype(float))
    back = np.rint(nib.affines.apply_affine(
        np.linalg.inv(roi_img.affine), lobe_ras)).astype(int)
    ok = np.all((back >= 0) & (back < np.array(roi.shape)[None, :]), axis=1)
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


def score_candidate(acoustic_file: Path, roi_nii=None) -> dict:
    """Spike-resistant focal metrics for one acoustic solve.

    The threshold is taken from the 99.99th percentile of in-brain intensity
    rather than its maximum: a reflection at a bone/brain interface can leave a
    single voxel above the focus, and half of that is then above the whole real
    lobe. See summarise_acoustic_BB, which reports both.
    """
    import numpy as np                                          # noqa: PLC0415
    from BabelViscoFDTD.H5pySimple import ReadFromH5py
    from scipy import ndimage

    d = ReadFromH5py(str(acoustic_file))
    p = np.asarray(d["p_amp"])
    mat = np.asarray(d["MaterialMap"])
    step = float(np.asarray(d["SpatialStep"]).ravel()[0]) * 1e3
    ix, iy, iz = (int(v) for v in np.asarray(d["TargetLocation"]).ravel())
    izf = p.shape[2] - 1 - iz          # p_amp is stored distal-first

    inten = (p**2) * (mat == 4)
    brain = inten[mat == 4]
    ref = float(np.percentile(brain[brain > 0], 99.99))
    lab, _ = ndimage.label(inten >= 0.5 * ref)
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    k = int(np.argmax(sizes))
    main = lab == k
    centre = np.array(ndimage.center_of_mass(main))
    out = {
        "lobe_mm3": float(sizes[k]) * step**3,
        "I_at_target": float(inten[ix, iy, izf] / ref),
        "target_inside": bool(main[ix, iy, izf]),
        "offset_mm": float(np.linalg.norm((centre - np.array([ix, iy, izf])) * step)),
        "focal_peak_outlier": float(brain.max() / ref),
    }
    out.update(roi_overlap(acoustic_file, main, roi_nii))
    return out


def write_vertices_explored(plantus_target_folder, adopted_vtx=None,
                            extra_column=None, filename="VERTICES_EXPLORED.md"):
    """Record every vertex solved for one target, as a markdown table beside it.

    The sweep prints its scores and they scroll away.  Only the adopted vertex
    keeps its BabelBrain output once the rest is cleared, so without this the
    reason a placement was chosen is lost with the fields it was chosen from.

    Every column comes from :func:`score_candidate` on the stored acoustic h5,
    so the table holds the sweep's own numbers rather than a re-derivation.
    Three earlier drafts of this record recomputed the metrics by hand and got
    the focal offset wrong twice -- once by measuring from the field maximum,
    where a single interface-reflection voxel outranks the focus.

    Used in: step 05.

    Parameters
    ----------
    plantus_target_folder:
        PlanTUS target folder, e.g. ``.../PlanTUS/sub-z002_CeA_CIT168_mask-R``.
        The record is written here, beside the vtx directories it describes.
    adopted_vtx:
        Vertex carried forward, marked in the table.
    extra_column:
        ``(heading, {vtx: value})`` for one further column, e.g. the share of
        the focus inside a containing structure.  Values are formatted as
        percentages.
    filename:
        Output name inside *plantus_target_folder*.

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
            "coverage", "ceiling", "efficiency", "off-target", "outlier"]
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
              "readable.  `outlier` at 1.5 or above means a single interface-reflection",
              "voxel outranks the focus and the row stops meaning much.", ""]

    out = folder / filename
    out.write_text("\n".join(lines))
    return out


def summarise_acoustic_BB(acoustic_file, fig_dir=None):
    """Print a summary table of the acoustic simulation output h5 file.

    Reads ``*DataForSim.h5`` produced by Step 5b and displays key simulation
    parameters, grid geometry, tissue composition, peak pressure values, and
    the extent of the focal region relative to the target.

    Targeting is judged on **where the −3 dB focal lobe sits** and **how large
    it is** — a lobe centred on the target is worthless if it is 90 mm long:

    - ``FLHM centroid → target (brain only)`` — reproduces the BabelBrain GUI's
      "Distance target to FLHM center" exactly.  Verified on sub-z002 vtx26749:
      GUI ``[1.1, 0.3, −0.7]`` mm, here ``[1.1, 0.3, −0.8]``.
    - ``Target I (norm to brain peak)`` — intensity at the target voxel as a
      fraction of the brain maximum.
    - ``−3 dB lobe axial extent (brain)`` — the lobe's depth interval, its
      length, and whether the target lies inside it.  Compare the length
      against the transducer's calibrated axial FLHM (DPX-500 at a 100 mm
      setting: 55 mm).
    - ``−3 dB lobe lateral width (brain)`` — the lobe's widest lateral extent.

    **The main lobe is the largest connected component above −3 dB**, following
    ``_BabelBaseTx.CalcVolumetricMetrics``.  Taking the component that contains
    the maximum instead — which this function used to do — reads a small distal
    hotspot as the focus whenever one marginally outpeaks the true lobe.  On
    sub-z002 vtx26749 that is a 51 mm³ blob against the far skull, and it
    reported the focus as 23.2 mm off when a 649 mm³ lobe was sitting on the
    target.  When the maximum falls outside the main lobe the volume row now
    says so explicitly.

    ``Off-target brain I`` uses the brain-restricted lobe; against the global
    lobe it degenerates to "all of brain" whenever the pressure maximum is in
    bone, which makes it equal to the brain peak and uninformative.

    Safety thresholds applied (colour coding):
      - Peak focus tissue       : green = Brain; orange = bone/skin
      - Peak I brain (norm)     : green ≥ 0.50; orange 0.25–0.50; red < 0.25
      - Target I (norm)         : green ≥ 0.75; orange 0.50–0.75; red < 0.50
      - −3 dB axial extent      : red when the target falls outside it
      - Off-target brain I      : green < 0.25 (−6 dB); orange 0.25–0.50; red ≥ 0.50
      - FLHM centroid → target  : green < 5 mm; orange 5–10 mm; red ≥ 10 mm
    Reference: Brinker et al. (2023) Brain Stimulation 16(3):856–871
               (ITRUSST TUS safety consensus); ISO/TS 63635:2022.

    Parameters
    ----------
    acoustic_file : str | Path
        Path to the ``*DataForSim.h5`` acoustic output from Step 5b.
        If the file does not exist, prints a warning and returns.
    fig_dir : str | Path | None, optional
        Directory to save the HTML summary table.  When provided, saves
        ``{stem}_acoustic_summary.html`` alongside the QC PNG.

    Used by: Step 05-BB (Step 5b summary cell).
    """
    import numpy as _np
    from scipy.ndimage import label as _label, center_of_mass as _com
    from IPython.display import HTML as _HTML, display as _display
    from BabelViscoFDTD.H5pySimple import ReadFromH5py

    # ── colour constants ──────────────────────────────────────────────
    _GREEN  = '#4caf50'
    _ORANGE = '#ff9800'
    _RED    = '#f44336'
    _WHITE  = '#ffffff'

    acoustic_file = str(acoustic_file)
    if not os.path.isfile(acoustic_file):
        print('[5b] DataForSim.h5 not found — run Step 5b first.')
        return

    ac  = ReadFromH5py(acoustic_file)
    p   = _np.array(ac['p_amp'])          # (nx, ny, nz)
    mat = _np.array(ac['MaterialMap'])    # 1=skin 2=cortical 3=trabec 4=brain
    tgt = _np.array(ac['TargetLocation']).astype(int)
    stp = float(ac['SpatialStep']) * 1e3  # mm

    nx, ny, nz = p.shape
    ix, iy, iz = tgt
    # p_amp and MaterialMap are flipped along z (index 0 = distal/brain side).
    # TargetLocation is stored as a pre-flip index, so convert before comparing
    # with any index derived from the flipped arrays.
    iz_f = nz - 1 - iz

    tissue_labels = {0: 'Water/Air', 1: 'Skin', 2: 'Cortical bone',
                     3: 'Trabecular bone', 4: 'Brain'}
    tissue_counts = {tissue_labels.get(t, str(t)): int((mat == t).sum())
                     for t in _np.unique(mat)}

    p2 = p ** 2
    I_norm = p2 / p2.max()
    brain_mask = (mat == 4)
    peak_brain_I = float(I_norm[brain_mask].max()) if brain_mask.any() else float('nan')

    # ── FLHM centroid: centre-of-mass of the half-maximum-intensity (−3 dB) region ───────
    # Threshold: I >= 0.5 × I_max  →  p >= p_max / √2.
    #
    # Computed twice, because the two answer different questions:
    #   whole domain — where the absolute pressure maximum sits.  If the skull
    #                  takes more pressure than the brain (common for deep
    #                  targets) this lobe lands in bone, which is what you want
    #                  to know for safety, but it says nothing about targeting.
    #   brain only   — where the therapeutic focus actually lands.  Thresholding
    #                  against the brain maximum instead of the global one is
    #                  what makes this meaningful: anchored to a bone hotspot,
    #                  the −3 dB region collapses to a few voxels in the skull
    #                  and the reported centroid/volume become nonsense.
    def _flhm_metrics(field, restrict=None, robust=False):
        """Return (centroid_str, volume_str, dist_mm, main_lobe_mask).

        Reproduces BabelBrain's own metric exactly — verified against the GUI
        on sub-z002 vtx26749: GUI [1.1, 0.3, −0.7] mm, here [1.1, 0.3, −0.8].
        See ``_BabelBaseTx.CalcVolumetricMetrics`` and
        ``_BabelBaseTx.CalculateDistancesTarget``:

        - threshold at 0.5 of the maximum *intensity* (−3 dB), i.e.
          ``p >= p_max / √2``, taken relative to the maximum inside *restrict*;
        - **main lobe = the largest connected component**, and
        - the sign convention is +z away from the transducer.

        The largest component matters.  Picking the component that *contains
        the maximum* instead reads a small distal hotspot as the focus whenever
        one marginally outpeaks the true lobe: on vtx26749 that is a 51 mm³
        blob against the far skull, 23.2 mm past a 649 mm³ lobe sitting on the
        target.  When the two differ the caller is warned rather than silently
        given one of them.
        """
        _f = field if restrict is None else _np.where(restrict, field, 0.0)
        _empty = _np.zeros(field.shape, dtype=bool)
        if not _np.isfinite(_f.max()) or _f.max() <= 0:
            return 'n/a', 'n/a', float('nan'), _empty
        # `robust` swaps the maximum for the 99.99th percentile as the level the
        # -3 dB threshold is taken from.  A reflection at a bone/brain interface
        # can put a single voxel well above the focus itself: for sub-z004 pmEC
        # left only ONE brain voxel is within 90 % of the maximum and half its
        # 27 neighbours are cortical bone, against 586 voxels sitting in pure
        # brain for the hippocampus placement.  Half of that outlier is then above
        # the whole real focus, so the largest component collapses to 0.3 mm3
        # and the field reads as having no focus at all -- when a 922 mm3 lobe
        # is plainly there.  A percentile ignores a lone outlier by
        # construction.
        _ref = (_np.percentile(_f[_f > 0], 99.99) if robust and (_f > 0).any()
                else _f.max())
        _over = (_f >= _ref / _np.sqrt(2))
        _lab, _n = _label(_over)
        if _n == 0:
            return 'n/a', 'n/a', float('nan'), _empty
        _sizes = _np.bincount(_lab.ravel())
        _sizes[0] = 0
        _main = (_lab == int(_np.argmax(_sizes)))
        _cx, _cy, _cz = _com(_main)
        _dx = (_cx - ix) * stp
        _dy = (_cy - iy) * stp
        # p_amp is stored distal-first, so depth decreases with index: negate to
        # get the GUI's "+z is deeper" sign.
        _dz = -(_cz - iz_f) * stp
        _dist = float(_np.sqrt(_dx**2 + _dy**2 + _dz**2))
        _nvox = int(_main.sum())
        _ntot = int(_over.sum())
        _vol = f'{_nvox * stp**3:.1f} mm³  ({_nvox} vox)'
        if _ntot != _nvox:
            _vol += (f'   |  all −3 dB: {_ntot * stp**3:.1f} mm³ ({_ntot} vox)'
                     f'  → main lobe is {100*_nvox/_ntot:.1f}% of it')
        # A maximum outside the main lobe is the case that used to be misread.
        _pk = _np.unravel_index(int(_np.argmax(_f)), _f.shape)
        if not _main[_pk]:
            _vol += ('   ⚠ the maximum lies in a *different*, smaller lobe '
                     f'{abs((_pk[2] - _cz) * stp):.0f} mm away — a hotspot, '
                     'not the focus')
        return (f'[{_dx:.1f}, {_dy:.1f}, {_dz:.1f}] mm'
                f'  (dist={_dist:.1f} mm from target)',
                _vol, _dist, _main)

    (_flhm_centroid_str, _flhm_vol_str,
     _dist_flhm, _main_mask) = _flhm_metrics(p)
    (_flhm_br_centroid_str, _flhm_br_vol_str,
     _dist_flhm_br, _main_mask_br) = _flhm_metrics(p, restrict=brain_mask)
    (_flhm_rb_centroid_str, _flhm_rb_vol_str,
     _dist_flhm_rb, _main_mask_rb) = _flhm_metrics(p, restrict=brain_mask,
                                                   robust=True)

    # How far the maximum stands above the rest of the brain field. Near 1 the
    # peak is the focus; the five EC placements where the metric broke sit at
    # 1.9-2.8, the intact ones at 1.15-1.23.
    _pb = (p**2)[brain_mask]
    _outlier = (float(_pb.max() / _np.percentile(_pb, 99.99))
              if _pb.size and _np.percentile(_pb, 99.99) > 0 else float('nan'))

    # ── Off-target brain: peak I in brain outside the *brain* focal volume ─
    # Uses the brain-restricted lobe: with the global lobe this degenerates to
    # "all of brain" whenever the pressure maximum is in bone, making the value
    # identical to the brain peak and therefore uninformative.
    _off_brain_mask = brain_mask & ~_main_mask_br
    if _off_brain_mask.any():
        _off_brain_I = float(I_norm[_off_brain_mask].max())
    else:
        _off_brain_I = float('nan')

    # ── Focal extent: the −3 dB region as a *range*, not a point ──────────
    # A centroid is only meaningful when the field has one compact focus.  For
    # a long, low-f-number beam the axial profile is nearly flat over tens of
    # mm, so whichever voxel happens to hold the maximum moves the centroid by
    # that whole length and the "distance to target" reads like a gross
    # mis-aim when the target is in fact well inside the focal region.
    # Measured on sub-z002 vtx26749: centroid → target = 23.2 mm, yet the
    # target sits at 79% of the brain peak intensity and 24 mm inside the
    # −3 dB span.  The range answers the question the centroid cannot.
    _depth = lambda _i: (nz - 1 - _i) * stp     # mm from the proximal face

    _Ib = _np.where(brain_mask, p, 0.0) ** 2
    if _main_mask_br.any() and _Ib.max() > 0:
        _tgt_I_rel = float(_Ib[ix, iy, iz_f] / _Ib.max())
        _inside    = bool(_main_mask_br[ix, iy, iz_f])
        _zs = _np.where(_main_mask_br.any(axis=(0, 1)))[0]
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
        _axial_str = (f'{_d_near:.1f} – {_d_far:.1f} mm from skin '
                      f'({_d_far - _d_near:.1f} mm long); target at {_d_tgt:.1f} mm '
                      f'{"✓ inside" if _inside else "⚠ OUTSIDE"}{_clip}')
        _xs, _ys, _ = _np.where(_main_mask_br)
        _lat = (max(_xs.max() - _xs.min(), _ys.max() - _ys.min()) + 1) * stp
        _lat_str = f'{_lat:.1f} mm  (widest lateral extent of the lobe)'
    else:
        _tgt_I_rel = float('nan')
        _inside    = False
        _axial_str = _lat_str = 'n/a'

    # Peak focus voxel location & tissue
    peak_idx = _np.unravel_index(_np.argmax(p2), p.shape)
    px, py, pz = peak_idx
    peak_tissue = tissue_labels.get(int(mat[px, py, pz]), 'Unknown')
    # Distance from target to focus
    dist_to_tgt = float(_np.sqrt(((px-ix)*stp)**2 + ((py-iy)*stp)**2 + ((pz-iz_f)*stp)**2))

    # ── colour helpers ────────────────────────────────────────────────
    def _c_tissue(t):
        return _GREEN if t == 'Brain' else _ORANGE

    def _c_brain_I(v):
        if _np.isnan(v): return _WHITE
        return _GREEN if v >= 0.50 else (_ORANGE if v >= 0.25 else _RED)

    def _c_off_brain(v):
        if _np.isnan(v): return _WHITE
        return _GREEN if v < 0.25 else (_ORANGE if v < 0.50 else _RED)

    def _c_dist(v):
        if _np.isnan(v): return _WHITE
        return _GREEN if v < 5 else (_ORANGE if v < 10 else _RED)

    def _c_tgt_I(v):
        if _np.isnan(v): return _WHITE
        return _GREEN if v >= 0.75 else (_ORANGE if v >= 0.50 else _RED)

    # rows: (label, value_str, colour)
    rows_grid = [
        ('Grid (vox)',           f'{nx} × {ny} × {nz}',                                          _WHITE),
        ('Spatial step',         f'{stp:.4f} mm',                                                 _WHITE),
        ('Domain size',          f'{nx*stp:.1f} × {ny*stp:.1f} × {nz*stp:.1f} mm',              _WHITE),
        ('Target voxel',         f'[{ix}, {iy}, {iz}]',                                          _WHITE),
        ('Target position',      f'[{ix*stp:.1f}, {iy*stp:.1f}, {iz*stp:.1f}] mm',              _WHITE),
        ('Peak p_amp',           f'{p.max():.4f} Pa',                                             _WHITE),
        ('Peak focus voxel',     f'[{px}, {py}, {pz}]',                                          _WHITE),
        ('Peak focus position',  f'[{px*stp:.1f}, {py*stp:.1f}, {pz*stp:.1f}] mm',              _WHITE),
        ('Peak focus tissue',
         f'⚠ {peak_tissue}' if peak_tissue != 'Brain' else f'✓ {peak_tissue}',
         _c_tissue(peak_tissue)),
        ('Peak→target dist',     f'{dist_to_tgt:.1f} mm   ← absolute pressure peak; bone if skull blocks', _WHITE),
        ('Peak I (norm)',         '1.000 (focus)',                                                 _WHITE),
        ('Peak I brain',
         f'{peak_brain_I:.4f}  (norm)  ← green ≥ 0.50 | orange 0.25–0.50 | red < 0.25',
         _c_brain_I(peak_brain_I)),
        ('Off-target brain I',
         (f'{_off_brain_I:.4f}  (norm)  ← green < 0.25 | orange 0.25–0.50 | red ≥ 0.50'
          if not _np.isnan(_off_brain_I) else 'n/a'),
         _c_off_brain(_off_brain_I)),
        # ── Where the focal lobe sits, and how big it is ──────────────────
        # The centroid says where; the extent says how selective.  Report both:
        # a lobe centred on the target is worthless if it is 90 mm long.
        ('Target I (norm to brain peak)',
         (f'{_tgt_I_rel:.3f}   ← green ≥ 0.75 | orange 0.50–0.75 | red < 0.50'
          if not _np.isnan(_tgt_I_rel) else 'n/a'),
         _c_tgt_I(_tgt_I_rel)),
        ('−3 dB lobe axial extent (brain)', _axial_str,
         _WHITE if _inside else _RED),
        ('−3 dB lobe lateral width (brain)', _lat_str, _WHITE),
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
         _c_dist(_dist_flhm)),
        ('FLHM volume (−3 dB I, whole domain)', _flhm_vol_str,                                   _WHITE),
        # Brain-only FLHM: thresholded against the brain maximum rather than
        # the global one.  This is the row that reproduces the GUI.
        ('FLHM centroid → target (brain only, ≈GUI)',
         _flhm_br_centroid_str,
         _c_dist(_dist_flhm_br)),
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
         _c_dist(_dist_flhm_rb)),
        ('FLHM volume (−3 dB I, brain, outlier-resistant)', _flhm_rb_vol_str,   _WHITE),
    ]
    rows_tis = [(lbl, f'{cnt:,} vox  ({100*cnt/mat.size:.1f}%)', _WHITE)
                for lbl, cnt in tissue_counts.items()]

    _ref = (
        '<p style="font-family:monospace;font-size:11px;color:#888;margin-top:6px;">'
        'Colour thresholds: Brinker et al. (2023) <i>Brain Stimulation</i> 16(3):856–871 '
        '(ITRUSST TUS safety consensus); ISO/TS 63635:2022.'
        '</p>'
    )

    def _tbl(title, rows):
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

    _html_body = (
        f'<h4 style="color:#aaddff;font-family:monospace;">Acoustic simulation summary'
        f' — {Path(acoustic_file).name}</h4>'
        + _tbl('Grid & simulation geometry', rows_grid)
        + '<br>'
        + _tbl('Tissue composition (MaterialMap)', rows_tis)
        + _ref
    )

    _display(_HTML(_html_body))

    if fig_dir is not None:
        _fig_dir = Path(fig_dir)
        _fig_dir.mkdir(parents=True, exist_ok=True)
        _stem = Path(acoustic_file).name.replace('_DataForSim.h5', '')
        _html_path = _fig_dir / f'{_stem}_acoustic_summary.html'
        # Definitions travel inside the file, not as a link to one. This HTML
        # gets moved -- attached to mail, dropped in a report folder, opened on
        # another machine -- and an absolute file:// path into the repo breaks
        # the moment it leaves this filesystem. Collapsed by default so the
        # table stays the first thing seen.
        _defs = [
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
        _rows = ''.join(
            f'<dt style="color:#e0e0e0;font-weight:600;margin-top:8px">{k}</dt>'
            f'<dd style="margin:2px 0 0 16px">{v}</dd>' for k, v in _defs)
        _foot = (
            '<details style="color:#9e9e9e;font:12px/1.5 sans-serif;'
            'margin-top:18px;max-width:820px">'
            '<summary style="cursor:pointer;color:#64b5f6">'
            'How to read these rows</summary>'
            f'<dl>{_rows}</dl>'
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
        _full_html = (
            '<!doctype html><html><head>'
            '<meta charset="utf-8">'
            '<style>body{background:#121212;margin:16px;}</style>'
            '</head><body>'
            + _html_body
            + _foot
            + '</body></html>'
        )
        _html_path.write_text(_full_html, encoding='utf-8')
        print(f'[QC] Acoustic summary saved → {_html_path.name}')


def plot_acoustic_qc_BB(acoustic_file, fig_dir, ID, tx_system, frequency, ppw,
                        roi_nii=None):
    """Plot normalised acoustic intensity QC figure and save as PNG.

    Produces a 2-panel figure (sagittal + coronal planes through the target)
    matching the BabelBrain GUI plot style (``_BabelBaseTx.UpdateAcResults``):

    * ``contourf`` with levels ``[0.1, 0.2, …, 1.0]`` and ``cmap=jet``
    * Tissue boundaries from remapped MaterialMap via ``contour([0,1,2])``
      drawn as black dotted lines
    * Air-pocket overlay (grey, when present in simulation domain)
    * Equal-aspect axes with Z increasing downward (``invert_yaxis``)
    * Target crosshair marker ``'+k'`` (markersize 18)

    Parameters
    ----------
    acoustic_file : str | Path
        Path to the ``*DataForSim.h5`` acoustic output from Step 5b.
    fig_dir : str | Path
        Directory where the PNG will be saved (created if absent).
    ID : str
        Label used in the filename and figure title.
    tx_system : str
        BabelBrain transducer identifier (e.g. ``'DPX_500'``).
    frequency : float
        Transducer centre frequency in Hz.
    ppw : int
        Points-per-wavelength used for the simulation.
    roi_nii : str | Path | None, optional
        Native-space ROI NIfTI from Step 3.  When provided the ROI outline
        is overlaid as a cyan contour on both panels.

    Returns
    -------
    str
        Absolute path to the saved PNG file.

    Used by: Step 05-BB (QC cell).
    """
    import numpy as _np
    import matplotlib.pyplot as _plt
    from IPython.display import Image as _IPImage, display as _display

    # Lazy import of BabelBrain h5 reader — bb_dir must already be on sys.path
    from BabelViscoFDTD.H5pySimple import ReadFromH5py

    acoustic_file = str(acoustic_file)
    fig_dir = Path(fig_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)

    if not os.path.isfile(acoustic_file):
        print('[QC] Acoustic file not found — run Step 5b first.')
        return ''

    ac  = ReadFromH5py(acoustic_file)
    # p_amp and MaterialMap are stored z-flipped in the h5 (index 0 = distal/brain).
    # z_vec is NOT flipped (index 0 = proximal/skin).  Unflip before plotting so
    # the intensity field aligns with the z coordinate axis.
    p   = _np.flip(_np.array(ac['p_amp']), axis=2)        # (nx, ny, nz) — unflipped
    mat = _np.flip(_np.array(ac['MaterialMap']), axis=2)   # unflipped
    tgt = _np.array(ac['TargetLocation']).astype(int)      # [ix, iy, iz] — pre-flip index = unflipped index
    stp = float(ac['SpatialStep']) * 1e3        # mm

    # Coordinate vectors (metres → mm)
    x_mm = _np.array(ac['x_vec']) * 1e3        # (nx,)
    y_mm = _np.array(ac['y_vec']) * 1e3        # (ny,)
    z_mm = _np.array(ac['z_vec']) * 1e3        # (nz,)

    ix, iy, iz = tgt
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

    # ── Optional: resample ROI mask onto simulation grid ─────────────────
    roi_3d = None
    if roi_nii and os.path.isfile(str(roi_nii)):
        try:
            import nibabel as _nib
            from nilearn.image import resample_img as _resample_img
            _roi_img = _nib.load(str(roi_nii))
            _sim_affine = _np.array(ac['affine'])
            _roi_rs = _resample_img(_roi_img, target_affine=_sim_affine,
                                    target_shape=p.shape, interpolation='nearest')
            roi_3d = (_roi_rs.get_fdata() > 0.5).astype(float)
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


def placement_metrics_BB(m2m_dir, sub_id_full, target_name, target_side,
                         tx_cfg, vtx, ppw=6):
    """Collect every step-5 number for one placement, as a flat dict.

    Used in: step 05 (QC), by :func:`compare_placements_BB`.

    Acoustic figures are parsed from :func:`summarise_acoustic_BB`'s own HTML so
    the definitions cannot drift from the pipeline; thermal comes from the
    ``_AllCombinations.h5`` and the derating/TPO numbers from the
    ``_Summary.csv``.  Returns ``None`` when the placement has no acoustic run.
    """
    import glob as _glob
    import html as _html
    import re as _re
    import tempfile as _tempfile

    import numpy as _np
    from BabelViscoFDTD.H5pySimple import ReadFromH5py as _Read

    m2m_dir = Path(m2m_dir)
    tx      = tx_cfg['babelbrain_id']
    khz     = int(tx_cfg['frequency_kHz'])
    ID      = f'{stem_for(sub_id_full, target_name, target_side)}_vtx{vtx}'
    prefix  = f'{ID}_{tx}_{khz}kHz_{ppw}PPW_'
    acoustic = m2m_dir / f'{prefix}DataForSim.h5'
    if not acoustic.is_file():
        return None

    folder = find_plantus_target_folder(m2m_dir, sub_id_full, target_name, target_side)
    out = {'vtx': vtx, 'ID': ID, 'prefix': prefix, 'acoustic': acoustic}

    # ── placement geometry ────────────────────────────────────────────────
    pl = {r['vtx']: r for r in list_plantus_vertices(folder, print_table=False)}
    out.update({k: pl.get(vtx, {}).get(k) for k in
                ('entry', 'side', 'angle_deg', 'skin_skull_deg',
                 'inter_mm', 'inter_near_mm')})
    try:
        out['depth_mm'] = read_depth_report(folder, vtx=vtx)[
            'exit_plane_to_ROI_distance_mm']
    except Exception:
        out['depth_mm'] = float('nan')

    # ── acoustic, via summarise_acoustic_BB's table ───────────────────────
    with _tempfile.TemporaryDirectory() as td:
        summarise_acoustic_BB(str(acoustic), fig_dir=td)
        _f = sorted(_glob.glob(td + '/*acoustic_summary.html'),
                    key=os.path.getmtime)[-1]
        doc = open(_f).read()
    rows = {}
    for tr in _re.findall(r'<tr.*?</tr>', doc, _re.S):
        cs = [_html.unescape(_re.sub(r'<[^>]+>', '', c)).strip()
              for c in _re.findall(r'<t[dh].*?</t[dh]>', tr, _re.S)]
        cs = [c for c in cs if c]
        if len(cs) >= 2:
            rows[cs[0]] = ' '.join(cs[1:])

    def _num(s):
        m = _re.search(r'-?\d+\.?\d*', s or '')
        return float(m.group()) if m else float('nan')

    out['peak_tissue']  = rows.get('Peak focus tissue', '').replace('⚠', '') \
                                                           .replace('✓', '').strip()
    out['peak_I_brain'] = _num(rows.get('Peak I brain'))
    out['off_brain']    = _num(rows.get('Off-target brain I'))
    # Targeting, as a range — see summarise_acoustic_BB for why the centroid
    # distance below is a diagnostic and not the measure to rank placements on.
    out['tgt_I'] = _num(rows.get('Target I (norm to brain peak)'))
    _ax = rows.get('−3 dB lobe axial extent (brain)', '')
    _m  = _re.search(r'([\d.]+) – ([\d.]+) mm from skin \(([\d.]+) mm long\); '
                     r'target at ([\d.]+) mm', _ax)
    out['ax_near'], out['ax_far'], out['ax_len'], out['ax_tgt'] = (
        [float(_m.group(i)) for i in (1, 2, 3, 4)] if _m else [float('nan')] * 4)
    out['ax_inside']  = 'inside' in _ax
    out['ax_clipped'] = 'brain boundary' in _ax
    out['lat_width']  = _num(rows.get('−3 dB lobe lateral width (brain)'))
    _br = rows.get('FLHM centroid → target (brain only, ≈GUI)', '')
    out['flhm_dist'] = (float(_re.search(r'dist=([\d.]+)', _br).group(1))
                        if 'dist=' in _br else float('nan'))
    _bv = rows.get('FLHM volume (−3 dB I, brain only)', '')
    out['flhm_vol']  = _num(_bv)
    out['flhm_frag'] = (float(_re.search(r'main lobe is ([\d.]+)%', _bv).group(1))
                        if 'main lobe is' in _bv else 100.0)

    # ── thermal ───────────────────────────────────────────────────────────
    th = m2m_dir / f'{prefix}DataForSim-ThermalField_AllCombinations.h5'
    out['thermal'] = th if th.is_file() else None
    for k in ('t_brain', 't_skin', 't_skull', 't_target',
              'cem_brain', 'cem_skin', 'cem_skull', 'mi'):
        out[k] = float('nan')
    if th.is_file():
        D = _Read(str(th))
        _g = lambda k: (float(_np.asarray(D[k]).ravel()[0])
                        if k in D else float('nan'))
        out['cem_brain'], out['cem_skin'], out['cem_skull'] = (
            _g('CEMBrain'), _g('CEMSkin'), _g('CEMSkull'))
        c0 = D['AllData'][0] if D.get('AllData') else {}
        tp_ = _np.asarray(c0.get('TempProfileTarget', [_np.nan])).ravel()
        out['t_target'] = float(_np.nanmax(tp_)) if tp_.size else float('nan')
        if 'MI' in c0:
            out['mi'] = float(_np.asarray(c0['MI']).ravel()[0])

    # ── derating / TPO ────────────────────────────────────────────────────
    out['derating'] = out['req_isppa'] = out['req_ispta'] = float('nan')
    cs_ = m2m_dir / f'{prefix}DataForSim-ThermalField_Summary.csv'
    if cs_.is_file():
        import csv as _csv
        row = next(iter(_csv.DictReader(open(cs_))), {})
        for src, dst in (('derating_ratio', 'derating'),
                         ('required_freefield_isppa_w_cm2', 'req_isppa'),
                         ('required_freefield_ispta_w_cm2', 'req_ispta')):
            try:
                out[dst] = float(row.get(src, 'nan'))
            except ValueError:
                pass
    return out


def compare_placements_BB(m2m_dir, sub_dir, sub_id_full, target_name, target_side,
                          tx_cfg, vtx_list, cut_coords, stim_label=None,
                          ppw=6, roi_nii=None, out_name=None):
    """Side-by-side PDF comparing placements: acoustic, thermal and metrics.

    Used in: step 05 (QC), to choose between placements and to share the result.

    One column per vertex, so rows line up: the acoustic view at *cut_coords*,
    the thermal QC figure, and every number from :func:`placement_metrics_BB`.
    All columns are cut at the **same** coordinates — pass the target location, or
    the comparison shows different anatomy per column and means nothing.

    The acoustic panel is rendered here; the thermal panel is the QC PNG already
    written by :func:`plot_thermal_qc_BB`, embedded so the shared document cannot
    disagree with the figures already reviewed.

    Parameters
    ----------
    m2m_dir, sub_dir : Path | str
        Subject's ``m2m_*`` directory and its parent (figures go in
        ``sub_dir/'figures'``).
    vtx_list : sequence of int
        Vertices to compare, left to right.
    cut_coords : tuple of float
        ``(x, y, z)`` in native RAS mm — normally the target.
    stim_label : str or None
        Stimulation label used in the thermal PNG name, e.g.
        ``'hippocampus_offline_Pan2025'``.
    roi_nii : str | Path | None
        ROI mask; drawn as a cyan contour on the acoustic panels.
    out_name : str or None
        PDF filename.  Defaults to
        ``{sub}_{target}{side}_placement_comparison.pdf``.

    Returns
    -------
    tuple of (Path or None, list of dict)
        PDF path and the per-vertex metrics.
    """
    import matplotlib.pyplot as _plt
    import nibabel as _nib
    from nilearn import plotting as _plotting

    m2m_dir, sub_dir = Path(m2m_dir), Path(sub_dir)
    # Same layout run_babelbrain writes into: acoustic above the protocol,
    # thermal under it.  See fig_dir_for().
    fig_dir = fig_dir_for(sub_dir, target_name)
    fig_dir_thermal = fig_dir_for(sub_dir, target_name, stim_label) if stim_label \
        else fig_dir
    t1 = m2m_dir / 'T1.nii.gz'
    x, y, z = (float(c) for c in cut_coords)

    mets = []
    for v in vtx_list:
        m = placement_metrics_BB(m2m_dir, sub_id_full, target_name, target_side,
                                 tx_cfg, v, ppw=ppw)
        if m is None:
            print(f'[compare] vtx{v}: no acoustic run — skipped.')
            continue
        mets.append(m)
    if not mets:
        print('[compare] Nothing to compare.')
        return None, []

    n = len(mets)
    fig = _plt.figure(figsize=(9.0 * n, 20.0), facecolor='white')
    gs  = fig.add_gridspec(4, n, height_ratios=[1.55, 1.05, 1.25, 1.30],
                           hspace=0.16, wspace=0.06)

    for j, m in enumerate(mets):
        # ── beam-aligned field, exactly as the BabelBrain GUI draws it ────
        # Kept as the first row because it is the view that can be checked
        # against the GUI directly; the anatomical ortho below it is the same
        # data in native T1 space and the two look nothing alike.
        axg = fig.add_subplot(gs[0, j])
        axg.axis('off')
        _gp = save_acoustic_gui_BB(m['acoustic'], fig_dir=fig_dir, title='')
        if _gp is not None and Path(_gp).is_file():
            axg.imshow(_plt.imread(str(_gp)))
        axg.set_title(f"vtx{m['vtx']}  —  beam-aligned (BabelBrain GUI view)",
                      fontsize=11)

        # ── acoustic at the shared cut ────────────────────────────────────
        ax = fig.add_subplot(gs[1, j])
        ax.set_facecolor('black')
        disp = _plotting.plot_stat_map(
            str(m['acoustic']).replace('_DataForSim.h5',
                                       '_FullElasticSolution_Sub_NORM.nii.gz'),
            bg_img=str(t1), cut_coords=(x, y, z), display_mode='ortho',
            threshold=0.05, cmap='jet', vmax=1.0, colorbar=True,
            black_bg=True, axes=ax,
            title=f"vtx{m['vtx']}  —  p/p_max @ x={x:.0f} y={y:.0f} z={z:.0f}")
        if roi_nii and os.path.isfile(str(roi_nii)):
            disp.add_contours(str(roi_nii), levels=[0.5], colors='cyan',
                              linewidths=1.2)

        # ── thermal: embed the QC figure already produced ─────────────────
        axt = fig.add_subplot(gs[2, j])
        axt.axis('off')
        _sp  = f'_{stim_label}' if stim_label else ''
        _png = fig_dir_thermal / f"{m['ID']}{_sp}_combo01_thermal_qc.png"
        if _png.is_file():
            axt.imshow(_plt.imread(str(_png)))
        else:
            axt.text(0.5, 0.5, f'thermal QC figure not found:\n{_png.name}',
                     ha='center', va='center', fontsize=9, color='#aa0000')

        # ── numbers ───────────────────────────────────────────────────────
        axn = fig.add_subplot(gs[3, j])
        axn.axis('off')

        def f(v, p=1, unit=''):
            import math
            return ('—' if v is None or (isinstance(v, float) and math.isnan(v))
                    else f'{v:.{p}f}{unit}')

        e = m.get('entry')
        lines = [
            ('PLACEMENT', ''),
            ('entry (x, y, z)', f'{e[0]:.0f}, {e[1]:.0f}, {e[2]:.0f}' if e else '—'),
            ('side',            m.get('side') or '—'),
            ('exit plane → ROI', f(m.get('depth_mm'), 1, ' mm')),
            ('aim angle (scalp normal → target)', f(m.get('angle_deg'), 1, '°')),
            ('skin–skull angle (obliquity on bone)',
             f(m.get('skin_skull_deg'), 1, '°')),
            ('ROI axis clip / ≤5 mm',
             f"{f(m.get('inter_mm'), 2)} / {f(m.get('inter_near_mm'), 2)} mm"),
            ('', ''),
            ('ACOUSTIC — where the focus is', ''),
            ('FLHM centroid → target (=GUI)', f(m.get('flhm_dist'), 1, ' mm')),
            ('I at target (norm to brain peak)', f(m.get('tgt_I'), 3)),
            ('target inside the −3 dB lobe', 'yes' if m.get('ax_inside') else 'NO'),
            ('', ''),
            ('ACOUSTIC — how selective', ''),
            ('−3 dB lobe axial span',
             (f"{f(m.get('ax_near'), 1)} – {f(m.get('ax_far'), 1)} mm"
              + ('  (clipped)' if m.get('ax_clipped') else ''))),
            ('−3 dB lobe axial length', f(m.get('ax_len'), 1, ' mm')),
            ('−3 dB lobe lateral width', f(m.get('lat_width'), 1, ' mm')),
            ('FLHM volume',             f(m.get('flhm_vol'), 1, ' mm³')),
            ('main lobe of −3 dB',      f(m.get('flhm_frag'), 0, ' %')),
            ('peak I in brain (norm)',  f(m.get('peak_I_brain'), 3)),
            ('off-target brain I',      f(m.get('off_brain'), 3)),
            ('pressure max in',         m.get('peak_tissue') or '—'),
            ('', ''),
            ('DOSE / DEVICE', ''),
            ('derating (in-situ / free-field)', f(m.get('derating'), 4)),
            ('required free-field ISPPA', f(m.get('req_isppa'), 1, ' W/cm²')),
            ('required free-field ISPTA', f(m.get('req_ispta'), 1, ' W/cm²')),
            ('', ''),
            ('THERMAL', ''),
            ('T at target',   f(m.get('t_target'), 3, ' °C')),
            ('CEM43 brain',   f(m.get('cem_brain'), 4)),
            ('CEM43 skin / skull',
             f"{f(m.get('cem_skin'), 4)} / {f(m.get('cem_skull'), 4)}"),
            ('MI',            f(m.get('mi'), 2)),
        ]
        yy = 0.99
        for k, v in lines:
            if k and not v:                      # section heading
                yy -= 0.012
                axn.text(0.0, yy, k, transform=axn.transAxes, fontsize=10.5,
                         fontweight='bold', va='top', color='#333333')
            elif k:
                axn.text(0.0, yy, k, transform=axn.transAxes, fontsize=10,
                         va='top', color='#555555')
                axn.text(1.0, yy, v, transform=axn.transAxes, fontsize=10,
                         va='top', ha='right', color='#000000')
            yy -= 0.040

    fig.suptitle(f'{sub_id_full} — {target_name}{target_side} — placement comparison'
                 f'   (all panels cut at the target: '
                 f'x={x:.0f} y={y:.0f} z={z:.0f})',
                 fontsize=13, fontweight='bold', y=0.995)

    if out_name is None:
        out_name = f'{sub_id_full}_{target_name}{target_side}_placement_comparison.pdf'
    out = fig_dir / out_name
    fig.savefig(out, bbox_inches='tight', facecolor='white')
    _plt.close(fig)
    print(f'[compare] {len(mets)} placement(s) → {out.name}')
    return out, mets


def save_acoustic_ortho_BB(acoustic_file, t1_path, cut_coords, fig_dir,
                           roi_nii=None, title=None, suffix=None, dpi=200):
    """Save the interactive viewer's orthogonal view as a static figure.

    Used in: step 05 (QC), after finding a position in
    :func:`view_acoustic_interactive_BB`.

    The nilearn HTML viewer has no way to export the view it is showing.  This
    renders the same overlay — the same ``*_FullElasticSolution_Sub_NORM.nii.gz``,
    threshold and colour scale — at coordinates you choose, so read
    ``x = … y = … z = …`` off the interactive viewer and pass them here.

    Parameters
    ----------
    acoustic_file : str | Path
        ``*DataForSim.h5`` from Step 5b; the NORM NIfTI is found beside it.
    t1_path : str | Path
        Native T1 used as the background.
    cut_coords : tuple of float
        ``(x, y, z)`` in native RAS mm, as displayed by the interactive viewer.
    fig_dir : str | Path
        Where to write the PNG.
    roi_nii : str | Path | None
        Target mask from Step 3; drawn as a contour when given, so the focus can
        be judged against the ROI rather than by eye.
    suffix : str or None
        Filename suffix.  ``None`` (default) builds it from the coordinates —
        ``ortho_x7y29z46`` — so several positions coexist instead of overwriting,
        and the filename says which slice it is.  Because *stem* comes from the
        acoustic file, the vertex is already in the name whenever the run was
        ``VTX``-namespaced, matching the other per-vertex outputs.
    dpi : int
        Output resolution.

    Returns
    -------
    Path or None
        The PNG written, or ``None`` if the NORM NIfTI is missing.
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

    fig = _plt.figure(figsize=(12, 4.2))
    # threshold/cmap/vmax mirror view_acoustic_interactive_BB so the static
    # figure and the interactive viewer cannot disagree.
    disp = _plotting.plot_stat_map(
        _nib.load(norm_nii),
        bg_img=_nib.load(str(t1_path)),
        cut_coords=(x, y, z),
        display_mode='ortho',
        threshold=0.05,
        cmap='jet',
        vmax=1.0,
        colorbar=True,
        black_bg=True,
        title=title,
        figure=fig,
    )
    if roi_nii and os.path.isfile(str(roi_nii)):
        disp.add_contours(str(roi_nii), levels=[0.5], colors='cyan',
                          linewidths=1.2)

    fig_dir = Path(fig_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)
    out = fig_dir / f'{stem}_{suffix}.png'
    fig.savefig(out, dpi=dpi, bbox_inches='tight', facecolor='black')
    _plt.close(fig)
    print(f'[ortho] Saved → {out.name}   (x={x:.0f} y={y:.0f} z={z:.0f})')
    return out


def save_acoustic_gui_BB(acoustic_file, fig_dir=None, distance_to_target=None,
                         show_water=False, title=None, suffix=None, dpi=200):
    """Reproduce the BabelBrain GUI's Step-2 "Ac Sim" figure, offline.

    A line-by-line port of ``_BabelBaseTx.UpdateAcResults`` in the BabelBrain
    source, so the saved PNG is the same plot the GUI draws: same field, same
    normalisation, same contour levels, same colormap, same axes.

    This is **beam-aligned** and is not comparable to
    :func:`save_acoustic_ortho_BB`, which plots native T1 anatomical space.
    Here Z is depth along the beam measured from the skin, X and Y are lateral
    offsets from the target, the black dotted lines are tissue boundaries from
    ``MaterialMap`` and the ``+`` marks the target.  A figure that "looks
    different from the notebook" is usually just these two conventions.

    What the GUI does, and therefore what this does:

    - intensity ``I = p²/(2ρc)`` using the per-voxel density and sound speed
      from ``Material``, **not** ``p²`` alone;
    - everything outside brain zeroed, then normalised to the brain maximum;
    - filled contours at 0.1, 0.2 … 1.0 of that maximum, ``jet``;
    - the two panels are the X–Z and Y–Z planes through the target.

    Parameters
    ----------
    acoustic_file : str | Path
        ``*DataForSim.h5`` from Step 5b.
    fig_dir : str | Path | None
        Where to write the PNG.  Returns the figure without saving if None.
    distance_to_target : float | None
        Skin-to-target distance in mm, used to label the Z axis exactly as the
        GUI's own widget value does.  Defaults to the distance measured from
        ``MaterialMap`` along the beam column, which can differ from the GUI's
        planning value by a voxel or so; it shifts the Z labels only, never the
        field.
    show_water : bool
        Plot the water-only companion run (``*Water_DataForSim.h5``) instead —
        the GUI's "Show water results" checkbox.  This is the free-field
        reference: it shows where the focus would be with no skull.
    """
    import numpy as _np
    import matplotlib.pyplot as _plt
    from BabelViscoFDTD.H5pySimple import ReadFromH5py

    acoustic_file = str(acoustic_file)
    if not os.path.isfile(acoustic_file):
        print('[gui-fig] DataForSim.h5 not found — run Step 5b first.')
        return None

    Skull = ReadFromH5py(acoustic_file)
    src   = Skull
    if show_water:
        wf = acoustic_file.replace('_DataForSim.h5', '_Water_DataForSim.h5')
        if not os.path.isfile(wf):
            print(f'[gui-fig] water companion not found: {Path(wf).name}')
            return None
        src = ReadFromH5py(wf)

    # The GUI flips p_amp and MaterialMap along z so index 0 is the skin side.
    p   = _np.ascontiguousarray(_np.flip(_np.asarray(src['p_amp']),   axis=2))
    mat = _np.ascontiguousarray(_np.flip(_np.asarray(Skull['MaterialMap']), axis=2))
    tgt = _np.asarray(Skull['TargetLocation']).astype(int)
    stp = float(Skull['SpatialStep']) * 1e3

    dens = _np.asarray(src['Material'])[:, 0][
        _np.ascontiguousarray(_np.flip(_np.asarray(src['MaterialMap']), axis=2))]
    sos  = _np.asarray(src['Material'])[:, 1][
        _np.ascontiguousarray(_np.flip(_np.asarray(src['MaterialMap']), axis=2))]

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

    xv = _np.asarray(Skull['x_vec']) * 1e3       # already centred on the target
    yv = _np.asarray(Skull['y_vec']) * 1e3
    zv = _np.asarray(Skull['z_vec']) * 1e3
    zv = zv - zv[tgt[2]] + distance_to_target    # 0 = skin, +Z = deeper

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
    """Interactive nilearn viewer of normalised acoustic intensity on native T1.

    Loads the ``*FullElasticSolution_Sub_NORM.nii.gz`` that BabelBrain saves
    alongside the h5.  This file carries the correct ``affineSub`` (sub-volume
    origin in native RAS mm), so the overlay is precisely registered to T1.

    Parameters
    ----------
    acoustic_file : str | Path
        Path to the ``*DataForSim.h5`` acoustic output from Step 5b.
        The corresponding ``*FullElasticSolution_Sub_NORM.nii.gz`` must exist
        in the same directory (created automatically by BabelBrain Step 5b).
    t1_path : str | Path
        Native T1 NIfTI (e.g. ``T1W`` / ``m2m_dir / 'T1.nii.gz'``).
    roi_nii : str | Path | None, optional
        Native-space target ROI mask NIfTI.  When provided, a second
        interactive viewer is displayed below the acoustic map showing the
        ROI outline on T1.
    title : str, optional
        Figure title.  Defaults to the acoustic file stem (without suffix).
    fig_dir : str | Path | None, optional
        Directory to save interactive viewers as HTML files.  When provided,
        both viewers are saved alongside the static QC PNG.

    Returns
    -------
    nilearn HTML view object  (auto-displayed in Jupyter).

    Used by: Step 05-BB (QC cell).
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
    """Back-calculate the free-field ISPPA needed to reach the planned in-situ ISPPA.

    Writes ``{stem}_Summary.csv`` next to the thermal output (or in *out_dir*)
    with one row per DC/PRF/Duration combination, and displays the same table.

    Why this is the number you need
    ------------------------------
    The stimulation YAMLs set ``BaseIsppa`` as the **in-situ** ISPPA at the focal
    point — what actually reaches the brain.  The NeuroFUS TPO, however, takes
    **free-field (in-water) ISPPA** as its input: its UI has an ``ISPPA`` field,
    and the box computes the per-channel power itself (test report §VIII).  The
    two differ by the skull/scalp insertion loss, which is what the simulation
    gives us.  So the operator-facing quantity is
    ``required free-field ISPPA = BaseIsppa / derating_ratio``.

    Derating ratio
    --------------
    Computed exactly as BabelBrain's "Total losses ratio using single punctual
    measurement" (``ThermalModeling/CalculateTemperatureEffects.py``):

        ratio = (max |p| inside brain / max |p| in the water-only run) ** 2

    since ISPPA scales with p².  Verified to reproduce BabelBrain's printed value
    bit-for-bit.  Both fields are flipped along z first, matching BabelBrain, and
    "brain" is ``MaterialMap >= 4`` (label 4 without CT; CT runs add 5-7).

    Calibrated reference
    --------------------
    When the transducer YAML carries ``calibration.isppa_w_per_cm2`` (present for
    CTX-500, absent for the UMD DPX-500), its mean is reported as the calibrated
    reference ISPPA together with the required/reference factor.  For the CTX-500
    the TPO holds ISPPA constant across the whole 41.4-69.7 mm steering range by
    adjusting power (test report §IV), so this reference does not depend on focal
    depth — hence no depth argument.

    Exceeding that reference is reported but **not** treated as an error: the
    ``Power limits enforced`` setting is adjustable, and choosing a per-subject
    ISPPA is a normal part of the workflow.  It does mean leaving the calibrated
    regime, which the vendor labels off-label, so it is surfaced explicitly.

    Parameters
    ----------
    acoustic_file : str | Path
        ``*DataForSim.h5`` from Step 5b.  The matching ``*_Water_DataForSim.h5``
        must sit beside it.
    allcomb_h5 : str | Path
        ``*_AllCombinations.h5`` from Step 5c, read for the protocol table.
    tx_cfg : dict
        Transducer config (``cfg['transducer_cfg']``), used for the optional
        calibrated-reference columns.
    out_dir : str | Path | None
        Where to write the CSV.  Defaults to the directory of *allcomb_h5*.
    display : bool
        Also render an HTML table (notebook use).

    Returns
    -------
    str
        Path to the written CSV.

    Used in: step 05 notebook (Step 5c summary).
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
    _ac = ReadFromH5py(acoustic_file)
    _wa = ReadFromH5py(water_file)
    p_tis = _np.ascontiguousarray(_np.flip(_np.asarray(_ac['p_amp']), axis=2))
    p_wat = _np.ascontiguousarray(_np.flip(_np.asarray(_wa['p_amp']), axis=2))
    matmap = _np.ascontiguousarray(_np.flip(_np.asarray(_ac['MaterialMap']), axis=2))

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
                       acoustic_file=None, baseline_t=37.0, stim_label=None):
    """Plot thermal QC figure(s) matching the BabelBrain GUI style.

    Produces one figure per parameter combination with two main panels that
    mirror the GUI Step-3 view:

    * **Left**: Isppa (W/cm²) — sagittal slice through target, coloured 0 →
      ISPPA.  Requires *acoustic_file* to compute the spatial intensity map.
    * **Right**: Temperature (°C) — absolute temperature at end of FUS,
      same slice.
    * **Right column**: safety summary (max temp + CEM43 per tissue, plus
      MI vs. the FDA diagnostic-ultrasound guideline of 1.9).

    Both panels use physical mm axes (distance from skin on Y, lateral mm
    centred at the beam axis on X) and display the skull boundary as a
    yellow dashed contour and the target as a black '+' crosshair.

    Parameters
    ----------
    allcomb_h5 : str | Path
        Path to ``*_AllCombinations.h5`` from Step 5c.  Falls back to glob
        search if the file is missing (e.g. after kernel restart).
    field_target : str
        Prefix used by BabelBrain (``f"{ID}_{tx_system}"``).  Glob fallback.
    m2m_dir : str | Path
        Subject ``m2m_*`` directory.  Glob fallback.
    fig_dir : str | Path
        Directory where PNGs will be saved (created if absent).
    ID : str
        Label used in filenames and figure title.
    sub_id_full : str
        Full BIDS subject ID (e.g. ``'sub-M3827'``).
    target_name : str
        Target label (e.g. ``'Ce_CeA'``).
    target_side : str
        Side suffix (``'_L'``, ``'_R'``, or ``''``).
    tx_system : str
        BabelBrain transducer identifier.
    frequency : float
        Transducer centre frequency in Hz.
    acoustic_file : str | Path | None, optional
        Path to ``*DataForSim.h5`` from Step 5b.  Required for the Isppa
        spatial map (left panel) and physical mm coordinate axes. When
        omitted the Isppa panel shows a placeholder and axes use voxels.
    baseline_t : float, optional
        Baseline body temperature in °C (default 37.0).

    Returns
    -------
    list[str]
        Absolute paths to saved PNGs (one per combination).

    Used by: Step 05-BB (QC cell).
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
        ac    = ReadFromH5py(str(acoustic_file))
        p_ac  = _np.flip(_np.array(ac['p_amp']), axis=2)   # unflipped (nx,ny,nz)
        stp   = float(ac['SpatialStep']) * 1e3               # mm/vox
        x_mm  = _np.array(ac['x_vec']) * 1e3
        y_mm  = _np.array(ac['y_vec']) * 1e3
        z_mm  = _np.array(ac['z_vec']) * 1e3
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

        # Temperature colour range: baseline to max+margin
        T_vmax = max(t_brain_max, t_skin_max, t_skull_max, baseline_t + 0.05)
        T_vmin = baseline_t - 0.02

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
            cb_i = _plt.colorbar(im_i, ax=axL, shrink=0.9, pad=0.02)
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
        _levels_t = _np.linspace(T_vmin, T_vmax, 30)
        im_t = axR.contourf(_XX, _ZZ, T_sl, levels=_levels_t,
                             cmap='jet', vmin=T_vmin, vmax=T_vmax)
        cb_t = _plt.colorbar(im_t, ax=axR, shrink=0.9, pad=0.02)
        cb_t.set_label('Temperature (°C)', fontsize=FS_CB)
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
            ('row', 'On / Off',        f'{DUR:.0f} s / {DUR_OFF:.0f} s',     '#000000'),
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
            f"On={DUR:.0f}s / Off={DUR_OFF:.0f}s",
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
