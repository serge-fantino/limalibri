# -*- coding: utf-8 -*-
"""Les outils de LimaLibri donnés à Claude (un serveur MCP en mémoire, par demande) : agir sur le livre
par les mêmes fonctions que l'auteur, avec leurs garde-fous.

    annoter    pose une annotation sur un paragraphe (^id) d'un chapitre, avec un extrait exact du
               paragraphe. Refusé, avec la raison, si le chapitre, le paragraphe ou l'extrait ne sont pas
               trouvés — Claude corrige et recommence. Une annotation porte son origine (la demande, la
               sorte de constat, sa gravité) : on la retrouve, on la classe en bloc.

Les annotations sont des notes : elles n'écrivent rien dans le texte ; la révision d'un chapitre les lit et
les traite (limalibri/redaction.py). Le nom vu par Claude : mcp__limalibri__annoter.
"""
import re

from claude_agent_sdk import tool, create_sdk_mcp_server

from . import livre

NOM = "limalibri"
SORTES = ("regle", "repetition", "recherche", "fait", "coherence", "clarte", "rythme", "remarque")


def _plat(t):
    return re.sub(r"\s+", " ", re.sub(r"\[\^[^\]]+\]|\[@[^\]]+\]|[*_`«»“”\"']", "", t or "")).strip().lower()


def serveur(demande, version=None, chapitres=None, auteur="Claude", poses=None):
    """Le serveur d'outils d'une demande. chapitres : la portée permise (None : tout le livre) ; poses : une
    liste où noter les annotations posées (le déroulé de la demande s'en sert)."""
    from . import harnais
    permis = set(chapitres) if chapitres else None
    noms = {c["slug"] for c in livre.chapitres()}

    @tool("annoter", "Pose une annotation sur un paragraphe d'un chapitre. chapitre : son slug ; bloc : l'ancre du "
          "paragraphe (les 4 caractères après ^ en fin de paragraphe, sans le ^) ; citation : un extrait EXACT du "
          "paragraphe (5 à 25 mots) ; texte : le constat et ce qu'il faudrait faire ; sorte : regle, repetition, "
          "recherche, fait, coherence, clarte, rythme ou remarque ; regle : le numéro (R3) si c'est un écart à une "
          "règle ; gravite : majeur ou mineur ; autre_chapitre / autre_bloc : où le livre le dit déjà (répétition, "
          "incohérence). Refusé, avec la raison, si l'ancre ou l'extrait ne sont pas trouvés.",
          {"type": "object", "properties": {
              "chapitre": {"type": "string"}, "bloc": {"type": "string"}, "citation": {"type": "string"},
              "texte": {"type": "string"}, "sorte": {"type": "string", "enum": list(SORTES)},
              "regle": {"type": "string"}, "gravite": {"type": "string", "enum": ["majeur", "mineur"]},
              "autre_chapitre": {"type": "string"}, "autre_bloc": {"type": "string"},
              **({} if version else {"version": {"type": "string", "enum": list(livre.VERSIONS)}})},
           "required": ["chapitre", "bloc", "citation", "texte"]})
    async def annoter(a):
        def refus(m):
            return {"content": [{"type": "text", "text": "REFUSÉ : " + m}], "is_error": True}
        ch = (a.get("chapitre") or "").strip()
        if ch not in noms:
            return refus("chapitre inconnu « %s » (un slug du plan)" % ch)
        if permis is not None and ch not in permis:
            return refus("le chapitre « %s » est hors de la portée de cette demande" % ch)
        bloc = (a.get("bloc") or "").strip().lstrip("^")
        v = version or a.get("version") or "essai"
        try:
            B = dict(harnais.blocs(ch, v))
        except Exception:                                   # noqa: BLE001
            return refus("pas de texte %s pour ce chapitre" % v)
        if bloc.startswith("note:"):
            return refus("une note de bas de page ne s'annote pas : vise le paragraphe qui l'appelle")
        if bloc not in B:
            return refus("paragraphe ^%s introuvable dans %s (%s) : relis le fichier, l'ancre est en fin de paragraphe" % (bloc, ch, v))
        if _plat(a.get("citation")) not in _plat(B[bloc]):
            return refus("l'extrait n'est pas dans le paragraphe ^%s : copie-le exactement" % bloc)
        sorte = a.get("sorte") or "remarque"
        lib = {"regle": "écart à une règle", "repetition": "répétition", "recherche": "manque de recherche",
               "fait": "fait à vérifier", "coherence": "incohérence", "clarte": "clarté", "rythme": "rythme"}.get(sorte)
        texte = " ".join((a.get("texte") or "").split())
        if a.get("autre_chapitre"):
            texte += " (voir %s%s)" % (a["autre_chapitre"], " ^" + a["autre_bloc"].lstrip("^") if a.get("autre_bloc") else "")
        e = livre.cree_annotation(ch, {
            "version": v, "bloc": bloc, "citation": a.get("citation"),
            "type": "question" if sorte in ("fait", "recherche") else "a-reecrire" if sorte != "remarque" else "remarque",
            "regles": [a["regle"]] if a.get("regle") else [], "auteur": auteur,
            "texte": ("[%s%s] " % (lib, " " + a["regle"] if a.get("regle") else "") if lib else "") + texte,
            "origine": {"demande": demande, "sorte": sorte, "gravite": a.get("gravite") or "mineur",
                        "autre_chapitre": a.get("autre_chapitre"), "autre_bloc": a.get("autre_bloc")}})
        if poses is not None:
            poses.append({"chapitre": ch, "annotation": e["id"], "bloc": bloc, "sorte": sorte, "gravite": a.get("gravite") or "mineur"})
        return {"content": [{"type": "text", "text": "annotation %s posée sur %s ^%s (%s)" % (e["id"], ch, bloc, v)}]}

    return create_sdk_mcp_server(NOM, tools=[annoter])


OUTILS = ["mcp__%s__annoter" % NOM]
