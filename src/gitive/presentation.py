"""Compact human-readable CLI output; raw records remain available as JSON."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import re

def dated(row):
    raw=row.get("created", "")
    match=re.search(r"(\d{8}T\d{6}Z)",str(raw) or row.get("id", ""))
    try:
        dt=datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc) if match else datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:return "brak strefy czasowej"
        return dt.astimezone(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError,TypeError):return "brak zapisanej daty"

def choice_label(row):
    name=row.get("target") or row.get("project") or row.get("browser") or "kopia"
    profiles=row.get("sessions",row.get("session_paths",[]))
    return dated(row)+" | "+name+(" | profile: "+str(len(profiles)) if "project" in row or "target" in row else "")

STATUS={'idle':'bezczynna','running':'w toku','stopping':'zatrzymywanie','stopped':'zatrzymana','complete':'zakończona','blocked':'zablokowana','error':'błąd','failed':'błąd','interrupted':'przerwana'}

def render(value,kind='status'):
    if kind=='inspect':
        browsers=', '.join(x['browser'] for x in value.get('browsers',[]) if x.get('present')) or 'brak'
        lines=['Przeglądarki wykryte na PC: '+browsers+' (nie oznacza skopiowania).']
        for key,label in [('snapshots','Archiwa'),('clones','Kopie'),('profiles','Profile noVNC')]:
            rows=value.get(key,[]);lines.append(f'{label}: {len(rows)}')
            for row in rows[-5:]:lines.append('  '+choice_label(row))
        return '\n'.join(lines)
    if kind=='projects':
        return '\n'.join(f"{name}: {STATUS.get(row.get('status'),row.get('status','—'))}" for name,row in value.items()) or 'Brak projektów.'
    if kind=='rank':return 'Wybrane rozwiązanie: '+value.get('solution','—')+'\nRanking: '+' → '.join(value.get('ranking',[]))
    if kind=='clean':
        dry='[podgląd] ' if value.get('dry_run') else ''
        cleaned=value.get('cleaned_count',0)
        kept=value.get('kept_count',0)
        kb=value.get('freed_bytes',0)/1024
        mb=kb/1024
        size_str=f"{mb:.1f} MB" if mb>=1 else f"{kb:.0f} KB"
        lines=[f"{dry}Czyszczenie danych: usunięto {cleaned} uruchomień, zachowano {kept} (zwolniono {size_str})."]
        if value.get('cleaned_runs'):
            samples=value['cleaned_runs'][:5]
            lines.append('Usunięte katalogi: '+', '.join(samples)+('...' if len(value['cleaned_runs'])>5 else ''))
        return '\n'.join(lines)
    operation=value.get('operation') or 'Pętla'
    lines=[f"{operation}: {STATUS.get(value.get('status'),value.get('status','brak danych'))}"]
    result=value.get('result') or {}
    if isinstance(result,dict):
        if result.get('id'):lines.append('Zapis: '+dated(result))
        if operation=='snapshot' and value.get('status')=='complete':
            lines.append('Profile: '+(', '.join(result.get('sessions',[])) or 'brak — przeglądarki nie skopiowano'))
            lines.append('Dalej: workspace clone (wybierz z listy)')
        elif operation=='clone' and value.get('status')=='complete':lines.append('Dalej: workspace resync (podgląd zmian)')
        elif operation=='resync':
            lines.append(f"Zmiany: {result.get('change_count',0)} | Konflikty: {result.get('conflict_count',0)}")
            lines.append('Tryb: podgląd' if result.get('dry_run') else 'Zapis: '+('wykonany' if result.get('applied') else 'nie wykonano'))
    if value.get('status')=='running':lines.append('Sprawdź później: workspace status' if value.get('operation') else 'Sprawdź później: status')
    if value.get('error'):lines.append('Błąd: '+str(value['error'])[:300])
    return '\n'.join(lines)
