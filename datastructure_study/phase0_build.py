#!/usr/bin/env python3
"""M1: build FK join graph + column profile + (enum) value index per DB.
Pure local, zero token. Writes structures/<db>.json."""
import sqlite3, json, os
from collections import deque, defaultdict

DBR = os.path.join(os.path.dirname(__file__), "..", "llm", "data", "dev_databases")
OUT = os.path.join(os.path.dirname(__file__), "structures")
DBS = ["california_schools", "financial", "toxicology"]
ENUM_MAX = 20


def build(db):
    path = os.path.join(DBR, db, db + ".sqlite")
    con = sqlite3.connect(path); cur = con.cursor()
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name<>'sqlite_sequence'")]

    # --- FK graph ---
    adj = defaultdict(list); fks = []
    for t in tables:
        for r in cur.execute(f"PRAGMA foreign_key_list('{t}')"):
            # (id, seq, table, from, to, on_update, on_delete, match)
            ref = r[2]; frm = r[3]; to = r[4]
            adj[t].append((ref, frm, to)); adj[ref].append((t, to, frm))
            fks.append({"from": f"{t}.{frm}", "to": f"{ref}.{to}"})

    def shortest_path(a, b):
        if a == b: return [a]
        seen = {a}; q = deque([[a]])
        while q:
            p = q.popleft()
            for (nb, _f, _t) in adj[p[-1]]:
                if nb in seen: continue
                if nb == b: return p + [nb]
                seen.add(nb); q.append(p + [nb])
        return None

    # all-pairs join paths (small schemas)
    paths = {}
    for i, a in enumerate(tables):
        for b in tables[i + 1:]:
            sp = shortest_path(a, b)
            if sp: paths[f"{a}|{b}"] = sp

    # --- column profile + enum value index ---
    profile = {}; value_index = defaultdict(list); cols_by_table = {}
    q = con.cursor()
    for t in tables:
        cols = cur.execute(f"PRAGMA table_info('{t}')").fetchall()
        cols_by_table[t] = [c[1] for c in cols]
        for c in cols:
            cid, name, ctype, notnull, dflt, pk = c
            key = f"{t}.{name}"
            try:
                nd = q.execute(f'SELECT COUNT(DISTINCT "{name}") FROM "{t}"').fetchone()[0]
            except Exception:
                nd = None
            enum = None
            if nd is not None and 0 < nd <= ENUM_MAX:
                enum = [r[0] for r in q.execute(
                    f'SELECT DISTINCT "{name}" FROM "{t}" WHERE "{name}" IS NOT NULL LIMIT {ENUM_MAX}').fetchall()]
                for v in enum:
                    value_index[str(v).lower()].append(key)
            profile[key] = {"type": ctype, "pk": bool(pk),
                            "ndistinct": nd, "enum": enum}

    con.close()
    return {"tables": tables, "columns_by_table": cols_by_table,
            "fks": fks, "join_paths": paths,
            "profile": profile, "value_index": value_index}


def main():
    os.makedirs(OUT, exist_ok=True)
    for db in DBS:
        s = build(db)
        open(os.path.join(OUT, db + ".json"), "w").write(
            json.dumps(s, ensure_ascii=False, indent=1))
        ncols = len(s["profile"]); nenum = sum(1 for v in s["profile"].values() if v["enum"])
        print(f"{db}: {len(s['tables'])} tables, {ncols} cols, {nenum} enum cols, "
              f"{len(s['fks'])} FKs, {len(s['join_paths'])} table-pair paths, "
              f"{len(s['value_index'])} indexed values")


if __name__ == "__main__":
    main()
