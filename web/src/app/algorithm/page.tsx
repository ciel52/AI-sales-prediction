import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";

export const metadata: Metadata = {
  title: "予測のしくみ | 青梅DX 来店予測",
  description: "来店・売上予測に使っている機械学習アルゴリズムと特徴量の説明",
};

const TOC = [
  { id: "overview", label: "役割分担" },
  { id: "target", label: "何を予測するか" },
  { id: "ingest", label: "生データの取込" },
  { id: "algorithm", label: "アルゴリズム" },
  { id: "why", label: "なぜこれを使うか" },
  { id: "features", label: "特徴量" },
  { id: "switching", label: "モデルの使い分け" },
  { id: "accuracy", label: "精度の見方" },
  { id: "not-used", label: "使っていないもの" },
];

const LAG_ROWS = [
  { date: "11/25（月）", receipts: 90, note: "lag7 の参照日" },
  { date: "11/26（火）", receipts: 108, note: "" },
  { date: "11/27（水）", receipts: 91, note: "" },
  { date: "11/28（木）", receipts: 97, note: "" },
  { date: "11/29（金）", receipts: 110, note: "" },
  { date: "11/30（土）", receipts: 81, note: "" },
  { date: "12/01（日）", receipts: 57, note: "lag1 の参照日" },
];

export default function AlgorithmPage() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-8 max-w-3xl">
        <p className="text-xs font-semibold tracking-[0.18em] text-[var(--accent)]">
          HOW THE FORECAST WORKS
        </p>
        <h1 className="m-plus-rounded-1c-regular mt-2 text-3xl text-[var(--ink)] sm:text-4xl">
          予測アルゴリズムの説明
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-[var(--muted)]">
          画面の予測値は、大規模言語モデル（LLM）ではなく
          scikit-learn のヒストグラム勾配ブースティングが算出しています。
          店舗担当者が数字の根拠を確認できるように、何を学習し、何を使っていないかをまとめます。
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <nav className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] px-4 py-3">
            <p className="text-[11px] font-medium text-[var(--muted)]">目次</p>
            <ul className="mt-2 space-y-1">
              {TOC.map((item) => (
                <li key={item.id}>
                  <a
                    href={`#${item.id}`}
                    className="block rounded-lg px-2 py-1 text-sm text-[var(--ink)] hover:bg-[var(--wash)]"
                  >
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
            <Link
              href="/"
              className="mt-3 block rounded-xl bg-[var(--ink)] px-3 py-2 text-center text-sm font-medium text-white"
            >
              予測デスクへ戻る
            </Link>
          </nav>
        </aside>

        <div className="space-y-6">
          <Section id="overview" title="役割分担">
            <p>
              アプリは2段構成です。数値の予測と、その解釈・施策提案は別の仕組みです。
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <InfoCard title="機械学習（数値）" kicker="予測デスクの数字">
                店舗×日の来店数と客単価を予測します。同じ入力なら同じ数字が出ます。
              </InfoCard>
              <InfoCard title="LLM（言葉）" kicker="施策提案AI">
                予測結果を文脈として受け取り、人員配置や販促の打ち手を文章で提案します。予測値自体は作り変えません。
              </InfoCard>
            </div>
          </Section>

          <Section id="target" title="何を予測するか">
            <p>
              売上を1本のモデルで直接予測せず、次のように分解します。来店と客単価は動き方が違うためです。
            </p>
            <p className="m-plus-rounded-1c-regular mt-4 rounded-xl bg-[var(--wash)] px-4 py-3 text-center text-lg text-[var(--ink)]">
              予測売上 ＝ 予測来店数 × 予測客単価
            </p>
            <p className="mt-4">
              来店数（receipts）は、購買データの売上伝票（RCPT）件数です。店舗に来て会計した人数の代理指標で、通行人カウントとは別物です。
              対象は連続日次が十分にある店舗（現状86店）を1つのモデルにプールして学習しています。
            </p>
          </Section>

          <Section id="ingest" title="生データの取込">
            <p>
              予測モデルは伝票1件ずつではなく、店舗×日に集計した表を学習します。生の購買履歴をそのまま特徴量にはしません。
            </p>
            <p className="m-plus-rounded-1c-regular mt-4 rounded-xl bg-[var(--wash)] px-4 py-3 text-center text-sm text-[var(--ink)]">
              生の購買伝票 → 店舗×日パネル → モデル学習 → 予測
            </p>
            <p className="mt-4">
              学習に使うのはサーバ上の店舗×日CSV（
              <code className="rounded bg-[var(--wash)] px-1">data/real_store_daily.csv</code>
              ）です。ブラウザからのファイルアップロードは行いません。社内DB連携後は、そこから同じCSV（または同等のパネル）を用意する想定です。
              生の購買履歴から作る場合は、起動時に
              <code className="rounded bg-[var(--wash)] px-1">test_data/</code>
              または <code className="rounded bg-[var(--wash)] px-1">RAW_BUYING_PATH</code>
              から自動で集計します。
            </p>
          </Section>

          <Section id="algorithm" title="アルゴリズム">
            <p>
              来店・客単価とも、scikit-learn の
              <code className="mx-1 rounded bg-[var(--wash)] px-1.5 py-0.5 text-[13px]">
                HistGradientBoostingRegressor
              </code>
              （ヒストグラム勾配ブースティング）です。決定木を少しずつ足して誤差を減らす GBDT の一種で、LightGBM と同じ系統です。
            </p>
            <ol className="mt-4 list-decimal space-y-2 pl-5">
              <li>最初の木は、平均来店数などの粗い予測を出します。</li>
              <li>その誤差（残差）を次の木が学習します。</li>
              <li>最大500本まで繰り返し、最終予測は全木の合計になります。</li>
            </ol>
            <p className="mt-4">
              「ヒストグラム」とは、特徴量を連続値のまま切らず、ビンにまとめてから分割を探す方式です。学習が速く、欠損値もそのまま扱えます。
              木なので「日曜かつこの店なら来店が落ちる」といった組み合わせを、掛け算の特徴を手で作らずに拾えます。
            </p>
            <div className="mt-4 overflow-x-auto rounded-xl border border-[var(--line)]">
              <table className="w-full text-left text-sm">
                <thead className="bg-[var(--wash)] text-xs text-[var(--muted)]">
                  <tr>
                    <th className="px-3 py-2 font-medium">設定</th>
                    <th className="px-3 py-2 font-medium">来店モデル</th>
                    <th className="px-3 py-2 font-medium">客単価モデル</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-[var(--line)]">
                    <td className="px-3 py-2">木の本数上限</td>
                    <td className="px-3 py-2">500</td>
                    <td className="px-3 py-2">300</td>
                  </tr>
                  <tr className="border-t border-[var(--line)]">
                    <td className="px-3 py-2">学習率</td>
                    <td className="px-3 py-2">0.05</td>
                    <td className="px-3 py-2">0.05</td>
                  </tr>
                  <tr className="border-t border-[var(--line)]">
                    <td className="px-3 py-2">木の深さ</td>
                    <td className="px-3 py-2">6</td>
                    <td className="px-3 py-2">4</td>
                  </tr>
                  <tr className="border-t border-[var(--line)]">
                    <td className="px-3 py-2">早期終了</td>
                    <td className="px-3 py-2">あり（検証15%）</td>
                    <td className="px-3 py-2">なし</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-[var(--muted)]">
              来店は曜日×店舗×ラグの組み合わせが効くので少し深く、客単価は変動が小さいので浅くしています。店舗IDは数値ではなくカテゴリ特徴として渡しています。
            </p>
          </Section>

          <Section id="why" title="なぜヒストグラム勾配ブースティングを使うか">
            <p>
              他の機械学習と精度を総当たり比較して勝った、という選定ではありません。
              この課題の性質に最初から合う本命として選び、単純なルール（7日前の実績、曜日平均など）に勝てることを検証して固定しています。
            </p>
            <ul className="mt-4 list-disc space-y-2 pl-5">
              <li>
                入力が表形式で、数量（来店ラグ）と区分（曜日・祝日・店舗）が混ざっている。
              </li>
              <li>
                行数が数千〜1万程度で、ニューラルネットより木モデルの方が安定しやすい。
              </li>
              <li>
                前年同日ラグのように欠損が出る列を、行を落とさず学習できる。
              </li>
              <li>
                既存の Python / scikit-learn 資産のまま、追加ライブラリなしでノートからAPIまで同じモデルを呼べる。
              </li>
            </ul>
            <p className="mt-4">
              LightGBM は同じ系統で精度差は小さい見込みです。差し替えより、通年データの追加や年末イベントの特徴量化の方が精度への寄与が大きい、という位置づけです。
            </p>
          </Section>

          <Section id="features" title="特徴量">
            <p>
              予測時点で翌日以降の実績は使いません。ラグはすべて1日以上ずらしています（リーク対策）。
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <InfoCard title="カレンダー（区分）" kicker="0/1 や曜日番号">
                曜日、月、週番号、週末、祝日、給料日前後（24〜26日）、月初、月末。店舗IDも含みます。
              </InfoCard>
              <InfoCard title="ラグ・移動平均（数量）" kicker="何人来たか">
                1日前・7日前の来店、直近7日・30日平均、前日の売上・客単価・会員数。当日の実績は入れません。
              </InfoCard>
            </div>

            <h3 className="mt-6 text-sm font-semibold text-[var(--ink)]">
              具体例：店舗 005497 の 2024-12-02（月）
            </h3>
            <p className="mt-2">
              この日の実績来店は 105 件ですが、これは答えなので特徴には使いません。モデルに渡すのは前日までの数字です。
            </p>
            <div className="mt-3 overflow-x-auto rounded-xl border border-[var(--line)]">
              <table className="w-full text-left text-sm">
                <thead className="bg-[var(--wash)] text-xs text-[var(--muted)]">
                  <tr>
                    <th className="px-3 py-2 font-medium">日付</th>
                    <th className="px-3 py-2 font-medium">来店</th>
                    <th className="px-3 py-2 font-medium">12/02 から見た役割</th>
                  </tr>
                </thead>
                <tbody>
                  {LAG_ROWS.map((row) => (
                    <tr key={row.date} className="border-t border-[var(--line)]">
                      <td className="px-3 py-2">{row.date}</td>
                      <td className="px-3 py-2">{row.receipts}</td>
                      <td className="px-3 py-2 text-[var(--muted)]">
                        {row.note || "7日平均の構成日"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="mt-3 space-y-1 text-sm">
              <li>
                <strong>lag1</strong>＝57（12/01）。直近の勢いですが、曜日が違います。
              </li>
              <li>
                <strong>lag7</strong>＝90（11/25）。先週の同じ曜日。重要度が最も高い特徴です。
              </li>
              <li>
                <strong>7日移動平均</strong>＝90.57（上表7日の平均）。1日のブレをならした最近の水準です。
              </li>
            </ul>
            <p className="mt-4 text-xs text-[var(--muted)]">
              特徴を1つずつ壊して誤差が増える量（permutation importance）では、7日前来店 0.49、店舗 0.35、曜日 0.12 で上位3つがほぼすべてです。
            </p>
          </Section>

          <Section id="switching" title="モデルの使い分け">
            <p>
              ラグ特徴は「その日の前日・前週の実績」が必要です。実績が無い将来日では使えないため、日付ごとにモデルを切り替え、画面の「予測方式」に出します。
            </p>
            <div className="mt-4 overflow-x-auto rounded-xl border border-[var(--line)]">
              <table className="w-full text-left text-sm">
                <thead className="bg-[var(--wash)] text-xs text-[var(--muted)]">
                  <tr>
                    <th className="px-3 py-2 font-medium">予測方式</th>
                    <th className="px-3 py-2 font-medium">使うとき</th>
                    <th className="px-3 py-2 font-medium">精度の目安</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-[var(--line)]">
                    <td className="px-3 py-2">実績ラグあり（高精度）</td>
                    <td className="px-3 py-2">前日・前週の実績が揃う日</td>
                    <td className="px-3 py-2">来店MAPE 約8%（通常期）</td>
                  </tr>
                  <tr className="border-t border-[var(--line)]">
                    <td className="px-3 py-2">カレンダー予測</td>
                    <td className="px-3 py-2">
                      実績は無いが、対象月が学習データにある（10〜12月）
                    </td>
                    <td className="px-3 py-2">来店MAPE 約9%</td>
                  </tr>
                  <tr className="border-t border-[var(--line)]">
                    <td className="px-3 py-2">曜日ベース予測（学習外の時期）</td>
                    <td className="px-3 py-2">
                      学習に無い月（現状の1〜9月）
                    </td>
                    <td className="px-3 py-2">季節変動を含まない参考値</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="mt-4">
              対象日そのものの実績が無いときは、同じ月日の過去実績を前年→前々年の順に探して参考値として併記します。曜日は一致しないことがあるため、表では参照日の曜日も表示します。
            </p>
          </Section>

          <Section id="accuracy" title="精度の見方">
            <p>
              学習はランダム分割せず、過去で学習して未来で検証します（時系列分割）。指標は MAE / RMSE / MAPE に加え、来店が多い繁忙日に絞った誤差です。
            </p>
            <div className="mt-4 overflow-x-auto rounded-xl border border-[var(--line)]">
              <table className="w-full text-left text-sm">
                <thead className="bg-[var(--wash)] text-xs text-[var(--muted)]">
                  <tr>
                    <th className="px-3 py-2 font-medium">検証期間</th>
                    <th className="px-3 py-2 font-medium">来店MAPE</th>
                    <th className="px-3 py-2 font-medium">備考</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-[var(--line)]">
                    <td className="px-3 py-2">10月後半</td>
                    <td className="px-3 py-2">15%</td>
                    <td className="px-3 py-2 text-[var(--muted)]">通常期</td>
                  </tr>
                  <tr className="border-t border-[var(--line)]">
                    <td className="px-3 py-2">11月後半 / 12月前半</td>
                    <td className="px-3 py-2">8%</td>
                    <td className="px-3 py-2 text-[var(--muted)]">通常期・最も良好</td>
                  </tr>
                  <tr className="border-t border-[var(--line)]">
                    <td className="px-3 py-2">12月後半（年末）</td>
                    <td className="px-3 py-2">29%</td>
                    <td className="px-3 py-2 text-[var(--muted)]">
                      学習データに年末の急落が無い
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="mt-4">
              比較相手は機械学習ではなく、7日前の実績・7日移動平均・店舗×曜日平均です。通常期はこれらを上回ります。年末の悪化はアルゴリズムの見直しより、休業日や初売りなどの確定イベントを特徴に足す方が効きます。
            </p>
          </Section>

          <Section id="not-used" title="使っていないもの">
            <ul className="list-disc space-y-2 pl-5">
              <li>
                SNSやニュースのイベント情報は、学習用の特徴量には入れていません。過去分を遡れず、希少イベントは統計的に学習できないためです。施策提案AIの文脈としては使う方針です。
              </li>
              <li>
                当日の通行人カウントは、来店そのものに近く循環になるため特徴にしません。
              </li>
              <li>
                LLMに実績を大量投入して数値予測させる方式は採用していません。再現性・リーク管理・説明責任の点で、店舗向けの確定値には向かないためです。
              </li>
            </ul>
            <p className="mt-4">
              画面の予測方式が「曜日ベース」のときは、学習データに無い時期の参考値です。人員計画の確定値としては幅を持って読んでください。
            </p>
          </Section>
        </div>
      </div>
    </main>
  );
}

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className="scroll-mt-6 rounded-2xl border border-[var(--line)] bg-[var(--panel)] px-5 py-5 sm:px-6"
    >
      <h2 className="font-display text-xl text-[var(--ink)]">{title}</h2>
      <div className="mt-3 space-y-3 text-sm leading-relaxed text-[var(--ink)]">
        {children}
      </div>
    </section>
  );
}

function InfoCard({
  title,
  kicker,
  children,
}: {
  title: string;
  kicker: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl bg-[var(--wash)] px-4 py-3">
      <p className="text-[11px] text-[var(--muted)]">{kicker}</p>
      <p className="mt-0.5 font-medium text-[var(--ink)]">{title}</p>
      <p className="mt-1 text-sm leading-relaxed text-[var(--muted)]">{children}</p>
    </div>
  );
}
