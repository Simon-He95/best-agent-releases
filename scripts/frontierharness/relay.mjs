import { createServer } from "node:http";
import { request } from "node:https";

const auth = process.env.DEEPSEEK_API_KEY;
const marker = process.env.FH_RELAY_TOKEN;
if (!auth || !marker) throw Error("Missing relay credentials");

const server = createServer(async (incoming, response) => {
  if (incoming.url !== "/v1/chat/completions" || incoming.method !== "POST") {
    response.writeHead(404).end();
    return;
  }
  if (incoming.headers.authorization !== "Bearer " + marker) {
    response.writeHead(403).end();
    return;
  }
  const stop = new AbortController();
  response.on("close", () => stop.abort());
  try {
    const chunks = [];
    let bytes = 0;
    for await (const chunk of incoming) {
      bytes += chunk.length;
      if (bytes > 16 * 1024 * 1024) {
        response.writeHead(413).end();
        return;
      }
      chunks.push(chunk);
    }
    const body = Buffer.concat(chunks);
    if (JSON.parse(body).model !== "deepseek-flash") {
      response.writeHead(400).end();
      return;
    }
    const upstream = request(
      "https://api.deepseek.com/chat/completions",
      {
        method: "POST",
        signal: stop.signal,
        headers: {
          Authorization: "Bearer " + auth,
          "Content-Type": "application/json",
          "Content-Length": body.length,
        },
      },
      (receipt) => {
        console.error(new Date().toISOString(), "upstream", receipt.statusCode);
        response.writeHead(receipt.statusCode, {
          "Content-Type": receipt.headers["content-type"] ?? "application/json",
        });
        receipt.on("error", () => response.destroy());
        receipt.pipe(response);
      },
    );
    upstream.on("error", (error) => {
      console.error(new Date().toISOString(), "relay", error.code ?? error.name);
      if (response.headersSent) response.destroy();
      else response.writeHead(502).end();
    });
    upstream.end(body);
  } catch {
    if (response.headersSent) response.destroy();
    else response.writeHead(400).end();
  }
});
server.listen(0, "0.0.0.0", () => console.log(server.address().port));
