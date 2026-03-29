# TUS Sonication Settings — Experiment Examples

This file collects sonication parameter sets per experiment/target for cross-reference.
**Add new entries as experiments are planned or run.**

Source: `config/TUS_sonification_settings.xlsx`  
Parameter definitions: [parameters.md](parameters.md)

---

## ラボのデフォルト設定（RIKEN CTX-500）

RIKEN の CTX-500 で使用する基準パラメータ（`標準(default)` シートより）。

| パラメータ | 値 | 備考 |
|---|---|---|
| Power/Ch (max) | 8.762 W | チャンネル最大出力 |
| Pactual (W/ch) | 8.762 W | 実測出力 |
| ISPPA | 16.35 W/cm² | 空間ピーク・パルス平均強度 |
| ISPTA | 6.54 W/cm² | 空間ピーク・時間平均強度 |
| Frequency | 500 kHz | 固定 |
| Focus | 69.7 mm | 頭皮からフォーカスまで |
| Pulse Duration (Burst) | 200 ms | 1パルス |
| Period (PRI) | 500 ms | パルス周期 |
| Timer | 0 ms (外部制御) | |
| Duty Cycle | 0.4 | = 200 / 500 ms |

---

## 実験・ターゲット別パラメータ

詳細データは `config/TUS_sonification_settings.xlsx` の `実験例` シートを参照。  
以下は主要な違いをまとめた比較表。

### 比較表

| パラメータ | RIKEN default | LC (Follini, monkey LC) | Ce_CeA (Haruno) | aMCC / ERROR (Xin) |
|---|---|---|---|---|
| Power/Ch (max) | 8.762 W | — | — | 5.739 W |
| Pactual (W/ch) | 8.762 W | — | — | 5.739 W |
| ISPPA | 16.35 W/cm² | 51.0 W/cm² | 30.02 W/cm² | 29.99 W/cm² |
| ISPTA | 6.54 W/cm² | 17.1 W/cm² | 9.00 W/cm² | 8.99 W/cm² |
| Frequency | 500 kHz | 250 kHz | 500 kHz | 500 kHz |
| Focus | 69.7 mm | 63.2 mm | 41–67.4 mm | 45–60 mm |
| Pulse Duration | 200 ms | 30 ms | 30 ms | 30 ms |
| Period (PRI) | 500 ms | 100 ms | 100 ms | 100 ms |
| Timer | — | 40 s | 40 s | 40 s |
| Duty Cycle | 0.4 | 0.3 | 0.3 | 0.3 |

---

## 実験計画（ラボ内）

`実験計画` シートより。各行はパラメータ（上から: Power max, Pactual, ISPPA, ISPTA, Freq, Focus, PD, Period, Timer, DC）。

### STRESS — Amygdala

| パラメータ | 値 |
|---|---|
| Focus | 41–67.4 mm |
| Pulse Duration | 30 ms |
| Period | 100 ms |
| Timer | 40 s |
| Duty Cycle | 0.3 |

> Power/ISPPA/ISPTA は未確定（計画中）。

---

### ERROR — aMCC（`60 mm diameter transducer`）

| パラメータ | 値 |
|---|---|
| Power/Ch (max) | 5.739 W |
| Pactual (W/ch) | 5.739 W |
| ISPPA | 29.99 W/cm² |
| ISPTA | 8.99 W/cm² |
| Frequency | 500 kHz |
| Focus | 60 mm diameter transducer |
| Pulse Duration | 30 ms |
| Period | 100 ms |
| Timer | 40 s |
| Duty Cycle | 0.3 |

---

### LS learning — LC

CTX-500 デフォルト設定をそのまま使用。

| パラメータ | 値 |
|---|---|
| Power/Ch (max) | 8.762 W |
| Pactual (W/ch) | 8.762 W |
| ISPPA | 16.35 W/cm² |
| ISPTA | 6.54 W/cm² |
| Frequency | 500 kHz |
| Focus | 69.7 mm |
| Pulse Duration | 200 ms |
| Period | 500 ms |
| Timer | 40 s |
| Duty Cycle | 0.4 |

---

## Xinさんへ — aMCC 設定

`Xinさんへ` シートより（Xin氏への共有用設定）。

| パラメータ | 値 |
|---|---|
| Power/Ch (max) | 5.739 W |
| Pactual (W/ch) | 5.739 W |
| ISPPA | 29.99 W/cm² |
| ISPTA | 8.99 W/cm² |
| Frequency | 500 kHz (変更不可) |
| Focus | 45–60 mm |
| Pulse Duration | 30 ms |
| Period | 100 ms |
| Timer | 40 s |
| Duty Cycle | 0.3 |

---

## 外部文献の参考パラメータ

### LC — Follini et al. (monkey LC)

| パラメータ | 値 |
|---|---|
| ISPPA | 51.0 W/cm² |
| ISPTA | 17.1 W/cm² |
| Frequency | 250 kHz |
| Focus | 63.2 mm |
| Pulse Duration | 30 ms |
| Period | 100 ms |
| Timer | 40 s |
| Duty Cycle | 0.3 |

### IFC / daINS — Osada et al.

| パラメータ | 値 |
|---|---|
| ISPPA | 35.8 W/cm² |
| Frequency | 500 kHz |
| Focus | 60 mm diameter transducer |
| Pulse Duration | 30 ms |
| Period | 100 ms |
| Timer | 40 s |
| Duty Cycle | 0.3 |

> Focal distance は "not reported (±0.53 mm accuracy)" と記載。

---

## 新しいエントリの追加方法

1. `config/TUS_sonification_settings.xlsx` の `実験例` または `実験計画` シートに記入
2. このファイルに対応セクションを追加（上記フォーマットに準拠）
3. 論文や他ラボの設定を参照した場合は出典（著者・年・DOI）を記載

*Last updated: 2026-03-23.*
