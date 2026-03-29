
### LIBRARIES/PACKAGES
import os
import sys
import glob
import re
import shutil
import pickle
import pprint
import math
#import pyinspect as pi
from collections import Counter, OrderedDict
from itertools import chain
from IPython.core.debugger import set_trace

import numpy as np
import pandas as pd
from pathlib import Path
import scipy
import scipy.io
import scipy.ndimage as ndi

import cv2
import pydicom
import ants
import nibabel as nib
from nibabel.orientations import io_orientation, axcodes2ornt, ornt_transform, apply_orientation
from nipype.interfaces.spm import NewSegment
from nipype.interfaces.matlab import MatlabCommand

### PLOTTING?
import matplotlib.pyplot as plt
import plotly
import plotly.graph_objs as go
from plotly.offline import download_plotlyjs, init_notebook_mode, iplot
import ipywidgets as widgets
plotly.offline.init_notebook_mode()

# ### CONFIGURATIONS ----------------------------------------------------------------
def configure_mri_env():
    # MAIN
    DIR_MAIN = Path.home() / 'Dropbox (Personal)' / 'w_SCRIPTS'
    
    ### SPM
    DIR_SPM = DIR_MAIN.parent / "w_ONGOINGMFILES64" / "w_OTHERS" / "spm12"
    DIR_TMP = DIR_SPM / "tpm" / "TPM.nii"
    MatlabCommand.set_default_paths(DIR_SPM)
    MatlabCommand.set_default_matlab_cmd("/Applications/MATLAB_R2021b.app/bin/matlab -nodesktop -nosplash")
    #MatlabCommand.set_default_matlab_cmd("/Applications/MATLAB_R2019b.app/bin/matlab -nodesktop -nosplash")
    return locals()

# ### FUNCTIONS ----------------------------------------------------------------
# -force to be 3d (index or average over 4th dim)
def load_as_3d(path):
    """
    Load an image as a proper 3D ANTs image.

    - If 4D, extract volume 0 (do NOT average)
    - If 3D, return as-is
    """
    from pathlib import Path
    import ants
    import numpy as np

    path = Path(path)
    img = ants.image_read(str(path))
    
    if img.dimension == 4:
        print(f"Converting 4D image to 3D: {path.name} with shape {img.shape}")
        
        data = img.numpy()[..., 0]  # Extract only the first volume
        print(" → Extracting first volume only (no averaging)")

        origin = tuple(img.origin[:3])
        spacing = tuple(img.spacing[:3])
        direction = np.array(img.direction)[:3, :3]

        return ants.from_numpy(
            data,
            origin=origin,
            spacing=spacing,
            direction=direction
        )

    elif img.dimension == 3:
        return img

    else:
        raise ValueError(f"Unsupported image dimension: {img.dimension}")

# # -adjust orientation of images
# def reorient_to_ras(img):
#     """Reorients ANTs image to RAS+ using nibabel affine as fallback"""
#     import nibabel as nib
#     import tempfile
#     import ants

#     with tempfile.NamedTemporaryFile(suffix=".nii.gz") as tmpfile:
#         ants.image_write(img, tmpfile.name)
#         nib_img = nib.load(tmpfile.name)
#         nib_img = nib.as_closest_canonical(nib_img)  # RAS+
#         nib.save(nib_img, tmpfile.name)
#         return ants.image_read(tmpfile.name)
    
# -for visualization
def ants_to_nib(ants_img):
    """Convert an ANTsImage to a nibabel Nifti1Image."""
    data = ants_img.numpy()
    affine = np.eye(4)
    affine[:3, :3] = np.dot(np.diag(ants_img.spacing), ants_img.direction)
    affine[:3, 3] = ants_img.origin
    return nib.Nifti1Image(data, affine)


# https://antspy.readthedocs.io/en/v0.4.2/_modules/ants/utils/convert_nibabel.html
def nifti_to_ants(nib_image):
    """
    Convert a Nibabel Nifti1Image to an ANTsPy ANTsImage, preserving orientation.
    """
    data = np.asanyarray(nib_image.dataobj)  # safer than get_data()
    ndim = data.ndim
    if ndim < 3:
        raise ValueError("NIfTI image must be at least 3D.")

    affine = nib_image.affine
    spacing = nib_image.header.get_zooms()[:ndim]
    origin = affine[:3, 3]
    direction = affine[:3, :3] / spacing[:3]

    ants_image = ants.from_numpy(
        data.astype(np.float32),  # safe dtype
        origin=origin.tolist(),
        spacing=spacing,
        direction=direction
    )
    return ants_image

def print_img_info(img):
    """
    Display image properties information.
    """
    if isinstance(img, nib.Nifti1Image):
        data = img.get_fdata()
        affine = img.affine
        print(f"  shape    = {data.shape}")
        print(f"  affine   =\n{affine}")
        spacing = np.sqrt((affine[:3, :3] ** 2).sum(axis=0))
        print(f"  spacing  = {spacing}")
        print(f"  origin   = {affine[:3, 3]}")
        print(f"  direction= ~from affine")
    elif isinstance(img, ants.ANTsImage):
        print(f"  shape    = {img.shape}")
        print(f"  spacing  = {img.spacing}")
        print(f"  origin   = {img.origin}")
        print(f"  direction= \n{img.direction}")
    else:
        print("  Unsupported image type")


def crop_image(img, x_range, y_range, z_range):
    """
    Crop a 3D NIfTI or ANTs image with updated affine/origin.

    Parameters:
    - img: nibabel.Nifti1Image or ants.ANTsImage
    - x_range, y_range, z_range: Tuples specifying voxel range to crop

    Returns:
    - Cropped image in the same format (nibabel or ANTs)
    """
    if isinstance(img, nib.Nifti1Image):
        data = img.get_fdata()
        cropped = data[x_range[0]:x_range[1], y_range[0]:y_range[1], z_range[0]:z_range[1]]

        affine = img.affine.copy()
        offset = np.dot(affine[:3, :3], [x_range[0], y_range[0], z_range[0]])
        affine[:3, 3] += offset

        return nib.Nifti1Image(cropped, affine, img.header)

    elif isinstance(img, ants.ANTsImage):
        arr = img.numpy()
        cropped = arr[x_range[0]:x_range[1], y_range[0]:y_range[1], z_range[0]:z_range[1]]

        new_origin = np.array(img.origin) + np.dot(img.direction, np.array([
            x_range[0] * img.spacing[0],
            y_range[0] * img.spacing[1],
            z_range[0] * img.spacing[2],
        ]))

        return ants.from_numpy(
            cropped.astype(np.float32),
            origin=new_origin.tolist(),
            spacing=img.spacing,
            direction=img.direction
        )

    else:
        raise TypeError("Unsupported image type. Must be nibabel.Nifti1Image or ants.ANTsImage")


# Functions emulating Xin's segmentation/simulation code for TUS
def allocatelabel_Xin(file, dlabel, threshold=0.1):
    """
    Thresholds a tissue probability map and assigns a discrete label.

    Parameters:
    - file (str or Path): Path to the NIfTI file containing the probability map (e.g., c1*.nii)
    - dlabel (int): Integer label to assign where the threshold is exceeded (e.g., 1 = GM)
    - threshold (float): Minimum probability value to be considered as tissue (default: 0.1)

    Returns:
    - labeled (ndarray): 3D array with voxels labeled as `dlabel` if above threshold, 0 otherwise
    - affine (ndarray): Affine matrix from the original NIfTI file
    - header (Nifti1Header): Header metadata from the original NIfTI file
    """
    img = nib.load(str(file))
    data = img.get_fdata()
    labeled = np.where(data > threshold, dlabel, 0)
    return labeled, img.affine, img.header

def plotImage_Xin(img, title='', scale=1.0):
    """
    Displays a 2D image or a single slice from a 3D volume using Plotly.

    Parameters:
    - img (ndarray): 2D image or 3D volume (numpy array)
    - title (str): Optional title for the plot
    - scale (float): Scale factor for the display size (default: 1.0)

    Behavior:
    - If `img` is 3D, shows the middle axial slice.
    - Image is flipped and transposed to match standard axial view.
    """
    if img.ndim == 3:
        img = img[:, :, img.shape[2] // 2]
    
    img_display = np.flipud(img.T)
    
    row, col = img_display.shape
    d = [go.Heatmap(z=img_display, x=np.arange(col), y=np.arange(row))]
    height = 600 * scale
    width = height * (col / row)
    layout = go.Layout(
        title=title,
        autosize=True,
        width=width,
        height=height,
    )
    fig = go.Figure(data=d, layout=layout)
    iplot(fig, show_link=False)

def remove_small_clusters_Xin(image_slice, threshold_area=20):
    """
    Removes small connected components from a 2D binary image slice.

    Parameters:
    - image_slice (ndarray): 2D binary image slice (e.g., a mask)
    - threshold_area (int): Minimum area in pixels to retain a cluster

    Returns:
    - cleaned_slice (ndarray): 2D image with small clusters removed
    """
    binary = (image_slice > 0).astype(np.uint8) * 255
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

    mask = np.zeros_like(labels, dtype=np.uint8)
    for i in range(1, num_labels):  # Skip background (label 0)
        if stats[i, cv2.CC_STAT_AREA] > threshold_area:
            mask[labels == i] = 1
    return (image_slice * mask).astype(image_slice.dtype)


def remove_small_clusters_3d_Xin(volume, label=5, min_size=100):
    mask = (volume == label)
    labeled, num = ndi.label(mask)
    sizes = ndi.sum(mask, labeled, range(1, num+1))
    
    cleaned = volume.copy()
    for i, size in enumerate(sizes, start=1):
        if size < min_size:
            cleaned[labeled == i] = 0
    return cleaned

### List of functions for from mri_python import *
__all__ = [
    "configure_mri_env",  
    "load_as_3d",
    "ants_to_nib",
    "nifti_to_ants",
    "print_img_info",
    "crop_image",
    "allocatelabel_Xin",
    "plotImage_Xin",
    "remove_small_clusters_Xin",
    "remove_small_clusters_3d_Xin"
]