"""Exercise the real search/catalog UI; stage mutations are intercepted, never executed.

Start the app, then: .venv/bin/python tests/browser_lab.py http://127.0.0.1:8017
"""
import json
import os
from pathlib import Path
import sys
import tempfile

from playwright.sync_api import sync_playwright, expect

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8017'
OUTPUT = Path(os.environ.get('COFFEE_BROWSER_OUTPUT', tempfile.gettempdir())) / 'search-surfaces'
OUTPUT.mkdir(parents=True, exist_ok=True)
expect.set_options(timeout=90000)


def fit(page):
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'horizontal page overflow'
    assert all(image.evaluate('(img) => img.complete && img.naturalWidth > 0') for image in page.locator('img:visible').all()), 'missing image'


def capture(page, name, width):
    page.evaluate('window.scrollTo(0, 0)')
    page.screenshot(path=str(OUTPUT / f'{name}-{width}.png'), full_page=True)
    page.screenshot(path=str(OUTPUT / f'{name}-{width}-viewport.png'))
    fit(page)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    for width, height in [(1280, 800), (1024, 900), (390, 844), (320, 740)]:
        page = browser.new_page(viewport={'width': width, 'height': height}, reduced_motion='reduce')
        errors = []
        page.on('pageerror', lambda problem: errors.append(str(problem)))
        page.goto(BASE)
        expect(page.locator('#search-status')).to_contain_text('Eligible')
        expect(page.locator('.ranking-column')).to_have_count(3)
        if width <= 640:
            page.locator('[data-method="keyword"]').click()
        expect(page.locator('.keyword .coffee-hit').first).to_contain_text('Ethiopia Yirgacheffe')
        page.locator('.keyword .coffee-hit').first.click()
        expect(page.locator('#inspector-content')).to_contain_text('Reciprocal Rank Fusion')
        if width == 1280:
            page.locator('[data-inspector="sql"]').click()
            expect(page.locator('#inspector-content')).to_contain_text('semantic_candidates AS MATERIALIZED')
            page.locator('[data-inspector="plan"]').click()
            page.get_by_role('button', name='Run EXPLAIN ANALYZE', exact=True).click()
            expect(page.locator('#inspector-content pre')).to_contain_text('Execution Time')
            page.locator('[data-inspector="export"]').click()
            with page.expect_download() as download:
                page.get_by_role('button', name='Download comparison JSON').click()
            evidence = json.loads(Path(download.value.path()).read_text())
            assert evidence['query'] == 'bergamot' and evidence['plan']['Plan']
            assert evidence['results'][0]['id'] == 'b_ethiopia_yirg'
        page.locator('[data-inspector="explain"]').click()
        capture(page, 'lab', width)
        page.locator('[data-regular="yuki"]').click()
        expect(page.get_by_role('dialog')).to_contain_text('a similar-tasting coffee')
        expect(page.locator('#lab-query')).to_have_value('bergamot')
        page.get_by_role('button', name='Compare this request', exact=True).click()
        expect(page.locator('#search-status')).to_contain_text('Eligible 0')
        assert page.locator('.coffee-hit').count() == 0
        page.locator('[data-regular="maya"]').click()
        page.get_by_role('button', name='Compare this request', exact=True).click()
        expect(page.locator('#search-status')).to_contain_text("'dessert'")
        page.locator('#write-own').click()
        expect(page.locator('#search-status')).to_contain_text('Write a request')
        page.locator('#lab-query').fill('chocolate')
        expect(page.locator('#search-status')).to_contain_text("'chocol'")
        page.locator('[data-regular="leo"]').click()
        page.get_by_role('button', name='Compare this request', exact=True).click()
        expect(page.locator('#search-status')).to_contain_text("'bergamot'")
        page.locator('.main-nav a[href="/catalog"]').click()
        expect(page.locator('#catalog-list .coffee-hit')).to_have_count(16)
        expect(page.locator('.vector-cell')).to_have_count(384)
        page.locator('[data-coffee="b_ethiopia_yirg"]').click()
        expect(page.locator('#catalog-detail h2')).to_have_text('Ethiopia Yirgacheffe')
        expect(page.locator('#catalog-detail')).to_contain_text('$19.00')
        capture(page, 'catalog', width)
        page.locator('.main-nav a[href="/experiments"]').click()
        expect(page.locator('.blind-choice')).to_have_count(9)
        expect(page.locator('#blind-reveal')).to_be_disabled()
        for round in page.locator('.blind-round').all():
            round.locator('button').first.click()
        page.locator('#blind-reveal').click()
        expect(page.locator('#blind-summary')).to_contain_text('Leo:')
        assert any(label in page.locator('.blind-label').first.inner_text() for label in ['Keyword', 'Vector', 'Hybrid'])
        # Comparison is read-only. Preparation and price writes stay intercepted below.
        if page.locator('#index-compare').is_enabled():
            page.locator('#index-iterative').check()
            page.locator('#index-compare').click()
            expect(page.locator('#index-status')).to_contain_text('Verified:')
            expect(page.locator('.neighbor-table tbody tr')).to_have_count(20)
            expect(page.locator('#index-results')).to_contain_text('Recall @20')
        capture(page, 'experiments', width)
        page.locator('.main-nav a[href="/concierge"]').click()
        expect(page.locator('#send')).to_be_enabled()
        page.locator('#q').fill('A draft that should survive navigation')
        capture(page, 'concierge', width)
        assert page.evaluate('document.querySelector("footer.footer").getBoundingClientRect().top >= document.querySelector(".side").getBoundingClientRect().bottom'), 'trace overlaps the footer'
        page.locator('.main-nav a[href="/"]').click()
        expect(page.locator('#lab-query')).to_have_value('bergamot')
        page.go_back()
        expect(page.locator('#q')).to_have_value('A draft that should survive navigation')
        assert not errors, errors
        print(f'{width}px: search, ranks, inspector, empty state, catalog, judging, navigation, draft preservation, images and overflow passed')
        page.close()

    # Validate stage controls and recovery without mutating the rehearsal database.
    page = browser.new_page()
    live_status = page.request.get(BASE + '/api/experiments/status').json()
    status = {**live_status, 'enabled': True,
              'price': {'active': False, 'current_cents': 1900, 'original_cents': None},
              'fixture': {**live_status['fixture'], 'ready': False}}
    calls = []
    page.route('**/api/experiments/status', lambda route: route.fulfill(json=status))

    def mutation(route):
        body = route.request.post_data_json
        calls.append((route.request.url, body))
        if route.request.url.endswith('/price'):
            active = body['action'] == 'raise'
            status['price'] = {'active': active, 'current_cents': 2400 if active else 1900, 'original_cents': 1900 if active else None}
            route.fulfill(json=status['price'])
        elif route.request.url.endswith('/prepare'):
            status['fixture'].update(ready=True, rows=12000, prepare_ms=100)
            route.fulfill(json=status['fixture'])
        else:
            route.fulfill(status=503, json={'detail': 'Controlled index failure. Please retry.'})

    page.route('**/api/experiments/price', mutation)
    page.route('**/api/experiments/index/*', mutation)
    page.goto(BASE + '/experiments')
    expect(page.locator('#price-raise')).to_be_enabled()
    page.locator('#price-raise').click()
    expect(page.locator('#price-restore')).to_be_enabled()
    expect(page.locator('#price-current')).to_contain_text('$24.00')
    page.locator('#price-restore').click()
    expect(page.locator('#price-raise')).to_be_enabled()
    expect(page.locator('#price-current')).to_contain_text('$19.00')
    page.locator('#index-prepare').click()
    expect(page.locator('#index-compare')).to_be_enabled()
    page.locator('#index-ef').fill('120')
    page.locator('#index-iterative').check()
    page.locator('#index-compare').click()
    expect(page.locator('#index-status')).to_contain_text('Controlled index failure')
    expect(page.locator('#index-compare')).to_be_enabled()
    assert calls[-1][1] == {'ef_search': 120, 'filtered': True, 'iterative': True}
    assert len(calls) == 4
    status['enabled'] = False
    page.reload()
    expect(page.locator('#stage-status')).to_contain_text('controls are off')
    expect(page.locator('#price-raise')).to_be_disabled()
    expect(page.locator('#index-prepare')).to_be_disabled()
    assert len(calls) == 4
    print('Intercepted stage actions: price raise/restore, fixture preparation, settings, failure recovery and disabled-server gate passed; no database mutations')
    browser.close()
