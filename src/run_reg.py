#!/usr/bin/env python3
"""
src/run_reg.py
Batch runner — Step 3: ANTs inverse registration (MNI → native).

Warps a MNI-space mask into each subject's native T1 space, saves the
native-space mask, computes the target coordinate (centre of mass), and
writes a registration QC figure.

Run this script from the standard MRI Python environment (mri_environment),
which must have antspy, nibabel, nilearn, templateflow, and scipy installed.

Algorithm (per subject)
-----------------------
1. Load native T1; reorient to RAS for ANTs.
2. Intensity-normalise MNI template (histogram_match / imath_normalize / none).
3. ANTs registration: Affine pre-step → SyN or SyNCC nonlinear refinement.
4. Apply forward transform (MNI → native) to mask with nearestNeighbor.
5. Save native mask.
6. Compute centre of mass (CoM) in native scanner coordinates.
7. Write overlay visualisation PNG.

Usage — single subject:
    python run_reg.py \\
        --site       config/sites/site_RIKEN_AK.yaml \\
        --sub        sub-SK \\
        --mask       masks/standardized/aMCC_NeuroSynthTopic112_mask_MNI.nii.gz \\
        --mask-label aMCC_NeuroSynthTopic112 \\
        [--ants-type SyN] [--intensity-norm histogram_match] \\
        [--z-threshold 1.0] [--dry-run]

Usage — batch:
    python run_reg.py \\
        --site       config/sites/site_RIKEN_AK.yaml \\
        --sub-list   subjects.txt \\
        --mask       masks/standardized/aMCC_NeuroSynthTopic112_mask_MNI.nii.gz \\
        --mask-label aMCC_NeuroSynthTopic112

Outputs (per subject, written to {data_dir}/{sub_id_bare}/):
    {sub_id_full}_{mask_label}_mask_native.nii.gz
    figures/{sub_id_full}_{mask_label}_native_overlay.png
    figures/{sub_id_full}_MNI2native_regcheck.png
    ants_transforms/{sub_id_full}_MNI2native_*.mat / *.nii.gz
"""

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate utils.py (same directory as this script)
# ---------------------------------------------------------------------------
_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from utils import (
    load_site_config,
    resolve_data_dir,
    normalise_sub_id,
    resolve_sub_dir,
    parse_sub_list,
    find_t1,
    apply_inverse_transform,
    compute_com_native,
    visualize_mask_native,
)


# ---------------------------------------------------------------------------
# Per-subject registration
# ---------------------------------------------------------------------------

def run_one(
    sub_id: str,
    data_dir: Path,
    mask_path: str,
    mask_label: str,
    ants_type: str,
    intensity_norm: str,
    z_threshold: float,
    dry_run: bool,
) -> None:
    """Run inverse registration for a single subject."""
    import ants
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nilearn import plotting
    from templateflow.api import get as tf_get

    _, sub_bare = normalise_sub_id(sub_id)
    sub_dir = resolve_sub_dir(data_dir, sub_bare, f"sub-{sub_bare}")
    sub_id_full = f"sub-{sub_bare}"

    if not sub_dir.exists():
        print(f"  ERROR: subject directory not found: {sub_dir}")
        return

    t1_path = find_t1(sub_dir, sub_bare)
    transforms_dir = sub_dir / "ants_transforms"
    transforms_dir.mkdir(parents=True, exist_ok=True)
    fig_dir = sub_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    native_mask_path = sub_dir / f"{sub_id_full}_{mask_label}_mask_native.nii.gz"

    print(f"  T1 native:    {t1_path}")
    print(f"  Mask (MNI):   {mask_path}")
    print(f"  Output mask:  {native_mask_path}")
    print(f"  ANTs type:    {ants_type}  |  intensity_norm: {intensity_norm}")

    if dry_run:
        print("  [dry-run] Skipping registration.")
        return

    # --- T1 loading and orientation -------------------------------------------
    t1_native_orig = ants.image_read(str(t1_path))
    t1_native_ras  = ants.reorient_image2(t1_native_orig, orientation="RAS")

    # --- MNI template -----------------------------------------------------------
    t1_mni_paths = tf_get(
        "MNI152NLin2009cAsym", resolution=1, suffix="T1w", extension="nii.gz"
    )
    t1_mni_path = str([p for p in t1_mni_paths if "desc-brain" not in str(p)][0])
    t1_mni_orig = ants.image_read(t1_mni_path)

    # --- Intensity normalisation -------------------------------------------------
    _norm_map = {
        "histogram_match": lambda: ants.histogram_match_image(
            source_image=t1_mni_orig,
            reference_image=t1_native_ras,
            number_of_histogram_bins=256,
            number_of_match_points=128,
            use_threshold_at_mean_intensity=True,
        ),
        "imath_normalize": lambda: ants.iMath(t1_mni_orig, "Normalize"),
        "none":            lambda: t1_mni_orig,
    }
    if intensity_norm not in _norm_map:
        raise ValueError(f"Unknown --intensity-norm: {intensity_norm!r}")
    t1_mni_ready = _norm_map[intensity_norm]()
    print(f"  Intensity normalisation: {intensity_norm}")

    # --- ANTs registration -------------------------------------------------------
    outprefix = str(transforms_dir / f"{sub_id_full}_MNI2native_")
    if ants_type in ("SyN", "SyNCC"):
        reg_affine = ants.registration(
            fixed=t1_native_ras,
            moving=t1_mni_ready,
            type_of_transform="Affine",
        )
        reg = ants.registration(
            fixed=t1_native_ras,
            moving=t1_mni_ready,
            type_of_transform=ants_type,
            initial_transform=reg_affine["fwdtransforms"][0],
            outprefix=outprefix,
        )
    else:  # "Affine"
        reg = ants.registration(
            fixed=t1_native_ras,
            moving=t1_mni_ready,
            type_of_transform=ants_type,
            outprefix=outprefix,
        )
    print(f"  Registration complete. Transforms: {reg['fwdtransforms']}")

    # --- Apply transform to mask -------------------------------------------------
    mask_native = apply_inverse_transform(
        mask_mni_path=mask_path,
        reg=reg,
        t1_native_ras=t1_native_ras,
        t1_native_orig=t1_native_orig,
        output_path=native_mask_path,
        interpolator="nearestNeighbor",
        mask_brain=True,
    )
    n_vox = int((mask_native.numpy() > z_threshold).sum())
    print(f"  Native mask saved: {native_mask_path}")
    print(f"  Voxels above z={z_threshold}: {n_vox}")

    # --- CoM --------------------------------------------------------------------
    com_mm, com_vox = compute_com_native(mask_native, z_threshold=z_threshold)
    print(f"  CoM (mm): x={com_mm[0]:.2f}  y={com_mm[1]:.2f}  z={com_mm[2]:.2f}")

    # --- Visualisation -----------------------------------------------------------
    fig_path = fig_dir / f"{sub_id_full}_{mask_label}_native_overlay.png"
    visualize_mask_native(
        mask_native=mask_native,
        t1_native=t1_native_orig,
        target_label=mask_label,
        output_path=fig_path,
        z_threshold=z_threshold,
    )
    print(f"  Overlay figure: {fig_path}")

    reg_fig_path = fig_dir / f"{sub_id_full}_MNI2native_regcheck.png"
    import nibabel as nib
    import numpy as np
    # ants_to_nib inline (avoids additional import)
    _warp = reg["warpedmovout"]
    _nib = nib.Nifti1Image(
        _warp.numpy().astype(np.float32), np.diag(list(_warp.spacing) + [1.0])
    )
    reg_fig = plotting.plot_anat(
        anat_img=_nib,
        bg_img=nib.load(str(t1_path)),
        display_mode="ortho",
        draw_cross=False,
        title="Registration QC: warped MNI template on native T1",
        dim=-1,
    )
    reg_fig.savefig(str(reg_fig_path), dpi=150)
    plt.close("all")
    print(f"  RegQC figure: {reg_fig_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Batch ANTs inverse registration runner (Step 3).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--site", required=True, metavar="YAML",
        help="Path to site config YAML.",
    )
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument(
        "--sub", metavar="SUB_ID",
        help="Single subject ID (e.g. sub-SK or SK).",
    )
    grp.add_argument(
        "--sub-list", metavar="FILE",
        help="Text file with one subject ID per line (# comments ignored).",
    )
    p.add_argument(
        "--mask", required=True, metavar="FILE",
        help="MNI-space mask NIfTI (e.g. masks/standardized/*.nii.gz).",
    )
    p.add_argument(
        "--mask-label", required=True, metavar="LABEL",
        help="Short label used in output filenames (e.g. aMCC_NeuroSynthTopic112).",
    )
    p.add_argument(
        "--ants-type", default="SyN",
        choices=["Affine", "SyN", "SyNCC"],
        help="ANTs registration type.",
    )
    p.add_argument(
        "--intensity-norm", default="histogram_match",
        choices=["histogram_match", "imath_normalize", "none"],
        dest="intensity_norm",
        help="MNI template intensity normalisation before registration.",
    )
    p.add_argument(
        "--z-threshold", type=float, default=0.0, dest="z_threshold",
        help="Voxel threshold for CoM and visualisation.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Validate inputs and print paths without running.",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    site_yaml = Path(args.site).expanduser().resolve()
    cfg = load_site_config(site_yaml)
    data_dir = resolve_data_dir(cfg)
    mask_path = str(Path(args.mask).expanduser().resolve())

    if not Path(mask_path).exists():
        sys.exit(f"ERROR: mask not found: {mask_path}")

    subjects = [args.sub] if args.sub else parse_sub_list(args.sub_list)

    print(f"Site:       {cfg.get('site', '?')} / {cfg.get('station', '?')}")
    print(f"Data dir:   {data_dir}")
    print(f"Mask:       {mask_path}")
    print(f"Label:      {args.mask_label}")
    print(f"Subjects:   {len(subjects)}")
    if args.dry_run:
        print("Mode:       DRY RUN")
    print()

    n_ok = n_fail = 0
    for sub_id in subjects:
        print(f"--- {sub_id} ---")
        try:
            run_one(
                sub_id=sub_id,
                data_dir=data_dir,
                mask_path=mask_path,
                mask_label=args.mask_label,
                ants_type=args.ants_type,
                intensity_norm=args.intensity_norm,
                z_threshold=args.z_threshold,
                dry_run=args.dry_run,
            )
            n_ok += 1
        except Exception as e:
            print(f"  ERROR: registration failed for {sub_id}: {e}")
            n_fail += 1
        print()

    print("=" * 50)
    print(f"Summary: {n_ok} completed  {n_fail} failed")


if __name__ == "__main__":
    main()
