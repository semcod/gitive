"""Explicit browser acceptance check against the three managed demo projects.

Run manually: python -m gitive.check_web --output /private/report-directory
Requires Playwright and installed Chrome. Creates one local acceptance ticket per
project, queues real tests, and opens one project terminal; no GitHub publication.
"""
import argparse
import json
from pathlib import Path
import time
import urllib.request
from datetime import datetime,timezone
from playwright.sync_api import sync_playwright,expect


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://127.0.0.1:8793');ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    result={'created':datetime.now(timezone.utc).isoformat(),'checks':[],'projects':{}};errors=[]
    initial=json.load(urllib.request.urlopen(a.url+'/api/control'))
    for name in ('atlas-api','orbit-web','relay-jobs'):
        p=next(p for p in initial['projects'] if p['name']==name)
        assert p['demo'] and p['workspace']['status']=='running',name+' must be a managed, running demo'
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True,executable_path='/usr/bin/google-chrome')
        context=browser.new_context(viewport={'width':1440,'height':1100});page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(a.url);expect(page.locator('.project-card')).to_have_count(len(initial['projects']))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        result['checks'].append('desktop layout, no horizontal overflow')
        for name in ('atlas-api','orbit-web','relay-jobs'):
            page.locator('#projectFilter').select_option(name)
            page.locator('#navigation [data-view=tickets]').click()
            expect(page.locator('.ticket-card').first).to_be_visible()
            assert all(p==name for p in page.locator('.ticket-card').evaluate_all('(items)=>items.map(x=>x.dataset.project)'))
            prior=next((t for t in initial['tickets'] if t['project']==name and t['title'].startswith('Odbiór panelu WWW ·')),None)
            if prior:title=prior['title']
            else:
                page.locator('#newTicket').click();expect(page.locator('#ticketForm [name=project]')).to_have_value(name)
                title='Odbiór panelu WWW · '+time.strftime('%H:%M:%S')
                page.locator('#ticketForm [name=title]').fill(title)
                page.locator('#ticketForm [name=description]').fill('Sprawdź wybór projektu, ticket nadrzędny, zapis statusu oraz testy w prywatnym kontenerze. Ticket utworzony przez rzeczywisty test przeglądarkowy.')
                page.locator('#ticketForm [name=engine]').select_option('gpt6')
                page.locator('#ticketForm [name=parent]').select_option('PLF-001')
                page.locator('#ticketForm [type=submit]').click();expect(page.locator('#create')).not_to_be_visible()
            page.get_by_role('button',name=title,exact=False).click()
            expect(page.locator('#runSelected')).to_be_disabled()
            page.locator('#manualStatus').select_option('review');page.locator('#saveStatus').click()
            expect(page.locator('#detail .detail-meta')).to_contain_text('Do przeglądu')
            page.locator('#detail [data-close]').click()
            page.locator('#navigation [data-view=workspaces]').click()
            page.locator('#content [data-action=runtime-test]').click()
            # Wait for actual docker exec result, not just HTTP enqueue acknowledgment.
            deadline=time.monotonic()+180;job=None
            while time.monotonic()<deadline:
                state=json.load(urllib.request.urlopen(a.url+'/api/control'))
                matching=[j for j in state['jobs'] if j['project']==name and j['action']=='runtime-test']
                if matching and matching[0]['status'] in ('complete','failed'):job=matching[0];break
                page.wait_for_timeout(1000)
            assert job,name+' missing test result'
            expected='failed' if name=='relay-jobs' else 'complete'
            assert job['status']==expected,job
            result['projects'][name]={'job':job['id'],'status':job['status'],'exit_code':job['result']['exit_code'],'ticket':title}
            page.locator('#refresh').click()
        result['checks']+=['project and ticket scoping across identical Planfile IDs','create ticket with project-scoped parent','manual status round-trip','runtime repair block visible before action','real container tests: two green, one controlled failure']
        page.locator('#projectFilter').select_option('');page.locator('#navigation [data-view=tickets]').click()
        page.locator('#search').fill('no-such-ticket-unique');expect(page.locator('.ticket-card')).to_have_count(0);page.locator('#search').fill('')
        page.keyboard.press('Control+k');page.locator('#paletteSearch').fill('orbit-web');page.locator('#paletteResults [data-project-open=orbit-web]').click();expect(page.locator('#projectFilter')).to_have_value('orbit-web')
        page.reload();expect(page.locator('#projectFilter')).to_have_value('orbit-web')
        result['checks']+=['empty search','Ctrl+K navigation','selection survives page reload']
        page.locator('#projectFilter').select_option('doctor-agent');page.locator('#navigation [data-view=tickets]').click();page.locator('.ticket-card').first.click();expect(page.locator('#runSelected')).to_be_disabled();expect(page.locator('#detail')).to_contain_text('Ticket zakończony');page.locator('#detail [data-close]').click()
        result['checks'].append('closed ticket cannot run')
        page.locator('#projectFilter').select_option('atlas-api');page.locator('#navigation [data-view=workspaces]').click();page.locator('#content [data-action=runtime-terminal]').click()
        deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            state=json.load(urllib.request.urlopen(a.url+'/api/control'));jobs=[j for j in state['jobs'] if j['project']=='atlas-api' and j['action']=='runtime-terminal']
            if jobs and jobs[0]['status'] in ('complete','failed'):
                assert jobs[0]['status']=='complete',jobs[0];result['terminal']=jobs[0];break
            page.wait_for_timeout(1000)
        else:raise AssertionError('Terminal did not open')
        result['checks'].append('web opens actual project SSH terminal in noVNC')
        page.locator('#projectFilter').select_option('');page.locator('#navigation [data-view=overview]').click();page.locator('#refresh').click();page.wait_for_timeout(1000);page.screenshot(path=str(a.output/'overview.png'),full_page=True)
        page.locator('#navigation [data-view=tickets]').click();page.screenshot(path=str(a.output/'tickets.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth');page.screenshot(path=str(a.output/'mobile.png'),full_page=True)
        result['checks'].append('mobile 390px, no horizontal overflow');result['javascript_errors']=errors;assert not errors,errors
        context.close();browser.close()
    (a.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
