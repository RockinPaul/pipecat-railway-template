import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../client.js", import.meta.url), "utf8")
  .replace(/^import Daily from "@daily-co\/daily-js";\s*/u, "");

function clientWithMicrophoneFailure(failure) {
  const elements = new Map();
  const requests = [];
  let dailyOptions;
  let destroyed = false;
  function element(selector) {
    if (!elements.has(selector)) {
      elements.set(selector, {
        value: "test-password",
        hidden: false,
        disabled: false,
        textContent: "",
        dataset: {},
        classList: { toggle() {} },
        listeners: {},
        addEventListener(name, handler) { this.listeners[name] = handler; },
        setAttribute() {},
      });
    }
    return elements.get(selector);
  }
  runInNewContext(source, {
    document: { querySelector: element },
    window: { addEventListener() {} },
    AbortSignal,
    clearInterval,
    fetch: async (path) => {
      requests.push(path);
      assert.equal(path, "/api/auth", "Microphone failure must not create a paid session");
      return { ok: true, status: 204 };
    },
    Daily: {
      createCallObject(options) {
        dailyOptions = options;
        return {
          on() {},
          async startCamera() { throw failure; },
          async destroy() { destroyed = true; },
        };
      },
    },
  }, { filename: "client.js" });
  return {
    element,
    requests,
    get dailyOptions() { return dailyOptions; },
    get destroyed() { return destroyed; },
    submit: () => element("#connect-form").listeners.submit({ preventDefault() {} }),
  };
}

test("Daily loads without eval under the server content security policy", async () => {
  const client = clientWithMicrophoneFailure(new Error("No microphone"));
  await client.submit();
  assert.equal(client.dailyOptions.dailyConfig?.avoidEval, true);
});

test("a string SDK rejection displays its message and permits retry", async () => {
  const client = clientWithMicrophoneFailure("Daily call machine could not load");
  await client.submit();
  assert.equal(client.element("#error").hidden, false);
  assert.equal(client.element("#error").textContent, "Daily call machine could not load");
  assert.equal(client.element("#status").textContent, "Not connected");
  assert.equal(client.element("#connect").disabled, false);
  assert.equal(client.element("#password").disabled, false);
  assert.equal(client.destroyed, true);
  assert.deepEqual(client.requests, ["/api/auth"]);
  await client.submit();
  assert.deepEqual(client.requests, ["/api/auth", "/api/auth"]);
});

test("an SDK rejection without a message displays a useful fallback", async () => {
  const client = clientWithMicrophoneFailure(null);
  await client.submit();
  assert.equal(client.element("#error").hidden, false);
  assert.match(client.element("#error").textContent, /audio connection could not start/i);
  assert.equal(client.destroyed, true);
});
