"""Contextual project/ticket shell; only backend evidence supplies the operation."""
import cmd
import getpass
import os
import re
import shlex
import sys
import threading
import time
from urllib.parse import urlencode


def text(value):
    return ''.join(c for c in str(value) if c.isprintable())


def segment(value):
    return re.sub(r'[^\w.@-]+', '-', str(value), flags=re.UNICODE)[:80] or '-'


class ContextShell(cmd.Cmd):
    intro = 'Wybierz numer · projects · tickets · menu · back · help · exit'

    def __init__(self, api, dispatch, records, menu, color, sync_help):
        super().__init__()
        self.api, self.dispatch, self.records = api, dispatch, records
        self.global_menu, self.color, self.sync_help = menu, color, sync_help
        try: self.username = getpass.getuser()
        except (KeyError, OSError): self.username = 'uid-'+str(os.getuid())
        self.project = self.ticket = None
        self.operation = {'operation': 'idle'}
        self.choices = []
        self.closed = threading.Event()

    @property
    def prompt(self):
        return '/'.join(segment(x) for x in (self.username, self.project or '-',
                         self.ticket['id'] if self.ticket else '-', self.operation['operation']))+'> '

    def refresh(self):
        key = (self.project, self.ticket['id'] if self.ticket else None)
        if not all(key):
            self.operation = {'operation': 'idle'}
            return
        try:
            value = self.api('/api/operations?'+urlencode(dict(project=key[0], ticket=key[1])), timeout=2)
        except Exception:
            value = {'operation': 'offline'}
        if key == (self.project, self.ticket['id'] if self.ticket else None):
            self.operation = value

    def poll(self):
        while not self.closed.wait(1):
            self.refresh()

    def preloop(self): self.onecmd('menu')
    def emptyline(self): self.refresh()

    def cmdloop(self, intro=None):
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return super().cmdloop(intro)
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.completion import WordCompleter
            from prompt_toolkit.styles import Style
        except ImportError:
            print('Odświeżanie po poleceniu; tryb live: pip install "prompt-toolkit>=3.0.52,<4"')
            return super().cmdloop(intro)
        self.preloop()
        print(self.intro)
        worker = threading.Thread(target=self.poll, daemon=True)
        worker.start()
        session = PromptSession(completer=WordCompleter(['projects', 'tickets', 'menu', 'back', 'status',
                              'run', 'new', 'sync', 'operations', 'watch', 'help', 'exit']))
        style = Style.from_dict({'prompt': 'cyan bold'}) if 'NO_COLOR' not in os.environ else Style.from_dict({})
        try:
            while True:
                try:
                    line = session.prompt(lambda: [('class:prompt', self.prompt)], refresh_interval=1, style=style)
                except KeyboardInterrupt:
                    continue
                except EOFError:
                    break
                if self.onecmd(line): break
        finally:
            self.closed.set()
            worker.join(3)

    def onecmd(self, line):
        try:
            return super().onecmd(line)
        except KeyboardInterrupt:
            print('Anulowano polecenie; uruchomiona pętla nadal działa.')
        except (Exception, SystemExit) as exc:
            if isinstance(exc, SystemExit) and exc.code in (None, 0): return
            print(self.color(text(exc), 'red'))
        finally:
            self.refresh()

    def show_choices(self, title, choices):
        self.choices = choices
        print(self.color('\n'+text(title), 'bold'))
        for i, (label, _) in enumerate(choices, 1): print(f'{i}. {text(label)}')
        print('Numer wybiera pozycję · back wraca o poziom · help pokazuje polecenia')

    def do_menu(self, arg):
        """Pokaż działania dla bieżącego projektu lub ticketu."""
        if arg.strip(): return self.onecmd(arg.strip())
        if self.ticket:
            self.show_choices(self.ticket['title'], [
                ('Status i powiązanie GitHub', 'status'), ('Uruchom ticket', 'run'),
                ('Pobierz zmiany powiązanego Issue', 'sync pull'), ('Wyślij ticket do GitHub', 'sync push'),
                ('Historia operacji', 'operations'), ('Wróć do projektu', 'back')])
        elif self.project:
            self.show_choices('PROJEKT: '+self.project, [
                ('Wybierz ticket', 'tickets'), ('Dodaj ticket', 'new'),
                ('Status projektu', 'status'), ('Testy we własnym runtime', 'twin test '+shlex.quote(self.project)),
                ('Terminal projektu w noVNC', 'twin terminal '+shlex.quote(self.project)),
                ('Wybierz inny projekt', 'projects'), ('Wróć do Gitive', 'back')])
        else:
            self.choices = [(row['label'], shlex.join(row['argv'])) for row in self.global_menu()]

    def do_projects(self, arg):
        """Wybierz projekt z listy: projects [nazwa]."""
        projects = self.api('/api/projects')
        if arg:
            if arg not in projects: raise ValueError('Nieznany projekt')
            self.project, self.ticket = arg, None
            self.operation = {'operation': 'idle'}
            self.do_menu('')
        else:
            self.show_choices('Wybierz projekt', [(name+' · '+p.get('status', '?'), 'projects '+shlex.quote(name))
                                                   for name, p in projects.items()])

    def require_project(self):
        if not self.project: raise ValueError('Najpierw wybierz projekt: projects')

    def require_ticket(self):
        self.require_project()
        if not self.ticket: raise ValueError('Najpierw wybierz ticket: tickets')

    def do_tickets(self, arg):
        """Lista lokalnych ticketów Planfile z datą i powiązaniem GitHub."""
        # Preserve the full CLI grammar, e.g. tickets create PROJECT --title ...
        if arg: return self.dispatch(['tickets', *shlex.split(arg)])
        self.require_project()
        self.ticket = None
        self.operation = {'operation': 'idle'}
        rows = self.records(self.project)
        self.ticket_choices = rows
        print('Lokalne tickety Planfile. GitHub oznacza powiązane Issue, nie import wszystkich zgłoszeń.')
        choices = []
        for i, row in enumerate(rows):
            github = 'GitHub #'+str(row['github'].get('id')) if row['github'].get('url') else 'tylko lokalny'
            choices.append((f"{row['title']} · {row['status']} · {row['executor']} · {row['created']} · {github}",
                            'select-ticket '+str(i+1)))
        self.show_choices('Wybierz ticket', choices)
        if not rows: print('Brak ticketów. Wpisz new, aby utworzyć pierwszy.')

    def select_ticket(self, number):
        index = int(number)-1
        if not 0 <= index < len(getattr(self, 'ticket_choices', [])): raise ValueError('Niepoprawny numer ticketu')
        self.ticket = self.ticket_choices[index]
        self.refresh()
        self.do_status('')
        self.do_menu('')

    def do_back(self, arg):
        """Powrót: ticket → projekt → Gitive."""
        if self.ticket: self.ticket = None
        else: self.project = None
        self.operation = {'operation': 'idle'}
        self.do_menu('')

    def do_status(self, arg):
        """Status bieżącego projektu, ticketu i rzeczywistego procesu."""
        if not self.project: return self.dispatch(['status'])
        if not self.ticket: return self.dispatch(['project', 'status', self.project])
        # Re-read local state after sync or execution; a menu snapshot isn't current state.
        row = next((r for r in self.records(self.project) if r['id'] == self.ticket['id']), None)
        if row is None: raise ValueError('Ticket jest już niedostępny; wybierz tickets')
        self.ticket = row
        self.refresh()
        print(text(f"{row['title']} · {row['status']} · {row['executor']}"))
        print(text('Planfile: '+row['id']+' · '+row['created']))
        print(text('GitHub: '+row['github'].get('url', 'brak powiązania — ticket lokalny')))
        op = self.operation
        print(text('Operacja: '+op['operation']+((' · '+op['function']+' · PID '+str(op['pid'])) if op.get('function') else '')))
        if op['operation'] == 'idle': print('Brak aktywnego procesu tego ticketu.')

    def do_run(self, arg):
        """Uruchom wybrany ticket przy użyciu przypisanego wykonawcy."""
        self.require_ticket()
        return self.dispatch(['tickets', 'run', self.project, '--ticket', self.ticket['id']])

    def do_new(self, arg):
        """Dodaj ticket do projektu: new [tytuł], następnie wybierz wykonawcę."""
        self.require_project()
        title = arg or input('Tytuł ticketu: ').strip()
        if not title: raise ValueError('Tytuł jest wymagany')
        description = input('Opis / kryteria odbioru: ').strip()
        names = ['auto', 'glm53', 'gpt6', 'opus5']
        print('1. Najlepszy według benchmarku · 2. GLM53 · 3. GPT6 · 4. Opus5')
        answer = input('Wykonawca [1]: ').strip() or '1'
        if answer not in ('1', '2', '3', '4'): raise ValueError('Niepoprawny numer')
        self.dispatch(['tickets', 'create', self.project, '--title', title, '--description', description,
                       '--engine', names[int(answer)-1]])
        self.do_tickets('')

    def do_sync(self, arg):
        """sync pull|push [owner/repo]: synchronizacja wybranego ticketu; sync bez ticketu: instrukcja PC."""
        if not self.ticket and not arg: return self.sync_help()
        self.require_ticket()
        args = shlex.split(arg)
        if not args or args[0] not in ('pull', 'push') or len(args) > 2:
            raise ValueError('Użyj sync pull lub sync push [owner/repo]')
        repo = args[1] if len(args) == 2 else self.ticket['github'].get('repository')
        if not repo: repo = input('Repozytorium GitHub (owner/repo): ').strip()
        self.dispatch(['tickets', 'sync', self.project, '--ticket', self.ticket['id'], '--direction', args[0], '--repo', repo])
        self.do_status('')

    def do_operations(self, arg):
        """Ostatnie zdarzenia operacji tego ticketu w bieżącym uruchomieniu."""
        self.require_ticket()
        self.refresh()
        for row in self.operation.get('events', []):
            print(text(f"{row['at']} · {row['operation']} · {row['function']} · {row['status']}"))
        if not self.operation.get('events'): print('Brak zdarzeń dla tego ticketu w bieżącym uruchomieniu.')

    def do_watch(self, arg):
        """Obserwuj zmiany operacji. Ctrl+C wraca do shellu, bez zatrzymywania zadania."""
        self.require_ticket()
        print('Ctrl+C: wróć do shellu. stop: osobne polecenie zatrzymania pętli.')
        previous = None
        try:
            while True:
                self.refresh()
                key = (self.prompt, self.operation.get('sequence'))
                if key != previous: print(self.prompt+text(self.operation.get('function', ''))); previous = key
                time.sleep(1)
        except KeyboardInterrupt: pass

    def do_stop(self, arg):
        """Zatrzymaj pętlę bieżącego projektu; nie zatrzymuj obcego wykonania."""
        self.require_project()
        if self.api('/api/state').get('project') != self.project:
            raise ValueError('Bieżąca pętla nie dotyczy tego projektu')
        self.dispatch(['stop'])

    def default(self, line):
        if line.strip() == '0': return self.do_back('')
        if line.strip().isdigit():
            index = int(line.strip())-1
            if not 0 <= index < len(self.choices): raise ValueError('Niepoprawny numer. Wpisz menu.')
            return self.onecmd(self.choices[index][1])
        args = shlex.split(line)
        if args[:1] == ['select-ticket']: return self.select_ticket(args[1])
        if args[:2] == ['project', 'open']: return self.do_projects(args[2] if len(args) > 2 else '')
        if args[:1] == ['shell']: raise ValueError('Jesteś już w shellu. Użyj menu.')
        if args[:1] == ['menu']: return self.onecmd(args[1]) if len(args) == 2 else self.do_menu('')
        return self.dispatch(args)

    def do_exit(self, arg): return True
    def do_EOF(self, arg): return True
