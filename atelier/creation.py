# -*- coding: utf-8 -*-
"""La création d'une fiche : une question, Claude cherche, et propose une fiche nouvelle.

Une demande de type « fiche » vit dans kb/demandes/<id>.json (elle n'appartient à aucun
chapitre ; ceux qu'elle sert sont dans sa cible). Claude lit d'abord les fiches voisines —
s'il en trouve une qui couvre déjà la question, il le dit (doublon) plutôt que de la refaire —,
puis cherche selon les règles du livre, et rend une fiche structurée : question, confiance
par degré, sections sourcées ([@cle]), ce que le livre peut en tirer, sources avec extraits,
liens vers les fiches voisines, chapitres servis.

Créer écrit, et seulement ce qui est retenu :
  kb/fiches/<slug>.md    la fiche, en-tête « origine: claude · etat: brouillon », sections
                         identifiées ({#id}), sources en fin
  brief.yaml             la fiche ajoutée aux « fiches: » des chapitres cochés (journal)
Les liens inverses (depuis les fiches voisines) sont proposés, jamais écrits.
"""
import re
import json
import time
import secrets
import datetime

import markdown
from claude_agent_sdk import ClaudeAgentOptions

from . import livre, kb, reecriture, verification

SLUG_KB = "_kb"                     # le « chapitre » des demandes qui n'en ont pas
SKILL = reecriture.SKILL.parent / "fiche.md"
LONGUEURS = {"courte": "600 à 900 mots", "moyenne": "1 200 à 1 800 mots", "longue": "2 500 à 3 500 mots"}

SCHEMA = {
    "type": "object",
    "properties": {
        "doublon": {"type": "object", "properties": {
            "fiche": {"type": "string"}, "raison": {"type": "string"}, "a_ajouter": {"type": "string"}},
            "required": ["fiche", "raison"]},
        "slug": {"type": "string"},
        "titre": {"type": "string"},
        "sujet": {"type": "string"},
        "question": {"type": "string"},
        "confiance": {"type": "array", "items": {"type": "object", "properties": {
            "degre": {"type": "string"}, "sur": {"type": "string"}}, "required": ["degre", "sur"]}},
        "sections": {"type": "array", "items": {"type": "object", "properties": {
            "titre": {"type": "string"}, "niveau": {"type": "integer"}, "texte": {"type": "string"},
            "degre": {"type": "string", "enum": list(kb.DEGRES)}},
            "required": ["titre", "texte", "degre"]}},
        "retenir": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "object", "properties": {
            "cle": {"type": "string"}, "ref": {"type": "string"}, "doi": {"type": "string"},
            "url": {"type": "string"}, "extrait": {"type": "string"}, "verifie": {"type": "boolean"},
            "centrale": {"type": "boolean"}},
            "required": ["cle", "ref", "extrait", "verifie"]}},
        "liens": {"type": "array", "items": {"type": "object", "properties": {
            "fiche": {"type": "string"}, "raison": {"type": "string"}}, "required": ["fiche", "raison"]}},
        "chapitres": {"type": "array", "items": {"type": "object", "properties": {
            "slug": {"type": "string"}, "raison": {"type": "string"}}, "required": ["slug", "raison"]}},
    },
    "required": ["slug", "titre", "sujet", "question", "confiance", "sections", "retenir", "sources"]}


# ------------------------------------------------------------------ contexte

def index_texte():
    """L'index des fiches, une ligne chacune : de quoi choisir les voisines à lire."""
    ETATS = {"a_confirmer": " [écrite par Claude, à confirmer : pas relue]",
             "brouillon": " [écrite par Claude, brouillon : pas encore relue]"}
    return "\n".join("- %s — %s%s%s" % (f["slug"], f["titre"],
                                         " : " + f["sujet"][:160] if f["sujet"] and f["sujet"] != f["titre"] else "",
                                         ETATS.get(f.get("etat"), "") if f.get("origine") == "claude" else "")
                     for f in kb.index())


def proposees(sauf=None):
    """Les fiches proposées par une création rendue mais pas encore décidée : slug -> {demande,
    titre, sujet, sections}. Une demande qui part les voit, et ne les double pas."""
    import json
    rep_ = livre.LIVRE / "kb" / "demandes"
    out = {}
    for f in sorted(rep_.glob("f-*.json")) if rep_.exists() else []:
        x = json.loads(f.read_text(encoding="utf-8"))
        R = x.get("resultat") or {}
        if x["id"] == sauf or x.get("etat") != "prete" or R.get("doublon") or not R.get("slug"):
            continue
        out[R["slug"]] = {"demande": x["id"], "titre": R.get("titre", ""), "sujet": R.get("sujet", ""),
                          "question": R.get("question") or x["cible"]["question"],
                          "sections": [s.get("titre", "") for s in R.get("sections") or []]}
    return out


def compile_contexte(d):
    m = livre.meta()
    systeme = re.sub(r"<!--.*?-->\n*", "", SKILL.read_text(encoding="utf-8"), flags=re.S)
    for k, v in (("titre", m.get("titre", "")), ("longueur", LONGUEURS.get(d.get("longueur"), LONGUEURS["moyenne"]))):
        systeme = systeme.replace("{{%s}}" % k, v)
    c = d["cible"]
    L = ["# Question\n\n" + c["question"]]
    if c.get("slug"):
        L.append("\nSlug souhaité : %s" % c["slug"])
    if d.get("consigne"):
        L.append("\n## Précision de l'auteur\n" + d["consigne"])
    chap = {x["slug"]: x for x in livre.chapitres()}
    for s in c.get("chapitres") or []:
        x = chap.get(s)
        if not x:
            continue
        L.append("\n## Chapitre %s « %s »%s" % (x.get("numero") or "", x["title"],
                                                 " — " + x["periode"] if x.get("periode") else ""))
        if x.get("atelier"):
            at = livre.atelier(s)
            fs = (at.get("brief") or {}).get("fiches") or []
            if fs:
                L.append("Ses fiches : " + ", ".join(fs))
            ecarts = [(i, a) for i, a in at["assertions"].items() if a.get("ecart") or not a.get("essai")]
            if ecarts:
                L.append("Assertions du verrou mal étayées (ce que la fiche pourrait couvrir) :")
                L += ["- %s : %s%s" % (i, a["texte"], " — écart : %s" % a["ecart"]["texte"] if a.get("ecart") else " — aucun appui")
                      for i, a in ecarts[:25]]
        L.append(verification.texte_carnet(s, list(livre.atelier(s)["assertions"]) if x.get("atelier") else []))
    src = c.get("sources_initiales") or []
    if src:
        L.append("\n## Sources déjà trouvées (par la demande %s)" % c.get("depuis", "?"))
        L += ["- %s%s — « %s »%s" % (s.get("ref", ""), " <%s>" % s["url"] if s.get("url") else "",
                                    (s.get("extrait") or "")[:300], "" if s.get("verifie") else " (non vérifié)")
              for s in src[:20]]
    L.append("\n## Les fiches existantes (kb/fiches/<slug>.md) — lire les voisines d'abord\n\n" + index_texte())
    P = proposees(sauf=d["id"])
    if P:
        L.append("\n## Fiches proposées, pas encore créées — ne pas les doubler\n"
                 "D'autres recherches viennent de proposer ces fiches ; l'auteur ne les a pas encore créées. "
                 "Elles ne sont pas dans kb/fiches/, mais elles comptent : si l'une couvre déjà la question, "
                 "remplis `doublon` avec son slug ; sinon, découpe ton sujet pour ne pas la recouvrir, et "
                 "cite-la [[slug]] là où tu t'appuies sur elle.")
        for s, x in P.items():
            L.append("- %s — %s : %s\n  question : %s\n  sections : %s" % (
                s, x["titre"], x["sujet"][:200], x["question"][:200], " · ".join(x["sections"])[:400]))
    L.append(reecriture.texte_budget(d["budget"]["limites"]).replace(
        "Une assertion ne demande pas une revue de littérature — deux sources sérieuses qui concordent suffisent.",
        "Une fiche n'est pas une revue exhaustive : les sources de référence, et les récentes qui changent quelque chose."))
    depot, h = livre.heritage()
    if depot:
        L.append("\nBibliographie centrale (lecture seule, pour reprendre les clés) : %s" % (depot / h.get("bibliographie", "")))
    return systeme, "\n".join(x for x in L if x)


# ------------------------------------------------------------------ cycle de vie

def _slug(s):
    s = kb._plat(s)
    return "-".join(re.findall(r"[a-z0-9]+", s))[:60]


def cree(corps, lancer=True):
    question = " ".join((corps.get("question") or "").split())
    if len(question) < 8:
        raise ValueError("une fiche part d'une question : l'écrire")
    chap = {c["slug"] for c in livre.chapitres()}
    d = {"id": "f-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "fiche", "portee": "fiche", "mode": "recherche",
         "consigne": (corps.get("consigne") or "").strip(),
         "longueur": corps.get("longueur") if corps.get("longueur") in LONGUEURS else "moyenne",
         "modele_choisi": reecriture._choix_modele(corps),
         "cible": {"question": question, "slug": _slug(corps.get("slug") or "") or None,
                   "chapitres": [s for s in corps.get("chapitres") or [] if s in chap],
                   "depuis": corps.get("depuis"), "sources_initiales": corps.get("sources_initiales") or []},
         "etat": "en_attente", "cree": livre._maintenant(), "rang": time.time()}
    d["titre"] = titre_de(d)
    reecriture._ecrit(SLUG_KB, d)
    return demarre(d["id"]) if lancer else d


def demarre(ident):
    """Lancer une demande (tout de suite, ou sortie de la file) : le contexte est compilé
    maintenant — il voit les fiches créées pendant l'attente."""
    d = reecriture.lit(SLUG_KB, ident)
    d["etat"] = "en_cours"
    d["lancee"] = livre._maintenant()
    d["budget"] = {"recherches": 0, "pages": 0, "limites": reecriture.limites("fiche")}
    systeme, message = compile_contexte(d)
    d["contexte"] = {"systeme": systeme, "message": message}
    reecriture._ecrit(SLUG_KB, d)
    import asyncio
    t = asyncio.get_running_loop().create_task(_execute(d["id"]))
    reecriture._taches.add(t)
    t.add_done_callback(reecriture._taches.discard)
    return d


def titre_de(d):
    q = d["cible"]["question"]
    return "Fiche : " + (q[:90] + ("…" if len(q) > 90 else ""))


async def _execute(ident):
    d = reecriture.lit(SLUG_KB, ident)
    outils = ["Read", "Grep", "Glob", "WebSearch", "WebFetch"]
    lim = d.get("budget", {}).get("limites") or reecriture.limites("fiche")
    depot, _ = livre.heritage()
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON, thinking=reecriture.PENSEE,
        tools=outils, allowed_tools=outils, max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), add_dirs=[str(depot)] if depot else [],
        system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": SCHEMA},
        hooks=reecriture.garde(d, lim), model=reecriture.modele("fiche", d))
    await reecriture._lance(SLUG_KB, d, options, d["contexte"]["message"], conclut,
                            apres=_d_office if d.get("creer_d_office") else None)


def conclut(d, sortie):
    R = dict(sortie)
    R["slug"] = _slug(R.get("slug") or d["cible"].get("slug") or R.get("titre", "")) or "fiche"
    connues = {f["slug"] for f in kb.index()}
    P = proposees(sauf=d["id"])
    R["liens"] = [l for l in R.get("liens") or [] if l.get("fiche") in connues]
    chap = {c["slug"] for c in livre.chapitres()}
    R["chapitres"] = [c for c in R.get("chapitres") or [] if c.get("slug") in chap]
    if R.get("doublon") and R["doublon"].get("fiche") in P:          # doublon d'une fiche proposée, pas créée
        R["doublon"]["proposee"] = P[R["doublon"]["fiche"]]["demande"]
    elif R.get("doublon") and R["doublon"].get("fiche") not in connues:
        R.pop("doublon")
    if R["slug"] in P:                                                # même slug qu'une fiche proposée
        R["slug_propose_par"] = P[R["slug"]]["demande"]
    d.update(etat="prete", resultat=R)
    d["apercu"] = {"md": texte_fiche(d, R, R["slug"], R.get("titre", "")), "slug_libre": R["slug"] not in connues}
    d["apercu"]["html"] = kb._rendu(kb._entete(d["apercu"]["md"])[1], connues | set(P), {})
    cites = {m.group(1).strip() for m in kb.LIEN.finditer(d["apercu"]["md"])}
    d["apercu"]["liens_morts"] = sorted(cites - connues)             # [[x]] vers une fiche qui n'existe pas
    cles = {s["cle"] for s in R.get("sources") or []}
    d["apercu"]["cles_inconnues"] = sorted({k for k in re.findall(r"@([\w-]+)", d["apercu"]["md"])} - cles)


# ------------------------------------------------------------------ la fiche écrite

def _confiance(R):
    return " · ".join("%s (%s)" % (c["degre"].strip(), " ".join(c["sur"].split())) if c.get("sur") else c["degre"].strip()
                      for c in R.get("confiance") or [])


def texte_fiche(d, R, slug, titre, etat="brouillon"):
    """Le Markdown de la fiche, dans la forme des fiches du livre."""
    L = ["---", "type: science", "sujet: %s" % " ".join(R.get("sujet", "").split()),
         "confiance: %s" % _confiance(R), "origine: claude", "etat: %s" % etat,
         "demande: %s" % d["id"], "cree: %s" % datetime.date.today().isoformat(), "---", "",
         "# %s" % (titre or R.get("titre") or slug), "",
         "*Écrite pour répondre à une question : %s*" % " ".join((R.get("question") or d["cible"]["question"]).split()),
         "", "---", ""]
    n = 0
    for s in R.get("sections") or []:
        niv = 3 if s.get("niveau") == 3 else 2
        if niv == 2:
            n += 1
        titre_s = re.sub(r"^\d+(\.\d+)*\.?\s+", "", s["titre"].strip())
        L += ["%s %s%s" % ("#" * niv, "%d. " % n if niv == 2 else "", titre_s), "", s["texte"].strip(), ""]
    if R.get("retenir"):
        L += ["## Ce que le livre peut en tirer", "", R["retenir"].strip(), ""]
    liens = R.get("liens") or []
    if liens:
        L += ["## Voisines", ""] + ["- [[%s]] — %s" % (l["fiche"], l["raison"].strip()) for l in liens] + [""]
    if R.get("sources"):
        L += ["## Sources", ""]
        for s in R["sources"]:
            ligne = "- `%s` — %s" % (s["cle"], s["ref"].strip())
            if s.get("doi"):
                ligne += " DOI %s" % s["doi"]
            if s.get("url"):
                ligne += " <%s>" % s["url"]
            ligne += (" — « %s »" % " ".join(s["extrait"].split())) if s.get("extrait") else ""
            if not s.get("verifie"):
                ligne += " *(non vérifié)*"
            L.append(ligne)
        L.append("")
    return "\n".join(L)


def decide(ident, corps):
    """{action: creer|rejeter, slug, titre, chapitres: [...], motif}."""
    d = reecriture.lit(SLUG_KB, ident)
    if d["etat"] == "a_confirmer":
        return confirme(ident, corps)
    if d["etat"] != "prete":
        raise reecriture.Conflit("la demande n'attend pas de décision (%s)" % d["etat"])
    motif = (corps.get("motif") or "").strip()
    if corps.get("action") == "rejeter":
        d.update(etat="decidee", decision={"proposition": None, "motif": motif, "date": livre._maintenant()})
        reecriture._ecrit(SLUG_KB, d)
        return d
    R = d["resultat"]
    slug = _slug(corps.get("slug") or R["slug"])
    if not slug:
        raise ValueError("un slug : minuscules, chiffres, tirets")
    if (kb.dossier() / (slug + ".md")).exists():
        raise ValueError("la fiche « %s » existe déjà : choisir un autre slug" % slug)
    _ecrit_fiche(d, R, slug, (corps.get("titre") or "").strip() or R["titre"], "brouillon")
    relies = _relie(slug, corps.get("chapitres") or [], ident)
    d.update(etat="decidee", decision={"proposition": slug, "fiche": slug, "chapitres": relies,
                                       "motif": motif, "date": livre._maintenant()})
    reecriture._ecrit(SLUG_KB, d)
    return d


def _ecrit_fiche(d, R, slug, titre, etat):
    """Écrit la fiche (sections identifiées) et sa confiance par paragraphe (le degré de chaque section)."""
    ident = d["id"]
    p = kb.dossier() / (slug + ".md")
    texte, _ = kb.identifie(texte_fiche(d, R, slug, titre, etat))
    kb.dossier().mkdir(parents=True, exist_ok=True)
    p.write_text(texte, encoding="utf-8")
    # la confiance par paragraphe : le degré que Claude a donné à chaque section
    degres = {re.sub(r"^\d+(\.\d+)*\.?\s+", "", s["titre"].strip()): s.get("degre") for s in R.get("sections") or []}
    par, courant = {}, None
    for bloc, _, titre in kb.blocs(kb._entete(texte)[1]):
        if titre:
            m = kb.TITRE.match(bloc) if "\n" not in bloc else None
            courant = degres.get(re.sub(r"^\d+(\.\d+)*\.?\s+", "", m.group(2).strip())) if m else courant
        elif courant in kb.DEGRES:
            par[kb.empreinte_bloc(bloc)] = {"degre": courant, "raison": "degré de la section, donné à la création"}
    if par:
        kb.ecrit_confiance(slug, {"par": "creation", "demande": ident, "date": livre._maintenant(), "paragraphes": par})


def _relie(slug, chapitres, ident):
    """Ajoute la fiche aux « fiches: » des chapitres donnés (journal du chapitre)."""
    relies = []
    for s in chapitres:
        try:
            at = livre.atelier(s)
        except KeyError:
            continue
        fs = list((at.get("brief") or {}).get("fiches") or [])
        if slug not in fs:
            livre.modifie_brief(s, {"fiches": fs + [slug]}, livre.empreinte_brief(s),
                                motif="fiche créée par la demande %s" % ident)
            relies.append(s)
    return relies


def _d_office(_slug_kb, d):
    """La file, en mode « créer d'office » : la fiche est écrite dès que Claude a rendu sa réponse,
    à l'état « a_confirmer » ; les briefs attendent la confirmation. Un doublon n'est pas écrit."""
    R = d.get("resultat") or {}
    if d.get("etat") != "prete" or R.get("doublon") or not R.get("sections"):
        return
    slug, n = R["slug"], 2
    while (kb.dossier() / (slug + ".md")).exists():
        slug, n = "%s-%d" % (R["slug"], n), n + 1
    _ecrit_fiche(d, R, slug, R["titre"], "a_confirmer")
    kb.journal({"type": "creation_d_office", "fiche": slug, "demande": d["id"]})
    d.update(etat="a_confirmer", decision={"proposition": slug, "fiche": slug, "d_office": True,
                                           "date": livre._maintenant()})


def confirme(ident, corps):
    """Une fiche créée d'office : {action: confirmer, chapitres} -> brouillon, reliée aux chapitres ;
    {action: rejeter, liens, motif} -> à la corbeille."""
    d = reecriture.lit(SLUG_KB, ident)
    if d["etat"] != "a_confirmer":
        raise reecriture.Conflit("la demande n'attend pas de confirmation (%s)" % d["etat"])
    slug = d["decision"]["fiche"]
    motif = (corps.get("motif") or "").strip()
    if corps.get("action") == "rejeter":
        res = kb.supprime(slug, corps.get("liens", "retirer"), motif or "création d'office non confirmée")
        d.update(etat="decidee", decision=dict(d["decision"], proposition=None, rejetee=livre._maintenant(),
                                               corbeille=res["corbeille"], motif=motif))
    else:
        kb.pose_entete(slug, {"etat": "brouillon", "confirmee": livre._maintenant()[:10]})
        relies = _relie(slug, corps.get("chapitres") or [], ident)
        kb.journal({"type": "confirmation", "fiche": slug, "demande": ident, "chapitres": relies})
        d.update(etat="decidee", decision=dict(d["decision"], chapitres=relies, confirmee=livre._maintenant()))
    reecriture._ecrit(SLUG_KB, d)
    return d
