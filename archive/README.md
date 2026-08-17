# archive（検証履歴）

社内でアプリを動かすだけなら、このフォルダは **不要** です。
予測デスクの起動手順はリポジトリ直下の `README.md` を参照してください。

ここに入っているのは、擬似データでの精度検証・実データEDA・旧PoCなど、
開発過程のノートブックとモジュールです。分析を再現するときだけ使います。

| ファイル | 内容 |
|---|---|
| `phase1_data.ipynb` | 擬似データ生成と傾向確認 |
| `phase2_visit_model.ipynb` | 擬似データでの来店・売上予測 |
| `phase5_llm_advisor.ipynb` | 施策提案プロンプトの検証 |
| `phase6_real_eda.ipynb` | 実データのEDA |
| `phase6_5_real_forecast.ipynb` | 実データ予測の精度検証 |
| `demo.ipynb` | 旧テーマ（イベント観光）の技術検証PoC |
| `retail_synthetic_data.py` / `visit_forecast.py` | 擬似データ用の生成・予測 |
| `synthetic_data.py` | PoC用の合成データ |
| `retail_synthetic.csv` | 生成済み擬似データ |

リポジトリ直下から開いてください。ノートブック側で `src/` と `archive/` の両方を参照します。

```bash
jupyter notebook archive/phase6_5_real_forecast.ipynb
```
