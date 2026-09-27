# -*- coding: utf-8 -*-
"""Reconstitue le journal de consommation (consommation.jsonl) depuis les demandes et les
conversations déjà faites, pour que les statistiques couvrent aussi le travail d'avant le journal.

    poetry run python3 migrer/consommation.py              le livre par défaut (UneVie/book-atelier)
    poetry run python3 migrer/consommation.py --sec        compte, sans écrire
    ATELIER_LIVRE=… poetry run python3 migrer/consommation.py

Une ligne par demande (ou par tour de conversation), marquée « reconstitue » : une demande reprise
ou poursuivie (« chercher encore ») n'a gardé que son cumul — sa ligne a la phase « cumul ». Les
lignes écrites en direct par l'atelier sont gardées telles quelles ; une demande qui en a déjà
n'est pas reconstituée. Rejouer le script remplace les lignes reconstituées, sans doublon.
"""
import os
import sys
import json
import pathlib
import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from atelier import livre, consommation          # noqa: E402


def _date(debut, duree):
    try:
        d = datetime.datetime.fromisoformat(debut)
        return (d + datetime.timedelta(seconds=duree or 0)).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return debut


def _ligne(source, genre, ident, chapitre, phase, debut, ex, web, session, **autres):
    j = ex.get("jetons") or {}
    e = {"date": _date(debut, ex.get("duree_s")), "debut": debut, "duree_s": ex.get("duree_s"),
         "source": source, "genre": genre, "phase": phase, "ident": ident,
         "chapitre": None if chapitre in (None, "_kb") else chapitre,
         "modele": ex.get("modele"), "modele_choisi": None, "issue": "ok", "erreur": None,
         "tours": ex.get("tours"), "web": web,
         "jetons": {k: int(j.get(k) or 0) for k in consommation.CLES}, "cout_usd": ex.get("cout_usd"),
         "par_modele": consommation._par_modele(j.get("par_modele")), "session": session, "reconstitue": True}
    e.update(autres)
    return e


def reconstitue():
    L = []
    base = livre.LIVRE
    demandes = [(p.parent.parent.name, p) for p in base.glob("chapters/*/demandes/*.json")]
    demandes += [("_kb", p) for p in base.glob("kb/demandes/*.json")]
    for slug, p in demandes:
        d = json.loads(p.read_text(encoding="utf-8"))
        ex = d.get("execution")
        if not ex:
            continue
        b = d.get("budget") or {}
        av = b.get("avant") or {}
        web = {k: (b.get(k) or 0) + (av.get(k) or 0) for k in ("recherches", "pages", "refus")}
        cumul = ex.get("reprises") or b.get("encore")
        e = _ligne("demande", d.get("type") or "reecriture", d["id"], slug, "cumul" if cumul else "initiale",
                   d.get("lancee") or d.get("cree"), ex, web, d.get("session_id"))
        if d.get("etat") == "erreur":
            e.update(issue="erreur", erreur=(d.get("erreur") or "")[:300])
        L.append(e)
    for p in base.glob("kb/conversations/*.json"):
        c = json.loads(p.read_text(encoding="utf-8"))
        for n, t in enumerate(c.get("tours") or [], 1):
            ex = t.get("execution")
            if not ex:
                continue
            b = t.get("budget") or {}
            L.append(_ligne("conversation", "conversation", c["id"], None, "tour", t.get("date"), ex,
                            {k: b.get(k) or 0 for k in ("recherches", "pages", "refus")}, c.get("session_id"), tour=n))
    return L


def main():
    sec = "--sec" in sys.argv
    vivantes = [e for e in consommation.lignes() if not e.get("reconstitue")]
    deja = {(e["source"], e["ident"], e.get("tour")) for e in vivantes}
    neuves = [e for e in reconstitue() if (e["source"], e["ident"], e.get("tour")) not in deja]
    tout = sorted(vivantes + neuves, key=lambda e: e.get("date") or "")
    cout = sum(e.get("cout_usd") or 0 for e in neuves)
    print("%s : %d lignes reconstituées (%.2f $), %d écrites en direct gardées" % (
        consommation.fichier(), len(neuves), cout, len(vivantes)))
    if sec:
        return
    consommation.fichier().write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in tout), encoding="utf-8")


if __name__ == "__main__":
    main()
