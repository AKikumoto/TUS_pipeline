from IPython.display import HTML, display

HTML_CONTENT = """
<style>
.s4-wrap *{box-sizing:border-box}
.s4-wrap{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;color:#1a1a1a;max-width:860px;margin:0 auto}
.s4-card{background:#f8f8f8;border:1px solid #e0e0e0;border-radius:10px;padding:14px 16px;margin-bottom:10px}
.s4-phase-bar{display:flex;align-items:stretch;border-radius:8px;overflow:hidden;border:1px solid #e0e0e0;margin-bottom:10px}
.s4-phase-col{flex:1;padding:10px 8px;text-align:center}
.s4-phase-label{font-size:12px;font-weight:600;margin-bottom:4px}
.s4-phase-sub{font-size:11px;opacity:.85;line-height:1.5}
.s4-ph-teal{background:#E1F5EE;color:#085041}
.s4-ph-coral{background:#FAECE7;color:#4A1B0C}
.s4-ph-green{background:#EAF3DE;color:#27500A}
.s4-ph-divider{width:1px;background:#e0e0e0;flex-shrink:0}
.s4-sec-title{font-size:12px;font-weight:600;color:#555;margin:0 0 6px}
.s4-wrap table{width:100%;border-collapse:collapse;font-size:12px}
.s4-wrap th{text-align:left;color:#555;font-weight:600;padding:4px 8px;border-bottom:1px solid #e0e0e0}
.s4-wrap td{text-align:left;padding:4px 8px;border-bottom:1px solid #e0e0e0;color:#1a1a1a;vertical-align:top}
.s4-wrap tr:last-child td{border-bottom:none}
.s4-wrap code{font-family:'SFMono-Regular',Consolas,monospace;font-size:11px;background:#efefef;padding:1px 4px;border-radius:4px;color:#c7254e}
.s4-badge{display:inline-block;font-size:10px;font-weight:600;padding:1px 6px;border-radius:10px;margin-left:4px;background:#E1F5EE;color:#085041}
.s4-badge-warn{display:inline-block;font-size:10px;font-weight:600;padding:1px 6px;border-radius:10px;margin-left:4px;background:#FAEEDA;color:#633806}
.s4-row2{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
.s4-row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:10px}
.s4-io-list{font-size:12px;margin:0;padding-left:16px;line-height:1.9;color:#1a1a1a}
.s4-note{font-size:11px;color:#888;font-style:italic}
.s4-title-row{display:flex;align-items:baseline;gap:8px;margin-bottom:10px}
.s4-title-row h3{margin:0;font-size:15px;font-weight:600;color:#1a1a1a}
.s4-title-row span{font-size:12px;color:#888}
.s4-metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:0}
.s4-metric{background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:10px 10px 8px;text-align:center}
.s4-metric-icon{font-size:18px;margin-bottom:4px}
.s4-metric-label{font-size:11px;font-weight:600;color:#333;margin-bottom:3px}
.s4-metric-desc{font-size:10px;color:#888;line-height:1.4}
.s4-patch-table{width:100%;border-collapse:collapse;font-size:11px}
.s4-patch-table th{text-align:left;color:#555;font-weight:600;padding:3px 8px;border-bottom:1px solid #e0e0e0}
.s4-patch-table td{padding:3px 8px;border-bottom:1px solid #e0e0e0;color:#1a1a1a;vertical-align:top}
.s4-patch-table tr:last-child td{border-bottom:none}
.s4-link{color:#185FA5;text-decoration:none;font-size:11px}
</style>

<div class="s4-wrap">

<div class="s4-title-row">
  <h3>Step 4 &#8212; PlanTUS: Interactive transducer placement</h3>
  <span>SimNIBS mesh &#8594; BrainSight coord</span>
</div>

<!-- Pipeline SVG -->
<div class="s4-card" style="padding:16px 16px 14px">
<svg width="100%" viewBox="0 0 780 130" xmlns="http://www.w3.org/2000/svg">
<defs>
  <marker id="arr4" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </marker>
</defs>
<rect x="4" y="14" width="88" height="28" rx="6" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="11" x="48" y="28" text-anchor="middle" dominant-baseline="central" fill="#085041">Site YAML</text>
<rect x="4" y="54" width="88" height="28" rx="6" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="11" x="48" y="68" text-anchor="middle" dominant-baseline="central" fill="#085041">m2m_&lt;sub&gt;/</text>
<line x1="92" y1="28" x2="104" y2="28" stroke="#888" stroke-width="1"/>
<line x1="92" y1="68" x2="104" y2="68" stroke="#888" stroke-width="1"/>
<line x1="104" y1="28" x2="104" y2="68" stroke="#888" stroke-width="1"/>
<line x1="104" y1="48" x2="118" y2="48" stroke="#888" stroke-width="1" marker-end="url(#arr4)"/>
<rect x="120" y="28" width="110" height="40" rx="6" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="175" y="42" text-anchor="middle" dominant-baseline="central" fill="#085041">Init</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="175" y="58" text-anchor="middle" dominant-baseline="central" fill="#0F6E56">config + SimNIBS env</text>
<line x1="230" y1="48" x2="248" y2="48" stroke="#888" stroke-width="1" marker-end="url(#arr4)"/>
<rect x="250" y="28" width="116" height="40" rx="6" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="308" y="42" text-anchor="middle" dominant-baseline="central" fill="#4A1B0C">prepscene</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="308" y="58" text-anchor="middle" dominant-baseline="central" fill="#993C1D">mesh &#8594; wb_view</text>
<line x1="366" y1="48" x2="384" y2="48" stroke="#888" stroke-width="1" marker-end="url(#arr4)"/>
<rect x="386" y="28" width="114" height="40" rx="6" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="443" y="42" text-anchor="middle" dominant-baseline="central" fill="#4A1B0C">Click vertex</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="443" y="58" text-anchor="middle" dominant-baseline="central" fill="#993C1D">&#8594; run placement</text>
<line x1="500" y1="48" x2="518" y2="48" stroke="#888" stroke-width="1" marker-end="url(#arr4)"/>
<rect x="520" y="28" width="118" height="40" rx="6" fill="#EAF3DE" stroke="#3B6D11" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="579" y="42" text-anchor="middle" dominant-baseline="central" fill="#27500A">BrainSight export</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="579" y="58" text-anchor="middle" dominant-baseline="central" fill="#3B6D11">focus matrix &#8594; .txt</text>
<line x1="638" y1="48" x2="656" y2="48" stroke="#888" stroke-width="1" marker-end="url(#arr4)"/>
<rect x="658" y="28" width="88" height="40" rx="6" fill="#EAF3DE" stroke="#3B6D11" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="702" y="42" text-anchor="middle" dominant-baseline="central" fill="#27500A">BrainSight</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="702" y="58" text-anchor="middle" dominant-baseline="central" fill="#3B6D11">/ Step 5</text>
<line x1="250" y1="68" x2="250" y2="88" stroke="#bbb" stroke-width="0.8" stroke-dasharray="3 2"/>
<line x1="366" y1="68" x2="366" y2="88" stroke="#bbb" stroke-width="0.8" stroke-dasharray="3 2"/>
<line x1="250" y1="88" x2="366" y2="88" stroke="#bbb" stroke-width="0.8" stroke-dasharray="3 2"/>
<line x1="308" y1="88" x2="308" y2="98" stroke="#bbb" stroke-width="0.8" stroke-dasharray="3 2" marker-end="url(#arr4)"/>
<text font-family="-apple-system,sans-serif" font-size="11" font-style="italic" x="308" y="112" text-anchor="middle" dominant-baseline="central" fill="#888">DRY_RUN=True: validate inputs only, no files written</text>
</svg>
</div>

<!-- Phase bar -->
<div class="s4-phase-bar">
  <div class="s4-phase-col s4-ph-teal">
    <div class="s4-phase-label">&#9312; Init</div>
    <div class="s4-phase-sub">Load config<br>Resolve m2m dir<br>SimNIBS PATH + transducer params</div>
  </div>
  <div class="s4-ph-divider"></div>
  <div class="s4-phase-col s4-ph-coral">
    <div class="s4-phase-label">&#9313; Placement</div>
    <div class="s4-phase-sub">prepscene &#8594; wb_view<br>Click vertex &#8594; place</div>
  </div>
  <div class="s4-ph-divider"></div>
  <div class="s4-phase-col s4-ph-green">
    <div class="s4-phase-label">&#9314; Export</div>
    <div class="s4-phase-sub">BrainSight .txt<br>from focus matrix</div>
  </div>
</div>

<!-- PlanTUS metrics -->
<div class="s4-card">
  <div class="s4-sec-title">PLANTUS METRICS (VISUALISED IN WB_VIEW)</div>
  <div class="s4-metric-grid">
    <div class="s4-metric">
      <div class="s4-metric-icon">&#8597;</div>
      <div class="s4-metric-label">Distance</div>
      <div class="s4-metric-desc">Skin surface &#8594; target (mm). Black outline = reachable zone given focal depth</div>
    </div>
    <div class="s4-metric">
      <div class="s4-metric-icon">&#11044;</div>
      <div class="s4-metric-label">Intersection</div>
      <div class="s4-metric-desc">Overlap (mm) between target ROI and idealized straight-line beam. Maximise this</div>
    </div>
    <div class="s4-metric">
      <div class="s4-metric-icon">&#8735;</div>
      <div class="s4-metric-label">Angle</div>
      <div class="s4-metric-desc">Skin/skull normal vector mismatch (&#176;). Minimise to reduce skull reflections</div>
    </div>
    <div class="s4-metric">
      <div class="s4-metric-icon">&#9940;</div>
      <div class="s4-metric-label">Avoidance zones</div>
      <div class="s4-metric-desc">Auto-detected no-go areas (ears, eyes, sinuses). Shown in grey on scalp</div>
    </div>
  </div>
  <p style="font-size:11px;color:#888;margin:8px 0 0;font-style:italic">&#9888;&#65039; PlanTUS does not model skull aberrations &#8212; always validate placements with full acoustic simulation (k-Wave / kPlan / BabelBrain)</p>
</div>

<!-- wb_view info -->
<div class="s4-card">
  <div class="s4-sec-title">WB_VIEW (CONNECTOME WORKBENCH)</div>
  <table>
    <tr><th>Action</th><th>How</th></tr>
    <tr><td>Open scene with scalp metrics</td><td><code>prepscene</code> generates <code>scene.scene</code>; wb_view launches automatically</td></tr>
    <tr><td>Select transducer position</td><td>Click scalp vertex &#8594; white sphere appears; vertex ID logged to FINER log</td></tr>
    <tr><td>Vertex ID capture</td><td><code>USE_PYNPUT=True</code>: pynput mouse listener &nbsp;|&nbsp; <code>False</code>: parse wb_view FINER log</td></tr>
    <tr><td>Review placement result</td><td>Oblique volume view shows acoustic focus vs. target overlap after <code>run_plantus_placement</code></td></tr>
  </table>
  <p style="font-size:11px;color:#888;margin:8px 0 0">Required version: &#8805;1.5 &nbsp;&#124;&nbsp; Current latest: 2.1.0 &nbsp;&#124;&nbsp; <a class="s4-link" href="https://www.humanconnectome.org/software/get-connectome-workbench">humanconnectome.org/software/get-connectome-workbench</a></p>
</div>

<!-- Run options -->
<div class="s4-card">
  <div class="s4-sec-title">RUN OPTIONS</div>
  <table>
    <tr><th>Setting</th><th>Value</th><th>Behaviour</th></tr>
    <tr>
      <td><code>DRY_RUN</code></td>
      <td><code>False</code></td>
      <td>Full processing: prepscene, wb_view, placement</td>
    </tr>
    <tr>
      <td></td>
      <td><code>True</code></td>
      <td>Validate inputs only; no files written</td>
    </tr>
    <tr>
      <td><code>USE_PYNPUT</code></td>
      <td><code>True</code></td>
      <td>pynput mouse listener &#8212; requires macOS Accessibility permission</td>
    </tr>
    <tr>
      <td></td>
      <td><code>False</code></td>
      <td>Parse wb_view FINER log directly &#8212; no Accessibility permission needed</td>
    </tr>
  </table>
</div>

<!-- TARGET_SIDE -->
<div class="s4-card">
  <div class="s4-sec-title">TARGET SIDE</div>
  <table>
    <tr><th>Setting</th><th>Description</th></tr>
    <tr><td><code>"_R"</code></td><td>Right hemisphere target</td></tr>
    <tr><td><code>"_L"</code></td><td>Left hemisphere target</td></tr>
    <tr><td><code>""</code></td><td>Bilateral (no hemisphere suffix)</td></tr>
  </table>
</div>

<!-- Inputs / Outputs -->
<div class="s4-row2">
  <div class="s4-card" style="margin-bottom:0">
    <div class="s4-sec-title">INPUTS REQUIRED</div>
    <ul class="s4-io-list">
      <li>Site YAML <code>config/sites/</code></li>
      <li>SimNIBS <code>m2m_&lt;sub_id&gt;/</code> dir <span class="s4-note">(from step 2)</span></li>
      <li>Target name + side <span class="s4-note">(matches mask label from step 3)</span></li>
    </ul>
  </div>
  <div class="s4-card" style="margin-bottom:0">
    <div class="s4-sec-title">OUTPUTS</div>
    <ul class="s4-io-list">
      <li>PlanTUS files in <code>m2m_&lt;sub_id&gt;/</code> <span class="s4-note">(placement angles, scene, log)</span></li>
      <li><code>&lt;sub_id&gt;_&lt;target&gt;&lt;side&gt;_brainsight.txt</code></li>
      <li><code>skin_target_distances.npy</code></li>
    </ul>
  </div>
</div>
<div style="margin-bottom:10px"></div>

<!-- Local patches -->
<div class="s4-card">
  <div class="s4-sec-title">LOCAL PATCHES <span class="s4-badge-warn">re-apply if PlanTUS / wb_view updated</span></div>
  <table class="s4-patch-table">
    <tr><th>Date</th><th>File</th><th>Change</th><th>Reason</th></tr>
    <tr>
      <td>2026-03-19</td>
      <td><code>PlanTUS.py</code> L600&#8211;602</td>
      <td><code>np.string_</code> &#8594; <code>np.bytes_</code> (3&#215;)</td>
      <td><code>np.string_</code> removed in NumPy 2.0</td>
    </tr>
    <tr>
      <td>2026-03-20</td>
      <td><code>PlanTUS.py</code> L563&#8211;570</td>
      <td>Quoted path args in <code>transform_surface_model</code> <code>os.system()</code> calls</td>
      <td>Dropbox path contains spaces; unquoted &#8594; silent failure</td>
    </tr>
    <tr>
      <td>2026-03-20</td>
      <td><code>src/utils.py</code> &#8212; <code>run_plantus</code></td>
      <td>Added 4 Qt5 HiDPI env vars to wb_view launch</td>
      <td>Retina display double-scaling collapses panels and misaligns click targets</td>
    </tr>
    <tr>
      <td>2026-03-20</td>
      <td><code>src/utils.py</code> &#8212; <code>run_plantus</code></td>
      <td><code>USE_PYNPUT</code> fallback to FINER log parsing</td>
      <td>pynput silently drops events without Accessibility permissions</td>
    </tr>
    <tr>
      <td>2026-03-20</td>
      <td><code>wb_view.app/Contents/Info.plist</code></td>
      <td>Added <code>NSHighResolutionCapable = false</code></td>
      <td>Suppresses macOS 2&#215; Retina scaling passed to Qt5. Backup: <code>Info.plist.bak</code></td>
    </tr>
  </table>
</div>

<!-- Settings at a glance -->
<div class="s4-card">
  <div class="s4-sec-title">SETTINGS AT A GLANCE</div>
  <table>
    <tr><th>Variable</th><th>What it controls</th></tr>
    <tr>
      <td class="s4-opt"><code>TARGET_NAME</code></td>
      <td>Label string that identifies the target region. Must match the <code>MASK_LABEL</code> used in step 3 — determines which native mask file (<code>*_mask_native.nii.gz</code>) PlanTUS searches for.</td>
    </tr>
    <tr>
      <td class="s4-opt"><code>TARGET_SIDE</code></td>
      <td>Hemisphere suffix appended to the target filename. <code>"_R"</code> = right, <code>"_L"</code> = left, <code>""</code> = bilateral (no suffix). Must match how the native mask was split in step 3.</td>
    </tr>
    <tr>
      <td class="s4-opt"><code>DRY_RUN</code></td>
      <td>When <code>True</code>: validates all inputs and prints what would run, but writes no files. Use to check paths before committing to a long placement session.</td>
    </tr>
    <tr>
      <td class="s4-opt"><code>USE_PYNPUT</code></td>
      <td>Controls how the scalp vertex click is captured from wb_view. <code>True</code> = pynput mouse listener (requires macOS Accessibility permission in System Preferences). <code>False</code> = parse wb_view FINER log directly — no special permission needed.</td>
    </tr>
    <tr>
      <td class="s4-opt"><code>ADDITIONAL_OFFSET</code></td>
      <td>Extra standoff distance (mm) added to the acoustic focal depth calculation. Use to account for coupling gel, water bath, or standoff pad thickness.</td>
    </tr>
  </table>
</div>

<!-- Dependencies & References -->
<div class="s4-row2">
  <div class="s4-card" style="margin-bottom:0">
    <div class="s4-sec-title">DEPENDENCIES</div>
    <table>
      <tr><th>Tool / Package</th><th>Used for</th></tr>
      <tr><td>SimNIBS &#8805; 4.0</td><td>Head mesh (<code>m2m_*/</code>), <code>mri2mesh</code> / <code>charm</code> pipeline</td></tr>
      <tr><td>PlanTUS</td><td>Transducer placement optimisation and prepscene</td></tr>
      <tr><td>Connectome Workbench (wb_view &#8805; 1.5)</td><td>Interactive scalp surface viewer</td></tr>
      <tr><td><code>src/utils.py</code></td><td>Shared pipeline utilities (<code>run_plantus</code>, <code>write_brainsight_for_vtx</code>)</td></tr>
    </table>
  </div>
  <div class="s4-card" style="margin-bottom:0">
    <div class="s4-sec-title">REFERENCES</div>
    <table>
      <tr><th>Tool</th><th>Citation / Link</th></tr>
      <tr>
        <td>PlanTUS</td>
        <td>Lueckel et al. (2025) <em>Brain Stimulation</em> 18(5):1563&#8211;1565 &nbsp;&#124;&nbsp; <a class="s4-link" href="https://doi.org/10.1016/j.brs.2025.08.013">doi:10.1016/j.brs.2025.08.013</a> &nbsp;&#124;&nbsp; <a class="s4-link" href="https://plan-tus.org">plan-tus.org</a></td>
      </tr>
      <tr>
        <td>SimNIBS</td>
        <td>Thielscher et al. (2015) <em>NeuroImage</em> 119:208&#8211;217 &nbsp;&#124;&nbsp; <a class="s4-link" href="https://simnibs.github.io">simnibs.github.io</a></td>
      </tr>
      <tr>
        <td>Connectome Workbench</td>
        <td><a class="s4-link" href="https://www.humanconnectome.org/software/connectome-workbench">humanconnectome.org/software/connectome-workbench</a> &nbsp;&#124;&nbsp; v2.1.0</td>
      </tr>
    </table>
  </div>
</div>
<div style="margin-bottom:10px"></div>

</div>
"""

display(HTML(HTML_CONTENT))
