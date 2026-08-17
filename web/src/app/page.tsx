"use client";

import { useState } from "react";
import Link from "next/link";
import { ChatPanel } from "@/components/ChatPanel";
import { PredictPanel, useShopsBootstrap } from "@/components/PredictPanel";
import { API_BASE, type Granularity, type PredictResponse } from "@/lib/api";

export default function HomePage() {
  const { shops, shopId, setShopId, bootError, booting } = useShopsBootstrap();
  const [granularity, setGranularity] = useState<Granularity>("daily");
  const [result, setResult] = useState<PredictResponse | null>(null);
  const [loading, setLoading] = useState(false);

  return (
    <main className="mx-auto min-h-screen max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-8">
        <h1 className="m-plus-rounded-1c-regular text-3xl text-[var(--ink)] sm:text-4xl">
          来店・売上予測デスク
        </h1>
        <p className="m-plus-rounded-1c-regular mt-2 max-w-2xl text-sm text-[var(--muted)]">
          日次・週次・月次の予測を実行し、施策提案AIと対話しながら打ち手を検討します。
          数字の根拠は
          <Link href="/algorithm" className="mx-1 text-[var(--accent)] underline-offset-2 hover:underline">
            予測のしくみ
          </Link>
          を参照してください。
          <br />
          API: <code className="m-plus-rounded-1c-regular text-[var(--ink)]">{API_BASE}</code>
        </p>
      </header>

      {booting && (
        <p className="mb-6 rounded-xl border border-[var(--line)] bg-[var(--panel)] px-4 py-3 text-sm text-[var(--muted)]">
          店舗一覧を読み込み中…
        </p>
      )}

      {!booting && bootError && (
        <p className="mb-6 rounded-xl border border-[var(--line)] bg-white px-4 py-3 text-sm text-[var(--muted)]">
          APIに接続できません。API が起動しているか確認してください。
          <br />
          {bootError}
        </p>
      )}

      {!booting && !bootError && shops.length === 0 && (
        <p className="mb-6 rounded-xl border border-[var(--line)] bg-white px-4 py-3 text-sm text-[var(--muted)]">
          学習データ（<code className="text-[var(--ink)]">data/real_store_daily.csv</code>
          ）がまだありません。ファイルを配置して API を再起動してください。取込はサーバ側で行います。
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <PredictPanel
          shops={shops}
          shopId={shopId}
          setShopId={setShopId}
          granularity={granularity}
          setGranularity={setGranularity}
          result={result}
          setResult={setResult}
          loading={loading}
          setLoading={setLoading}
        />
        <ChatPanel
          result={result}
          shopId={shopId}
          granularity={granularity}
        />
      </div>
    </main>
  );
}
