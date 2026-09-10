"""Regenerate Markdown, CSV and JSON summaries from timestamped immutable iteration files."""
from __future__ import annotations
import csv
import json
from pathlib import Path
from .common import dump,utc


def summarize(run_dir):
    run_dir=Path(run_dir); manifest=json.loads((run_dir/'manifest.json').read_text())
    rows=[json.loads(p.read_text()) for p in sorted((run_dir/'iterations').glob('*.json'))]
    summary={'run_id':manifest['run_id'],'mode':manifest['mode'],'generated':utc(),'completed_iterations':len(rows),
             'expected_iterations':len(manifest['solutions'])*len(manifest['projects'])*manifest['iterations'],'solutions':{}}
    for solution in manifest['solutions']:
        own=[r for r in rows if r['solution']==solution]; calls=[c for r in own for c in r.get('llm_calls',[])]
        finals=[json.loads(p.read_text()) for p in (run_dir/'final').glob(f'{solution}--*.json')]
        costs=[c.get('cost_usd') for c in calls]
        summary['solutions'][solution]=dict(iterations=len(own),repairs_attempted=sum(r['status'] not in ('already_green','mock_no_repair','worker_failed') for r in own),
            accepted=sum(bool(r.get('accepted')) for r in own),green_stages=sum(r.get('after',{}).get('green',False) for r in own),
            noops=sum(r['status']=='already_green' for r in own),errors=sum(r['status'] in ('error','worker_failed') for r in own),
            regressions=sum(bool(r.get('regressions')) for r in own),final_green_projects=sum(f['oracle']['green'] for f in finals),
            final_tests_passed=sum(f['oracle']['passed'] for f in finals),final_tests_total=sum(f['oracle']['total'] for f in finals),
            seconds=round(sum(r.get('seconds',0) for r in own),3),llm_calls=len(calls),tokens=sum(c.get('total_tokens',0) or 0 for c in calls),
            cost_usd=round(sum(costs),6) if costs and all(isinstance(c,(int,float)) for c in costs) else None)
    dump(run_dir/'summary.json',summary)
    with (run_dir/'iterations.csv').open('w',newline='') as stream:
        columns=['solution','project','iteration','status','accepted','seconds','tests_passed','tests_total','llm_calls','tokens']
        writer=csv.DictWriter(stream,fieldnames=columns); writer.writeheader()
        for r in rows:
            writer.writerow({**{k:r.get(k) for k in columns[:6]},'tests_passed':r.get('after',{}).get('passed'),
                'tests_total':r.get('after',{}).get('total'),'llm_calls':len(r.get('llm_calls',[])),
                'tokens':sum(c.get('total_tokens',0) or 0 for c in r.get('llm_calls',[]))})
    metadata=dict(id='benchmark-'+manifest['run_id'],kind='analysis',version=1,date=manifest['started'][:10],owner='semcod/gitive',
                  status='local',source_revision=manifest['git_head'],evidence=['manifest.json','iterations.csv','summary.json'])
    text='# Benchmark napraw — '+manifest['run_id']+'\n\n```json\n'+json.dumps(metadata,indent=2)+'\n```\n\n'
    text+=f"Wersja przypadków: `{manifest.get('fixture_version',1)}`. Liczby: `{manifest.get('case_counts','9 na projekt')}`.\n\n"
    text+=f"Tryb: **{manifest['mode']}**. Zapisane iteracje: **{len(rows)}/{summary['expected_iterations']}**. Model: `{manifest['model']}`.\n\n"
    if manifest['mode']=='mock': text+='**Test infrastruktury: brak wywołań LLM; wyniki nie mierzą skuteczności napraw.**\n\n'
    if manifest.get('methodology_status')=='pilot':
        text+='**Przebieg pilotażowy — nie używać do rankingu końcowego.** '+manifest.get('methodology_note','')+'\n\n'
    text+='''## Wyniki

| Rozwiązanie | Przyjęte poprawki | Zielone etapy | Końcowo zielone projekty | Końcowe testy | Błędy adaptera | LLM | Tokeny | Czas s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
'''
    for name,s in summary['solutions'].items():
        text+=f"| {name} | {s['accepted']} | {s['green_stages']}/{s['iterations']} | {s['final_green_projects']}/{len(manifest['projects'])} | {s['final_tests_passed']}/{s['final_tests_total']} | {s['errors']} | {s['llm_calls']} | {s['tokens']} | {s['seconds']} |\n"
    text+='\n## Trajektorie\n\n| Rozwiązanie | Projekt | Iteracja | Wynik | Testy etapu | Przyjęto | Czas s |\n|---|---|---:|---|---:|---|---:|\n'
    for r in rows:
        a=r.get('after',{}); text+=f"| {r['solution']} | {r['project']} | {r['iteration']} | {r['status']} | {a.get('passed','?')}/{a.get('total','?')} | {r.get('accepted',False)} | {r.get('seconds',0)} |\n"
    text+='''
## Interpretacja i ograniczenia

To benchmark lokalnych komponentów naprawczych z adapterami, a nie pełnych wdrożeń
GitHub Actions. Jedna próba na każdą parę rozwiązanie–projekt; brak podstaw do istotności
statystycznej lub wnioskowania o działaniu nieskończonej pętli. Wspólny model i kolejność
sekwencyjna mogą wpływać na opóźnienia dostawcy oraz cache. Czas nie stanowi rankingu modeli.

- GLM53: oryginalny krytyk/wybór, generator patcha i walidator; lokalny most testów i commitów.
- GPT6: oryginalne kontrakty, scorer, walidatory planu i patcha; lokalny most kontrolera
  i informacji zwrotnej. Nie uruchamiano produkcyjnej maszyny stanów GitHub, polityk merge,
  ani czasowego cooldownu między zadaniami (nowa grupa testów w każdym etapie).
- Opus5: oryginalna pętla wyboru z lokalnym transportem faktów oraz **dodany wykonawca
  benchmarku**. Ten przebieg nie wywołuje nowego natywnego modułu `repair`.
  Jego skuteczność wykonawcza dotyczy tej kompozycji, nie pełnej pętli produktu Opus5.

Każdy projekt startuje z identycznego błędnego kodu. Wszystkie trzy usterki są obecne od
początku; w kolejnych iteracjach ujawniane są testy kumulatywnie (liczby przypadków określa wersja zestawu w manifeście). Wcześniejsze
poprawki pozostają. Pełny zewnętrzny oracle jest uruchamiany także przed i po patchu;
jego przyszłe przypadki nie są przekazywane LLM. Każda nowa regresja odrzuca patch.
Poprawka jest przyjmowana tylko przy zwiększeniu liczby zaliczonych testów bieżącego
etapu. Już zielony etap wykonuje no-op bez LLM. `27 iteracji` nie oznacza 27 przyjętych
poprawek. Liczba przyjętych poprawek sama w sobie nie jest rankingiem: lepsza poprawka
może naprawić przyszłe błędy wcześniej i zmniejszyć liczbę późniejszych zmian.

Testy są niezmienne i znajdują się poza edytowanym projektem. Kod wykonywany jest w
osobnym procesie bez sekretów w środowisku; proces nie jest sandboxem systemowym.
Nie tworzono issues, PR ani zdalnych commitów. Raporty, różnice i podsumowania są
lokalne. Koszt jest dostępny tylko, jeśli SDK zwróci metadane kosztu; brak ceny nie
jest zerowym kosztem. Tokeny błędnych żądań bez usage pozostają nieznane.

## Artefakty

- [Manifest konfiguracji i skrótów źródeł](manifest.json)
- [Podsumowanie JSON](summary.json)
- [Wszystkie iteracje CSV](iterations.csv)
- `iterations/`: metryki, błędy, testy przed/po i metadane wywołań.
- `patches/`: rzeczywiste patche, także odrzucone.
- `final/`: końcowy kod i wynik pełnego oracle dla każdej pary.
- Repos i stan roboczy pozostają w prywatnym katalogu wskazanym w manifeście.
'''
    (run_dir/'report.md').write_text(text)
    return summary
