#!/usr/bin/env python3
"""
src/run_prepall.py
Master pipeline orchestrator — Steps 1, 3, 4 and 5 end-to-end.

Runs the full TUS preparation pipeline for one or more subjects:
  [seg]      Step 1: SimNIBS charm segmentation
  [reg]      Step 3: ANTs inverse registration (MNI → native)
  [com]      Step 4a: Centre-of-Mass targeting + BrainSight export (identity rotation)
  [plantus]  Step 4b: PlanTUS automated placement (best vertex, real transducer matrix)
  [sweep]    Step 4-5: placement sweep, acoustic only (run_sweep.py), for choosing a vertex
  [babel]    Step 5:  BabelBrain domain, acoustic and thermal simulation

Note: ``com`` and ``plantus`` are independent and can both be run as a cross-check.
``sweep`` builds its own PlanTUS scene, so it does not need ``plantus``.
``sweep`` and ``babel`` are refused in one run: without ``vtx`` babel takes
the newest vtx folder, which after a sweep is the last candidate solved, not
the chosen one.  Choose the vertex from VERTICES_EXPLORED.md, then run babel
with ``vtx``.

Each step is modular: individual steps can be activated or deactivated via
``--steps`` (or the ``steps`` key in the pipeline YAML).  Subjects run
sequentially.  For each subject, ``seg`` runs once; the other steps then run
in order for each target in turn.  A failed step skips the steps after it for
that target, and a failed ``seg`` skips the subject.  Each step's start and
end are timestamped, for a log read later.  The exit code is 1 when any step
failed.

Internal design
---------------
This script calls the individual step runners as subprocesses, all using the
current Python interpreter (``sys.executable``):
  seg     → src/run_seg.py
  reg     → src/run_reg.py
  com     → src/run_com.py
  plantus → src/run_planTUS.py
  sweep   → src/run_sweep.py      (no dry run of its own: --dry-run prints its command)
  babel   → src/run_babelbrain.py

Every step requires the mri conda environment (antspy, nilearn, SimNIBS 4.6+
pip-installed).  Activate it before running this script.

The tus-prepare skill (.claude/skills/tus-prepare/SKILL.md) runs this script
with --steps seg,reg,sweep under nohup, then run_babelbrain.py --vtx for each
placement a person chose.

Usage — pipeline YAML (recommended for multi-subject batch):
    python run_prepall.py --config pipeline.yaml [--steps seg,reg,plantus,babel] [--dry-run]

Usage — inline CLI (single subject or quick run):
    python run_prepall.py \\
        --site       config/sites/site_RIKEN_AK.yaml \\
        --mask       masks/standardized/aMCC_NeuroSynthTopic112_mask_MNI.nii.gz \\
        --mask-label aMCC_NeuroSynthTopic112 \\
        --subjects   sub-01 sub-02 sub-03 \\
        --steps      seg,reg,plantus,babel \\
        [--target-side _R] [--additional-offset 0.0] \\
        [--stim config/stimulation/stimulation_hippocampus_offline_Pan2025.yaml] \\
        [--vtx 10202] [--reuse-files] [--skip-thermal] \\
        [--ants-type SyN] [--intensity-norm histogram_match] \\
        [--fix-qform] [--dry-run]

    Several targets: give several --mask and as many --mask-label, in the
    same order.

Pipeline YAML format
--------------------
Paths are absolute (~ allowed) or relative to the YAML's folder, except
sub_list_dir, which is relative to the site's data_root.  A template is in
config/template_pipeline.yaml.

    site:           ../config/sites/site_RIKEN_AK.yaml
    sub_list_dir:   SUB_LIST_PREP                    # default: the site YAML's
    mask:           ../masks/standardized/aMCC_NeuroSynthTopic112_mask_MNI.nii.gz
    mask_label:     aMCC_NeuroSynthTopic112
    target_name:    aMCC_NeuroSynthTopic112   # optional, defaults to mask_label
    target_side:    _R
    additional_offset: 0.0
    registration_type: SyN                   # SyN | SyNCC | Affine
    intensity_norm:    histogram_match        # histogram_match | imath_normalize | none
    z_threshold:       0.0
    fix_qform:         true
    top_pct:           0.9
    steps:             [seg, reg, com, plantus, babel]   # default: seg, reg, plantus
    stim:              config/stimulation/...yaml        # required for sweep and babel
    stratify:          7                                 # sweep: see run_sweep.py
    vtx:               10202                             # babel: default newest
    reuse_files:       false                             # babel
    skip_thermal:      false                             # babel
    subjects:
      - sub_id: sub-01
      - sub_id: sub-02
        target_side: _L
        additional_offset: 2.0
      - sub_id: sub-03
        skip: true

Several targets: a ``targets`` list in place of mask, mask_label and
target_name.  ``vtx`` then cannot be given, since it names one placement.

    targets:
      - mask:       ../masks/standardized/alEC_Maass2015_mask_MNI.nii.gz
        mask_label: alEC_Maass2015
      - mask:       ../masks/standardized/pmEC_Maass2015_mask_MNI.nii.gz
        mask_label: pmEC_Maass2015
        target_name: pmEC_Maass2015          # optional, defaults to mask_label
        additional_offset: 20.0              # optional; replaces the subject's
                                             # pad for this target
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Locate utils.py (same directory as this script)
# ---------------------------------------------------------------------------
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def _require_yaml() -> None:
    if yaml is None:
        sys.exit("ERROR: PyYAML is required. Install it: pip install pyyaml")


def _load_yaml(path: Path) -> dict:
    _require_yaml()
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def _load_subject_list_file(
    path: Path,
    default_target_side: str,
    default_offset: float,
) -> list[dict[str, Any]]:
    """Load subject list from a plain-text or YAML file."""
    if path.suffix in (".yaml", ".yml"):
        _require_yaml()
        data = _load_yaml(path)
        raw = data.get("subjects", data) if isinstance(data, dict) else data
        subjects = []
        for entry in raw:
            if isinstance(entry, str):
                entry = {"sub_id": entry}
            if entry.get("skip"):
                continue
            subjects.append({
                "sub_id":            entry["sub_id"],
                "target_side":       entry.get("target_side", default_target_side),
                "additional_offset": float(entry.get("additional_offset", default_offset)),
            })
        return subjects
    else:
        subjects = []
        for line in path.read_text().splitlines():
            line = line.split("#")[0].strip()
            if line:
                subjects.append({
                    "sub_id":            line,
                    "target_side":       default_target_side,
                    "additional_offset": default_offset,
                })
        return subjects


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

def _resolve_config(args: argparse.Namespace) -> dict[str, Any]:
    """Merge pipeline YAML (if given) with CLI args into a flat config dict.

    CLI args override YAML values where both are present.
    """
    cfg: dict[str, Any] = {}

    if args.config:
        config_path = Path(args.config).expanduser().resolve()
        raw = _load_yaml(config_path)
        cfg.update(raw)
        if "targets" in raw and {"mask", "mask_label", "target_name"} & raw.keys():
            sys.exit("ERROR: the pipeline YAML has both 'targets' and "
                     "mask/mask_label/target_name; use one or the other.")
        # Resolve relative paths in YAML against the YAML file's directory
        _base = config_path.parent
        # (~ is expanded first, so ~/... counts as absolute)
        for key in ("site", "mask", "stim"):
            if key in cfg and cfg[key]:
                p = Path(str(cfg[key])).expanduser()
                cfg[key] = str(p if p.is_absolute() else (_base / p).resolve())
        for t in cfg.get("targets") or []:
            if t.get("mask"):
                p = Path(str(t["mask"])).expanduser()
                t["mask"] = str(p if p.is_absolute() else (_base / p).resolve())

    # CLI overrides
    if args.site:
        cfg["site"] = str(Path(args.site).expanduser().resolve())
    if getattr(args, "sub_list_dir", None):
        cfg["sub_list_dir"] = args.sub_list_dir
    if args.mask:
        cfg["mask"] = [str(Path(m).expanduser().resolve()) for m in args.mask]
    if getattr(args, "mask_label", None):
        cfg["mask_label"] = args.mask_label
    if getattr(args, "target_name", None):
        cfg["target_name"] = args.target_name
    if getattr(args, "target_side", None):
        cfg["target_side"] = args.target_side
    if getattr(args, "additional_offset", None) is not None:
        cfg["additional_offset"] = args.additional_offset
    if getattr(args, "stim", None):
        cfg["stim"] = str(Path(args.stim).expanduser().resolve())
    if getattr(args, "vtx", None) is not None:
        cfg["vtx"] = args.vtx
    if getattr(args, "reuse_files", None):
        cfg["reuse_files"] = True
    if getattr(args, "skip_thermal", None):
        cfg["skip_thermal"] = True
    if getattr(args, "ants_type", None):
        cfg["registration_type"] = args.ants_type
    if getattr(args, "intensity_norm", None):
        cfg["intensity_norm"] = args.intensity_norm
    if getattr(args, "z_threshold", None) is not None:
        cfg["z_threshold"] = args.z_threshold
    if getattr(args, "top_pct", None) is not None:
        cfg["top_pct"] = args.top_pct
    if getattr(args, "fix_qform", False):
        cfg["fix_qform"] = True

    # Targets, each {mask, mask_label, target_name}: the YAML 'targets' list, or
    # mask and mask_label (YAML or CLI, one or several, paired by order). The
    # CLI replaces a YAML list.
    if args.mask or getattr(args, "mask_label", None) or "targets" not in cfg:
        masks  = cfg.get("mask") or []
        labels = cfg.get("mask_label") or []
        masks  = masks  if isinstance(masks, list)  else [masks]
        labels = labels if isinstance(labels, list) else [labels]
        if masks and labels and len(masks) != len(labels):
            sys.exit(f"ERROR: {len(masks)} mask(s) but {len(labels)} mask label(s); "
                     "give one label per mask, in the same order.")
        cfg["targets"] = [{"mask": masks[i] if masks else None, "mask_label": label}
                          for i, label in enumerate(labels)]
    for t in cfg["targets"]:
        t.setdefault("mask", None)
        t.setdefault("target_name", t.get("mask_label"))
    if cfg.get("target_name"):
        if len(cfg["targets"]) != 1:
            sys.exit("ERROR: target_name applies to one target; with several, "
                     "give it per entry of a 'targets' list.")
        cfg["targets"][0]["target_name"] = cfg["target_name"]

    # Steps: CLI flag takes precedence over YAML
    if args.steps:
        cfg["steps"] = [s.strip() for s in args.steps.split(",")]
    elif "steps" not in cfg:
        cfg["steps"] = ["seg", "reg", "plantus"]      # babel is opt-in: it is the
                                                 # expensive stage and needs a
                                                 # stimulation YAML

    # Subject list: CLI takes precedence over YAML subjects
    if getattr(args, "subjects", None):
        cfg["subjects"] = [
            {
                "sub_id":            s,
                "target_side":       cfg.get("target_side", ""),
                "additional_offset": float(cfg.get("additional_offset", 0.0)),
            }
            for s in args.subjects
        ]
    elif getattr(args, "subject_list", None):
        cfg["subjects"] = _load_subject_list_file(
            Path(args.subject_list).expanduser().resolve(),
            default_target_side=cfg.get("target_side", ""),
            default_offset=float(cfg.get("additional_offset", 0.0)),
        )
    elif "subjects" in cfg:
        # YAML subjects: apply defaults and filter skips
        resolved = []
        for entry in cfg["subjects"]:
            if isinstance(entry, str):
                entry = {"sub_id": entry}
            if entry.get("skip"):
                continue
            resolved.append({
                "sub_id":            entry["sub_id"],
                "target_side":       entry.get("target_side",       cfg.get("target_side", "")),
                "additional_offset": float(entry.get("additional_offset", cfg.get("additional_offset", 0.0))),
            })
        cfg["subjects"] = resolved

    # Defaults for optional fields
    cfg.setdefault("target_side",      "")
    cfg.setdefault("additional_offset", 0.0)
    cfg.setdefault("registration_type", "SyN")
    cfg.setdefault("intensity_norm",    "histogram_match")
    cfg.setdefault("z_threshold",       0.0)
    cfg.setdefault("fix_qform",         False)
    cfg.setdefault("top_pct",           0.9)

    return cfg


# ---------------------------------------------------------------------------
# Step runners (subprocess wrappers)
# ---------------------------------------------------------------------------

def _run_seg(
    sub_id: str,
    site_yaml: str,
    sub_list_dir: str | None,
    fix_qform: bool,
    dry_run: bool,
    runner: Path,
    python: str,
) -> int:
    cmd = [python, str(runner), "--site", site_yaml, "--sub", sub_id]
    if fix_qform:
        cmd.append("--fix-qform")
    if sub_list_dir:
        cmd += ["--sub-list-dir", sub_list_dir]
    if dry_run:
        cmd.append("--dry-run")
    print(f"  [seg] {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def _run_reg(
    sub_id: str,
    site_yaml: str,
    sub_list_dir: str | None,
    mask: str,
    mask_label: str,
    ants_type: str,
    intensity_norm: str,
    z_threshold: float,
    dry_run: bool,
    runner: Path,
    python: str,
) -> int:
    cmd = [
        python, str(runner),
        "--site",           site_yaml,
        "--sub",            sub_id,
        "--mask",           mask,
        "--mask-label",     mask_label,
        "--ants-type",      ants_type,
        "--intensity-norm", intensity_norm,
        "--z-threshold",    str(z_threshold),
    ]
    if sub_list_dir:
        cmd += ["--sub-list-dir", sub_list_dir]
    if dry_run:
        cmd.append("--dry-run")
    print(f"  [reg] {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def _run_com(
    sub_id: str,
    site_yaml: str,
    sub_list_dir: str | None,
    mask_label: str,
    target_side: str,
    z_threshold: float,
    dry_run: bool,
    runner: Path,
    python: str,
) -> int:
    cmd = [
        python, str(runner),
        "--site",       site_yaml,
        "--sub",        sub_id,
        "--mask-label", mask_label,
        "--side",       target_side,
        "--threshold",  str(z_threshold),
    ]
    if sub_list_dir:
        cmd += ["--sub-list-dir", sub_list_dir]
    if dry_run:
        cmd.append("--dry-run")
    print(f"  [com] {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def _run_plantus(
    sub_id: str,
    site_yaml: str,
    sub_list_dir: str | None,
    target: str,
    target_side: str,
    additional_offset: float,
    top_pct: float,
    dry_run: bool,
    runner: Path,
    python: str,
) -> int:
    cmd = [
        python, str(runner),
        "--site",              site_yaml,
        "--sub",               sub_id,
        "--target",            target,
        "--side",              target_side,
        "--additional-offset", str(additional_offset),
        "--top-pct",           str(top_pct),
    ]
    if sub_list_dir:
        cmd += ["--sub-list-dir", sub_list_dir]
    if dry_run:
        cmd.append("--dry-run")
    print(f"  [plantus] {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def _run_sweep(
    sub_id: str,
    site_yaml: str,
    sub_list_dir: str | None,
    target: str,
    target_side: str,
    stim: str,
    additional_offset: float,
    stratify: int | None,
    dry_run: bool,
    runner: Path,
    python: str,
) -> int:
    # No --top-pct: the sweep's own 0.5 is deliberate (run_sweep.py, --top-pct).
    cmd = [
        python, str(runner),
        "--site",              site_yaml,
        "--sub",               sub_id,
        "--target",            target,
        "--side",              target_side,
        "--stim",              stim,
        "--additional-offset", str(additional_offset),
    ]
    if stratify:
        cmd += ["--stratify", str(int(stratify))]
    if sub_list_dir:
        cmd += ["--sub-list-dir", sub_list_dir]
    print(f"  [sweep] {' '.join(cmd)}")
    if dry_run:                      # run_sweep has no dry run of its own
        print("  [sweep] dry run: command printed, not run")
        return 0
    result = subprocess.run(cmd)
    return result.returncode


def _run_babel(
    sub_id: str,
    site_yaml: str,
    sub_list_dir: str | None,
    target: str,
    target_side: str,
    stim: str,
    vtx: int | None,
    reuse_files: bool,
    skip_thermal: bool,
    dry_run: bool,
    runner: Path,
    python: str,
) -> int:
    cmd = [
        python, str(runner),
        "--site",              site_yaml,
        "--sub",               sub_id,
        "--target",            target,
        "--side",              target_side,
        "--stim",              stim,
    ]
    # No pad here: run_babelbrain reads it from the placement's depth report,
    # written by the plantus step.
    if vtx is not None:
        cmd += ["--vtx", str(vtx)]
    if reuse_files:
        cmd.append("--reuse-files")
    if skip_thermal:
        cmd.append("--skip-thermal")
    if sub_list_dir:
        cmd += ["--sub-list-dir", sub_list_dir]
    if dry_run:
        cmd.append("--dry-run")
    print(f"  [babel] {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_config(cfg: dict) -> list[str]:
    errors = []
    if not cfg.get("site"):
        errors.append("'site' (site YAML path) is required.")
    elif not Path(cfg["site"]).exists():
        errors.append(f"site YAML not found: {cfg['site']}")
    steps   = set(cfg.get("steps", []))
    targets = cfg.get("targets", [])
    if {"reg", "com", "plantus", "sweep", "babel"} & steps:
        if not targets:
            errors.append("A target ('mask_label', or a 'targets' list) is "
                          "required for reg/com/plantus/sweep/babel steps.")
        for t in targets:
            if not t.get("mask_label"):
                errors.append(f"A target has no 'mask_label': {t}")
    if {"reg", "plantus"} & steps:
        for t in targets:
            if not t.get("mask"):
                errors.append("'mask' (MNI-space mask path) is required for "
                              f"reg/plantus steps: {t.get('mask_label')}")
            elif not Path(t["mask"]).exists():
                errors.append(f"mask not found: {t['mask']}")
    if "babel" in steps and cfg.get("vtx") is not None and len(targets) > 1:
        errors.append("'vtx' names one placement, so it takes one target.")
    if {"sweep", "babel"} <= steps:
        errors.append("sweep and babel cannot run together: without 'vtx' babel "
                      "takes the newest vtx folder, the last candidate the sweep "
                      "solved. Choose the vertex from VERTICES_EXPLORED.md, then "
                      "run babel with 'vtx'.")
    if not cfg.get("subjects"):
        errors.append("No subjects specified.")
    unknown_steps = set(cfg.get("steps", [])) - {"seg", "reg", "com", "plantus", "sweep", "babel"}
    if unknown_steps:
        errors.append(f"Unknown step(s): {unknown_steps}. "
                      f"Valid: seg, reg, com, plantus, sweep, babel.")
    if {"sweep", "babel"} & steps and not cfg.get("stim"):
        errors.append("'stim' (stimulation protocol YAML) is required for the "
                      "sweep and babel steps.")
    return errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="TUS preparation pipeline orchestrator (Steps 1, 3, 4, 5).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Run with --config for multi-subject batch (recommended).\n"
            "Run with --site/--mask/--subjects for quick single-target runs.\n"
        ),
    )

    # Config file vs inline
    p.add_argument(
        "--config", metavar="YAML",
        help="Pipeline YAML (site, mask, subjects, steps, options). "
             "CLI args override YAML values.",
    )

    # Core settings (can also be in YAML)
    p.add_argument("--site",       metavar="YAML",  help="Site config YAML path.")
    p.add_argument("--sub-list-dir", metavar="DIR", dest="sub_list_dir",
                   help="Subject folder, relative to the site's data_root or "
                        "absolute. Default: the site YAML's sub_list_dir.")
    p.add_argument("--mask",       nargs="+", metavar="FILE",
                   help="MNI-space mask NIfTI; several for several targets.")
    p.add_argument("--mask-label", nargs="+", metavar="LABEL", dest="mask_label",
                   help="Mask label (used in output filenames); one per --mask, "
                        "in the same order.")
    p.add_argument("--target-name", metavar="LABEL", dest="target_name",
                   help="PlanTUS target label (defaults to --mask-label). "
                        "One target only.")
    p.add_argument("--target-side", default=None, dest="target_side",
                   metavar="_R|_L|''",
                   help="Side suffix for PlanTUS target.")
    p.add_argument("--stim", metavar="YAML", default=None,
                   help="Stimulation protocol YAML. Required for the sweep and babel steps.")
    p.add_argument("--vtx", type=int, default=None, metavar="N",
                   help="Placement for the babel step. Default: the newest.")
    p.add_argument("--reuse-files", action="store_true", default=None,
                   help="babel: skip a stage whose output already exists.")
    p.add_argument("--skip-thermal", action="store_true", default=None,
                   help="babel: stop after the acoustic stage.")
    p.add_argument("--additional-offset", type=float, default=None,
                   dest="additional_offset",
                   help="Gel/pad offset in mm for PlanTUS.")

    # Subject list
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--subjects",    nargs="+", metavar="SUB_ID",
                     help="Inline subject IDs.")
    grp.add_argument("--subject-list", metavar="FILE", dest="subject_list",
                     help="Text or YAML subject list file.")

    # Step control
    p.add_argument(
        "--steps", metavar="seg,reg,plantus", default=None,
        help="Comma-separated steps to run (default: seg,reg,plantus). "
             "Valid: seg, reg, com, plantus, sweep, babel. "
             "com and plantus are independent and can both be run; "
             "sweep and babel cannot run together.",
    )

    # Seg options
    p.add_argument("--fix-qform", action="store_true", dest="fix_qform",
                   help="Run fslorient -copysform2qform before charm (seg step).")

    # Reg options
    p.add_argument("--ants-type", default=None,
                   choices=["Affine", "SyN", "SyNCC"], dest="ants_type",
                   help="ANTs registration type (reg step).")
    p.add_argument("--intensity-norm", default=None,
                   choices=["histogram_match", "imath_normalize", "none"],
                   dest="intensity_norm",
                   help="MNI template intensity normalisation (reg step).")
    p.add_argument("--z-threshold", type=float, default=None, dest="z_threshold",
                   help="Voxel threshold for CoM (reg step).")

    # PlanTUS options
    p.add_argument("--top-pct", type=float, default=None, dest="top_pct",
                   help="Top-candidate fraction for best-vertex selection (plantus step).")

    # Global
    p.add_argument("--dry-run", action="store_true",
                   help="Validate and print commands without executing.")

    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Flush each line, so in a log file these lines stay in order with the
    # runners' own output.
    sys.stdout.reconfigure(line_buffering=True)
    args = parse_args()

    if not args.config and not args.site:
        sys.exit("ERROR: provide --config or --site (with --mask, --subjects/--subject-list).")

    # Build unified config
    cfg = _resolve_config(args)

    # Validate
    errors = _validate_config(cfg)
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        sys.exit(1)

    # Resolve runner scripts (same directory as this file)
    runners = {
        "seg":     _SRC_DIR / "run_seg.py",
        "reg":     _SRC_DIR / "run_reg.py",
        "com":     _SRC_DIR / "run_com.py",
        "plantus": _SRC_DIR / "run_planTUS.py",
        "sweep":   _SRC_DIR / "run_sweep.py",
        "babel":   _SRC_DIR / "run_babelbrain.py",
    }
    for step, path in runners.items():
        if step in cfg["steps"] and not path.exists():
            sys.exit(f"ERROR: runner not found: {path}")

    steps        = cfg["steps"]
    target_steps = [s for s in steps if s != "seg"]
    targets      = cfg["targets"] if target_steps else []
    subjects     = cfg["subjects"]
    n_total      = len(subjects)
    dry_run      = args.dry_run

    print("\n" + "=" * 60)
    print("  run_prepall — TUS preparation pipeline")
    print(f"  Site        : {Path(cfg['site']).name}")
    print(f"  Subject dir : {cfg.get('sub_list_dir') or '(the site YAML sub_list_dir)'}")
    print(f"  Steps       : {' -> '.join(steps)}")
    print(f"  Subjects    : {n_total}")
    for t in targets:
        mask_name = f"  ({Path(t['mask']).name})" if t.get("mask") else ""
        print(f"  Target      : {t['mask_label']}{mask_name}")
    print(f"  Dry-run     : {dry_run}")
    print(f"  Started     : {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60 + "\n")
    t_run = time.time()

    results: dict[str, dict[str, str]] = {}  # "sub_id target" -> {step: "ok"/"fail"}

    for idx, sub in enumerate(subjects, start=1):
        sub_id = sub["sub_id"]
        t_side = sub["target_side"]
        print(f"\n[{idx}/{n_total}] {sub_id}")

        seg_result: dict[str, str] = {}
        if "seg" in steps:
            print(f"\n  -- Step: seg --  {datetime.now():%Y-%m-%d %H:%M:%S}")
            t_step = time.time()
            rc = _run_seg(
                sub_id=sub_id,
                site_yaml=cfg["site"],
                sub_list_dir=cfg.get("sub_list_dir"),
                fix_qform=cfg.get("fix_qform", False),
                dry_run=dry_run,
                runner=runners["seg"],
                python=sys.executable,
            )
            seg_result["seg"] = "ok" if rc == 0 else f"fail(rc={rc})"
            status = "OK" if rc == 0 else f"FAILED (rc={rc})"
            print(f"  [seg] {status}  {datetime.now():%H:%M:%S}, "
                  f"{(time.time() - t_step) / 60:.1f} min")
        if not targets:
            results[sub_id] = seg_result

        for target in targets:
            label = target["mask_label"]
            # A target's own pad replaces the subject's for that target
            offset = float(target.get("additional_offset", sub["additional_offset"]))
            row_results = results[f"{sub_id} {label}{t_side}"] = dict(seg_result)
            failed = seg_result.get("seg", "ok") != "ok"

            for step in target_steps:
                if failed:               # a later step would run on a broken input
                    row_results[step] = "skipped"
                    print(f"\n  -- Step: {step} [{label}] -- skipped: an earlier step failed")
                    continue
                print(f"\n  -- Step: {step} [{label}] --  {datetime.now():%Y-%m-%d %H:%M:%S}")
                t_step = time.time()
                rc = 0

                if step == "reg":
                    rc = _run_reg(
                        sub_id=sub_id,
                        site_yaml=cfg["site"],
                        sub_list_dir=cfg.get("sub_list_dir"),
                        mask=target["mask"],
                        mask_label=label,
                        ants_type=cfg.get("registration_type", "SyN"),
                        intensity_norm=cfg.get("intensity_norm", "histogram_match"),
                        z_threshold=float(cfg.get("z_threshold", 0.0)),
                        dry_run=dry_run,
                        runner=runners["reg"],
                        python=sys.executable,
                    )

                elif step == "com":
                    rc = _run_com(
                        sub_id=sub_id,
                        site_yaml=cfg["site"],
                        sub_list_dir=cfg.get("sub_list_dir"),
                        mask_label=label,
                        target_side=t_side,
                        z_threshold=float(cfg.get("z_threshold", 0.0)),
                        dry_run=dry_run,
                        runner=runners["com"],
                        python=sys.executable,
                    )

                elif step == "plantus":
                    rc = _run_plantus(
                        sub_id=sub_id,
                        site_yaml=cfg["site"],
                        sub_list_dir=cfg.get("sub_list_dir"),
                        target=target["target_name"],
                        target_side=t_side,
                        additional_offset=offset,
                        top_pct=float(cfg.get("top_pct", 0.9)),
                        dry_run=dry_run,
                        runner=runners["plantus"],
                        python=sys.executable,
                    )

                elif step == "sweep":
                    rc = _run_sweep(
                        sub_id=sub_id,
                        site_yaml=cfg["site"],
                        sub_list_dir=cfg.get("sub_list_dir"),
                        target=target["target_name"],
                        target_side=t_side,
                        stim=cfg["stim"],
                        additional_offset=offset,
                        stratify=cfg.get("stratify"),
                        dry_run=dry_run,
                        runner=runners["sweep"],
                        python=sys.executable,
                    )

                elif step == "babel":
                    rc = _run_babel(
                        sub_id=sub_id,
                        site_yaml=cfg["site"],
                        sub_list_dir=cfg.get("sub_list_dir"),
                        target=target["target_name"],
                        target_side=t_side,
                        stim=cfg["stim"],
                        vtx=cfg.get("vtx"),
                        reuse_files=bool(cfg.get("reuse_files", False)),
                        skip_thermal=bool(cfg.get("skip_thermal", False)),
                        dry_run=dry_run,
                        runner=runners["babel"],
                        python=sys.executable,
                    )

                row_results[step] = "ok" if rc == 0 else f"fail(rc={rc})"
                failed = rc != 0
                status = "OK" if rc == 0 else f"FAILED (rc={rc})"
                print(f"  [{step}] {status}  {datetime.now():%H:%M:%S}, "
                      f"{(time.time() - t_step) / 60:.1f} min")

    # Final summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    width = max([20] + [len(k) for k in results])
    header = f"  {'Subject / target':<{width}}" + "".join(f"  {s:<10}" for s in steps)
    print(header)
    print("  " + "-" * (width - 2 + 12 * len(steps)))
    all_ok = True
    for sub_id, step_results in results.items():
        row = f"  {sub_id:<{width}}" + "".join(
            f"  {step_results.get(s, '-'):<10}" for s in steps
        )
        print(row)
        if any("fail" in v for v in step_results.values()):
            all_ok = False
    print("=" * 60)
    print("  All steps completed." if all_ok else "  Some steps FAILED -- check output above.")
    print(f"  Finished {datetime.now():%Y-%m-%d %H:%M:%S}, {(time.time() - t_run) / 60:.1f} min")
    print()
    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
