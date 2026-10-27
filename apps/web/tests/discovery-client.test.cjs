const { test, after } = require("node:test");
const assert = require("node:assert/strict");
const { mkdtempSync, rmSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join, resolve } = require("node:path");
const { execFileSync } = require("node:child_process");

// Exercise the real adapter without adding test dependencies or emitting into src.
const web = resolve(__dirname, "..");
const output = mkdtempSync(join(tmpdir(), "trama-client-tests-"));
execFileSync(join(web, "node_modules/.bin/tsc"), [
  "--target", "ES2020", "--module", "commonjs", "--moduleResolution", "node",
  "--skipLibCheck", "--strict", "--outDir", output, "lib/discovery.ts",
], { cwd: web, stdio: "pipe" });
const { ApiError, discoveryApi, monitorApi, request, sourceUrl } = require(join(output, "apps/web/lib/discovery.js"));
after(() => rmSync(output, { recursive: true, force: true }));

test("source links reject executable protocols and malformed URLs", () => {
  for (const value of [null, "javascript:alert(1)", "data:text/html,test", "/relative", "not a URL"]) {
    assert.equal(sourceUrl(value), undefined);
  }
  assert.equal(sourceUrl("https://openalex.org/W123"), "https://openalex.org/W123");
});

test("error envelopes preserve retry policy but never display arbitrary backend messages", async t => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async () => new Response(JSON.stringify({ error: {
    code: "source_unavailable", message: "internal private diagnostic", retryable: true,
  } }), { status: 503 });
  await assert.rejects(request("/discoveries/example", new AbortController().signal), error => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 503);
    assert.equal(error.code, "source_unavailable");
    assert.equal(error.retryable, true);
    assert.ok(!error.message.includes("private diagnostic"));
    return true;
  });
});

test("non-JSON failures get a safe non-retryable 404", async t => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async () => new Response("<html>missing</html>", { status: 404 });
  await assert.rejects(request("/discoveries/example", new AbortController().signal), error =>
    error instanceof ApiError && !error.retryable && !error.message.includes("<html>"));
});

test("cancellation reaches the underlying request and requests do not use cached pages", async t => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const controller = new AbortController();
  let reachedSignal;
  globalThis.fetch = async (_url, init) => {
    assert.equal(init.cache, "no-store");
    assert.equal(init.headers["Content-Type"], undefined);
    reachedSignal = init.signal;
    return new Promise((_resolve, reject) => init.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true }));
  };
  const pending = discoveryApi.read("run-id", controller.signal);
  controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
  assert.equal(reachedSignal.aborted, true);
});

test("pagination escapes cursors and mutations carry identity without automatic retries", async t => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return new Response(JSON.stringify({ id: "result" }), { status: 200 });
  };
  const signal = new AbortController().signal;
  await discoveryApi.read("run/id", signal, "cursor&limit=50");
  const query = new URL(calls[0].url);
  assert.equal(query.searchParams.get("limit"), "20");
  assert.equal(query.searchParams.get("cursor"), "cursor&limit=50");
  await discoveryApi.create("https://github.com/example/project", "stable-key", signal);
  assert.equal(calls[1].init.headers["Idempotency-Key"], "stable-key");
  await discoveryApi.feedback("edge/id", "confirmed", signal);
  assert.ok(calls[2].url.endsWith("/relationships/edge%2Fid/feedback"));
  assert.deepEqual(JSON.parse(calls[2].init.body), { status: "confirmed" });
  await monitorApi.update("run-id", { enabled: false, interval_seconds: 300, reanalyze_on_change: true }, signal);
  assert.equal(JSON.parse(calls[3].init.body).reanalyze_on_change, true);
  assert.equal(calls.length, 4);
});
