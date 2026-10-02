"""Readable, offline board snapshots from already-fetched GitHub metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import re

from .github import positive_number, validate_repo


def filter_rows(rows: list[dict], kind: str = "all", available: bool = False) -> list[dict]:
    """Select rows without changing their computed claim or voting state."""
    if kind not in {"all", "idea", "task", "review"}:
        raise ValueError("kind must be all, idea, task, or review")
    return [row for row in rows if (kind == "all" or row["kind"] == kind)
            and (not available or (row["kind"] == "task" and row["status"] == "available"))]


def _text(value: object) -> str:
    return " ".join("".join(char if char.isprintable() else " " for char in str(value)).split())


def _timestamp(value: datetime | str) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must include a timezone")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _item(row: dict, repo: str) -> dict:
    number = positive_number(row["number"])
    kind = row["kind"]
    if kind not in {"idea", "task", "review"}:
        raise ValueError("Unknown board row kind")
    command = f"python3 -m commonwork {{}} --repo {repo} {number}"
    item = {"number": number, "kind": kind, "title": _text(row["title"]),
            "url": f"https://github.com/{repo}/{'pull' if kind == 'review' else 'issues'}/{number}",
            "details": [], "commands": [], "available": False}
    if kind == "idea":
        item.update(status="Discussion", action="Open discussion", hint="Help turn this idea into one small, testable task.")
    elif kind == "task":
        available = row["status"] == "available"
        item.update(status="Available" if available else "Claimed", available=available, action="Open task")
        if available:
            item["hint"] = "Read the scope, request a claim, then confirm the reservation before starting."
            item["commands"].append(("Request a claim · posts to GitHub", command.format("claim")))
        else:
            holder = (row.get("holder") or {}).get("login", "unknown")
            item["details"].append(f"Held by @{_text(holder)} until {_text(row.get('expires_at'))} (UTC).")
            item["hint"] = "Someone is working on this. Read the latest comments before coordinating a handoff."
        item["commands"].append(("Read the assignment · saves a local file",
                                 command.format("packet") + f" --output work-packets/task-{number}.md"))
    else:
        sha = row.get("head_sha", "")
        if not isinstance(sha, str) or not re.fullmatch(r"[a-fA-F0-9]{40}", sha):
            raise ValueError("Review row needs a full head_sha")
        status = {"waiting": "Needs reviews", "approved": "Community support",
                  "changes_requested": "Below support threshold"}.get(row["status"], _text(row["status"]))
        item.update(status=f"Draft · {status}" if row.get("draft") else status, action="Open pull request")
        item["details"] = [f"{row['yes']} yes · {row['no']} no · {row['abstain']} abstain",
                           f"{row['decisive_votes']} of {row['quorum']} decisive votes needed for quorum",
                           f"Current commit: {sha.lower()}"]
        if row.get("stale_count"):
            item["details"].append(f"{row['stale_count']} stale ballot(s) need fresh review.")
        item["hint"] = ("Draft: the author is still working. Feedback is welcome; this is not ready for merge."
                        if row.get("draft") else "Inspect this exact commit before voting. Support is advisory; maintainers decide merges.")
        item["commands"] = [("Prepare a review · saves a local file",
                             command.format("review") + f" --output work-packets/review-{number}.md")]
    return item


def render_board_text(rows: list[dict], repo: str, *, generated_at: datetime | str, policy_source: str) -> str:
    """Render actionable terminal text; do not perform reads or writes."""
    repo = validate_repo(repo)
    lines = [f"Commonwork · {repo}", f"Read-only snapshot · {_timestamp(generated_at)}",
             f"Policy: {_text(policy_source)}", ""]
    if not rows:
        lines.extend(["No matching open ideas, tasks, or pull requests in this snapshot.",
                      f"Browse current issues: https://github.com/{repo}/issues",
                      f"Propose an idea: https://github.com/{repo}/issues/new?template=idea.yml",
                      f"Propose a bounded task: https://github.com/{repo}/issues/new?template=task.yml"])
    for row in rows:
        item = _item(row, repo)
        lines.extend([f"#{item['number']} · {item['kind']} · {item['status']} · {item['title']}",
                      item["url"], *item["details"], item["hint"]])
        for label, command in item["commands"]:
            lines.extend([f"  {label}:", f"  {command}"])
        lines.append("")
    lines.append("Rerun the board command before acting; claims and PR commits can change. This snapshot posts nothing.")
    return "\n".join(lines) + "\n"


def render_board_html(rows: list[dict], repo: str, *, generated_at: datetime | str, policy_source: str) -> str:
    """Render a standalone snapshot with local-only search and filters."""
    repo = validate_repo(repo)
    items = [_item(row, repo) for row in rows]
    cards = []
    for item in items:
        details = "".join(f"<li>{escape(_text(detail))}</li>" for detail in item["details"])
        commands = "".join(f"<div class='command'><span>{escape(label)}</span><pre tabindex='0'><code>{escape(command)}</code></pre></div>"
                           for label, command in item["commands"])
        cards.append(f"""<article class="card" data-kind="{item['kind']}" data-available="{str(item['available']).lower()}">
          <div class="card-top"><span class="eyebrow">{item['kind']} / #{item['number']}</span><span class="pill {'ready' if item['available'] else ''}">{escape(item['status'])}</span></div>
          <h2><a href="{escape(item['url'], quote=True)}">{escape(item['title'])}</a></h2>
          <ul class="details">{details}</ul><p class="hint">{escape(item['hint'])}</p>
          {commands}<a class="open-link" href="{escape(item['url'], quote=True)}">{item['action']} <span aria-hidden="true">↗</span></a>
        </article>""")
    available = sum(item["available"] for item in items)
    reviews = sum(item["kind"] == "review" for item in items)
    ideas = sum(item["kind"] == "idea" for item in items)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><title>Commonwork · {escape(repo)}</title>
<style>{_STYLE}</style></head><body><div class="wrap">
<header><a class="brand" href="https://github.com/{repo}"><span class="mark" aria-hidden="true">✳</span> Commonwork</a><span class="snapshot">Read-only snapshot</span></header>
<main><section class="hero" aria-labelledby="heading"><div><p class="eyebrow">Small contributions. Shared progress.</p>
<h1 id="heading">Find your next<br><em>useful contribution.</em></h1><p class="intro">Pick a small task, bring your own tools, and help a shared project move forward.</p>
<a class="repo" href="https://github.com/{repo}">{escape(repo)} ↗</a></div>
<dl class="stats"><div><dt>Available tasks</dt><dd>{available}</dd></div><div><dt>Open PRs</dt><dd>{reviews}</dd></div><div><dt>Ideas</dt><dd>{ideas}</dd></div></dl></section>
<aside class="notice"><strong>Captured {_timestamp(generated_at)}</strong><span>Policy: {escape(_text(policy_source))}</span>
<span>Counts cover the items included below. Claims and commits may have changed since this snapshot.</span></aside>
<form class="filters" id="filters" role="search"><div><label for="search">Search this snapshot</label><input id="search" type="search" placeholder="Title, contributor, or issue number"></div>
<div><label for="kind">Contribution type</label><select id="kind"><option value="all">All contributions</option><option value="task">Tasks</option><option value="review">Pull requests</option><option value="idea">Ideas</option></select></div>
<label class="check"><input id="available" type="checkbox">Available tasks only</label></form>
<p id="results" class="result-count" role="status" aria-live="polite">{len(items)} contribution(s) in this snapshot</p>
<section class="grid" aria-label="Contributions">{''.join(cards)}</section>
<section id="empty" class="empty"{' hidden' if items else ''}><span aria-hidden="true">↗</span><h2>No matching contributions</h2>
<p>Try another filter or check the repository for current work. Have a useful idea? Start with one small result people can review.</p>
<div><a href="https://github.com/{repo}/issues">Browse current issues</a><a href="https://github.com/{repo}/issues/new?template=idea.yml">Propose an idea</a><a href="https://github.com/{repo}/issues/new?template=task.yml">Propose a task</a></div></section>
</main><footer><strong>Your tools. Your budget. A shared result.</strong><p>Rerun the board export command to fetch new activity; reloading this page does not update its data. This page posts no comments. Commands are suggestions to run yourself; claim commands post to GitHub. Review packets are read-only. Votes advise maintainers and never merge a pull request.</p></footer>
</div><script>{_SCRIPT}</script></body></html>"""


_STYLE = """
:root{--paper:#f5f3eb;--ink:#243d35;--muted:#5a6d63;--green:#28674b;--line:#d5ddcf;--lime:#ddebba}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 system-ui,-apple-system,sans-serif}
a{color:var(--green);text-underline-offset:4px}a:focus-visible,input:focus-visible,select:focus-visible,pre:focus-visible{outline:3px solid #a45135;outline-offset:4px}
.wrap{max-width:1240px;margin:auto;padding:0 36px}header{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:18px 0;border-bottom:1px solid var(--line)}
.brand{font-size:24px;font-weight:750;text-decoration:none;letter-spacing:-1px}.mark{font-size:32px;vertical-align:middle;margin-right:8px}.snapshot,.eyebrow{font:11px/1.5 ui-monospace,monospace;letter-spacing:1.2px;text-transform:uppercase}.snapshot{background:#e5eadb;padding:8px 12px;border-radius:4px}
.hero{display:grid;grid-template-columns:1.6fr 1fr;gap:50px;align-items:end;padding:30px 0 24px}h1{font-size:clamp(32px,3.8vw,48px);line-height:1.08;letter-spacing:-2px;margin:10px 0 15px;font-weight:680}h1 em{font-family:Georgia,serif;font-weight:400}.intro{max-width:490px;color:var(--muted);margin-bottom:14px}.repo{font:13px/1.6 ui-monospace,monospace;overflow-wrap:anywhere}
.stats{display:flex;justify-content:space-between;gap:18px;border-top:1px solid var(--line);padding-top:18px;margin:0 0 5px}.stats div{display:flex;flex-direction:column-reverse}.stats dt{font-size:12px;color:var(--muted)}.stats dd{font-size:40px;line-height:1.3;margin:0;font-weight:600}
.notice{display:flex;flex-wrap:wrap;gap:3px 22px;border:1px solid var(--line);background:#eaf0e1;padding:15px 18px;font-size:12px;border-radius:7px}.notice span:last-child{flex-basis:100%}.notice span{overflow-wrap:anywhere}
.filters{display:flex;align-items:end;gap:20px;margin:22px 0 8px}.filters>div:first-child{flex:1}.filters label{display:block;font-size:12px;font-weight:600;margin-bottom:7px}input,select{font:inherit;background:#fffdf7;border:1px solid #a8b7a9;border-radius:6px;padding:10px 12px;color:var(--ink);min-height:46px}input[type=search]{width:100%}.filters .check{display:flex;gap:9px;align-items:center;min-height:46px;margin:0;white-space:nowrap}input[type=checkbox]{min-height:0;width:17px;height:17px;accent-color:var(--green)}
.result-count{font:12px/1.5 ui-monospace,monospace;color:var(--muted);margin:18px 0}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.card{background:#fffdf7;border:1px solid var(--line);border-radius:10px;padding:24px;min-width:0}.card-top{display:flex;align-items:center;justify-content:space-between;gap:10px}.pill{font-size:11px;padding:4px 9px;border:1px solid var(--line);border-radius:20px;background:#f0f1e9;text-align:right}.pill.ready{background:var(--lime);border-color:#c0d194}h2{font-size:22px;line-height:1.35;letter-spacing:-.4px;margin:17px 0}h2 a{color:var(--ink);text-decoration:none}h2 a:hover{text-decoration:underline}.details{list-style:none;padding:0;margin:12px 0;font-size:12px;font-family:ui-monospace,monospace;overflow-wrap:anywhere}.details li{margin:5px 0}.hint{font-size:14px;color:var(--muted)}.command{margin-top:16px}.command>span{font-size:11px;font-weight:600}.command pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef1e7;font-size:12px;line-height:1.6;padding:11px 13px;border-radius:6px;margin:5px 0 0}.open-link{display:inline-block;font-size:13px;font-weight:600;margin-top:20px}
.empty{border:1px dashed #b8c3b0;border-radius:10px;padding:42px;text-align:center;background:#faf9f2}.empty>span{font-size:35px}.empty p{max-width:540px;margin:0 auto 20px;color:var(--muted)}.empty div{display:flex;justify-content:center;gap:22px;flex-wrap:wrap;font-size:13px}[hidden]{display:none!important}footer{border-top:1px solid var(--line);margin:40px 0 0;padding:25px 0 32px}footer strong{font-size:14px}footer p{max-width:850px;font-size:12px;color:var(--muted)}
@media(max-width:850px){.hero{grid-template-columns:1fr;gap:26px}.stats{max-width:440px}.filters{flex-wrap:wrap}.filters>div:first-child{flex-basis:100%}.grid{grid-template-columns:1fr}}
@media(max-width:500px){.wrap{padding:0 20px}header{gap:10px}.brand{font-size:20px}.snapshot{font-size:9px;padding:7px}.hero{padding:35px 0 26px}.card{padding:19px}.card-top{align-items:start}.filters>div{width:100%}select{width:100%}.empty{padding:28px 20px}.stats dd{font-size:34px}}
"""

_SCRIPT = """
const form=document.getElementById('filters'), search=document.getElementById('search'), kind=document.getElementById('kind'), available=document.getElementById('available');
const cards=Array.from(document.querySelectorAll('.card'));
function filter(){const query=search.value.toLocaleLowerCase().trim();let count=0;for(const card of cards){const show=(!query||card.textContent.toLocaleLowerCase().includes(query))&&(kind.value==='all'||card.dataset.kind===kind.value)&&(!available.checked||card.dataset.available==='true');card.hidden=!show;if(show)count++;}document.getElementById('results').textContent=count+' of '+cards.length+' contribution(s) shown';document.getElementById('empty').hidden=count!==0;}
form.addEventListener('submit',event=>event.preventDefault());form.addEventListener('input',filter);form.addEventListener('change',filter);
"""
