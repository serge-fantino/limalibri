# -*- coding: utf-8 -*-
"""Creuser une fiche : Claude la lit et propose des fiches complémentaires.

Une demande de type « pistes » vit dans kb/demandes/<id>.json. Claude lit la fiche, cherche
ce qu'elle effleure sans le traiter, et, pour chaque piste, vérifie dans la base si elle est
déjà couverte (Grep, index, voisines) avant de la classer : nouvelle, à compléter (une fiche
en parle trop brièvement) ou couverte. Aucune recherche web : c'est une lecture de la base.

Décider lance, pour chaque piste cochée, une création de fiche (limalibri/creation.py) avec sa
question — la création revérifie le doublon au moment d'écrire. Les pistes « à compléter »
attendent la complétion d'une fiche.
"""
import re
import time
import secrets

from claude_agent_sdk import ClaudeAgentOptions

from . import livre, kb, reecriture, creation

SLUG_KB = creation.SLUG_KB
SKILL = reecriture.SKILL.parent / "pistes.md"
STATUTS = ("nouvelle", "a_completer", "couverte")

SCHEMA = {
    "type": "object",
    "properties": {
        "note": {"type": "string"},
        "pistes": {"type": "array", "items": {"type": "object", "properties": {
            "question": {"type": "string"},
            "slug": {"type": "string"},
            "statut": {"type": "string", "enum": list(STATUTS)},
            "fiche_existante": {"type": "string"},
            "section_existante": {"type": "string"},
            "appel": {"type": "string"},
            "pourquoi": {"type": "string"},
            "chapitres": {"type": "array", "items": {"type": "string"}},
            "priorite": {"type": "string", "enum": ["haute", "moyenne", "basse"]}},
            "required": ["question", "slug", "statut", "pourquoi", "priorite"]}}},
    "required": ["pistes"]}


def _voisines(slug):
    """Les voisines d'une fiche : ses liens, celles qui la citent, celles de son cluster."""
    I = {f["slug"]: f for f in kb.index()}
    f = I[slug]
    try:
        g = kb.graphe()
        cl = next(n["cluster"] for n in g["noeuds"] if n["id"] == slug)
        cluster = [n["id"] for n in g["noeuds"] if n["type"] == "fiche" and n["cluster"] == cl and n["id"] != slug]
        mots = g["clusters"][cl]["mots"]
    except Exception:                          # noqa: BLE001 — le graphe est un plus, pas un prérequis
        cluster, mots = [], []
    return f, I, cluster, mots


def compile_contexte(d):
    m = livre.meta()
    systeme = re.sub(r"<!--.*?-->\n*", "", SKILL.read_text(encoding="utf-8"), flags=re.S)
    systeme = systeme.replace("{{titre}}", m.get("titre", ""))
    slug = d["cible"]["fiche"]
    f, I, cluster, mots = _voisines(slug)
    meta, corps = kb._lit(slug)
    L = ["# La fiche à creuser : %s — %s" % (slug, f["titre"]),
         "Fichier : kb/fiches/%s.md (le lire en entier)" % slug,
         "Sujet : %s" % meta.get("sujet", ""), "Confiance : %s" % meta.get("confiance", "")]
    from . import filiation
    n = filiation.reglage()["enfants"]
    L.append("\nPlafond de ce livre : %d piste%s au plus — les plus utiles au livre, les autres non." % (n, "s" if n > 1 else ""))
    if d.get("consigne"):
        L.append("\n## Précision de l'auteur\n" + d["consigne"])
    L.append("\n## Ses sections\n" + "\n".join("%s- %s {#%s}" % ("  " * (s["niveau"] - 2), s["titre"], s["id"])
                                               for s in kb._structure(corps)[1]))
    morts = sorted({x.group(1).strip() for x in kb.LIEN.finditer(corps)} - set(I))
    if morts:
        L.append("\nSes liens vers des fiches qui n'existent pas : " + ", ".join(morts))
    L.append("\n## Ses voisines")
    L.append("Elle cite : " + (", ".join(f["liens"]) or "aucune"))
    L.append("Elle est citée par : " + (", ".join(f["entrants"]) or "aucune"))
    if cluster:
        L.append("Son cluster (%s) : %s" % (" · ".join(mots[:3]), ", ".join(cluster)))
    chap = [c for c in livre.chapitres() if c.get("atelier")]
    utilise = [c for c in f["chapitres"]]
    if utilise:
        L.append("\n## Les chapitres qui l'utilisent")
        for c in utilise:
            L.append("- %s (%s)" % (c["slug"], c["title"]))
    L.append("\n## Les chapitres de l'atelier (slugs possibles pour « chapitres »)\n" +
             "\n".join("- %s — %s" % (c["slug"], c["title"]) for c in chap))
    L.append("\n## Toutes les fiches (kb/fiches/<slug>.md)\n\n" + creation.index_texte())
    from . import refs
    L.append(refs.annexe(d.get("consigne")))
    return systeme, "\n".join(L)


def cree(corps):
    slug = (corps.get("fiche") or "").strip()
    kb._lit(slug)                                   # KeyError si la fiche n'existe pas
    d = {"id": "p-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "pistes", "portee": "pistes", "mode": "lecture",
         "consigne": (corps.get("consigne") or "").strip(),
         "modele_choisi": reecriture._choix_modele(corps),
         "cible": {"fiche": slug},
         "etat": "en_cours", "cree": livre._maintenant(),
         "budget": {"recherches": 0, "pages": 0, "limites": reecriture.limites("pistes")}}
    d["titre"] = titre_de(d)
    systeme, message = compile_contexte(d)
    d["contexte"] = {"systeme": systeme, "message": message}
    reecriture._ecrit(SLUG_KB, d)
    from . import file
    return file.part(SLUG_KB, d, "pistes", "_execute", d["id"])


def titre_de(d):
    return "Creuser la fiche « %s »" % d["cible"]["fiche"]


async def _execute(ident):
    d = reecriture.lit(SLUG_KB, ident)
    outils = ["Read", "Grep", "Glob"]                # une lecture de la base : pas de web
    lim = d.get("budget", {}).get("limites") or reecriture.limites("pistes")
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON, thinking=reecriture.PENSEE,
        tools=outils, allowed_tools=outils, max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": SCHEMA},
        hooks=reecriture.garde(d, lim), model=reecriture.modele("pistes", d))
    await reecriture._lance(SLUG_KB, d, options, d["contexte"]["message"], conclut)


def conclut(d, sortie):
    connues = {f["slug"] for f in kb.index()}
    chap = {c["slug"] for c in livre.chapitres()}
    out = []
    def nom(x):                                 # « kb/fiches/saisons.md », « [[saisons]] » -> « saisons »
        x = re.sub(r"^.*/|\.md$|\[\[|\]\]", "", (x or "").strip())
        return x.split("#")[0].strip() or None

    for p in sortie.get("pistes") or []:
        p = dict(p)
        if p.get("fiche_existante"):
            p["fiche_existante"] = nom(p["fiche_existante"])
        # une section : le premier identifiant donné, s'il existe dans la fiche visée
        for cle, fiche in (("section_existante", p.get("fiche_existante")), ("appel", d["cible"]["fiche"])):
            ids = re.findall(r"[a-z0-9][a-z0-9-]*", (p.get(cle) or "").lower())
            try:
                connues_s = {s["id"] for s in kb._structure(kb._lit(fiche)[1])[1]} if fiche in connues else set()
            except KeyError:
                connues_s = set()
            p[cle] = next((i for i in ids if i in connues_s), None)
        p["slug"] = creation._slug(p.get("slug") or p["question"][:40]) or "piste"
        p["chapitres"] = [c for c in p.get("chapitres") or [] if c in chap]
        if p.get("fiche_existante") not in connues:
            p.pop("fiche_existante", None)
            p.pop("section_existante", None)
            if p["statut"] != "nouvelle":        # « couverte par » une fiche qui n'existe pas : non
                p["statut"] = "nouvelle"
        if p["statut"] == "nouvelle" and p["slug"] in connues:
            p["statut"], p["fiche_existante"] = "couverte", p["slug"]   # le slug est pris : la fiche existe
        out.append(p)
    d.update(etat="prete", resultat={"note": sortie.get("note", ""), "pistes": out})


def decide(ident, corps):
    """{action: creer|rejeter, pistes: [{i, question?, slug?, chapitres?}], motif}. Créer lance
    une création de fiche par piste retenue ; la demande garde le lien vers chacune."""
    d = reecriture.lit(SLUG_KB, ident)
    if d["etat"] != "prete":
        raise reecriture.Conflit("la demande n'attend pas de décision (%s)" % d["etat"])
    motif = (corps.get("motif") or "").strip()
    if corps.get("action") == "rejeter":
        d.update(etat="decidee", decision={"proposition": None, "motif": motif, "date": livre._maintenant()})
        reecriture._ecrit(SLUG_KB, d)
        return d
    P = d["resultat"]["pistes"]
    from . import filiation
    pl = filiation.place(ident)
    choisies = corps.get("pistes") or []
    if len(choisies) > pl["permis"]:
        raise ValueError("%d pistes cochées, %d permises — %s" % (
            len(choisies), pl["permis"], pl["motif"] or "plafond : %d fiches au plus par creusement (claude.file.enfants)"
            % filiation.reglage()["enfants"]))
    lancees = []
    with filiation.depuis(ident):
        _cree_fiches(d, P, choisies, lancees, ident)
    if not lancees:
        raise ValueError("aucune piste cochée")
    d = reecriture.lit(SLUG_KB, ident)           # relue : elle compte maintenant ses enfants
    d.update(etat="decidee", decision={"proposition": "pistes", "lancees": lancees, "motif": motif,
                                       "date": livre._maintenant(), "en_file": True})
    reecriture._ecrit(SLUG_KB, d)
    from . import file
    file.suivante()                              # seulement si l'enchaînement est activé
    return d


def _cree_fiches(d, P, choisies, lancees, ident):
    for x in choisies:
        i = x.get("i")
        if not isinstance(i, int) or not 0 <= i < len(P):
            raise ValueError("piste inconnue : %s" % i)
        p = P[i]
        n = creation.cree(lancer=False, corps={
            "question": x.get("question") or p["question"], "slug": x.get("slug") or p["slug"],
            "chapitres": x.get("chapitres") if x.get("chapitres") is not None else p.get("chapitres"),
            "depuis": ident, "modele": x.get("modele"),
            "consigne": "Piste proposée en creusant la fiche [[%s]]%s : %s" % (
                d["cible"]["fiche"], " (section {#%s})" % p["appel"] if p.get("appel") else "", p["pourquoi"])})
        lancees.append({"i": i, "demande": n["id"]})
