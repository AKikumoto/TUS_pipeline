"""
scripts/TUS/z_dont_edit/step03_inverse_registration.py
Command-line interface for Step 03 — inverse registration (MNI → native).

Mirrors the logic in step03_inverse_registration.ipynb but runs non-interactively, useful
for batch processing multiple subjects.

Usage
-----
  python step03_inverse_registration.py \\
      --site   ../config/sites/site_RIKEN_AK.yaml \\
      --sub    sub-SK \\
      --mask   ../masks/original/v5-topics-400_112_error_errors_monitoring_association-test_z_FDR_0.01.nii.gz \\
      --label  aMCC_NeuroSynthTopic112 \\
      [--threshold 1.0] \\
      [--transform SyN]

Outputs (written to <data_root>/<sub>/):
  <sub>_<label>_mask_native.nii.gz
  figures/<sub>_<label>_native_overlay.png
  figures/<sub>_MNI2native_regcheck.png
"""

import argparse
import sys
from pathlib import Path

# Allow running from the run/ directory without installing the package
SRC_DIR = str(Path(__file__).parent.resolve())
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils import (
    load_site_config,
    resolve_data_dir,
    normalise_sub_id,
    find_t1,
    ants_to_nib,
    register_mni_to_native,
    apply_inverse_transform,
    compute_com_native,
    visualize_mask_native,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Step 03 — ANTs inverse registration (MNI → native space).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--site",      required=True,  help="Path to site YAML config.")
    p.add_argument("--sub",       required=True,  help="Subject ID (e.g. sub-SK or SK).")
    p.add_argument("--mask",      required=True,  help="MNI-space mask NIfTI to warp.")
    p.add_argument("--label",     required=True,  help="Short label used in output filenames.")
    p.add_argument("--threshold", type=float, default=0.0,
                   help="Voxel threshold applied to mask for CoM and visualisation.")
    p.add_argument("--transform", default="SyN",
                   choices=["Affine", "SyN", "SyNCC"],
                   help="ANTs registration type.")
    p.add_argument("--interpolator", default="nearestNeighbor",
                   choices=["nearestNeighbor", "linear", "gaussian", "bspline"],
                   help="Interpolation used when warping the mask.")
    return p.parse_args(argv)


def run(args: argparse.Namespace) -> None:
    import ants
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nilearn import plotting
    from templateflow.api import get as tf_get

    # ------------------------------------------------------------------ paths
    cfg         = load_site_config(args.site)
    data_dir    = resolve_data_dir(cfg)
    _, sub_bare = normalise_sub_id(args.sub)
    sub_dir     = data_dir / f"sub-{sub_bare}"
    t1_path     = find_t1(sub_dir, sub_bare)
    sub_id_full = f"sub-{sub_bare}"

    t1_mni_paths = tf_get("MNI152NLin2009cAsym", resolution=1, suffix="T1w", extension="nii.gz")
    t1_mni_path  = str([p for p in t1_mni_paths if "desc-brain" not in str(p)][0])

    transforms_dir   = sub_dir / "ants_transforms"
    native_mask_path = sub_dir / f"{sub_id_full}_{args.label}_mask_native.nii.gz"
    fig_dir          = sub_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    print(f"Subject:      {sub_id_full}")
    print(f"T1 native:    {t1_path}")
    print(f"MNI template: {t1_mni_path}")
    print(f"Mask (MNI):   {args.mask}")

    # -------------------------------------------------------- Step 3a: register
    t1_native_ras, _, reg = register_mni_to_native(
        t1_native_path=t1_path,
        t1_mni_path=t1_mni_path,
        output_dir=transforms_dir,
        sub_id=sub_id_full,
        type_of_transform=args.transform,
    )

    # ----------------------------------------- Step 3b: apply transform + save
    t1_native_orig = ants.image_read(str(t1_path))
    mask_native    = apply_inverse_transform(
        mask_mni_path=args.mask,
        reg=reg,
        t1_native_ras=t1_native_ras,
        t1_native_orig=t1_native_orig,
        output_path=native_mask_path,
        interpolator=args.interpolator,
        mask_brain=True,
    )

    n_vox = int((mask_native.numpy() > args.threshold).sum())
    print(f"Native mask voxels above threshold={args.threshold}: {n_vox}")

    # --------------------------------------------------- Step 3c: visualise
    fig_path = fig_dir / f"{sub_id_full}_{args.label}_native_overlay.png"
    visualize_mask_native(
        mask_native=mask_native,
        t1_native=t1_native_orig,
        target_label=args.label,
        output_path=fig_path,
        z_threshold=args.threshold,
    )

    reg_fig_path = fig_dir / f"{sub_id_full}_MNI2native_regcheck.png"
    reg_fig = plotting.plot_anat(
        anat_img=ants_to_nib(reg["warpedmovout"]),
        bg_img=ants_to_nib(t1_native_ras),
        display_mode="ortho",
        draw_cross=False,
        title="Registration QC: warped MNI template on native T1",
        dim=-1,
    )
    reg_fig.savefig(str(reg_fig_path), dpi=150)
    plt.close("all")
    print(f"Reg QC figure: {reg_fig_path}")

    # --------------------------------------------------- Step 3d: CoM
    com_mm, com_vox = compute_com_native(mask_native, z_threshold=args.threshold)

    print()
    print("=" * 50)
    print(f"Target:           {args.label}")
    print(f"Subject:          {sub_id_full}")
    print(f"CoM (native, mm): x={com_mm[0]:.2f}  y={com_mm[1]:.2f}  z={com_mm[2]:.2f}")
    print(f"CoM (voxel):      i={com_vox[0]:.1f}  j={com_vox[1]:.1f}  k={com_vox[2]:.1f}")
    print("=" * 50)


def main() -> None:
    args = _parse_args()
    run(args)


if __name__ == "__main__":
    main()
