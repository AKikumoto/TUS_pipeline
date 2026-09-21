"""
Generate PNG reference cards for pipeline steps using matplotlib.

Convention
----------
Each step has two companion files in z_references/:
  step[N]_reference.py   — HTML card rendered inside the notebook
  step[N]_reference.png  — static PNG embedded in the Markdown header

This script generates all step PNGs.  Add a new section (and update OUT)
for each new step as it is introduced.

Run from any directory:
    python z_references/generate_png.py

Requires: matplotlib (available in mri environment)
"""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

HERE = Path(__file__).parent.resolve()
OUT  = HERE / "step3_reference.png"

C = {
    "teal_bg":   "#E1F5EE", "teal_fg":   "#085041",
    "purple_bg": "#EEEDFE", "purple_fg": "#3C3489",
    "amber_bg":  "#FAEEDA", "amber_fg":  "#633806",
    "green_bg":  "#EAF3DE", "green_fg":  "#27500A",
    "card_bg":   "#F8F8F8", "border":    "#E0E0E0",
    "title":     "#1A1A1A", "sub":       "#555555",
    "note":      "#888888",
    "badge_bg":  "#E1F5EE", "badge_fg":  "#085041",
}

FIG_W, FIG_H = 8.6, 9.2
DPI = 130


def card(ax, x, y, w, h):
    ax.add_patch(patches.FancyBboxPatch(
        (x, y - h), w, h, boxstyle="round,pad=0.04",
        facecolor=C["card_bg"], edgecolor=C["border"], linewidth=0.8, zorder=2))


def hline(ax, x, y, w):
    ax.plot([x, x + w], [y, y], color=C["border"], lw=0.6, zorder=3)


def section_title(ax, x, y, text):
    ax.text(x, y, text, fontsize=8, fontweight="bold",
            color=C["sub"], va="top", zorder=4)


def row(ax, x, y, w, cells, widths, header=False, last=False):
    ROW_H = 0.22
    bx = x
    for cell_w, (text, is_code, bdg) in zip(widths, cells):
        if header:
            ax.text(bx + 0.06, y - 0.05, text, fontsize=7.5,
                    fontweight="bold", color=C["sub"], va="top", zorder=4)
        elif is_code:
            ax.text(bx + 0.06, y - 0.05, text, fontsize=7.5,
                    fontfamily="monospace", color="#c7254e", va="top", zorder=4)
            if bdg:
                ax.text(bx + 0.06 + len(text) * 0.052 + 0.05, y - 0.08,
                        f" {bdg} ", fontsize=6.2, color=C["badge_fg"],
                        bbox=dict(boxstyle="round,pad=0.12",
                                  facecolor=C["badge_bg"], edgecolor="none"),
                        va="center", zorder=4)
        else:
            ax.text(bx + 0.06, y - 0.05, text, fontsize=7.5,
                    color=C["title"], va="top", zorder=4)
        bx += cell_w
    if not last:
        hline(ax, x, y - ROW_H, w)
    return y - ROW_H


fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor="white")
ax  = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.set_facecolor("white")
ax.axis("off")

M = 0.30
W = FIG_W - M - 0.20
y = FIG_H - 0.30

# ── Title ─────────────────────────────────────────────────────────────────────
ax.text(M, y, "Step 3 — Inverse registration",
        fontsize=14, fontweight="bold", color=C["title"], va="top")
ax.text(M + 4.5, y - 0.02, "MNI → native space",
        fontsize=10, color=C["note"], va="top")
y -= 0.52

# ── Phase bar ─────────────────────────────────────────────────────────────────
phases = [
    ("① Init",         "Load config\nLoad T1",                "teal"),
    ("② Registration", "Intensity norm\nRegister\nApply warp", "purple"),
    ("③ QC",           "Mask overlay\nReg check",              "amber"),
    ("④ Output",       "CoM / peak\n→ BrainSight",            "green"),
]
ph, pw = 0.74, W / 4
for i, (lbl, sub, col) in enumerate(phases):
    bx = M + i * pw
    ax.add_patch(patches.FancyBboxPatch(
        (bx + 0.04, y - ph), pw - 0.08, ph,
        boxstyle="round,pad=0.04",
        facecolor=C[f"{col}_bg"], edgecolor=C["border"], linewidth=0.7, zorder=2))
    ax.text(bx + pw / 2, y - 0.13, lbl, ha="center", va="top",
            fontsize=8.5, fontweight="bold", color=C[f"{col}_fg"], zorder=3)
    ax.text(bx + pw / 2, y - 0.37, sub, ha="center", va="top",
            fontsize=7.5, color=C[f"{col}_fg"], linespacing=1.5, zorder=3)
y -= ph + 0.18

# ── REGISTRATION_MODE ─────────────────────────────────────────────────────────
h1 = 0.87
card(ax, M, y, W, h1)
section_title(ax, M + 0.12, y - 0.10, "REGISTRATION_MODE")
c1 = [1.5, 3.2, 3.0]
y2 = y - 0.32
y2 = row(ax, M+0.08, y2, W-0.16,
         [("Mode",False,None),("When to use",False,None),("Transform source",False,None)], c1, header=True)
y2 = row(ax, M+0.08, y2, W-0.16,
         [('"ants"',True,None),("No fmriprep; run ANTs from scratch",False,None),("Computed here → ants_transforms/",False,None)], c1)
y2 = row(ax, M+0.08, y2, W-0.16,
         [('"fmriprep"',True,None),("fmriprep already run; reuse warp",False,None),("fmriprep/sub-*/anat/*.h5",False,None)], c1, last=True)
y -= h1 + 0.14

# ── INTENSITY_NORM + REGISTRATION_TYPE ───────────────────────────────────────
half = (W - 0.12) / 2
h2 = 0.92
card(ax, M, y, half, h2)
section_title(ax, M + 0.12, y - 0.10, "INTENSITY_NORM  (ANTs only)")
c2 = [2.6, 1.3]
y3 = y - 0.32
y3 = row(ax, M+0.08, y3, half-0.08, [("Setting",False,None),("Best for",False,None)], c2, header=True)
y3 = row(ax, M+0.08, y3, half-0.08, [('"histogram_match"',True,"default"),("3T",False,None)], c2)
y3 = row(ax, M+0.08, y3, half-0.08, [('"imath_normalize"',True,None),("7T / LC",False,None)], c2)
y3 = row(ax, M+0.08, y3, half-0.08, [('"none"',True,None),("Quick test",False,None)], c2, last=True)

x2 = M + half + 0.12
card(ax, x2, y, half, h2)
section_title(ax, x2 + 0.12, y - 0.10, "REGISTRATION_TYPE  (ANTs only)")
c3 = [1.5, 2.4]
y4 = y - 0.32
y4 = row(ax, x2+0.08, y4, half-0.08, [("Setting",False,None),("Notes",False,None)], c3, header=True)
y4 = row(ax, x2+0.08, y4, half-0.08, [('"SyN"',True,"default"),("Fast; 3T aMCC / amygdala",False,None)], c3)
y4 = row(ax, x2+0.08, y4, half-0.08, [('"SyNCC"',True,None),("Slower; better for 7T LC",False,None)], c3, last=True)
y -= h2 + 0.14

# ── TARGET_MODE ───────────────────────────────────────────────────────────────
h3 = 0.87
card(ax, M, y, W, h3)
section_title(ax, M + 0.12, y - 0.10, "TARGET_MODE")
c4 = [1.5, 6.2]
y5 = y - 0.32
y5 = row(ax, M+0.08, y5, W-0.16, [("Setting",False,None),("Method",False,None)], c4, header=True)
y5 = row(ax, M+0.08, y5, W-0.16,
         [('"CoM"',True,"default"),("Centre of mass of thresholded native mask",False,None)], c4)
y5 = row(ax, M+0.08, y5, W-0.16,
         [('"peak_func"',True,None),("Peak voxel of functional map within mask — requires FUNC_MAP_FILE",False,None)], c4)
y5 = row(ax, M+0.08, y5, W-0.16,
         [('"skip"',True,None),("No coordinate computation (mask QC only)",False,None)], c4, last=True)
y -= h3 + 0.14

# ── Inputs + Outputs ──────────────────────────────────────────────────────────
h4 = 1.12
card(ax, M, y, half, h4)
section_title(ax, M + 0.12, y - 0.10, "Inputs required")
inputs = [
    (False, "Site YAML  config/sites/"),
    (False, "Native T1 NIfTI (auto via site config)"),
    (False, "MNI mask  masks/standardized/"),
    (True,  "  ↳ MNI152NLin2009cAsym 1 mm"),
    (True,  "fmriprep mode: *_xfm.h5"),
    (True,  "peak_func mode: MNI funcmap"),
]
for i, (dim, txt) in enumerate(inputs):
    ax.text(M + 0.20, y - 0.33 - i * 0.135, txt, fontsize=7.2,
            color=C["note"] if dim else C["title"], va="top", zorder=4)

card(ax, x2, y, half, h4)
section_title(ax, x2 + 0.12, y - 0.10, "Outputs")
outputs = [
    "*_mask_native.nii.gz",
    "*_native.nii.gz  (peak_func only)",
    "figures/*_native_overlay.png",
    "figures/*_regcheck.png  (ANTs only)",
]
for i, txt in enumerate(outputs):
    ax.text(x2 + 0.20, y - 0.33 - i * 0.165, txt, fontsize=7.2,
            color=C["title"], va="top", fontfamily="monospace", zorder=4)

# ── Save ──────────────────────────────────────────────────────────────────────
plt.savefig(str(OUT), dpi=DPI, bbox_inches="tight",
            facecolor="white", edgecolor="none")
plt.close()
print(f"Saved: {OUT}")
