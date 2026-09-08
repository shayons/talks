"""Streaming contracts: early delivery, isolation, failure and cancellation."""
import asyncio
import json
import os
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app
import agents
import llm


class StreamingAPITests(unittest.TestCase):
    def test_validates_route_and_uuid_before_starting_worker(self):
        with TestClient(app.app) as client, patch.object(app, "run_query") as run:
            for fields in [{"model_route": "invented"}, {"session_id": "bad-uuid"}]:
                response = client.post("/api/query/stream", json={"customer_id": "u_marco", "query": "coffee", **fields})
                self.assertEqual(response.status_code, 422)
            run.assert_not_called()

    def test_openai_without_key_fails_before_session_write(self):
        with patch.dict(os.environ, {}, clear=True), TestClient(app.app) as client, patch.object(app, "run_query") as run:
            response = client.post("/api/query/stream", json={"customer_id": "u_marco", "query": "coffee", "model_route": "openai"})
            self.assertEqual(response.status_code, 422)
            self.assertIn("OPENAI_API_KEY", response.json()["detail"])
            run.assert_not_called()

    def test_provider_error_is_redacted_and_never_done(self):
        with TestClient(app.app) as client, patch.object(app, "run_query", side_effect=RuntimeError("private credential detail")), self.assertLogs("app", level="ERROR"):
            response = client.post("/api/query/stream", json={"customer_id": "u_marco", "query": "coffee"})
            self.assertIn('"type": "error"', response.text)
            self.assertNotIn("private credential detail", response.text)
            self.assertNotIn('"type": "done"', response.text)

    def test_customer_mismatch_does_not_become_a_success(self):
        with TestClient(app.app) as client, patch.object(app, "run_query", side_effect=agents.SessionCustomerMismatchError("session does not belong to customer")):
            response = client.post("/api/query/stream", json={"customer_id": "u_ana", "query": "coffee"})
            self.assertIn("does not belong", response.text)
            self.assertNotIn('"type": "done"', response.text)


class WorkerBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_delta_is_delivered_while_worker_is_still_running(self):
        release = threading.Event()
        completed = threading.Event()

        def run(**kwargs):
            kwargs["on_event"]({"type": "text_delta", "text": "Bergamot"})
            if not release.wait(3):
                raise RuntimeError("test did not release worker")
            completed.set()
            return {"session_id": "test"}

        with patch.object(app, "run_query", run):
            stream = app.query_events(app.QueryIn(customer_id="u_marco", query="coffee"))
            try:
                self.assertEqual(await anext(stream), ": connected\n\n")
                delta = await asyncio.wait_for(anext(stream), 2)
                self.assertIn("Bergamot", delta)
                self.assertFalse(completed.is_set())
                release.set()
                done = await asyncio.wait_for(anext(stream), 2)
                self.assertIn('"type": "done"', done)
            finally:
                release.set()
                await stream.aclose()

    async def test_disconnect_sets_worker_cancellation(self):
        stopped = threading.Event()

        def run(**kwargs):
            kwargs["on_event"]({"type": "status", "text": "Working"})
            if kwargs["cancelled"].wait(3):
                stopped.set()
                raise llm.RunCancelled()
            raise RuntimeError("cancellation not propagated")

        with patch.object(app, "run_query", run):
            stream = app.query_events(app.QueryIn(customer_id="u_marco", query="coffee"))
            await anext(stream)
            await anext(stream)
            await stream.aclose()
            self.assertTrue(await asyncio.to_thread(stopped.wait, 2))


class StrandsContractTests(unittest.IsolatedAsyncioTestCase):
    async def intent(self, payload, stop="tool_use", name="record_intent"):
        class Model:
            async def stream(self, *args, **kwargs):
                yield {"contentBlockStart": {"contentBlockIndex": 0, "start": {"toolUse": {"name": name}}}}
                encoded = json.dumps(payload)
                for text in [encoded[:7], encoded[7:]]:
                    yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": text}}}}
                yield {"messageStop": {"stopReason": stop}}
                yield {"metadata": {"usage": {"inputTokens": 20, "outputTokens": 30}}}

        with patch.object(llm, "make_model", return_value=Model()):
            return await llm._invoke(route=llm.resolve_route("bedrock-openai"), model_id="test",
                system="test", messages=[], tool=agents.INTENT_TOOL_SPEC,
                max_tokens=2048, on_text=None, cancelled=None)

    async def test_validates_fragmented_structured_intent_and_keeps_zero_budget(self):
        payload = {"brew_method": None, "explicit_roasts": [], "origins": [], "budget_cents": 0,
                   "wants_order": False, "order_referent_bean_id": None, "reasoning": "Free coffee"}
        result = await self.intent(payload)
        self.assertEqual(result["tool_input"]["budget_cents"], 0)
        self.assertEqual(result["usage"]["outputTokens"], 30)

    async def test_invalid_intent_cannot_reach_order_logic(self):
        with self.assertRaises(Exception):
            await self.intent({"wants_order": "false"})
        with self.assertRaises(ValueError):
            await self.intent({}, stop="max_tokens")
        with self.assertRaises(ValueError):
            await self.intent({}, name="place_order")

    async def test_provider_enum_spelling_is_normalized_but_unknown_values_fail(self):
        payload = {"brew_method": "pour-over", "explicit_roasts": ["medium_light"],
                   "origins": [], "budget_cents": 2000, "wants_order": False,
                   "order_referent_bean_id": None, "reasoning": "Pour-over coffee"}
        result = await self.intent(payload)
        self.assertEqual(result["tool_input"]["brew_method"], "pour_over")
        self.assertEqual(result["tool_input"]["explicit_roasts"], ["medium-light"])
        from jsonschema import ValidationError
        for bad in [{"brew_method": "invented"}, {"wants_order": "false"},
                    {"budget_cents": "2000"}]:
            with self.assertRaises(ValidationError):
                await self.intent({**payload, **bad})

    async def test_only_complete_response_is_retained_in_context(self):
        received = []
        ctx = agents.AgentContext("sid", "u_marco", "coffee", on_event=received.append)
        ctx.text_delta("<b>Try")
        ctx.text_delta(" coffee</b>")
        ctx.emit_response("<b>Try coffee</b>", [], 30)
        self.assertEqual([e["type"] for e in received], ["text_delta", "text_delta", "response"])
        self.assertEqual([e["type"] for e in ctx.events], ["response"])

    async def test_cancelled_context_rejects_further_events(self):
        cancelled = threading.Event()
        ctx = agents.AgentContext("sid", "u_marco", "coffee", cancelled=cancelled)
        cancelled.set()
        with self.assertRaises(llm.RunCancelled):
            ctx.text_delta("Should not arrive")
        self.assertEqual(ctx.events, [])
