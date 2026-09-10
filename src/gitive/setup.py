"""Prepare private state and copy only the Hub control bearer to a read-only secret mount."""
from pathlib import Path
import os
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[2]
data=Path(os.getenv('GITIVE_ISOLATION_ROOT',str(Path.home()/'.local/share/gitive-isolated')))/'app-data'; data.mkdir(parents=True,exist_ok=True,mode=0o700)
source=Path(os.getenv('LLM_HUB_ROOT','/home/tom/github/subactor/llm-account-hub'))/'.env'
token=dotenv_values(source).get('CONTROL_API_TOKEN')
if not token: raise SystemExit('Brak CONTROL_API_TOKEN w konfiguracji huba')
p=data/'hub-token'; p.write_text(token);p.chmod(0o600)
print('Przygotowano prywatny katalog i token Control; nie kopiowano danych logowania Codexa.')
