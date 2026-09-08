import assert from "node:assert/strict";
import { test } from "node:test";
import { consumeEvents } from "../static/stream.mjs";

function response(text, chunkSize = 1) {
  const bytes = new TextEncoder().encode(text);
  return new Response(
    new ReadableStream({
      start(controller) {
        for (let offset = 0; offset < bytes.length; offset += chunkSize)
          controller.enqueue(bytes.slice(offset, offset + chunkSize));
        controller.close();
      },
    }),
    { headers: { "Content-Type": "text/event-stream" } },
  );
}

test("UTF-8 characters and CRLF delimiters can split at any byte", async () => {
  const received = [];
  await consumeEvents(
    response(
      ': keep-alive\r\n\r\ndata: {"type":"text_delta","text":"café · ☕"}\r\n\r\ndata: {"type":"done"}\r\n\r\n',
    ),
    (event) => received.push(event),
  );
  assert.equal(received[0].text, "café · ☕");
  assert.equal(received.at(-1).type, "done");
});
test("multiple events per packet are delivered in order", async () => {
  const received = [];
  await consumeEvents(
    response(
      'data: {"type":"session"}\n\ndata: {"type":"text_delta"}\n\ndata: {"type":"done"}\n\n',
      1000,
    ),
    (event) => received.push(event.type),
  );
  assert.deepEqual(received, ["session", "text_delta", "done"]);
});
test("a truncated stream cannot report success", async () => {
  await assert.rejects(
    consumeEvents(
      response('data: {"type":"text_delta","text":"Partial"}\n\n'),
      () => {},
    ),
    /before the reply completed/,
  );
});
test("server errors preserve the useful message", async () => {
  await assert.rejects(
    consumeEvents(
      response('data: {"type":"error","detail":"Model unavailable"}\n\n'),
      () => {},
    ),
    /Model unavailable/,
  );
});
