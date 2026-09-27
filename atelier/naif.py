# -*- coding: utf-8 -*-
"""La lecture naïve : un relecteur qui n'a lu ni le cadre, ni le storyboard, ni le reste du livre.

C'est la porte que l'ancien cycle jugeait la plus importante, et la seule qu'aucun programme ne
fait (recit/cadre/00-relecture.md). Claude reçoit le texte d'un chapitre, et rien d'autre — pas
d'outils, pas de fiches, pas de verrou. Son ignorance est l'instrument : il relève chaque endroit
où il doit deviner.

Une demande de type « naive » vit dans chapters/<slug>/demandes/. Chaque relevé : le paragraphe,
la citation exacte, le type, ce qu'il a dû deviner, une reformulation qui change le moins de mots.
Décider, relevé par relevé : appliquer la reformulation (correction du paragraphe, au journal),
en faire une annotation, ou l'ignorer. Clore enregistre la lecture, avec l'empreinte du texte
tel qu'il est APRÈS les corrections (chapters/<slug>/relectures.json) : la porte « naïf » est
passée, et se rouvre dès qu'un mot change.
"""
import re
import time
import secrets

from claude_agent_sdk import ClaudeAgentOptions

from . import livre, reecriture, harnais, edition

TYPES = {"referent": "référent flottant", "ellipse": "ellipse non résolue", "formule": "formule cassée",
         "chiffre": "chiffre ambigu", "contradiction": "contradiction ou redite", "relire": "à relire deux fois"}

SCHEMA = {
    "type": "object",
    "properties": {
        "impression": {"type": "string"},
        "releves": {"type": "array", "items": {"type": "object", "properties": {
            "bloc": {"type": "string"},
            "citation": {"type": "string"},
            "type": {"type": "string", "enum": list(TYPES)},
            "devine": {"type": "string"},
            "reformulation": {"type": "string"}},
            "required": ["bloc", "citation", "type", "devine", "reformulation"]}}},
    "required": ["releves"]}

SYSTEME = """Tu es un lecteur. Tu n'as rien lu d'autre de ce livre : ni son plan, ni ses notes de travail,
ni les chapitres qui précèdent. On te donne un texte, et une seule consigne : relève chaque endroit où
tu dois DEVINER. Ton ignorance est l'instrument ; ne la compense pas par ta culture.

Six types de relevés :
- referent : un pronom ou un démonstratif sans antécédent clair ;
- ellipse : une formule raccourcie dont il manque un morceau ;
- formule : la syntaxe ou la logique ne retombe plus (une phrase cassée) ;
- chiffre : un nombre sans unité, ou deux nombres qu'on ne peut pas comparer ;
- contradiction : deux passages qui s'opposent, ou qui se répètent ;
- relire : une phrase correcte, mais qui oblige à revenir en arrière.

Pour chaque relevé : le repère du paragraphe (entre crochets devant lui : recopie-le sans les
crochets), la citation EXACTE (recopiée caractère pour caractère, la plus courte qui suffit), le type,
ce que tu as dû deviner, et une reformulation de cette citation qui change le moins de mots possible
et garde le ton. Ne juge ni le style ni le fond, ne propose rien d'autre : seulement ce qui oblige à
deviner. Un texte clair peut n'avoir aucun relevé. `impression` : une ou deux phrases, en lecteur."""


def cree(slug, corps):
    version = corps.get("version") or "recit"
    if version not in livre.VERSIONS:
        raise ValueError("version inconnue : %s" % version)
    B = harnais.blocs(slug, version)
    if not B:
        raise ValueError("pas de texte à lire")
    d = {"id": "n-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "naive", "portee": "naive", "mode": "lecture",
         "consigne": "", "modele_choisi": reecriture._choix_modele(corps),
         "cible": {"version": version, "blocs": [], "annotations": [], "empreinte": harnais.empreinte(slug, version)},
         "etat": "en_cours", "cree": livre._maintenant(),
         "budget": {"recherches": 0, "pages": 0, "limites": reecriture.limites("naive")}}
    c = next((x for x in livre.chapitres() if x["slug"] == slug), {})
    texte = "\n\n".join("[%s] %s" % (b, t) for b, t in B)
    d["contexte"] = {"systeme": SYSTEME, "message": "# %s\n\n%s" % (c.get("title", slug), texte)}
    d["titre"] = titre_de(d)
    reecriture._ecrit(slug, d)
    import asyncio
    t = asyncio.get_running_loop().create_task(_execute(slug, d["id"]))
    reecriture._taches.add(t)
    t.add_done_callback(reecriture._taches.discard)
    return d


def titre_de(d):
    return "Lecture naïve — %s" % ("récit" if d["cible"]["version"] == "recit" else "essai")


async def _execute(slug, ident):
    d = reecriture.lit(slug, ident)
    lim = d["budget"]["limites"]
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON, thinking=reecriture.PENSEE,
        tools=[], allowed_tools=[], max_turns=lim["tours"] + 1, setting_sources=[],
        cwd=str(livre.LIVRE), system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": SCHEMA}, model=reecriture.modele("naive", d))
    await reecriture._lance(slug, d, options, d["contexte"]["message"], conclut)


def _norm(s):
    return " ".join((s or "").split())


def conclut(d, sortie):
    out = []
    for r in sortie.get("releves") or []:
        r = dict(r)
        r["bloc"] = re.sub(r"[\[\]^\s]", "", r.get("bloc", ""))
        out.append(r)
    d.update(etat="prete", resultat={"impression": sortie.get("impression", ""), "releves": out})


def trouve(slug, version, r):
    """La citation est-elle (encore) dans son paragraphe ? Rend le texte du paragraphe, ou None."""
    if r["bloc"].startswith("note:"):
        return None
    try:
        t = edition.lit_bloc(slug, version, r["bloc"])["texte"]
    except KeyError:
        return None
    return t if _norm(r["citation"]) in _norm(t) else None


def decide(slug, ident, corps):
    """{actions: [{i, action: appliquer|annoter|ignorer, reformulation?}]} : puis la lecture est close
    et enregistrée (empreinte du texte après corrections)."""
    d = reecriture.lit(slug, ident)
    if d["etat"] != "prete":
        raise reecriture.Conflit("la demande n'attend pas de décision (%s)" % d["etat"])
    version = d["cible"]["version"]
    R = d["resultat"]["releves"]
    faits = []
    for x in corps.get("actions") or []:
        i, action = x.get("i"), x.get("action")
        if not isinstance(i, int) or not 0 <= i < len(R) or action not in ("appliquer", "annoter", "ignorer"):
            raise ValueError("action inconnue : %s" % x)
        r = R[i]
        if action == "appliquer":
            t = trouve(slug, version, r)
            if t is None:
                action = "annoter"                     # la citation n'y est plus : on garde le relevé en annotation
            else:
                nouveau = _norm(t).replace(_norm(r["citation"]), _norm(x.get("reformulation") or r["reformulation"]), 1)
                edition.modifie_bloc(slug, version, r["bloc"], nouveau, t, "lecture naïve %s (%s)" % (ident, TYPES.get(r["type"])))
        if action == "annoter":
            bloc = r["bloc"] if not r["bloc"].startswith("note:") else None
            if bloc:
                livre.cree_annotation(slug, {"version": version, "bloc": bloc, "citation": r["citation"],
                                             "type": "a-reecrire", "auteur": "lecture naïve",
                                             "texte": "%s — %s. Proposition : « %s »" % (TYPES.get(r["type"], r["type"]), r["devine"], r["reformulation"])})
        faits.append({"i": i, "action": action})
    traites = sum(1 for f in faits if f["action"] in ("appliquer", "annoter"))
    harnais.enregistre_naive(slug, version, ident, len(R), traites)
    d.update(etat="decidee", decision={"proposition": "close", "faits": faits, "date": livre._maintenant()})
    reecriture._ecrit(slug, d)
    return d
