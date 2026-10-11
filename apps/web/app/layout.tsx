import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "TRAMA — Agente de Contexto Acadêmico",
  description: "Mapa de contexto acadêmico: fontes, relações e timeline (MVP mockado)."
};

export default function RootLayout({
  children
}: {
  children: ReactNode;
}): JSX.Element {
  return (
    <html lang="pt-BR">
      <head>
        <link
          rel="preconnect"
          href="https://fonts.googleapis.com"
        />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Patrick+Hand&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen bg-bg font-sans text-ink antialiased">
        {children}
      </body>
    </html>
  );
}
