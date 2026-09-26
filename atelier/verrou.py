# -*- coding: utf-8 -*-
"""Le verrou, modifiable : texte, statut et note d'une assertion ; ajout ; liens.

Les règles du livre (CLAUDE.md de l'ancien dépôt) :
  · les identifiants sont stables : on ajoute « 5.9a » après « 5.9 », on ne renumérote pas ;
  · une assertion retirée n'est pas effacée : elle reste, statut « retiree », avec son motif et
    sa date ;
  · une correction de texte garde l'ancien texte dans la note, avec la date et le motif.

Les liens : une assertion est portée par des paragraphes du récit (links.yaml) et étayée par
des paragraphes de l'essai (le champ « essai » de l'assertion, dans verrou.yaml).
Chaque changement va au journal (type « verrou ») : les paragraphes qui portent l'assertion
passent ainsi à « cadre modifié » dans l'état de validation.
"""
import io
import json
import hashlib

from ruamel.yaml import YAML

from . import livre

STATUTS = ("obligatoire", "supprimable", "retiree")


class Conflit(Exception):
    pass


def _y():
    return livre.yaml_rt()


def empreinte(slug):
    p = livre.dossier(slug) / "verrou.yaml"
    return hashlib.sha1(p.read_bytes()).hexdigest()[:12] if p.exists() else ""


def _charge(slug, attendue):
    p = livre.dossier(slug) / "verrou.yaml"
    if empreinte(slug) != attendue:
        raise Conflit("verrou.yaml a changé depuis son ouverture")
    return p, _y().load(p.read_text(encoding="utf-8"))


def _ecrit(p, doc):
    p.write_text(livre.rt_texte(_y(), doc), encoding="utf-8")


def _journal(slug, e):
    with (livre.dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(e, type="verrou", date=livre._maintenant()), ensure_ascii=False) + "\n")


def _trouve(doc, ident):
    for s in doc["sections"]:
        for i, a in enumerate(s["assertions"]):
            if str(a["id"]) == ident:
                return s, i, a
    raise KeyError(ident)


def _trace(a, quoi, motif):
    t = "%s le %s%s" % (quoi, livre._maintenant()[:10], " — " + motif if motif else "")
    a["note"] = (str(a.get("note")) + " ; " if a.get("note") else "") + t


def modifie(slug, ident, champs, motif, attendue):
    p, doc = _charge(slug, attendue)
    _, _, a = _trouve(doc, ident)
    motif = (motif or "").strip()
    texte = " ".join((champs.get("texte") or "").split())
    statut = champs.get("statut") or a.get("statut")
    if statut not in STATUTS:
        raise ValueError("statut inconnu : %s" % statut)
    if statut == "retiree" and a.get("statut") != "retiree" and not motif:
        raise ValueError("une assertion retirée garde son motif : le donner")
    if texte and texte != a["texte"]:
        ancien = a["texte"]
        a["texte"] = texte
        _trace(a, "texte modifié (avant « %s »)" % ancien, motif)
        _journal(slug, {"assertion": ident, "champ": "texte", "avant": ancien, "apres": texte, "motif": motif})
    if statut != a.get("statut"):
        avant = a.get("statut")
        a["statut"] = statut
        _trace(a, "retirée" if statut == "retiree" else "passée %s" % statut, motif)
        _journal(slug, {"assertion": ident, "champ": "statut", "avant": avant, "apres": statut, "motif": motif})
    if "note" in champs:                               # la note elle-même, réécrite à la main
        n = " ".join((champs.get("note") or "").split())
        if n != (a.get("note") or ""):
            if n:
                a["note"] = n
            else:
                a.pop("note", None)
    _ecrit(p, doc)
    return {"assertion": ident, "empreinte": empreinte(slug)}


def _suivant(doc, base):
    """« 1.8 » -> « 1.8a » (ou la première lettre libre) ; « 1.8a » -> « 1.8b »."""
    racine = base.rstrip("abcdefghijklmnopqrstuvwxyz")
    pris = {str(a["id"]) for s in doc["sections"] for a in s["assertions"]}
    for c in "abcdefghijklmnopqrstuvwxyz":
        if racine + c not in pris:
            return racine + c
    raise ValueError("plus de suffixe libre après %s" % racine)


def _ancre(slug, doc, bloc=None, plan=None):
    """Après quelle assertion placer une assertion nouvelle, quand on ne le dit pas :
    la dernière que porte le paragraphe ; sinon la dernière des paragraphes qui le précèdent
    dans son plan ; sinon la dernière de la section du plan ; sinon la dernière du verrou."""
    liens = livre.atelier(slug)["links"].get("recit", {})
    if bloc and not plan:
        plan = (liens.get(bloc) or {}).get("plan")
    ordre = [b for b, l in liens.items() if l.get("plan") == plan] if plan else []
    if bloc in ordre:
        ordre = ordre[:ordre.index(bloc) + 1]
    for b in reversed(ordre):
        a = (liens.get(b) or {}).get("assertions") or []
        if a:
            return str(a[-1])
    for s in doc["sections"]:
        if str(s.get("id")) == str(plan) and s["assertions"]:
            return str(s["assertions"][-1]["id"])
    derniere = [a for s in doc["sections"] for a in s["assertions"]]
    if not derniere:
        raise ValueError("verrou vide : pas d'assertion où s'accrocher")
    return str(derniere[-1]["id"])


def ajoute(slug, apres, texte, statut, porte_par, motif, attendue, bloc=None, plan=None):
    texte = " ".join((texte or "").split())
    if not texte:
        raise ValueError("une assertion a un texte")
    if statut not in ("obligatoire", "supprimable"):
        raise ValueError("statut inconnu : %s" % statut)
    p, doc = _charge(slug, attendue)
    if not apres:
        apres = _ancre(slug, doc, bloc, plan)
    s, i, _ = _trouve(doc, apres)
    ident = _suivant(doc, apres)
    nouvelle = {"id": ident, "statut": statut, "texte": texte}
    nouvelle["note"] = "ajoutée le %s%s" % (livre._maintenant()[:10], " — " + motif if motif else "")
    s["assertions"].insert(i + 1, nouvelle)
    _ecrit(p, doc)
    _journal(slug, {"assertion": ident, "champ": "ajout", "apres": texte, "apres_assertion": apres, "motif": motif})
    for b in porte_par or []:
        attache_recit(slug, ident, b)
    return {"assertion": ident, "empreinte": empreinte(slug)}


# ------------------------------------------------------------------ liens

def _links(slug):
    p = livre.dossier(slug) / "links.yaml"
    return p, _y().load(p.read_text(encoding="utf-8"))


def attache_recit(slug, ident, bloc):
    p, doc = _links(slug)
    l = doc.get("recit", {}).get(bloc)
    if l is None:
        raise KeyError(bloc)
    liste = l.setdefault("assertions", [])
    if ident not in [str(x) for x in liste]:
        liste.append(ident)
        l.pop("ajout", None)                     # un paragraphe qui porte une assertion n'est plus un ajout
        _ecrit(p, doc)
        _journal(slug, {"assertion": ident, "champ": "porte_par", "apres": bloc})
    return {"assertion": ident}


def detache_recit(slug, ident, bloc):
    p, doc = _links(slug)
    l = doc.get("recit", {}).get(bloc)
    if l is None:
        raise KeyError(bloc)
    liste = l.get("assertions") or []
    garde = [x for x in liste if str(x) != ident]
    if len(garde) != len(liste):
        if garde:
            l["assertions"] = garde
        else:
            l.pop("assertions", None)
        _ecrit(p, doc)
        _journal(slug, {"assertion": ident, "champ": "porte_par", "avant": bloc})
    return {"assertion": ident}


def attache_essai(slug, ident, bloc, appui, attendue):
    if appui not in ("direct", "partiel"):
        raise ValueError("appui : direct ou partiel")
    p, doc = _charge(slug, attendue)
    _, _, a = _trouve(doc, ident)
    liens = a.setdefault("essai", [])
    deja = next((l for l in liens if l["bloc"] == bloc), None)
    if deja:
        deja["appui"] = appui
    else:
        liens.append({"bloc": bloc, "appui": appui})
    _ecrit(p, doc)
    _journal(slug, {"assertion": ident, "champ": "essai", "apres": {"bloc": bloc, "appui": appui}})
    return {"assertion": ident, "empreinte": empreinte(slug)}


def detache_essai(slug, ident, bloc, attendue):
    p, doc = _charge(slug, attendue)
    _, _, a = _trouve(doc, ident)
    liens = [l for l in a.get("essai") or [] if l["bloc"] != bloc]
    if liens:
        a["essai"] = liens
    else:
        a.pop("essai", None)
    _ecrit(p, doc)
    _journal(slug, {"assertion": ident, "champ": "essai", "avant": bloc})
    return {"assertion": ident, "empreinte": empreinte(slug)}
