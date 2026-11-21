async function openEvidenceEgress() {
  const providerPath = process.env.BEST_AGENT_PROVIDER_CONFIG;
  const port = process.env.FH_EVIDENCE_PORT;
  if (!providerPath || !port) throw new Error("Missing CI evidence transport configuration");
  const provider = JSON.parse(await readFile(providerPath, "utf8")) as {
    baseURL: string;
    apiKey: string;
  };
  const destination = new URL("attempt-evidence", provider.baseURL);
  destination.port = port;
  const upload = requestEvidence(destination, {
    method: "POST",
    headers: { Authorization: "Bearer " + provider.apiKey },
  });
  const finished = new Promise<void>((resolve, reject) => {
    upload.once("error", reject);
    upload.once("response", (response) => {
      response.once("error", reject);
      response.once("end", () => {
        if (response.statusCode === 204) resolve();
        else reject(new Error("CI runner did not preserve the evidence stream"));
      });
      response.resume();
    });
  });
  void finished.catch(() => undefined);
  return {
    write: (bytes: Buffer) => new Promise<void>((resolve, reject) => {
      upload.write(bytes, (error) => error ? reject(error) : resolve());
    }),
    // The runner syncs the file before acknowledging the completed stream.
    sync: async () => {},
    close: async () => {
      upload.end();
      await finished;
    },
  };
}
