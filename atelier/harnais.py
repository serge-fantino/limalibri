# -*- coding: utf-8 -*-
"""Le harnais : les portes qu'une version d'un chapitre doit passer avant d'être validée.

Repris de l'ancien cycle (recit/outils/cycle.py : cadre, style, relecture, répétitions, naïf),
dans l'atelier. Chaque porte rend : ok ou non, le nombre de relevés, et chaque relevé avec son
paragraphe (^id), l'extrait en cause et la règle. Une porte « avertissement » informe sans
bloquer.

Récit                                         Essai
  verrou      ce que le cadre exige             appui       ce que l'essai doit étayer
  séquence    l'ordre déclaré par plan          appareil    notes, citations, renvois
  budget      mots, paragraphes, tics           garde-fous  les contrôles de regles/essai.md
  interdits   les mots bannis du brief          répétitions
  garde-fous  les contrôles de regles/recit.md  naïf
  filet       les heuristiques de relecture
  répétitions groupes de quatre mots répétés
  formules    R14 : une formule sert une fois
  naïf        une lecture naïve a vu CE texte

Rien n'est corrigé ici : le harnais compte et désigne. Valider prend l'état présent comme
référence (validation.marque_valide) — si une porte bloque, il faut dire pourquoi (motif).
"""
import re
import json
import hashlib
import collections

from . import livre, regles, reecriture, validation

STOP = set("le la les un une des de du d l et à a en dans que qui ne pas plus est sont était ce cette ces il "
           "elle ils on se sa son ses leur pour par sur au aux avec sans y n s c tout".split())
TICS = {"et_c_est_max": (r", et c(?:'est|e n'est|'était)", "« , et c'est »"),
        "et_initial_max": (r"(?:^|[.!?»]\s+)Et ", "« Et » en tête de phrase"),
        "tirets_max": (r"—", "tiret cadratin")}


def _phrases(t):
    return [p for p in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", t)) if p.strip()]


def _texte_plat(t):
    t = re.sub(r"\[\^[^\]]+\]|\[@[^\]]+\]|\[sec:[^\]]+\]", "", t)
    return re.sub(r"[*_`]", "", t)


def blocs(slug, version):
    """[(id, texte)] : les paragraphes ; pour l'essai, les notes s'y ajoutent (« note:cle »)."""
    out = [(b, t) for b, t in reecriture._blocs(slug, version)]
    if version == "essai":
        md = (livre.dossier(slug) / "essai.md").read_text(encoding="utf-8")
        for m in re.finditer(r"^\[\^([^\]]+)\]:\s*(.+?)(?=^\[\^|^#|\Z)", md, re.S | re.M):
            out.append(("note:" + m.group(1), " ".join(m.group(2).split())))
    return out


def empreinte(slug, version):
    t = (livre.dossier(slug) / (version + ".md")).read_text(encoding="utf-8")
    return hashlib.sha256(re.sub(r"\s+", " ", re.sub(r"\s\^[a-z0-9]+\s*$", "", t, flags=re.M)).strip().encode()).hexdigest()[:16]


def _porte(ident, titre, releves, niveau="bloquant", resume="", ok=None):
    return {"id": ident, "titre": titre, "niveau": niveau, "n": len(releves),
            "ok": (not releves) if ok is None else ok, "releves": releves[:200], "resume": resume}


def _extrait(texte, m, large=60):
    a, b = max(0, m.start() - large), min(len(texte), m.end() + large)
    return ("…" if a else "") + texte[a:b].strip() + ("…" if b < len(texte) else "")


# ------------------------------------------------------------------ les portes

def _controles(version, B, niveau):
    """Les contrôles des garde-fous (regles/<version>.md) d'un niveau donné."""
    R = regles.lit(version)
    releves, bilan = [], []
    for e in R["elements"]:
        for c in e.get("controles") or []:
            if c.get("niveau", "bloquant") != niveau or c.get("erreur"):
                continue
            rx = re.compile(c["motif"], re.I)
            trouves = []
            for b, t in B:
                plat = _texte_plat(t)
                for ph in _phrases(plat):
                    for m in rx.finditer(ph):
                        trouves.append({"bloc": b, "extrait": _extrait(ph, m), "trouve": m.group(0).strip(),
                                        "regle": e["id"], "libelle": c.get("libelle") or e["titre"]})
            plafond = c.get("plafond")
            if trouves and (plafond is None or len(trouves) > plafond):
                releves += trouves
                bilan.append("%s%s : %d%s" % (e["id"] + " " if e["type"] == "regle" else "", c.get("libelle", ""), len(trouves),
                                              " (plafond %d)" % plafond if plafond else ""))
    return releves, bilan


def _repetitions(B):
    mots_par_bloc = []
    for b, t in B:
        for w in re.findall(r"[a-zàâçéèêëîïôûùüÿñæœ']+", _texte_plat(t).lower()):
            mots_par_bloc.append((w, b))
    g = collections.defaultdict(list)
    for i in range(len(mots_par_bloc) - 3):
        k = tuple(w for w, _ in mots_par_bloc[i:i + 4])
        g[k].append(mots_par_bloc[i][1])
    out = []
    for k, bs in g.items():
        if len(bs) > 1 and sum(1 for w in k if w not in STOP) >= 2:
            out.append({"bloc": bs[1], "extrait": " ".join(k), "trouve": " ".join(k),
                        "libelle": "répété %d fois (^%s)" % (len(bs), ", ^".join(dict.fromkeys(bs)))})
    return out


def portes_recit(slug):
    at = livre.atelier(slug)
    br = at.get("brief") or {}
    liens = at["links"].get("recit", {})
    B = blocs(slug, "recit")
    ids = [b for b, _ in B]
    P = []
    # verrou
    rel = []
    portees = collections.Counter(a for l in liens.values() for a in (l.get("assertions") or []))
    for aid, a in at["assertions"].items():
        if a.get("statut") == "obligatoire" and not portees.get(aid):
            rel.append({"bloc": None, "extrait": a["texte"], "regle": aid, "libelle": "assertion obligatoire portée par aucun paragraphe"})
        if a.get("statut") == "retiree" and portees.get(aid):
            b = next(b for b, l in liens.items() if aid in (l.get("assertions") or []))
            rel.append({"bloc": b, "extrait": a["texte"], "regle": aid, "libelle": "assertion retirée, encore portée"})
    for b in ids:
        l = liens.get(b) or {}
        if not l.get("assertions") and not l.get("ajout"):
            rel.append({"bloc": b, "extrait": dict(B)[b][:160], "libelle": "paragraphe hors verrou (ni assertion, ni ajout autorisé)"})
    quota = {x["id"]: x.get("ajouts") for x in br.get("beats") or []}
    ajouts = collections.Counter(l.get("plan") for l in liens.values() if l.get("ajout"))
    for plan, n in ajouts.items():
        q = quota.get(plan)
        if isinstance(q, int) and n > q:
            rel.append({"bloc": None, "extrait": "plan %s" % plan, "libelle": "%d ajouts hors verrou pour un quota de %d" % (n, q)})
    if not at["assertions"]:                  # migré sans cadre : rien à tenir encore, on le dit une fois
        P.append(_porte("verrou", "Verrou", [{"bloc": None, "extrait": "", "libelle": "pas encore de verrou : chapitre migré sans cadre"}],
                        niveau="avertissement", resume="pas encore de verrou"))
    else:
        P.append(_porte("verrou", "Verrou", rel, resume="%d assertions, %d portées" % (len(at["assertions"]), len(portees))))
    # séquence
    rel, declares = [], 0
    for beat in br.get("beats") or []:
        seq = beat.get("sequence") or []
        if not seq:
            continue
        declares += 1
        du_plan = [b for b in ids if (liens.get(b) or {}).get("plan") == beat["id"]]
        for i, b in enumerate(du_plan):
            g = (seq[i] if i < len(seq) else "").strip()
            attendu = "ajout" if g.startswith("ajout") else ",".join(x.strip() for x in g.split(",") if x.strip())
            l = liens.get(b) or {}
            reel = "ajout" if l.get("ajout") else ",".join(l.get("assertions") or [])
            if attendu != reel:
                rel.append({"bloc": b, "extrait": "déclaré : %s — le texte : %s" % (g or "(rien)", reel or "(rien)"),
                            "regle": "plan %s" % beat["id"], "libelle": "séquence déclarée non suivie"})
    P.append(_porte("sequence", "Séquence", rel, resume="%d plan(s) à séquence déclarée" % declares if declares else "aucune séquence déclarée"))
    # budget
    bud = br.get("budget") or {}
    texte = " ".join(_texte_plat(t) for _, t in B)
    mots, rel = len(texte.split()), []
    for cle, n, lib in (("mots", mots, "mots"), ("paragraphes", len(B), "paragraphes")):
        c = bud.get(cle) or {}
        if c.get("cible") and abs(n - c["cible"]) > (c.get("tolerance") or 0):
            rel.append({"bloc": None, "extrait": "%d %s pour une cible de %d ± %d" % (n, lib, c["cible"], c.get("tolerance") or 0),
                        "libelle": "hors budget (%s)" % lib})
    longues = [(b, ph) for b, t in B for ph in _phrases(_texte_plat(t)) if len(ph.split()) > 40]
    if bud.get("phrases_longues_max") is not None and len(longues) > bud["phrases_longues_max"]:
        rel += [{"bloc": b, "extrait": ph[:200], "libelle": "phrase longue (%d mots) — %d pour un plafond de %d" % (
            len(ph.split()), len(longues), bud["phrases_longues_max"])} for b, ph in longues]
    for cle, (motif, lib) in TICS.items():
        if bud.get(cle) is None:
            continue
        tr = [(b, m, t) for b, t in B for m in re.finditer(motif, _texte_plat(t))]
        if len(tr) > bud[cle]:
            rel += [{"bloc": b, "extrait": _extrait(_texte_plat(t), m), "trouve": m.group(0).strip(),
                     "libelle": "%s — %d pour un plafond de %d" % (lib, len(tr), bud[cle])} for b, m, t in tr]
    P.append(_porte("budget", "Budget", rel, resume="%d mots, %d paragraphes" % (mots, len(B))))
    # interdits du brief
    rel = []
    for mot in br.get("interdits") or []:
        rx = re.compile(r"\b%s\b" % re.escape(str(mot)), re.I)
        for b, t in B:
            for m in rx.finditer(_texte_plat(t)):
                rel.append({"bloc": b, "extrait": _extrait(_texte_plat(t), m), "trouve": m.group(0), "libelle": "mot interdit : %s" % mot})
    P.append(_porte("interdits", "Mots interdits", rel, resume="%d mot(s) interdit(s) au brief" % len(br.get("interdits") or [])))
    # garde-fous, filet
    rel, bilan = _controles("recit", B, "bloquant")
    P.append(_porte("gardefous", "Garde-fous", rel, resume="; ".join(bilan)))
    rel, bilan = _controles("recit", B, "avertissement")
    P.append(_porte("filet", "Filet de relecture", rel, niveau="avertissement", resume="; ".join(bilan)))
    # répétitions
    P.append(_porte("repetitions", "Répétitions", _repetitions(B)))
    # R14 : les formules réservées
    rel = []
    autres = [c["slug"] for c in livre.chapitres() if c.get("atelier") and c["slug"] != slug]
    for f in br.get("derogations") or []:
        f = str(f).strip()
        if len(f) < 4:
            continue
        rx = re.compile(re.escape(f), re.I)
        ici = [(b, m) for b, t in B for m in rx.finditer(t)]
        if len(ici) > 1:
            rel += [{"bloc": b, "extrait": f, "regle": "R14", "libelle": "formule réservée employée %d fois dans le chapitre" % len(ici)} for b, m in ici]
        for s in autres:
            p = livre.dossier(s) / "recit.md"
            if p.exists() and rx.search(p.read_text(encoding="utf-8")):
                rel.append({"bloc": None, "extrait": f, "regle": "R14", "libelle": "formule réservée, reprise dans « %s »" % s})
    P.append(_porte("formules", "Formules (R14)", rel, resume="%d formule(s) réservée(s)" % len(br.get("derogations") or [])))
    P.append(porte_naive(slug, "recit"))
    return P


def portes_essai(slug):
    at = livre.atelier(slug)
    B = blocs(slug, "essai")
    md = (livre.dossier(slug) / "essai.md").read_text(encoding="utf-8")
    P = []
    # appui : ce que le verrou demande à l'essai
    rel, ecarts = [], []
    for aid, a in at["assertions"].items():
        if a.get("statut") == "retiree":
            continue
        if not a.get("essai"):
            rel.append({"bloc": None, "extrait": a["texte"], "regle": aid, "libelle": "assertion sans appui dans l'essai"})
        elif a.get("ecart"):
            ecarts.append({"bloc": (a["essai"][0] or {}).get("bloc"), "extrait": a["ecart"].get("texte", ""), "regle": aid,
                           "libelle": "écart (%s)" % a["ecart"].get("type", "?")})
    P.append(_porte("appui", "Appui du verrou", rel, resume="%d assertion(s) sans appui, %d écart(s)" % (len(rel), len(ecarts))))
    P.append(_porte("ecarts", "Écarts avec le récit", ecarts, niveau="avertissement"))
    # l'appareil : notes, citations, renvois, sections
    rel = []
    appels = set(re.findall(r"\[\^([^\]]+)\](?!:)", md))
    defs = set(re.findall(r"^\[\^([^\]]+)\]:", md, re.M))
    for n in sorted(appels - defs):
        rel.append({"bloc": None, "extrait": "[^%s]" % n, "libelle": "note appelée, jamais définie"})
    for n in sorted(defs - appels):
        rel.append({"bloc": "note:" + n, "extrait": "[^%s]" % n, "libelle": "note définie, jamais appelée"})
    from . import sources
    T = sources.toutes()
    for b, t in B:
        for cle in re.findall(r"\[@([\w-]+)\]", t):
            o = T.get(cle)
            if T and not o:
                rel.append({"bloc": b, "extrait": "[@%s]" % cle, "libelle": "citation absente de la bibliographie (kb/sources)"})
            elif o and o.get("statut") in ("introuvable", "mal_attribuee", "doublon"):
                rel.append({"bloc": b, "extrait": "[@%s]" % cle, "libelle": "citation d'une œuvre %s" % o["statut"].replace("_", " ")})
    secs = re.findall(r"^#{2,6} .*\{#([\w-]+)\}\s*$", md, re.M)
    for s in sorted({x for x in secs if secs.count(x) > 1}):
        rel.append({"bloc": None, "extrait": "{#%s}" % s, "libelle": "identifiant de section en double"})
    for s in sorted(set(re.findall(r"\[sec:([\w-]+)\]", md)) - set(secs)):
        rel.append({"bloc": None, "extrait": "[sec:%s]" % s, "libelle": "renvoi vers une section inexistante"})
    P.append(_porte("appareil", "Appareil", rel, resume="%d notes, %d citations" % (len(defs), len(re.findall(r"\[@[\w-]+\]", md)))))
    rel, bilan = _controles("essai", B, "bloquant")
    P.append(_porte("gardefous", "Garde-fous", rel, resume="; ".join(bilan)))
    rel, bilan = _controles("essai", B, "avertissement")
    if rel:
        P.append(_porte("filet", "Filet de relecture", rel, niveau="avertissement", resume="; ".join(bilan)))
    P.append(_porte("repetitions", "Répétitions", _repetitions([x for x in B if not x[0].startswith("note:")])))
    P.append(porte_naive(slug, "essai"))
    return P


# ------------------------------------------------------------------ la lecture naïve (registre)

def _registre(slug):
    p = livre.dossier(slug) / "relectures.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def enregistre_naive(slug, version, demande, releves, traites):
    R = _registre(slug)
    R[version] = {"empreinte": empreinte(slug, version), "date": livre._maintenant(), "demande": demande,
                  "releves": releves, "traites": traites}
    (livre.dossier(slug) / "relectures.json").write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")


def porte_naive(slug, version):
    r = _registre(slug).get(version)
    e = empreinte(slug, version)
    if not r:
        return _porte("naif", "Lecture naïve", [], ok=False, resume="aucune lecture naïve enregistrée")
    if r["empreinte"] != e:
        return _porte("naif", "Lecture naïve", [], ok=False,
                      resume="le texte a changé depuis la lecture du %s (%s) : à relire" % (r["date"][:10], r["demande"]))
    return _porte("naif", "Lecture naïve", [], ok=True,
                  resume="lu le %s (%s) : %d relevé(s), %d traité(s)" % (r["date"][:10], r["demande"], r["releves"], r["traites"]))


# ------------------------------------------------------------------ le rapport, la validation

def rapport(slug, version):
    if version not in livre.VERSIONS:
        raise KeyError(version)
    livre.atelier(slug)
    P = portes_recit(slug) if version == "recit" else portes_essai(slug)
    bloquantes = [p for p in P if p["niveau"] == "bloquant" and not p["ok"]]
    E = validation.etat(slug)
    return {"chapitre": slug, "version": version, "portes": P, "ok": not bloquantes,
            "bloquantes": [p["id"] for p in bloquantes], "a_revalider": E.get("resume", {}).get(version, {})}


def valide(slug, version, motif=""):
    """Prendre l'état présent comme référence. Si une porte bloque, un motif est exigé."""
    R = rapport(slug, version)
    motif = (motif or "").strip()
    if not R["ok"] and not motif:
        raise ValueError("portes non passées (%s) : dire pourquoi valider quand même" % ", ".join(R["bloquantes"]))
    validation.marque_valide(slug, version, None, par="harnais")
    with (livre.dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "harnais", "version": version, "date": livre._maintenant(), "motif": motif,
                            "portes": {p["id"]: p["n"] if not p["ok"] else 0 for p in R["portes"]}},
                           ensure_ascii=False) + "\n")
    return rapport(slug, version)
