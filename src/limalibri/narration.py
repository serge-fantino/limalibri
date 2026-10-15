# -*- coding: utf-8 -*-
"""Écrire le récit d'un chapitre depuis son storyboard : Claude écrit les paragraphes, l'auteur pose.

Une demande « recit » (kb/demandes/t-*.json ; capacité « ecrire_recit »). Sa portée : le chapitre entier, un
plan du storyboard (A, B…), ou un seul paragraphe d'un plan (son rang : le micro-récit qu'il réalise).
Claude reçoit les règles du récit, l'intention de la version, le storyboard du chapitre (l'intention, la
tenue, chaque plan avec ses micro-récits, sa séquence, ses assertions), le verrou (le texte des
assertions), le récit déjà écrit du chapitre (ce qui entoure la portée) et la fin du récit du chapitre
précédent. Il lit l'essai et les fiches (Read, Grep) : le récit ne dit rien que l'essai n'établisse. Pas de
web. Fable par défaut : c'est un travail d'écriture.

Il rend, pour chaque plan de la portée, ses paragraphes dans l'ordre — un par micro-récit, plus les ajouts
permis — chacun avec les assertions qu'il porte (ou « ajout »). Poser réécrit recit.md : les paragraphes du
plan (ou le paragraphe du rang) sont remplacés, le reste est gardé tel quel, avec ses ancres ; links.yaml
suit (plan, assertions, ajout) ; l'ancien récit est archivé dans historique/.

Un plan d'en-tête (livre.en_tete : l'ouverture d'Un Monde) s'écrit par sa capacité du livre (capacites_livre.py,
primitive plan_de_tete) : la même demande t-, avec « capacite » dans sa cible — Claude reçoit la section des règles
qui donne la voix de ce texte et la consigne du livre, et rend les micro-récits avec les paragraphes ; poser met le
plan en tête du storyboard (créé s'il manque). Le récit ordinaire laisse ces plans tels quels.
"""
import re
import json
import time
import secrets

from claude_agent_sdk import ClaudeAgentOptions

from . import livre, reecriture

SLUG_KB = "_kb"
DEFAUT = "claude-fable-5-1"
ANCRE = re.compile(r"[ \t]+\^([a-z0-9]+)[ \t]*$")

SYSTEME = """Tu écris le RÉCIT du livre « {titre} ». Le livre a deux versions alignées chapitre pour chapitre :
l'essai, qui explique, et le récit, qui raconte. Le storyboard du chapitre (dans le message) est ton cadre :
chaque plan a un lieu, un temps, une ambiance, une attaque, une chute, et ses micro-récits — un par
paragraphe, dans l'ordre. Un paragraphe réalise son micro-récit : il le fait voir, il ne le résume pas.

La rigueur vient de l'essai : chaque plan porte des assertions du verrou (leur texte est dans le message),
dans l'ordre de sa séquence. Le récit ne dit rien que l'essai n'établisse ; lis l'essai du chapitre
(chapters/<slug>/essai.md) pour les faits, les noms, les chiffres. Tu peux lire les fiches (kb/fiches/) et le
récit des autres chapitres (chapters/*/recit.md). Pas de web. Les règles du récit, ci-dessous, priment pour
la forme : la voix, le registre, ce qui est interdit.

Écris seulement ce que la portée demande ; le reste du récit est dans le message pour la continuité (une
attaque qui reprend la chute d'avant, aucune formule déjà servie). Rends, pour chaque plan de la portée, ses
paragraphes dans l'ordre — EXACTEMENT un par micro-récit, le n-ième réalisant le n-ième micro-récit (le texte
et le storyboard restent alignés ligne à ligne ; un paragraphe hors verrou est un micro-récit dont la séquence
dit « ajout ») : texte (un paragraphe, sans titre, sans ancre ^), assertions (les identifiants du verrou qu'il
porte), ajout (vrai pour un paragraphe hors verrou) ; et
des remarques : ce que tu n'as pas pu faire voir, les écarts au storyboard que tu proposes. Tout en français.

## Les règles du récit
{regles}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "plans": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"},
            "paragraphes": {"type": "array", "items": {"type": "object", "properties": {
                "texte": {"type": "string"}, "assertions": {"type": "array", "items": {"type": "string"}},
                "ajout": {"type": "boolean"}}, "required": ["texte"]}}},
            "required": ["id", "paragraphes"]}},
        "remarques": {"type": "string"}},
    "required": ["plans"]}


def _yaml(p):
    import yaml
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}


def _brief(slug):
    return _yaml(livre.dossier(slug) / "brief.yaml")


def _verrou(slug):
    return {str(a["id"]): a for s in _yaml(livre.dossier(slug) / "verrou.yaml").get("sections") or []
            for a in s.get("assertions") or [] if a.get("statut") != "retiree"}


def _paragraphes(slug):
    """Le récit présent, dans l'ordre : [(id ou None, texte brut du bloc)] — les séparateurs gardés."""
    p = livre.dossier(slug) / "recit.md"
    if not p.exists():
        return []
    out = []
    for b in re.split(r"\n[ \t]*\n", p.read_text(encoding="utf-8").strip("\n")):
        if not b.strip():
            continue
        m = ANCRE.search(b.rstrip())
        out.append((m.group(1) if m else None, ANCRE.sub("", b.rstrip()).strip() if m else b.strip()))
    return out


def _liens(slug):
    return (_yaml(livre.dossier(slug) / "links.yaml").get("recit") or {})


def par_plan(slug):
    """{plan: [(id, texte)]} dans l'ordre du texte ; un paragraphe sans plan suit le plan d'avant."""
    L = _liens(slug)
    out, cour = {}, None
    for i, t in _paragraphes(slug):
        if i is None:
            continue
        cour = (L.get(i) or {}).get("plan") or cour or "?"
        out.setdefault(str(cour), []).append((i, t))
    return out


def _effectifs(g):
    """[(rang, (id, texte, lien))] triés : un paragraphe qui porte son rang (lien « rang », le micro-récit qu'il
    réalise) tient sa place ; les autres prennent les places libres, dans l'ordre du texte. Sans rang
    explicite, c'est l'ordre du texte — le cas des récits écrits d'un trait."""
    pris = {int(x[2]["rang"]) for x in g if x[2].get("rang")}
    out, k = [], 1
    for x in g:
        if x[2].get("rang"):
            out.append((int(x[2]["rang"]), x))
            continue
        while k in pris:
            k += 1
        out.append((k, x))
        pris.add(k)
    return sorted(out, key=lambda y: y[0])


def _materialise(g):
    """Le groupe d'un plan, chaque paragraphe avec son rang écrit (avant de le modifier à la main)."""
    return [(x[0], x[1], dict(x[2], rang=r)) for r, x in _effectifs(g)]


def portee_lisible(c, plan=None, rang=None):
    if plan and rang:
        return "%s — plan %s, paragraphe %s" % (c["title"], plan, rang)
    if plan:
        return "%s — plan %s" % (c["title"], plan)
    return c["title"]


def cree(corps):
    """{chapitre, plan?, rang? (1, 2…), capacite? (une capacité du livre : son plan d'en-tête), consigne?, modele?, poser?}."""
    from . import capacites_livre
    slug = (corps.get("chapitre") or "").strip()
    c = next((x for x in livre.chapitres() if x["slug"] == slug), None)
    if not c:
        raise ValueError("chapitre inconnu : %s" % slug)
    beats = _brief(slug).get("beats") or []
    plan = str(corps.get("plan") or "").strip() or None
    rang = int(corps["rang"]) if corps.get("rang") else None
    capacite = (corps.get("capacite") or "").strip() or None
    if not capacite and plan and plan in livre.plans_en_tete(slug):     # un plan d'en-tête : sa capacité l'écrit
        cap = capacites_livre.de_plan(plan)
        if not cap:
            raise ValueError("le plan %s est à part (en-tête) : la capacité du livre qui l'écrit n'est plus déclarée" % plan)
        capacite = cap["id"]
    if capacite:
        cap = capacites_livre.une(capacite)
        plan, rang = cap["plan"]["id"], None
    elif not beats:
        raise ValueError("le chapitre n'a pas de storyboard : le récit s'écrit depuis ses plans")
    if not capacite and plan and plan not in {str(b.get("id")) for b in beats}:
        raise ValueError("plan inconnu : %s" % plan)
    if rang and not plan:
        raise ValueError("un paragraphe se désigne par son plan et son rang")
    if rang is not None and rang < 1:
        raise ValueError("rang : 1, 2…")
    choisi = reecriture._choix_modele(corps) or (cap.get("modele") if capacite else None)
    d = {"id": "t-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "recit", "portee": "recit", "mode": "ecriture",
         "consigne": (corps.get("consigne") or "").strip(),
         "modele_choisi": choisi or (None if reecriture.modele("recit") else DEFAUT),
         "poser": bool(corps.get("poser")),
         "cible": {"chapitre": slug, "version": "recit", "plan": plan, "rang": rang, **({"capacite": capacite} if capacite else {})},
         "etat": "en_attente", "cree": livre._maintenant(), "rang": time.time()}
    d["titre"] = "%s — %s%s" % (cap["libelle"][:1].upper() + cap["libelle"][1:] if capacite else "Récit",
                                "%s. " % c["numero"] if c.get("numero") else "", c["title"] if capacite else portee_lisible(c, plan, rang))
    reecriture._ecrit(SLUG_KB, d)
    from . import file
    return file.part(SLUG_KB, d, "narration", "demarre", d["id"])


def _plan_texte(b, V):
    if livre.en_tete(b):
        return ["## Plan %s — %s (à part : un texte en tête du chapitre, dans une autre voix ; il n'est pas à écrire ici)"
                % (b.get("id"), b.get("title") or "")]
    L = ["## Plan %s — %s" % (b.get("id"), b.get("title") or "")]
    for k in ("lieu", "temps", "ambiance", "attaque", "chute"):
        if b.get(k):
            L.append("%s : %s" % (k, " ".join(str(b[k]).split())))
    L.append("ajouts permis : %s" % (b.get("ajouts") or 0))
    if b.get("sequence"):
        L.append("séquence : " + "  /  ".join(str(x) for x in b["sequence"]))
    if b.get("assertions"):
        L.append("assertions :")
        L += ["- %s %s" % (x, " ".join((V.get(str(x)) or {}).get("texte", "(absente du verrou)").split())) for x in b["assertions"]]
    if b.get("recits"):
        L.append("micro-récits (un par paragraphe, dans l'ordre) :")
        L += ["%d. %s" % (i + 1, r) for i, r in enumerate(b["recits"])]
    if b.get("note"):
        L.append("note : %s" % b["note"])
    return L


def compile_contexte(d):
    from . import plan as P_, regles
    if d["cible"].get("capacite"):
        return _contexte_tete(d)
    slug, plan, rang = d["cible"]["chapitre"], d["cible"].get("plan"), d["cible"].get("rang")
    systeme = SYSTEME.format(titre=livre.meta().get("titre", ""), regles=regles.texte_pour_claude("recit") or "(aucune)")
    P = P_.lit()
    ordre = [(p, c) for p in P["parties"] for c in p["chapitres"]]
    i = next(k for k, (_, c) in enumerate(ordre) if c["slug"] == slug)
    p, c = ordre[i]
    br, V = _brief(slug), _verrou(slug)
    intention = livre.intention_version("recit")
    L = (["# Le récit, selon l'auteur", intention, ""] if intention else []) + [
        "# Le chapitre : %s — %s" % (slug, c["title"]), "Sa partie : %s%s" % (p["title"], " — " + p["arc"] if p.get("arc") else ""),
        "Son essai : chapters/%s/essai.md (à lire pour les faits)" % slug, ""]
    for k, lib in (("intent", "Intention"), ("tenue", "Tenue")):
        v = br.get(k)
        if v:
            L.append("%s : %s" % (lib, " · ".join("%s : %s" % (a, " ".join(str(b).split())) for a, b in v.items())
                                  if isinstance(v, dict) else " ".join(str(v).split())))
    if br.get("constraints"):
        L += ["Interdits propres au storyboard :"] + ["- " + x for x in br["constraints"]]
    L += ["", "# Le storyboard"]
    for b in br.get("beats") or []:
        L += [""] + _plan_texte(b, V)

    # ce que la demande écrit
    L += ["", "# La portée"]
    if not plan:
        L.append("Le chapitre entier : tous les plans, dans l'ordre (sauf les plans à part, en tête : ils restent tels quels).")
    elif not rang:
        L.append("Le plan %s seulement : tous ses paragraphes, exactement un par micro-récit." % plan)
    else:
        L.append("Le plan %s, paragraphe %d seulement : UN paragraphe, qui réalise le micro-récit %d du plan. "
                 "Rends le plan %s avec ce seul paragraphe." % (plan, rang, rang, plan))

    # le récit présent, pour la continuité
    G = _groupes(slug)
    if any(G.values()):
        L += ["", "# Le récit déjà écrit du chapitre (paragraphes par plan, numérotés par micro-récit ; ce qui est dans "
              "la portée sera remplacé)"]
        for b in br.get("beats") or []:
            ps = _effectifs(G.get(str(b.get("id"))) or [])
            L.append("\n## %s%s" % (b.get("id"), "" if ps else " — rien d'écrit"))
            for r, (_, t, _l) in ps:
                dedans = (not plan and not livre.en_tete(b)) or (str(b.get("id")) == plan and (not rang or r == rang))
                L.append("%d.%s %s" % (r, " [à remplacer]" if dedans else "", t))
    if i > 0:
        pc = ordre[i - 1][1]
        prec = [t for x, t in _paragraphes(pc["slug"]) if x]
        L += ["", "# La fin du récit du chapitre précédent : %s — %s" % (pc["slug"], pc["title"])]
        L += prec[-2:] or ["(pas encore écrit)"]
    if d.get("consigne"):
        L += ["", "# La consigne de l'auteur", d["consigne"]]
    from . import refs
    L.append(refs.annexe(d.get("consigne")))
    return systeme, "\n".join(L)


# ------------------------------------------------------------------ un plan d'en-tête (capacité du livre)

SYSTEME_TETE = """Tu écris {libelle} d'un chapitre du livre « {titre} ». Le livre a deux versions alignées chapitre pour
chapitre : l'essai, qui explique, et le récit, qui raconte. Ce que tu écris n'est ni l'un ni l'autre : un texte à part,
en tête du chapitre du récit, avant son premier plan, rendu à part (italique, un blanc après). Sa voix, sa matière et
sa forme sont dans la section « {regle} » des règles ci-dessous et dans la consigne du livre : pour ce texte, elles
priment sur la voix du récit. Les autres règles du récit valent aussi, sauf ce qu'elles disent de la voix.

Les faits viennent de l'essai : lis l'essai du chapitre (chapters/{slug}/essai.md). Tu peux lire les fiches
(kb/fiches/) et le récit des chapitres (chapters/*/recit.md). Pas de web. Tu ne dis rien que l'essai n'établisse.

Longueur : {longueur}. Rends le plan « {plan} » avec ses paragraphes, dans l'ordre ; pour chacun : texte (un
paragraphe, sans titre, sans ancre ^) et micro (le micro-récit qu'il réalise : ce qu'il fait voir, en une phrase ; il
devient la ligne du storyboard en regard). Et des remarques : ce que tu n'as pas pu faire, ce que tu proposes. Tout en
français.

## La voix de ce texte : {regle}
{texte_regle}

## La consigne du livre pour ce texte
{consigne}

## Les règles du récit
{regles}"""

SCHEMA_TETE = {
    "type": "object",
    "properties": {
        "plans": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"},
            "paragraphes": {"type": "array", "items": {"type": "object", "properties": {
                "texte": {"type": "string"}, "micro": {"type": "string"}}, "required": ["texte", "micro"]}}},
            "required": ["id", "paragraphes"]}},
        "remarques": {"type": "string"}},
    "required": ["plans"]}


def _longueur(cap):
    L = []
    if cap.get("mots"):
        L.append("%d à %d mots en tout" % tuple(cap["mots"]))
    if cap.get("paragraphes"):
        a, b = cap["paragraphes"]
        L.append("%d paragraphe%s" % (a, "s" if a > 1 else "") if a == b else "%d à %d paragraphes" % (a, b))
    return ", ".join(L) or "celle que la règle donne"


def _texte_tete(slug, pid):
    """Les paragraphes d'un plan (d'en-tête), dans l'ordre."""
    return [t for _, (_, t, _) in _effectifs(_groupes(slug).get(pid) or [])]


def _contexte_tete(d):
    from . import plan as P_, regles, capacites_livre
    slug = d["cible"]["chapitre"]
    cap = capacites_livre.une(d["cible"]["capacite"])
    pid = cap["plan"]["id"]
    sec = capacites_livre.regle(cap)
    systeme = SYSTEME_TETE.format(
        libelle=cap["libelle"].replace("écrire ", "", 1), titre=livre.meta().get("titre", ""), slug=slug, plan=pid,
        regle=(sec or {}).get("titre") or cap.get("regle") or "(aucune)", longueur=_longueur(cap),
        texte_regle=(sec or {}).get("texte") or "(la section n'est pas encore écrite : suis la consigne du livre)",
        consigne=cap.get("consigne") or "(aucune)", regles=regles.texte_pour_claude("recit") or "(aucune)")
    P = P_.lit()
    ordre = [(p, c) for p in P["parties"] for c in p["chapitres"]]
    i = next(k for k, (_, c) in enumerate(ordre) if c["slug"] == slug)
    p, c = ordre[i]
    ch = next((x for x in livre.chapitres() if x["slug"] == slug), {})
    br = _brief(slug)
    L = ["# Le chapitre : %s — %s" % (slug, c["title"])]
    if ch.get("periode"):
        L.append("Son moment : %s" % ch["periode"])
    L += ["Sa partie : %s%s" % (p["title"], " — " + p["arc"] if p.get("arc") else ""),
          "Son essai : chapters/%s/essai.md (à lire pour les faits)" % slug]
    if isinstance(br.get("intent"), dict) and br["intent"]:
        L.append("Ce que le chapitre fait comprendre : " + " · ".join(" ".join(str(v).split()) for v in br["intent"].values()))
    ordinaires = [b for b in br.get("beats") or [] if not livre.en_tete(b)]
    if ordinaires:
        L += ["", "# Le récit qui suit ton texte : ses plans (pour savoir où il entre, pas pour le résumer)"]
        L += ["- %s %s — attaque : %s" % (b.get("id"), b.get("title") or "", " ".join(str(b.get("attaque") or "—").split()))
              for b in ordinaires]
    G = _groupes(slug)
    debut = [t for b in ordinaires for _, (_, t, _) in _effectifs(G.get(str(b.get("id"))) or [])][:2]
    if debut:
        L += ["", "# Le récit commence ainsi (ton texte le précède : n'en reprends ni les images ni les formules)"] + debut
    deja = _texte_tete(slug, pid)
    if deja:
        L += ["", "# Le texte actuel de ce plan (à remplacer en entier)"] + deja
    if i > 0:
        pc = ordre[i - 1][1]
        prec = _texte_tete(pc["slug"], pid) if livre.dossier(pc["slug"]).is_dir() else []
        if prec:
            L += ["", "# Le même texte, au chapitre précédent (%s — %s) : ne reprends aucune de ses formules"
                  % (pc["slug"], pc["title"])] + prec
    L += ["", "Les textes de ce plan dans les autres chapitres : chapters/*/recit.md, les paragraphes du plan « %s » "
          "dans chapters/*/links.yaml — une formule ne sert qu'une fois." % pid]
    if d.get("consigne"):
        L += ["", "# La consigne de l'auteur", d["consigne"]]
    from . import refs
    L.append(refs.annexe(d.get("consigne")))
    return systeme, "\n".join(L)


def _resultat_tete(d, sortie):
    from . import capacites_livre
    cap = capacites_livre.une(d["cible"]["capacite"])
    pid = cap["plan"]["id"]
    ps = []
    for p in sortie.get("plans") or []:
        if str(p.get("id") or "").strip() not in (pid, ""):
            continue
        ps += [{"texte": _propre(x.get("texte")), "micro": " ".join(str(x.get("micro") or "").split()),
                "assertions": [], "ajout": True} for x in p.get("paragraphes") or [] if _propre(x.get("texte"))]
    mots = sum(len(x["texte"].split()) for x in ps)
    hors = []
    if cap.get("mots") and not cap["mots"][0] <= mots <= cap["mots"][1]:
        hors.append("%d mots pour %d à %d" % (mots, cap["mots"][0], cap["mots"][1]))
    if cap.get("paragraphes") and not cap["paragraphes"][0] <= len(ps) <= cap["paragraphes"][1]:
        hors.append("%d paragraphes pour %d à %d" % (len(ps), cap["paragraphes"][0], cap["paragraphes"][1]))
    return {"plans": [{"id": pid, "paragraphes": ps}] if ps else [], "remarques": sortie.get("remarques") or "", "mots": mots,
            "capacite": cap["id"], "controle": {"inconnues": [], "non_portees": [], "ecarts": [], "longueur": hors}}


def _pose_plan_tete(slug, capacite, R):
    """Le plan d'en-tête dans brief.yaml : créé en tête s'il manque, ses micro-récits remplacés par ceux de la réponse."""
    from . import capacites_livre
    from ruamel.yaml.comments import CommentedMap, CommentedSeq
    cap = capacites_livre.une(capacite)
    pid = cap["plan"]["id"]
    ps = next((p["paragraphes"] for p in R["plans"] if p["id"] == pid), None)
    if not ps:
        raise ValueError("rien à poser : la réponse n'a aucun paragraphe pour le plan %s" % pid)
    p = livre.dossier(slug) / "brief.yaml"
    y = livre.yaml_rt()
    doc = (y.load(p.read_text(encoding="utf-8")) if p.exists() else None) or CommentedMap()
    if doc.get("beats") is None:
        doc["beats"] = CommentedSeq()
    beats = doc["beats"]
    b = next((x for x in beats if str(x.get("id")) == pid), None)
    if b is None:
        b = CommentedMap()
        b["id"] = pid
        b["sorte"] = cap["id"]
        b["title"] = cap["plan"]["titre"]
        beats.insert(sum(1 for x in beats if livre.en_tete(x)), b)     # après les autres plans d'en-tête, avant le récit
    else:
        b["sorte"] = cap["id"]
        tete = [x for x in beats if livre.en_tete(x)]
        if beats.index(b) >= len(tete):                                 # un plan d'en-tête reste en tête
            beats.remove(b)
            beats.insert(len(tete) - 1, b)
    b["recits"] = [x.get("micro") or "(paragraphe %d)" % (k + 1) for k, x in enumerate(ps)]
    p.write_text(livre.rt_texte(y, doc), encoding="utf-8")


def demarre(ident):
    d = reecriture.lit(SLUG_KB, ident)
    d.update(etat="en_cours", lancee=livre._maintenant(),
             budget={"recherches": 0, "pages": 0, "limites": reecriture.limites("recit")})
    systeme, message = compile_contexte(d)
    d["contexte"] = {"systeme": systeme, "message": message}
    reecriture._ecrit(SLUG_KB, d)
    return reecriture.tache(_execute(ident))


async def _execute(ident):
    d = reecriture.lit(SLUG_KB, ident)
    outils = ["Read", "Grep", "Glob"]
    lim = d["budget"]["limites"]
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON, thinking=reecriture.PENSEE,
        tools=outils, allowed_tools=outils, max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": SCHEMA_TETE if d["cible"].get("capacite") else SCHEMA},
        hooks=reecriture.garde(d, lim), model=reecriture.modele("recit", d))
    await reecriture._lance(SLUG_KB, d, options, d["contexte"]["message"], conclut)


def _propre(t):
    return ANCRE.sub("", " ".join(str(t or "").split())).strip()


def conclut(d, sortie):
    plan, rang = d["cible"].get("plan"), d["cible"].get("rang")
    R = _resultat_tete(d, sortie) if d["cible"].get("capacite") else _resultat(d, sortie)
    d.update(etat="prete", resultat=R)
    if d.get("poser"):
        try:
            e = pose(d["cible"]["chapitre"], R, d["id"], plan, rang, d["cible"].get("capacite"))
            d.update(etat="decidee", decision={"proposition": "posee", "d_office": True, "date": livre._maintenant(), **e})
        except Exception as e:                          # noqa: BLE001 — la proposition reste à décider
            d["erreur_pose"] = "%s" % e


def _resultat(d, sortie):
    plan, rang = d["cible"].get("plan"), d["cible"].get("rang")
    beats = {str(b.get("id")): b for b in _brief(d["cible"]["chapitre"]).get("beats") or [] if not livre.en_tete(b)}
    V = _verrou(d["cible"]["chapitre"])
    plans = []
    for p in sortie.get("plans") or []:
        pid = str(p.get("id") or "").strip()
        if pid not in beats or (plan and pid != plan):
            continue
        ps = [{"texte": _propre(x.get("texte")), "assertions": [str(a) for a in x.get("assertions") or []],
               "ajout": bool(x.get("ajout"))} for x in p.get("paragraphes") or [] if _propre(x.get("texte"))]
        if rang:
            ps = ps[:1]
        plans.append({"id": pid, "paragraphes": ps})
    attendues = {str(a) for pid in ([plan] if plan else beats) for a in (beats.get(pid) or {}).get("assertions") or []}
    portees = {a for p in plans for x in p["paragraphes"] for a in x["assertions"]}
    ecarts = [{"plan": p["id"], "paragraphes": len(p["paragraphes"]), "micro_recits": len(beats[p["id"]].get("recits") or [])}
              for p in plans if not rang and len(p["paragraphes"]) != len(beats[p["id"]].get("recits") or [])]
    R = {"plans": plans, "remarques": sortie.get("remarques") or "",
         "mots": sum(len(x["texte"].split()) for p in plans for x in p["paragraphes"]),
         "controle": {"inconnues": sorted(a for a in portees if V and a not in V),
                      "non_portees": [] if rang else sorted(attendues - portees), "ecarts": ecarts}}
    return R


def _nouvel_id(pris):
    while True:
        i = secrets.token_hex(2)
        if i not in pris and not i.isdigit() and not re.fullmatch(r"\d+e\d+", i):
            pris.add(i)
            return i


def pose(slug, R, demande, plan=None, rang=None, capacite=None):
    """Réécrit recit.md : les paragraphes de la portée remplacés, le reste gardé avec ses ancres ; links.yaml suit.
    Avec une capacité du livre : son plan d'en-tête est d'abord posé (ou mis à jour) en tête du storyboard."""
    from . import plan as P_
    dossier = livre.dossier(slug)
    if capacite:
        _pose_plan_tete(slug, capacite, R)
    beats = [str(b.get("id")) for b in _brief(slug).get("beats") or []]
    nouveaux = {p["id"]: p["paragraphes"] for p in R["plans"]}
    if not nouveaux:
        raise ValueError("rien à poser : la réponse n'a aucun paragraphe pour la portée")
    pr = dossier / "recit.md"
    ancien = pr.read_text(encoding="utf-8") if pr.exists() else ""
    PP = par_plan(slug)
    L = _liens(slug)
    pris = set(L) | {i for i, _ in _paragraphes(slug) if i}
    pe = dossier / "essai.md"
    if pe.exists():
        pris |= set(re.findall(r"\^([a-z0-9]+)\s*$", pe.read_text(encoding="utf-8"), re.M))

    # le nouveau découpage : {plan: [(id, texte, lien)]}
    groupes, retires, ecrits = _groupes(slug), [], []
    lien_de = lambda pid, x: {"plan": pid, **({"assertions": x["assertions"]} if x["assertions"] else {}),
                              **({"ajout": True} if x["ajout"] and not x["assertions"] else {})}
    for pid in list(groupes):
        if pid in nouveaux and (not plan or pid == plan):
            if rang:                                      # un paragraphe, à son rang : remplacé s'il existe
                x = nouveaux[pid][0]
                g = _materialise(groupes[pid])
                k = next((k for k, y in enumerate(g) if y[2]["rang"] == rang), None)
                i = g[k][0] if k is not None else _nouvel_id(pris)
                if k is not None:
                    g[k] = (i, x["texte"], dict(lien_de(pid, x), rang=rang))
                else:
                    g.append((i, x["texte"], dict(lien_de(pid, x), rang=rang)))
                groupes[pid] = g
                ecrits.append(i)
            else:                                         # tout le plan : écrit d'un trait, dans l'ordre
                retires += [y[0] for y in groupes[pid]]
                groupes[pid] = []
                for x in nouveaux[pid]:
                    i = _nouvel_id(pris)
                    groupes[pid].append((i, x["texte"], lien_de(pid, x)))
                    ecrits.append(i)

    # archive, texte, liens
    if ancien.strip():
        h = dossier / "historique"
        h.mkdir(exist_ok=True)
        nom = "recit-%s.md" % time.strftime("%Y%m%d-%H%M%S")
        while (h / nom).exists():
            nom = nom[:-3] + "b.md"
        (h / nom).write_text(ancien, encoding="utf-8")
    else:
        nom = None
    _ecrit(slug, groupes, ecrits)
    e = {"type": "recit_redige", "chapitre": slug, "demande": demande, "plan": plan, "rang": rang,
         "paragraphes": len(ecrits), "retires": len(retires), "archive": nom,
         "mots": sum(len(t.split()) for g in groupes.values() for _, t, _ in g)}
    with (dossier / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(e, date=livre._maintenant()), ensure_ascii=False) + "\n")
    P_.journal(e)
    return e


def _ecrit(slug, groupes, ecrits=()):
    """Écrit recit.md (un groupe par plan, séparés par ---) et links.yaml (les liens gardés, ceux des
    paragraphes écrits remplacés) ; le chapitre passe en brouillon s'il était au plan."""
    from . import plan as P_
    dossier = livre.dossier(slug)
    pr = dossier / "recit.md"
    groupes = {p: [x for _, x in _effectifs(g)] for p, g in groupes.items()}
    blocs = ["\n\n".join("%s ^%s" % (t, i) for i, t, _ in g) for g in groupes.values() if g]
    pr.write_text("\n\n---\n\n".join(blocs) + "\n", encoding="utf-8")
    pl = dossier / "links.yaml"
    y = livre.yaml_rt()
    doc = y.load(pl.read_text(encoding="utf-8")) if pl.exists() else None
    if doc is None:
        from ruamel.yaml.comments import CommentedMap
        doc = CommentedMap()
    rec = doc.get("recit") or {}
    from ruamel.yaml.comments import CommentedMap
    neuf = CommentedMap()
    for g in groupes.values():
        for i, _, lien in g:
            n = rec.get(i)
            if n is None or i in ecrits:
                n = lien
            elif n.get("rang") != lien.get("rang"):         # le rang a bougé (fait à la main)
                if lien.get("rang"):
                    n["rang"] = lien["rang"]
                else:
                    n.pop("rang", None)
            neuf[i] = n
    doc["recit"] = neuf
    pl.write_text(livre.rt_texte(y, doc), encoding="utf-8")

    # la structure : le récit existe, en brouillon
    ys, st = P_._lit_structure()
    _, _, x = P_._chapitre(st, slug)
    vs = list(x.get("versions") or [])
    if "recit" not in vs:
        x["versions"] = vs + ["recit"]
    if (x.get("status") or "outline") == "outline":
        x["status"] = "draft"
    P_._ecrit_structure(ys, st)


# ------------------------------------------------------------------ à la main

def _groupes(slug):
    """{plan: [(id, texte, lien)]} : les plans du storyboard dans l'ordre, puis ceux que le texte seul connaît."""
    beats = [str(b.get("id")) for b in _brief(slug).get("beats") or []]
    PP, L = par_plan(slug), _liens(slug)
    return {pid: [(i, t, dict(L.get(i) or {"plan": pid})) for i, t in PP.get(pid, [])]
            for pid in beats + [x for x in PP if x not in beats]}


def _forme(texte):
    import textwrap
    texte = ANCRE.sub("", texte.strip())
    if re.search(r"^\s*([-*+]\s|>|\||\d+[.)]\s|#)", texte, re.M):
        return texte
    return textwrap.fill(" ".join(texte.split()), width=100, break_long_words=False, break_on_hyphens=False)


def suit_micro_recits(slug, pid, op, rang, vers=None, n=0):
    """Le storyboard a changé de forme (livre.forme_plan) : les paragraphes du plan suivent leur micro-récit —
    une ligne (micro-récit, paragraphe) bouge d'un bloc. rang, vers : depuis 0 ; n : le nombre de micro-récits
    après l'opération. Retirer un micro-récit retire son paragraphe (son texte reste au journal)."""
    G = _groupes(slug)
    if not G.get(pid):
        return
    g = _materialise(G[pid])
    r = rang + 1
    if op == "recit_ajoute":
        # inséré : les lignes suivantes descendent ; ajouté en fin de plan : il reçoit le premier paragraphe resté
        # sans micro-récit, s'il y en a un
        if r < n:
            g = [(i, t, dict(l, rang=l["rang"] + 1) if l["rang"] >= r else l) for i, t, l in g]
    elif op == "recit_retire":
        for i, tx, l in [x for x in g if x[2]["rang"] == r]:
            _note(slug, {"type": "texte", "version": "recit", "source": "storyboard", "bloc": i, "avant": tx, "apres": None,
                         "plan": pid, "rang": r, "assertions": list(l.get("assertions") or []),
                         "motif": "son micro-récit est retiré du storyboard"})
        g = [(i, t, dict(l, rang=l["rang"] - 1) if l["rang"] > r else l) for i, t, l in g if l["rang"] != r]
    elif op == "recit_deplace":
        m = max(n, max(x[2]["rang"] for x in g))
        idx = list(range(m))
        idx.insert(int(vers), idx.pop(rang))
        g = [(i, t, dict(l, rang=idx.index(l["rang"] - 1) + 1) if l["rang"] <= m else l) for i, t, l in g]
    else:
        return
    G[pid] = g
    _ecrit(slug, G)


def _note(slug, e):
    with (livre.dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(e, date=livre._maintenant()), ensure_ascii=False) + "\n")


def retrait_permis(slug, pid, rang, force=False):
    """Retirer le micro-récit d'un rang (depuis 0) retire son paragraphe : refusé s'il porte des assertions, sauf force."""
    for r, (i, _, l) in _effectifs(_groupes(slug).get(pid) or []):
        if r == rang + 1 and l.get("assertions") and not force:
            raise ValueError("le paragraphe de ce micro-récit porte %s : le retirer les laisse sans récit"
                             % ", ".join(map(str, l["assertions"])))


def paragraphe(slug, op, corps):
    """Le texte du récit, à la main, rangé par plan (la même forme que le storyboard) :
      ajoute  {plan, rang (0…), texte, micro?}  le paragraphe d'une ligne vide ; avec « micro », une ligne nouvelle
                                         (micro-récit et paragraphe) insérée à ce rang, les suivantes descendent
      retire  {bloc, avant, force?}      refusé s'il porte des assertions, sauf force
      deplace {bloc, vers (0…)}          la ligne entière : son micro-récit bouge avec lui (livre.forme_plan)
    Le texte et le storyboard restent alignés ligne à ligne : un paragraphe n'entre que sur une ligne qui a son
    micro-récit, et ne change de place qu'avec lui. Le rang (le micro-récit que le paragraphe réalise) s'écrit
    dans links.yaml dès qu'on touche au plan à la main.
    La correction du texte d'un paragraphe reste edition.modifie_bloc."""
    G = _groupes(slug)
    e = {"type": "texte", "version": "recit", "source": "correction", "motif": corps.get("motif") or ""}
    beats = {str(b.get("id")): b for b in _brief(slug).get("beats") or []}
    if op == "ajoute":
        pid = str(corps.get("plan") or "")
        if pid not in G:
            raise KeyError(pid)
        texte = (corps.get("texte") or "").strip()
        if not texte:
            raise ValueError("un paragraphe vide : écris-le d'abord")
        r = int(corps.get("rang") or 0) + 1                 # l'API compte depuis 0 ; le rang écrit, depuis 1
        if r < 1:
            raise ValueError("rang : 0, 1…")
        micro = " ".join((corps.get("micro") or "").split())
        n = len((beats.get(pid) or {}).get("recits") or [])
        if micro:                                           # une ligne nouvelle : le micro-récit d'abord (les suivants descendent)
            livre.forme_plan(slug, "recit_ajoute", {"plan": pid, "rang": r - 1, "texte": micro}, livre.empreinte_brief(slug),
                             corps.get("motif") or "")
            r = min(r, n + 1)                               # au-delà du plan : la ligne s'ajoute à la fin
            G = _groupes(slug)
            if any(x[2]["rang"] == r for x in _materialise(G[pid])):
                raise ValueError("le micro-récit est ajouté, mais sa ligne a déjà un paragraphe (resté sans micro-récit) : "
                                 "corrige-le plutôt")
        elif r > n:
            raise ValueError("le rang %d n'a pas de micro-récit : décris-le avec le paragraphe (une ligne nouvelle)" % r)
        elif any(x[2]["rang"] == r for x in _materialise(G[pid])):
            raise ValueError("le rang %d est déjà écrit : corrige-le, ou insère une ligne nouvelle (micro-récit et paragraphe)" % r)
        g = _materialise(G[pid])
        pris = set(_liens(slug)) | {i for i, _ in _paragraphes(slug) if i}
        pe = livre.dossier(slug) / "essai.md"
        if pe.exists():
            pris |= set(re.findall(r"\^([a-z0-9]+)\s*$", pe.read_text(encoding="utf-8"), re.M))
        i = _nouvel_id(pris)
        g.append((i, _forme(texte), {"plan": pid, "rang": r}))
        G[pid] = g
        _ecrit(slug, G, [i])
        e.update(bloc=i, avant=None, apres=texte, plan=pid, rang=r)
    else:
        bloc = str(corps.get("bloc") or "")
        pid = next((p for p, g in G.items() if any(x[0] == bloc for x in g)), None)
        if pid is None:
            raise KeyError(bloc)
        g = _materialise(G[pid])
        k = next(k for k, x in enumerate(g) if x[0] == bloc)
        i, texte, lien = g[k]
        if op == "retire":
            if corps.get("avant") is not None and " ".join(corps["avant"].split()) != " ".join(texte.split()):
                raise reecriture.Conflit("le paragraphe ^%s a changé depuis son ouverture" % bloc)
            if lien.get("assertions") and not corps.get("force"):
                raise ValueError("ce paragraphe porte %s : le retirer les laisse sans récit" % ", ".join(map(str, lien["assertions"])))
            del g[k]                                        # les autres gardent leur rang : la place reste vide
            G[pid] = g
            _ecrit(slug, G)
            e.update(bloc=bloc, avant=texte, apres=None, plan=pid, rang=lien["rang"],
                     assertions=list(lien.get("assertions") or []))
        elif op == "deplace":
            r = int(corps.get("vers")) + 1
            n = len((beats.get(pid) or {}).get("recits") or [])
            de = lien["rang"]
            if de <= n and 1 <= r <= n:                     # la ligne entière : le micro-récit bouge, le texte suit
                livre.forme_plan(slug, "recit_deplace", {"plan": pid, "rang": de - 1, "vers": r - 1}, livre.empreinte_brief(slug),
                                 corps.get("motif") or "")
            elif de > n and r >= 1 and not any(x[2]["rang"] == r for x in g):
                g[k] = (i, texte, dict(lien, rang=r))       # un paragraphe sans micro-récit rejoint une ligne vide
                G[pid] = g
                _ecrit(slug, G)
            else:
                raise ValueError("ce déplacement désalignerait le texte et le storyboard (rangs 1 à %d, place libre "
                                 "pour un paragraphe sans micro-récit)" % n)
            e.update(bloc=bloc, plan=pid, rang=de, vers=r)
        else:
            raise ValueError("opération inconnue : %s" % op)
    with (livre.dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(e, date=livre._maintenant()), ensure_ascii=False) + "\n")
    return {"bloc": e.get("bloc"), "plan": e.get("plan")}


def decide(ident, corps):
    """{action: retenir | rejeter, motif?}."""
    d = reecriture.lit(SLUG_KB, ident)
    if d["etat"] != "prete":
        raise reecriture.Conflit("le récit n'attend pas de décision (%s)" % d["etat"])
    if corps.get("action") == "rejeter":
        d.update(etat="decidee", decision={"proposition": None, "motif": (corps.get("motif") or "").strip(), "date": livre._maintenant()})
    else:
        e = pose(d["cible"]["chapitre"], d["resultat"], ident, d["cible"].get("plan"), d["cible"].get("rang"),
                 d["cible"].get("capacite"))
        d.update(etat="decidee", decision={"proposition": "posee", "date": livre._maintenant(), **e})
    reecriture._ecrit(SLUG_KB, d)
    return d
