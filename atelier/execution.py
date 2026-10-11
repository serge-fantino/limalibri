# -*- coding: utf-8 -*-
"""Piloter un objectif : de ses écarts, un plan d'exécution ; du plan, une série.

Le plan se calcule, sans Claude, à partir des écarts mesurés (atelier/objectifs.py), chapitre par
chapitre, dans l'ordre où le travail doit se faire :

    brief      le chapitre n'a qu'un synopsis (essai)                       Claude
    ecrire     il n'a pas encore de texte (essai)                           Claude
    reviser    portes du harnais en échec (ou visées par « relu ») : la      Claude
               consigne nomme les portes, et l'intention de l'objectif
    naif       lecture naïve à faire (ou visée par « relu »), après la       Claude
               révision : elle lit le texte révisé
    statut     passer en relu / validé — c'est l'auteur qui le décide       auteur
    manques, fiches, annotations, decider : à l'auteur, avec le lien

Chaque élément dit pourquoi il est là (les écarts qu'il traite), ce qu'il coûterait (moyennes du journal
de consommation du livre) et où il en est : à lancer, déjà en file, en cours, dans une série, fait.
Exécuter : les éléments de Claude retenus deviennent une série (atelier/serie.py) rattachée à l'objectif,
qui avance d'elle-même, chapitre par chapitre ; on l'arrête, on la reprend. Avant de lancer, le budget
restant de l'objectif est vérifié.
"""
import json

from . import livre, avancement, objectifs

ORDRE = ("brief", "ecrire", "reviser", "naif", "statut", "manques", "fiches", "annotations", "decider")
LIB = {"brief": "développer le brief", "ecrire": "écrire l'essai", "reviser": "réviser l'essai", "naif": "lecture naïve",
       "statut": "passer en relu", "manques": "traiter les manques", "fiches": "choisir des fiches",
       "annotations": "traiter les annotations", "decider": "décider les résultats en attente"}
CLAUDE = ("brief", "ecrire", "reviser", "naif")
GENRE = {"brief": "plan", "ecrire": "redaction", "reviser": "redaction", "naif": "naive"}
DEFAUT = {"plan": (0.8, 80), "redaction": (1.6, 280), "naive": (0.5, 120)}     # $ et secondes, sans historique


def _moyennes():
    p = livre.LIVRE / "consommation.jsonl"
    acc = {}
    if p.exists():
        for l in p.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(l)
            except ValueError:
                continue
            if e.get("source") == "demande" and e.get("issue") == "ok" and e.get("cout_usd"):
                a = acc.setdefault(e.get("genre"), [0, 0, 0])
                a[0] += e["cout_usd"]
                a[1] += e.get("duree_s") or 0
                a[2] += 1
    out = dict(DEFAUT)
    for g, (c, d, n) in acc.items():
        if n >= 3:
            out[g] = (c / n, d / n)
    return out


def _consigne_revision(o, portes):
    L = ["Objectif de l'auteur : « %s »." % o["titre"]]
    if portes:
        L.append("Le harnais signale en échec : %s. Révise pour que ces portes passent, sans perdre le contenu "
                 "établi par le verrou." % ", ".join(p.lower() for p in portes))
    if o.get("intention"):
        L.append("Intention de l'auteur pour ce travail : %s" % o["intention"])
    return " ".join(L)


def _encours(T, series):
    """(chapitre, action) -> où en est déjà ce travail : {statut, demande?, serie?}."""
    out = {}
    for s in series:
        if s.get("etat") not in ("en_cours", "arretee"):
            continue
        for e in s["etapes"]:
            if e["etat"] in ("a_faire", "en_cours", "erreur"):
                out[(e["chapitre"], e["action"])] = {"statut": "serie", "serie": s["id"], "demande": e.get("demande"),
                                                     "etape": e["etat"]}
    for ch, t in T.items():
        for quoi, L in (("en_cours", t.get("en_cours") or []), ("en_file", t.get("en_file") or []),
                        ("a_decider", t.get("a_decider") or [])):
            for x in L:
                a = {"naive": "naif", "plan": "brief"}.get(x.get("type"))
                if x.get("type") == "redaction":
                    a = "reviser" if "Réviser" in (x.get("titre") or "") else "ecrire"
                if a and (ch, a) not in out:
                    out[(ch, a)] = {"statut": quoi, "demande": x["id"], "slug": x.get("slug")}
    return out


def plan(ident):
    from . import suivi, travail, serie
    o = next((x for x in objectifs.lit_tous() if x.get("id") == ident), None)
    if not o:
        raise KeyError(ident)
    version = o.get("version", "essai")
    S = suivi.suivi(version)
    e = next(x for x in S["objectifs"] if x["id"] == ident)
    C = {c["slug"]: c for c in S["chapitres"]}
    T = travail.par_chapitre()
    series = [s for s in serie.liste() if s.get("objectif") == ident]
    deja = _encours(T, series)
    niveaux = list(avancement.NIVEAUX)
    cible_niv = next((cr["valeur"] for cr in o.get("criteres") or [] if cr["id"] == "niveau"), None)
    vise_relu = cible_niv in ("relu", "valide")
    M = _moyennes()
    items = []
    for l in e["chapitres"]:
        if not l["ecarts"]:
            continue
        c = C[l["slug"]]
        m = c.get("mesures") or {}
        rates = {x["critere"]: x for x in l["ecarts"]}
        niv = m.get("niveau") or "vide"
        a_faire = {}                                     # action -> [pourquoi]

        def ajoute(a, pourquoi):
            a_faire.setdefault(a, []).append(pourquoi)
        if "niveau" in rates:
            lib = "niveau %s (%s)" % (niv, rates["niveau"]["attendu"])
            if version == "essai" and niv in ("vide", "synopsis"):
                ajoute("brief", lib)
            if version == "essai" and niv in ("vide", "synopsis", "brief") and niveaux.index(cible_niv) >= niveaux.index("brouillon"):
                ajoute("ecrire", lib)
            if vise_relu and niveaux.index(niv) < niveaux.index(cible_niv):
                ajoute("statut", lib)
        ecrit = m.get("ecrit") or "ecrire" in a_faire
        if ecrit and m.get("portes_ko") and ("controles" in rates or ("niveau" in rates and vise_relu)):
            ajoute("reviser", "portes en échec : %s" % ", ".join(t.lower() for t in m.get("portes_ko_titres") or []))
        if ecrit and not m.get("naif") and ("naif" in rates or ("niveau" in rates and vise_relu)):
            ajoute("naif", "lecture naïve à faire")
        for k, a in (("manques", "manques"), ("fiches", "fiches"), ("annotations", "annotations"), ("a_decider", "decider")):
            if k in rates:
                x = rates[k]
                ajoute(a, "%s : %s (%s)" % (x["libelle"], x["mesure"], x["attendu"]))
        for a in ORDRE:
            if a not in a_faire:
                continue
            it = {"id": "%s:%s" % (l["slug"], a), "chapitre": l["slug"], "numero": l["numero"], "titre": l["titre"],
                  "action": a, "libelle": LIB[a] if a != "statut" else ("valider" if cible_niv == "valide" else "passer en relu"),
                  "par": "claude" if a in CLAUDE else "auteur", "pourquoi": a_faire[a]}
            if a == "reviser":
                it["consigne"] = _consigne_revision(o, m.get("portes_ko_titres") or [])
            if a in CLAUDE:
                cout, duree = M.get(GENRE[a], DEFAUT[GENRE[a]])
                it.update(cout=round(cout, 2), duree_s=round(duree))
                d = deja.get((l["slug"], a))
                it["statut"] = d["statut"] if d else "a_lancer"
                if d:
                    it["suivi"] = d
            else:
                it["statut"] = "auteur"
                vue = "%s/%s" % (l["slug"], "essai/texte" if version == "essai" else "recit/texte")
                it["vue"] = {"statut": "plan/c/%s" % l["slug"], "fiches": "plan/c/%s" % l["slug"]}.get(a, vue)
                it["tiroir"] = {"annotations": "annotations", "manques": "manques"}.get(a)
                if a == "decider":
                    it["demandes"] = (C[l["slug"]].get("travail") or {}).get("a_decider") or []
            items.append(it)
    restant = None if o.get("budget") is None else round(o["budget"] - e["depense"], 2)
    return {"objectif": e, "version": version, "items": items, "series": series, "budget_restant": restant,
            "moyennes": {g: {"cout": round(c, 2), "duree_s": round(d)} for g, (c, d) in M.items()}}


def execute(ident, corps):
    """{items: [id], poser?: bool, modele?, consigne?, forcer?: bool} -> la série lancée."""
    from . import serie
    P = plan(ident)
    voulus = set(corps.get("items") or [])
    I = [x for x in P["items"] if x["id"] in voulus and x["par"] == "claude" and x["statut"] == "a_lancer"]
    if not I:
        raise ValueError("rien à lancer : choisir des éléments « à lancer »")
    poser = corps.get("poser") is not False
    if not poser:                                   # sans pose, la lecture naïve lirait le texte d'avant la révision
        revus = {x["chapitre"] for x in I if x["action"] == "reviser"}
        I = [x for x in I if not (x["action"] == "naif" and x["chapitre"] in revus)]
    cout = round(sum(x.get("cout") or 0 for x in I), 2)
    if P["budget_restant"] is not None and cout > P["budget_restant"] and not corps.get("forcer"):
        raise OverflowError("estimation %.2f $ pour %.2f $ restants au budget de l'objectif" % (cout, P["budget_restant"]))
    etapes = [{"chapitre": x["chapitre"], "action": x["action"], "consigne": x.get("consigne")} for x in I]
    return serie.cree({"etapes": etapes, "version": P["version"], "objectif": ident, "poser": poser,
                       "consigne": corps.get("consigne") or "", "modele": corps.get("modele")})
