# -*- coding: utf-8 -*-
"""La vérification d'une référence : une œuvre de la bibliographie, confrontée à ses sources.

Une demande de type « reference » vit dans kb/demandes/<id>.json. Claude établit, sur les pages
de l'éditeur, de PubMed, d'arXiv ou d'un dépôt (jamais de mémoire) :
  · si l'œuvre existe, et laquelle c'est — auteurs, titre, revue, volume, pages, année, DOI lu ;
  · si elle est déjà dans la base sous une autre clé (même DOI, même titre) ;
  · si elle dit ce qu'on lui fait dire, à chaque endroit qui la cite (notes de l'essai, fiches).
Il rend un verdict : confirmée, corrigée, introuvable, mal attribuée, doublon.

Retenir écrit kb/sources/<cle>.yaml (référence, DOI, statut, la vérification, date et demande),
met à jour la bibliographie des chapitres qui la citent (la référence, le doute levé), et note
tout au journal de la base. Rien d'autre : une clé ne change pas (un doublon est signalé, pas
fusionné).
"""
import re
import time
import secrets

import yaml
from claude_agent_sdk import ClaudeAgentOptions

from . import livre, kb, reecriture, sources

SLUG_KB = "_kb"
VERDICTS = {"confirmee": "verifiee", "corrigee": "corrigee", "introuvable": "introuvable",
            "mal_attribuee": "mal_attribuee", "doublon": "doublon"}

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "resume": {"type": "string"},
        "identite": {"type": "object", "properties": {
            "auteurs": {"type": "string"}, "titre": {"type": "string"}, "revue": {"type": "string"},
            "annee": {"type": "string"}, "volume": {"type": "string"}, "pages": {"type": "string"},
            "doi": {"type": "string"}, "url": {"type": "string"}, "lu_sur": {"type": "string"}}},
        "ref": {"type": "string"},
        "doublon_de": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "object", "properties": {
            "ou": {"type": "string"}, "appui": {"type": "string", "enum": ["oui", "partiel", "non", "inverifiable"]},
            "extrait": {"type": "string"}, "commentaire": {"type": "string"}},
            "required": ["ou", "appui", "commentaire"]}}},
    "required": ["verdict", "resume", "citations"]}

SYSTEME = """Tu vérifies une référence bibliographique d'un livre de vulgarisation en français. On te
donne l'œuvre telle que le livre la cite (clé, référence, DOI s'il y en a un) et les endroits qui
la citent. Tu établis, et tu rends :

1. L'œuvre existe-t-elle, et laquelle est-ce ? Trouve-la sur la page de l'éditeur, PubMed, PMC,
   arXiv, un dépôt institutionnel. Relève auteurs, titre, revue, volume, pages, année. Le DOI
   n'est donné que s'il a été lu sur une page consultée (dis laquelle dans `lu_sur`) — jamais de
   mémoire. Sur un mur payant : le résumé, PMC, arXiv ; deux tentatives au plus.
2. Est-elle déjà dans la base sous une autre clé ? On te donne les candidats proches ; s'il y en a
   un qui est la même œuvre, verdict « doublon » et sa clé dans `doublon_de`.
3. Dit-elle ce qu'on lui fait dire ? Pour chaque endroit qui la cite, compare ce qu'il lui attribue
   à ce que tu as lu (le résumé suffit souvent) : appui oui, partiel, non, ou inverifiable (tu n'as
   pas pu lire assez), avec l'extrait lu et un commentaire bref.

Le verdict : confirmee (tout est juste), corrigee (l'œuvre existe, mais la référence est à
rectifier : rends alors `ref` corrigée, au format de la base — Auteurs, initiales. « Titre ».
*Revue* volume(numéro), pages (année).), introuvable (aucune trace fiable), mal_attribuee (l'œuvre
existe, mais un endroit lui fait dire ce qu'elle ne dit pas), doublon. `resume` : deux ou trois
phrases, en français.

Mesure : une référence n'est pas une revue de littérature. Trois recherches et quatre pages
suffisent presque toujours ; au-delà, l'outil t'est refusé : rends ce que tu as."""


def _titre(ref):
    m = re.search(r"«\s*(.+?)\s*»", ref or "")
    return (m.group(1) if m else (ref or "")[:120]).strip()


def candidats(cle, o):
    """Des œuvres de la base qui pourraient être la même : même DOI, ou titres très proches."""
    T = sources.toutes()
    doi = (o.get("doi") or "").lower()
    mots = set(re.findall(r"[a-z]{5,}", kb._plat(_titre(o.get("ref")))))
    out = []
    for c, x in T.items():
        if c == cle:
            continue
        if doi and (x.get("doi") or "").lower() == doi:
            out.append((c, "même DOI"))
            continue
        m2 = set(re.findall(r"[a-z]{5,}", kb._plat(_titre(x.get("ref")))))
        if mots and m2 and len(mots & m2) / max(len(mots), len(m2)) >= 0.6:
            out.append((c, "titre proche"))
    return out[:8]


def usages(cle):
    """Où l'œuvre est citée : les notes de l'essai (leur texte), et les fiches (le paragraphe)."""
    out = []
    for c in livre.chapitres():
        p = livre.dossier(c["slug"]) / "bibliographie.yaml"
        if not c.get("atelier") or not p.exists():
            continue
        for e in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("sources") or []:
            if str(e["cle"]) != cle:
                continue
            essai = (livre.dossier(c["slug"]) / "essai.md").read_text(encoding="utf-8")
            for n in e.get("notes") or []:
                m = re.search(r"^\[\^%s\]:\s*(.+?)(?=^\[\^|\Z)" % re.escape(n), essai, re.S | re.M)
                if m:
                    out.append({"ou": "note %s (chapitre %s)" % (n, c["slug"]), "texte": " ".join(m.group(1).split())[:1200]})
    for s in kb._slugs():
        _, corps = kb._lit(s)
        for texte, sec, titre in kb.blocs(corps):
            if not titre and "[@%s" % cle in texte.replace("; @", "; [@").replace(", @", ", [@"):
                out.append({"ou": "fiche %s, section {#%s}" % (s, sec), "texte": " ".join(texte.split())[:1200]})
    return out[:12]


def cree(corps, lancer=True):
    cle = (corps.get("cle") or "").strip()
    o = sources.lit(cle)                          # KeyError si l'œuvre n'est pas dans la base
    d = {"id": "r-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "reference", "portee": "reference", "mode": "recherche",
         "consigne": (corps.get("consigne") or "").strip(),
         "modele_choisi": reecriture._choix_modele(corps),
         "cible": {"cle": cle, "ref": o.get("ref"), "statut_avant": o.get("statut")},
         "etat": "en_attente", "cree": livre._maintenant(), "rang": time.time()}
    d["titre"] = titre_de(d)
    reecriture._ecrit(SLUG_KB, d)
    return demarre(d["id"]) if lancer else d


def titre_de(d):
    return "Vérifier la référence %s" % d["cible"]["cle"]


def demarre(ident):
    d = reecriture.lit(SLUG_KB, ident)
    cle = d["cible"]["cle"]
    o = sources.lit(cle)
    L = ["# L'œuvre à vérifier : %s" % cle, "Référence : %s" % (o.get("ref") or "?")]
    for k in ("doi", "url", "doute", "notes", "origine"):
        if o.get(k):
            L.append("%s : %s" % (k, o[k]))
    U = usages(cle)
    L.append("\n## Où le livre la cite (%d endroit(s))" % len(U))
    L += ["\n### %s\n%s" % (u["ou"], u["texte"]) for u in U] or ["(aucune citation par clé ; exploitée dans les fiches : %s)"
                                                                 % ", ".join(o.get("fiches") or []) or "rien"]
    C = candidats(cle, o)
    if C:
        L.append("\n## Œuvres proches déjà dans la base (doublon possible)")
        for c, pourquoi in C:
            L.append("- %s (%s) : %s" % (c, pourquoi, sources.lit(c).get("ref", "")[:300]))
    if d.get("consigne"):
        L.append("\n## Précision de l'auteur\n" + d["consigne"])
    d.update(etat="en_cours", lancee=livre._maintenant(),
             budget={"recherches": 0, "pages": 0, "limites": reecriture.limites("reference")},
             contexte={"systeme": SYSTEME, "message": "\n".join(L)})
    d["cible"]["usages"] = [u["ou"] for u in U]
    reecriture._ecrit(SLUG_KB, d)
    import asyncio
    t = asyncio.get_running_loop().create_task(_execute(ident))
    reecriture._taches.add(t)
    t.add_done_callback(reecriture._taches.discard)
    return d


async def _execute(ident):
    d = reecriture.lit(SLUG_KB, ident)
    outils = ["Read", "Grep", "Glob", "WebSearch", "WebFetch"]
    lim = d["budget"]["limites"]
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON, thinking=reecriture.PENSEE,
        tools=outils, allowed_tools=outils, max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": SCHEMA},
        hooks=reecriture.garde(d, lim), model=reecriture.modele("reference", d))
    await reecriture._lance(SLUG_KB, d, options, d["contexte"]["message"], conclut)


def conclut(d, sortie):
    R = dict(sortie)
    I = R.get("identite") or {}
    if I.get("doi"):
        I["doi"] = re.sub(r"^(doi:?\s*|https?://(dx\.)?doi\.org/)", "", I["doi"].strip(), flags=re.I)
    if R.get("doublon_de") and R["doublon_de"] not in sources.toutes():
        R["doublon_inconnu"] = R.pop("doublon_de")
    d.update(etat="prete", resultat=R)


def decide(ident, corps):
    """{action: retenir|rejeter, ref?, doi?, motif}. Retenir écrit l'œuvre et les chapitres qui la citent."""
    d = reecriture.lit(SLUG_KB, ident)
    if d["etat"] != "prete":
        raise reecriture.Conflit("la demande n'attend pas de décision (%s)" % d["etat"])
    motif = (corps.get("motif") or "").strip()
    if corps.get("action") == "rejeter":
        d.update(etat="decidee", decision={"proposition": None, "motif": motif, "date": livre._maintenant()})
        reecriture._ecrit(SLUG_KB, d)
        return d
    R = d["resultat"]
    cle = d["cible"]["cle"]
    o = dict(sources.lit(cle))
    I = R.get("identite") or {}
    ref = (corps.get("ref") or R.get("ref") or "").strip()
    doi = (corps.get("doi") if corps.get("doi") is not None else I.get("doi")) or o.get("doi")
    avant = {k: o.get(k) for k in ("ref", "doi", "url", "statut", "doute")}
    if ref and R["verdict"] in ("corrigee", "confirmee"):
        o["ref"] = ref
    o["doi"] = doi
    if I.get("url") and not o.get("url"):
        o["url"] = I["url"]
    o["statut"] = VERDICTS[R["verdict"]]
    if R["verdict"] == "doublon" and R.get("doublon_de"):
        o["doublon_de"] = R["doublon_de"]
    if R["verdict"] in ("confirmee", "corrigee"):
        o.pop("doute", None)
    o["verification"] = {"date": livre._maintenant()[:10], "demande": ident, "verdict": R["verdict"],
                         "resume": R.get("resume", "")[:600],
                         "citations": [{k: c.get(k) for k in ("ou", "appui", "commentaire")} for c in R.get("citations") or []]}
    sources.ecrit(cle, o)
    # les chapitres qui la citent : la référence à jour, le doute levé
    y = livre.yaml_rt()
    chapitres = []
    for c in livre.chapitres():
        p = livre.dossier(c["slug"]) / "bibliographie.yaml"
        if not c.get("atelier") or not p.exists():
            continue
        doc = y.load(p.read_text(encoding="utf-8"))
        change = False
        for e in doc.get("sources") or []:
            if str(e["cle"]) == cle:
                e["ref"], e["centrale"] = o.get("ref") or e.get("ref"), True
                if o.get("doi"):
                    e["doi"] = o["doi"]
                if "doute" in e and o["statut"] in ("verifiee", "corrigee"):
                    del e["doute"]
                change = True
        if change:
            p.write_text(livre.rt_texte(y, doc), encoding="utf-8")
            chapitres.append(c["slug"])
    sources.journal({"type": "reference_verifiee", "cle": cle, "demande": ident, "verdict": R["verdict"],
                     "avant": avant, "apres": {k: o.get(k) for k in avant}, "chapitres": chapitres, "motif": motif})
    d.update(etat="decidee", decision={"proposition": "retenue", "statut": o["statut"], "chapitres": chapitres,
                                       "motif": motif, "date": livre._maintenant()})
    reecriture._ecrit(SLUG_KB, d)
    return d
