# -*- coding: utf-8 -*-
"""Piloter le plan d'un objectif : le plan retenu d'un cadrage, exécuté phase par phase.

Un plan vit dans kb/plans/<objectif>.json (l'ancien est archivé quand un nouveau est retenu) :

    {id, objectif, demande (le cadrage), cree, etat, options: {poser, d_office, modele},
     cadre (ce qui a été appliqué), phases: [{titre, but, point_arret, etat, actions: [
        {id, capacite, params, pourquoi, depend, etat, demande?, slug?, erreur?}]}], journal}

États du plan : pret (retenu, pas lancé), en_cours, pause (rien de neuf ne part ; ce qui tourne finit),
point_arret (une phase finie attend l'auteur : « continuer »), bloque (une action en erreur : la relancer
ou la sauter), fini, arrete.
États d'une action : a_faire, lancee (sa demande tourne ou attend dans la file), a_toi (une tâche de
l'auteur, qu'il marque faite), faite, sautee, erreur.

Avancer : dans la phase courante, chaque action dont les dépendances sont faites part — par
capacites.lance(), marquée du plan (les demandes d'un plan partent de la file d'elles-mêmes, comme
celles d'une série). Une action est faite quand sa demande a rendu son résultat (prête, à confirmer,
décidée) : ce qui attend une décision de l'auteur se décide au point d'arrêt de la phase. Le pilotage
avance à la fin de chaque demande (reecriture._lance), au démarrage du serveur, et sur chaque geste de
l'auteur.
"""
import json
import time
import secrets

from . import livre, reecriture, objectifs, capacites

SLUG_KB = "_kb"
TERMINE = ("prete", "a_confirmer", "decidee", "remplacee")


class Conflit(Exception):
    pass


def _dossier():
    p = livre.LIVRE / "kb" / "plans"
    p.mkdir(parents=True, exist_ok=True)
    return p


def lit(objectif):
    p = _dossier() / (objectif + ".json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _ecrit(P):
    P["modifie"] = livre._maintenant()
    (_dossier() / (P["objectif"] + ".json")).write_text(json.dumps(P, ensure_ascii=False, indent=1), encoding="utf-8")
    from . import evenements
    evenements.publie("serie", id=P["id"], etat=P["etat"], objectif=P["objectif"])


def _note(P, texte):
    P.setdefault("journal", []).append({"date": livre._maintenant(), "texte": texte})


def tous():
    out = []
    for p in _dossier().glob("*.json"):
        if p.stem.count("--") == 0:
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except ValueError:
                pass
    return out


# ------------------------------------------------------------------ retenir un cadrage

def retient(objectif, corps):
    """{demande, actions: [id], cadre: [index], couper: [id demande], edits?: {id: params},
    options?: {poser, d_office, modele}} — applique le cadre retenu, coupe, et pose le plan (prêt)."""
    from . import regles, file
    o = next((x for x in objectifs.lit_tous() if x.get("id") == objectif), None)
    if not o:
        raise KeyError(objectif)
    d = reecriture.lit(SLUG_KB, corps.get("demande") or "")
    if d.get("type") != "cadrage" or d["cible"].get("objectif") != objectif:
        raise ValueError("ce n'est pas un cadrage de cet objectif")
    if d["etat"] != "prete":
        raise Conflit("le cadrage n'attend pas de décision (%s)" % d["etat"])
    avant = lit(objectif)
    if avant and avant["etat"] in ("en_cours", "point_arret", "bloque"):
        raise Conflit("un plan est en cours pour cet objectif : le mettre en pause ou l'arrêter d'abord")
    R = d["resultat"]
    version = o.get("version", "essai")
    # le plan d'abord : rien n'est appliqué s'il ne tient pas
    garde = set(corps.get("actions") or [])
    edits = corps.get("edits") or {}
    phases = []
    for ph in R.get("phases") or []:
        A = []
        for a in ph.get("actions") or []:
            if a.get("id") not in garde:
                continue
            A.append({"id": a["id"], "capacite": a["capacite"], "params": edits.get(a["id"]) or a.get("params") or {},
                      "pourquoi": a.get("pourquoi"), "depend": [x for x in a.get("depend") or [] if x in garde or ":" in x],
                      "etat": "a_faire"})
        if A:
            phases.append({"titre": ph["titre"], "but": ph.get("but"), "point_arret": bool(ph.get("point_arret")),
                           "etat": "a_venir", "actions": A})
    if not phases:
        raise ValueError("aucune action retenue")
    K = {"chapitres": capacites._chapitres(), "fiches": capacites._fiches(), "parties": capacites._parties()}
    mauvaises = {a["id"]: capacites.valide(a["capacite"], a["params"], K) for ph in phases for a in ph["actions"]}
    mauvaises = {k: v for k, v in mauvaises.items() if v}
    if mauvaises:
        raise ValueError("actions invalides : " + " ; ".join("%s : %s" % (k, ", ".join(v)) for k, v in mauvaises.items()))
    # puis le cadre
    applique = []
    existantes = {e["titre"].strip().lower() for e in regles.lit(version)["elements"] if e.get("type") == "regle"}
    for k in corps.get("cadre") or []:
        try:
            c = (R.get("cadre") or [])[int(k)]
        except (IndexError, ValueError, TypeError):
            continue
        if c["type"] == "regle":
            titre = (c.get("titre") or c["texte"][:60]).strip()
            if titre.lower() in existantes:              # déjà là : ne pas la doubler
                applique.append({"type": "regle", "titre": titre, "deja": True})
                continue
            r = regles.ajoute(version, titre, c["texte"], regles.lit(version)["empreinte"])
            existantes.add(titre.lower())
            applique.append({"type": "regle", "id": r["cree"]["id"], "titre": r["cree"]["titre"]})
        elif c["type"] == "regle_revue" and c.get("cible"):
            el = next((e for e in regles.lit(version)["elements"] if e["id"] == c["cible"]), None)
            if not el:
                applique.append({"type": "regle_revue", "id": c["cible"], "erreur": "introuvable"})
                continue
            regles.modifie(version, c["cible"], (c.get("titre") or el["titre"]).strip(), c["texte"], regles.lit(version)["empreinte"])
            applique.append({"type": "regle_revue", "id": c["cible"], "titre": c.get("titre") or el["titre"]})
        elif c["type"] == "critere" and c.get("critere") in objectifs.CRITERES:
            cr = [x for x in o.get("criteres") or [] if x["id"] != c["critere"]] + \
                 [{"id": c["critere"], "valeur": c.get("valeur", objectifs.CRITERES[c["critere"]][2])}]
            o = objectifs.modifie(objectif, {"criteres": cr})
            applique.append({"type": "critere", "id": c["critere"], "valeur": c.get("valeur")})
        elif c["type"] == "consigne":
            o = objectifs.ajoute_consigne(objectif, c["texte"])
            applique.append({"type": "consigne", "texte": c["texte"]})
    # couper
    coupees = []
    for ident in corps.get("couper") or []:
        try:
            file.retire(ident)
            coupees.append(ident)
        except Exception:                               # noqa: BLE001 — seule une demande en attente se retire
            pass
    if avant:                                          # l'ancien plan est archivé ; ses demandes en file retirées
        _retire_en_file(avant)
        (_dossier() / (objectif + ".json")).rename(_dossier() / ("%s--%s.json" % (objectif, time.strftime("%Y%m%d-%H%M%S"))))
    O = corps.get("options") or {}
    P = {"id": "pl-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2), "objectif": objectif,
         "demande": d["id"], "cree": livre._maintenant(), "etat": "pret", "version": version,
         "options": {"poser": O.get("poser", True) is not False, "d_office": O.get("d_office", True) is not False,
                     "modele": O.get("modele")},
         "cadre": applique, "coupees": coupees, "phases": phases, "journal": []}
    _note(P, "plan retenu : %d phase(s), %d action(s)" % (len(phases), sum(len(p["actions"]) for p in phases)))
    _ecrit(P)
    d.update(etat="decidee", decision={"proposition": "plan", "plan": P["id"], "cadre": applique, "coupees": coupees,
                                       "date": livre._maintenant()})
    reecriture._ecrit(SLUG_KB, d)
    return P


# ------------------------------------------------------------------ les gestes de l'auteur

def _plan(objectif):
    P = lit(objectif)
    if not P:
        raise KeyError(objectif)
    return P


def geste(objectif, op):
    P = _plan(objectif)
    if op == "demarrer":
        if P["etat"] not in ("pret", "pause", "bloque"):
            raise Conflit("le plan est %s" % P["etat"])
        _note(P, "démarré" if P["etat"] == "pret" else "repris")
        P["etat"] = "en_cours"
    elif op == "pause":
        if P["etat"] != "en_cours":
            raise Conflit("le plan n'est pas en cours (%s)" % P["etat"])
        P["etat"] = "pause"
        _note(P, "mis en pause")
    elif op == "continuer":
        if P["etat"] != "point_arret":
            raise Conflit("le plan n'attend pas l'auteur (%s)" % P["etat"])
        ph = next(p for p in P["phases"] if p["etat"] == "point_arret")
        ph.update(etat="faite", validee=livre._maintenant())
        P["etat"] = "en_cours"
        _note(P, "point d'arrêt passé : %s" % ph["titre"])
    elif op == "arreter":
        P["etat"] = "arrete"
        n = _retire_en_file(P)
        _note(P, "arrêté" + (" — %d demande(s) retirée(s) de la file" % n if n else ""))
    else:
        raise ValueError("geste inconnu : %s" % op)
    _ecrit(P)
    avance()                                     # tous les plans : l'un peut attendre une action de celui-ci
    from . import file                           # reprise : ses demandes en file repartent
    file.suivante()
    return lit(objectif)


def _retire_en_file(P):
    """Les demandes du plan encore en file : retirées, et leurs actions sautées."""
    from . import file
    n = 0
    for ph in P["phases"]:
        for a in ph["actions"]:
            if a["etat"] != "lancee":
                continue
            d = _etat_demande(a)
            if d and d.get("etat") == "en_attente":
                try:
                    file.retire(a["demande"])
                    a.update(etat="sautee", erreur="retirée de la file (plan arrêté)")
                    n += 1
                except Exception:                       # noqa: BLE001
                    pass
    return n


def geste_action(objectif, aid, op):
    P = _plan(objectif)
    a = next((a for ph in P["phases"] for a in ph["actions"] if a["id"] == aid), None)
    if not a:
        raise KeyError(aid)
    if op == "fait":
        if a["etat"] not in ("a_toi", "a_faire"):
            raise Conflit("l'action n'attend pas l'auteur (%s)" % a["etat"])
        a.update(etat="faite", finie=livre._maintenant())
    elif op == "sauter":
        if a["etat"] in ("faite", "lancee"):
            raise Conflit("l'action est %s" % a["etat"])
        a.update(etat="sautee")
    elif op == "relancer":
        if a["etat"] != "erreur":
            raise Conflit("seule une action en erreur se relance")
        a.update(etat="a_faire", erreur=None, demande=None)
        if P["etat"] == "bloque":
            P["etat"] = "en_cours"
    else:
        raise ValueError("geste inconnu : %s" % op)
    _note(P, "%s : %s" % (aid, op))
    _ecrit(P)
    avance()
    return lit(objectif)


# ------------------------------------------------------------------ avancer

def _etat_demande(a):
    try:
        return reecriture.lit(a["slug"], a["demande"])
    except Exception:                                   # noqa: BLE001
        return None


def _lance(P, o, a, phase=None):
    from . import filiation
    O = P["options"]
    champs = {"plan": {"plan": P["id"], "objectif": P["objectif"], "action": a["id"], "phase": phase}}
    if a["capacite"] == "fiche" and O.get("d_office"):
        champs["creer_d_office"] = True
    with filiation.marque(**champs):
        slug, d = capacites.lance(a["capacite"], a["params"], o.get("consigne") or "",
                                  {"poser": O.get("poser", True), "modele": O.get("modele"), "version": P.get("version")})
    a.update(etat="lancee", demande=d["id"], slug=slug, lancee=livre._maintenant())


def avance(objectif=None):
    for P in ([lit(objectif)] if objectif else tous()):
        if not P or P["etat"] != "en_cours":
            continue
        o = next((x for x in objectifs.lit_tous() if x.get("id") == P["objectif"]), {})
        while True:
            ph = next((p for p in P["phases"] if p["etat"] not in ("faite",)), None)
            if ph is None:
                P["etat"] = "fini"
                _note(P, "plan fini")
                break
            ph["etat"] = "en_cours" if ph["etat"] == "a_venir" else ph["etat"]
            # ce qui tournait
            for a in ph["actions"]:
                if a["etat"] != "lancee":
                    continue
                d = _etat_demande(a)
                if d is None or d.get("etat") == "retiree":
                    a.update(etat="sautee", erreur="demande disparue ou retirée")
                elif d["etat"] in TERMINE:
                    a.update(etat="faite", finie=livre._maintenant())
                elif d["etat"] == "erreur":
                    a.update(etat="erreur", erreur=d.get("erreur"))
            if any(a["etat"] == "erreur" for a in ph["actions"]):
                P["etat"] = "bloque"
                _note(P, "bloqué : %s" % ", ".join(a["id"] for a in ph["actions"] if a["etat"] == "erreur"))
                break
            # ce qui peut partir (une dépendance « o-xxxx:a8 » vise le plan d'un autre objectif)
            faites = {a["id"] for p in P["phases"] for a in p["actions"] if a["etat"] in ("faite", "sautee")}
            for x in {x for a in ph["actions"] for x in a.get("depend") or [] if ":" in x}:
                oo, aa = x.split(":", 1)
                Q = lit(oo)
                if Q and any(b["id"] == aa and b["etat"] in ("faite", "sautee") for q in Q["phases"] for b in q["actions"]):
                    faites.add(x)
            for a in ph["actions"]:
                if a["etat"] != "a_faire" or not set(a.get("depend") or []) <= faites:
                    continue
                if a["capacite"] == "auteur":
                    a["etat"] = "a_toi"
                    continue
                try:
                    _lance(P, o, a, P["phases"].index(ph))
                except Exception as e:                  # noqa: BLE001 — l'action est en erreur, le plan bloqué
                    a.update(etat="erreur", erreur="%s" % e)
            if any(a["etat"] == "erreur" for a in ph["actions"]):
                P["etat"] = "bloque"
                break
            if all(a["etat"] in ("faite", "sautee") for a in ph["actions"]):
                if ph.get("point_arret") and not ph.get("validee"):
                    ph["etat"] = "point_arret"
                    P["etat"] = "point_arret"
                    _note(P, "point d'arrêt : %s" % ph["titre"])
                    break
                ph["etat"] = "faite"
                continue
            break
        _ecrit(P)
