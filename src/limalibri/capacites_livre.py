# -*- coding: utf-8 -*-
"""Les capacités propres à un livre : capacites.yaml, à la racine du livre, compose des primitives de LimaLibri.

Une idée propre à un livre (l'ouverture d'Un Monde : une courte page en tête de chaque chapitre, dans une autre
voix) devient de la configuration du livre, pas du code. Chaque capacité déclarée nomme sa primitive et la règle ;
elle entre au catalogue (capacites.py) comme les autres : la page « Capacités », les séries, les plans d'objectif.

La primitive, pour l'instant :
  plan_de_tete   un plan à part, en tête du storyboard d'un chapitre du récit (brief.yaml, « sorte ») : Claude
                 écrit ses micro-récits et ses paragraphes d'un même geste (narration.py, une demande t-) ; ils se
                 rendent à part (livre.marque_en_tete : italique, un blanc après). Les demandes du storyboard et du
                 récit le gardent tel quel, en tête.

  ouverture:
    libelle: écrire l'ouverture
    quoi: une courte page en tête du chapitre, dans la voix du monde
    primitive: plan_de_tete
    plan: {id: ouverture, titre: Ouverture}
    regle: L'ouverture          # une section de regles/recit.md (son titre ou son identifiant) : la voix
    mots: [250, 350]
    paragraphes: [2, 4]
    consigne: |                 # ce que Claude reçoit en plus de la règle
      …

Une erreur dans le fichier se dit (avertissements), elle ne casse rien : la capacité fautive est écartée.
"""
import re

import yaml

from . import livre

FICHIER = "capacites.yaml"
PRIMITIVES = {
    "plan_de_tete": "un plan à part en tête du storyboard d'un chapitre du récit : ses micro-récits et ses paragraphes, "
                    "écrits par Claude d'un même geste, rendus à part (italique, un blanc après)",
}
ID = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
PLAN_ID = re.compile(r"^[a-z][a-z0-9-]{1,30}$")


def _bornes(v, nom, A):
    if v is None:
        return None
    try:
        a, b = (int(v), int(v)) if isinstance(v, int) else (int(v[0]), int(v[1]))
    except (TypeError, ValueError, IndexError):
        A.append("%s : deux nombres, [min, max]" % nom)
        return None
    return [min(a, b), max(a, b)]


def lit():
    """{"capacites": {id: capacité normalisée}, "avertissements": [...], "existe": bool}."""
    p = livre.LIVRE / FICHIER
    if not p.exists():
        return {"capacites": {}, "avertissements": [], "existe": False}
    A, C = [], {}
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        return {"capacites": {}, "avertissements": ["%s illisible : %s" % (FICHIER, " ".join(str(e).split()))], "existe": True}
    if not isinstance(doc, dict):
        return {"capacites": {}, "avertissements": ["%s : une capacité par clé (id: {…})" % FICHIER], "existe": True}
    from . import capacites
    plans = {}
    for k, v in doc.items():
        k = str(k)
        a = []
        if not ID.match(k):
            a.append("identifiant : minuscules, chiffres et _ (« %s »)" % k)
        elif k in capacites.CATALOGUE:
            a.append("« %s » est déjà une capacité de LimaLibri : choisir un autre identifiant" % k)
        if not isinstance(v, dict):
            A.append("%s : une description (libelle, primitive…)" % k)
            continue
        prim = str(v.get("primitive") or "")
        if prim not in PRIMITIVES:
            a.append("primitive inconnue : « %s » (connues : %s)" % (prim, ", ".join(PRIMITIVES)))
        pl = v.get("plan") or {}
        pid = str(pl.get("id") or k) if isinstance(pl, dict) else str(pl)
        if not PLAN_ID.match(pid):
            a.append("plan.id : minuscules, chiffres et - (« %s »)" % pid)
        elif pid in plans:
            a.append("plan.id « %s » déjà pris par %s" % (pid, plans[pid]))
        cap = {"id": k, "libelle": " ".join(str(v.get("libelle") or k).split()),
               "quoi": " ".join(str(v.get("quoi") or "").split()), "primitive": prim, "version": "recit",
               "plan": {"id": pid, "titre": (pl.get("titre") if isinstance(pl, dict) else None) or pid.capitalize()},
               "regle": str(v.get("regle") or "").strip() or None,
               "mots": _bornes(v.get("mots"), "mots", a),
               "paragraphes": _bornes(v.get("paragraphes"), "paragraphes", a),
               "consigne": str(v.get("consigne") or "").strip(),
               "modele": str(v.get("modele") or "").strip() or None}
        bloquant = bool(a)
        if cap["regle"] and not regle(cap):                 # pas bloquant : la section est peut-être encore à écrire
            a.append("regle : pas de section « %s » dans regles/recit.md — Claude n'aura que la consigne" % cap["regle"])
        A += ["%s — %s" % (k, x) for x in a]
        if not bloquant:
            C[k] = cap
            plans[pid] = k
    return {"capacites": C, "avertissements": A, "existe": True}


def toutes():
    return lit()["capacites"]


def une(ident):
    c = toutes().get(ident)
    if not c:
        raise ValueError("capacité du livre inconnue : %s" % ident)
    return c


def de_plan(pid):
    """La capacité qui écrit ce plan d'en-tête (ou None)."""
    return next((c for c in toutes().values() if c["plan"]["id"] == str(pid)), None)


def regle(cap):
    """La section des règles qui donne sa voix à la capacité : {id, titre, texte} ou None."""
    if not cap.get("regle"):
        return None
    from . import regles
    cle = cap["regle"].strip().lower()
    for e in regles.lit(cap["version"])["elements"]:
        if cle in (str(e["id"]).lower(), str(e["titre"]).strip().lower()):
            return e
    return None


def pour_catalogue(cap):
    """La capacité au format du catalogue : (libellé, quoi, genre, paramètres, fin, par)."""
    quoi = cap["quoi"] or PRIMITIVES.get(cap["primitive"], "")
    detail = []
    if cap["mots"]:
        detail.append("%d à %d mots" % tuple(cap["mots"]))
    if cap["regle"]:
        detail.append("sa voix : la section « %s » des règles du récit" % cap["regle"])
    quoi = "%s%s Propre à ce livre (%s), primitive « %s »." % (
        quoi, (" (" + " ; ".join(detail) + ")") if detail else "", FICHIER, cap["primitive"])
    return (cap["libelle"], quoi, "recit", {"chapitre": "chapitre!", "consigne": "texte"}, "pose", "claude")


def artefacts(cap):
    return (["posé d'office : chapters/<slug>/brief.yaml — le plan « %s » en tête du storyboard (ses micro-récits) ; "
             "chapters/<slug>/recit.md et links.yaml — ses paragraphes, en tête ; l'ancien récit dans historique/" % cap["plan"]["id"]],
            ["chapters/<slug>/brief.yaml (le plan « %s ») ; chapters/<slug>/recit.md et links.yaml" % cap["plan"]["id"]])
