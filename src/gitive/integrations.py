"""Multi-source ticket streaming and fast task realization for GitHub, GitLab, and Local projects."""
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

CACHE = {}
CACHE_TTL = 20  # seconds

WIP_LABELS = {
    "wip", "in progress", "in-progress", "doing", "underway",
    "assigned", "work in progress", "active", "started", "w trakcie"
}

def normalize_priority(value):
    """Return a stable priority value for UI sorting."""
    text = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    text = re.sub(r"^(?:priority|prio)[-:_]", "", text)
    aliases = {
        "urgent": "critical", "p0": "critical", "highest": "critical",
        "p1": "high", "higher": "high",
        "p2": "medium", "normal": "medium", "default": "medium",
        "p3": "low", "lower": "low", "p4": "backlog",
    }
    return aliases.get(text, text if text in {"critical", "high", "medium", "low", "backlog"} else "medium")

def priority_from_labels(labels):
    """Infer priority from common label spellings without changing source labels."""
    for label in labels or []:
        text = str(label).strip().lower()
        match = re.search(r"(?:priority|prio)[\s:_-]*(critical|urgent|highest|higher|high|medium|normal|default|low|lower|backlog|p[0-4])$", text)
        if match:
            return normalize_priority(match.group(1))
        if text in {"critical", "urgent", "highest", "high", "higher", "medium", "normal", "low", "lower", "backlog", "p0", "p1", "p2", "p3", "p4"}:
            return normalize_priority(text)
    return "medium"

def _normalize_ticket_num(val):
    if val is None:
        return None
    s = str(val).strip()
    m = re.search(r'(?:ticket-?)?(\d+)', s, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return s.lower()

def get_github_token():
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if token:
        return token
    candidates = [
        Path(os.getenv("GITIVE_HOST_HOME", "/host-home")) / ".config/gh/hosts.yml",
        Path.home() / ".config/gh/hosts.yml",
    ]
    for p in candidates:
        if p.is_file():
            try:
                for line in p.read_text().splitlines():
                    if "oauth_token:" in line:
                        return line.split()[-1].strip()
            except Exception:
                pass
    try:
        res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return None

def collect_busy_ticket_keys(projects_dict):
    """Collect ticket numbers and slugs that are already being worked on (in progress or done locally)."""
    busy_keys = set()

    def mark_busy(repo_identifier, ticket_raw):
        t_norm = _normalize_ticket_num(ticket_raw)
        if t_norm is not None:
            if repo_identifier:
                clean = repo_identifier.rstrip("/").split("/")[-1].lower()
                busy_keys.add((clean, t_norm))
                busy_keys.add((repo_identifier.lower(), t_norm))
            else:
                busy_keys.add(t_norm)

    all_paths = []
    for name, p in projects_dict.items():
        all_paths.append((name, Path(p.get("path", ""))))
        all_paths.append((name, Path(p.get("source_path", ""))))

    source_root = Path(os.getenv("GITIVE_SOURCE_ROOT", "/source/github"))
    copy_root = Path(os.getenv("GITIVE_COPY_ROOT", "/workspace/github"))
    for root in (source_root, copy_root):
        if root.is_dir():
            for child in root.iterdir():
                if child.is_dir():
                    all_paths.append((child.name, child))
                    try:
                        for sub in child.iterdir():
                            if sub.is_dir() and ((sub / ".worktrees").is_dir() or (sub / ".git").is_dir() or (sub / "project").is_dir()):
                                all_paths.append((f"{child.name}/{sub.name}", sub))
                    except Exception:
                        pass

    seen_dirs = set()
    for repo_name, p_dir in all_paths:
        if not p_dir or not p_dir.is_dir():
            continue
        try:
            real_p = p_dir.resolve()
        except Exception:
            real_p = p_dir
        if real_p in seen_dirs:
            continue
        seen_dirs.add(real_p)

        # 1. Active worktrees
        wt_dir = p_dir / ".worktrees"
        if wt_dir.is_dir():
            try:
                for wt in wt_dir.iterdir():
                    if wt.is_dir() and "ticket-" in wt.name:
                        mark_busy(repo_name, wt.name)
            except Exception:
                pass

        # 2. Active git branch
        head_file = p_dir / ".git" / "HEAD"
        if head_file.is_file():
            try:
                head_content = head_file.read_text().strip()
                if "ticket" in head_content:
                    mark_busy(repo_name, head_content)
            except Exception:
                pass

        # 3. Planfile non-open tickets
        if (p_dir / ".planfile").is_dir():
            try:
                from .planfile_bridge import PlanfileBridge
                bridge = PlanfileBridge(p_dir)
                for t in bridge.store.list_tickets(sprint="all"):
                    st = t.status.value if hasattr(t.status, "value") else str(t.status)
                    if st.lower() not in ("open", "todo", "new", "backlog"):
                        mark_busy(repo_name, t.id)
                        binding = t.sync.get("github", {})
                        if binding.get("issue"):
                            mark_busy(repo_name, binding.get("issue"))
            except Exception:
                pass

        # 4. project/ticket-* with non-open status
        proj_t_dir = p_dir / "project"
        if proj_t_dir.is_dir():
            try:
                for tf in proj_t_dir.glob("ticket-*"):
                    if tf.is_dir():
                        readme = tf / "README.md"
                        if readme.is_file():
                            text = readme.read_text()
                            st_match = re.search(r'(?i)\bstatus\b\s*[:*]+\s*([a-zA-Z_-]+)', text)
                            status_val = st_match.group(1).upper() if st_match else ""
                            if status_val in ("IN_PROGRESS", "DONE", "CLOSED", "ACTIVE", "PUBLICATION", "RESOLVED", "CANCELLED"):
                                mark_busy(repo_name, tf.name)
            except Exception:
                pass

    return busy_keys

def is_ticket_busy(repo, number, busy_keys):
    if not busy_keys:
        return False
    num = _normalize_ticket_num(number)
    if num is None:
        return False
    if num in busy_keys:
        return True
    if repo:
        clean = repo.rstrip("/").split("/")[-1].lower()
        if (clean, num) in busy_keys or (repo.lower(), num) in busy_keys:
            return True
    return False

def fetch_github_issues(repo, credential=None, state="open", limit=30):
    cache_key = f"gh:{repo}:{state}"
    now = time.time()
    if cache_key in CACHE and now - CACHE[cache_key]["time"] < CACHE_TTL:
        return CACHE[cache_key]["data"]

    credential = credential or get_github_token()
    url = f"https://api.github.com/repos/{repo}/issues?state={state}&per_page={limit}&sort=updated"
    headers = {
        "User-Agent": "Gitive-Loop/1.0",
        "Accept": "application/vnd.github+json"
    }
    if credential:
        headers["Authorization"] = f"Bearer {credential}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        if cache_key in CACHE:
            return CACHE[cache_key]["data"]
        return []

    results = []
    for item in data:
        # Ignore pull requests returned by the issues endpoint
        if "pull_request" in item:
            continue
        # Only keep strictly open issues (not closed)
        if item.get("state") != "open":
            continue
        raw_labels = item.get("labels", [])
        label_names = [l.get("name") for l in raw_labels if isinstance(l, dict) and "name" in l]
        # Ignore issues with WIP / in-progress labels
        if any(isinstance(l, str) and l.lower() in WIP_LABELS for l in label_names):
            continue

        desc = item.get("body") or ""
        target_repo = None
        m_target = re.search(r"(?mi)^\s*(?:-\s*)?target_repository:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", desc)
        if m_target:
            target_repo = m_target.group(1).strip()
        else:
            m_title = re.search(r"in\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", item.get("title", ""))
            if m_title:
                target_repo = m_title.group(1).strip()

        clean_repo_id = repo.replace("/", "-")
        results.append({
            "id": f"gh-{clean_repo_id}-{item['number']}",
            "source": "github",
            "repository": repo,
            "target_repository": target_repo,
            "number": item["number"],
            "title": item.get("title", ""),
            "description": desc,
            "status": "open",
            "url": item.get("html_url", f"https://github.com/{repo}/issues/{item['number']}"),
            "updated_at": item.get("updated_at", ""),
            "created_at": item.get("created_at", ""),
            "labels": label_names,
            "priority": priority_from_labels(label_names),
            "author": item.get("user", {}).get("login", "")
        })

    CACHE[cache_key] = {"time": now, "data": results}
    return results

def fetch_gitlab_issues(project_path, gitlab_url="https://gitlab.com", token=None, limit=30):
    cache_key = f"gl:{project_path}"
    now = time.time()
    if cache_key in CACHE and now - CACHE[cache_key]["time"] < CACHE_TTL:
        return CACHE[cache_key]["data"]

    encoded = urllib.parse.quote(project_path, safe="")
    url = f"{gitlab_url.rstrip('/')}/api/v4/projects/{encoded}/issues?state=opened&per_page={limit}&order_by=updated_at"
    headers = {"User-Agent": "Gitive-Loop/1.0"}
    token = token or os.getenv("GITLAB_TOKEN")
    if token:
        headers["PRIVATE-TOKEN"] = token

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        if cache_key in CACHE:
            return CACHE[cache_key]["data"]
        return []

    results = []
    clean_gl_id = project_path.replace("/", "-")
    for item in data:
        if item.get("state") != "opened":
            continue
        labels = item.get("labels", [])
        if any(isinstance(l, str) and l.lower() in WIP_LABELS for l in labels):
            continue
        results.append({
            "id": f"gl-{clean_gl_id}-{item['iid']}",
            "source": "gitlab",
            "repository": project_path,
            "number": item["iid"],
            "title": item.get("title", ""),
            "description": item.get("description") or "",
            "status": "open",
            "url": item.get("web_url", ""),
            "updated_at": item.get("updated_at", ""),
            "created_at": item.get("created_at", ""),
            "labels": labels,
            "priority": priority_from_labels(labels),
            "author": item.get("author", {}).get("username", "")
        })

    CACHE[cache_key] = {"time": now, "data": results}
    return results

def discover_local_tickets(projects_dict, root_dir=None, busy_keys=None):
    results = []

    for name, p in projects_dict.items():
        proj_path = Path(p.get("path", ""))
        source_path = Path(p.get("source_path", ""))

        # 1. Planfile tickets if available (only open/todo, not in_progress or done)
        try:
            from .planfile_bridge import PlanfileBridge
            if proj_path.is_dir() and (proj_path / ".planfile").is_dir():
                bridge = PlanfileBridge(proj_path)
                for t in bridge.store.list_tickets(sprint="all"):
                    st = t.status.value if hasattr(t.status, "value") else str(t.status)
                    if st.lower() not in ("open", "todo", "new", "backlog"):
                        continue
                    if is_ticket_busy(name, t.id, busy_keys):
                        continue
                    binding = t.sync.get("github", {})
                    results.append({
                        "id": f"local-{name}-{t.id}",
                        "source": "local",
                        "project": name,
                        "repository": binding.get("repository", name),
                        "number": t.id,
                        "title": t.name,
                        "description": t.description,
                        "status": "open",
                        "url": binding.get("url") or "",
                        "planfile_id": t.id,
                        "planfile_url": "/?" + urllib.parse.urlencode({
                            "tab": "tickets", "project": name, "ticket": t.id, "action": "detail"
                        }),
                        "updated_at": t.updated_at.isoformat() if hasattr(t, "updated_at") and t.updated_at else "",
                        "created_at": t.created_at.isoformat() if hasattr(t, "created_at") and t.created_at else "",
                        "priority": normalize_priority(getattr(t, "priority", "medium")),
                        "engine": t.executor.handler if t.executor else "auto",
                        "labels": ["planfile", f"engine:{t.executor.handler}" if t.executor else "unassigned"]
                    })
        except Exception:
            pass

        # 2. Check for project/ticket-* markdown that is strictly OPEN/TODO (no worktrees)
        target_dir = source_path if source_path.is_dir() else proj_path
        if target_dir.is_dir():
            t_dir = target_dir / "project"
            if t_dir.is_dir():
                for tf in t_dir.glob("ticket-*"):
                    if tf.is_dir():
                        if is_ticket_busy(name, tf.name, busy_keys):
                            continue
                        readme = tf / "README.md"
                        if readme.is_file():
                            text = readme.read_text()
                            st_match = re.search(r'(?i)\bstatus\b\s*[:*]+\s*([a-zA-Z_-]+)', text)
                            status_val = st_match.group(1).upper() if st_match else ""
                            # Only include if explicitly OPEN/TODO/DRAFT
                            if status_val not in ("OPEN", "TODO", "DRAFT"):
                                continue
                            first_line = text.splitlines()
                            title = first_line[0].lstrip("# ").strip() if first_line else tf.name
                            results.append({
                                "id": f"doc-{name}-{tf.name}",
                                "source": "local",
                                "project": name,
                                "repository": name,
                                "number": tf.name,
                                "title": title,
                                "description": f"Ticket z repozytorium: {tf}",
                                "status": "open",
                                "url": "",
                                "updated_at": datetime.fromtimestamp(readme.stat().st_mtime, tz=timezone.utc).isoformat(),
                                "created_at": datetime.fromtimestamp(readme.stat().st_ctime, tz=timezone.utc).isoformat(),
                                "priority": "medium",
                                "labels": ["repository-ticket"]
                            })

    return results

def aggregate_tickets(projects_dict, source="all", custom_repos=None, query=None, limit=80):
    all_tickets = []
    busy_keys = collect_busy_ticket_keys(projects_dict)

    # 1. GitHub sources (strictly open and not busy)
    if source in ("all", "github"):
        repos = set(custom_repos or [])
        repos.add("semcod/code2logic")
        repos.add("semcod/gitive")
        for p in projects_dict.values():
            sp = p.get("source_path", "")
            if "semcod/" in sp:
                repos.add("semcod/" + sp.split("semcod/")[-1].split("/")[0])
            elif "subactor/" in sp:
                repos.add("subactor/" + sp.split("subactor/")[-1].split("/")[0])

        token = get_github_token()
        for r in repos:
            try:
                issues = fetch_github_issues(r, token, state="open", limit=30)
                for item in issues:
                    if not is_ticket_busy(r, item.get("number"), busy_keys):
                        all_tickets.append(item)
            except Exception:
                pass

    # 2. GitLab sources
    if source in ("all", "gitlab"):
        pass

    # 3. Local sources (only open/todo)
    if source in ("all", "local"):
        try:
            local_items = discover_local_tickets(projects_dict, busy_keys=busy_keys)
            for item in local_items:
                if not is_ticket_busy(item.get("repository"), item.get("number"), busy_keys):
                    all_tickets.append(item)
        except Exception:
            pass

    # Filter out anything that is not open
    all_tickets = [t for t in all_tickets if t.get("status") == "open"]

    # Filter by search query if provided
    if query:
        q = query.lower()
        all_tickets = [
            t for t in all_tickets
            if q in t.get("title", "").lower() or q in t.get("description", "").lower() or q in t.get("repository", "").lower()
        ]

    # Sort by updated_at descending
    def sort_key(t):
        up = t.get("updated_at") or ""
        return up

    all_tickets.sort(key=sort_key, reverse=True)
    return all_tickets[:limit]

def match_project_for_repo(repo, projects_dict):
    """Find the best matching project for a given repo (e.g., semcod/code2logic -> code2logic)."""
    clean_repo = repo.split("/")[-1].lower()
    if clean_repo in projects_dict:
        return clean_repo
    for name, p in projects_dict.items():
        if clean_repo in name.lower() or name.lower() in clean_repo:
            return name
        sp = p.get("source_path", "").lower()
        if clean_repo in sp:
            return name
    return next(iter(projects_dict.keys())) if projects_dict else None
