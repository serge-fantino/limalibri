# -*- coding: utf-8 -*-
"""Enchaîner des actions sur plusieurs chapitres : une série.

Une série vit dans kb/series/<id>.json : des chapitres, des actions, et la liste des étapes qui en
découle, chapitre par chapitre (le brief du premier, son texte, puis le brief du deuxième…), pour que
chaque chapitre lise le précédent déjà écrit. Une étape part quand la précédente a fini ; la série
avance d'elle-même à la fin de chaque demande (reecriture._lance l'appelle), sans dépendre de
l'enchaînement automatique de la file.

Les actions :
  brief    Claude développe le chapitre (planif, niveau chapitre) ; la proposition est retenue d'office :
           les fiches, le squelette et le verrou (amorcer) ; le synopsis et la question seulement s'ils
           manquent — ce que l'auteur a écrit n'est pas écrasé.
  ecrire   Claude écrit l'essai (redaction), posé d'office : le chapitre suivant le lira.
  naif     une lecture naïve de la version (naif) ; les relevés restent à décider par l'auteur.

Une étape sans objet est sautée (un brief déjà prêt, un essai déjà écrit). Une étape en erreur arrête
la série, qui le dit ; on la reprend (l'étape est relancée) ou on l'abandonne.
"""
import json
import time
import secrets

from . import livre, reecriture, avancement

SLUG_KB = "_kb"
ACTIONS = ("brief", "ecrire", "reviser", "naif")
LIB = {"brief": "développer le brief", "ecrire": "écrire l'essai", "reviser": "réviser l'essai", "naif": "lecture naïve"}


def _dossier():
    p = livre.LIVRE / "kb" / "series"
    p.mkdir(parents=True, exist_ok=True)
    return p


def lit(ident):
    p = _dossier() / (ident + ".json")
    if not p.exists():
        raise KeyError(ident)
    return json.loads(p.read_text(encoding="utf-8"))


def _ecrit(s):
    s["modifie"] = livre._maintenant()
    (_dossier() / (s["id"] + ".json")).write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    from . import evenements
    evenements.publie("serie", id=s["id"], etat=s["etat"])


def liste():
    return sorted((json.loads(p.read_text(encoding="utf-8")) for p in _dossier().glob("*.json")),
                  key=lambda s: s["cree"], reverse=True)


def cree(corps):
    """{chapitres: [slug], actions: [brief|ecrire|naif], version?, consigne?, longueur?, modele?}"""
    ordre = [c["slug"] for c in livre.chapitres()]
    chs = [s for s in ordre if s in set(corps.get("chapitres") or [])]
    acts = [a for a in ACTIONS if a in set(corps.get("actions") or [])]
    if not chs or not acts:
        raise ValueError("des chapitres et au moins une action")
    s = {"id": "serie-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2), "cree": livre._maintenant(),
         "etat": "en_cours", "actions": acts, "version": corps.get("version") or "essai",
         "options": {k: corps.get(k) for k in ("consigne", "longueur", "modele", "mots")},
         "etapes": [{"chapitre": c, "action": a, "etat": "a_faire"} for c in chs for a in acts]}
    _ecrit(s)
    avance(s["id"])
    return lit(s["id"])


def arrete(ident):
    s = lit(ident)
    if s["etat"] in ("finie", "abandonnee"):
        return s
    s["etat"] = "abandonnee"
    for e in s["etapes"]:
        if e["etat"] == "a_faire":
            e["etat"] = "abandonnee"
    _ecrit(s)
    return s


def reprend(ident):
    s = lit(ident)
    for e in s["etapes"]:
        if e["etat"] in ("erreur", "abandonnee"):
            e.update(etat="a_faire", demande=None, erreur=None)
    s["etat"] = "en_cours"
    s.pop("erreur", None)
    _ecrit(s)
    avance(ident)
    return lit(ident)


# ------------------------------------------------------------------ avancer

def _chapitre(slug):
    return next(c for c in livre.chapitres() if c["slug"] == slug)


def _demande(e):
    slug = SLUG_KB if e["action"] in ("brief", "ecrire", "reviser") else e["chapitre"]
    try:
        return reecriture.lit(slug, e["demande"])
    except Exception:                                 # noqa: BLE001
        return None


def _retient_brief(d):
    """La proposition de brief, retenue d'office : fiches, squelette et verrou ; synopsis et question
    seulement s'ils manquent."""
    from . import planif, plan
    C = (d.get("resultat") or {}).get("chapitre") or {}
    slug = d["cible"]["chapitre"]
    cur = next((c for p in plan.lit()["parties"] for c in p["chapitres"] if c["slug"] == slug), {})
    champs = [k for k in ("synopsis", "question") if C.get(k) and not cur.get(k)]
    deja = [f for f in cur.get("fiches") or [] if f not in {x.get("fiche") for x in C.get("fiches") or []}]
    if deja:                                    # les fiches choisies par l'auteur restent
        C["fiches"] = [{"fiche": f, "raison": "déjà au brief"} for f in deja] + list(C.get("fiches") or [])
        reecriture._ecrit(SLUG_KB, d)
    if C.get("fiches"):
        champs.append("fiches")
    return planif.decide(d["id"], {"chapitre": champs, "amorce": True})


def _lance(s, e):
    """Lancer une étape ; rend False si elle est sans objet (sautée)."""
    c = _chapitre(e["chapitre"])
    o = s["options"]
    if e["action"] == "brief":
        if avancement.niveau(c, "essai") not in ("vide", "synopsis"):
            return False
        from . import planif
        d = planif.cree({"niveau": "chapitre", "chapitre": c["slug"], "consigne": o.get("consigne") or "", "modele": o.get("modele")})
    elif e["action"] == "ecrire":
        if avancement.niveau(c, "essai") not in ("synopsis", "brief"):
            return False
        from . import redaction
        d = redaction.cree({"chapitre": c["slug"], "poser": True, "consigne": o.get("consigne") or "",
                            "longueur": o.get("longueur"), "modele": o.get("modele"), "serie": s["id"]})
    elif e["action"] == "reviser":
        if avancement.niveau(c, "essai") not in ("brouillon", "relu", "valide"):
            return False
        from . import redaction
        d = redaction.cree({"chapitre": c["slug"], "revision": True, "poser": True, "consigne": o.get("consigne") or "",
                            "mots": o.get("mots"), "modele": o.get("modele"), "serie": s["id"]})
    else:
        if avancement.niveau(c, s["version"]) not in ("brouillon", "relu", "valide"):
            return False
        from . import naif
        d = naif.cree(c["slug"], {"version": s["version"], "modele": o.get("modele")})
    if d.get("etat") == "en_attente" and not d.get("serie"):   # en file : marquée de la série, elle partira d'elle-même
        d["serie"] = s["id"]
        reecriture._ecrit(SLUG_KB if e["action"] in ("brief", "ecrire", "reviser") else e["chapitre"], d)
    e.update(etat="en_cours", demande=d["id"], lancee=livre._maintenant())
    return True


def avance(ident=None):
    """Faire avancer une série (ou toutes) : clore l'étape finie, lancer la suivante."""
    for s in ([lit(ident)] if ident else [x for x in liste() if x["etat"] == "en_cours"]):
        if s["etat"] != "en_cours":
            continue
        while True:
            cur = next((e for e in s["etapes"] if e["etat"] == "en_cours"), None)
            if cur:
                d = _demande(cur)
                if d is None or d["etat"] in ("en_cours", "en_attente"):
                    break                                   # elle travaille encore
                if d["etat"] == "erreur":
                    cur.update(etat="erreur", erreur=d.get("erreur"))
                    s.update(etat="arretee", erreur="%s, %s : %s" % (LIB[cur["action"]], cur["chapitre"], d.get("erreur")))
                    break
                if cur["action"] == "brief" and d["etat"] == "prete":
                    try:
                        _retient_brief(d)
                    except Exception as x:                  # noqa: BLE001
                        cur.update(etat="erreur", erreur="brief non retenu : %s" % x)
                        s.update(etat="arretee", erreur=cur["erreur"])
                        break
                if cur["action"] in ("ecrire", "reviser") and d.get("erreur_pose"):
                    cur.update(etat="erreur", erreur=d["erreur_pose"])
                    s.update(etat="arretee", erreur="essai non posé (%s) : %s" % (cur["chapitre"], d["erreur_pose"]))
                    break
                cur.update(etat="faite", finie=livre._maintenant())
                continue
            suivante = next((e for e in s["etapes"] if e["etat"] == "a_faire"), None)
            if not suivante:
                s["etat"] = "finie"
                break
            try:
                if not _lance(s, suivante):
                    suivante["etat"] = "sautee"
                    continue
            except Exception as x:                          # noqa: BLE001
                suivante.update(etat="erreur", erreur="%s" % x)
                s.update(etat="arretee", erreur="%s, %s : %s" % (LIB[suivante["action"]], suivante["chapitre"], x))
            break
        _ecrit(s)
