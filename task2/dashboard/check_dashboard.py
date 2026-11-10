"""Browser regression checks for the offline dashboard (optional Playwright)."""
import argparse
import csv
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
local_tools = ROOT.parents[1] / '.dashboard-preview-tools'
if local_tools.is_dir():
    sys.path.insert(0, str(local_tools))
from playwright.sync_api import sync_playwright


def check(browser_path=None):
    output = ROOT / 'out/dashboard_preview'
    output.mkdir(parents=True, exist_ok=True)
    summary = json.loads((ROOT / 'out/engineering_verified_20261110_final/verification_summary.json').read_text(encoding='utf-8'))
    with (ROOT / 'out/engineering_verified_20261110_final/global_fine.csv').open() as stream:
        grid = list(csv.DictReader(stream))
    results, errors, requests = [], [], []
    with sync_playwright() as p:
        options = dict(headless=True)
        if browser_path:
            options['executable_path'] = str(browser_path)
        browser = p.chromium.launch(**options)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1, accept_downloads=True)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        # Test these handlers without changing the user's system clipboard.
        page.add_init_script("""
        Object.defineProperty(navigator,'clipboard',{configurable:true,value:{
          writeText:async function(text){window.__summaryCopied=text;}
        }});
        document.execCommand=function(command){
          if(command==='copy'){window.__summaryCopied=document.querySelector('textarea').value;return true;}
          return false;
        };
        window.print=function(){window.__printRequested=true;};
        """)
        page.goto((ROOT / 'dashboard/index.html').as_uri())
        page.wait_for_function('!!window.task2Dashboard')
        assert not errors, errors
        assert all(url.startswith('file:') for url in requests), requests
        state = page.evaluate('window.task2Dashboard.getState()')
        assert state['covered'] == 58775 and state['total'] == 59040
        assert page.locator('#remaining-count').inner_text() == '265'
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        results.append('offline_load_and_verified_final_counts')
        page.screenshot(path=str(output / 'desktop_overview.png'))

        for name in ('calculation', 'stk', 'theory'):
            page.locator('[data-task="' + name + '"]').click()
            assert page.locator('[data-task="' + name + '"]').get_attribute('aria-selected') == 'true'
            assert page.locator('#task-panel').inner_text().strip()
        page.locator('#tab-theory').focus()
        page.keyboard.press('ArrowRight')
        assert page.locator('#tab-calculation').get_attribute('aria-selected') == 'true'
        results.append('responsibility_tabs_and_keyboard')

        page.locator('[data-time="86400"]').click()
        expected = sum(bool(r['first_access_s']) and float(r['first_access_s']) <= 86400 for r in grid)
        assert page.evaluate('window.task2Dashboard.getState().covered') == expected
        page.locator('#t90-button').click()
        state = page.evaluate('window.task2Dashboard.getState()')
        assert state['covered'] >= math.ceil(.9 * 59040)
        assert abs(state['time'] - summary['global_coverage']['T90_s']) < 1e-7
        page.locator('[data-time="604800"]').click()
        assert page.evaluate('window.task2Dashboard.getState().covered') == 58775
        results.append('coverage_time_controls_match_source_csv')

        missing = next(r for r in grid if not r['first_access_s'])
        box = page.locator('#coverage-map').bounding_box()
        left = 35 if box['width'] < 430 else 43
        x = box['x'] + left + (float(missing['lon_deg']) + 180) / 360 * (box['width'] - left - 13)
        y = box['y'] + 12 + (90 - float(missing['lat_deg'])) / 180 * (box['height'] - 42)
        page.mouse.move(x, y)
        assert '七天内未覆盖' in page.locator('#map-tooltip').inner_text()
        before = page.locator('#coverage-map').evaluate('(canvas)=>canvas.toDataURL()')
        page.locator('#highlight-missing').uncheck()
        after = page.locator('#coverage-map').evaluate('(canvas)=>canvas.toDataURL()')
        assert before != after
        page.locator('#highlight-missing').check()
        results.append('map_inspection_and_final_missing_highlight')

        total = 0
        for day in range(7):
            page.locator('[data-day="' + str(day) + '"]').click()
            total += page.locator('#region-day-rows tr').count()
            assert page.locator('[data-day="' + str(day) + '"]').get_attribute('aria-pressed') == 'true'
        assert total == 169
        page.locator('[data-day="0"]').click()
        results.append('seven_day_regional_windows_total_169')

        page.locator('#copy-summary').click()
        copied = page.evaluate('window.__summaryCopied')
        assert copied.startswith('目前已完成：') and '265' in copied and '\n\n5、' in copied
        with page.expect_download() as download_info:
            page.locator('#download-summary').click()
        download_info.value.save_as(str(output / 'summary.txt'))
        assert (output / 'summary.txt').read_text(encoding='utf-8-sig') == copied
        page.locator('#print-button').click()
        assert page.evaluate('window.__printRequested')
        results.append('copy_download_and_print_actions')

        page.locator('#toast').evaluate('(node)=>node.hidden=true')
        page.locator('#results').evaluate('(node)=>window.scrollTo(0,window.scrollY+node.getBoundingClientRect().top-25)')
        page.screenshot(path=str(output / 'desktop_results.png'))
        for width in (360, 390, 768):
            page.set_viewport_size({'width': width, 'height': 844})
            page.evaluate('window.scrollTo(0,0)')
            page.wait_for_timeout(180)
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), 'horizontal overflow at ' + str(width)
            assert page.locator('#copy-summary').is_visible()
            page.screenshot(path=str(output / ('mobile_' + str(width) + '.png')))
        page.locator('#results').evaluate('(node)=>window.scrollTo(0,window.scrollY+node.getBoundingClientRect().top-105)')
        page.screenshot(path=str(output / 'mobile_results.png'))
        results.append('responsive_layout_360_390_768')
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.pdf(path=str(output / 'dashboard.pdf'), format='A4', print_background=True)
        assert (output / 'dashboard.pdf').stat().st_size > 5000
        results.append('printable_pdf')
        assert not errors, errors
        local_paths = set()
        for name in ('theory', 'calculation', 'stk'):
            page.locator('[data-task="' + name + '"]').click()
            for href in page.locator('a[href]').evaluate_all('(links)=>links.map(a=>a.getAttribute("href"))'):
                if href.startswith('../'):
                    local_paths.add(href)
        for href in local_paths:
            assert (ROOT / 'dashboard' / href).resolve().is_file(), href
        results.append('all_local_resource_links_exist')
        browser.close()
    report = {'passed': True, 'checks': results, 'page_errors': errors, 'offline_request_count': len(requests)}
    (output / 'browser_checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    edge = Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    parser.add_argument('--browser', type=Path, default=edge if edge.exists() else None)
    check(parser.parse_args().browser)
