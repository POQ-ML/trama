export type AnalysisBlock = { kind: "heading" | "paragraph"; text: string };

// Only standalone, known section names become headings. Everything else stays
// literal React text: no HTML, Markdown links, or model-provided URLs parsed.
const headings = /^(?:o que o artigo propõe|relação possível com o projeto|como explorar|limites e incertezas)$/i;

export function analysisBlocks(text: string): AnalysisBlock[] {
  const blocks: AnalysisBlock[] = [];
  let paragraph: string[] = [];
  const flush = (): void => {
    if (paragraph.length) blocks.push({ kind: "paragraph", text: paragraph.join("\n") });
    paragraph = [];
  };
  for (const line of text.replace(/\r\n?/g, "\n").split("\n")) {
    const title = line.trim().replace(/^#{1,4}\s+/, "").replace(/^\*\*(.*?)\*\*:?$/, "$1").replace(/:$/, "");
    if (headings.test(title)) { flush(); blocks.push({ kind: "heading", text: title }); }
    else if (!line.trim()) flush();
    else paragraph.push(line);
  }
  flush();
  return blocks;
}

export function analysisLabel(text: string): string {
  if (/^\s*Hipótese exploratória\b/i.test(text)) return "Hipótese exploratória · contingência textual";
  if (/^\s*(?:Sugestão de contribuição|Análise gerada)/i.test(text)) return "Análise registrada · sujeita a revisão humana";
  return "Explicação registrada · confira as evidências";
}
