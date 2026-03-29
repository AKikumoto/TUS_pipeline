#!/usr/bin/env python3
"""
src/run_prepall.py
Master pipeline orchestrator — Steps 1, 3, and 4 end-to-end.

Runs the full TUS preparation pipeline for one or more subjects:
  [seg]     Step 1: SimNIBS charm segmentation
  [reg]     Step 3: ANTs inverse registration (MNI → native)
  [com]     Step 4a: Centre-of-Mass targeting + BrainSight export (identity rotation)
  [plantus] Step 4b: PlanTUS automated placement (best vertex, real transducer matrix)

Note: ``com`` and ``plantus`` are independent and can both be run as a cross-check.

Each step is modular: individual steps can be activated or deactivated via
``--steps`` (or the ``steps`` key in the pipeline YAML).  Steps run in
sequence per subject; subjects run sequentially.

Internal design
---------------
This script calls the individual step runners as subprocesses, all using the
current Python interpreter (``sys.executable``):
  seg     → src/run_seg.py
  reg     → src/run_reg.py
  com     → src/run_com.py
  plantus → src/run_planTUS.py

All three steps require the mri conda environment (antspy, nilearn, SimNIBS 4.6+
pip-installed).  Activate it before running this script.

Usage — pipeline YAML (recommended for multi-subject batch):
    python run_prepall.py --config pipeline.yaml [--steps seg,reg,plantus] [--dry-run]

Usage — inline CLI (single subject or quick run):
    python run_prepall.py \\
        --site       config/sites/site_RIKEN_AK.yaml \\
        --mask       masks/standardized/aMCC_NeuroSynthTopic112_mask_MNI.nii.gz \\
        --mask-label aMCC_NeuroSynthTopic112 \\
        --subjects   sub-01 sub-02 sub-03 \\
        --steps      seg,reg,plantus \\
        [--target-side _R] [--additional-offset 0.0] \\
        [--ants-type SyN] [--intensity-norm histogram_match] \\
        [--fix-qform] [--dry-run]

Pipeline YAML format
--------------------
    site:           ../config/sites/site_RIKEN_AK.yaml
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
    steps:             [seg, reg, com, plantus]   # default: seg, reg, plantus
    subjects:
      - sub_id: sub-01
      - sub_id: sub-02
        target_side: _L
        additional_offset: 2.0
      - sub_id: sub-03
        skip: true
"""

import argparse
import subprocess
import sys
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
        # Resolve relative paths in YAML against the YAML file's directory
        _base = config_path.parent
        for key in ("site", "mask"):
            if key in cfg and cfg[key] and not Path(str(cfg[key])).is_absolute():
                cfg[key] = str((_base / cfg[key]).resolve())

    # CLI overrides
    if args.site:
        cfg["site"] = str(Path(args.site).expanduser().resolve())
    if args.mask:
        cfg["mask"] = str(Path(args.mask).expanduser().resolve())
    if getattr(args, "mask_label", None):
        cfg["mask_label"] = args.mask_label
    if getattr(args, "target_name", None):
        cfg["target_name"] = args.target_name
    if getattr(args, "target_side", None):
        cfg["target_side"] = args.target_side
    if getattr(args, "additional_offset", None) is not None:
        cfg["additional_offset"] = args.additional_offset
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

    # Steps: CLI flag takes precedence over YAML
    if args.steps:
        cfg["steps"] = [s.strip() for s in args.steps.split(",")]
    elif "steps" not in cfg:
        cfg["steps"] = ["seg", "reg", "plantus"]

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
    cfg.setdefault("target_name",      cfg.get("mask_label", ""))
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
    fix_qform: bool,
    dry_run: bool,
    runner: Path,
    python: str,
) -> int:
    cmd = [python, str(runner), "--site", site_yaml, "--sub", sub_id]
    if fix_qform:
        cmd.append("--fix-qform")
    if dry_run:
        cmd.append("--dry-run")
    print(f"  [seg] {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def _run_reg(
    sub_id: str,
    site_yaml: str,
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
    if dry_run:
        cmd.append("--dry-run")
    print(f"  [reg] {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def _run_com(
    sub_id: str,
    site_yaml: str,
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
    if dry_run:
        cmd.append("--dry-run")
    print(f"  [com] {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def _run_plantus(
    sub_id: str,
    site_yaml: str,
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
    if dry_run:
        cmd.append("--dry-run")
    print(f"  [plantus] {' '.join(cmd)}")
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
    needs_mask_label = {"reg", "com", "plantus"} & set(cfg.get("steps", []))
    if needs_mask_label and not cfg.get("mask_label"):
        errors.append("'mask_label' is required for reg/com/plantus steps.")
    needs_mni_mask = {"reg", "plantus"} & set(cfg.get("steps", []))
    if needs_mni_mask:
        if not cfg.get("mask"):
            errors.append("'mask' (MNI-space mask path) is required for reg/plantus steps.")
        elif not Path(cfg["mask"]).exists():
            errors.append(f"mask not found: {cfg['mask']}")
    if not cfg.get("subjects"):
        errors.append("No subjects specified.")
    unknown_steps = set(cfg.get("steps", [])) - {"seg", "reg", "com", "plantus"}
    if unknown_steps:
        errors.append(f"Unknown step(s): {unknown_steps}. Valid: seg, reg, com, plantus.")
    return errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="TUS preparation pipeline orchestrator (Steps 1, 3, 4).",
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
    p.add_argument("--mask",       metavar="FILE",  help="MNI-space mask NIfTI.")
    p.add_argument("--mask-label", metavar="LABEL", dest="mask_label",
                   help="Mask label (used in output filenames).")
    p.add_argument("--target-name", metavar="LABEL", dest="target_name",
                   help="PlanTUS target label (defaults to --mask-label).")
    p.add_argument("--target-side", default=None, dest="target_side",
                   metavar="_R|_L|''",
                   help="Side suffix for PlanTUS target.")
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
             "Valid: seg, reg, com, plantus. "
             "com and plantus are independent and can both be run.",
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
    }
    for step, path in runners.items():
        if step in cfg["steps"] and not path.exists():
            sys.exit(f"ERROR: runner not found: {path}")

    steps     = cfg["steps"]
    subjects  = cfg["subjects"]
    n_total   = len(subjects)
    dry_run   = args.dry_run

    print("\n" + "=" * 60)
    print("  run_prepall — TUS preparation pipeline")
    print(f"  Site        : {Path(cfg['site']).name}")
    print(f"  Steps       : {' -> '.join(steps)}")
    print(f"  Subjects    : {n_total}")
    if any(s in steps for s in ("reg", "plantus")):
        print(f"  Mask (MNI)  : {Path(cfg['mask']).name}  [{cfg['mask_label']}]")
    elif "com" in steps and cfg.get("mask_label"):
        print(f"  Mask label  : {cfg['mask_label']}")
    print(f"  Dry-run     : {dry_run}")
    print("=" * 60 + "\n")

    results: dict[str, dict[str, str]] = {}  # sub_id -> {step: "ok"/"fail"}

    for idx, sub in enumerate(subjects, start=1):
        sub_id = sub["sub_id"]
        t_side = sub["target_side"]
        offset = sub["additional_offset"]
        print(f"\n[{idx}/{n_total}] {sub_id}")
        results[sub_id] = {}

        for step in steps:
            print(f"\n  -- Step: {step} --")
            rc = 0

            if step == "seg":
                rc = _run_seg(
                    sub_id=sub_id,
                    site_yaml=cfg["site"],
                    fix_qform=cfg.get("fix_qform", False),
                    dry_run=dry_run,
                    runner=runners["seg"],
                    python=sys.executable,
                )

            elif step == "reg":
                rc = _run_reg(
                    sub_id=sub_id,
                    site_yaml=cfg["site"],
                    mask=cfg["mask"],
                    mask_label=cfg["mask_label"],
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
                    mask_label=cfg["mask_label"],
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
                    target=cfg.get("target_name") or cfg["mask_label"],
                    target_side=t_side,
                    additional_offset=offset,
                    top_pct=float(cfg.get("top_pct", 0.9)),
                    dry_run=dry_run,
                    runner=runners["plantus"],
                    python=sys.executable,
                )

            results[sub_id][step] = "ok" if rc == 0 else f"fail(rc={rc})"
            status = "OK" if rc == 0 else f"FAILED (rc={rc})"
            print(f"  [{step}] {status}")

    # Final summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    header = f"  {'Subject':<20}" + "".join(f"  {s:<10}" for s in steps)
    print(header)
    print("  " + "-" * (18 + 12 * len(steps)))
    all_ok = True
    for sub_id, step_results in results.items():
        row = f"  {sub_id:<20}" + "".join(
            f"  {step_results.get(s, '-'):<10}" for s in steps
        )
        print(row)
        if any("fail" in v for v in step_results.values()):
            all_ok = False
    print("=" * 60)
    print("  All steps completed." if all_ok else "  Some steps FAILED -- check output above.")
    print()


if __name__ == "__main__":
    main()
