# -*- coding: utf-8 -*-
"""La file d'attente de toutes les demandes (celles de la base comme celles des chapitres).

Une demande ne part que si la place est libre : pas plus de claude.file.simultanees demandes en même
temps (1 par défaut). Sinon elle passe « en_attente », dans l'ordre d'arrivée, avec de quoi la lancer
plus tard (son « départ » : le module et la fonction qui la font tourner). Quand une demande finit :
  · la suivante d'une SÉRIE part d'elle-même (lancer une série vaut accord) ;
  · les autres partent d'elles-mêmes si l'enchaînement est activé (claude.file.auto), sinon elles
    attendent le ▶ de l'auteur.
« Lancer maintenant » force le départ, en parallèle de ce qui tourne. Une demande en attente survit
à un redémarrage ; on peut la retirer tant qu'elle n'est pas partie. L'assistant (les conversations)
et la lecture de confiance d'une fiche restent hors de la file : ce sont des échanges courts.

Le contexte d'une création de fiche, d'une vérification de référence, d'une recherche de texte
original et d'une rédaction est compilé à son départ, pas à sa mise en file : elle voit ce qui a
été créé entre-temps.
"""
import json
import time
import asyncio
import importlib

from . import livre, reecriture

SLUG_KB = "_kb"


def reglage():
    f = (livre.meta().get("claude") or {}).get("file") or {}
    from . import filiation
    return dict({"auto": bool(f.get("auto", False)), "simultanees": max(1, int(f.get("simultanees", 1) or 1)),
                 "creer_d_office": bool(f.get("creer_d_office", False))}, **filiation.reglage())


def _toutes():
    """[(slug, demande)] : la base, puis les chapitres."""
    out = []
    d = livre.LIVRE / "kb" / "demandes"
    if d.exists():
        out += [(SLUG_KB, json.loads(p.read_text(encoding="utf-8"))) for p in d.glob("*.json")]
    c = livre.LIVRE / "chapters"
    if c.exists():
        out += [(p.parent.parent.name, json.loads(p.read_text(encoding="utf-8"))) for p in c.glob("*/demandes/*.json")]
    return out


def _trouve(ident):
    for s, d in _toutes():
        if d.get("id") == ident:
            return s, d
    raise KeyError(ident)


def etat():
    T = _toutes()
    attente = sorted(((s, x) for s, x in T if x.get("etat") == "en_attente"),
                     key=lambda sx: (sx[1].get("rang") or 0, sx[1].get("cree") or ""))
    return {"reglage": reglage(),
            "en_cours": [x["id"] for s, x in T if x.get("etat") == "en_cours"],
            "en_attente": [{"id": x["id"], "slug": s, "type": x.get("type"), "titre": x.get("titre"), "cree": x.get("cree"),
                            "question": (x.get("cible") or {}).get("question"), "serie": x.get("serie"), "rang": i + 1}
                           for i, (s, x) in enumerate(attente)]}


def _occupes(sauf=None):
    return sum(1 for s, x in _toutes() if x.get("etat") == "en_cours" and x.get("id") != sauf)


def _tache(depart, slug=None, ident=None):
    mod = importlib.import_module("." + depart["module"], __package__)
    r = getattr(mod, depart["fonction"])(*depart.get("args") or [])
    if asyncio.iscoroutine(r):
        t = reecriture.tache(r)
        if ident:
            t.add_done_callback(lambda t: _echec(slug, ident, t))
    return r


def _demarre(slug, ident, depart):
    """Le départ ; s'il échoue tout de suite, la demande passe en erreur (et l'erreur remonte)."""
    try:
        _tache(depart, slug, ident)
    except Exception as e:                       # noqa: BLE001
        d = reecriture.lit(slug, ident)
        d.update(etat="erreur", erreur="échec au départ — %s: %s" % (type(e).__name__, e))
        reecriture._ecrit(slug, d)
        raise


def _echec(slug, ident, t):
    """Une tâche morte d'une exception hors de reecriture._lance (avant l'appel à Claude) laissait sa
    demande « en cours » pour toujours : elle passe en erreur, avec l'exception."""
    if t.cancelled() or t.exception() is None:
        return
    try:
        d = reecriture.lit(slug, ident)
    except KeyError:
        return
    if d.get("etat") == "en_cours":
        e = t.exception()
        d.update(etat="erreur", erreur="échec au départ — %s: %s" % (type(e).__name__, e))
        reecriture._ecrit(slug, d)
        reecriture._actives.discard(ident)
        suivante()


def part(slug, d, module, fonction, *args, forcer=False):
    """Le seul départ des demandes : tout de suite si la place est libre (ou si c'est forcé), sinon en
    file. Rend la demande."""
    d["depart"] = {"module": module, "fonction": fonction, "args": list(args)}
    if not forcer and _occupes(sauf=d["id"]) >= reglage()["simultanees"]:
        d.update(etat="en_attente", en_file=livre._maintenant(), rang=d.get("rang") or time.time())
        reecriture._ecrit(slug, d)
        return d
    d.update(etat="en_cours", lancee=livre._maintenant())
    reecriture._ecrit(slug, d)
    _demarre(slug, d["id"], d["depart"])
    return reecriture.lit(slug, d["id"])


# les demandes mises en file avant le départ générique (fiche, référence, texte original, rédaction)
ANCIENS = {"fiche": "creation", "reference": "references", "document": "documents", "redaction": "redaction"}


def lance(ident):
    """Lancer une demande en attente, maintenant (en parallèle de ce qui tourne)."""
    slug, d = _trouve(ident)
    if d.get("etat") != "en_attente":
        raise reecriture.Conflit("la demande n'est pas en attente (%s)" % d.get("etat"))
    if d.get("type") == "fiche" and reglage()["creer_d_office"]:
        d["creer_d_office"] = True                 # la fiche sera écrite dès la réponse, « à confirmer »
    depart = d.get("depart") or ({"module": ANCIENS[d.get("type")], "fonction": "demarre", "args": [ident]}
                                 if d.get("type") in ANCIENS else None)
    if not depart:
        raise ValueError("demande sans départ connu : %s" % d.get("type"))
    d.update(etat="en_cours", depart=depart, lancee=livre._maintenant())
    d.pop("en_file", None)
    reecriture._ecrit(slug, d)
    _demarre(slug, ident, depart)
    return reecriture.lit(slug, ident)


def retire(ident):
    slug, d = _trouve(ident)
    if d.get("etat") != "en_attente":
        raise reecriture.Conflit("seule une demande en attente se retire (%s)" % d.get("etat"))
    d.update(etat="retiree", retiree=livre._maintenant())
    reecriture._ecrit(slug, d)
    return d


def suivante():
    """S'il reste de la place : lancer la plus ancienne en attente — celle d'une série toujours, les
    autres seulement si l'enchaînement est activé."""
    r = reglage()
    lancees = []
    while _occupes() < r["simultanees"]:
        cand = [x for x in etat()["en_attente"] if r["auto"] or x.get("serie")]
        if not cand:
            break
        lancees.append(lance(cand[0]["id"]))
    return lancees[0] if lancees else None
