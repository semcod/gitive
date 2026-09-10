"""Three small projects; three initially broken behaviors and immutable oracle cases each."""
PROJECTS = {
    "invoice_math": {
        "description": "Billing functions: percentage discount (0..100), tax applied after discount, decimal HALF_UP money rounding.",
        "source": '''from decimal import Decimal, ROUND_HALF_UP


def discounted(amount, percent):
    """Return amount reduced by percent (e.g. 20 means 20%)."""
    return amount * (1 - percent)


def taxed(amount, percent):
    """Return amount including percentage tax (e.g. 23 means 23%)."""
    return amount + percent


def money(value):
    """Return a string rounded to two decimals using decimal HALF_UP."""
    return str(round(float(value), 2))
''',
        "cases": [
            (1, "discounted", [100, 20], 80), (1, "discounted", [50, 0], 50), (1, "discounted", [200, 100], 0),
            (2, "taxed", [200, 23], 246), (2, "taxed", [50, 10], 55), (2, "taxed", [40, 0], 40),
            (3, "money", ["2.675"], "2.68"), (3, "money", ["1"], "1.00"), (3, "money", ["-1.005"], "-1.01"),
        ],
    },
    "url_router": {
        "description": "URL utilities: segment-boundary route prefixes, case-insensitive HTTP methods, query decoding with blank values and percent escapes.",
        "source": '''from urllib.parse import parse_qs


def matches(path, prefix):
    """A prefix matches itself and descendant segments, never partial names."""
    return path.startswith(prefix)


def allowed(method, methods):
    """HTTP method comparison is case insensitive on both sides."""
    return method in methods


def query_value(query, key):
    """Return the first decoded query value, retaining blanks; None when absent."""
    for pair in query.split('&'):
        name, _, value = pair.partition('=')
        if name == key:
            return value or None
    return None
''',
        "cases": [
            (1,"matches",["/api2/users","/api"],False),(1,"matches",["/api/users","/api"],True),(1,"matches",["/api","/api"],True),
            (2,"allowed",["get",["GET","POST"]],True),(2,"allowed",["POST",["post"]],True),(2,"allowed",["DELETE",["get"]],False),
            (3,"query_value",["q=hello+world","q"],"hello world"),(3,"query_value",["q=&q=second","q"],""),(3,"query_value",["x=1","q"],None),
        ],
    },
    "job_queue": {
        "description": "Queue helpers: highest priority first with FIFO ties, retries only while attempts < max_attempts, stable deduplication by (tenant,id).",
        "source": '''def ordered(jobs):
    """Return job IDs sorted by descending priority, preserving input order on ties."""
    return [j['id'] for j in sorted(jobs, key=lambda j: j['priority'])]


def may_retry(attempts, max_attempts):
    """Retries are allowed only when attempts is strictly below max_attempts."""
    return attempts <= max_attempts


def unique(jobs):
    """Keep the first job for each (tenant,id), preserving input order."""
    seen, out = set(), []
    for job in jobs:
        if job['id'] not in seen:
            seen.add(job['id'])
            out.append(job)
    return out
''',
        "cases": [
            (1,"ordered",[[{"id":"a","priority":1},{"id":"b","priority":3},{"id":"c","priority":3}]], ["b","c","a"]),
            (1,"ordered",[[]],[]),(1,"ordered",[[{"id":"x","priority":0}]], ["x"]),
            (2,"may_retry",[3,3],False),(2,"may_retry",[2,3],True),(2,"may_retry",[0,0],False),
            (3,"unique",[[{"tenant":"a","id":1},{"tenant":"b","id":1}]], [{"tenant":"a","id":1},{"tenant":"b","id":1}]),
            (3,"unique",[[{"tenant":"a","id":1},{"tenant":"a","id":1}]], [{"tenant":"a","id":1}]),
            (3,"unique",[[]],[]),
        ],
    },
}
