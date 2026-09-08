// POST-based SSE, including UTF-8 and event boundaries split across packets.
export async function consumeEvents(response, onEvent) {
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : `Request failed (${response.status}).`,
    );
  }
  if (
    !response.headers.get("content-type")?.includes("text/event-stream") ||
    !response.body
  ) {
    throw new Error("The server did not return a chat stream.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let terminal = false;
  const parse = () => {
    let boundary;
    while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
      const frame = buffer.slice(0, boundary.index);
      buffer = buffer.slice(boundary.index + boundary[0].length);
      const data = frame
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).replace(/^ /, ""))
        .join("\n");
      if (!data) continue;
      const event = JSON.parse(data);
      if (event.type === "error")
        throw new Error(event.detail || "The reply stream failed.");
      onEvent(event);
      if (event.type === "done") {
        terminal = true;
        return;
      }
    }
    if (buffer.length > 1_000_000)
      throw new Error("Chat event exceeded the size limit.");
  };
  try {
    while (!terminal) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      parse();
      if (done) break;
    }
    if (!terminal)
      throw new Error("The connection ended before the reply completed.");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
