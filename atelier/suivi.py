# -*- coding: utf-8 -*-
"""Le suivi d'une version (récit ou essai) : où en est chaque chapitre, où en est le livre, et ce
qu'il reste à faire.

La note d'un chapitre est une progression par étapes pondérées, lue dans ses fichiers — ce qui a
été fait, pas ce qui est bon :

    étape         poids   essai                                         récit
    cadre           10    synopsis + question                           idem
    preparation     15    fiches (≥ 2) + un plan (verrou, squelette      storyboard : plans + micro-récits
                          ou texte en sections)
    texte           30    rédigé (au prorata des sections écrites)      rédigé (au prorata des plans couverts)
    appareil        15    sources connues, notes complètes,             assertions obligatoires portées
                          assertions appuyées                           par les paragraphes
    controles       15    portes bloquantes du harnais passées          idem
    relecture       15    lecture naïve à jour, annotations traitées,   idem
                          statut relu (revised) ou validé (locked)

Chaque manque devient une action, qui dit où aller. Le rapport du harnais (le plus coûteux) est gardé
en cache tant que les fichiers du chapitre et ses garde-fous n'ont pas changé.
"""
import re
import json
import time

import yaml

from . import livre, avancement

ETAPES = (("cadre", "Cadre", 10), ("preparation", "Préparation", 15), ("texte", "Texte", 30),
          ("appareil", "Appareil", 15), ("controles", "Contrôles", 15), ("relecture", "Relecture", 15))
_cache = {}


def _yaml(p):
    try:
        return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}
    except yaml.YAMLError:
        return {}


def _cle(slug, version):
    d = livre.dossier(slug)
    fs = sorted(d.glob("*")) + [livre.LIVRE / "regles" / (version + ".md")]
    return tuple((f.name, f.stat().st_mtime_ns) for f in fs if f.is_file())


def _rapport(slug, version):
    from . import harnais
    k = (livre.LIVRE, slug, version)
    cle = _cle(slug, version)
    if k in _cache and _cache[k][0] == cle:
        return _cache[k][1]
    try:
        r = harnais.rapport(slug, version)
    except Exception as e:                          # noqa: BLE001 — un rapport illisible ne bloque pas le suivi
        r = {"portes": [], "absent": True, "erreur": "%s" % e}
    _cache[k] = (cle, r)
    return r


def _action(etape, libelle, vue, tiroir=None, type_=None, poids=None):
    return {"etape": etape, "libelle": libelle, "vue": vue, "tiroir": tiroir, "type": type_ or etape, "gain": poids}


def chapitre(c, version, demandes):
    slug = c["slug"]
    d = livre.dossier(slug)
    br = _yaml(d / "brief.yaml")
    V = [a for s in _yaml(d / "verrou.yaml").get("sections") or [] for a in s.get("assertions") or []
         if a.get("statut") != "retiree"]
    pv = d / (version + ".md")
    brut = pv.read_text(encoding="utf-8") if pv.exists() else ""
    niv = avancement.niveau(c, version)
    ecrit = niv in ("brouillon", "relu", "valide")
    vue_texte = "%s/%s" % (slug, "essai/texte" if version == "essai" else "recit/texte")
    plan_c = "plan/c/%s" % slug
    E, A = {}, []

    def note(k, points, detail):
        mx = dict((x, p) for x, _, p in ETAPES)[k]
        E[k] = {"points": round(max(0, min(mx, points)), 1), "max": mx, "detail": detail}

    # cadre
    s, q = bool(br.get("synopsis")), bool(br.get("question"))
    note("cadre", 5 * s + 5 * q, " · ".join(x for x in ("synopsis" if s else "", "question" if q else "") if x) or "rien")
    if not (s and q):
        A.append(_action("cadre", "écrire %s" % " et ".join(x for x in ("le synopsis" if not s else "", "la question" if not q else "") if x),
                         plan_c, type_="synopsis", poids=10 - 5 * s - 5 * q))

    # préparation
    fiches = [str(x) for x in br.get("fiches") or []]
    if version == "essai":
        pf = 7.5 if len(fiches) >= 2 else 4 if fiches else 0
        sections = len(re.findall(r"^##\s", brut, re.M))
        plan_ok = bool(V) or avancement.squelette(brut) or (ecrit and sections >= 2)
        note("preparation", pf + 7.5 * plan_ok, "%d fiche(s) · %s" % (len(fiches), "verrou" if V else "squelette" if avancement.squelette(brut)
                                                                     else "texte en sections" if plan_ok else "pas de plan"))
        if len(fiches) < 2:
            A.append(_action("preparation", "choisir des fiches (%d)" % len(fiches), plan_c, type_="fiches", poids=7.5 - pf))
        if not plan_ok:
            A.append(_action("preparation", "amorcer : squelette et verrou", plan_c, type_="amorcer", poids=7.5))
    else:
        beats = br.get("beats") or []
        avec = sum(1 for b in beats if b.get("recits"))
        pts = 15 if beats and avec == len(beats) else 8 if beats else 0
        note("preparation", pts, "%d plan(s), %d avec micro-récits" % (len(beats), avec) if beats else "pas de storyboard")
        if pts < 15:
            A.append(_action("preparation", "écrire le storyboard" if not beats else "compléter les micro-récits",
                             "%s/recit/storyboard" % slug, type_="storyboard", poids=15 - pts))

    # texte
    if version == "essai":
        paras = [b for b in re.split(r"\n[ \t]*\n", brut) if b.strip() and not b.lstrip().startswith(("#", "[^"))]
        faits = [b for b in paras if not b.strip().startswith("*À écrire")]
        frac = len(faits) / len(paras) if paras else 0
        mots = len(re.sub(r"\^[a-z0-9]+|\[\^[^\]]+\]|\[@[\w-]+\]", "", brut).split()) if frac else 0
        note("texte", 30 * frac, "%d mots" % mots if frac == 1 else "%d/%d paragraphes écrits" % (len(faits), len(paras)) if paras else "rien d'écrit")
        if frac < 1:
            A.append(_action("texte", "écrire l'essai" if not faits else "finir l'essai (%d section(s) à écrire)" % (len(paras) - len(faits)),
                             vue_texte, type_="ecrire", poids=round(30 * (1 - frac), 1)))
    else:
        beats = br.get("beats") or []
        liens = (_yaml(d / "links.yaml").get("recit") or {})
        couverts = {(l or {}).get("plan") for l in liens.values()}
        frac = (sum(1 for b in beats if b.get("id") in couverts) / len(beats) if beats else 1) if brut.strip() else 0
        mots = len(re.sub(r"\^[a-z0-9]+", "", brut).split()) if brut.strip() else 0
        note("texte", 30 * frac, "%d mots" % mots if brut.strip() else "rien d'écrit")
        if frac < 1:
            A.append(_action("texte", "écrire le récit" if not brut.strip() else "écrire les plans manquants", vue_texte,
                             type_="ecrire", poids=round(30 * (1 - frac), 1)))

    # appareil
    if version == "essai":
        det, pts = [], 0
        if ecrit:
            from . import sources
            connues = set(sources.toutes()) if sources.existe() else set(livre.sources())
            cles = set(livre.CITATION.findall(brut))
            inconnues = sorted(k for k in cles if connues and k not in connues)
            p_cit = 0 if not cles else 5 * (1 - len(inconnues) / len(cles))
            appels = set(re.findall(r"\[\^([^\]]+)\](?!:)", brut))
            defs = set(re.findall(r"^\[\^([^\]]+)\]:", brut, re.M))
            orph = (appels - defs) | (defs - appels)
            p_notes = 5 if not orph else 2.5
            appuyees = sum(1 for a in V if a.get("essai"))
            p_app = 5 * appuyees / len(V) if V else 0
            pts = p_cit + p_notes + p_app
            det = ["%d source(s)%s" % (len(cles), ", %d inconnue(s)" % len(inconnues) if inconnues else ""),
                   "notes %s" % ("complètes" if not orph else "orphelines : %d" % len(orph)),
                   "%d/%d assertions appuyées" % (appuyees, len(V)) if V else "pas de verrou"]
            if not cles:
                A.append(_action("appareil", "citer les sources ([@cle])", vue_texte, type_="sources", poids=5))
            elif inconnues:
                A.append(_action("appareil", "%d source(s) absente(s) de la bibliographie" % len(inconnues),
                                 "%s/essai/biblio" % slug, type_="sources", poids=round(5 - p_cit, 1)))
            if orph:
                A.append(_action("appareil", "%d note(s) orpheline(s)" % len(orph), "%s/essai/notes" % slug, type_="notes", poids=2.5))
            if not V:
                A.append(_action("appareil", "établir le verrou (les assertions du chapitre)", plan_c, type_="verrou", poids=5))
            elif appuyees < len(V):
                A.append(_action("appareil", "%d assertion(s) sans appui dans l'essai" % (len(V) - appuyees), vue_texte,
                                 tiroir="harnais", type_="appui", poids=round(5 - p_app, 1)))
        note("appareil", pts, " · ".join(det) or "rien d'écrit")
    else:
        pts, det = 0, "rien d'écrit"
        if ecrit:
            ob = [a for a in V if a.get("statut") == "obligatoire"]
            liens = (_yaml(d / "links.yaml").get("recit") or {})
            portees = {x for l in liens.values() for x in ((l or {}).get("assertions") or [])}
            n = sum(1 for a in ob if a["id"] in portees)
            pts = 15 * n / len(ob) if ob else 0
            det = "%d/%d assertions portées" % (n, len(ob)) if ob else "pas de verrou"
            if not ob:
                A.append(_action("appareil", "établir le verrou (les assertions du chapitre)", plan_c, type_="verrou", poids=15))
            elif n < len(ob):
                A.append(_action("appareil", "%d assertion(s) portée(s) par aucun paragraphe" % (len(ob) - n), vue_texte,
                                 tiroir="harnais", type_="appui", poids=round(15 - pts, 1)))
        note("appareil", pts, det)

    # contrôles et relecture : le harnais
    R = _rapport(slug, version) if ecrit and d.is_dir() else {"portes": [], "absent": True}
    bloq = [p for p in R.get("portes") or [] if p["niveau"] == "bloquant" and p["id"] != "naif"]
    ko = [p for p in bloq if not p["ok"]]
    note("controles", 15 * (len(bloq) - len(ko)) / len(bloq) if bloq else 0,
         ("%d/%d portes passées" % (len(bloq) - len(ko), len(bloq))) if bloq else "rien à contrôler")
    if ko:
        A.append(_action("controles", "harnais : %s" % ", ".join(p["titre"].lower() for p in ko), vue_texte,
                         tiroir="harnais", type_="harnais", poids=round(15 * len(ko) / len(bloq), 1)))
    naif = next((p for p in R.get("portes") or [] if p["id"] == "naif"), None)
    ouvertes = [a for a in livre.annotations(slug) if a.get("version") == version and a.get("etat") == "ouverte"] if d.is_dir() else []
    p_naif = 5 if naif and naif["ok"] else 0
    p_ann = (5 if not ouvertes else 2.5 if len(ouvertes) <= 3 else 0) if ecrit else 0
    p_st = {"relu": 3, "valide": 5}.get(niv, 0)
    note("relecture", p_naif + p_ann + p_st, " · ".join([
        "lecture naïve %s" % ("à jour" if p_naif else "à faire"), "%d annotation(s) ouverte(s)" % len(ouvertes),
        {"relu": "relu", "valide": "validé"}.get(niv, "brouillon" if ecrit else "—")]))
    if ecrit:
        if not p_naif:
            A.append(_action("relecture", "lecture naïve" + (" (le texte a changé)" if naif and "changé" in (naif.get("resume") or "") else ""),
                             vue_texte, tiroir="harnais", type_="naif", poids=5))
        if ouvertes:
            A.append(_action("relecture", "%d annotation(s) ouverte(s)" % len(ouvertes), vue_texte, tiroir="annotations",
                             type_="annotations", poids=round(5 - p_ann, 1)))
        if niv == "brouillon":
            A.append(_action("relecture", "passer en relu, puis en validé", plan_c, type_="statut", poids=5))
        # la relecture critique : jamais faite, ou le texte a changé depuis la dernière (hors barème)
        R = [x for x in demandes.get(slug, []) if x.get("type") == "relecture" and x.get("version") in (None, version)]
        if not any(x.get("etat") in ("en_attente", "en_cours") for x in R):
            faites = sorted((x for x in R if x.get("etat") in ("decidee", "prete")), key=lambda x: x["cree"])
            depuis = None
            if faites:
                import datetime
                try:
                    depuis = datetime.datetime.fromisoformat(faites[-1]["cree"]).timestamp()
                except ValueError:
                    depuis = None
            if not faites:
                A.append(_action("relecture", "relecture critique", vue_texte, type_="relecture"))
            elif depuis and pv.exists() and pv.stat().st_mtime > depuis:
                A.append(_action("relecture", "relecture critique (le texte a changé depuis)", vue_texte, type_="relecture"))

    # un chapitre qui n'a qu'un synopsis : une seule action, développer le brief (synopsis et question s'ils
    # manquent, fiches, déroulé, squelette et verrou) — c'est ce que fait la proposition de Claude
    if version == "essai" and niv in ("vide", "synopsis"):
        faits = [a for a in A if a["type"] in ("synopsis", "fiches", "amorcer")]
        if faits:
            A = [_action("preparation", "développer le brief", plan_c, type_="brief",
                         poids=round(sum(a.get("gain") or 0 for a in faits), 1))] + [a for a in A if a not in faits]

    # les demandes du chapitre qui attendent l'auteur
    for x in demandes.get(slug, []):
        if x.get("etat") == "prete" and (x.get("version") in (None, version) or x.get("type") == "redaction" and version == "essai"):
            A.append(_action("demandes", "à décider : %s" % (x.get("titre") or x["id"])[:80], vue_texte, tiroir=x["id"], type_="decider"))
        if x.get("type") == "redaction" and version == "essai" and x.get("etat") == "decidee" and x.get("manques"):
            A.append(_action("demandes", "%d manque(s) signalé(s) par la rédaction" % x["manques"], vue_texte, tiroir=x["id"], type_="manques"))

    score = round(sum(e["points"] for e in E.values()))
    mesures = {"niveau": niv, "score": score, "fiches": len(fiches), "annotations": len(ouvertes) if ecrit else 0,
               "naif": bool(p_naif), "portes_ko": len(ko), "portes_ko_titres": [p["titre"] for p in ko], "controles": bool(bloq) and not ko, "ecrit": ecrit}
    return {"slug": slug, "mesures": mesures, "numero": c.get("numero"), "titre": c["title"], "partie": c.get("partie"),
            "partie_titre": c.get("partie_titre"), "niveau": niv, "score": score, "etapes": E, "actions": A}


def _demandes():
    """Les demandes utiles au suivi, par chapitre (chapitres et base)."""
    from . import reecriture
    out = {}
    try:
        for x in reecriture.liste_toutes():
            ch = x.get("chapitre") if x.get("chapitre") != "_kb" else None
            if x.get("type") == "redaction":
                d = reecriture.lit("_kb", x["id"])
                ch = d["cible"].get("chapitre")
                x = dict(x, manques=len((d.get("resultat") or {}).get("manques") or []) if d.get("etat") == "decidee" else 0)
                x["chapitre"] = ch
            if x.get("type") == "relecture":            # une relecture vaut pour chacun de ses chapitres
                for c in x.get("chapitres") or []:
                    out.setdefault(c, []).append(dict(x, chapitre=c))
                continue
            if ch:
                out.setdefault(ch, []).append(x)
    except Exception:                                   # noqa: BLE001
        pass
    # d'une rédaction, seule la plus récente compte
    for ch, L in out.items():
        red = sorted((x for x in L if x.get("type") == "redaction"), key=lambda x: x["cree"])
        out[ch] = [x for x in L if x.get("type") != "redaction"] + red[-1:]
    return out


def un(version, slug):
    """Le suivi d'un seul chapitre (le bandeau « prochaine étape »)."""
    if version not in livre.VERSIONS:
        raise KeyError(version)
    c = next((x for x in livre.chapitres() if x["slug"] == slug), None)
    if not c:
        raise KeyError(slug)
    r = chapitre(c, version, _demandes())
    r["bareme"] = [{"id": k, "titre": t, "max": p} for k, t, p in ETAPES]
    return r


def suivi(version):
    if version not in livre.VERSIONS:
        raise KeyError(version)
    t0 = time.time()
    D = _demandes()
    from . import travail, objectifs
    T = travail.par_chapitre()
    C = [chapitre(c, version, D) for c in livre.chapitres() if version in (c.get("versions") or [version]) or True]
    for c in C:                                        # le travail en cours du chapitre (demandes, manques)
        c["travail"] = travail.public({c["slug"]: T.get(c["slug"]) or {"en_file": [], "en_cours": [], "a_decider": [],
                                                                         "manques": 0, "demandes": set()}})[c["slug"]]
    n = len(C) or 1
    etapes = {k: {"titre": t, "max": p, "moyenne": round(sum(c["etapes"][k]["points"] for c in C) / n, 1),
                  "complets": sum(1 for c in C if c["etapes"][k]["points"] >= p)} for k, t, p in ETAPES}
    repartition = {v: sum(1 for c in C if c["niveau"] == v) for v in avancement.NIVEAUX}
    groupes = {}
    for c in C:
        for a in c["actions"]:
            g = groupes.setdefault(a["type"], {"type": a["type"], "etape": a["etape"], "chapitres": [], "gain": 0})
            g["chapitres"].append({"slug": c["slug"], "numero": c["numero"], "titre": c["titre"], "libelle": a["libelle"],
                                   "vue": a["vue"], "tiroir": a["tiroir"]})
            g["gain"] += a.get("gain") or 0
    ordre = {k: i for i, (k, _, _) in enumerate(ETAPES)}
    G = sorted(groupes.values(), key=lambda g: (ordre.get(g["etape"], 9), -len(g["chapitres"])))
    for g in G:
        g["gain"] = round(g["gain"] / n, 1)            # ce que le livre gagnerait, en points de moyenne
    S = {"chapitres": C}
    O = objectifs.evalue_tous(version, S, T)
    try:                                               # le pilotage de chaque objectif : son cadrage, son plan
        from . import pilotage, reecriture
        K = {}
        for x in reecriture.liste("_kb"):
            if x.get("type") == "cadrage" and x.get("etat") not in ("retiree", "remplacee"):
                K.setdefault("_", []).append(x)
        for o in O:
            P = pilotage.lit(o["id"])
            ks = [x for x in K.get("_", []) if reecriture.lit("_kb", x["id"]).get("cible", {}).get("objectif") == o["id"]]
            k = max(ks, key=lambda x: x["cree"]) if ks else None
            o["pilotage"] = {"plan": P and P["etat"], "cadrage": k and {"id": k["id"], "etat": k["etat"]},
                             "actions": P and sum(len(ph["actions"]) for ph in P["phases"]),
                             "faites": P and sum(1 for ph in P["phases"] for a in ph["actions"] if a["etat"] in ("faite", "sautee"))}
    except Exception:                                  # noqa: BLE001 — le suivi passe avant
        pass
    autres = sum(1 for o in objectifs.lit_tous() if o.get("version", "essai") != version)
    sans = travail.public({travail.SANS: T[travail.SANS]})[travail.SANS] if travail.SANS in T else None
    return {"version": version, "objectifs": O, "objectifs_autre_version": autres, "sans_chapitre": sans,
            "score": round(sum(c["score"] for c in C) / n), "etapes": etapes,
            "repartition": repartition, "chapitres": C, "groupes": G, "calcule_en": round(time.time() - t0, 2),
            "bareme": [{"id": k, "titre": t, "max": p} for k, t, p in ETAPES]}
