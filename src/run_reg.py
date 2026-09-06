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
    {sub_id_full}_{mask_label}_mask.nii.gz
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
    fig_dir_for,
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
    reuse_transforms: bool = True,
    lr_split: bool = True,
    hemisphere_split: bool = False,
) -> None:
    """Run inverse registration for a single subject."""
    import ants
    import nibabel as nib
    import numpy as np
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
    fig_dir = fig_dir_for(sub_dir)          # figures/registration
    fig_dir.mkdir(parents=True, exist_ok=True)

    native_mask_path = sub_dir / f"{sub_id_full}_{mask_label}_mask.nii.gz"

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
    # The warp depends on the subject, not on the mask, so registering again for
    # every mask is wasted work: six masks across two subjects meant twelve SyN
    # runs where two would do.  Reuse what is already on disk unless told not to.
    outprefix = str(transforms_dir / f"{sub_id_full}_MNI2native_")
    _warp_path = f"{outprefix}1Warp.nii.gz"
    _aff_path  = f"{outprefix}0GenericAffine.mat"
    _have = Path(_warp_path).is_file() and Path(_aff_path).is_file()
    if reuse_transforms and _have:
        # ANTs orders fwdtransforms warp-first, affine-second.
        xfm_override = [_warp_path, _aff_path]
        reg = None
        print(f"  Reusing transforms in {transforms_dir.name}/ "
              f"(pass --no-reuse-transforms to re-register)")
    elif ants_type in ("SyN", "SyNCC"):
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
    if reg is not None:
        xfm_override = None
        print(f"  Registration complete. Transforms: {reg['fwdtransforms']}")

    # --- Apply transform to mask -------------------------------------------------
    mask_native = apply_inverse_transform(
        mask_mni_path=mask_path,
        reg=reg,
        transform_list_override=xfm_override,
        t1_native_ras=t1_native_ras,
        t1_native_orig=t1_native_orig,
        output_path=native_mask_path,
        interpolator="nearestNeighbor",
        mask_brain=True,
    )
    n_vox = int((mask_native.numpy() > z_threshold).sum())
    print(f"  Native mask saved: {native_mask_path}")
    print(f"  Voxels above z={z_threshold}: {n_vox}")

    # --- L/R hemisphere split ----------------------------------------------------
    # step03's notebook does this (LR_SPLIT); the batch runner did not, so
    # bilateral masks came out of a batch run with no _L / _R to target.
    if lr_split:
        # The hemisphere map is only loaded if it is actually going to be used.
        # It used to be loaded unconditionally and its absence skipped the whole
        # split, so moving it into aux/ silently stopped every target being
        # split at all -- while the x-sign path, which is now the default, does
        # not need it.
        _hemi = Path(mask_path).parent / "aux" / "MNI_hemispheres_BN_1mm.nii.gz"
        if not _hemi.is_file():
            _hemi = Path(mask_path).parent / "MNI_hemispheres_BN_1mm.nii.gz"

        def _hemisphere_parts():
            if not _hemi.is_file():
                print(f"  [warn] hemisphere map not found ({_hemi.name})")
                return None
            _xfm = xfm_override if reg is None else reg["fwdtransforms"]
            hemi_ras = ants.apply_transforms(
                fixed=t1_native_ras, moving=ants.image_read(str(_hemi)),
                transformlist=_xfm, interpolator="nearestNeighbor")
            _m = ants.resample_image_to_target(mask_native, t1_native_ras).numpy()
            _h = hemi_ras.numpy().astype(int)

            def _to_orig(arr):
                img = ants.from_numpy(arr.astype("float32"),
                                      origin=t1_native_ras.origin,
                                      spacing=t1_native_ras.spacing,
                                      direction=t1_native_ras.direction)
                return ants.resample_image_to_target(img, t1_native_orig)

            return {sd: _to_orig(_m * (_h == cd)) for sd, cd in (("L", 1), ("R", 2))}

        if True:
            # Split on the sign of x, read from the saved NIfTI's own affine
            # with nibabel.
            #
            # NOT the Brainnetome hemisphere map, which was the original method:
            # it leaves voxels unassigned wherever none of its 246 parcels
            # reach, and those holes are not where one would guess. LC lands
            # entirely in one, so both sides came back empty. Entorhinal cortex
            # loses 18-20 % of its voxels the same way, at x = -25..-11 mm --
            # and silently, since the split still returns something. The map has
            # no midline gap to blame: its labels span -71..+1 and -1..+73 mm
            # and overlap by 2 mm, with 7635 labelled voxels inside |x| < 1 mm.
            #
            # Deriving x from the ANTs origin and spacing instead of the affine
            # put the right nucleus in the _L file: ANTs stores images LPS
            # internally, so origin[0] + i * spacing[0] is not the RAS x.
            #
            # Refused when the mask reaches the midline, where the sign of x
            # would cut through a structure rather than between its halves. The
            # hemisphere map is then the only option left, and --hemisphere-split
            # asks for it explicitly.
            _img = nib.load(str(native_mask_path))
            _dat = _img.get_fdata()
            _idx = np.array(np.nonzero(_dat > z_threshold)).T
            _xv = nib.affines.apply_affine(_img.affine, _idx)[:, 0] if _idx.size else np.array([])
            _use_x = (not hemisphere_split) and _xv.size and np.abs(_xv).min() >= 1.0

            if _use_x:
                print(f"  split on sign of x "
                      f"(nearest voxel {np.abs(_xv).min():.1f} mm off midline)")
                _grid = np.indices(_dat.shape).reshape(3, -1).T
                _xg = nib.affines.apply_affine(
                    _img.affine, _grid)[:, 0].reshape(_dat.shape)
                _parts = {"L": (_dat * (_xg < 0)), "R": (_dat * (_xg > 0))}
                for _side, _arr in _parts.items():
                    _out = sub_dir / f"{sub_id_full}_{mask_label}_mask-{_side}.nii.gz"
                    nib.save(nib.Nifti1Image(_arr.astype("float32"),
                                             _img.affine, _img.header), str(_out))
                    print(f"  {_side}: {int((_arr > z_threshold).sum()):6d} "
                          f"voxels -> {_out.name}")
            else:
                if not hemisphere_split:
                    print("  [note] mask reaches the midline; falling back to the "
                          "Brainnetome hemisphere map, which may drop voxels it "
                          "does not cover")
                _parts = _hemisphere_parts()
                if _parts is None:
                    print("  [warn] no split written")
                    _parts = {}
                _kept = 0
                for _side, _img_side in _parts.items():
                    _n = int((_img_side.numpy() > z_threshold).sum())
                    _kept += _n
                    _out = sub_dir / f"{sub_id_full}_{mask_label}_mask-{_side}.nii.gz"
                    ants.image_write(_img_side, str(_out))
                    print(f"  {_side}: {_n:6d} voxels -> {_out.name}")
                _tot = int((_dat > z_threshold).sum())
                if _kept < _tot:
                    print(f"  [warn] hemisphere map covers {_kept} of {_tot} voxels "
                          f"({_tot - _kept} dropped, {100 * (_tot - _kept) / max(_tot, 1):.0f} %)")

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
    # warpedmovout only comes back from a live registration.  When the
    # transforms were reused, apply them to the template to get the same
    # image — the regcheck figure matters more, not less, when the warp was
    # not computed in this run.
    _warp = (reg["warpedmovout"] if reg is not None else
             ants.apply_transforms(fixed=t1_native_ras, moving=t1_mni_ready,
                                   transformlist=xfm_override))
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
        "--hemisphere-split", action="store_true",
        help="Split with the Brainnetome hemisphere map instead of the sign of "
             "x. The map has parcellation coverage holes and drops voxels "
             "silently -- 18-20 %% of entorhinal cortex, all of LC -- so it is "
             "only worth using for a mask that genuinely crosses the midline.",
    )
    p.add_argument(
        "--no-lr-split", dest="lr_split", action="store_false", default=True,
        help="Skip the left/right hemisphere split. On by default, matching "
             "step03's LR_SPLIT.",
    )
    p.add_argument(
        "--no-reuse-transforms", dest="reuse_transforms",
        action="store_false", default=True,
        help="Re-run ANTs even when this subject's transforms already exist. "
             "The warp depends only on the subject, so reuse is the default.",
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
                reuse_transforms=args.reuse_transforms,
                lr_split=args.lr_split,
                hemisphere_split=args.hemisphere_split,
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
