const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const { mkdtempSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join, resolve } = require('node:path');
const { execFileSync } = require('node:child_process');
const web = resolve(__dirname, '..');
const output = mkdtempSync(join(tmpdir(), 'trama-analysis-tests-'));
execFileSync(join(web, 'node_modules/.bin/tsc'), ['--target', 'ES2020', '--module', 'commonjs', '--skipLibCheck', '--outDir', output, 'lib/readableAnalysis.ts'], { cwd: web });
const { analysisBlocks, analysisLabel } = require(join(output, 'readableAnalysis.js'));
after(() => rmSync(output, { recursive: true, force: true }));
test('structured analysis yields four headings and preserves complete paragraphs', () => {
  const input = 'Sugestão de contribuição, sujeita a revisão humana.\r\n\r\nO que o artigo propõe\r\nTexto integral.\r\n\r\nRelação possível com o projeto\r\nRelação cautelosa.\r\n\r\nComo explorar\r\nExperimento.\r\n\r\nLimites e incertezas\r\nLimites.';
  const blocks = analysisBlocks(input);
  assert.equal(blocks.filter(b => b.kind === 'heading').length, 4);
  assert.equal(blocks.at(-1).text, 'Limites.');
});
test('legacy text, HTML and Markdown URLs remain literal text with no inferred structure', () => {
  const legacy = 'Texto legado\nsem separação. <script>alert(1)</script> [fonte](javascript:alert(1))';
  assert.deepEqual(analysisBlocks(legacy), [{kind:'paragraph',text:legacy}]);
  assert.deepEqual(analysisBlocks(''), []);
  assert.equal(analysisLabel('Legado'), 'Explicação registrada · confira as evidências');
});
test('fallback is identified by its explicit prefix, never by an incidental quoted mention', () => {
  assert.match(analysisLabel('Hipótese exploratória — sem LLM.'), /contingência/);
  assert.doesNotMatch(analysisLabel('Sugestão de contribuição. Cita Hipótese exploratória.'), /contingência/);
  assert.doesNotMatch(analysisLabel('Texto sem modo'), /gerada/);
  assert.equal(analysisLabel('Sugestão de contribuição, sujeita a revisão humana. Template legado.'), 'Análise registrada · sujeita a revisão humana');
});
