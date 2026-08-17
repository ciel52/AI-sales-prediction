import type { Metadata } from "next";
import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

export const metadata: Metadata = {
  title: "青梅DX 来店予測",
  description: "日次・週次・月次の来店・売上予測と施策提案AI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body className="antialiased">
        <SiteHeader />
        {children}
      </body>
    </html>
  );
}
