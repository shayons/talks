"""One end-to-end browser check: pick a question, see graded columns, open the SQL."""

from __future__ import annotations

import os
import socket
import threading
import time

import pytest
import uvicorn
from playwright.sync_api import sync_playwright

from hybrid_lab import bedrock

SCREENSHOT_DIR = os.getenv("LAB_SCREENSHOT_DIR")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def live_server(test_dsn, monkeypatch):
    monkeypatch.setattr(
        bedrock, "rerank",
        lambda query, docs, top_n=None: [(i, 1 / (i + 1)) for i in reversed(range(len(docs)))],
    )
    from hybrid_lab.server import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def test_question_renders_graded_columns_and_sql(live_server):
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 950})
        page.on("console", lambda message: message.type == "error" and errors.append(message.text))
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{live_server}/#q=101")
        page.wait_for_selector(".column")
        assert page.locator(".column").count() == 4
        assert page.locator(".answers .tag").count() == 3
        assert page.locator(".row.is-answer").count() >= 3
        assert "3 of 3 answers" in page.locator(".column").nth(1).inner_text()
        if SCREENSHOT_DIR:
            page.screenshot(path=f"{SCREENSHOT_DIR}/search.png", full_page=True)
        page.locator(".column").nth(2).get_by_role("button", name="SQL").click()
        page.wait_for_selector("#drawer:not([hidden]) .sql")
        assert "ARM QUERY" in page.locator(".sql").inner_text()
        if SCREENSHOT_DIR:
            page.screenshot(path=f"{SCREENSHOT_DIR}/sql.png")
        page.keyboard.press("Escape")
        assert page.locator("#drawer").is_hidden()
        browser.close()
    assert errors == []
