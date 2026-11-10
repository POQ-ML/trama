const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const { mkdtempSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join, resolve } = require('node:path');
const { execFileSync } = require('node:child_process');
const web = resolve(__dirname, '..');
const output = mkdtempSync(join(tmpdir(), 'trama-orbit-tests-'));
execFileSync(join(web, 'node_modules/.bin/tsc'), ['--target', 'ES2020', '--module', 'commonjs', '--skipLibCheck', '--outDir', output, 'lib/contextMapLayout.ts'], {cwd:web});
const { orbitLayout, MAP_WIDTH, MAP_HEIGHT, MAP_CENTER, ARTICLE_WIDTH, ARTICLE_HEIGHT } = require(join(output, 'contextMapLayout.js'));
after(() => rmSync(output, {recursive:true, force:true}));

test('each supported orbit keeps article cards inside the canvas and disjoint from the hub and other cards', () => {
  for (let count = 0; count <= 5; count++) {
    const positions = orbitLayout(count);
    assert.equal(positions.length, count);
    for (const [index, p] of positions.entries()) {
      assert.ok(p.x - ARTICLE_WIDTH / 2 >= 0 && p.x + ARTICLE_WIDTH / 2 <= MAP_WIDTH);
      assert.ok(p.y - ARTICLE_HEIGHT / 2 >= 0 && p.y + ARTICLE_HEIGHT / 2 <= MAP_HEIGHT);
      const nearX = Math.max(Math.abs(p.x-MAP_CENTER.x)-ARTICLE_WIDTH/2,0);
      const nearY = Math.max(Math.abs(p.y-MAP_CENTER.y)-ARTICLE_HEIGHT/2,0);
      assert.ok(Math.hypot(nearX, nearY) > 112, 'card must clear the central ring');
      for (const other of positions.slice(index+1)) {
        assert.ok(Math.abs(p.x-other.x) >= ARTICLE_WIDTH || Math.abs(p.y-other.y) >= ARTICLE_HEIGHT, 'article rectangles must not overlap');
      }
      for (const value of Object.values(p)) assert.ok(Number.isFinite(value));
    }
  }
});

test('large result sets require bounded map pagination rather than crowded orbits', () => {
  for (const count of [-1, 6, 20, NaN, 1.5]) assert.throws(() => orbitLayout(count), RangeError);
});
