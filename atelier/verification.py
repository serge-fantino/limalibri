# -*- coding: utf-8 -*-
"""La vérification : une ou plusieurs assertions du verrou, confrontées aux sources.

Une demande de type « verification » vit, comme une réécriture, dans
chapters/<slug>/demandes/<id>.json. Claude cherche (le livre en lecture seule, puis le web
par WebSearch/WebFetch, selon les règles du livre), rend un verdict par assertion avec ses
sources, et propose : un passage pour l'essai (nouveau paragraphe placé dans le plan, ou
complément d'un paragraphe), les œuvres à ajouter à la bibliographie, ce qui change dans le
verrou, et s'il faut réécrire le récit.

Retenir applique, et seulement ce qui est retenu :
  essai.md             le passage (nouveau ^id, ou texte du paragraphe complété) et ses notes
  bibliographie.yaml   les œuvres nouvelles
  verrou.yaml          l'assertion reliée au passage, l'écart levé, ou le texte corrigé (motif
                       et date dans la note, l'ancien texte gardé)
  annotations          l'annotation d'origine, résolue
  journal.jsonl        une ligne par changement
L'emplacement proposé par Claude peut être remplacé par l'auteur avant de retenir.
"""
import re
import json
import time
import secrets
import textwrap

from claude_agent_sdk import ClaudeAgentOptions
from ruamel.yaml import YAML

from . import livre, regles, essai, reecriture

SKILL = reecriture.SKILL.parent / "verification.md"
VERDICTS = ("etabli", "nuance", "contredit", "introuvable")

SCHEMA = {
    "type": "object",
    "properties": {
        "hypotheses": {"type": "array", "items": {"type": "object", "properties": {
            "assertion": {"type": "string"},
            "verdict": {"type": "string", "enum": list(VERDICTS)},
            "resume": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "object", "properties": {
                "ref": {"type": "string"}, "doi": {"type": "string"}, "url": {"type": "string"},
                "extrait": {"type": "string"}, "verifie": {"type": "boolean"}},
                "required": ["ref", "extrait", "verifie"]}}},
            "required": ["assertion", "verdict", "resume", "sources"]}},
        "essai": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["ajout", "complement", "aucune"]},
            "section": {"type": "string"},
            "apres_bloc": {"type": "string"},
            "bloc": {"type": "string"},
            "texte": {"type": "string"},
            "notes": {"type": "array", "items": {"type": "object", "properties": {
                "cle": {"type": "string"}, "texte": {"type": "string"}}, "required": ["cle", "texte"]}},
            "justification": {"type": "string"}},
            "required": ["action", "justification"]},
        "bibliographie": {"type": "array", "items": {"type": "object", "properties": {
            "cle": {"type": "string"}, "ref": {"type": "string"}, "doi": {"type": "string"}},
            "required": ["cle", "ref"]}},
        "verrou": {"type": "array", "items": {"type": "object", "properties": {
            "assertion": {"type": "string"},
            "action": {"type": "string", "enum": ["lier", "nuancer", "corriger", "rien"]},
            "texte": {"type": "string"}, "motif": {"type": "string"}},
            "required": ["assertion", "action"]}},
        "recit": {"type": "object", "properties": {
            "a_reecrire": {"type": "boolean"}, "raison": {"type": "string"}},
            "required": ["a_reecrire"]}},
    "required": ["hypotheses", "essai", "verrou", "recit"]}


# ------------------------------------------------------------------ contexte

def _plan_texte(slug):
    """Le plan de l'essai, lisible : sections (id) et paragraphes (^id, premiers mots)."""
    P = essai.plan(slug)
    L = []

    def f(s, ind):
        if s["id"]:
            L.append("%s%s [section %s]" % ("  " * ind, s["titre"], s["id"]))
        for b in s["blocs"]:
            L.append("%s  ^%s — %s" % ("  " * ind, b["id"], b["debut"]))
        for e in s["enfants"]:
            f(e, ind + 1)
    f(P["arbre"], 0)
    return "\n".join(L)


def _fiches_du_chapitre(slug):
    f = (livre.atelier(slug).get("brief") or {}).get("fiches") or []
    return " — celles du chapitre : %s" % ", ".join(str(x) for x in f) if f else ""


def compile_contexte(slug, d):
    m = livre.meta()
    at = livre.atelier(slug)
    textes_e = dict(reecriture._blocs(slug, "essai"))
    textes_r = dict(reecriture._blocs(slug, "recit"))
    systeme = re.sub(r"<!--.*?-->\n*", "", SKILL.read_text(encoding="utf-8"), flags=re.S)
    for k, v in (("titre", m.get("titre", "")), ("slug", slug),
                 ("regles", regles.texte_pour_claude("essai") or "(pas de garde-fous pour l'essai)")):
        systeme = systeme.replace("{{%s}}" % k, v)

    c = next((x for x in livre.chapitres() if x["slug"] == slug), {})
    L = ["# Chapitre « %s »%s" % (c.get("title", slug), " — %s" % c["periode"] if c.get("periode") else "")]
    L.append("\n## Assertions à vérifier")
    for aid in d["cible"]["assertions"]:
        a = at["assertions"].get(aid, {})
        L.append("\n### %s (%s) : %s" % (aid, a.get("statut", "?"), a.get("texte", "?")))
        if a.get("note"):
            L.append("note du verrou : %s" % a["note"])
        if a.get("ecart"):
            L.append("écart connu (%s) : %s" % (a["ecart"]["type"], a["ecart"]["texte"]))
        for e in a.get("essai") or []:
            L.append("appui actuel dans l'essai (%s, ^%s) : %s" % (e["appui"], e["bloc"], textes_e.get(e["bloc"], "?")[:900]))
        if not a.get("essai"):
            L.append("aucun appui dans l'essai")
        for b, l in at["links"]["recit"].items():
            if aid in (l.get("assertions") or []):
                L.append("ce que dit le récit (^%s) : %s" % (b, textes_r.get(b, "?")))
    ann = next((x for x in livre.annotations(slug) if x["id"] == d["cible"].get("annotation")), None)
    if ann:
        L.append("\n## La question de l'auteur (annotation %s)\n%s%s" % (
            ann["id"], "sur « %s » : " % ann["citation"] if ann.get("citation") else "", ann.get("texte", "")))
    if d.get("consigne"):
        L.append("\n## Précision de l'auteur\n" + d["consigne"])
    L.append("\n## Le plan de l'essai (sections et paragraphes, pour placer un ajout)\n\n" + _plan_texte(slug))
    biblio = at.get("bibliographie") or []
    if biblio:
        L.append("\n## Bibliographie du chapitre (clés déjà disponibles)\n" +
                 "\n".join("- %s : %s" % (b["cle"], b["ref"][:160]) for b in biblio))
    L.append(texte_carnet(slug, d["cible"]["assertions"]))
    L.append(reecriture.texte_budget(d["budget"]["limites"]))
    depot, h = livre.heritage()
    L.append("\n## Où chercher dans le livre (lecture seule)\n"
             "Dossier courant : chapters/%s/ (essai.md, verrou.yaml, bibliographie.yaml) ; les fiches "
             "scientifiques du livre : kb/fiches/<slug>.md%s%s." % (
                 slug, _fiches_du_chapitre(slug),
                 " ; dépôt d'origine : %s — bibliographie centrale %s" % (depot, h.get("bibliographie", "")) if depot else ""))
    return systeme, "\n".join(L)


# ------------------------------------------------------------------ normaliser

ID_ASSERTION = re.compile(r"^\s*(\d+\.\d+[a-z]?)")


def _id(x):
    """« 1.1 — la mer était… » ou « 1.1 » -> « 1.1 » ; « ^b54b » -> « b54b »."""
    x = (x or "").strip()
    m = ID_ASSERTION.match(x)
    return m.group(1) if m else x.lstrip("^").split()[0] if x else x


def _normalise(R, ids=None):
    """Claude rend parfois l'assertion avec son texte, ou un paragraphe avec son ^ : on garde l'id.
    Un id qui n'est pas parmi ceux demandés, quand un seul l'était, est celui-là."""
    def aid(x):
        i = _id(x)
        return ids[0] if ids and len(ids) == 1 and i not in ids else i
    for h in R.get("hypotheses") or []:
        h["assertion"] = aid(h.get("assertion"))
    for v in R.get("verrou") or []:
        v["assertion"] = aid(v.get("assertion"))
    E = R.get("essai") or {}
    for k in ("bloc", "apres_bloc"):
        if E.get(k):
            E[k] = _id(E[k])
    if E.get("section"):
        s = E["section"].strip()
        E["section"] = s if re.fullmatch(r"[\w-]+", s) else None
    return R


# ------------------------------------------------------------------ cycle de vie

def cree(slug, corps):
    at = livre.atelier(slug)
    ids = [a for a in (corps.get("assertions") or []) if a in at["assertions"]]
    ann = corps.get("annotation")
    if ann and not ids:                          # une annotation : les assertions de son paragraphe
        a = next((x for x in livre.annotations(slug) if x["id"] == ann), None)
        if a:
            l = at["links"].get(a["version"], {}).get(a["bloc"], {})
            ids = list(l.get("assertions") or [])
    if not ids:
        raise ValueError("aucune assertion à vérifier")
    d = {"id": "v-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "verification", "portee": "verification", "mode": "recherche",
         "consigne": (corps.get("consigne") or "").strip(),
         "modele_choisi": reecriture._choix_modele(corps),
         "cible": {"version": "essai", "assertions": ids, "annotation": ann,
                   "annotations": [ann] if ann else [], "blocs": []},
         "etat": "en_cours", "cree": livre._maintenant(),
         "budget": {"recherches": 0, "pages": 0, "limites": reecriture.limites("verification")}}
    systeme, message = compile_contexte(slug, d)
    d["contexte"] = {"systeme": systeme, "message": message}
    d["_slug"] = slug
    d["titre"] = reecriture.titre_de(d)
    d.pop("_slug")
    reecriture._ecrit(slug, d)
    import asyncio
    t = asyncio.get_running_loop().create_task(_execute(slug, d["id"]))
    reecriture._taches.add(t)
    t.add_done_callback(reecriture._taches.discard)
    return d


async def _execute(slug, ident):
    d = reecriture.lit(slug, ident)
    outils = ["Read", "Grep", "Glob", "WebSearch", "WebFetch"]
    lim = d.get("budget", {}).get("limites") or reecriture.limites("verification")
    depot, _ = livre.heritage()
    options = ClaudeAgentOptions(
        tools=outils, allowed_tools=outils, max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), add_dirs=[str(depot)] if depot else [],
        system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": SCHEMA},
        hooks=reecriture.garde(d, lim), model=reecriture.modele("verification", d))
    await reecriture._lance(slug, d, options, d["contexte"]["message"], conclut, apres=au_carnet)


def conclut(d, sortie):
    d.update(etat="prete", resultat=_normalise(sortie, d["cible"]["assertions"]))


# ------------------------------------------------------------------ carnet de recherche

# Le carnet du chapitre (chapters/<slug>/recherches.jsonl) : ce que chaque vérification a lu,
# conclu, et n'a pas pu ouvrir. Il est rendu aux vérifications suivantes — la mémoire d'une
# demande à l'autre, sans rejouer les sessions.

def au_carnet(slug, d):
    R = d.get("resultat") or {}
    e = {"demande": d["id"], "date": livre._maintenant(), "issue": d["etat"],
         "assertions": d["cible"]["assertions"],
         "verdicts": [{k: h.get(k) for k in ("assertion", "verdict", "resume")} for h in R.get("hypotheses") or []],
         "sources": [dict({k: s.get(k) for k in ("ref", "url", "doi", "extrait", "verifie") if s.get(k) is not None},
                          assertion=h.get("assertion"))
                     for h in R.get("hypotheses") or [] for s in h.get("sources") or []],
         "pages": d.get("pages") or [], "inaccessibles": d.get("inaccessibles") or []}
    with (livre.dossier(slug) / "recherches.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")


def carnet(slug):
    """Le carnet, une entrée par demande (la plus récente l'emporte : une reprise complète)."""
    p = livre.dossier(slug) / "recherches.jsonl"
    par = {}
    for l in p.read_text(encoding="utf-8").splitlines() if p.exists() else []:
        if l.strip():
            e = json.loads(l)
            par[e["demande"]] = e
    return sorted(par.values(), key=lambda e: e["date"])


def texte_carnet(slug, ids):
    C = carnet(slug)
    if not C:
        return ""
    L = ["\n## Carnet de recherche du chapitre (vérifications précédentes)"]
    verdicts = [(e["date"][:10], v) for e in C for v in e["verdicts"] if v.get("assertion") in ids]
    if verdicts:
        L.append("Verdicts déjà rendus :")
        L += ["- %s %s (%s) : %s" % (v["assertion"], v.get("verdict"), date, (v.get("resume") or "")[:300])
              for date, v in verdicts]
    vues, sources = set(), []
    for e in reversed(C):
        for s in e["sources"]:
            cle = s.get("url") or s.get("ref")
            if s.get("assertion") in ids and cle not in vues:
                vues.add(cle)
                sources.append(s)
    if sources:
        L.append("Sources déjà lues pour ces assertions (les réutiliser plutôt que de les relire) :")
        L += ["- [%s] %s%s — « %s »%s" % (s.get("assertion"), s.get("ref", "")[:160], " <%s>" % s["url"] if s.get("url") else "",
                                        (s.get("extrait") or "")[:300], "" if s.get("verifie") else " (non vérifié)")
              for s in sources[:20]]
    morts = sorted({u for e in C for u in e.get("inaccessibles") or [] if u})
    if morts:
        L.append("Pages inaccessibles déjà essayées — ne pas y retourner :")
        L += ["- " + u for u in morts[:30]]
    return "\n".join(L) if len(L) > 1 else ""


# ------------------------------------------------------------------ appliquer

def _nouvel_id(slug):
    pris = {b for b, _ in reecriture._blocs(slug, "essai")} | {b for b, _ in reecriture._blocs(slug, "recit")}
    while True:
        i = secrets.token_hex(2)
        if i not in pris and not i.isdigit() and not re.fullmatch(r"\d+e\d+", i):   # « 5e56 » serait un nombre en YAML
            return i


def _paragraphe(texte, ident):
    texte = re.sub(r"\s*\^[a-z0-9]{4,}\b", "", texte)      # Claude recopie parfois l'identifiant
    return textwrap.fill(" ".join(texte.split()), width=100, break_long_words=False,
                         break_on_hyphens=False) + " ^" + ident


def _yaml():
    return livre.yaml_rt()


def decide(slug, ident, corps):
    d = reecriture.lit(slug, ident)
    if d["etat"] != "prete":
        raise reecriture.Conflit("demande %s : rien à décider (%s)" % (ident, d["etat"]))
    quand = livre._maintenant()
    motif = (corps.get("motif") or "").strip()
    if not corps.get("retenir"):
        d["decision"] = {"proposition": None, "motif": motif, "date": quand}
        d["etat"] = "decidee"
        reecriture._ecrit(slug, d)
        return d

    R = _normalise(d["resultat"])
    E = R.get("essai") or {}
    journal = []
    bloc_essai = None
    cles_notes = [n["cle"].strip().lstrip("[^").rstrip("]") for n in (E.get("notes") or [])]

    # 1. l'essai
    if E.get("action") in ("ajout", "complement") and E.get("texte"):
        us = essai._lit(slug)
        existantes = {u["brut"].split("]:", 1)[0][2:] for u in us if u["kind"] == "autre" and u["brut"].startswith("[^")}
        notes = []
        for n, cle in zip(E.get("notes") or [], cles_notes):
            if not cle.startswith(slug + "-"):
                cle = slug + "-" + cle
            while cle in existantes:
                cle += "-bis"
            notes.append((n["cle"].strip().lstrip("[^").rstrip("]"), cle, n["texte"]))
            existantes.add(cle)
        texte = E["texte"]
        for avant, apres, _ in notes:                 # les clés éventuellement préfixées
            texte = texte.replace("[^%s]" % avant, "[^%s]" % apres)
        if E["action"] == "complement":
            bloc_essai = E.get("bloc")
            i = essai._index(us, "bloc", bloc_essai)
            journal.append({"type": "texte", "version": "essai", "bloc": bloc_essai,
                            "avant": us[i]["brut"], "apres": texte})
            us[i]["brut"] = _paragraphe(texte, bloc_essai)
        else:
            bloc_essai = _nouvel_id(slug)
            place = corps.get("place") or ({"type": "bloc", "id": E["apres_bloc"], "place": "apres"}
                                           if E.get("apres_bloc") else
                                           {"type": "section", "id": E.get("section"), "place": "fin"})
            k = essai._position(us, place)
            us[k:k] = [{"kind": "bloc", "id": bloc_essai, "brut": _paragraphe(texte, bloc_essai)}]
            journal.append({"type": "texte", "version": "essai", "bloc": bloc_essai, "avant": None,
                            "apres": texte, "place": place})
        if notes:
            dernier = max((j for j, u in enumerate(us) if u["kind"] == "autre" and u["brut"].startswith("[^")),
                          default=len(us) - 1)
            nouvelles = [{"kind": "autre", "brut": "[^%s]: %s" % (cle, " ".join(t.split()))} for _, cle, t in notes]
            us[dernier + 1:dernier + 1] = nouvelles
        essai._fichier(slug).write_text(essai._texte(us), encoding="utf-8")

    # 2. la bibliographie du chapitre
    centrale = livre.sources()
    pb = livre.dossier(slug) / "bibliographie.yaml"
    y = _yaml()
    if R.get("bibliographie"):
        doc = y.load(pb.read_text(encoding="utf-8")) if pb.exists() else {"chapter": slug, "sources": []}
        presentes = {s["cle"] for s in doc.get("sources") or []}
        for b in R["bibliographie"]:
            if b["cle"] in presentes:
                continue
            e = {"cle": b["cle"], "ref": b["ref"]}
            if b.get("doi"):
                e["doi"] = b["doi"]
            e.update(centrale=b["cle"] in centrale, citation="cle")
            e["ajoute_par"] = ident
            doc.setdefault("sources", []).append(e)
            journal.append({"type": "bibliographie", "cle": b["cle"]})
        pb.write_text(livre.rt_texte(y, doc), encoding="utf-8")

    # 3. le verrou
    pv = livre.dossier(slug) / "verrou.yaml"
    doc = y.load(pv.read_text(encoding="utf-8"))
    verdicts = {h["assertion"]: h for h in R.get("hypotheses") or []}
    for v in R.get("verrou") or []:
        a = next((x for s in doc["sections"] for x in s["assertions"] if x["id"] == v["assertion"]), None)
        if a is None or v["action"] == "rien":
            continue
        if bloc_essai and v["action"] in ("lier", "nuancer", "corriger"):
            liens = a.setdefault("essai", [])
            deja = next((l for l in liens if l["bloc"] == bloc_essai), None)
            if deja:
                deja["appui"] = "direct"             # le paragraphe complété étaie désormais l'assertion
            else:
                liens.append({"bloc": bloc_essai, "appui": "direct"})
        if v["action"] in ("corriger", "nuancer") and v.get("texte"):
            ancien = a["texte"]
            a["texte"] = " ".join(v["texte"].split())
            trace = "%s le %s (%s) : avant « %s » — %s" % (
                "corrigé" if v["action"] == "corriger" else "nuancé", quand[:10], ident, ancien, v.get("motif", ""))
            a["note"] = (a.get("note", "") + " ; " if a.get("note") else "") + trace
            journal.append({"type": "verrou", "assertion": a["id"], "avant": ancien, "apres": a["texte"]})
        h = verdicts.get(a["id"])
        a["verifie"] = {"date": quand[:10], "demande": ident, "verdict": h["verdict"] if h else None}
        if a.get("ecart") and v["action"] in ("lier", "corriger", "nuancer"):
            journal.append({"type": "verrou", "assertion": a["id"], "ecart_leve": dict(a["ecart"])})
            del a["ecart"]
    pv.write_text(livre.rt_texte(y, doc), encoding="utf-8")

    # 4. l'annotation d'origine, et le journal
    if d["cible"].get("annotation"):
        livre._ajoute(slug, {"id": d["cible"]["annotation"], "etat": "resolue", "resolue_par": ident, "modifie": quand})
    with (livre.dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
        for j in journal:
            f.write(json.dumps(dict(j, date=quand, source=ident, motif=motif), ensure_ascii=False) + "\n")
    d["decision"] = {"proposition": "retenue", "motif": motif, "date": quand, "bloc_essai": bloc_essai,
                     "place": corps.get("place")}
    d["etat"] = "decidee"
    reecriture._ecrit(slug, d)
    return d
