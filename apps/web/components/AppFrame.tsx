import type { ReactNode } from 'react';
import Navbar from './Navbar';
export default function AppFrame({ children }: { children: ReactNode }): JSX.Element {
  return <><a href="#main-content" className="skip-link">Ir para o conteúdo</a><Navbar />
    <main id="main-content" className="mx-auto max-w-[1440px] px-5 py-8 sm:px-9 sm:py-12">{children}</main>
    <footer className="mx-auto flex max-w-[1440px] flex-wrap justify-between gap-3 border-t border-border px-5 py-6 text-xs text-muted sm:px-9"><span>TRAMA · Contexto que conecta.</span><span>Espaço local compartilhado · sem contas individuais.</span></footer></>;
}
