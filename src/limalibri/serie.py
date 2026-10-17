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
  storyboard  Claude prépare les plans du récit depuis l'essai, posés d'office.
  recit    Claude écrit le récit depuis le storyboard (narration), posé d'office.
  naif     une lecture naïve de la version (naif) ; les relevés restent à décider par l'auteur.
  <id>     une capacité propre au livre (capacites.yaml : l'ouverture…), posée d'office, après le récit du chapitre
           (elle le lit) ; sautée si le chapitre a déjà son plan d'en-tête, s'il est exclu (« sauf »), ou s'il n'a pas
           encore d'essai (les faits) ou de récit.

Une étape sans objet est sautée (un brief déjà prêt, un essai déjà écrit). Une étape en erreur arrête
la série, qui le dit ; on la reprend (l'étape est relancée) ou on l'abandonne.
"""
import json
import time
import secrets

from . import livre, reecriture, avancement

SLUG_KB = "_kb"
ACTIONS = ("brief", "ecrire", "reviser", "storyboard", "recit", "naif")
LIB = {"brief": "développer le brief", "ecrire": "écrire l'essai", "reviser": "réviser l'essai", "storyboard": "écrire le storyboard",
       "recit": "écrire le récit",
       "naif": "lecture naïve"}
KB = ("brief", "ecrire", "reviser", "storyboard", "recit")          # les étapes dont la demande vit dans kb/demandes


def actions():
    """Les actions d'une série, dans l'ordre d'un chapitre : celles du livre (capacites.yaml) après le récit."""
    from . import capacites_livre
    return ACTIONS[:-1] + tuple(capacites_livre.toutes()) + ACTIONS[-1:]


def lib(a):
    from . import capacites_livre
    c = capacites_livre.toutes().get(a)
    return c["libelle"] if c else LIB.get(a, a)


def _kb(a):
    return a in KB or a not in ACTIONS


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
    """{chapitres: [slug], actions: [brief|ecrire|…|<capacité du livre>|naif], version?, consigne?, longueur?, modele?}"""
    ordre = [c["slug"] for c in livre.chapitres()]
    A = actions()
    if corps.get("etapes"):                     # des étapes données (un objectif) : chacune avec sa consigne
        connus = set(ordre)
        E = [{"chapitre": e["chapitre"], "action": e["action"], "etat": "a_faire",
              **({"consigne": e["consigne"]} if e.get("consigne") else {}),
              **({"annotations": e["annotations"]} if e.get("annotations") else {})}
             for e in corps["etapes"] if e.get("action") in A and e.get("chapitre") in connus]
        E.sort(key=lambda e: (ordre.index(e["chapitre"]), A.index(e["action"])))
        acts = [a for a in A if a in {e["action"] for e in E}]
        if not E:
            raise ValueError("aucune étape")
    else:
        chs = [s for s in ordre if s in set(corps.get("chapitres") or [])]
        acts = [a for a in A if a in set(corps.get("actions") or [])]
        if not chs or not acts:
            raise ValueError("des chapitres et au moins une action")
        E = [{"chapitre": c, "action": a, "etat": "a_faire"} for c in chs for a in acts]
    s = {"id": "serie-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2), "cree": livre._maintenant(),
         "etat": "en_cours", "actions": acts, "version": corps.get("version") or "essai",
         "options": {k: corps.get(k) for k in ("consigne", "longueur", "modele", "mots", "poser")},
         "etapes": E}
    if corps.get("objectif"):
        s["objectif"] = corps["objectif"]
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
    anciennes = {}
    for k, e in enumerate(s["etapes"]):
        if e["etat"] in ("erreur", "abandonnee"):
            if e.get("demande"):
                anciennes[k] = (SLUG_KB if _kb(e["action"]) else e["chapitre"], e["demande"])
            e.update(etat="a_faire", demande=None, erreur=None)
    s["etat"] = "en_cours"
    s.pop("erreur", None)
    _ecrit(s)
    avance(ident)
    s = lit(ident)
    for k, (slug, vieille) in anciennes.items():    # la liste des demandes dit la même chose que la série
        neuve = s["etapes"][k].get("demande")
        try:
            v = reecriture.lit(slug, vieille)
        except Exception:                           # noqa: BLE001
            continue
        if neuve and v.get("etat") in ("erreur", "prete", "en_attente"):
            v.update(etat="remplacee", remplacee_par=neuve)
            reecriture._ecrit(slug, v)
            n = reecriture.lit(slug, neuve)
            n["relance_de"] = vieille
            reecriture._ecrit(slug, n)
    return s


def relie(ident, vieille, neuve):
    """Une demande d'étape relancée hors de la série (depuis son tiroir) : l'étape suit la nouvelle."""
    try:
        s = lit(ident)
    except Exception:                               # noqa: BLE001
        return
    e = next((x for x in s["etapes"] if x.get("demande") == vieille), None)
    if not e:
        return
    e.update(demande=neuve, etat="en_cours", erreur=None, lancee=livre._maintenant())
    if s["etat"] == "arretee":                        # la série reste arrêtée : « reprendre » la fait continuer
        s["erreur"] = "étape relancée hors de la série — « reprendre » pour continuer"
    _ecrit(s)


# ------------------------------------------------------------------ avancer

def _chapitre(slug):
    return next(c for c in livre.chapitres() if c["slug"] == slug)


def _demande(e):
    slug = SLUG_KB if _kb(e["action"]) else e["chapitre"]
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
    o = dict(s["options"])
    if e.get("consigne"):                         # la consigne propre à l'étape (un objectif), avant celle de la série
        o["consigne"] = e["consigne"] + ("\n\n" + o["consigne"] if o.get("consigne") else "")
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
        d = redaction.cree({"chapitre": c["slug"], "revision": True, "poser": o.get("poser") is not False, "consigne": o.get("consigne") or "",
                            "annotations": e.get("annotations"),
                            "mots": o.get("mots"), "modele": o.get("modele"), "serie": s["id"]})
    elif e["action"] == "storyboard":
        # le storyboard part de l'essai ; posé d'office : le chapitre suivant enchaîne sur lui
        if avancement.niveau(c, "essai") not in ("brouillon", "relu", "valide"):
            return False
        from . import storyboard
        d = storyboard.cree({"chapitre": c["slug"], "consigne": o.get("consigne") or "", "modele": o.get("modele"),
                             "poser": o.get("poser") is not False})
    elif e["action"] == "recit":
        # le récit part du storyboard ; un récit déjà écrit n'est pas réécrit par une série
        if avancement.niveau(c, "recit") != "brief":
            return False
        from . import narration
        d = narration.cree({"chapitre": c["slug"], "consigne": o.get("consigne") or "", "modele": o.get("modele"),
                            "poser": o.get("poser") is not False})
    elif e["action"] not in ACTIONS:
        # une capacité du livre (un plan d'en-tête) : une fois par chapitre, depuis son essai
        from . import capacites_livre, narration
        cap = capacites_livre.toutes().get(e["action"])
        if not cap or cap["plan"]["id"] in livre.plans_en_tete(c["slug"]) or capacites_livre.exclu(cap, c["slug"]) \
                or avancement.niveau(c, "essai") not in ("brouillon", "relu", "valide") or not narration.recit_ecrit(c["slug"]):
            return False
        d = narration.cree({"chapitre": c["slug"], "capacite": cap["id"], "consigne": o.get("consigne") or "",
                            "modele": o.get("modele"), "poser": o.get("poser") is not False})
    else:
        if avancement.niveau(c, s["version"]) not in ("brouillon", "relu", "valide"):
            return False
        from . import naif
        d = naif.cree(c["slug"], {"version": s["version"], "modele": o.get("modele")})
    if not d.get("serie"):                         # la demande sait sa série (en file : elle partira d'elle-même)
        slug_d = SLUG_KB if _kb(e["action"]) else e["chapitre"]
        d = reecriture.lit(slug_d, d["id"])           # relue : elle a pu démarrer et s'écrire entre-temps
        d["serie"] = s["id"]
        reecriture._ecrit(slug_d, d)
    e.update(etat="en_cours", demande=d["id"], lancee=livre._maintenant())
    return True


def _resynchronise(s):
    """Une série arrêtée dont l'étape en erreur a été reprise ou relancée hors d'elle (depuis le tiroir de la
    demande) : l'étape dit l'état réel de sa demande. La série reste arrêtée — « reprendre » la fait continuer :
    rien ne repart sans que l'auteur le demande."""
    change = False
    for e in s["etapes"]:
        if e["etat"] not in ("erreur", "en_cours") or not e.get("demande"):
            continue
        d = _demande(e)
        if d is None:
            continue
        if d.get("remplacee_par"):                      # relancée : l'étape suit la nouvelle
            e["demande"] = d["remplacee_par"]
            d = _demande(e) or d
            change = True
        if d["etat"] in ("en_cours", "en_attente"):
            e.update(etat="en_cours", erreur=None)
        elif d["etat"] in ("prete", "decidee") and not d.get("erreur_pose"):
            e.update(etat="faite", erreur=None, finie=livre._maintenant())
        else:
            continue
        change = True
    if change and not any(e["etat"] == "erreur" for e in s["etapes"]):
        s["erreur"] = "étape reprise hors de la série — « reprendre » pour continuer"
    return change


def avance(ident=None):
    """Faire avancer une série (ou toutes) : clore l'étape finie, lancer la suivante."""
    for s in ([lit(ident)] if ident else [x for x in liste() if x["etat"] in ("en_cours", "arretee")]):
        if s["etat"] == "arretee":
            if _resynchronise(s):
                _ecrit(s)
            continue
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
                    s.update(etat="arretee", erreur="%s, %s : %s" % (lib(cur["action"]), cur["chapitre"], d.get("erreur")))
                    break
                if cur["action"] == "brief" and d["etat"] == "prete":
                    try:
                        _retient_brief(d)
                    except Exception as x:                  # noqa: BLE001
                        cur.update(etat="erreur", erreur="brief non retenu : %s" % x)
                        s.update(etat="arretee", erreur=cur["erreur"])
                        break
                if cur["action"] in ("ecrire", "reviser", "storyboard", "recit") and d.get("erreur_pose"):
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
                s.update(etat="arretee", erreur="%s, %s : %s" % (lib(suivante["action"]), suivante["chapitre"], x))
            break
        _ecrit(s)
