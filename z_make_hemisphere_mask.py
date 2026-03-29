"""
Generate MNI_hemispheres_BN_1mm.nii.gz from BN atlas.
L=1, R=2, midline/unassigned=0.
Output: masks/standardized/MNI_hemispheres_BN_1mm.nii.gz
"""
import os
import numpy as np
import nibabel as nib
from pathlib import Path

BN_ROOT = Path(os.environ["NILEARN_DATA"]) / "bn"
bn_atlas_path = BN_ROOT / "BN_Atlas_246_1mm.nii.gz"
bn_lut_path   = BN_ROOT / "BN_Atlas_246_LUT.txt"

print(f"BN atlas: {bn_atlas_path.exists()}")
print(f"BN LUT:   {bn_lut_path.exists()}")

bn_lut   = np.loadtxt(str(bn_lut_path), dtype=str)
bn_ids   = bn_lut[:, 0].astype(int)
bn_names = bn_lut[:, 1].tolist()
left_ids  = [int(idx) for idx, name in zip(bn_ids, bn_names) if name.endswith("_L")]
right_ids = [int(idx) for idx, name in zip(bn_ids, bn_names) if name.endswith("_R")]
print(f"Left labels: {len(left_ids)}, Right labels: {len(right_ids)}")

bn_img  = nib.as_closest_canonical(nib.load(str(bn_atlas_path)))
bn_data = bn_img.get_fdata().astype(int)

hemi = np.zeros_like(bn_data, dtype=np.uint8)
for idx in left_ids:
    hemi[bn_data == idx] = 1
for idx in right_ids:
    hemi[bn_data == idx] = 2

print(f"L voxels: {(hemi==1).sum()}, R voxels: {(hemi==2).sum()}, unassigned: {(hemi==0).sum()}")

out_path = Path(__file__).parent / "masks" / "standardized" / "MNI_hemispheres_BN_1mm.nii.gz"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_img = nib.Nifti1Image(hemi, bn_img.affine, bn_img.header)
out_img.set_data_dtype(np.uint8)
nib.save(out_img, str(out_path))
print(f"Saved: {out_path.name}  ({out_path.stat().st_size / 1e6:.2f} MB)")
