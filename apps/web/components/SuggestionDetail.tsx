"use client";

import type { FeedbackUpdate, SuggestionRead } from "../../../packages/shared/src";
import { dateLabel, sourceUrl, statusLabel } from "../lib/discovery";
import { analysisBlocks, analysisLabel } from "../lib/readableAnalysis";
import { Button } from "./ui/button";

export default function SuggestionDetail({ suggestion, saving, error, onFeedback, onClose }: {
  suggestion: SuggestionRead; saving: boolean; error: string | null;
  onFeedback: (status: FeedbackUpdate["status"]) => void; onClose: () => void;
}): JSX.Element {
  const articleUrl = sourceUrl(suggestion.article.original_url);
  return <section className="card h-fit min-w-0 lg:sticky lg:top-6" aria-labelledby="detail-title">
    <div className="flex items-center justify-between gap-2"><span className="eyebrow">Conexão em detalhe</span><Button size="sm" variant="ghost" onClick={onClose} aria-label="Fechar detalhes">Fechar ×</Button></div>
    <h2 id="detail-title" tabIndex={-1} className="break-words font-hand text-3xl leading-tight">{suggestion.article.label}</h2>
    <p className="text-sm"><span className="status-chip">{statusLabel[suggestion.status]}</span></p>
    {articleUrl && <a href={articleUrl} target="_blank" rel="noopener noreferrer" className="source-link">Abrir artigo na fonte ↗</a>}
    <div className="border-t border-border pt-4">
      <h3 className="mb-2 font-semibold">Como pode contribuir</h3>
      <p className="mb-4 text-xs font-medium text-muted">{analysisLabel(suggestion.justification)}</p>
      <div className="space-y-4">{analysisBlocks(suggestion.justification).map((block, index) => block.kind === "heading"
        ? <h4 key={index} className="pt-2 text-base font-semibold">{block.text}</h4>
        : <p key={index} className="whitespace-pre-wrap break-words text-sm leading-relaxed">{block.text}</p>)}</div>
      <p className="mt-3 text-xs leading-relaxed text-muted">Uma possibilidade de contribuição, a avaliar no contexto do projeto. A relação não comprova uso, implementação ou autoria.</p>
    </div>
    <div className="border-t border-border pt-4">
      <h3 className="mb-3 font-semibold">Evidências dos dois lados</h3>
      <p className="mb-4 text-xs leading-relaxed text-muted">Trechos originais, sem tradução; podem estar em inglês. Abra cada evidência para consultar o texto preservado e sua fonte.</p>
      {(["repo", "article"] as const).map(side => {
        const evidences = suggestion.evidences.filter(e => e.side === side);
        return <div key={side} className="mb-4 space-y-3">
          <p className="eyebrow">{side === "repo" ? "01 · Repositório GitHub" : "02 · Artigo OpenAlex"}</p>
          {!evidences.length && <p className="text-sm text-muted">Evidência indisponível para este lado.</p>}
          {evidences.map((e, index) => <details key={e.id} className="rounded-md border border-border bg-surface-muted p-3">
            <summary className="cursor-pointer text-sm font-medium">Consultar trecho original {index + 1} · {side === "repo" ? "GitHub" : "OpenAlex"}</summary>
            <blockquote className="mt-3 whitespace-pre-wrap break-words border-l-2 border-ink pl-3 text-sm leading-relaxed">{e.excerpt}</blockquote>
            <p className="mt-3 break-words text-xs text-muted">{e.locator}</p>
            <p className="mt-1 text-xs text-muted">Observado em {dateLabel(e.captured_at)}</p>
            {sourceUrl(e.reference_url) && <a className="source-link mt-2 inline-block" href={sourceUrl(e.reference_url)} target="_blank" rel="noopener noreferrer">Conferir na fonte ↗</a>}
            <details className="mt-2 text-xs"><summary>Versão da evidência</summary><code className="mt-2 block break-all">{e.capture_version}</code></details>
          </details>)}
        </div>;
      })}
      <p className="text-xs leading-relaxed text-muted">Trechos preservados da análise. Datas indicam observação da fonte; não são necessariamente a data de publicação ou de um commit.</p>
    </div>
    <div className="border-t border-border pt-4">
      <h3 className="mb-2 font-semibold">Temas do artigo</h3>
      <p className="mb-3 text-xs text-muted">Classificações fornecidas pelo OpenAlex nesta análise.</p>
      <ul className="flex flex-wrap gap-2" aria-label="Temas OpenAlex">{suggestion.topics.map(t => <li key={t.id} className="status-chip">{t.label}</li>)}</ul>
      {!suggestion.topics.length && <p className="text-sm text-muted">Sem temas disponíveis.</p>}
    </div>
    <div className="border-t border-border pt-4" aria-busy={saving}>
      <h3 className="mb-2 font-semibold">Esta conexão ajuda seu projeto?</h3>
      <div className="flex flex-wrap gap-2">
        <Button variant={suggestion.status === "confirmed" ? "default" : "outline"} disabled={saving} aria-pressed={suggestion.status === "confirmed"} onClick={() => onFeedback("confirmed")}>Relevante</Button>
        <Button variant={suggestion.status === "rejected" ? "default" : "outline"} disabled={saving} aria-pressed={suggestion.status === "rejected"} onClick={() => onFeedback("rejected")}>Não relevante</Button>
      </div>
      <p role="status" className="mt-3 text-xs text-muted">{saving ? "Salvando avaliação…" : `Avaliação: ${statusLabel[suggestion.status]} · ${dateLabel(suggestion.updated_at)}`}</p>
      {error && <p role="alert" className="mt-2 text-sm">{error} Sua avaliação anterior foi mantida. Tente novamente nos botões acima.</p>}
    </div>
  </section>;
}
