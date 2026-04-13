import type { Metadata } from "next";
import type { ReactNode } from "react";

import { getAppTitle } from "@/lib/env";

import "./globals.css";


export const metadata: Metadata = {
  title: `${getAppTitle()} | Next.js MVP`,
  description: "Prvni migrovana internetova vrstva dashboardu nad existujicim FastAPI.",
};


export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="cs">
      <body>{children}</body>
    </html>
  );
}
