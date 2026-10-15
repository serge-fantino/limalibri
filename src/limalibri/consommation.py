# -*- coding: utf-8 -*-
"""Le journal de consommation de Claude, attaché au livre : `consommation.jsonl` à sa racine.

Une ligne par exécution de Claude (une demande, sa reprise, un « chercher encore », un tour de
conversation, une lecture de confiance), écrite quand l'exécution finit, jamais réécrite. Chaque
ligne porte ses propres chiffres — pas le cumul d'une demande — pour que les sommes soient justes :

    date, debut, duree_s       fin et début (ISO, heure locale), durée
    source                     demande | conversation | confiance
    genre                      verification, reecriture, fiche, pistes, renvois, reference, naive,
                               document, plan, conversation, confiance
    phase                      initiale | reprise | encore | tour
    ident, chapitre            la demande (ou la conversation), son chapitre (null : la base, le livre)
    modele                     le modèle qui a répondu ; modele_choisi : celui demandé pour cette requête
    issue, erreur              ok | erreur
    tours                      tours de l'agent
    web                        {recherches, pages, refus} de cette exécution
    jetons                     {entree, sortie, cache_cree, cache_lu}
    cout_usd                   au tarif API
    par_modele                 {modele: {entree, sortie, cache_cree, cache_lu, pensee, recherches_web, cout_usd}}
    session                    l'identifiant de session (une reprise garde celle de sa demande)
    reconstitue                vrai pour les lignes refaites après coup depuis les demandes (migrer/)

Le format se lit tel quel : `duckdb -c "select genre, sum(cout_usd) from 'consommation.jsonl' group by 1"`,
ou `pandas.read_json(..., lines=True)`.
"""
import json
import datetime

from . import livre

NOM = "consommation.jsonl"
CLES = ("entree", "sortie", "cache_cree", "cache_lu")


def fichier():
    return livre.LIVRE / NOM


def _par_modele(pm):
    """model_usage du SDK (camelCase) -> nos noms."""
    out = {}
    for nom, u in (pm or {}).items():
        g = lambda *ks: next((u[k] for k in ks if isinstance(u.get(k), (int, float))), 0)   # noqa: E731
        out[nom] = {"entree": g("inputTokens", "input_tokens"), "sortie": g("outputTokens", "output_tokens"),
                    "cache_cree": g("cacheCreationInputTokens", "cache_creation_input_tokens"),
                    "cache_lu": g("cacheReadInputTokens", "cache_read_input_tokens"),
                    "pensee": g("thinkingTokens"), "recherches_web": g("webSearchRequests"),
                    "cout_usd": u.get("costUSD")}
    return out


def note(source, genre, ident, chapitre=None, phase="initiale", debut=None, duree_s=None, modele=None,
         modele_choisi=None, issue="ok", erreur=None, tours=None, web=None, jetons=None, cout_usd=None,
         session=None, **autres):
    """Ajoute une ligne. Ne lève jamais : le journal ne doit pas casser le travail qu'il décrit."""
    try:
        j = jetons or {}
        e = {"date": livre._maintenant(), "debut": debut, "duree_s": duree_s,
             "source": source, "genre": genre, "phase": phase,
             "ident": ident, "chapitre": None if chapitre in (None, "_kb") else chapitre,
             "modele": modele, "modele_choisi": modele_choisi,
             "issue": issue, "erreur": (erreur or "")[:300] or None, "tours": tours,
             "web": web or {"recherches": 0, "pages": 0, "refus": 0},
             "jetons": {k: int(j.get(k) or 0) for k in CLES},
             "cout_usd": cout_usd, "par_modele": _par_modele(j.get("par_modele")),
             "session": session}
        e.update({k: v for k, v in autres.items() if v is not None})
        with fichier().open("a", encoding="utf-8") as f:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    except Exception as x:                             # noqa: BLE001
        print("limalibri : journal de consommation —", x)


def depuis_resultat(resultat):
    """(jetons, cout, tours) d'un ResultMessage, pour cette exécution seule."""
    from . import reecriture
    return reecriture.jetons(resultat), getattr(resultat, "total_cost_usd", None), getattr(resultat, "num_turns", None)


def debut_iso(t0):
    return datetime.datetime.fromtimestamp(t0).astimezone().isoformat(timespec="seconds")


# ------------------------------------------------------------------ lire, compter

def lignes():
    p = fichier()
    if not p.exists():
        return []
    out = []
    for l in p.read_text(encoding="utf-8").splitlines():
        if l.strip():
            try:
                out.append(json.loads(l))
            except ValueError:
                pass
    return out


def _vide():
    return {"n": 0, "erreurs": 0, "cout_usd": 0.0, "duree_s": 0.0, "tours": 0,
            "recherches": 0, "pages": 0, **{k: 0 for k in CLES}}


def _ajoute(a, e):
    a["n"] += 1
    a["erreurs"] += e.get("issue") == "erreur"
    a["cout_usd"] += e.get("cout_usd") or 0
    a["duree_s"] += e.get("duree_s") or 0
    a["tours"] += e.get("tours") or 0
    w = e.get("web") or {}
    a["recherches"] += w.get("recherches") or 0
    a["pages"] += w.get("pages") or 0
    for k in CLES:
        a[k] += (e.get("jetons") or {}).get(k) or 0


def _fin(a):
    total_in = a["entree"] + a["cache_cree"] + a["cache_lu"]
    a["cache_part"] = round(100 * a["cache_lu"] / total_in, 1) if total_in else None
    a["cout_usd"] = round(a["cout_usd"], 4)
    a["duree_s"] = round(a["duree_s"], 1)
    a["cout_moyen"] = round(a["cout_usd"] / a["n"], 4) if a["n"] else None
    return a


def stats(depuis=None, jusqua=None):
    """Totaux et regroupements (genre, modèle, jour, chapitre, source, phase) sur une période
    (dates AAAA-MM-JJ, bornes incluses)."""
    L = [e for e in lignes() if (not depuis or e["date"][:10] >= depuis) and (not jusqua or e["date"][:10] <= jusqua)]
    total = _vide()
    groupes = {g: {} for g in ("genre", "modele", "jour", "chapitre", "source", "phase")}
    for e in L:
        _ajoute(total, e)
        cles = {"genre": e.get("genre"), "modele": e.get("modele") or "?", "jour": e["date"][:10],
                "chapitre": e.get("chapitre") or "(base / livre)", "source": e.get("source"), "phase": e.get("phase")}
        for g, c in cles.items():
            _ajoute(groupes[g].setdefault(c or "?", _vide()), e)
    out = {"fichier": NOM, "lignes": len(L), "premiere": L[0]["date"] if L else None, "derniere": L[-1]["date"] if L else None,
           "reconstituees": sum(1 for e in L if e.get("reconstitue")), "total": _fin(total)}
    for g, D in groupes.items():
        rang = (lambda kv: kv[0]) if g == "jour" else (lambda kv: -kv[1]["cout_usd"])
        out[g] = [dict(_fin(v), cle=k) for k, v in sorted(D.items(), key=rang)]
    return out
