# -*- coding: utf-8 -*-
"""Cadrer un objectif : Claude lit l'objectif, interroge le livre, et rend un plan en phases.

Une demande « cadrage » (kb/demandes/k-*.json). Claude reçoit l'objectif (titre, critères, intention,
budget), les mesures du suivi chapitre par chapitre, le travail en attente, le plan du livre, l'index des
fiches, les règles d'écriture et le catalogue des capacités (limalibri/capacites.py) — puis il lit lui-même
ce qu'il veut dans le livre (Read, Grep, Glob ; pas de web) pour se faire son idée. Il rend :

    lecture      ce qu'il comprend de l'objectif, reformulé
    sous_buts    l'objectif découpé ; chacun mesuré (un critère), à mesurer, ou à juger
    diagnostic   par chapitre, ce qui bloque vraiment
    cadre        ce qu'il propose d'ajouter au cadre : une règle d'écriture, un critère, une consigne commune
    phases       le plan : des phases (avec point d'arrêt pour l'auteur), faites d'actions — chacune une
                 capacité du catalogue avec ses paramètres, son pourquoi, ses dépendances
    couper       les demandes en attente qui ne servent pas l'objectif
    remarques    ce qui reste hors de portée, les risques

Le harnais contrôle la réponse : capacités connues, paramètres valides (chapitres, fiches, parties),
dépendances connues et sans cycle, coût estimé face au budget, et couverture — chaque critère non tenu,
sur chaque chapitre, est-il traité par une action ? L'auteur retient ensuite ce qu'il veut
(limalibri/pilotage.py).
"""
import json
import time
import secrets

from claude_agent_sdk import ClaudeAgentOptions

from . import livre, reecriture, objectifs, capacites

SLUG_KB = "_kb"

SYSTEME = """Tu es l'architecte du travail sur le livre « {titre} ». L'auteur te confie un objectif ; tu dois
le comprendre, te faire ta propre idée de l'état du livre, et organiser le travail pour l'atteindre.

Ce que tu as : l'objectif, les mesures de l'atelier chapitre par chapitre, le travail en attente, le plan
du livre, l'index des fiches, les règles d'écriture, et le catalogue des capacités. Le livre est dans ton
répertoire de travail : lis ce qu'il faut (Read, Grep, Glob) — les essais (chapters/<slug>/essai.md), les
briefs (chapters/<slug>/brief.yaml), les fiches (kb/fiches/<slug>.md), les règles (regles/). Ne lis pas
tout : échantillonne, compare, cherche (Grep) ce que l'objectif vise. Pas de web.

Ce que tu rends :
- ta lecture de l'objectif, en clair, et ses sous-buts : pour chacun, dis s'il est mesuré par un critère
  de l'atelier, s'il pourrait l'être (« a_mesurer » : dis comment), ou s'il ne peut qu'être jugé ;
- un diagnostic court par chapitre qui pose problème (pas les autres) ;
- les ajouts au cadre que l'objectif appelle : une règle d'écriture nouvelle si l'objectif introduit une
  exigence que les règles ne disent pas (titre court, texte d'une ou deux phrases, à l'impératif) ; une
  règle ou une section existante à RÉÉCRIRE si elle contredit l'objectif (regle_revue : cible = son
  identifiant, R5 ou la-voix ; le texte nouveau en entier) ; un critère mesuré à ajouter ; une consigne
  commune à toutes les actions. Rien si le cadre suffit ;
- le plan, en phases ordonnées. Une phase a un but ; elle finit par un point d'arrêt quand l'auteur doit
  décider avant la suite (retenir des fiches, une structure, relire). Chaque action est une capacité du
  catalogue, avec ses paramètres exacts (slugs de chapitres, de fiches, de parties tels qu'ils existent),
  un pourquoi qui la rattache à l'objectif, et ses dépendances (identifiants d'actions qui doivent finir
  avant elle). Donne à chaque action un identifiant court (a1, a2…). Une action peut aussi dépendre d'une
  action du plan d'un AUTRE objectif (voir « Les plans des autres objectifs ») : écris alors
  « <objectif>:<action> », par exemple « o-9f89:a8 » — le storyboard d'un chapitre après la révision de
  son essai, par exemple ;
- les demandes en attente qui ne servent pas l'objectif (à couper) ;
- tes remarques : ce qui est hors de portée, ce qui dépasse le budget, les risques.

Principes :
- Le moins d'actions possible pour atteindre l'objectif. Pas d'action « au cas où ».
- Une révision a une consigne propre au chapitre : ce qu'il doit perdre (une répétition, en nommant le
  chapitre qui le dit déjà), gagner (une fiche nouvelle), corriger (une porte du harnais). Jamais la même
  consigne recopiée sur vingt chapitres.
- L'ordre compte : les fiches avant les révisions qui s'en servent ; une révision avant la lecture naïve
  du même chapitre ; une structure du livre décidée avant de réviser selon elle.
- Ce que seul l'auteur peut faire (décider, relire, passer un chapitre en relu, trancher) est une action
  `auteur`.
- Reste dans le budget s'il y en a un ; sinon dis ce que tu sacrifies.
- Tout en français."""

SCHEMA = {
    "type": "object",
    "properties": {
        "lecture": {"type": "string"},
        "sous_buts": {"type": "array", "items": {"type": "object", "properties": {
            "texte": {"type": "string"}, "mesure": {"type": "string", "enum": ["mesure", "a_mesurer", "juge"]},
            "comment": {"type": "string"}}, "required": ["texte", "mesure"]}},
        "diagnostic": {"type": "array", "items": {"type": "object", "properties": {
            "chapitre": {"type": "string"}, "texte": {"type": "string"}}, "required": ["chapitre", "texte"]}},
        "cadre": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "string", "enum": list(capacites.CADRE)}, "titre": {"type": "string"}, "texte": {"type": "string"},
            "critere": {"type": "string"}, "valeur": {"type": ["string", "number", "boolean"]},
            "cible": {"type": "string"},
            "pourquoi": {"type": "string"}}, "required": ["type", "texte", "pourquoi"]}},
        "phases": {"type": "array", "items": {"type": "object", "properties": {
            "titre": {"type": "string"}, "but": {"type": "string"}, "point_arret": {"type": "boolean"},
            "actions": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "capacite": {"type": "string", "enum": list(capacites.CATALOGUE)},
                "params": {"type": "object"}, "pourquoi": {"type": "string"},
                "depend": {"type": "array", "items": {"type": "string"}}},
                "required": ["id", "capacite", "params", "pourquoi"]}}},
            "required": ["titre", "but", "actions"]}},
        "couper": {"type": "array", "items": {"type": "object", "properties": {
            "demande": {"type": "string"}, "pourquoi": {"type": "string"}}, "required": ["demande", "pourquoi"]}},
        "remarques": {"type": "string"}},
    "required": ["lecture", "phases"]}


def _mesures(S):
    L = ["chapitre | niveau | score | portes en échec | lecture naïve | fiches | manques | à décider"]
    for c in S["chapitres"]:
        m, t = c.get("mesures") or {}, c.get("travail") or {}
        L.append("%s. %s (%s) | %s | %s %% | %s | %s | %s | %s | %s" % (
            c.get("numero"), c["titre"], c["slug"], m.get("niveau"), m.get("score"),
            ", ".join(m.get("portes_ko_titres") or []) or "—", "à jour" if m.get("naif") else "à faire",
            m.get("fiches"), t.get("manques", 0), len(t.get("a_decider") or [])))
    return "\n".join(L)


def _attente():
    from . import travail
    T = travail.par_chapitre()
    vus, L = set(), []
    for ch, t in T.items():
        for x in (t.get("en_file") or []) + (t.get("a_decider") or []) + (t.get("en_cours") or []):
            if x["id"] in vus:
                continue
            vus.add(x["id"])
            L.append("- %s · %s · %s" % (x["id"], x["etat"], x["titre"]))
    return "\n".join(L) or "(rien)"


def _autres_plans(sauf):
    from . import pilotage
    L = []
    for o in objectifs.lit_tous():
        if o.get("id") == sauf or o.get("etat") == "archive":
            continue
        P = pilotage.lit(o["id"])
        if not P:
            continue
        L.append("## %s — « %s » (%s, plan %s)" % (o["id"], o["titre"], o.get("version", "essai"), P["etat"]))
        for k, ph in enumerate(P["phases"], 1):
            for a in ph["actions"]:
                L.append("- %s:%s · phase %d · %s · %s · %s" % (o["id"], a["id"], k, a["capacite"], a["etat"],
                                                               ", ".join("%s=%s" % (x, v) for x, v in (a.get("params") or {}).items()
                                                                         if x in ("chapitre", "partie", "fiche"))))
    return "\n".join(L) or "(aucun)"


def compile_contexte(d):
    from . import suivi, planif, plan, creation, regles
    o = next(x for x in objectifs.lit_tous() if x.get("id") == d["cible"]["objectif"])
    version = o.get("version", "essai")
    S = suivi.suivi(version)
    e = next(x for x in S["objectifs"] if x["id"] == o["id"])
    systeme = SYSTEME.format(titre=livre.meta().get("titre", ""))
    restant = None if o.get("budget") is None else round(o["budget"] - e["depense"], 2)
    L = ["# L'objectif", "Titre : %s" % o["titre"], "Version : %s" % version,
         "Cette version, selon l'auteur : %s" % (livre.intention_version(version) or "(rôle non décrit dans livre.yaml)"),
         "Périmètre : %s" % e["perimetre_libelle"],
         "Critères mesurés : %s" % (" ; ".join("%s %s — tenu sur %d/%d chapitres" % (c["libelle"], c["attendu"], c["tenus"], c["total"])
                                             for c in e["criteres_eval"]) or "aucun"),
         "Intention (jugée par l'auteur) : %s" % (o.get("intention") or "aucune"),
         "Consigne commune déjà posée : %s" % (o.get("consigne") or "aucune"),
         "Budget : %s" % ("%.2f $ restants sur %.2f $" % (restant, o["budget"]) if restant is not None else "non fixé"),
         "Échéance : %s" % (o.get("echeance") or "aucune")]
    if d.get("consigne"):
        L += ["", "# Précision de l'auteur pour ce cadrage", d["consigne"]]
    L += ["", "# Les mesures de l'atelier, chapitre par chapitre (version %s)" % version, _mesures(S),
          "", "Critères que l'atelier sait mesurer (pour un critère à ajouter) : " +
          ", ".join("%s (%s %s)" % (k, v[0], v[1]) for k, v in objectifs.CRITERES.items() if version in v[3]),
          "", "# Le travail en attente (demandes en file, en cours, à décider)", _attente(),
          "", "# Le plan du livre", planif._texte_plan(plan.lit(), None, None),
          "", "# Les fiches (kb/fiches/<slug>.md)", creation.index_texte(),
          "", "# Les règles d'écriture (%s) — identifiants : %s" % (version, ", ".join(
              "%s (%s)" % (e["id"], e["titre"]) for e in regles.lit(version)["elements"])),
          regles.texte_pour_claude(version) or "(aucune)",
          "", "# Les plans des autres objectifs (pour dépendre de leurs actions : « <objectif>:<action> »)", _autres_plans(o["id"]),
          "", "# Les capacités (le plan n'emploie que celles-ci)", capacites.texte_pour_claude()]
    from . import refs
    L.append(refs.annexe(d.get("consigne")))
    return systeme, "\n".join(L)


def cree(ident_objectif, corps):
    o = next((x for x in objectifs.lit_tous() if x.get("id") == ident_objectif), None)
    if not o:
        raise KeyError(ident_objectif)
    d = {"id": "k-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "cadrage", "portee": "cadrage", "mode": "lecture",
         "consigne": (corps.get("consigne") or "").strip(), "modele_choisi": reecriture._choix_modele(corps),
         "cible": {"objectif": ident_objectif, "titre": o["titre"]},
         "etat": "en_attente", "cree": livre._maintenant(), "rang": time.time()}
    d["titre"] = "Cadrer l'objectif « %s »" % o["titre"][:70]
    reecriture._ecrit(SLUG_KB, d)
    from . import file
    return file.part(SLUG_KB, d, "cadrage", "demarre", d["id"])


def demarre(ident):
    """Le contexte est compilé au départ : il voit l'état du livre à ce moment."""
    d = reecriture.lit(SLUG_KB, ident)
    d.update(etat="en_cours", lancee=livre._maintenant(),
             budget={"recherches": 0, "pages": 0, "limites": reecriture.limites("cadrage")})
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
        output_format={"type": "json_schema", "schema": schema()},
        hooks=reecriture.garde(d, lim), model=reecriture.modele("cadrage", d))
    await reecriture._lance(SLUG_KB, d, options, d["contexte"]["message"], conclut)


# ------------------------------------------------------------------ le contrôle

def schema():
    """Le schéma de la réponse, les capacités du livre comprises (capacites.yaml)."""
    import copy
    S = copy.deepcopy(SCHEMA)
    S["properties"]["phases"]["items"]["properties"]["actions"]["items"]["properties"]["capacite"]["enum"] = list(capacites.tout())
    return S


COUVRE = {"niveau": ("brief", "ecrire", "reviser", "naif", "auteur"), "controles": ("reviser",), "naif": ("naif",),
          "manques": ("fiche", "creuser", "reviser", "auteur"), "fiches": ("brief", "fiche", "auteur"),
          "annotations": ("auteur", "reviser"), "a_decider": ("auteur",), "score": tuple(capacites.CATALOGUE)}


def _externe_existe(ref):
    """« o-xxxx:a8 » : une action du plan d'un autre objectif."""
    from . import pilotage
    if ":" not in ref:
        return False
    o, a = ref.split(":", 1)
    P = pilotage.lit(o)
    return bool(P) and any(x["id"] == a for ph in P["phases"] for x in ph["actions"])


def controle(sortie, ident_objectif):
    """Ce que le harnais dit du plan rendu : problèmes par action, dépendances, couverture, coût."""
    from . import suivi, execution
    o = next(x for x in objectifs.lit_tous() if x.get("id") == ident_objectif)
    K = {"chapitres": capacites._chapitres(), "fiches": capacites._fiches(), "parties": capacites._parties()}
    A = [a for ph in sortie.get("phases") or [] for a in ph.get("actions") or []]
    ids = [a.get("id") for a in A]
    pb = {}
    for a in A:
        p = capacites.valide(a.get("capacite"), a.get("params"), K)
        inconnues = [x for x in a.get("depend") or [] if x not in ids and not _externe_existe(x)]
        if inconnues:
            p.append("dépend d'actions inconnues : %s" % ", ".join(inconnues))
        if p:
            pb[a.get("id")] = p
    if len(set(ids)) != len(ids):
        pb["_"] = ["identifiants d'action en double"]
    # un cycle ?
    dep = {a.get("id"): set(a.get("depend") or []) for a in A}
    vus, cycle = set(), []

    def visite(x, pile):
        if x in pile:
            cycle.append(x)
            return
        if x in vus:
            return
        vus.add(x)
        for y in dep.get(x, ()):
            visite(y, pile | {x})
    for x in dep:
        visite(x, frozenset())
    # la couverture : chaque critère non tenu, sur chaque chapitre
    S = suivi.suivi(o.get("version", "essai"))
    e = next(x for x in S["objectifs"] if x["id"] == ident_objectif)
    trous = []

    def touche(a, slug):
        P = a.get("params") or {}
        return P.get("chapitre") == slug or slug in (P.get("chapitres") or []) or \
            (not P.get("chapitre") and a.get("capacite") == "auteur")
    for l in e["chapitres"]:
        for ec in l["ecarts"]:
            caps = tuple(capacites.tout()) if ec["critere"] == "score" else COUVRE.get(ec["critere"], ())
            if not any(a.get("capacite") in caps and touche(a, l["slug"]) for a in A):
                trous.append({"chapitre": l["slug"], "critere": ec["critere"], "libelle": ec["libelle"]})
    M = execution._moyennes()
    cout = round(sum(capacites.cout(a.get("capacite"), M)[0] for a in A if a.get("capacite") != "auteur"), 2)
    duree = round(sum(capacites.cout(a.get("capacite"), M)[1] for a in A if a.get("capacite") != "auteur"))
    restant = None if o.get("budget") is None else round(o["budget"] - e["depense"], 2)
    return {"problemes": pb, "cycle": sorted(set(cycle)), "trous": trous, "cout": cout, "duree_s": duree,
            "budget_restant": restant, "actions": len(A)}


def decide(ident, corps):
    """{action: rejeter, motif} — retenir passe par le pilotage (limalibri/pilotage.py)."""
    d = reecriture.lit(SLUG_KB, ident)
    if d["etat"] != "prete":
        raise reecriture.Conflit("le cadrage n'attend pas de décision (%s)" % d["etat"])
    if corps.get("action") != "rejeter":
        raise ValueError("retenir un cadrage : depuis la vue de l'objectif")
    d.update(etat="decidee", decision={"proposition": None, "motif": (corps.get("motif") or "").strip(), "date": livre._maintenant()})
    reecriture._ecrit(SLUG_KB, d)
    return d


def conclut(d, sortie):
    d["resultat"] = sortie
    try:
        d["controle"] = controle(sortie, d["cible"]["objectif"])
    except Exception as e:                              # noqa: BLE001 — le contrôle ne doit pas perdre la réponse
        d["controle"] = {"erreur": "%s" % e}
    d["etat"] = "prete"
