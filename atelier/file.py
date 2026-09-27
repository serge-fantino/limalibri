# -*- coding: utf-8 -*-
"""La file d'attente des demandes qui n'appartiennent à aucun chapitre (kb/demandes/).

Une création de fiche retenue depuis « creuser » ne part pas tout de suite : elle est mise
« en_attente ». Par défaut, on la lance à la main (▶). L'enchaînement automatique est une
option, à activer explicitement (livre.yaml, claude.file.auto) : les demandes en attente
partent alors l'une après l'autre (claude.file.simultanees, 1 par défaut), la suivante quand
la précédente a fini. Le contexte d'une demande est compilé à son lancement, pas à sa mise en
file : elle voit les fiches créées entre-temps (et le doublon qu'une voisine vient d'écrire).
Une demande en attente survit à un redémarrage ; on peut la retirer tant qu'elle n'est pas
partie.
"""
import json

from . import livre, reecriture

SLUG_KB = "_kb"


def reglage():
    f = (livre.meta().get("claude") or {}).get("file") or {}
    return {"auto": bool(f.get("auto", False)), "simultanees": max(1, int(f.get("simultanees", 1) or 1)),
            "creer_d_office": bool(f.get("creer_d_office", False))}


def _toutes():
    d = livre.LIVRE / "kb" / "demandes"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))] if d.exists() else []


def etat():
    ds = _toutes()
    attente = sorted((x for x in ds if x.get("etat") == "en_attente"), key=lambda x: (x["cree"], x.get("rang", 0)))
    return {"reglage": reglage(), "en_cours": [x["id"] for x in ds if x.get("etat") == "en_cours"],
            "en_attente": [{"id": x["id"], "type": x["type"], "titre": x.get("titre"), "cree": x["cree"],
                            "question": x["cible"].get("question")} for x in attente]}


def lance(ident):
    """Lancer une demande en attente, maintenant."""
    d = reecriture.lit(SLUG_KB, ident)
    if d.get("etat") != "en_attente":
        raise reecriture.Conflit("la demande n'est pas en attente (%s)" % d.get("etat"))
    if d.get("type") == "fiche":
        from . import creation
        if reglage()["creer_d_office"]:              # la fiche sera écrite dès la réponse, « à confirmer »
            d["creer_d_office"] = True
            reecriture._ecrit(SLUG_KB, d)
        return creation.demarre(ident)
    raise ValueError("type de demande sans file : %s" % d.get("type"))


def retire(ident):
    d = reecriture.lit(SLUG_KB, ident)
    if d.get("etat") != "en_attente":
        raise reecriture.Conflit("seule une demande en attente se retire (%s)" % d.get("etat"))
    d.update(etat="retiree", retiree=livre._maintenant())
    reecriture._ecrit(SLUG_KB, d)
    return d


def suivante():
    """Si l'enchaînement est activé et qu'il reste de la place : lancer la plus ancienne en attente."""
    r = reglage()
    if not r["auto"]:
        return None
    e = etat()
    if len(e["en_cours"]) >= r["simultanees"] or not e["en_attente"]:
        return None
    return lance(e["en_attente"][0]["id"])
