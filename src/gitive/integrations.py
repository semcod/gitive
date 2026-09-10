"""Multi-source ticket streaming and fast task realization for GitHub, GitLab, and Local projects."""
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

CACHE = {}
CACHE_TTL = 20  # seconds

def get_github_token():
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if token:
        return token
    # Check potential hosts.yml locations
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

def fetch_github_issues(repo, token=None, state="all", limit=30):
    cache_key = f"gh:{repo}:{state}"
    now = time.time()
    if cache_key in CACHE and now - CACHE[cache_key]["time"] < CACHE_TTL:
        return CACHE[cache_key]["data"]

    token = token or get_github_token()
    url = f"https://api.github.com/repos/{repo}/issues?state={state}&per_page={limit}&sort=updated"
    headers = {
        "User-Agent": "Gitive-Loop/1.0",
        "Accept": "application/vnd.github+json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        # If cache exists (even stale), return it on network failure
        if cache_key in CACHE:
            return CACHE[cache_key]["data"]
        return []

    results = []
    for item in data:
        # Ignore pull requests returned by the issues endpoint
        if "pull_request" in item:
            continue
        results.append({
            "id": f"gh-{repo.replace('/', '-')}-{item['number']}",
            "source": "github",
            "repository": repo,
            "number": item["number"],
            "title": item.get("title", ""),
            "description": item.get("body") or "",
            "status": "done" if item.get("state") == "closed" else "open",
            "url": item.get("html_url", f"https://github.com/{repo}/issues/{item['number']}"),
            "updated_at": item.get("updated_at", ""),
            "created_at": item.get("created_at", ""),
            "labels": [l.get("name") for l in item.get("labels", []) if isinstance(l, dict) and "name" in l],
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
    url = f"{gitlab_url.rstrip('/')}/api/v4/projects/{encoded}/issues?per_page={limit}&order_by=updated_at"
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
    for item in data:
        results.append({
            "id": f"gl-{project_path.replace('/', '-')}-{item['iid']}",
            "source": "gitlab",
            "repository": project_path,
            "number": item["iid"],
            "title": item.get("title", ""),
            "description": item.get("description") or "",
            "status": "done" if item.get("state") == "closed" else "open",
            "url": item.get("web_url", ""),
            "updated_at": item.get("updated_at", ""),
            "created_at": item.get("created_at", ""),
            "labels": item.get("labels", []),
            "author": item.get("author", {}).get("username", "")
        })

    CACHE[cache_key] = {"time": now, "data": results}
    return results

def discover_local_tickets(projects_dict, root_dir=None):
    results = []
    source_root = Path(os.getenv("GITIVE_SOURCE_ROOT", "/source/github"))
    copy_root = Path(os.getenv("GITIVE_COPY_ROOT", "/workspace/github"))

    for name, p in projects_dict.items():
        proj_path = Path(p.get("path", ""))
        source_path = Path(p.get("source_path", ""))
        # 1. Planfile tickets if available
        try:
            from .planfile_bridge import PlanfileBridge
            if proj_path.is_dir() and (proj_path / ".planfile").is_dir():
                bridge = PlanfileBridge(proj_path)
                for t in bridge.store.list_tickets():
                    binding = t.sync.get("github", {})
                    results.append({
                        "id": f"local-{name}-{t.id}",
                        "source": "local",
                        "project": name,
                        "repository": binding.get("repository", name),
                        "number": t.id,
                        "title": t.name,
                        "description": t.description,
                        "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                        "url": binding.get("url") or "",
                        "updated_at": t.updated_at.isoformat() if hasattr(t, "updated_at") and t.updated_at else "",
                        "created_at": t.created_at.isoformat() if hasattr(t, "created_at") and t.created_at else "",
                        "engine": t.executor.handler if t.executor else "auto",
                        "labels": ["planfile", f"engine:{t.executor.handler}" if t.executor else "unassigned"]
                    })
        except Exception:
            pass

        # 2. Check for project/ticket-* or .worktrees in source or copy
        target_dir = source_path if source_path.is_dir() else proj_path
        if target_dir.is_dir():
            # Look for worktrees
            wt_dir = target_dir / ".worktrees"
            if wt_dir.is_dir():
                for wt in wt_dir.iterdir():
                    if wt.name.startswith("ticket-"):
                        ticket_slug = wt.name.removeprefix("ticket-")
                        results.append({
                            "id": f"wt-{name}-{wt.name}",
                            "source": "local",
                            "project": name,
                            "repository": name,
                            "number": wt.name,
                            "title": f"Worktree: {ticket_slug.replace('--', ' / ')}",
                            "description": f"Aktywny worktree w {wt}",
                            "status": "in_progress",
                            "url": "",
                            "updated_at": datetime.fromtimestamp(wt.stat().st_mtime, tz=timezone.utc).isoformat(),
                            "created_at": datetime.fromtimestamp(wt.stat().st_ctime, tz=timezone.utc).isoformat(),
                            "labels": ["worktree"]
                        })
            # Look for project/ticket-* markdown
            t_dir = target_dir / "project"
            if t_dir.is_dir():
                for tf in t_dir.glob("ticket-*"):
                    if tf.is_dir():
                        readme = tf / "README.md"
                        if readme.is_file():
                            first_line = readme.read_text().splitlines()
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
                                "labels": ["repository-ticket"]
                            })

    return results

def aggregate_tickets(projects_dict, source="all", custom_repos=None, query=None, limit=80):
    all_tickets = []
    
    # 1. GitHub sources
    if source in ("all", "github"):
        repos = set(custom_repos or [])
        # Auto-detect repos from projects
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
                issues = fetch_github_issues(r, token=token, limit=30)
                all_tickets.extend(issues)
            except Exception:
                pass

    # 2. GitLab sources
    if source in ("all", "gitlab"):
        # If any gitlab repos provided
        pass

    # 3. Local sources
    if source in ("all", "local"):
        try:
            local_items = discover_local_tickets(projects_dict)
            all_tickets.extend(local_items)
        except Exception:
            pass

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
    # Fallback to first project if available
    return next(iter(projects_dict.keys())) if projects_dict else None
