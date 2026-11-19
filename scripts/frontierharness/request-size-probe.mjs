import { writeFileSync } from "node:fs";
import { join } from "node:path";

const root = process.env.FH_ROOT;
const url = "http://127.0.0.1:" + process.env.FH_PORT;
const marker = process.env.FH_OAUTH_REPRO_PROXY_KEY;
const paddedBytes = 4_800_000;
const results = [];

function payload(stdout, filler) {
  const messages = [{ role: "system", content: "Reply with only OK." }];
  for (const content of filler) {
    messages.push({ role: "user", content }, { role: "assistant", content: "OK" });
  }
  messages.push(
    { role: "user", content: "Confirm the result of the diagnostic tool call." },
    { role: "assistant", content: null, tool_calls: [{
      id: "probe_exec", type: "function",
      function: { name: "exec", arguments: '{"argv":["printf","OK"]}' },
    }] },
    { role: "tool", tool_call_id: "probe_exec", content: JSON.stringify({
      kind: "known", status: "succeeded", payload: { exitCode: 0, stdout, stderr: "" },
    }) },
  );
  return {
    model: "deepseek-v4.1-flash", messages, stream: false, max_tokens: 128,
    tools: [{ type: "function", function: {
      name: "exec", description: "Synthetic diagnostic tool.",
      parameters: { type: "object", properties: { argv: { type: "array", items: { type: "string" } } } },
    } }],
  };
}

async function probe(name, stdout, filler = [], pad = 0) {
  const body = JSON.stringify(payload(stdout, filler));
  const missing = pad && pad - Buffer.byteLength(body);
  if (missing < 0) throw new Error("Probe does not fit the fixed request length");
  const wire = body + " ".repeat(missing);
  const started = Date.now();
  const result = {
    name, request_bytes: Buffer.byteLength(wire), tool_stdout_bytes: Buffer.byteLength(stdout),
    filler_bytes: filler.reduce((sum, part) => sum + Buffer.byteLength(part), 0),
  };
  try {
    const response = await fetch(url + "/size-" + name + "/v1/chat/completions", {
      method: "POST", headers: {
        Authorization: "Bearer " + marker, "Content-Type": "application/json",
      },
      body: wire, signal: AbortSignal.timeout(300_000),
    });
    result.status = response.status;
    const raw = await response.text();
    writeFileSync(join(root, "raw/size-" + name + ".json"), raw, { mode: 0o600 });
    let receipt;
    try { receipt = JSON.parse(raw); } catch { receipt = {}; }
    result.prompt_tokens = receipt.usage?.prompt_tokens ?? null;
    result.error = receipt.error?.code ?? null;
  } catch (error) {
    result.client_error = error.name;
  }
  result.seconds = (Date.now() - started) / 1000;
  results.push(result);
  writeFileSync(join(root, "report/request-size-probe.json"), JSON.stringify(results, null, 2));
  console.log(JSON.stringify(result));
  return result;
}

const control = await probe("control", "OK");
if (control.status !== 200 || !control.prompt_tokens) throw new Error("Tool-shaped control did not complete");
if (process.env.FH_EXPERIMENT === "probe") {
  await probe("wire", "OK", [], paddedBytes);
  await probe("tool", (" ".repeat(96) + "\n").repeat(13_000), [], paddedBytes);
}

const calibration = await probe("calibrate", "OK", [" x".repeat(4096)]);
if (!calibration.prompt_tokens || calibration.prompt_tokens <= control.prompt_tokens) {
  throw new Error("Could not calibrate input tokens");
}
const tokensPerRepeat = (calibration.prompt_tokens - control.prompt_tokens) / 4096;
const densityProbe = process.env.FH_EXPERIMENT === "density-probe";
for (const target of densityProbe ? [1_150_000] : [900_000, 1_150_000]) {
  const repeats = Math.floor((target - control.prompt_tokens) / tokensPerRepeat);
  const parts = [];
  for (let offset = 0; offset < repeats; offset += 50_000) {
    parts.push(" x".repeat(Math.min(50_000, repeats - offset)));
  }
  if (densityProbe) {
    await probe("low-density", "OK", parts.map(part => "x".repeat(part.length)), paddedBytes);
  }
  await probe("context-" + target, "OK", parts, paddedBytes);
}
