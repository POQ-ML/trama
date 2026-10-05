import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "TRAMA — Agente de Contexto Acadêmico",
  description: "HUD de contexto acadêmico: mapa, fontes e timeline (MVP mockado)."
};

export default function RootLayout({
  children
}: {
  children: ReactNode;
}): JSX.Element {
  return (
    <html lang="pt-BR" className="dark">
      <body className="min-h-screen bg-void font-sans text-slate-200 antialiased">
        {children}
      </body>
    </html>
  );
}
