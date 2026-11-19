import { appendFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { request as requestHttps } from "node:https";
import { pathToFileURL } from "node:url";

const repo = process.env.FH_REPO;
const model = "deepseek-v4.1-flash";
const marker = process.env.FH_OAUTH_REPRO_PROXY_KEY;
const ledger = process.env.FH_LEDGER;
const log = value => appendFileSync(ledger, JSON.stringify(value)+"\n",{mode:0o600});
let ordinal=0;
const firstTags=new Set();
const digest=x=>createHash("sha256").update(JSON.stringify(x)).digest("hex");
if (!repo || !marker) throw new Error("Set FH_REPO and FH_OAUTH_REPRO_PROXY_KEY.");
const fromRepo = (path) => import(pathToFileURL(repo + "/" + path).href);
const { projectDimOAuthTransportHeaders } = await fromRepo("packages/model-binding-ai-sdk/dist/index.js");
const session = JSON.parse(process.env.FH_DIM_OAUTH_SESSION ?? "{}");
if (!session.access || !session.baseUrl || !(session.expires > Date.now() + 7 * 3600000)) {
  throw new Error("OAuth access session is missing or expires before the CI budget");
}
const target = new URL(session.baseUrl.replace(/\/$/, "") + "/chat/completions");
if (target.protocol !== "https:" || target.hostname === "api.deepseek.com") {
  throw new Error("Expected the HTTPS Dim OAuth endpoint");
}

const server = createServer(async (request, response) => {
  if (request.method === "GET" && request.url === "/ready") {
    response.writeHead(204).end();
    return;
  }
  const route=request.url?.match(/^\/([a-zA-Z0-9_.-]+)\/v1\/chat\/completions$/);
  if (request.method !== "POST" || !route) {
    response.writeHead(404).end();
    return;
  }
  if (request.headers.authorization !== "Bearer " + marker) {
    response.writeHead(403).end();
    return;
  }
  const tag=route[1], id=++ordinal;
  const abort = new AbortController();
  let usage, status, recorded=false;
  const recordEnd = ended => {
    if (recorded) return;
    recorded=true;
    log({tag,id,phase:"finish",status,usage,ended});
  };
  response.on("close", () => {
    abort.abort();
    recordEnd(response.writableFinished);
  });
  try {
    const chunks = [];
    let size = 0;
    for await (const chunk of request) {
      size += chunk.length;
      if (size > 8 * 1024 * 1024) {
        response.writeHead(413).end();
        return;
      }
      chunks.push(chunk);
    }
    const body = Buffer.concat(chunks);
    const payload=JSON.parse(body.toString());
    if (payload.model !== model) {
      response.writeHead(400).end();
      return;
    }
    const first=!firstTags.has(tag);
    if(first) firstTags.add(tag);
    const system=first?(payload.messages??[]).filter(m=>m.role==="system").map(m=>m.content):[];
    const msg=payload.messages??[];
    const diag=new Set();
    for(const m of msg){
      for(const call of m.tool_calls??[]){
        if(/best-agent-evidence\.jsonl|\/logs\/agent/.test(String(call.function?.arguments)))diag.add(call.id);
      }
    }
    const diagReplies=msg.filter(m=>m.role==="tool"&&diag.has(m.tool_call_id));
    log({tag,id,phase:"request",bytes:body.length,model:payload.model,effort:payload.reasoning_effort,
      self_diagnostic_call_ids:[...diag],
      diagnostic_reply_bytes:diagReplies.reduce((sum,m)=>sum+Buffer.byteLength(String(m.content)),0),
      ...(first?{tool_count:payload.tools?.length,tool_digest:digest(payload.tools ?? []),system_count:system.length,
         baseline_first_instruction:digest(system[0] ?? null),deadline:system.some(x=>String(x).includes("Run deadline (UTC)"))}:{})});
    const credential = { access: session.access };
    const upstream = await new Promise((resolve, reject) => {
      const outbound = requestHttps(target, {
        method: "POST",
        headers: Object.fromEntries(projectDimOAuthTransportHeaders({
          "Content-Type": "application/json",
          "Content-Length": String(body.length),
          Authorization: "Bearer " + credential.access,
        })),
        signal: abort.signal,
      }, resolve);
      outbound.on("error", reject);
      outbound.end(body);
    });
    status=upstream.statusCode;
    log({tag,id,phase:"headers",status});
    const sse = String(upstream.headers["content-type"]).includes("text/event-stream");
    let pending="";
    const observe=line=>{
      if(line.startsWith("data: "))line=line.slice(6);
      let decoded;
      try{decoded=JSON.parse(line);}catch{return;}
      if(decoded.usage) usage=decoded.usage;
    };
    upstream.setEncoding("utf8");
    upstream.on("data",chunk=>{
      pending+=chunk;
      if(!sse)return;
      const lines=pending.split("\n");
      pending=lines.pop();
      for(const line of lines)if(line.startsWith("data: "))observe(line);
    });
    upstream.on("end",()=>{
      if(pending)observe(pending);
      recordEnd(true);
    });
    console.error(new Date().toISOString(), "upstream", upstream.statusCode);
    response.writeHead(upstream.statusCode, {
      "Content-Type": upstream.headers["content-type"] ?? "application/json",
    });
    upstream.on("error", () => response.destroy());
    upstream.pipe(response);
  } catch (error) {
    console.error(new Date().toISOString(), "relay-error", error.code ?? error.name);
    if (!response.headersSent) response.writeHead(502).end("Local OAuth relay request failed.");
    else response.destroy();
  }
});
server.listen(0, "0.0.0.0", () => console.log(server.address().port));
