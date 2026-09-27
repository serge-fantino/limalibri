# -*- coding: utf-8 -*-
"""La confiance par paragraphe d'une fiche, lue par Claude à la demande.

La fiche dit sa confiance en tête, par degré (« établi (…) · débattu (…) »). Cette lecture
la redescend au paragraphe : pour chacun, un degré — établi, débattu, récent, hypothèse,
projeté, ou raisonnement (liaison, méthode, conseil d'écriture : pas un fait) — et une raison
brève. Claude juge sur le texte et sur la ligne de confiance, sans outils ni recherche : c'est
une lecture, pas une vérification.

Le résultat va dans kb/fiches/<slug>.confiance.json, jamais dans la fiche : chaque paragraphe
y est désigné par son empreinte ; un paragraphe dont le texte change perd sa marque.
"""
import time
import asyncio

from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage

from . import livre, kb, reecriture

SCHEMA = {
    "type": "object",
    "properties": {"paragraphes": {"type": "array", "items": {"type": "object", "properties": {
        "n": {"type": "integer"},
        "degre": {"type": "string", "enum": list(kb.DEGRES)},
        "raison": {"type": "string"}},
        "required": ["n", "degre", "raison"]}}},
    "required": ["paragraphes"]}

SYSTEME = """Tu lis une fiche scientifique d'un livre de vulgarisation en français, et tu donnes, pour
chaque paragraphe numéroté, son degré de confiance :

- établi : un fait acquis, mesuré, sur lequel le domaine s'accorde ;
- débattu : une question ouverte, des positions qui s'opposent, une valeur contestée ;
- récent : un résultat de ces dernières années, pas encore éprouvé ou répliqué ;
- hypothèse : un mécanisme ou une interprétation plausibles, non démontrés ;
- projeté : une projection, un modèle du futur, une extrapolation ;
- raisonnement : pas un fait — liaison, méthode, argument de l'auteur, conseil d'écriture.

Juge sur le texte du paragraphe (ses verbes, ses réserves, ses dates) et sur la ligne de
confiance de la fiche, qui dit quels points sont établis, débattus, récents. Un paragraphe qui
mêle deux degrés prend le moins sûr. La raison : dix mots au plus, en français. Ne cherche
rien, n'invente rien : c'est une lecture."""

_encours = {}


def paragraphes(slug):
    """Les paragraphes à juger : [(n, empreinte, section, texte)]."""
    _, corps = kb._lit(slug)
    titres, out, sec_titre = {}, [], ""
    for texte, sec, titre in kb.blocs(corps):
        if titre:
            m = kb.TITRE.match(texte) if "\n" not in texte else None
            if m:
                sec_titre = m.group(2)
            continue
        if len(" ".join(texte.split())) < 40:
            continue
        out.append((len(out) + 1, kb.empreinte_bloc(texte), sec_titre, texte))
    return out


def lance(slug, modele=None):
    kb._lit(slug)                                  # KeyError si la fiche n'existe pas
    if _encours.get(slug):
        raise reecriture.Conflit("une lecture est déjà en cours pour cette fiche")
    _encours[slug] = {"debut": time.time()}
    t = asyncio.get_running_loop().create_task(_lit(slug, modele))
    reecriture._taches.add(t)
    t.add_done_callback(reecriture._taches.discard)
    return etat(slug)


def etat(slug):
    e = _encours.get(slug)
    return {"en_cours": bool(e), "depuis_s": round(time.time() - e["debut"]) if e else None,
            "resultat": kb.confiance_par(slug)}


async def _lit(slug, modele):
    ps = paragraphes(slug)
    meta, _ = kb._lit(slug)
    message = "Fiche « %s »\nLigne de confiance : %s\n\n%s" % (
        slug, meta.get("confiance", "(aucune)"),
        "\n\n".join("[%d] (section : %s)\n%s" % (n, s, t) for n, _, s, t in ps))
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON,
        tools=[], allowed_tools=[], max_turns=3, setting_sources=[], cwd=str(livre.LIVRE),
        system_prompt=SYSTEME, output_format={"type": "json_schema", "schema": SCHEMA},
        model=modele or reecriture.modele("fiche"))
    resultat, nom = None, None
    try:
        async for m in query(prompt=message, options=options):
            if isinstance(m, AssistantMessage):
                nom = m.model
            elif isinstance(m, ResultMessage):
                resultat = m
        sortie = getattr(resultat, "structured_output", None) or {}
        par = {}
        emp = {n: e for n, e, _, _ in ps}
        for x in sortie.get("paragraphes") or []:
            if x.get("n") in emp and x.get("degre") in kb.DEGRES:
                par[emp[x["n"]]] = {"degre": x["degre"], "raison": x.get("raison", "")}
        if not par:
            raise ValueError("aucun paragraphe jugé")
        kb.ecrit_confiance(slug, {"par": "lecture", "modele": nom, "date": livre._maintenant(),
                                  "cout_usd": getattr(resultat, "total_cost_usd", None),
                                  "paragraphes": par})
    except Exception as e:                        # noqa: BLE001 — rendu à l'auteur
        ancien = kb.confiance_par(slug) or {}
        kb.ecrit_confiance(slug, dict(ancien, erreur="%s: %s" % (type(e).__name__, e), date_erreur=livre._maintenant()))
    finally:
        _encours.pop(slug, None)
