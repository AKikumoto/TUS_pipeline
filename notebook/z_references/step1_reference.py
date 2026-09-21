from IPython.display import HTML, display

HTML_CONTENT = """
<style>
.s1-wrap *{box-sizing:border-box}
.s1-wrap{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;color:#1a1a1a;max-width:860px;margin:0 auto}
.s1-card{background:#f8f8f8;border:1px solid #e0e0e0;border-radius:10px;padding:14px 16px;margin-bottom:10px}
.s1-phase-bar{display:flex;align-items:stretch;border-radius:8px;overflow:hidden;border:1px solid #e0e0e0;margin-bottom:10px}
.s1-phase-col{flex:1;padding:10px 8px;text-align:center}
.s1-phase-label{font-size:12px;font-weight:600;margin-bottom:4px}
.s1-phase-sub{font-size:11px;opacity:.85;line-height:1.5}
.s1-ph-teal{background:#E1F5EE;color:#085041}
.s1-ph-purple{background:#EEEDFE;color:#3C3489}
.s1-ph-amber{background:#FAEEDA;color:#633806}
.s1-ph-green{background:#EAF3DE;color:#27500A}
.s1-ph-divider{width:1px;background:#e0e0e0;flex-shrink:0}
.s1-sec-title{font-size:12px;font-weight:600;color:#555;margin:0 0 8px;letter-spacing:.03em}
.s1-wrap table{width:100%;border-collapse:collapse;font-size:12px}
.s1-wrap th{text-align:left;color:#555;font-weight:600;padding:4px 8px;border-bottom:1px solid #e0e0e0}
.s1-wrap td{padding:4px 8px;border-bottom:1px solid #e0e0e0;color:#1a1a1a;vertical-align:top}
.s1-wrap tr:last-child td{border-bottom:none}
.s1-wrap code{font-family:'SFMono-Regular',Consolas,monospace;font-size:11px;background:#efefef;padding:1px 4px;border-radius:4px;color:#c7254e}
.s1-badge{display:inline-block;font-size:10px;font-weight:600;padding:1px 6px;border-radius:10px;margin-left:4px;background:#E1F5EE;color:#085041}
.s1-row2{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
.s1-io-list{font-size:12px;margin:0;padding-left:16px;line-height:1.9;color:#1a1a1a}
.s1-note{font-size:11px;color:#888;font-style:italic}
.s1-title-row{display:flex;align-items:baseline;gap:8px;margin-bottom:10px}
.s1-title-row h3{margin:0;font-size:15px;font-weight:600;color:#1a1a1a}
.s1-title-row span{font-size:12px;color:#888}
.s1-tissue-layout{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}
.s1-tissue-list{list-style:none;margin:0;padding:0;font-size:12px;display:flex;flex-direction:column;gap:5px}
.s1-tissue-list li{display:flex;align-items:center;gap:8px;line-height:1.4}
.s1-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0;border:1px solid rgba(0,0,0,.12)}
.s1-lnum{font-family:'SFMono-Regular',Consolas,monospace;font-size:10px;color:#888;width:14px;flex-shrink:0}
.s1-link{color:#185FA5;text-decoration:none;font-size:11px}
.s1-imglink{display:flex;align-items:center;gap:8px;padding:10px 12px;background:#fff;border:1px solid #e0e0e0;border-radius:8px;text-decoration:none;color:#1a1a1a;font-size:12px}
.s1-imglink-icon{font-size:20px;flex-shrink:0}
.s1-imglink-text{line-height:1.5}
.s1-imglink-title{font-weight:600;font-size:12px}
.s1-imglink-sub{font-size:11px;color:#888}
.s1-next-badge{display:inline-block;font-size:10px;font-weight:600;padding:1px 7px;border-radius:10px;background:#EEEDFE;color:#3C3489;margin-left:4px}
</style>

<div class="s1-wrap">

<div class="s1-title-row">
  <h3>Step 1 &#8212; SimNIBS segmentation (charm)</h3>
  <span>T1w MRI &#8594; tetrahedral head mesh</span>
</div>

<div class="s1-card" style="padding:16px 16px 14px">
<svg width="100%" viewBox="0 0 780 90" xmlns="http://www.w3.org/2000/svg">
<defs>
  <marker id="arr1" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </marker>
</defs>
<rect x="4" y="20" width="88" height="40" rx="6" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="48" y="36" text-anchor="middle" dominant-baseline="central" fill="#085041">T1w NIfTI</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="48" y="52" text-anchor="middle" dominant-baseline="central" fill="#0F6E56">BIDS format</text>
<line x1="92" y1="40" x2="110" y2="40" stroke="#888" stroke-width="1" marker-end="url(#arr1)"/>
<rect x="112" y="20" width="110" height="40" rx="6" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="167" y="36" text-anchor="middle" dominant-baseline="central" fill="#3C3489">qform fix</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="167" y="52" text-anchor="middle" dominant-baseline="central" fill="#534AB7">fslorient (optional)</text>
<line x1="222" y1="40" x2="240" y2="40" stroke="#888" stroke-width="1" marker-end="url(#arr1)"/>
<rect x="242" y="20" width="110" height="40" rx="6" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="297" y="36" text-anchor="middle" dominant-baseline="central" fill="#3C3489">charm</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="297" y="52" text-anchor="middle" dominant-baseline="central" fill="#534AB7">SimNIBS &#8805;4.0</text>
<line x1="352" y1="40" x2="420" y2="40" stroke="#888" stroke-width="1" marker-end="url(#arr1)"/>
<rect x="422" y="20" width="120" height="40" rx="6" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="482" y="36" text-anchor="middle" dominant-baseline="central" fill="#633806">QC</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="482" y="52" text-anchor="middle" dominant-baseline="central" fill="#854F0B">verify + tissue overlay</text>
<line x1="542" y1="40" x2="562" y2="40" stroke="#888" stroke-width="1" marker-end="url(#arr1)"/>
<rect x="564" y="20" width="130" height="40" rx="6" fill="#EAF3DE" stroke="#3B6D11" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="629" y="34" text-anchor="middle" dominant-baseline="central" fill="#27500A">m2m_&lt;sub_id&gt;/</text>
<text font-family="-apple-system,sans-serif" font-size="10" x="629" y="52" text-anchor="middle" dominant-baseline="central" fill="#3B6D11">&#8594; Step 3 &amp; Step 4</text>
</svg>
</div>

<div class="s1-phase-bar">
  <div class="s1-phase-col s1-ph-teal">
    <div class="s1-phase-label">&#9312; Init</div>
    <div class="s1-phase-sub">Load config<br>Resolve T1w path</div>
  </div>
  <div class="s1-ph-divider"></div>
  <div class="s1-phase-col s1-ph-purple">
    <div class="s1-phase-label">&#9313; Segmentation</div>
    <div class="s1-phase-sub">qform fix (optional)<br>charm (20&#8211;60 min)</div>
  </div>
  <div class="s1-ph-divider"></div>
  <div class="s1-phase-col s1-ph-amber">
    <div class="s1-phase-label">&#9314; QC</div>
    <div class="s1-phase-sub">Verify output files<br>Tissue overlay plots</div>
  </div>
  <div class="s1-ph-divider"></div>
  <div class="s1-phase-col s1-ph-green">
    <div class="s1-phase-label">&#9315; Output</div>
    <div class="s1-phase-sub">m2m_&lt;sub_id&gt;/<br>&#8594; Step 3 &amp; Step 4</div>
  </div>
</div>

<div class="s1-card">
  <div class="s1-sec-title">TISSUE LABELS (final_tissues.nii.gz)</div>
  <div class="s1-tissue-layout">
    <ul class="s1-tissue-list">
      <li><span class="s1-lnum">1</span><span class="s1-dot" style="background:#E8E4F8;border-color:#AFA9EC"></span>White matter</li>
      <li><span class="s1-lnum">2</span><span class="s1-dot" style="background:#C8E6C9;border-color:#81C784"></span>Grey matter</li>
      <li><span class="s1-lnum">3</span><span class="s1-dot" style="background:#B3E5FC;border-color:#4FC3F7"></span>CSF</li>
      <li><span class="s1-lnum">4</span><span class="s1-dot" style="background:#F5D5A0;border-color:#EF9F27"></span>Skull (bone)</li>
      <li><span class="s1-lnum">5</span><span class="s1-dot" style="background:#FADADD;border-color:#F09595"></span>Scalp</li>
      <li><span class="s1-lnum">6</span><span class="s1-dot" style="background:#E0E0E0;border-color:#BDBDBD"></span>Eye region</li>
      <li style="margin-top:8px;color:#888;font-size:11px;font-style:italic">
        QA: open <code>charm_report.html</code> in browser,<br>
        or overlay <code>final_tissues.nii.gz</code> on <code>T1.nii.gz</code>
      </li>
    </ul>
    <div style="display:flex;flex-direction:column;gap:8px">
      <a class="s1-imglink" href="https://simnibs.github.io/simnibs/build/html/tutorial/head_meshing.html" target="_blank">
        <span class="s1-imglink-icon">&#129504;</span>
        <span class="s1-imglink-text">
          <div class="s1-imglink-title">charm segmentation example</div>
          <div class="s1-imglink-sub">simnibs.github.io &#8212; head meshing tutorial</div>
        </span>
      </a>
      <a class="s1-imglink" href="https://simnibs.github.io/simnibs/build/html/documentation/command_line/charm.html" target="_blank">
        <span class="s1-imglink-icon">&#128196;</span>
        <span class="s1-imglink-text">
          <div class="s1-imglink-title">charm command-line reference</div>
          <div class="s1-imglink-sub">simnibs.github.io &#8212; charm docs</div>
        </span>
      </a>
    </div>
  </div>
</div>

<div class="s1-card">
  <div class="s1-sec-title">RUN OPTIONS</div>
  <table>
    <tr><th>Setting</th><th>Value</th><th>Behaviour</th></tr>
    <tr><td><code>FIX_QFORM</code></td><td><code>True</code> <span class="s1-badge">default</span></td><td>Run <code>fslorient -copysform2qform</code> before charm (recommended)</td></tr>
    <tr><td></td><td><code>False</code></td><td>Skip qform fix</td></tr>
    <tr><td><code>DRY_RUN</code></td><td><code>False</code> <span class="s1-badge">default</span></td><td>Full execution: qform fix + charm</td></tr>
    <tr><td></td><td><code>True</code></td><td>Print commands only; no files written</td></tr>
  </table>
</div>

<div class="s1-row2">
  <div class="s1-card" style="margin-bottom:0">
    <div class="s1-sec-title">INPUTS REQUIRED</div>
    <ul class="s1-io-list">
      <li>Site YAML <code>config/sites/</code></li>
      <li>T1w NIfTI <code>{sub_dir}/*_T1w.nii[.gz]</code><br><span class="s1-note">auto-located via site config</span></li>
      <li>SimNIBS &#8805;4.0 (<code>charm</code> on PATH)</li>
      <li>FSL <code>fslorient</code> <span class="s1-note">(optional, for qform fix)</span></li>
    </ul>
  </div>
  <div class="s1-card" style="margin-bottom:0">
    <div class="s1-sec-title">OUTPUTS</div>
    <ul class="s1-io-list">
      <li><code>m2m_{sub_id}/final_tissues.nii.gz</code></li>
      <li><code>m2m_{sub_id}/final_tissues_LUT.txt</code></li>
      <li><code>m2m_{sub_id}/T1.nii.gz</code></li>
      <li><code>m2m_{sub_id}/*.msh</code></li>
    </ul>
    <div style="margin-top:8px;font-size:11px;color:#888">
      Next steps:<br>
      <span class="s1-next-badge">Step 3</span> inverse registration (MNI &#8594; native)<br>
      <span class="s1-next-badge">Step 4</span> PlanTUS transducer placement
    </div>
  </div>
</div>
<div style="margin-bottom:10px"></div>

<div class="s1-row2">
  <div class="s1-card" style="margin-bottom:0">
    <div class="s1-sec-title">DEPENDENCIES</div>
    <table>
      <tr><th>Package / Tool</th><th>Used for</th></tr>
      <tr><td><strong>SimNIBS</strong> (<code>charm</code>)</td><td>Head mesh segmentation</td></tr>
      <tr><td>FSL (<code>fslorient</code>)</td><td>qform/sform fix (optional)</td></tr>
      <tr><td><code>nibabel</code></td><td>NIfTI file I/O</td></tr>
      <tr><td><code>nilearn</code></td><td>QA visualisation, image resampling</td></tr>
      <tr><td><code>numpy</code>, <code>matplotlib</code></td><td>Tissue overlay plots</td></tr>
      <tr><td><code>src/utils.py</code></td><td>Shared pipeline utilities</td></tr>
    </table>
  </div>
  <div class="s1-card" style="margin-bottom:0">
    <div class="s1-sec-title">REFERENCES</div>
    <table>
      <tr><th>Tool</th><th>Citation / Link</th></tr>
      <tr><td>SimNIBS / charm</td><td>Puonti et al. (2020) <em>NeuroImage</em>. <a style="color:#185FA5;font-size:11px" href="https://doi.org/10.1016/j.neuroimage.2020.116987">doi:10.1016/j.neuroimage.2020.116987</a> &#124; <a style="color:#185FA5;font-size:11px" href="https://simnibs.github.io/simnibs/build/html/tutorial/head_meshing.html">head meshing tutorial</a></td></tr>
      <tr><td>FSL / fslorient</td><td><a style="color:#185FA5;font-size:11px" href="https://fsl.fmrib.ox.ac.uk/fsl/docs/#/utilities/fslorient">fsl.fmrib.ox.ac.uk/fsl/docs</a></td></tr>
    </table>
  </div>
</div>
<div style="margin-bottom:10px"></div>

</div>
"""

display(HTML(HTML_CONTENT))
