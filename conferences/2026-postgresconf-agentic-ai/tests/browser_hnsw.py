"""Real, read-only embedding walkthrough checks; no chat models or catalog writes."""
import math
import os
from pathlib import Path
import sys
import tempfile

from playwright.sync_api import sync_playwright, expect

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8017'
OUTPUT = Path(os.environ.get('COFFEE_BROWSER_OUTPUT', tempfile.gettempdir())) / 'coffee-hnsw'
OUTPUT.mkdir(parents=True, exist_ok=True)
expect.set_options(timeout=90000)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    for width, height in [(1728, 940), (1024, 900), (390, 844), (320, 740)]:
        page = browser.new_page(viewport={'width': width, 'height': height}, reduced_motion='reduce')
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        with page.expect_response(lambda response: response.url.endswith('/api/search/walkthrough')) as response:
            page.goto(BASE + '/catalog')
        data = response.value.json()
        expect(page.locator('#hnsw-status')).to_contain_text('384 dimensions')
        expect(page.locator('.hnsw-layer')).to_have_count(3)
        expect(page.locator('.hnsw-story h3')).to_have_text('Start with a sparse layer')
        expect(page.locator('#hnsw-previous')).to_be_disabled()
        page.locator('#hnsw-next').click()
        expect(page.locator('.hnsw-story .hnsw-eyebrow')).to_contain_text('Step 2 /')
        page.locator('#hnsw-previous').click()
        expect(page.locator('.hnsw-story .hnsw-eyebrow')).to_contain_text('Step 1 /')
        # Camera controls change the projection, not the search state.
        before = page.locator('.hnsw-plane').first.get_attribute('points')
        page.get_by_role('button', name='Rotate graph right', exact=True).click()
        assert page.locator('.hnsw-plane').first.get_attribute('points') != before
        expect(page.locator('.hnsw-story .hnsw-eyebrow')).to_contain_text('Step 1 /')
        page.get_by_role('button', name='Reset view', exact=True).click()
        # Exact full-vector distance is available through an accessible selector.
        page.locator('#hnsw-coffee').select_option('4')
        query, vector = data['query_embedding'], data['products'][4]['embedding']
        distance = 1 - sum(a*b for a, b in zip(query, vector)) / math.sqrt(sum(a*a for a in query) * sum(b*b for b in vector))
        expect(page.locator('#hnsw-distance')).to_contain_text(f'{distance:.4f}')
        page.locator('.hnsw-node[data-node="0"] .hnsw-node-target').first.click()
        expect(page.locator('#hnsw-coffee')).to_have_value('0')
        page.locator('#hnsw-progress').press('End')
        expect(page.locator('.hnsw-story h3')).to_have_text('Return the nearest candidates found')
        expect(page.locator('.hnsw-candidates li.returned')).to_have_count(3)
        expect(page.locator('#hnsw-next')).to_be_disabled()
        page.locator('#hnsw-ef').select_option('16')
        expect(page.locator('.hnsw-story .hnsw-eyebrow')).to_contain_text('Step 1 /')
        page.locator('#hnsw-progress').press('End')
        expect(page.locator('.hnsw-outcome')).to_contain_text('3 / 3')
        page.locator('#catalog-hnsw').screenshot(path=str(OUTPUT / f'walkthrough-{width}.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'page overflow'
        # New queries replace the prior graph and result, including error recovery.
        page.get_by_role('button', name='chocolate espresso', exact=True).click()
        expect(page.locator('#hnsw-status')).to_contain_text('“chocolate espresso”')
        expect(page.locator('.hnsw-story .hnsw-eyebrow')).to_contain_text('Step 1 /')
        page.route('**/api/search/walkthrough', lambda route: route.fulfill(status=503, json={'detail': 'Controlled walkthrough failure.'}))
        page.locator('#hnsw-query').fill('floral and fruity')
        page.get_by_role('button', name='Trace query', exact=True).click()
        expect(page.locator('#hnsw-status')).to_contain_text('Controlled walkthrough failure')
        expect(page.locator('.hnsw-content')).not_to_be_visible()
        expect(page.get_by_role('button', name='Trace query', exact=True)).to_be_enabled()
        page.unroute('**/api/search/walkthrough')
        page.get_by_role('button', name='Trace query', exact=True).click()
        expect(page.locator('#hnsw-status')).to_contain_text('“floral and fruity”')
        expect(page.locator('.hnsw-content')).to_be_visible()
        assert not errors, errors
        page.close()
        print(f'{width}px: real embeddings, 3D camera, stepping, full-vector distances, candidate limit, results, query changes and failure recovery passed')
    browser.close()
