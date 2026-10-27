"""Opt-in real browser regression using only an ephemeral synthetic demo.

Requires Python 3.11+, Playwright, Pillow, Chrome and local Tesseract. Run:
TRADE_ROOM_BROWSER_TESTS=1 python -m unittest discover -s tests -p test_ui_browser.py -v
Set TRADE_ROOM_CHROME for a nonstandard Chrome path. Screenshots and the JSON
report go to a new temporary directory, or TRADE_ROOM_UI_OUTPUT outside the repo.
"""
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit


@unittest.skipUnless(os.getenv('TRADE_ROOM_BROWSER_TESTS') == '1',
                     'Opt-in browser rendering test; see module docstring')
class BrowserUiTests(unittest.TestCase):
    def test_editorial_layout_and_existing_workflows(self):
        from PIL import Image, ImageDraw, ImageFont
        from playwright.sync_api import sync_playwright, expect
        from app import create_server
        from scripts.offline_tests import ROOT

        output = Path(os.getenv('TRADE_ROOM_UI_OUTPUT') or
                      tempfile.mkdtemp(prefix='trade-room-ui-')).resolve()
        self.assertFalse(output.is_relative_to(ROOT.resolve()))
        output.mkdir(parents=True, exist_ok=True)
        chrome = os.getenv('TRADE_ROOM_CHROME') or shutil.which('google-chrome')
        if not chrome and Path('/Applications/Google Chrome.app').exists():
            chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        errors, external, responses, layouts = [], [], [], []

        with patch.dict(os.environ, {'LLM_ENABLED': 'false'}):
            server = create_server(port=0, source='demo', token='', public_origin='')
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=chrome)
                    context = browser.new_context(viewport={'width': 1440, 'height': 1100},
                                                  reduced_motion='reduce')

                    def local_only(route):
                        url = route.request.url
                        if urlsplit(url).hostname == '127.0.0.1':
                            route.continue_()
                        else:
                            external.append(url)
                            route.abort()

                    context.route('**/*', local_only)
                    page = context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('console', lambda message: errors.append(message.text)
                            if message.type == 'error' else None)
                    page.on('response', lambda response: responses.append(response.url)
                            if response.status >= 400 else None)
                    page.goto(f'http://127.0.0.1:{server.server_port}/')
                    expect(page.locator('#app')).to_be_visible()
                    expect(page.locator('#source-badge')).to_have_text('SYNTHETIC DEMO')
                    expect(page.locator('#llm-rank')).to_be_disabled()
                    expect(page.locator('#llm-summary')).to_be_disabled()
                    page.locator('#scan').click()
                    expect(page.locator('#cards > .card')).to_have_count(12, timeout=20000)

                    def screenshot(name, selector=None):
                        if selector:
                            page.locator(selector).first.evaluate(
                                "e => e.scrollIntoView({block:'start',behavior:'instant'})")
                        else:
                            page.evaluate("scrollTo({top:0,behavior:'instant'})")
                        # Viewport captures avoid Chromium's tall-page tiling artifacts.
                        page.screenshot(path=str(output / f'{name}.png'))

                    def layout(width, height):
                        page.set_viewport_size({'width': width, 'height': height})
                        result = page.evaluate('''() => ({
                            width: innerWidth, height: innerHeight,
                            documentWidth: document.documentElement.scrollWidth,
                            mainWidth: document.querySelector('main').getBoundingClientRect().width,
                            cards: getComputedStyle(document.querySelector('#cards')).gridTemplateColumns.split(' ').length,
                            stats: getComputedStyle(document.querySelector('.stats-strip')).gridTemplateColumns.split(' ').length,
                            overflow: [...document.querySelectorAll('#app *')].filter(e => {
                                const r = e.getBoundingClientRect();
                                return r.width && (r.left < -1 || r.right > innerWidth + 1);
                            }).map(e => e.id || e.className)
                        })''')
                        self.assertEqual(result['documentWidth'], width, result)
                        self.assertEqual(result['overflow'], [], result)
                        self.assertEqual(result['cards'], 1 if width <= 680 else 2)
                        self.assertEqual(result['stats'], 2 if width <= 680 else 4)
                        if width == 1440:
                            self.assertEqual(result['mainWidth'], 1240)
                        layouts.append(result)

                    layout(1440, 1100)
                    screenshot('desktop')
                    screenshot('desktop-shortlist', '.recommendations .section-heading')
                    page.locator('#cards > .card > summary').first.focus()
                    page.keyboard.press('Enter')
                    expect(page.locator('#cards > .card').first).to_have_attribute('open', '')
                    page.locator('#cards .lineup-block > summary').first.click()
                    screenshot('desktop-breakdown', '#cards > .card')
                    page.locator('#cards > .card > summary').first.click()
                    for width, height in [(1024, 900), (768, 1024), (390, 844), (320, 740)]:
                        layout(width, height)
                    page.set_viewport_size({'width': 390, 'height': 844})
                    screenshot('mobile')
                    screenshot('mobile-shortlist', '.recommendations .section-heading')
                    page.locator('[data-filter=one]').click()
                    expect(page.locator('#cards .empty')).to_contain_text('No matching mutual-upside trades.')
                    self.assertTrue(all('1-for-1' in text for text in
                                        page.locator('#cards h3').all_text_contents()))
                    page.locator('[data-filter=package]').click()
                    expect(page.locator('#cards > .card')).to_have_count(12)
                    page.locator('[data-filter=all]').click()
                    page.locator('#cards > .card > summary').first.click()
                    layout(320, 740)
                    screenshot('mobile-breakdown', '#cards > .card .details-content')
                    page.locator('input[name=give]').nth(1).check()
                    page.locator('input[name=receive]').nth(4).check()
                    screenshot('mobile-workbench', '#workbench')
                    page.locator('#evaluate').click()
                    expect(page.locator('#manual-result > .card')).to_be_visible()
                    screenshot('mobile-manual', '#manual-result')
                    page.locator('input[name=give]').nth(1).uncheck()
                    expect(page.locator('#manual-result')).to_be_empty()
                    page.locator('#method-open').click()
                    expect(page.locator('#method-dialog')).to_be_visible()
                    page.keyboard.press('Escape')
                    expect(page.locator('#method-open')).to_be_focused()

                    # Upload real synthetic pixels through the actual local OCR endpoint.
                    image = Image.new('RGB', (900, 300), 'white')
                    draw = ImageDraw.Draw(image)
                    try:
                        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 32)
                    except OSError:
                        font = ImageFont.load_default(size=32)
                    draw.multiline_text((30, 25), 'Avery Vale\nBennett Vale\nCameron Vale',
                                        fill='black', font=font, spacing=20)
                    buffer = BytesIO()
                    image.save(buffer, format='PNG')
                    expect(page.locator('#upload-button')).to_be_enabled()
                    page.locator('#upload').set_input_files({'name': 'synthetic-lineup.png',
                        'mimeType': 'image/png', 'buffer': buffer.getvalue()})
                    expect(page.locator('#ocr-dialog')).to_be_visible(timeout=20000)
                    page.locator('#ocr-team').select_option('harbor')
                    expect(page.locator('#ocr-matches > .player-option')).to_have_count(12)
                    for width, height in [(1440, 1100), (390, 844), (320, 740), (844, 390)]:
                        page.set_viewport_size({'width': width, 'height': height})
                        page.locator('#ocr-confirm').scroll_into_view_if_needed()
                        geometry = page.locator('#ocr-confirm').bounding_box()
                        self.assertGreaterEqual(geometry['y'], 0)
                        self.assertLessEqual(geometry['y'] + geometry['height'], height)
                        self.assertEqual(page.locator('#ocr-dialog').evaluate(
                            '(e) => e.scrollWidth <= e.clientWidth'), True)
                        screenshot(f'ocr-{width}', '#ocr-confirm')
                    page.set_viewport_size({'width': 390, 'height': 844})
                    page.locator('#ocr-ack').check()
                    page.locator('#ocr-confirm').click()
                    expect(page.locator('#ocr-dialog')).not_to_be_visible(timeout=20000)
                    expect(page.locator('#cards > .card')).to_have_count(12)
                    expect(page.locator('#ocr-text')).to_have_value('')
                    report = {'layouts': layouts, 'consoleErrors': errors,
                              'httpErrors': responses, 'externalRequests': external}
                    (output / 'report.json').write_text(json.dumps(report, indent=2))
                    self.assertEqual(errors, [])
                    self.assertEqual(responses, [])
                    self.assertEqual(external, [])
                    print(f'Browser screenshots and report: {output}')
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
