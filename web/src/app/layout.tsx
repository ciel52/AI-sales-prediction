import type { Metadata, Viewport } from "next";
import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

export const metadata: Metadata = {
  title: "青梅DX 来店予測",
  description: "日次・週次・月次の来店・売上予測と施策提案AI",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja" suppressHydrationWarning>
      <body className="antialiased">
        <script
          dangerouslySetInnerHTML={{
            __html:
              "(function(){try{if(localStorage.getItem('ome-easy-read')==='1')document.documentElement.classList.add('easy-read')}catch(e){}})();",
          }}
        />
        <SiteHeader />
        {children}
      </body>
    </html>
  );
}
