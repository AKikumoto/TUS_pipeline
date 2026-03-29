# TUS Sonication Parameters — Definitions and User Control

Reference: Murphy et al. (2025), *Clinical Neurophysiology* 171:192–226 (Table 1).  
See also: `config/TUS_sonification_settings.xlsx`

---

## 1. ユーザーが直接設定できるパラメータ

| パラメータ | 略称・単位 | 定義 | 補足 |
|---|---|---|---|
| **Operating Frequency** | f₀ (kHz / MHz) | トランスデューサーの発振周波数。ほとんどのデバイスでは固定（例: CTX-500 は 500 kHz）。 | 低周波ほど頭蓋骨透過率が高い。高周波ほど空間分解能が高い。 |
| **Pulse Duration (PD)** | PD (ms) | 1パルスの持続時間（連続照射照射の場合はPulse Train Durationと同値）。 | "Burst"と呼ばれることもあるが、Murphyらは用語統一のためPulse Durationを推奨。 |
| **Pulse Repetition Frequency** | PRF (Hz) | パルスを繰り返す頻度（= 1 / PRI）。 | PRIはPulse Repetition Interval: 2パルスの開始点間の時間。 |
| **Pulse Repetition Interval** | PRI (ms) | 連続する2パルスの開始点間の時間（= 1 / PRF）。 | PeriodまたはIPIと呼ばれることもある。 |
| **Pulse Train Duration (PTD)** | PTD (s) | 一連のパルス列（Pulse Train）が照射される全時間。 | 1トライアルあたりの照射時間に相当。 |
| **Pulse Train Repetition Interval** | PTRI (s) | パルス列の開始点間の時間。 | トライアル間インターバル（ITI）に対応。 |
| **Duty Cycle** | DC (%) | 照射時間の割合 = PD / PRI × 100。矩形波パルスでのみ定義。 | 例: PD 30 ms、Period 100 ms → DC = 30%。 |
| **Timer** | — (s) | 全刺激時間の合計。0 = 外部制御（トリガー制御）。 | 多くの場合 40 s 程度の1試行で設定。 |
| **Focal Depth / Focus** | — (mm) | 頭皮表面からフォーカスまでの距離。デバイスにより選択制または固定。 | CTX-500: 41.4–69.7 mm の範囲で設定可能。 |
| **Power / Ch (max)** | W / ch | チャンネルごとに設定する最大出力電力。 | 多くのデバイスでは上限設定が可能。 |
| **Waveform Mode** | — | 連続波（CW）またはパルス波（PW）の選択。通常はパルス波。 | CWは熱負荷リスクが高い。 |

---

## 2. 自動計算されるパラメータ（直接設定不可）

| パラメータ | 略称・単位 | 定義 | 算出式 |
|---|---|---|---|
| **Pactual** | W / ch | 実際に出力された電力。設定値とインピーダンスから自動制御。 | デバイス内部で決定 |
| **ISPPA** | W/cm² | Spatial Peak Pulse Average Intensity: フォーカスのピーク地点でパルス持続時間に渡り平均した強度。安全性評価の主指標。 | PII / PD |
| **ISPTA** | mW/cm² または W/cm² | Spatial Peak Temporal Average Intensity: ISPPA × Duty Cycle。熱的負荷の指標。 | ISPPA × DC |
| **ISPTP** | W/cm² | Spatial Peak Temporal Peak Intensity: 瞬間的なピーク強度。 | max(p²sp(t)) / Z |
| **Mechanical Index (MI)** | — (無次元) | キャビテーション発生リスクの指標。pr.3は0.3 dB/cm/MHz で減衰補正した圧力。 | pr.3 / √f₀ |
| **Thermal Index (TI)** | — (無次元) | 熱的バイオエフェクトのリスク指標。 | 装置が自動計算 |
| **TIC** | — (無次元) | Cranial Thermal Index: 頭蓋骨での温度上昇リスク。 | 出力をW/0.210 W で除算 |

---

## 3. 圧力・強度の基本量（報告・解釈に必要）

| パラメータ | 略称・単位 | 定義 |
|---|---|---|
| **Acoustic Pressure** | p (MPa) | 周囲圧力からの瞬間的な圧力偏差。 |
| **Peak Positive Pressure** | p+ (MPa) | 音波の圧縮ピーク圧力（pc とも表記）。 |
| **Peak Negative Pressure** | p− (MPa) | 音波の希薄化（rarefaction）最大負圧（pr とも表記）。キャビテーションに関与。 |
| **Spatial Peak Pressure** | psp (MPa) | パルスの定常部分でのフォーカスピーク圧力。 |
| **Pulse Intensity Integral** | PII | パルス持続時間中の瞬間強度の積分値。 |
| **Instantaneous Intensity** | I(t) (W/cm²) | 時刻tにおける瞬間強度。= p² / (密度 × 音速) = p² / Z |

---

## 4. CTX-500 (RIKEN) の固定パラメータ

| パラメータ | 値 | 備考 |
|---|---|---|
| Frequency (f₀) | 500 kHz | 変更不可 |
| Focal Distance 範囲 | 41.4–69.7 mm | 頭皮から焦点まで |
| Max Power/Ch | 8.762 W | デフォルト上限 |

---

## 5. 安全基準の目安

参考値（デバイス仕様・規制文書により異なる）：

| 指標 | 推奨上限 | 根拠 |
|---|---|---|
| ISPTA | < 720 mW/cm² | FDA diagnostic ultrasound guideline（目安） |
| MI | < 1.9 | FDA 非診断用超音波の安全指針 |
| TIC | < 6 | 頭蓋骨熱上昇リスク（ITRUSSTガイドライン参照） |

> **Note:** TUS神経刺激の安全基準は現在も標準化途中。最新ガイドラインは [ITRUSST website](https://itrusst.com) および Murphy et al. (2025) を参照。

---

## 6. 用語の揺れに関する注意

Murphy et al. (2025) は用語の不統一が再現性を損なうと指摘している：

| 混同されやすい用語 | 推奨される用語 | 意味 |
|---|---|---|
| "Burst" | Pulse Duration (PD) | 1パルスの持続時間 |
| "Sonication" | Pulse Train Duration | パルス列全体の時間 |
| "Stimulus" | 文脈による — 明示が必要 | 文脈依存のため明示推奨 |
| "Period" | Pulse Repetition Interval (PRI) | インターバル含むパルス周期 |

---

*Last updated: 2026-03-23. Source: Murphy et al. 2025 Table 1; `TUS_sonification_settings.xlsx`.*
