import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { once } from "node:events";
import test from "node:test";

const require = createRequire(import.meta.url);
const fromNodeGyp = createRequire(require.resolve("node-gyp/package.json"));

test("node-gyp uses patched Undici 8 and can fetch build inputs", async () => {
  const { version } = fromNodeGyp("undici/package.json");
  const [major, minor, patch] = version.split(".").map(Number);
  assert.equal(major, 8, "do not cross an Undici API major");
  assert.ok(minor > 12 || (minor === 12 && patch >= 2), version);

  const server = createServer((request, response) => response.end("build input"));
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  try {
    const { fetch } = fromNodeGyp("undici");
    const response = await fetch(`http://127.0.0.1:${server.address().port}/`);
    assert.equal(response.status, 200);
    assert.equal(await response.text(), "build input");
  } finally {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
});
