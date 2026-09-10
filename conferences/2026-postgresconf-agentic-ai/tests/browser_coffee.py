"""Browser integration checks with controlled streams; no model calls or DB writes.

Start the app, then run: python tests/browser_coffee.py [http://127.0.0.1:8018]
"""
import json
import os
from pathlib import Path
import sys
import tempfile
from playwright.sync_api import sync_playwright, expect

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8018'
OUTPUT = Path(os.environ.get('COFFEE_BROWSER_OUTPUT', tempfile.gettempdir())) / 'coffee-integration'
OUTPUT.mkdir(parents=True, exist_ok=True)
SID = '11111111-1111-4111-8111-111111111111'
CUSTOMERS = [
    {'id': 'u_marco', 'name': 'Leo', 'summary': 'Floral pour-over coffee'},
    {'id': 'u_ana', 'name': 'Maya', 'summary': 'Dark espresso'},
    {'id': 'u_yuki', 'name': 'Yuki', 'summary': 'Japanese single origins'},
]
CONFIG = {'default': 'bedrock-openai', 'routes': [
    {'id': 'bedrock-openai', 'label': 'GPT-5.6 Luna + Sol · Bedrock', 'configured': True,
     'intent_model': 'Luna', 'response_model': 'Sol'},
    {'id': 'bedrock-claude', 'label': 'Haiku + Sonnet · Bedrock', 'configured': True,
     'intent_model': 'Haiku', 'response_model': 'Sonnet'},
    {'id': 'openai', 'label': 'OpenAI API', 'configured': False,
     'intent_model': 'Luna', 'response_model': 'Sol'},
]}
PRODUCTS = [
    {'id': 'b_ethiopia_yirg', 'name': 'Ethiopia Yirgacheffe', 'origin': 'Yirgacheffe, Ethiopia',
     'roast_level': 'medium-light', 'flavor_notes': ['jasmine', 'lemon', 'bergamot'],
     'price_cents': 1900, 'in_stock': 42, 'image_url': '/static/products/coffee-light.webp'},
    {'id': 'b_colombia', 'name': 'Colombia Huila', 'origin': 'Huila, Colombia',
     'roast_level': 'medium', 'flavor_notes': ['caramel', 'orange', 'chocolate'],
     'price_cents': 1750, 'in_stock': 28, 'image_url': '/static/products/coffee-medium.webp'},
    {'id': 'b_espresso_blend', 'name': 'House Espresso Blend', 'origin': 'Brazil & Colombia',
     'roast_level': 'dark', 'flavor_notes': ['chocolate', 'hazelnut'],
     'price_cents': 1600, 'in_stock': 240, 'image_url': '/static/products/coffee-dark.webp'},
]
MOCK_FETCH = r"""
const originalFetch = window.fetch.bind(window);
window.requests = [];
window.fetch = async (url, options) => {
  if (url !== '/api/query/stream') return originalFetch(url, options);
  window.requests.push(JSON.parse(options.body));
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({start(controller) {
    window.emit = event => controller.enqueue(encoder.encode('data: ' + JSON.stringify(event) + '\n\n'));
    window.closeStream = () => controller.close();
    window.emit({type:'session', session_id:'11111111-1111-4111-8111-111111111111'});
    window.emit({type:'plan', title:'Read the catalog', steps:['Retrieve beans', 'Verify stock'], duration_ms:2});
    window.emit({type:'step', index:0, state:'done'});
    window.emit({type:'panel', tag:'CATALOG', tag_class:'green" onclick="window.injected=1', title:'Canonical rows',
      columns:['name','price','stock'], rows:[['Ethiopia Yirgacheffe','$19.00','42']],
      sql:"SELECT name, price_cents, in_stock FROM beans WHERE in_stock > 0",
      meta:'Verified <b>catalog</b><img src=x onerror="window.injected=1">'});
    window.emit({type:'text_delta', text:'Try <b>floral coffee</b>.<img src=x onerror="window.injected=1">'});
  }}), {headers:{'Content-Type':'text/event-stream'}});
};
"""


def configure(page, startup_failure=False):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.add_init_script(MOCK_FETCH)
    attempts = [0]
    def customers(route):
        attempts[0] += 1
        route.fulfill(status=503 if startup_failure and attempts[0] == 1 else 200,
                      content_type='application/json', body=json.dumps(CUSTOMERS))
    page.route('**/api/customers', customers)
    page.route('**/api/chat/config', lambda route: route.fulfill(json=CONFIG))
    page.goto(BASE + '/concierge')
    return errors


def finish(page, products=PRODUCTS):
    event = {'type': 'response', 'text': 'Try <cite data-k="beans.b_ethiopia_yirg">Ethiopia Yirgacheffe</cite> for a floral cup.',
             'citations': [{'key': 'beans.b_ethiopia_yirg', 'label': 'Ethiopia Yirgacheffe'}],
             'confidence': 94, 'products': products}
    page.evaluate('(event) => { window.emit(event); window.emit({type:"done"}); window.closeStream(); }', event)
    expect(page.locator('#send')).to_be_enabled()


with sync_playwright() as p:
    browser = p.chromium.launch()
    for width, height in [(1440, 1000), (390, 844), (320, 740)]:
        page = browser.new_page(viewport={'width': width, 'height': height}, reduced_motion='reduce')
        errors = configure(page)
        expect(page.locator('#send')).to_be_enabled()
        expect(page.locator('.regular .name').first).to_have_text('Leo')
        expect(page.locator('#guideView')).to_contain_text('A short demo with Leo')
        expect(page.get_by_role('button', name='Lighter and more floral', exact=True)).to_be_disabled()
        # A profile is a preview: dismissing it preserves the draft and customer.
        page.locator('#q').fill('Keep this draft')
        page.locator('[data-customer="u_yuki"]').click()
        expect(page.get_by_role('dialog')).to_be_visible()
        expect(page.locator('#persona-name')).to_have_text('Yuki')
        expect(page.locator('#persona-personality')).to_contain_text('provenance')
        expect(page.locator('#persona-name')).to_be_focused()
        assert page.locator('#persona-brief').evaluate('(dialog) => dialog.scrollTop') == 0
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(OUTPUT / f'persona-{width}.png'))
        page.keyboard.press('Tab')
        expect(page.get_by_role('button', name='Close', exact=True)).to_be_focused()
        page.keyboard.press('Tab')
        expect(page.get_by_role('button', name='Use this request', exact=True)).to_be_focused()
        page.keyboard.press('Tab')
        expect(page.get_by_role('button', name='Close', exact=True)).to_be_focused()
        page.keyboard.press('1')
        expect(page.locator('#persona-name')).to_have_text('Yuki')
        expect(page.locator('#customer')).to_have_value('u_marco')
        page.keyboard.press('Escape')
        expect(page.get_by_role('dialog')).not_to_be_visible()
        expect(page.locator('[data-customer="u_yuki"]')).to_be_focused()
        expect(page.locator('#q')).to_have_value('Keep this draft')
        # The explicit CTA prepares a request, without calling a model.
        page.locator('[data-customer="u_ana"]').click()
        page.get_by_role('button', name='Use this request', exact=True).click()
        expect(page.locator('#customer')).to_have_value('u_ana')
        expect(page.locator('#q')).to_have_value('Cold brew options')
        expect(page.get_by_role('button', name='Order that', exact=True)).to_be_disabled()
        assert page.evaluate('window.requests.length') == 0
        page.locator('[data-customer="u_marco"]').click()
        page.get_by_role('button', name='Use this request', exact=True).click()
        page.select_option('#modelRoute', 'bedrock-claude')
        page.fill('#q', 'Show me floral coffee')
        page.click('#send')
        expect(page.locator('.msg .body')).to_contain_text('floral coffee')
        expect(page.locator('#send')).to_be_disabled()
        for selector in ['#customer', '#modelRoute', '#reset', '.regular', '.pill']:
            for control in page.locator(selector).all():
                expect(control).to_be_disabled()
        assert page.evaluate('window.requests[0].model_route') == 'bedrock-claude'
        page.locator('.chat-head .lbl').click()
        page.keyboard.press('2')
        assert page.locator('#customer').input_value() == 'u_marco'
        assert page.evaluate('window.injected') is None
        finish(page)
        expect(page.get_by_role('button', name='Lighter and more floral', exact=True)).to_be_enabled()
        expect(page.locator('.product')).to_have_count(3)
        expect(page.locator('.product').first).to_contain_text('$19.00')
        expect(page.locator('.product').first).to_contain_text('42 in stock')
        expect(page.locator('.product').first.locator('img')).to_have_attribute('src', '/static/products/coffee-light.webp')
        for img in page.locator('.product img').all():
            img.scroll_into_view_if_needed()
            expect(img).to_be_visible()
            page.wait_for_function('(img) => img.complete && img.naturalWidth > 0', arg=img.element_handle())
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert page.evaluate('window.injected') is None
        # Reopening the selected person must preserve a completed conversation.
        page.locator('#q').fill('Keep my follow-up')
        page.locator('[data-customer="u_marco"]').click()
        page.get_by_role('button', name='Close', exact=True).click()
        expect(page.locator('.product')).to_have_count(3)
        expect(page.locator('#sid')).to_have_text(SID[:8])
        expect(page.locator('#q')).to_have_value('Keep my follow-up')
        page.locator('#chat').evaluate('(node) => { node.scrollTop = node.querySelector(".msg.agent:last-child").offsetTop - node.offsetTop; }')
        page.mouse.move(0, 0)
        page.evaluate('window.scrollTo(0, 0)')
        page.screenshot(path=str(OUTPUT / f'coffee-{width}.png'), full_page=True)
        # Reuse the server-issued session on a follow-up and keep failures recoverable.
        page.fill('#q', 'Something lighter')
        page.click('#send')
        expect(page.locator('.msg .body').last).to_contain_text('floral coffee')
        assert page.evaluate('window.requests[1].session_id') == SID
        page.evaluate('window.closeStream()')
        expect(page.locator('.msg.incomplete')).to_have_count(1)
        expect(page.locator('#q')).to_have_value('Something lighter')
        expect(page.locator('#send')).to_be_enabled()
        page.click('#reset')
        expect(page.locator('.product')).to_have_count(0)
        expect(page.locator('#sid')).to_have_text('—')
        page.fill('#q', 'Any Japanese coffee?')
        page.click('#send')
        expect(page.locator('.msg .body')).to_contain_text('floral coffee')
        assert page.evaluate('window.requests[2].session_id') is None
        finish(page, products=[])
        expect(page.locator('.product')).to_have_count(0)
        assert not errors, errors
        page.close()
        print(f'{width}px: streaming, customer lock, route, catalog images, XSS, continuity, failure, reset and no-match passed')
    # Only a completed reply with products enables the referential order prompt.
    page = browser.new_page()
    errors = configure(page)
    expect(page.locator('#send')).to_be_enabled()
    page.select_option('#customer', 'u_ana')
    page.get_by_role('button', name='Cold brew options', exact=True).click()
    expect(page.locator('.msg .body')).to_contain_text('floral coffee')
    finish(page, products=[])
    expect(page.get_by_role('button', name='Order that', exact=True)).to_be_disabled()
    page.get_by_role('button', name='Cold brew options', exact=True).click()
    expect(page.locator('.msg .body').last).to_contain_text('floral coffee')
    finish(page)
    expect(page.get_by_role('button', name='Order that', exact=True)).to_be_enabled()
    page.get_by_role('button', name='Order that', exact=True).click()
    expect(page.locator('.msg .body').last).to_contain_text('floral coffee')
    assert page.evaluate('window.requests.at(-1).session_id') == SID
    finish(page, products=[])
    assert not errors, errors
    page.close()
    print('Persona preview, draft/session preservation, explicit request handoff and recommendation-gated order passed')
    page = browser.new_page()
    errors = configure(page, startup_failure=True)
    expect(page.locator('#retry')).to_be_visible()
    expect(page.locator('#send')).to_be_disabled()
    page.click('#retry')
    expect(page.locator('#send')).to_be_enabled()
    assert not errors, errors
    print('Startup failure and retry passed')
    browser.close()
