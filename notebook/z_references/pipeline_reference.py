from IPython.display import HTML, display

HTML_CONTENT = """
<style>
.pip-wrap *{box-sizing:border-box}
.pip-wrap{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;color:#1a1a1a;max-width:860px;margin:0 auto}
.pip-card{background:#f8f8f8;border:1px solid #e0e0e0;border-radius:10px;padding:14px 16px;margin-bottom:10px}
.pip-sec-title{font-size:12px;font-weight:600;color:#555;margin:0 0 6px}
.pip-wrap table{width:100%;border-collapse:collapse;font-size:12px}
.pip-wrap th{text-align:left;color:#555;font-weight:600;padding:4px 8px;border-bottom:1px solid #e0e0e0}
.pip-wrap td{text-align:left;padding:4px 8px;border-bottom:1px solid #e0e0e0;color:#1a1a1a;vertical-align:top}
.pip-wrap tr:last-child td{border-bottom:none}
.pip-wrap code{font-family:'SFMono-Regular',Consolas,monospace;font-size:11px;background:#efefef;padding:1px 4px;border-radius:4px;color:#c7254e}
.pip-note{font-size:11px;color:#888;font-style:italic}
.pip-io-list{font-size:12px;margin:0;padding-left:16px;line-height:1.9;color:#1a1a1a}
.pip-title-row{display:flex;align-items:baseline;gap:8px;margin-bottom:10px}
.pip-title-row h3{margin:0;font-size:15px;font-weight:600;color:#1a1a1a}
.pip-title-row span{font-size:12px;color:#888}
.pip-row2{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
.pip-badge-par{display:inline-block;font-size:10px;font-weight:600;padding:1px 6px;border-radius:10px;background:#FFF3E0;color:#8B4000}
.pip-badge-req{display:inline-block;font-size:10px;font-weight:600;padding:1px 6px;border-radius:10px;background:#EEEDFE;color:#3C3489}
.pip-badge-ext{display:inline-block;font-size:10px;font-weight:600;padding:1px 6px;border-radius:10px;background:#F3F4F6;color:#555}
</style>

<div class="pip-wrap">

<div class="pip-title-row">
  <h3>TUS targeting pipeline</h3>
  <span>SimNIBS &#8594; masks &#8594; registration &#8594; PlanTUS &#8594; BabelBrain</span>
</div>

<!-- Pipeline SVG -->
<div class="pip-card" style="padding:20px 16px 16px">
<svg width="100%" viewBox="0 0 680 310" xmlns="http://www.w3.org/2000/svg">
<defs>
  <marker id="parr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M2 1L8 5L2 9" fill="none" stroke="#888" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </marker>
</defs>

<!-- ── Phase containers ── -->
<!-- Preprocessing (Steps 1+2) -->
<rect x="8" y="8" width="262" height="180" rx="10" fill="#F0FBF6" stroke="#9FE1CB" stroke-width="1" stroke-dasharray="5 3"/>
<text font-family="-apple-system,sans-serif" font-size="10" font-weight="600" x="139" y="22" text-anchor="middle" fill="#0F6E56">PREPROCESSING</text>

<!-- Targeting (Steps 3+4) -->
<rect x="282" y="8" width="262" height="180" rx="10" fill="#F4F3FE" stroke="#AFA9EC" stroke-width="1" stroke-dasharray="5 3"/>
<text font-family="-apple-system,sans-serif" font-size="10" font-weight="600" x="413" y="22" text-anchor="middle" fill="#534AB7">TARGETING</text>

<!-- Simulation (Step 5) -->
<rect x="556" y="8" width="116" height="180" rx="10" fill="#FFFBF0" stroke="#FAC775" stroke-width="1" stroke-dasharray="5 3"/>
<text font-family="-apple-system,sans-serif" font-size="10" font-weight="600" x="614" y="22" text-anchor="middle" fill="#854F0B">SIMULATION</text>

<!-- ── Step 1: Segmentation ── -->
<text font-family="-apple-system,sans-serif" font-size="10" font-weight="600" x="80" y="38" text-anchor="middle" fill="#888">Step 1</text>
<rect x="22" y="44" width="116" height="52" rx="7" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.8"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="600" x="80" y="64" text-anchor="middle" dominant-baseline="central" fill="#085041">Segmentation</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="80" y="82" text-anchor="middle" dominant-baseline="central" fill="#0F6E56">SimNIBS charm</text>
<text font-family="-apple-system,sans-serif" font-size="10" x="80" y="108" text-anchor="middle" fill="#888">m2m_{sub_id}/</text>

<!-- ── parallel OK badge ── -->
<rect x="144" y="62" width="68" height="16" rx="8" fill="#FFF3E0" stroke="#E8A235" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="9" font-weight="600" x="178" y="70" text-anchor="middle" dominant-baseline="central" fill="#8B4000">parallel OK</text>

<!-- ── Step 2: Mask prep ── -->
<text font-family="-apple-system,sans-serif" font-size="10" font-weight="600" x="208" y="38" text-anchor="middle" fill="#888">Step 2</text>
<rect x="152" y="44" width="106" height="52" rx="7" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.8"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="600" x="205" y="64" text-anchor="middle" dominant-baseline="central" fill="#085041">Mask prep</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="205" y="82" text-anchor="middle" dominant-baseline="central" fill="#0F6E56">MNI masks</text>
<text font-family="-apple-system,sans-serif" font-size="10" x="205" y="108" text-anchor="middle" fill="#888">*_mask_MNI.nii.gz</text>

<!-- ── Step 3: Inv. registration ── -->
<text font-family="-apple-system,sans-serif" font-size="10" font-weight="600" x="345" y="38" text-anchor="middle" fill="#888">Step 3</text>
<rect x="293" y="44" width="104" height="52" rx="7" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.8"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="600" x="345" y="62" text-anchor="middle" dominant-baseline="central" fill="#3C3489">Registration</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="345" y="80" text-anchor="middle" dominant-baseline="central" fill="#534AB7">MNI &#8594; native</text>
<text font-family="-apple-system,sans-serif" font-size="10" x="345" y="108" text-anchor="middle" fill="#888">*_mask_native.nii.gz</text>

<!-- ── Step 4: PlanTUS ── -->
<text font-family="-apple-system,sans-serif" font-size="10" font-weight="600" x="470" y="38" text-anchor="middle" fill="#888">Step 4</text>
<rect x="410" y="44" width="122" height="52" rx="7" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.8"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="600" x="471" y="62" text-anchor="middle" dominant-baseline="central" fill="#3C3489">PlanTUS</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="471" y="80" text-anchor="middle" dominant-baseline="central" fill="#534AB7">Transducer placement</text>
<text font-family="-apple-system,sans-serif" font-size="10" x="471" y="108" text-anchor="middle" fill="#888">*_brainsight.txt</text>

<!-- ── Step 5: BabelBrain ── -->
<text font-family="-apple-system,sans-serif" font-size="10" font-weight="600" x="614" y="38" text-anchor="middle" fill="#888">Step 5</text>
<rect x="566" y="44" width="96" height="52" rx="7" fill="#FAEEDA" stroke="#BA7517" stroke-width="0.8"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="600" x="614" y="62" text-anchor="middle" dominant-baseline="central" fill="#633806">BabelBrain</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="614" y="80" text-anchor="middle" dominant-baseline="central" fill="#854F0B">Acoustic + thermal</text>
<text font-family="-apple-system,sans-serif" font-size="10" x="614" y="108" text-anchor="middle" fill="#888">*_DataForSim.h5</text>

<!-- ── Arrows (main flow) ── -->
<!-- 1→3: m2m_dir dependency (dashed, via bottom) -->
<line x1="80" y1="112" x2="80" y2="148" stroke="#bbb" stroke-width="0.8" stroke-dasharray="4 3"/>
<line x1="80" y1="148" x2="345" y2="148" stroke="#bbb" stroke-width="0.8" stroke-dasharray="4 3"/>
<line x1="345" y1="148" x2="345" y2="98" stroke="#bbb" stroke-width="0.8" stroke-dasharray="4 3" marker-end="url(#parr)"/>
<text font-family="-apple-system,sans-serif" font-size="9" x="200" y="145" text-anchor="middle" fill="#aaa">m2m mesh</text>

<!-- 2→3: mask dependency (dashed) -->
<line x1="258" y1="70" x2="291" y2="70" stroke="#888" stroke-width="0.8" marker-end="url(#parr)"/>

<!-- 3→4: arrow -->
<line x1="397" y1="70" x2="408" y2="70" stroke="#888" stroke-width="0.8" marker-end="url(#parr)"/>

<!-- 1→4: m2m mesh dependency (dashed, via bottom deeper) -->
<line x1="80" y1="160" x2="80" y2="168" stroke="#bbb" stroke-width="0.8" stroke-dasharray="4 3"/>
<line x1="80" y1="168" x2="471" y2="168" stroke="#bbb" stroke-width="0.8" stroke-dasharray="4 3"/>
<line x1="471" y1="168" x2="471" y2="98" stroke="#bbb" stroke-width="0.8" stroke-dasharray="4 3" marker-end="url(#parr)"/>

<!-- 4→5: arrow -->
<line x1="532" y1="70" x2="564" y2="70" stroke="#888" stroke-width="0.8" marker-end="url(#parr)"/>

<!-- ── Legend ── -->
<rect x="8" y="198" width="652" height="1" fill="#e0e0e0"/>
<rect x="8" y="214" width="12" height="12" rx="3" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.8"/>
<text font-family="-apple-system,sans-serif" font-size="11" x="24" y="220" dominant-baseline="central" fill="#555">Preprocessing (Steps 1–2)</text>
<rect x="196" y="214" width="12" height="12" rx="3" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.8"/>
<text font-family="-apple-system,sans-serif" font-size="11" x="212" y="220" dominant-baseline="central" fill="#555">Targeting (Steps 3–4)</text>
<rect x="372" y="214" width="12" height="12" rx="3" fill="#FAEEDA" stroke="#BA7517" stroke-width="0.8"/>
<text font-family="-apple-system,sans-serif" font-size="11" x="388" y="220" dominant-baseline="central" fill="#555">Simulation (Step 5)</text>
<line x1="522" y1="220" x2="542" y2="220" stroke="#bbb" stroke-width="0.8" stroke-dasharray="4 3"/>
<text font-family="-apple-system,sans-serif" font-size="11" x="547" y="220" dominant-baseline="central" fill="#555">Data dependency</text>

<!-- ── Execution order note ── -->
<text font-family="-apple-system,sans-serif" font-size="10" x="8" y="248" fill="#888">Execution order: Steps 1 &amp; 2 can run in parallel &#8594; Step 3 requires 1+2 &#8594; Step 4 requires 1+3 &#8594; Step 5 requires 1+4</text>
</svg>
</div>

<!-- Step summary table -->
<div class="pip-card">
<p class="pip-sec-title">STEP SUMMARY</p>
<table>
  <tr>
    <th>Step</th><th>Notebook</th><th>Tool / method</th><th>Key output</th><th>Run time</th>
  </tr>
  <tr>
    <td><strong>1</strong></td>
    <td><code>step01_segmentation_simnibs.ipynb</code></td>
    <td>SimNIBS <code>charm</code></td>
    <td><code>m2m_{sub_id}/</code></td>
    <td>20–60 min</td>
  </tr>
  <tr>
    <td><strong>2</strong></td>
    <td><code>step02_prepare_masks.ipynb</code></td>
    <td>nibabel / nilearn / ANTs</td>
    <td><code>masks/standardized/*_mask_MNI.nii.gz</code></td>
    <td>&lt; 5 min</td>
  </tr>
  <tr>
    <td><strong>3</strong></td>
    <td><code>step03_inverse_registration.ipynb</code></td>
    <td>ANTs <code>SyN</code> / fmriprep warp</td>
    <td><code>{sub_dir}/*_mask_native.nii.gz</code></td>
    <td>5–20 min</td>
  </tr>
  <tr>
    <td><strong>4</strong></td>
    <td><code>step04_planTUS.ipynb</code></td>
    <td>PlanTUS + wb_view</td>
    <td><code>m2m_{sub_id}/*_brainsight.txt</code></td>
    <td>5–15 min</td>
  </tr>
  <tr>
    <td><strong>5</strong></td>
    <td><code>step05_babelbrain.ipynb</code><br><span style="font-size:11px;color:#888">or BabelBrain standalone (GUI)</span></td>
    <td>BabelBrain — GPU acoustic + thermal</td>
    <td><code>*_BabelViscoInput.nii.gz</code><br><code>*_DataForSim.h5</code><br><code>*_Thermal_*.h5</code></td>
    <td>10–60 min (GPU-dependent)</td>
  </tr>
</table>
<p style="font-size:11px;color:#888;margin:8px 0 0;font-style:italic">For batch processing across multiple subjects, see <code>README.md</code> → Batch Processing.</p>
</div>
<div class="pip-card">
  <p class="pip-sec-title">HOW TO USE — GENERAL</p>
  <table>
    <tr>
      <th style="width:28%">Step</th>
      <th>Instructions</th>
    </tr>
    <tr>
      <td><strong>1. Set up conda environment</strong></td>
      <td>
        Create and activate the <code>mri</code> environment once before first use:<br>
        <code>conda env create -f environment/mri_environment.yml</code><br>
        <code>conda activate mri</code><br>
        <span class="pip-note">Re-run <code>conda env update</code> if <code>mri_environment.yml</code> is updated.</span>
      </td>
    </tr>
    <tr>
      <td><strong>2. Install external software</strong></td>
      <td>
        The following tools must be installed separately (not via conda):<br>
        &bull; <strong>SimNIBS &#8805; 4.0</strong> — <a style="color:#185FA5;font-size:12px" href="https://simnibs.github.io">simnibs.github.io</a> (steps 1 &amp; 4)<br>
        &bull; <strong>Connectome Workbench (wb_view)</strong> — <a style="color:#185FA5;font-size:12px" href="https://www.humanconnectome.org/software/connectome-workbench">humanconnectome.org/software/connectome-workbench</a> (step 4)<br>
        &bull; <strong>FSL &#8805; 6.0</strong> — <a style="color:#185FA5;font-size:12px" href="https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation">fsl.fmrib.ox.ac.uk</a> (step 1 — <code>fslorient</code> for qform/sform fix)<br>
        &bull; <strong>PlanTUS</strong> — included in <code>PlanTUS/</code> directory; see <a style="color:#185FA5;font-size:12px" href="https://doi.org/10.1016/j.brs.2025.08.013">Lueckel et al. 2025</a> (step 4)<br>
        &bull; <strong>BabelBrain</strong> (standalone app) — <a style="color:#185FA5;font-size:12px" href="https://github.com/ProteusMRIgHIFU/BabelBrain/releases">github.com/ProteusMRIgHIFU/BabelBrain/releases</a> (step 5 — acoustic &amp; thermal simulation)<br>
        <span class="pip-note">BabelBrain: download the DMG for macOS (ARM64 for M1/M2/M3, Intel X64 otherwise). GPU with Metal/OpenCL/CUDA required; Apple Silicon (M1+, 16 GB+) is recommended.</span>
      </td>
    </tr>
    <tr>
      <td><strong>3. Clone the repository</strong></td>
      <td>
        The pipeline code is maintained in <a style="color:#185FA5;font-size:12px" href="https://github.com/AKikumoto/TUS_pipeline">github.com/AKikumoto/TUS_pipeline</a> and continuously synced from <code>CFDLab_wiki</code>.<br>
        <code>git clone https://github.com/AKikumoto/TUS_pipeline.git</code>
      </td>
    </tr>
    <tr>
      <td><strong>4. Create a site config YAML</strong></td>
      <td>
        Copy the template and fill in paths for your machine:<br>
        <code>cp config/sites/template_site.yaml config/sites/site_&lt;SITE&gt;_&lt;STATION&gt;.yaml</code><br><br>
        Key fields to update: <code>data_root</code>, <code>fsl_bin</code>, <code>freesurfer_home</code>, <code>workbench_bin</code>, <code>transducer</code>.<br>
        <span class="pip-note">Subject data (<code>m2m_*/</code>, T1w NIfTI, etc.) are stored separately and are <strong>not</strong> tracked in this repository. Point <code>data_root</code> to your local data directory.</span><br>
        <span class="pip-note">Examples: <code>site_RIKEN_AK.yaml</code> (local Mac), <code>site_Brown_Oscar_AK.yaml</code> (Oscar HPC). See <code>config/HPC/</code> for HPC-specific setup guides.</span>
      </td>
    </tr>
  </table>
</div>

<!-- Acknowledgements & References -->
<div class="pip-card" style="margin-bottom:0">
  <p class="pip-sec-title">DEPENDENCIES, ACKNOWLEDGEMENTS &amp; REFERENCES</p>
  <p style="font-size:12px;color:#555;margin:0 0 10px">If you use this pipeline, please cite the relevant tools for each step used.</p>
  <table>
    <tr><th style="width:14%">Step</th><th style="width:18%">Tool</th><th style="width:32%">Reference</th><th>DOI / Link</th></tr>

    <tr><td colspan="4" style="background:#f3f3f3;font-size:10px;font-weight:600;color:#555;padding:4px 8px">PREPROCESSING — TOOLS</td></tr>
    <tr>
      <td>Step 1</td><td>SimNIBS / charm</td>
      <td>Puonti et al. (2020) <em>NeuroImage</em> 219:117109</td>
      <td><a style="color:#185FA5;font-size:11px" href="https://doi.org/10.1016/j.neuroimage.2020.116987">doi:10.1016/j.neuroimage.2020.116987</a> &nbsp;&#124;&nbsp; <a style="color:#185FA5;font-size:11px" href="https://simnibs.github.io/simnibs/build/html/tutorial/head_meshing.html">head meshing tutorial</a></td>
    </tr>
    <tr>
      <td>Step 1</td><td>FSL / fslorient</td>
      <td>Jenkinson et al. (2012) <em>NeuroImage</em> 62(2):782–790</td>
      <td><a style="color:#185FA5;font-size:11px" href="https://fsl.fmrib.ox.ac.uk/fsl/docs/#/utilities/fslorient">fsl.fmrib.ox.ac.uk/fsl/docs</a></td>
    </tr>
    <tr>
      <td>Steps 2–3</td><td>ANTs / antspyx</td>
      <td>Avants et al. (2011) <em>NeuroImage</em> 54(3):2033–2044</td>
      <td><a style="color:#185FA5;font-size:11px" href="https://doi.org/10.1016/j.neuroimage.2010.09.025">doi:10.1016/j.neuroimage.2010.09.025</a> &nbsp;&#124;&nbsp; <a style="color:#185FA5;font-size:11px" href="https://github.com/ANTsX/ANTsPy">github.com/ANTsX/ANTsPy</a></td>
    </tr>
    <tr>
      <td>Steps 2–3</td><td>templateflow</td>
      <td>Ciric et al. (2022) <em>Nature Methods</em> 19:1568–1571</td>
      <td><a style="color:#185FA5;font-size:11px" href="https://doi.org/10.1038/s41592-022-01681-2">doi:10.1038/s41592-022-01681-2</a></td>
    </tr>
    <tr>
      <td>Steps 2–3</td><td>nilearn</td>
      <td>Abraham et al. (2014) <em>Front. Neuroinform.</em> 8:14</td>
      <td><a style="color:#185FA5;font-size:11px" href="https://doi.org/10.3389/fninf.2014.00014">doi:10.3389/fninf.2014.00014</a></td>
    </tr>

    <tr><td colspan="4" style="background:#EAF3DE;font-size:10px;font-weight:600;color:#27500A;padding:4px 8px">PREPROCESSING — AVAILABLE MASKS (Step 2, cite as applicable) &nbsp;<span style="font-weight:400;font-style:italic;color:#4a7a2a">— examples only; any NIfTI in MNI152NLin2009cAsym 1 mm space can be added to <code style="background:none;color:#4a7a2a">masks/standardized/</code> and used as a target</span></td></tr>
    <tr>
      <td><code>aMCC_NeuroSynthTopic112</code></td><td>NeuroSynth v5</td>
      <td>Yarkoni et al. (2011) <em>Nature Methods</em> 8:665–670</td>
      <td><a style="color:#185FA5;font-size:11px" href="https://doi.org/10.1038/nmeth.1635">doi:10.1038/nmeth.1635</a></td>
    </tr>
    <tr>
      <td><code>BST_BNST, Ce_CeA</code><br><span style="font-size:10px;color:#888">+ BN atlas masks (A13, dIa, dId, dIg, vIa, rHipp)</span></td><td>Brainnetome atlas</td>
      <td>Fan et al. (2016) <em>Cerebral Cortex</em> 26(8):3508–3526</td>
      <td><a style="color:#185FA5;font-size:11px" href="https://doi.org/10.1093/cercor/bhw157">doi:10.1093/cercor/bhw157</a></td>
    </tr>
    <tr>
      <td><code>Ce_CeA</code></td><td>CIT168</td>
      <td>Pauli et al. (2018) <em>Scientific Data</em> 5:180063</td>
      <td><a style="color:#185FA5;font-size:11px" href="https://doi.org/10.1038/sdata.2018.63">doi:10.1038/sdata.2018.63</a></td>
    </tr>
    <tr>
      <td><code>BST_BNST</code></td><td>Blackford BNST</td>
      <td>Avery et al. (2022) <em>Neuropsychopharmacology</em></td>
      <td></td>
    </tr>
    <tr>
      <td><code>Dahl_LCmax_prob</code></td><td>LC mask (Dahl)</td>
      <td>Dahl et al. (2022) <em>Nature Human Behaviour</em></td>
      <td><a style="color:#185FA5;font-size:11px" href="https://osf.io/at3ym/">osf.io/at3ym</a></td>
    </tr>
    <tr>
      <td><code>IFJ_CSphere, FEF_CSphere</code></td><td>Coordinate sphere</td>
      <td><span style="color:#888;font-size:11px">custom — no citation required</span></td>
      <td></td>
    </tr>

    <tr><td colspan="4" style="background:#f3f3f3;font-size:10px;font-weight:600;color:#555;padding:4px 8px">TARGETING</td></tr>
    <tr>
      <td>Step 4</td><td>PlanTUS</td>
      <td>Lueckel et al. (2025) <em>Brain Stimulation</em> 18(5):1563–1565</td>
      <td><a style="color:#185FA5;font-size:11px" href="https://doi.org/10.1016/j.brs.2025.08.013">doi:10.1016/j.brs.2025.08.013</a> &nbsp;&#124;&nbsp; <a style="color:#185FA5;font-size:11px" href="https://plan-tus.org">plan-tus.org</a></td>
    </tr>
    <tr>
      <td>Steps 1, 4</td><td>SimNIBS (mesh)</td>
      <td>Thielscher et al. (2015) <em>NeuroImage</em> 119:208–217</td>
      <td><a style="color:#185FA5;font-size:11px" href="https://simnibs.github.io">simnibs.github.io</a></td>
    </tr>
    <tr>
      <td>Step 4</td><td>Connectome Workbench</td>
      <td>Marcus et al. (2011) <em>NeuroImage</em> 54(4):2951–2956</td>
      <td><a style="color:#185FA5;font-size:11px" href="https://www.humanconnectome.org/software/connectome-workbench">humanconnectome.org</a> &nbsp;&#124;&nbsp; v2.1.0</td>
    </tr>

    <tr><td colspan="4" style="background:#f3f3f3;font-size:10px;font-weight:600;color:#555;padding:4px 8px">SIMULATION</td></tr>
    <tr>
      <td>Step 5</td><td>BabelBrain</td>
      <td>Pichardo (2023) <em>IEEE Trans. Ultrason. Ferroelectr. Freq. Control</em> 70(7):587–599</td>
      <td><a style="color:#185FA5;font-size:11px" href="https://doi.org/10.1109/TUFFC.2023.3274046">doi:10.1109/TUFFC.2023.3274046</a></td>
    </tr>
    <tr>
      <td>Step 5</td><td>BabelViscoFDTD</td>
      <td>Pichardo et al. (2017) <em>Phys. Med. Biol.</em> 62(17):6938</td>
      <td><a style="color:#185FA5;font-size:11px" href="https://doi.org/10.1088/1361-6560/aa7ccc">doi:10.1088/1361-6560/aa7ccc</a></td>
    </tr>
  </table>
</div>

</div>
"""

display(HTML(HTML_CONTENT))
