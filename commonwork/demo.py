"""A deterministic, offline walkthrough using the real coordination functions."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from .coordinator import DEFAULT_POLICY
from .tasks import claim_state, render_claim_summary, render_work_packet
from .votes import tally_votes, render_vote_summary


OLD_SHA = "a12bc345" + "0" * 32
NEW_SHA = "b78de901" + "0" * 32


def _comment(number, user_id, login, body, minute=0):
    timestamp = f"2026-10-02T12:{minute:02}:00Z"
    return {"id": number, "body": body, "user": {"id": user_id, "login": login, "type": "User"},
            "created_at": timestamp, "updated_at": timestamp}


def run_demo(output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    task = {"number": 12, "title": "[Task] Make the food pantry directory accessible",
            "state": "open", "html_url": "https://github.com/example/community-project/issues/12",
            "body": "### Goal\nHelp neighbors using a keyboard find a food pantry.\n\n"
                    "### Acceptance criteria\n- Every filter has a visible label.\n- Keyboard focus is visible.\n"
                    "- Document the keyboard walkthrough and its result.\n\n"
                    "### Allowed files\nweb/directory.html\nweb/directory.css\n\n"
                    "### Out of scope\nDo not alter pantry listings, contact details, or opening hours.\n\n"
                    "### Suggested effort\n30 minutes"}
    now = datetime(2026, 10, 2, 12, 30, tzinfo=timezone.utc)
    claims = [_comment(10, 11, "river", "/claim"), _comment(11, 12, "sage", "/claim", 1)]
    ballots = [
        _comment(20, 21, "morgan", f"/vote yes {OLD_SHA}\nI tested tab navigation and visible focus.", 2),
        _comment(21, 22, "kai", f"/vote yes {OLD_SHA}\nI checked each filter label in the diff.", 3),
        _comment(22, 23, "jules", f"/vote no {OLD_SHA}\nThe mobile focus indicator needs more contrast.", 4),
        _comment(23, 11, "river", f"/vote yes {OLD_SHA}\nThis is my PR; this vote must not count.", 5),
    ]
    claim = claim_state(claims, now, DEFAULT_POLICY["claim_hours"])
    before = tally_votes(ballots, OLD_SHA, 11, DEFAULT_POLICY)
    after = tally_votes(ballots, NEW_SHA, 11, DEFAULT_POLICY)
    packet = render_work_packet(task, "example/community-project", OLD_SHA)
    summary = render_vote_summary(before)
    (output / "work-packet.md").write_text(packet)
    (output / "vote-summary.md").write_text(summary)
    (output / "claim-summary.md").write_text(render_claim_summary(claim))
    (output / "results.json").write_text(json.dumps({"mode": "offline_fixture", "claim": claim, "current_revision": before, "new_revision": after}, indent=2) + "\n")
    document = _page(before, after, summary)
    (output / "index.html").write_text(document)
    return output / "index.html"


def _page(before, after, summary):
    # Serialize computed results, never user-generated HTML. Script escaping is
    # retained if fixture names later become user-provided in a read-only export.
    scenarios = json.dumps([before, after]).replace("<", "\\u003c")
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Commonwork · A little spare intelligence. A shared purpose.</title>
<style>
:root{--ink:#243d35;--muted:#65736c;--paper:#f5f3eb;--line:#d7ddd1;--green:#28674b;--lime:#d9edab;--rust:#a45135}
*{box-sizing:border-box}body{margin:0;color:var(--ink);background:var(--paper);font:16px/1.6 system-ui,-apple-system,sans-serif}
a{color:var(--green);text-underline-offset:4px}button{font:inherit;cursor:pointer}button:focus-visible,a:focus-visible{outline:3px solid var(--rust);outline-offset:4px}
.wrap{max-width:1200px;margin:auto;padding:0 36px}header{display:flex;justify-content:space-between;align-items:center;padding:25px 0;border-bottom:1px solid var(--line);gap:20px}
.logo{font-size:22px;font-weight:750;letter-spacing:-1px;display:flex;align-items:center;gap:10px}.mark{width:30px;height:30px;display:grid;grid-template-columns:1fr 1fr;gap:3px;transform:rotate(-8deg)}.mark i{background:var(--green);border-radius:50% 50% 3px 50%}.mark i:nth-child(2){opacity:.5}.mark i:nth-child(3){opacity:.75}
.badge{font:11px/1.3 ui-monospace,monospace;letter-spacing:1.2px;text-transform:uppercase;background:#e7ebdf;padding:9px 12px;border-radius:5px}.hero{padding:56px 0 40px;display:grid;grid-template-columns:1.65fr 1fr;gap:55px;align-items:end}
.eyebrow{font:12px ui-monospace,monospace;text-transform:uppercase;letter-spacing:2px;color:var(--green)}h1{font-family:Georgia,serif;font-size:clamp(38px,5.3vw,66px);line-height:1.05;font-weight:400;letter-spacing:-2px;margin:18px 0 23px}h1 em{font-weight:400;color:var(--green)}.intro{max-width:610px;font-size:18px;color:var(--muted);line-height:1.65}.aside{border-left:2px solid var(--green);padding:4px 0 4px 23px;margin-bottom:7px}.aside p{margin:0 0 14px}.aside small{color:var(--muted)}
.section-head{display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--line);padding:25px 0 20px;gap:20px}h2{font-size:20px;margin:0;font-weight:650;letter-spacing:-.4px}.section-head span{font-size:13px;color:var(--muted)}.board{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-bottom:44px}.lane-name{font:11px ui-monospace,monospace;text-transform:uppercase;letter-spacing:1.5px;margin:0 0 12px;color:var(--muted)}.card{background:#fffef9;border:1px solid var(--line);border-radius:12px;padding:23px;min-height:285px;display:flex;flex-direction:column}.card .tag{font:11px ui-monospace,monospace;color:var(--green);margin-bottom:15px}h3{font-size:20px;line-height:1.3;margin:0 0 12px;letter-spacing:-.5px}.card p{font-size:14px;color:var(--muted);margin:0 0 20px}.card-bottom{margin-top:auto;padding-top:16px;border-top:1px solid var(--line);font-size:13px}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--green);margin-right:6px}.pill{font-size:11px;border-radius:20px;padding:4px 9px;background:#eaf0df;display:inline-block;margin-bottom:13px;align-self:flex-start}
.lab{background:var(--ink);color:#f7f7ed;border-radius:16px;padding:32px;display:grid;grid-template-columns:1fr 1.15fr;gap:42px;margin-bottom:28px}.lab .eyebrow{color:var(--lime)}.lab h2{font:33px/1.15 Georgia,serif;margin:13px 0 17px}.lab p{font-size:14px;color:#c2cec4}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:23px 0}.tabs button{border:1px solid #738779;background:transparent;color:#f7f7ed;border-radius:6px;padding:9px 14px;font-size:13px}.tabs button[aria-pressed=true]{background:var(--lime);color:var(--ink);border-color:var(--lime)}
.vote-panel{background:#f9faf3;color:var(--ink);border-radius:9px;padding:23px}.vote-top{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--muted)}.counts{display:flex;gap:35px;margin:18px 0}.count b{display:block;font-size:34px;line-height:1.1}.count span{font-size:12px;color:var(--muted)}#status{font-size:17px;font-weight:650;margin:7px 0}.sha{overflow-wrap:anywhere;font-size:11px;font-family:ui-monospace,monospace;background:#e8eee3;padding:9px;border-radius:5px}#explanation{font-size:13px;color:var(--muted);margin:12px 0}.rule{font-size:11px;color:var(--muted);border-top:1px solid var(--line);padding-top:12px}.links{display:flex;gap:23px;flex-wrap:wrap;font-size:13px;margin-bottom:30px}details{border:1px solid var(--line);padding:15px 20px;border-radius:9px;margin-bottom:35px}summary{cursor:pointer;font-size:14px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;line-height:1.6;color:var(--muted)}footer{padding:20px 0 32px;border-top:1px solid var(--line);font-size:12px;color:var(--muted);display:flex;gap:24px;justify-content:space-between}
@media(max-width:780px){.wrap{padding:0 20px}.hero{grid-template-columns:1fr;gap:20px;padding:36px 0}.board{grid-template-columns:1fr}.card{min-height:0}.lab{grid-template-columns:1fr;padding:24px;gap:15px}.section-head{align-items:flex-start;flex-direction:column;gap:5px}header{gap:10px}.badge{font-size:9px}footer{flex-direction:column;gap:5px}.counts{gap:28px}}
</style></head><body><div class="wrap">
<header><div class="logo"><span class="mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span>commonwork</div><span class="badge">Local prototype · Offline demo</span></header>
<main><section class="hero"><div><div class="eyebrow">Small contributions. Shared progress.</div><h1>Your spare AI time.<br><em>Something good, together.</em></h1><p class="intro">Pick a useful task. Work with the AI tools you already have. Bring back a contribution the community can review.</p></div><div class="aside"><p>You keep your AI account.<br>GitHub holds the shared work.<br>The community helps decide.</p><small>Example project below: a neighborhood food pantry directory. All people, work, and votes shown here are fixtures.</small></div></section>
<div class="section-head"><h2>From an idea to a contribution</h2><span>One project · Three steps · Your own pace</span></div>
<section class="board" aria-label="Example collaboration board">
<div><p class="lane-name">01 / Shape an idea</p><article class="card"><span class="tag">IDEA #8</span><h3>Help neighbors find a food pantry.</h3><p>A simple, accessible directory of local resources, with a clear way to report outdated information.</p><div class="card-bottom"><span class="dot"></span>Discuss the goal in a GitHub issue</div></article></div>
<div><p class="lane-name">02 / Contribute a little</p><article class="card"><span class="tag">TASK #12 · ABOUT 30 MIN</span><h3>Make the directory work with a keyboard.</h3><p>Label each filter, make focus visible, and document a keyboard walkthrough.</p><span class="pill">Reserved by river · 24-hour lease</span><div class="card-bottom"><a href="work-packet.md">Open the AI work packet ↗</a></div></article></div>
<div><p class="lane-name">03 / Review the result</p><article class="card"><span class="tag">PULL REQUEST #16</span><h3>Accessible filters and visible focus.</h3><p>Contributors explain their votes in the PR. The tally is tied to the exact code they reviewed.</p><span class="pill">2 yes · 1 no · Community support</span><div class="card-bottom">Maintainer reviews and decides to merge</div></article></div>
</section>
<section class="lab" aria-label="Interactive vote demonstration"><div><div class="eyebrow">Try the voting rule</div><h2>Approval belongs to<br>the code you reviewed.</h2><p>A new commit changes the proposal. Switch revisions to see the real vote engine discard ballots for the old version.</p><div class="tabs"><button type="button" aria-pressed="true" id="old">Reviewed revision</button><button type="button" aria-pressed="false" id="new">After a new commit</button></div><p>No request is sent to GitHub. These results were computed locally from sample comments.</p></div><div class="vote-panel" aria-live="polite"><div class="vote-top">Commonwork community vote · Advisory</div><div class="counts"><div class="count"><b id="yes">2</b><span>Yes</span></div><div class="count"><b id="no">1</b><span>No</span></div><div class="count"><b id="abstain">0</b><span>Abstain</span></div></div><div id="status">Community support reached</div><div class="sha" id="sha"></div><p id="explanation"></p><div class="rule">At least 3 yes/no votes · At least 2/3 yes · PR author excluded<br>One account is one ballot, not proof of one independent person.</div></div></section>
<nav class="links" aria-label="Demo artifacts"><a href="vote-summary.md">PR comment preview ↗</a><a href="claim-summary.md">Task reservation ↗</a><a href="results.json">Inspect computed results ↗</a></nav>
<details><summary>See the exact comment the coordinator would post</summary><pre>""" + html.escape(summary) + """</pre></details>
</main><footer><span>An offline walkthrough. Live coordination happens in your GitHub repository.</span><span>No AI credentials collected. No automatic merging.</span></footer></div>
<script>const states=""" + scenarios + """;
function show(i){const s=states[i];for(const k of ['yes','no','abstain'])document.getElementById(k).textContent=s[k];document.getElementById('sha').textContent=s.head_sha;document.getElementById('status').textContent=s.status==='approved'?'Community support reached':'Fresh reviews needed';document.getElementById('explanation').textContent=i?'All 3 eligible ballots refer to the previous commit. None count toward this revision.':'Three reviewers cast eligible ballots. The author’s self-vote was excluded. Required tests and the maintainer’s review still apply.';document.getElementById('old').setAttribute('aria-pressed',String(i===0));document.getElementById('new').setAttribute('aria-pressed',String(i===1));}
document.getElementById('old').addEventListener('click',()=>show(0));document.getElementById('new').addEventListener('click',()=>show(1));show(0);
</script></body></html>"""
