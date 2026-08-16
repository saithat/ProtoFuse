import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("renders the ProtoFuse evaluation readout", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /ProtoFuse \/ Evaluation Readout/i);
  assert.match(html, /Current evidence is narrow/);
  assert.match(html, /Conclusions remain workload-specific/);
  assert.match(html, /CUSTOM adaptive MFE · seeds 200–203/);
  assert.match(html, /9\.72/);
  assert.match(html, /CUSTOM cohort: 4 \/ 4 pairs/);
  assert.match(html, /How ProtoFuse works/);
  assert.match(html, /Match only what is identical/);
  assert.match(html, /Original objectives validate the selected output/);
  assert.match(html, /One seed creates one trajectory/);
  assert.match(html, /Many rows remain one unit/);
  assert.match(html, /CUSTOM frozen audit/);
  assert.match(html, /Ligand joint external audit/);
  assert.match(html, /Evo2 independent audit/);
  assert.match(html, /Paired execution evidence/i);
  assert.match(html, /full-pool · fresh confirmation · CPU/i);
  assert.match(html, /frozen external audit failed/i);
  assert.match(html, /Minimum eval contract/);
  assert.doesNotMatch(html, /Your site is taking shape/);
});
