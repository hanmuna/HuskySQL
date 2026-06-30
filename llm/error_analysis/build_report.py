"""Generate report.html: all failures, grouped by difficulty (tabs) then by
auto-classified error category (collapsible cases). The gallery + AST clause
stats are deterministic; the RA/BNF lens bullets and root-cause paragraph come
from outputs/insights.json (run 07_synthesize_insights.py first) and are
grounded in real idx examples from this run, not hand-written.

Run: python3 error_analysis/build_report.py
"""
import os
import re
import sys
import json
import html
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from error_analysis import common, sql_struct

DIFFS = [("simple", "Simple"), ("moderate", "Moderate"), ("challenging", "Challenging")]

# Coarse buckets shown in the report — id -> (label, one-line description).
# The fine-grained heuristics in classify() are mapped onto these via FINE_TO_COARSE.
CATS = [
    ("value",       "Value / literal",           "Structurally right — the bug is a literal, value, case or format (date format, string case, a constant)."),
    ("projection",  "Projection / output shape", "Wrong output — wrong/missing/extra columns, <code>SELECT *</code>, <code>||</code> concatenation, or a <code>DISTINCT</code> mismatch."),
    ("filter",      "Filtering · WHERE",         "Wrong filter logic — extra/missing predicate, wrong comparison, or a strict/inclusive boundary operator."),
    ("tables",      "Tables / joins",            "Queried or joined a different set of base tables than gold."),
    ("structure",   "Query structure",           "Different nesting or aggregation — subquery, aggregate construction, or counting granularity."),
    ("unparseable", "Unparseable prediction",    "The predicted SQL did not parse."),
    ("other",       "Other structural difference", "Diverges across several clauses with no single dominant cause — inspect the pair."),
]
CAT_ORDER = {c[0]: i for i, c in enumerate(CATS)}

# Map the fine-grained classify() result onto a coarse bucket.
FINE_TO_COARSE = {
    "value_only": "value",
    "concat": "projection", "star": "projection", "projection": "projection", "distinct": "projection",
    "where": "filter", "boundary": "filter",
    "table_diff": "tables",
    "subquery": "structure", "aggregation": "structure", "granularity": "structure",
    "unparseable": "unparseable",
    "other": "other",
}


def classify(pred, gold, diffs, p_only, g_only):
    psql = pred["sql"]
    if pred.get("parse_error") or not psql.strip():
        return "unparseable"
    if not diffs:
        return "value_only"
    if "DPipe" in p_only or "DPipe" in g_only:
        return "concat"
    star_re = re.compile(r"select\s+(distinct\s+)?[\w`]*\.?\*", re.I)
    if bool(star_re.search(psql)) != bool(star_re.search(gold["sql"])):
        return "star"
    cd = re.compile(r"count\s*\(\s*distinct", re.I)
    cs = re.compile(r"count\s*\(\s*\*", re.I)
    if (cd.search(psql) and cs.search(gold["sql"])) or (cs.search(psql) and cd.search(gold["sql"])):
        return "granularity"
    strict = (p_only.get("LT", 0) + p_only.get("GT", 0)) and (g_only.get("LTE", 0) + g_only.get("GTE", 0))
    strict_rev = (g_only.get("LT", 0) + g_only.get("GT", 0)) and (p_only.get("LTE", 0) + p_only.get("GTE", 0))
    if strict or strict_rev:
        return "boundary"
    if set(diffs) <= {"SELECT", "DISTINCT"}:
        return "projection"
    if "FROM" in diffs:
        return "table_diff"
    if "SUBQUERY" in diffs:
        return "subquery"
    if "AGGREGATION" in diffs:
        return "aggregation"
    if "DISTINCT" in diffs:
        return "distinct"
    if "WHERE" in diffs:
        return "where"
    return "other"


def chips(counter, n=5):
    items = counter.most_common(n)
    if not items:
        return '<span class="sub">none</span>'
    return '<div class="chips">' + "".join(f'<span class="cc">{html.escape(k)}×{v}</span>' for k, v in items) + "</div>"


def _sem(label, cls, text, mono_block=False):
    """One RA/BNF row: label chip + LLM-derived text (— if missing)."""
    val = html.escape(text.strip()) if isinstance(text, str) and text.strip() else "—"
    tag = "pre" if mono_block else "code"
    return f'<div class="semrow"><span class="semlab {cls}">{label}</span><{tag} class="semval">{val}</{tag}></div>'


def case_html(idx, ev, pred, gold, diffs, p_only, g_only):
    q = html.escape(ev["question"])
    psql = html.escape(pred["sql"])
    gsql = html.escape(gold["sql"])
    tags = ", ".join(diffs) if diffs else "value-only"
    sem = (
        _sem("RA · pred", "p", pred.get("relational_algebra")) +
        _sem("RA · gold", "g", gold.get("relational_algebra")) +
        _sem("BNF · pred", "p", pred.get("bnf_derivation"), mono_block=True) +
        _sem("BNF · gold", "g", gold.get("bnf_derivation"), mono_block=True)
    )
    return f"""    <div class="case">
      <div class="chd"><span class="id">idx {idx}</span><span class="dot">{html.escape(ev['db_id'])}</span>
        <span class="tags">{html.escape(tags)}</span></div>
      <div class="q">“{q}”</div>
      <div class="side p"><div class="lab">Pred · wrong</div><pre>{psql}</pre></div>
      <div class="side g"><div class="lab">Gold</div><pre>{gsql}</pre></div>
      <div class="astrow"><span class="lbl">AST Δ</span>
        <span class="apg">pred</span>{chips(p_only,4)}<span class="apg">gold</span>{chips(g_only,4)}</div>
      <details class="sem"><summary>Relational algebra &amp; BNF derivation</summary>
        {sem}
      </details>
    </div>
"""


def categorize_failures(w, g):
    """idx -> {diffs, p_only, g_only, cat} for every failed prediction in w/g.
    Shared by build_report.py (renders cases) and 07_synthesize_insights.py
    (picks representative examples) so the classification logic lives in one place.
    """
    out = {}
    for idx, pr in w.items():
        gd = g[idx]
        diffs = sql_struct.diff_categories(pr["fingerprint"], gd["fingerprint"]) if not pr.get("parse_error") else []
        p_only = Counter(pr["productions"]) - Counter(gd["productions"])
        g_only = Counter(gd["productions"]) - Counter(pr["productions"])
        cat = FINE_TO_COARSE[classify(pr, gd, diffs, p_only, g_only)]
        out[idx] = {"diffs": diffs, "p_only": p_only, "g_only": g_only, "cat": cat}
    return out


def load_insights():
    path = os.path.join(common.OUT_DIR, "insights.json")
    if not os.path.exists(path):
        return None
    return json.load(open(path))


def clause_bars_html(clause_pct, n=7):
    items = sorted(clause_pct.items(), key=lambda kv: -kv[1])[:n]
    rows = []
    for name, pct in items:
        rows.append(
            f'      <li><span class="bn">{html.escape(name)}</span>'
            f'<span class="bar"><i style="width:{min(pct,100):.0f}%"></i></span>'
            f'<span class="bp">{pct:.1f}%</span></li>'
        )
    return "\n".join(rows)


def bullets_html(bullets):
    return "\n".join(f"      <li>{html.escape(b)}</li>" for b in bullets)


def main():
    w = {x["idx"]: x for x in common.read_jsonl(os.path.join(common.OUT_DIR, "wrong_pred_analysis.jsonl"))}
    g = {x["idx"]: x for x in common.read_jsonl(os.path.join(common.OUT_DIR, "gold_analysis.jsonl"))}
    ev = {x["idx"]: x for x in common.read_jsonl(os.path.join(common.OUT_DIR, "eval_results.jsonl"))}
    insights = load_insights()

    n_total_diff = Counter(r["difficulty"] for r in ev.values())
    cats = categorize_failures(w, g)

    # bucket[difficulty][category] = list of case html
    bucket = {d: {} for d, _ in DIFFS}
    counts = {d: 0 for d, _ in DIFFS}
    for idx, pr in w.items():
        gd = g[idx]
        c = cats[idx]
        diffs, p_only, g_only, cat = c["diffs"], c["p_only"], c["g_only"], c["cat"]
        d = ev[idx]["difficulty"]
        bucket[d].setdefault(cat, []).append((idx, case_html(idx, ev[idx], pr, gd, diffs, p_only, g_only)))
        counts[d] += 1

    panes = []
    for d, _ in DIFFS:
        # Error categories for this difficulty, most frequent first (drives both rank + sections).
        ranked = sorted(bucket[d].items(), key=lambda kv: (-len(kv[1]), CAT_ORDER[kv[0]]))
        total = counts[d] or 1
        ranks = []
        for i, (cat, cases) in enumerate(ranked, 1):
            label = next(c[1] for c in CATS if c[0] == cat)
            pct = 100 * len(cases) / total
            ranks.append(
                f'    <div class="rankitem"><span class="rk">{i}</span>'
                f'<div class="rkbody"><div class="rkname">{label}</div>'
                f'<div class="rksub">{len(cases)} · {pct:.0f}%</div></div></div>'
            )
        rankblock = f'  <div class="rankgrid">\n' + "\n".join(ranks) + "\n  </div>" if ranks else ""

        sections = []
        for cat, cases in ranked:
            label, desc = next(c[1:] for c in CATS if c[0] == cat)
            cases.sort(key=lambda t: t[0])
            body = "".join(c for _, c in cases)
            sections.append(
                f'  <div class="catsec"><div class="cathd"><span class="catname">{label}</span>'
                f'<span class="catn">{len(cases)}</span></div>'
                f'<p class="catdesc">{desc}</p>\n<div class="casegrid">\n{body}</div></div>'
            )
        panes.append(f'<div class="pane" id="p-{d[0]}">\n' + rankblock + "\n" + "\n".join(sections) + "\n</div>")

    tabbar = "".join(
        f'<label class="tablab" for="t-{d[0]}">{lbl} <span class="ct">{counts[d]}</span></label>'
        for d, lbl in DIFFS
    )

    n_total = len(ev)
    n_failed = len(w)
    ex_overall = 100 * (n_total - n_failed) / n_total
    ex_by_diff = {
        d: 100 * (n_total_diff[d] - counts[d]) / n_total_diff[d] if n_total_diff[d] else 0.0
        for d, _ in DIFFS
    }

    if insights:
        ra_bullets = bullets_html(insights.get("ra_bullets", []))
        bnf_bullets = bullets_html(insights.get("bnf_bullets", []))
        root_cause = html.escape(insights.get("root_cause", ""))
        clause_bars = clause_bars_html(insights.get("clause_pct", {}))
    else:
        ra_bullets = bnf_bullets = '      <li class="sub">Run 07_synthesize_insights.py to populate this.</li>'
        root_cause = "Run <code>07_synthesize_insights.py</code> to populate a data-grounded root-cause summary."
        clause_bars = '      <li class="sub">No clause data — run 05_compare_report.py first.</li>'

    htmldoc = TEMPLATE.format(
        tabbar=tabbar,
        panes="\n".join(panes),
        n_simple=counts["simple"], n_mod=counts["moderate"], n_hard=counts["challenging"],
        n_total=n_total, n_failed=n_failed, ex_overall=ex_overall,
        ex_simple=ex_by_diff["simple"], ex_mod=ex_by_diff["moderate"], ex_hard=ex_by_diff["challenging"],
        q_simple=n_total_diff["simple"], q_mod=n_total_diff["moderate"], q_hard=n_total_diff["challenging"],
        ra_bullets=ra_bullets, bnf_bullets=bnf_bullets, root_cause=root_cause, clause_bars=clause_bars,
    )
    out = os.path.join(common.OUT_DIR, "..", "report.html")
    out = os.path.abspath(out)
    with open(out, "w") as f:
        f.write(htmldoc)
    print(f"Wrote {out}")
    for d, lbl in DIFFS:
        line = ", ".join(f"{cat}:{len(cs)}" for cat, cs in sorted(bucket[d].items(), key=lambda kv: -len(kv[1])))
        print(f"  {lbl} ({counts[d]}): {line}")


TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GPT-5.2 Text-to-SQL Failure Gallery — BIRD Full Dev</title>
<style>
  :root{{--bg:#f6f7f9;--panel:#fff;--soft:#eef1f6;--line:#e4e8f0;--ink:#19202e;--mut:#646f85;
    --acc:#2f6fe0;--acc-soft:#eaf1fe;--pred:#c2410c;--pred-soft:#fdf1ec;--pred-line:#f3d4c4;
    --gold:#15803d;--gold-soft:#eef8f1;--gold-line:#c8e6d2;--warn:#9a6700;--warn-soft:#fff8e6;--warn-line:#f0dba6;
    --mono:"SF Mono",ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace;}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased;overflow-x:hidden;}}
  .wrap{{max-width:1180px;margin:0 auto;padding:52px 24px 110px;}}
  .tag{{display:inline-block;font:600 11px/1 var(--mono);letter-spacing:.14em;color:var(--acc);text-transform:uppercase;padding:6px 11px;background:var(--acc-soft);border-radius:999px;margin-bottom:20px;}}
  h1{{font-size:32px;line-height:1.16;margin:0 0 14px;letter-spacing:-.025em;font-weight:750;}}
  .lead{{font-size:16px;color:#39435a;max-width:74ch;}}
  .meta{{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px;}}
  .chip{{font:13px/1 var(--mono);color:var(--mut);background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:8px 11px;}}
  .chip b{{color:var(--ink);}}
  h2{{font-size:13px;margin:50px 0 4px;letter-spacing:.08em;text-transform:uppercase;color:var(--acc);font-weight:700;}}
  .h2sub{{font-size:23px;font-weight:700;letter-spacing:-.02em;margin:0 0 18px;}}
  .grid{{display:grid;gap:14px;grid-template-columns:repeat(4,1fr);margin:8px 0 24px;}}
  .card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;box-shadow:0 1px 2px rgba(20,30,60,.04);}}
  .card .k{{font:600 11px/1 var(--mono);color:var(--mut);letter-spacing:.07em;text-transform:uppercase;}}
  .card .v{{font-size:32px;font-weight:760;margin-top:9px;letter-spacing:-.02em;}}
  .card .v small{{font-size:14px;color:var(--mut);font-weight:500;}}
  .card .sub{{color:var(--mut);font-size:12.5px;margin-top:4px;}}
  .tabin{{position:absolute;opacity:0;pointer-events:none;}}
  .tabbar{{display:flex;gap:8px;margin:6px 0 22px;flex-wrap:wrap;position:sticky;top:0;background:var(--bg);padding:10px 0;z-index:5;}}
  .tablab{{cursor:pointer;font:600 13.5px/1 -apple-system,sans-serif;padding:11px 16px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--mut);display:flex;align-items:center;gap:8px;transition:.15s;user-select:none;}}
  .tablab .ct{{font:700 11px/1 var(--mono);background:var(--soft);color:var(--mut);padding:3px 6px;border-radius:5px;}}
  .tablab:hover{{border-color:#cdd6e6;}}
  #t-s:checked~.tabbar label[for=t-s],#t-m:checked~.tabbar label[for=t-m],#t-c:checked~.tabbar label[for=t-c]{{background:var(--ink);color:#fff;border-color:var(--ink);}}
  #t-s:checked~.tabbar label[for=t-s] .ct,#t-m:checked~.tabbar label[for=t-m] .ct,#t-c:checked~.tabbar label[for=t-c] .ct{{background:rgba(255,255,255,.18);color:#fff;}}
  .pane{{display:none;}}
  #t-s:checked~.panes #p-s,#t-m:checked~.panes #p-m,#t-c:checked~.panes #p-c{{display:block;}}
  .rankgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:4px 0 30px;}}
  .rankitem{{display:flex;align-items:center;gap:12px;background:var(--panel);border:1px solid var(--line);
    border-radius:12px;padding:13px 16px;box-shadow:0 1px 2px rgba(20,30,60,.04);}}
  .rankitem .rk{{font:760 16px/1 var(--mono);color:var(--acc);background:var(--acc-soft);
    width:34px;height:34px;border-radius:9px;display:flex;align-items:center;justify-content:center;flex:none;}}
  .rankitem .rkname{{font-size:14px;font-weight:650;letter-spacing:-.01em;}}
  .rankitem .rksub{{font:600 11px/1 var(--mono);color:var(--mut);margin-top:4px;}}
  @media(max-width:680px){{.rankgrid{{grid-template-columns:1fr}}}}
  .catsec{{margin:26px 0;}}
  .cathd{{display:flex;align-items:center;gap:10px;margin-bottom:2px;}}
  .catname{{font-size:18px;font-weight:700;letter-spacing:-.01em;}}
  .catn{{font:700 11px/1 var(--mono);background:var(--acc-soft);color:var(--acc);padding:4px 8px;border-radius:6px;}}
  .catdesc{{margin:0 0 14px;color:var(--mut);font-size:13.5px;}}
  .casegrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;}}
  .case{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;min-width:0;
    box-shadow:0 1px 2px rgba(20,30,60,.03);min-height:430px;display:flex;flex-direction:column;transition:box-shadow .15s,border-color .15s,transform .15s;}}
  .case .side{{max-height:200px;}}
  .case:hover{{box-shadow:0 8px 24px rgba(20,30,60,.10);border-color:#d2dbea;transform:translateY(-2px);}}
  .chd{{display:flex;align-items:center;gap:8px;margin-bottom:9px;flex:none;}}
  .chd .id{{font:700 12px/1 var(--mono);background:var(--ink);color:#fff;padding:5px 8px;border-radius:6px;flex:none;}}
  .chd .dot{{font:12px/1 var(--mono);color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
  .chd .tags{{margin-left:auto;font:600 10px/1 var(--mono);color:var(--pred);background:var(--pred-soft);border:1px solid var(--pred-line);padding:4px 8px;border-radius:6px;letter-spacing:.02em;flex:none;max-width:55%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
  .q{{font-style:italic;color:#2b3445;margin:0 0 11px;font-size:12.5px;line-height:1.45;flex:none;
    display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}}
  .side{{border:1px solid var(--line);border-radius:9px;overflow:hidden;margin-bottom:9px;
    flex:1 1 0;display:flex;flex-direction:column;min-height:0;}}
  .side .lab{{font:700 10px/1 var(--mono);letter-spacing:.05em;text-transform:uppercase;padding:7px 10px;flex:none;}}
  .side.p .lab{{background:var(--pred-soft);color:var(--pred);border-bottom:1px solid var(--pred-line);}}
  .side.g .lab{{background:var(--gold-soft);color:var(--gold);border-bottom:1px solid var(--gold-line);}}
  pre{{margin:0;padding:10px;flex:1 1 0;min-height:0;min-width:0;overflow-x:hidden;overflow-y:auto;font:11.5px/1.55 var(--mono);color:#2b3242;background:#fbfcfe;white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;}}
  .astrow{{display:flex;align-items:center;flex-wrap:wrap;gap:5px;margin-top:2px;padding-top:9px;border-top:1px dashed var(--line);flex:none;max-height:46px;overflow:hidden;}}
  .astrow .apg{{font:700 9px/1 var(--mono);letter-spacing:.04em;text-transform:uppercase;color:var(--mut);margin-left:4px;}}
  .lbl{{font:700 9px/1.4 var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--mut);}}
  .chips{{display:inline-flex;flex-wrap:wrap;gap:4px;}}
  .cc{{font:600 9.5px/1 var(--mono);padding:3px 6px;border-radius:5px;background:var(--soft);color:#4a5570;}}
  .sub{{color:var(--mut);font-size:12.5px;}}
  .sem{{margin-top:10px;padding-top:9px;border-top:1px dashed var(--line);flex:none;}}
  .sem summary{{cursor:pointer;font:700 10px/1 var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--acc);list-style:none;}}
  .sem summary::-webkit-details-marker{{display:none;}}
  .sem summary::before{{content:"▸ ";color:var(--mut);}}
  .sem[open] summary::before{{content:"▾ ";}}
  .semrow{{margin-top:8px;}}
  .semlab{{display:inline-block;font:700 9px/1 var(--mono);letter-spacing:.04em;text-transform:uppercase;padding:3px 6px;border-radius:5px;margin-bottom:4px;}}
  .semlab.p{{background:var(--pred-soft);color:var(--pred);border:1px solid var(--pred-line);}}
  .semlab.g{{background:var(--gold-soft);color:var(--gold);border:1px solid var(--gold-line);}}
  .semval{{display:block;margin:0;font:11px/1.5 var(--mono);color:#2b3242;background:#fbfcfe;border:1px solid var(--line);
    border-radius:7px;padding:8px 10px;white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;}}
  .lensgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:18px 0 8px;}}
  .lens{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 20px;box-shadow:0 1px 2px rgba(20,30,60,.04);}}
  .lens p{{font-size:13.5px;color:#39435a;margin:0 0 12px;}}
  .lens .sub{{font-size:12px;}}
  .lenshd{{display:flex;align-items:center;gap:9px;font-size:15px;font-weight:700;letter-spacing:-.01em;margin-bottom:12px;}}
  .lenstag{{font:700 10px/1 var(--mono);letter-spacing:.05em;text-transform:uppercase;padding:5px 8px;border-radius:6px;}}
  .lenstag.ast{{background:var(--acc-soft);color:var(--acc);}}
  .lenstag.ra{{background:var(--gold-soft);color:var(--gold);}}
  .lenstag.bnf{{background:var(--pred-soft);color:var(--pred);}}
  .rankbars{{list-style:none;margin:0 0 10px;padding:0;}}
  .rankbars li{{display:flex;align-items:center;gap:9px;margin:7px 0;}}
  .rankbars .bn{{font:600 10.5px/1 var(--mono);color:#4a5570;width:88px;flex:none;}}
  .rankbars .bar{{flex:1 1 0;height:8px;background:var(--soft);border-radius:5px;overflow:hidden;}}
  .rankbars .bar i{{display:block;height:100%;background:linear-gradient(90deg,var(--acc),#5b8def);border-radius:5px;}}
  .rankbars .bp{{font:700 10.5px/1 var(--mono);color:var(--mut);width:42px;text-align:right;flex:none;}}
  .reasons{{margin:0;padding-left:18px;font-size:13px;color:#39435a;}}
  .reasons li{{margin:9px 0;line-height:1.5;}}
  .reasons .cc{{margin-right:5px;}}
  @media(max-width:900px){{.lensgrid{{grid-template-columns:1fr}}}}
  .caveat{{background:var(--warn-soft);border:1px solid var(--warn-line);border-left:3px solid var(--warn);border-radius:10px;padding:16px 20px;margin:24px 0;}}
  .caveat b{{color:var(--warn);}}
  code{{font-family:var(--mono);background:var(--soft);padding:1px 6px;border-radius:5px;font-size:12.5px;}}
  footer{{margin-top:60px;padding-top:24px;border-top:1px solid var(--line);color:var(--mut);font-size:13px;}}
  @media(max-width:1000px){{.casegrid{{grid-template-columns:repeat(2,1fr)}}}}
  @media(max-width:680px){{.grid{{grid-template-columns:repeat(2,1fr)}}.casegrid{{grid-template-columns:1fr}}.case{{height:auto;max-height:520px}}}}
</style></head><body><div class="wrap">

<header>
  <span class="tag">BIRD Full Dev · Text-to-SQL Error Analysis</span>
  <h1>GPT-5.2 failure gallery — every wrong query, grouped by cause</h1>
  <p class="lead">All {n_failed} failures from {n_total} BIRD dev questions (with-knowledge run). Pick a difficulty tab, then expand
  any case to see the wrong prediction beside the gold query and the AST-node difference. Cases are
  auto-grouped by error category.</p>
  <div class="meta">
    <span class="chip">Model <b>gpt-5.2-chat-latest</b></span>
    <span class="chip">via <b>AIML API</b></span>
    <span class="chip">EX <b>{ex_overall:.2f}%</b></span>
    <span class="chip"><b>{n_failed}</b> / {n_total} failures</span>
  </div>
</header>

<h2>Result</h2><div class="h2sub">Accuracy by difficulty</div>
<div class="grid">
  <div class="card"><div class="k">Simple</div><div class="v">{ex_simple:.1f}<small>%</small></div><div class="sub">{q_simple} q · {n_simple} wrong</div></div>
  <div class="card"><div class="k">Moderate</div><div class="v">{ex_mod:.1f}<small>%</small></div><div class="sub">{q_mod} q · {n_mod} wrong</div></div>
  <div class="card"><div class="k">Challenging</div><div class="v">{ex_hard:.1f}<small>%</small></div><div class="sub">{q_hard} q · {n_hard} wrong</div></div>
  <div class="card"><div class="k">Overall EX</div><div class="v">{ex_overall:.1f}<small>%</small></div><div class="sub">{n_total} q · {n_failed} wrong</div></div>
</div>

<h2>Why these queries fail</h2><div class="h2sub">Read through three lenses — AST · RA · BNF</div>
<p class="lead">The three structural views answer three different questions: the <b>AST clause-fingerprint</b>
says <i>which clause</i> breaks, the <b>relational algebra</b> says <i>what diverged semantically</i>,
and the <b>BNF derivation</b> says <i>which grammar production</i> the model over- or under-expanded.</p>

<div class="lensgrid">
  <div class="lens">
    <div class="lenshd"><span class="lenstag ast">AST · clause</span> Where it breaks</div>
    <p>Share of the {n_failed} failures whose clause-level fingerprint differs from gold in this
    clause (a question can differ in several clauses, so this is not a partition):</p>
    <ul class="rankbars">
{clause_bars}
    </ul>
  </div>

  <div class="lens">
    <div class="lenshd"><span class="lenstag ra">RA · semantic</span> What diverged</div>
    <p>Side-by-side relational algebra over real failing cases from this run:</p>
    <ul class="reasons">
{ra_bullets}
    </ul>
  </div>

  <div class="lens">
    <div class="lenshd"><span class="lenstag bnf">BNF · grammar</span> How it errs</div>
    <p>Which grammar productions the model over- or under-expands relative to gold's derivation:</p>
    <ul class="reasons">
{bnf_bullets}
    </ul>
  </div>
</div>

<div class="caveat"><p><b>Root cause.</b> {root_cause}</p></div>

<h2>Failure gallery</h2><div class="h2sub">Click a difficulty, then expand any case</div>
<input class="tabin" type="radio" name="tab" id="t-s" checked>
<input class="tabin" type="radio" name="tab" id="t-m">
<input class="tabin" type="radio" name="tab" id="t-c">
<div class="tabbar">{tabbar}</div>
<div class="panes">
{panes}
</div>

<div class="caveat"><p><b>Categories are auto-classified.</b> Each case is bucketed by deterministic
heuristics over the predicted-vs-gold structural diff (clause fingerprint + AST node difference).
They flag the <i>most likely</i> cause; BIRD gold's terse house style means a single value bug can
still light up several clauses.</p></div>

<footer>Generated by <code>error_analysis/build_report.py</code> from <code>outputs/</code> ·
GPT-5.2 via AIML API · EX {ex_overall:.2f}% over {n_total} BIRD dev SQLite questions · {n_failed} failures.</footer>
</div></body></html>"""


if __name__ == "__main__":
    main()
