from IPython.display import HTML, display

HTML_CONTENT = """
<style>
.s5-wrap *{box-sizing:border-box}
.s5-wrap{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;color:#1a1a1a;max-width:860px;margin:0 auto}
.s5-card{background:#f8f8f8;border:1px solid #e0e0e0;border-radius:10px;padding:14px 16px;margin-bottom:10px}
.s5-phase-bar{display:flex;align-items:stretch;border-radius:8px;overflow:hidden;border:1px solid #e0e0e0;margin-bottom:10px}
.s5-phase-col{flex:1;padding:10px 8px;text-align:center}
.s5-phase-label{font-size:12px;font-weight:600;margin-bottom:4px}
.s5-phase-sub{font-size:11px;opacity:.85;line-height:1.5}
.s5-ph-teal{background:#E1F5EE;color:#085041}
.s5-ph-purple{background:#EEEDFE;color:#3C3489}
.s5-ph-amber{background:#FAEEDA;color:#633806}
.s5-ph-coral{background:#FAECE7;color:#4A1B0C}
.s5-ph-green{background:#EAF3DE;color:#27500A}
.s5-ph-divider{width:1px;background:#e0e0e0;flex-shrink:0}
.s5-sec-title{font-size:12px;font-weight:600;color:#555;margin:0 0 6px}
.s5-wrap table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}
.s5-wrap th{text-align:left;color:#555;font-weight:600;padding:4px 8px;border-bottom:1px solid #e0e0e0;word-break:break-word}
.s5-wrap td{text-align:left;padding:4px 8px;border-bottom:1px solid #e0e0e0;color:#1a1a1a;vertical-align:top;overflow-wrap:break-word;word-break:break-word}
.s5-wrap tr:last-child td{border-bottom:none}
.s5-wrap code{font-family:'SFMono-Regular',Consolas,monospace;font-size:11px;background:#efefef;padding:1px 4px;border-radius:4px;color:#c7254e;word-break:break-all;overflow-wrap:break-word}
.s5-badge{display:inline-block;font-size:10px;font-weight:600;padding:1px 6px;border-radius:10px;margin-left:4px;background:#E1F5EE;color:#085041}
.s5-badge-warn{display:inline-block;font-size:10px;font-weight:600;padding:1px 6px;border-radius:10px;margin-left:4px;background:#FAEEDA;color:#633806}
.s5-badge-gpu{display:inline-block;font-size:10px;font-weight:600;padding:1px 6px;border-radius:10px;background:#EEEDFE;color:#3C3489}
.s5-row2{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
.s5-io-list{font-size:12px;margin:0;padding-left:16px;line-height:1.9;color:#1a1a1a}
.s5-note{font-size:11px;color:#888;font-style:italic}
.s5-title-row{display:flex;align-items:baseline;gap:8px;margin-bottom:10px}
.s5-title-row h3{margin:0;font-size:15px;font-weight:600;color:#1a1a1a}
.s5-title-row span{font-size:12px;color:#888}
.s5-opt{white-space:nowrap}
.s5-link{color:#185FA5;text-decoration:none;font-size:11px}
</style>

<div class="s5-wrap">

<div class="s5-title-row">
  <h3>Step 5 &#8212; BabelBrain: Acoustic &amp; Thermal Simulation</h3>
  <span>Brainsight trajectory &#8594; acoustic field &#8594; thermal maps</span>
</div>

<!-- Pipeline SVG -->
<div class="s5-card" style="padding:16px 16px 14px">
<svg width="100%" viewBox="0 0 780 110" xmlns="http://www.w3.org/2000/svg">
<defs>
  <marker id="arr5" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </marker>
</defs>
<!-- Inputs -->
<rect x="4" y="14" width="88" height="26" rx="5" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="11" x="48" y="27" text-anchor="middle" dominant-baseline="central" fill="#085041">Site YAML</text>
<rect x="4" y="48" width="88" height="26" rx="5" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="11" x="48" y="61" text-anchor="middle" dominant-baseline="central" fill="#085041">m2m_&lt;sub&gt;/</text>
<rect x="4" y="82" width="88" height="26" rx="5" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="11" x="48" y="95" text-anchor="middle" dominant-baseline="central" fill="#085041">*_brainsight.txt</text>
<!-- merge arrow -->
<line x1="92" y1="27" x2="104" y2="27" stroke="#888" stroke-width="1"/>
<line x1="92" y1="61" x2="104" y2="61" stroke="#888" stroke-width="1"/>
<line x1="92" y1="95" x2="104" y2="95" stroke="#888" stroke-width="1"/>
<line x1="104" y1="27" x2="104" y2="95" stroke="#888" stroke-width="1"/>
<line x1="104" y1="61" x2="118" y2="61" stroke="#888" stroke-width="1" marker-end="url(#arr5)"/>
<!-- Init -->
<rect x="120" y="41" width="100" height="40" rx="6" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="170" y="55" text-anchor="middle" dominant-baseline="central" fill="#085041">Init</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="170" y="71" text-anchor="middle" dominant-baseline="central" fill="#0F6E56">resolve paths + tx params</text>
<line x1="220" y1="61" x2="238" y2="61" stroke="#888" stroke-width="1" marker-end="url(#arr5)"/>
<!-- 5a Domain -->
<rect x="240" y="41" width="120" height="40" rx="6" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="300" y="55" text-anchor="middle" dominant-baseline="central" fill="#3C3489">5a Domain gen</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="300" y="71" text-anchor="middle" dominant-baseline="central" fill="#534AB7">tissue mask (SimNIBS mesh)</text>
<line x1="360" y1="61" x2="378" y2="61" stroke="#888" stroke-width="1" marker-end="url(#arr5)"/>
<!-- 5b Acoustic -->
<rect x="380" y="41" width="120" height="40" rx="6" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="440" y="55" text-anchor="middle" dominant-baseline="central" fill="#633806">5b Acoustic sim</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="440" y="71" text-anchor="middle" dominant-baseline="central" fill="#854F0B">FDTD (GPU)</text>
<line x1="500" y1="61" x2="518" y2="61" stroke="#888" stroke-width="1" marker-end="url(#arr5)"/>
<!-- 5c Thermal -->
<rect x="520" y="41" width="120" height="40" rx="6" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="580" y="55" text-anchor="middle" dominant-baseline="central" fill="#4A1B0C">5c Thermal sim</text>
<text font-family="-apple-system,sans-serif" font-size="11" x="580" y="71" text-anchor="middle" dominant-baseline="central" fill="#993C1D">BHTE</text>
<line x1="640" y1="61" x2="658" y2="61" stroke="#888" stroke-width="1" marker-end="url(#arr5)"/>
<!-- Output -->
<rect x="660" y="41" width="114" height="40" rx="6" fill="#EAF3DE" stroke="#3B6D11" stroke-width="0.5"/>
<text font-family="-apple-system,sans-serif" font-size="12" font-weight="500" x="717" y="53" text-anchor="middle" dominant-baseline="central" fill="#27500A">Outputs</text>
<text font-family="-apple-system,sans-serif" font-size="10" x="717" y="68" text-anchor="middle" dominant-baseline="central" fill="#3B6D11">*_DataForSim.h5 + thermal</text>
</svg>
</div>

<!-- Phase bar -->
<div class="s5-phase-bar">
  <div class="s5-phase-col s5-ph-teal">
    <div class="s5-phase-label">&#9312; Init</div>
    <div class="s5-phase-sub">Load site config<br>Resolve m2m + trajectory<br>Auto-load tx params</div>
  </div>
  <div class="s5-ph-divider"></div>
  <div class="s5-phase-col s5-ph-purple">
    <div class="s5-phase-label">&#9313; 5a Domain gen</div>
    <div class="s5-phase-sub">Tissue mask from<br>SimNIBS mesh + trajectory<br>(1–5 min)</div>
  </div>
  <div class="s5-ph-divider"></div>
  <div class="s5-phase-col s5-ph-amber">
    <div class="s5-phase-label">&#9314; 5b Acoustic sim</div>
    <div class="s5-phase-sub">Rayleigh + FDTD<br>GPU-accelerated<br>(5–30 min)</div>
  </div>
  <div class="s5-ph-divider"></div>
  <div class="s5-phase-col s5-ph-coral">
    <div class="s5-phase-label">&#9315; 5c Thermal sim</div>
    <div class="s5-phase-sub">BHTE per DC/PRF combo<br>(2–10 min)</div>
  </div>
  <div class="s5-ph-divider"></div>
  <div class="s5-phase-col s5-ph-green">
    <div class="s5-phase-label">&#9316; QC</div>
    <div class="s5-phase-sub">Output file summary<br>sizes + paths</div>
  </div>
</div>

<!-- Settings at a glance -->
<div class="s5-card">
  <div class="s5-sec-title">SETTINGS AT A GLANCE</div>
  <table>
    <tr><th style="width:30%">Variable <span class="s5-note">(BabelBrain name)</span></th><th>Definition</th></tr>

    <!-- ── Acoustic sim ── -->
    <tr>
      <td colspan="2" style="background:#EEEDFE;color:#3C3489;font-weight:600;font-size:11px;padding:5px 8px">
        ACOUSTIC SIM — Steps 5a &amp; 5b &nbsp;·&nbsp; inputs: <code style="color:#3C3489">m2m_dir/</code> + <code style="color:#3C3489">*_brainsight.txt</code> from Step 4. Not affected by STIM_YAML.
      </td>
    </tr>
    <tr>
      <td class="s5-opt"><code>PPW</code><br><span class="s5-note">BB: <code>SpatialStep</code></span></td>
      <td><strong>Points Per Wavelength</strong> — number of FDTD grid nodes per acoustic wavelength. Spatial step = SOS / freq / PPW (mm). <code>6</code> = fast (minimum); <code>9</code> = converged. Compute cost scales as PPW³.</td>
    </tr>
    <tr>
      <td class="s5-opt"><code>Z_BEYOND</code><br><span class="s5-note">BB: <code>ZBeyond</code></span></td>
      <td><strong>Depth beyond focus</strong> — simulation domain extends this far past the focal point (m). Default <code>40e-3</code> (40 mm). Increase for large focal spots or bony structures in the far field.</td>
    </tr>
    <tr>
      <td class="s5-opt"><code>ADDITIONAL_OFFSET_MM</code><br><span class="s5-note">BB: → <code>ZSteering</code></span></td>
      <td><strong>Gel pad offset</strong> — physical spacing between coupling bladder and scalp (mm). Used in Step 5b to adjust electronic steering; Step 4 (PlanTUS) is unaffected. Standard pads: 3, 5, 10 mm.</td>
    </tr>
    <tr>
      <td class="s5-opt"><code>USE_CT</code><br><span class="s5-note">BB: <code>CoregCT_MRI</code><br>→ see RUN OPTIONS</span></td>
      <td><strong>Skull model</strong> — <code>False</code>: skull from SimNIBS <code>charm</code> segmentation. <code>True</code>: CT coregistered to T1w for patient-specific acoustic properties (requires <code>CT_PATH</code>).</td>
    </tr>
    <tr>
      <td class="s5-opt"><code>CT_TYPE</code><br><span class="s5-note">BB: <code>CTType</code></span></td>
      <td><strong>CT scanner type</strong> — HU → acoustic property mapping. <code>1</code> = real CT &nbsp;·&nbsp; <code>2</code> = ZTE &nbsp;·&nbsp; <code>3</code> = PETRA. Only used when <code>USE_CT=True</code>.</td>
    </tr>

    <!-- ── Thermal sim ── -->
    <tr>
      <td colspan="2" style="background:#FAECE7;color:#4A1B0C;font-weight:600;font-size:11px;padding:5px 8px">
        THERMAL SIM — Step 5c &nbsp;·&nbsp; all parameters loaded from <code style="color:#4A1B0C">STIM_YAML</code>. Only other input is the acoustic output (<code style="color:#4A1B0C">*DataForSim.h5</code>) from Step 5b.
      </td>
    </tr>
    <tr>
      <td class="s5-opt" colspan="2"><span class="s5-note"><code>STIM_YAML</code> — naming convention: <code>stimulation_[target]_[online|offline]_[experiment].yaml</code> &nbsp;·&nbsp; see <code>config/stimulation/</code>. All 7 keys below are <strong>required</strong> (KeyError if missing).</span></td>
    </tr>
    <tr>
      <td class="s5-opt"><code>BaseIsppa</code><br><span class="s5-note">BB: same</span></td>
      <td><strong>Planned in-situ I<sub>SPPA</sub></strong> (W/cm²) at the focal point — the intensity BabelBrain uses for the BHTE solve. Set to your intended experimental in-situ intensity. Results scale linearly, so no re-simulation is needed for other power levels. The per-subject in-water power (TPO setting) required to achieve this in-situ intensity is back-calculated in the Summary CSV.<br><span class="s5-note">Not a free-field (in-water) value — in-water ISPPA is higher due to skull attenuation and varies by subject.</span></td>
    </tr>
    <tr>
      <td class="s5-opt"><code>DC</code><br><span class="s5-note">BB: <code>DutyCycle</code></span></td>
      <td><strong>Duty Cycle</strong> (0–1) — fraction of each pulse period during which ultrasound is active. I<sub>SPTA</sub> = I<sub>SPPA</sub> × DC. E.g. DC=0.3, PRF=5 Hz → 60 ms on per 200 ms period.<br><span class="s5-note">Primary thermal safety driver: average power deposited in tissue scales linearly with DC. MI is independent of DC (set by peak pressure only).</span></td>
    </tr>
    <tr>
      <td class="s5-opt"><code>PRF</code><br><span class="s5-note">BB: same</span></td>
      <td><strong>Pulse Repetition Frequency</strong> (Hz) — number of pulses per second within the sonication burst. Burst length = DC / PRF (s). Independent of the carrier (transducer) frequency.<br><span class="s5-note">Controls how finely ON-time is distributed within Duration. MI is independent of PRF.</span></td>
    </tr>
    <tr>
      <td class="s5-opt"><code>Duration</code><br><span class="s5-note">BB: <code>DurationUS</code></span></td>
      <td><strong>Sonication-on duration</strong> per cycle (s) — how long the device fires in one on/off repetition.<br><span class="s5-note">Governs cumulative thermal load per cycle. For trial-locked (online) protocols, set to the per-trial stimulus duration.</span></td>
    </tr>
    <tr>
      <td class="s5-opt"><code>DurationOff</code><br><span class="s5-note">BB: same</span></td>
      <td><strong>Rest duration</strong> per cycle (s) — silent interval between repetitions that allows tissue to dissipate heat. <code>0.0</code> = continuous block with no rest.<br><span class="s5-note">For online TUS, corresponds to the inter-trial interval (ITI). Longer DurationOff → lower peak ΔT. Offline DurationOff=0 is the conservative upper bound on thermal load.</span></td>
    </tr>
    <tr>
      <td class="s5-opt"><code>Repetitions</code><br><span class="s5-note">BB: same</span></td>
      <td><strong>Repetitions</strong> — number of on/off cycles. Total time = <code>Repetitions × (Duration + DurationOff)</code>.<br><span class="s5-note">Offline worst-case: Reps=1, long Duration, DurationOff=0. Trial-locked online: Reps = trial count, Duration = per-trial duration, DurationOff = ITI.</span></td>
    </tr>
    <tr>
      <td class="s5-opt"><code>NumberGrouped­Sonications</code><br><span class="s5-note">BB: same</span></td>
      <td><strong>Number of grouped bursts</strong> — BHTE total iterations = <code>NumberGroupedSonications × Repetitions</code>. <code>1</code> = no grouping (single block).</td>
    </tr>
    <tr>
      <td class="s5-opt"><code>PauseBetween­GroupedSonications</code><br><span class="s5-note">BB: same</span></td>
      <td><strong>Pause between groups</strong> (s) — rest inserted after every <code>Repetitions</code> cycles. <code>0.0</code> when <code>NumberGroupedSonications=1</code>.</td>
    </tr>
  </table>
  <p class="s5-note" style="margin-top:6px">Transducer params (TX_SYSTEM, frequency, aperture, focal length) and computing device/backend are auto-loaded from the site YAML in Step 5-0. Source: <a class="s5-link" href="https://proteusmrighifu.github.io/BabelBrain/pipeline/BabelBrain.html">BabelBrain documentation</a></p>
</div>

<!-- Sonication Parameters & Safety Metrics -->
<div class="s5-card">
  <div class="s5-sec-title">SONICATION PARAMETERS &amp; SAFETY METRICS <span class="s5-note">Murphy et al. (2025) Fig. 2 / Table 1</span></div>
  <svg width="100%" viewBox="0 0 750 308" xmlns="http://www.w3.org/2000/svg" style="display:block">
    <!-- Panel 1: Pulse train level (y=0-100) -->
    <text x="8" y="55" font-size="8" fill="#555" text-anchor="middle" transform="rotate(-90 8 55)" font-family="-apple-system,sans-serif">Peak-peak pressure</text>
    <line x1="25" y1="60" x2="580" y2="60" stroke="#ccc" stroke-width="0.8" stroke-dasharray="3,3"/>
    <rect x="70"  y="25" width="80" height="35" fill="#888" opacity="0.75" rx="1"/>
    <rect x="210" y="25" width="80" height="35" fill="#888" opacity="0.75" rx="1"/>
    <rect x="350" y="25" width="80" height="35" fill="#888" opacity="0.75" rx="1"/>
    <text x="470" y="48" font-size="14" fill="#bbb" font-family="serif">···</text>
    <line x1="350" y1="24" x2="370" y2="10" stroke="#555" stroke-width="0.7"/>
    <text x="374" y="9" font-size="8.5" fill="#333" font-family="-apple-system,sans-serif">Pulse train</text>
    <line x1="70"  y1="68" x2="150" y2="68" stroke="#444" stroke-width="0.8"/>
    <line x1="70"  y1="65" x2="70"  y2="71" stroke="#444" stroke-width="0.8"/>
    <line x1="150" y1="65" x2="150" y2="71" stroke="#444" stroke-width="0.8"/>
    <text x="110" y="78" font-size="7.5" fill="#444" text-anchor="middle" font-family="-apple-system,sans-serif">Pulse train duration</text>
    <line x1="70"  y1="87" x2="210" y2="87" stroke="#444" stroke-width="0.8"/>
    <line x1="70"  y1="84" x2="70"  y2="90" stroke="#444" stroke-width="0.8"/>
    <line x1="210" y1="84" x2="210" y2="90" stroke="#444" stroke-width="0.8"/>
    <text x="140" y="96" font-size="7.5" fill="#444" text-anchor="middle" font-family="-apple-system,sans-serif">Pulse train repetition interval</text>
    <!-- Panel 2: Individual pulse level (y=102-205) -->
    <line x1="25" y1="102" x2="750" y2="102" stroke="#e0e0e0" stroke-width="0.8"/>
    <text x="8" y="157" font-size="8" fill="#555" text-anchor="middle" transform="rotate(-90 8 157)" font-family="-apple-system,sans-serif">Peak (+) pressure</text>
    <line x1="25" y1="160" x2="460" y2="160" stroke="#ccc" stroke-width="0.8" stroke-dasharray="3,3"/>
    <line x1="70" y1="60" x2="70" y2="112" stroke="#ccc" stroke-width="0.7" stroke-dasharray="4,3"/>
    <line x1="150" y1="60" x2="430" y2="112" stroke="#ccc" stroke-width="0.7" stroke-dasharray="4,3"/>
    <path d="M 70,160 Q 71,147 72,160 Q 73,173 74,160 Q 75,147 76,160 Q 77,173 78,160 Q 79,147 80,160 Q 81,173 82,160 Q 83,147 84,160 Q 85,173 86,160 Q 87,147 88,160 Q 89,173 90,160 Q 91,147 92,160 Q 93,173 94,160 Q 95,147 96,160 Q 97,173 98,160 Q 99,147 100,160" fill="none" stroke="#444" stroke-width="1.1"/>
    <path d="M 170,160 Q 171,147 172,160 Q 173,173 174,160 Q 175,147 176,160 Q 177,173 178,160 Q 179,147 180,160 Q 181,173 182,160 Q 183,147 184,160 Q 185,173 186,160 Q 187,147 188,160 Q 189,173 190,160 Q 191,147 192,160 Q 193,173 194,160 Q 195,147 196,160 Q 197,173 198,160 Q 199,147 200,160" fill="none" stroke="#444" stroke-width="1.1"/>
    <path d="M 270,160 Q 271,147 272,160 Q 273,173 274,160 Q 275,147 276,160 Q 277,173 278,160 Q 279,147 280,160 Q 281,173 282,160 Q 283,147 284,160 Q 285,173 286,160 Q 287,147 288,160 Q 289,173 290,160 Q 291,147 292,160 Q 293,173 294,160 Q 295,147 296,160 Q 297,173 298,160 Q 299,147 300,160" fill="none" stroke="#444" stroke-width="1.1"/>
    <path d="M 370,160 Q 371,147 372,160 Q 373,173 374,160 Q 375,147 376,160 Q 377,173 378,160 Q 379,147 380,160 Q 381,173 382,160 Q 383,147 384,160 Q 385,173 386,160 Q 387,147 388,160 Q 389,173 390,160 Q 391,147 392,160 Q 393,173 394,160 Q 395,147 396,160 Q 397,173 398,160 Q 399,147 400,160" fill="none" stroke="#444" stroke-width="1.1"/>
    <text x="425" y="165" font-size="14" fill="#bbb" font-family="serif">···</text>
    <line x1="85" y1="146" x2="115" y2="122" stroke="#555" stroke-width="0.7"/>
    <text x="118" y="120" font-size="8.5" fill="#333" font-family="-apple-system,sans-serif">Pulse</text>
    <line x1="70"  y1="174" x2="100" y2="174" stroke="#444" stroke-width="0.8"/>
    <line x1="70"  y1="171" x2="70"  y2="177" stroke="#444" stroke-width="0.8"/>
    <line x1="100" y1="171" x2="100" y2="177" stroke="#444" stroke-width="0.8"/>
    <text x="85" y="185" font-size="7.5" fill="#444" text-anchor="middle" font-family="-apple-system,sans-serif">Pulse Duration (PD)</text>
    <line x1="70"  y1="193" x2="170" y2="193" stroke="#444" stroke-width="0.8"/>
    <line x1="70"  y1="190" x2="70"  y2="196" stroke="#444" stroke-width="0.8"/>
    <line x1="170" y1="190" x2="170" y2="196" stroke="#444" stroke-width="0.8"/>
    <text x="120" y="201" font-size="7.5" fill="#444" text-anchor="middle" font-family="-apple-system,sans-serif">Pulse repetition Interval (PRI)</text>
    <text x="510" y="148" font-size="10" fill="#555" font-family="-apple-system,sans-serif">PRI = 1 / PRF</text>
    <rect x="505" y="155" width="222" height="22" fill="#EEEDFE" rx="3"/>
    <text x="514" y="170" font-size="10.5" fill="#3C3489" font-weight="600" font-family="-apple-system,sans-serif">Pulse duty cycle (DC) = PD / PRI</text>
    <!-- Panel 3: Intensity (y=207-308) -->
    <line x1="25" y1="207" x2="750" y2="207" stroke="#e0e0e0" stroke-width="0.8"/>
    <text x="8" y="258" font-size="8" fill="#555" text-anchor="middle" transform="rotate(-90 8 258)" font-family="-apple-system,sans-serif">Intensity</text>
    <line x1="25" y1="300" x2="460" y2="300" stroke="#ccc" stroke-width="0.8"/>
    <line x1="70" y1="196" x2="70" y2="213" stroke="#ccc" stroke-width="0.7" stroke-dasharray="4,3"/>
    <line x1="430" y1="196" x2="430" y2="213" stroke="#ccc" stroke-width="0.7" stroke-dasharray="4,3"/>
    <rect x="70"  y="233" width="30" height="67" fill="#6B9DE8" opacity="0.5" rx="1"/>
    <rect x="170" y="233" width="30" height="67" fill="#6B9DE8" opacity="0.5" rx="1"/>
    <rect x="270" y="233" width="30" height="67" fill="#6B9DE8" opacity="0.5" rx="1"/>
    <rect x="370" y="233" width="30" height="67" fill="#6B9DE8" opacity="0.5" rx="1"/>
    <rect x="70"  y="280" width="360" height="20" fill="#D87AB0" opacity="0.5" rx="1"/>
    <text x="108" y="267" font-size="9.5" fill="#1E4FA8" font-style="italic" font-family="-apple-system,sans-serif">I</text>
    <text x="115" y="271" font-size="7" fill="#1E4FA8" font-family="-apple-system,sans-serif">SPPA</text>
    <text x="245" y="294" font-size="9.5" fill="#8B2060" font-style="italic" font-family="-apple-system,sans-serif">I</text>
    <text x="252" y="297" font-size="7" fill="#8B2060" font-family="-apple-system,sans-serif">SPTA</text>
    <rect x="505" y="220" width="225" height="76" fill="#f8f8f8" stroke="#e0e0e0" rx="4"/>
    <text x="516" y="241" font-size="10" fill="#1E4FA8" font-style="italic" font-family="-apple-system,sans-serif">I</text>
    <text x="523" y="244" font-size="7.5" fill="#1E4FA8" font-family="-apple-system,sans-serif">SPPA</text>
    <text x="533" y="241" font-size="10" fill="#333" font-family="-apple-system,sans-serif"> = p&#178; / (Z &#215; 2)</text>
    <line x1="510" y1="252" x2="725" y2="252" stroke="#e8e8e8" stroke-width="0.5"/>
    <text x="516" y="266" font-size="10" fill="#8B2060" font-style="italic" font-family="-apple-system,sans-serif">I</text>
    <text x="523" y="269" font-size="7.5" fill="#8B2060" font-family="-apple-system,sans-serif">SPTA</text>
    <text x="533" y="266" font-size="10" fill="#333" font-family="-apple-system,sans-serif"> = I</text>
    <text x="550" y="269" font-size="7.5" fill="#333" font-family="-apple-system,sans-serif">SPPA</text>
    <text x="561" y="266" font-size="10" fill="#333" font-family="-apple-system,sans-serif"> &#215; DC</text>
    <text x="516" y="284" font-size="8" fill="#888" font-family="-apple-system,sans-serif">p = peak pressure</text>
    <text x="516" y="293" font-size="8" fill="#888" font-family="-apple-system,sans-serif">Z = acoustic impedance</text>
  </svg>
  <table style="margin-top:8px">
    <tr><th style="width:18%">Metric</th><th style="width:26%">Formula</th><th>Meaning &amp; Safety relevance</th></tr>
    <tr>
      <td><em>I</em><sub>SPPA</sub></td>
      <td>p² / (2Z)</td>
      <td>Focal-peak intensity averaged over the pulse duration. Mechanical and thermal driver at the pulse level.</td>
    </tr>
    <tr>
      <td><em>I</em><sub>SPTA</sub></td>
      <td><em>I</em><sub>SPPA</sub> × DC</td>
      <td>Time-averaged intensity — primary thermal safety metric. <strong>Temporal window must be specified</strong> (pulse-train window vs. full session). BabelBrain BHTE solves the full Duration / DurationOff structure rather than relying on this formula alone.</td>
    </tr>
    <tr>
      <td>MI</td>
      <td>p<sub>r,3</sub> / √f</td>
      <td>Mechanical Index — cavitation risk. <strong>Independent of DC, Duration, and DurationOff</strong>; determined only by peak negative pressure and frequency. FDA diagnostic-ultrasound limit: 1.9.</td>
    </tr>
    <tr>
      <td>TI / TI<sub>c</sub></td>
      <td>—</td>
      <td>Thermal Index / Cranial Thermal Index — proportional to power at focus relative to 1 °C rise. TI<sub>c</sub> tracks skull bone heating specifically.</td>
    </tr>
  </table>
  <p class="s5-note" style="margin-top:6px">Source: Murphy et al. (2025) <em>Clin. Neurophysiol.</em> 171:192–226 &nbsp;·&nbsp; <a class="s5-link" href="https://doi.org/10.1016/j.clinph.2025.01.004">doi:10.1016/j.clinph.2025.01.004</a> &nbsp;·&nbsp; Table 1 &amp; Fig. 2</p>
</div>

<!-- Run options -->
<div class="s5-card">
  <div class="s5-sec-title">RUN OPTIONS</div>
  <table>
    <tr><th>Setting</th><th>Value</th><th>Behaviour</th></tr>
    <tr>
      <td><code>DRY_RUN</code></td>
      <td><code>False</code> <span class="s5-badge">default</span></td>
      <td>Full execution: domain → acoustic → thermal</td>
    </tr>
    <tr>
      <td></td>
      <td><code>True</code></td>
      <td>Validate paths only; no files written</td>
    </tr>
    <tr>
      <td><code>REUSE_FILES</code></td>
      <td><code>True</code> <span class="s5-badge">default</span></td>
      <td>Skip stage if output already exists (safe to re-run)</td>
    </tr>
    <tr>
      <td></td>
      <td><code>False</code></td>
      <td>Force re-run of all stages</td>
    </tr>
    <tr>
      <td><code>USE_CT</code></td>
      <td><code>False</code> <span class="s5-badge">default</span></td>
      <td>Skull from SimNIBS segmentation only</td>
    </tr>
    <tr>
      <td></td>
      <td><code>True</code></td>
      <td>Use CT/ZTE/PETRA for patient-specific skull acoustics — requires <code>CT_PATH</code></td>
    </tr>
  </table>
</div>

<!-- OUTPUT FILES -->
<div class="s5-card">
  <div class="s5-sec-title">ROLE OF STEP 5 — Dosimetry &amp; Safety</div>
  <p style="font-size:12px;color:#555;margin:0 0 8px">
    After neuronavigation coordinates are fixed in Step 4 (PlanTUS), Step 5 handles <strong>dosimetry and safety verification</strong>.
    Outputs feed directly into experimental protocol design and IRB documentation.
  </p>
  <table>
    <tr><th style="width:30%">Purpose</th><th>Description</th></tr>
    <tr>
      <td><strong>① Safety verification</strong></td>
      <td>Confirm that temperature rise in brain, skin and skull (MTB/MTS/MTC) and CEM43 thermal dose fall within IRB-approved limits. Applied uniformly across all subjects.</td>
    </tr>
    <tr>
      <td><strong>② Individualized dosing</strong></td>
      <td>
        Because skull transmission varies across subjects, the Export summary CSV is used to back-calculate the in-water intensity (IsppaWater) required to achieve the target I_SPPA in tissue — and set the TPO accordingly on the day of experiment.
        <span class="s5-note">Example: target I_SPPA(tissue) = 5 W/cm² → Sub-01: 28 W/cm² in water, Sub-02: 33 W/cm² in water</span>
      </td>
    </tr>
  </table>
  <p class="s5-note" style="margin-top:6px">&#9888;&#65039; Neuronavigation is finalized in Step 4. Step 5 focuses on dosimetry.</p>
</div>

<!-- OUTPUT FILES -->
<div class="s5-card">
  <div class="s5-sec-title">OUTPUT FILES (all in <code>m2m_{sub_id}/</code>)</div>
  <table>
    <tr><th>Stage</th><th>Filename pattern</th><th>Contents</th><th>Use</th></tr>
    <tr>
      <td>5a</td>
      <td><code>{ID}_{TX}_{freq}kHz_{PPW}PPW_BabelViscoInput.nii.gz</code></td>
      <td>Tissue mask NIfTI with acoustic material properties per voxel</td>
      <td>Input to 5b FDTD</td>
    </tr>
    <tr>
      <td>5b</td>
      <td><code>{ID}_{TX}_{freq}kHz_{PPW}PPW_Foc{f}_Diam{d}_DataForSim.h5</code></td>
      <td>HDF5: pressure field, ISPPA map, mechanical index, skull transmission</td>
      <td>Acoustic field QC &amp; input to 5c</td>
    </tr>
    <tr>
      <td>5c</td>
      <td><code>*_Thermal_Isppa{i}_DC{dc}_PRF{prf}_Dur{t}.h5</code></td>
      <td>HDF5: temperature rise map, ΔT peak, CEM43 thermal dose, MI (mechanical index)</td>
      <td>Safety verification &amp; IRB reporting. QC figure shows MI vs. FDA diagnostic-ultrasound limit of 1.9 (green = within, red = exceeds). <code>[Safety] MI = ...</code> is printed to console.</td>
    </tr>
    <tr>
      <td>5c</td>
      <td><code>*_Summary.csv</code></td>
      <td>I_SPPA(tissue) vs I_SPPA(water) table + safety metrics (MTB/MTS/MTC/CEM43)</td>
      <td><strong>TPO setting per subject (individualized dosing)</strong></td>
    </tr>
  </table>
  <p class="s5-note" style="margin-top:6px">ID = <code>{sub_id_full}_T1w_{TARGET_NAME}{TARGET_SIDE}</code></p>
</div>

<!-- Inputs / Outputs -->
<div class="s5-row2">
  <div class="s5-card" style="margin-bottom:0">
    <div class="s5-sec-title">INPUTS REQUIRED</div>
    <ul class="s5-io-list">
      <li>Site YAML <code>config/sites/</code></li>
      <li><code>m2m_{sub_id}/</code> dir <span class="s5-note">(from Step 1)</span></li>
      <li><code>m2m_{sub_id}/T1.nii.gz</code></li>
      <li><code>*_brainsight.txt</code> <span class="s5-note">(from Step 4)</span></li>
      <li>CT NIfTI <span class="s5-note">(optional — if <code>USE_CT=True</code>)</span></li>
      <li>GPU with Metal/OpenCL/CUDA</li>
    </ul>
  </div>
  <div class="s5-card" style="margin-bottom:0">
    <div class="s5-sec-title">OUTPUTS</div>
    <ul class="s5-io-list">
      <li><code>*_BabelViscoInput.nii.gz</code> <span class="s5-note">(domain)</span></li>
      <li><code>*_DataForSim.h5</code> <span class="s5-note">(acoustic)</span></li>
      <li><code>*_Thermal_*.h5</code> <span class="s5-note">(thermal, per protocol)</span></li>
    </ul>
    <div style="margin-top:8px;font-size:11px;color:#888">
      &#9888;&#65039; Step 5 is the terminal step — outputs are used for <strong>dosimetry</strong> (individualized TPO setting per subject) and <strong>safety assessment</strong> (IRB reporting). Neuronavigation coordinates are determined in Step 4.
    </div>
  </div>
</div>
<div style="margin-bottom:10px"></div>

<!-- Dependencies & References -->
<div class="s5-row2">
  <div class="s5-card" style="margin-bottom:0">
    <div class="s5-sec-title">DEPENDENCIES</div>
    <table>
      <tr><th>Tool / Package</th><th>Used for</th></tr>
      <tr><td>BabelBrain</td><td>Full pipeline orchestration (Steps 5a–5c)</td></tr>
      <tr><td>BabelViscoFDTD</td><td>FDTD acoustic solver (GPU kernels)</td></tr>
      <tr><td>pycork</td><td>CSG boolean mesh operations (domain generation)</td></tr>
      <tr><td>cupy <span class="s5-badge-gpu">CUDA</span> / metalcomputebabel <span class="s5-badge-gpu">Metal</span></td><td>GPU backend</td></tr>
      <tr><td>SimNIBS &#8805; 4.0</td><td>Head mesh (<code>m2m_*/</code>) for tissue segmentation</td></tr>
      <tr><td><code>src/utils.py</code></td><td>Shared pipeline utilities</td></tr>
    </table>
  </div>
  <div class="s5-card" style="margin-bottom:0">
    <div class="s5-sec-title">REFERENCES</div>
    <table>
      <tr><th>Tool</th><th>Citation / Link</th></tr>
      <tr>
        <td>BabelBrain</td>
        <td>Pichardo (2023) <em>IEEE Trans. Ultrason. Ferroelectr. Freq. Control</em> 70(7):587–599 &nbsp;&#124;&nbsp; <a class="s5-link" href="https://doi.org/10.1109/TUFFC.2023.3274046">doi:10.1109/TUFFC.2023.3274046</a></td>
      </tr>
      <tr>
        <td>BabelViscoFDTD</td>
        <td>Pichardo et al. (2017) <em>Phys. Med. Biol.</em> 62(17):6938 &nbsp;&#124;&nbsp; <a class="s5-link" href="https://doi.org/10.1088/1361-6560/aa7ccc">doi:10.1088/1361-6560/aa7ccc</a></td>
      </tr>
      <tr>
        <td>SimNIBS</td>
        <td>Puonti et al. (2020) <em>NeuroImage</em> 219:117109 &nbsp;&#124;&nbsp; <a class="s5-link" href="https://simnibs.github.io">simnibs.github.io</a></td>
      </tr>
      <tr>
        <td>TUS safety guidance</td>
        <td>Murphy et al. (2025) <em>Clin. Neurophysiol.</em> 171:192–226 &nbsp;&#124;&nbsp; <a class="s5-link" href="https://doi.org/10.1016/j.clinph.2025.01.004">doi:10.1016/j.clinph.2025.01.004</a></td>
      </tr>
    </table>
  </div>
</div>
<div style="margin-bottom:10px"></div>

</div>
"""

display(HTML(HTML_CONTENT))
