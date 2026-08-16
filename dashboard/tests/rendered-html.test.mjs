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
  assert.match(html, /We can measure speed/);
  assert.match(html, /Checkpointing is implemented and tested/);
  assert.match(html, /2 saved · 3 resumed · 0 repeated/);
  assert.match(html, /How ProtoFuse works/);
  assert.match(html, /Match only what is identical/);
  assert.match(html, /Original objectives validate the selected output/);
  assert.match(html, /One seed creates one trajectory/);
  assert.match(html, /Many rows remain one unit/);
  assert.match(html, /60 train \+ 20 calibration \+ 20 untouched test trajectories/);
  assert.match(html, /effective independent N/i);
  assert.match(html, /Full vs fused evidence/);
  assert.match(html, /Minimum eval contract/);
  assert.doesNotMatch(html, /Your site is taking shape/);
});
