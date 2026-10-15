# -*- coding: utf-8 -*-
"""La relecture critique : Claude relit une partie du livre (ou quelques chapitres) en connaissant ses
règles et le reste du livre, et rend des constats ancrés sur les paragraphes — que l'auteur pose en
annotations.

Une demande « relecture » (kb/demandes/q-*.json ; capacité « relire »). Ce n'est ni la lecture naïve (un
lecteur qui ne sait rien, un chapitre), ni le harnais (des contrôles mécaniques) : c'est un relecteur
averti, qui lit tout le texte de la portée, et va voir ailleurs dans le livre (Grep, lecture) ce qui s'y dit
déjà. Ses constats :

    regle        un écart à une règle d'écriture (son numéro)
    repetition   ce que le livre dit déjà ailleurs (le chapitre, le paragraphe) — et lequel doit le garder
    recherche    une affirmation qui manque d'appui : une fiche à créer, ou à creuser
    fait         une affirmation douteuse ou fausse : à vérifier
    coherence    une contradiction avec un autre chapitre
    clarte       un passage qu'un lecteur ne suivra pas
    rythme       une longueur, un piétinement, une digression

Claude pose chaque constat lui-même, en annotation, avec l'outil « annoter » (limalibri/outils_livre.py) :
sur le paragraphe (^id), avec un extrait exact — l'outil refuse une ancre ou un extrait introuvables, Claude
corrige. Il rend à la fin un bilan par chapitre et une synthèse. La révision d'un chapitre lit ses
annotations ouvertes et les traite (limalibri/redaction.py). Si la relecture ne convient pas, « classer ses
annotations » les marque résolues d'un coup. Pas de web. Fable par défaut : c'est une lecture de jugement.
"""
import re
import time
import secrets

from claude_agent_sdk import ClaudeAgentOptions

from . import livre, reecriture

SLUG_KB = "_kb"
DEFAUT = "claude-fable-5-1"
TYPES = ("regle", "repetition", "recherche", "fait", "coherence", "clarte", "rythme")
LIB = {"regle": "écart à une règle", "repetition": "répétition", "recherche": "manque de recherche", "fait": "fait à vérifier",
       "coherence": "incohérence", "clarte": "clarté", "rythme": "rythme"}

SYSTEME = """Tu es le relecteur critique du livre « {titre} » — version {version}. Tu relis la portée indiquée
(une partie, ou quelques chapitres) EN ENTIER, paragraphe par paragraphe, et tu rends des constats précis.

Tu connais : les règles d'écriture de cette version (ci-dessous), le plan du livre (tous les chapitres et
leur synopsis), l'index des fiches. Le livre est dans ton répertoire de travail : lis les chapitres de la
portée (chapters/<slug>/{version}.md) en entier ; pour savoir si une idée est déjà ailleurs, cherche
(Grep sur chapters/*/{version}.md) et lis le passage. Les fiches (kb/fiches/) te disent ce qui est établi.
Pas de web.

Ce que tu cherches, dans cet ordre d'importance :
- repetition : la même explication, la même idée, le même exemple déjà donnés dans un autre chapitre, même
  avec d'autres mots. Nomme l'autre chapitre (et son paragraphe ^id si tu l'as), et dis lequel des deux
  doit garder le passage (en général : là où il sert le mieux le propos) ;
- regle : un écart à une règle d'écriture — cite son numéro (R3…) ;
- coherence : une contradiction avec un autre chapitre (un chiffre, une date, une explication) ;
- fait : une affirmation douteuse, imprécise ou fausse au regard des fiches ;
- recherche : une affirmation importante qui n'a pas d'appui dans les fiches — formule la question de la
  fiche à écrire (ou la fiche existante à creuser) ;
- clarte : ce qu'un lecteur curieux ne suivra pas ;
- rythme : une digression, un piétinement, une longueur.

Chaque constat, tu le POSES aussitôt avec l'outil « annoter » (mcp__limalibri__annoter) :
- chapitre, et bloc : l'ancre du paragraphe telle qu'elle est en fin de paragraphe (sans le ^) ;
- citation : un extrait EXACT de ce paragraphe (copié, 5 à 25 mots) ;
- texte : le problème en une ou deux phrases, et quoi faire (une reformulation, une coupe, un renvoi ; la
  question de la fiche à écrire ; la fiche à creuser) ;
- sorte, gravité (majeur : à traiter ; mineur : à voir), le numéro de règle s'il y en a une, et pour une
  répétition ou une incohérence l'autre chapitre (et son ^id).
Si l'outil refuse, corrige l'ancre ou l'extrait et recommence. Pas de constat vague, pas de compliment, pas
de doublon. Si un chapitre est bon, peu de constats.
Pour chaque chapitre, un bilan d'une ou deux phrases. Puis une synthèse de la portée : ses défauts
récurrents, ce qui revient d'un chapitre à l'autre. Tout en français.

## Les règles d'écriture ({version})
{regles}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "bilans": {"type": "array", "items": {"type": "object", "properties": {
            "chapitre": {"type": "string"}, "bilan": {"type": "string"}}, "required": ["chapitre", "bilan"]}},
        "synthese": {"type": "string"}},
    "required": ["synthese"]}


def _portee(corps):
    """(chapitres, partie) de la portée : une partie, ou une liste de chapitres."""
    from . import plan
    P = plan.lit()
    if corps.get("partie"):
        p = next((p for p in P["parties"] if p.get("id") == corps["partie"]), None)
        if not p:
            raise ValueError("partie inconnue : %s" % corps["partie"])
        return [c["slug"] for c in p["chapitres"]], p["id"]
    connus = [c["slug"] for c in livre.chapitres()]
    chs = [c for c in connus if c in set(corps.get("chapitres") or [])]
    if not chs:
        raise ValueError("une partie, ou des chapitres")
    return chs, None


def cree(corps):
    version = corps.get("version") or "essai"
    if version not in livre.VERSIONS:
        raise ValueError("version inconnue : %s" % version)
    chs, partie = _portee(corps)
    ecrits = [s for s in chs if (livre.dossier(s) / (version + ".md")).exists()]
    if not ecrits:
        raise ValueError("rien d'écrit à relire dans cette portée")
    choisi = reecriture._choix_modele(corps)
    d = {"id": "q-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "relecture", "portee": "relecture", "mode": "lecture",
         "consigne": (corps.get("consigne") or "").strip(),
         # Fable par défaut, sauf si le livre a réglé un modèle pour la relecture (claude.relecture.modele)
         "modele_choisi": choisi or (None if reecriture.modele("relecture") else DEFAUT),
         "cible": {"version": version, "chapitres": ecrits, "partie": partie},
         "etat": "en_attente", "cree": livre._maintenant(), "rang": time.time()}
    d["titre"] = "Relecture critique — %s" % (("partie %s" % partie) if partie else ", ".join(ecrits[:3]) + ("…" if len(ecrits) > 3 else ""))
    reecriture._ecrit(SLUG_KB, d)
    from . import file
    return file.part(SLUG_KB, d, "relecture", "demarre", d["id"])


def compile_contexte(d):
    from . import planif, plan, creation, regles
    version = d["cible"]["version"]
    systeme = SYSTEME.format(titre=livre.meta().get("titre", ""), version=version,
                             regles=regles.texte_pour_claude(version) or "(aucune)")
    noms = {c["slug"]: c for c in livre.chapitres()}
    intention = livre.intention_version(version)
    L = (["# Cette version, selon l'auteur (son intention : relis aussi à cette aune)", intention, ""] if intention else [])
    L.append("# La portée : relis ces chapitres en entier")
    for s in d["cible"]["chapitres"]:
        c = noms.get(s, {})
        L.append("- %s — %s%s : chapters/%s/%s.md" % (s, "%s. " % c["numero"] if c.get("numero") else "", c.get("title", s), s, version))
    if d.get("consigne"):
        L += ["", "# Précision de l'auteur", d["consigne"]]
    L += ["", "# Le plan du livre (pour savoir ce que disent les autres chapitres)", planif._texte_plan(plan.lit(), None, None),
          "", "# Les fiches (kb/fiches/<slug>.md)", creation.index_texte()]
    from . import refs
    L.append(refs.annexe(d.get("consigne")))
    return systeme, "\n".join(L)


def demarre(ident):
    d = reecriture.lit(SLUG_KB, ident)
    d.update(etat="en_cours", lancee=livre._maintenant(),
             budget={"recherches": 0, "pages": 0, "limites": reecriture.limites("relecture")})
    systeme, message = compile_contexte(d)
    d["contexte"] = {"systeme": systeme, "message": message}
    reecriture._ecrit(SLUG_KB, d)
    return reecriture.tache(_execute(ident))


async def _execute(ident):
    from . import outils_livre
    d = reecriture.lit(SLUG_KB, ident)
    outils = ["Read", "Grep", "Glob"]
    lim = d["budget"]["limites"]
    srv = outils_livre.serveur(ident, d["cible"]["version"], d["cible"]["chapitres"], auteur="relecture critique")
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON, thinking=reecriture.PENSEE,
        tools=outils, allowed_tools=outils + outils_livre.OUTILS, mcp_servers={outils_livre.NOM: srv},
        max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": SCHEMA},
        hooks=reecriture.garde(d, lim), model=reecriture.modele("relecture", d))
    await reecriture._lance(SLUG_KB, d, options, d["contexte"]["message"], conclut)


def posees(d):
    """Les annotations posées par cette relecture (leur origine le dit), chapitre par chapitre."""
    out = []
    for s in d["cible"]["chapitres"]:
        try:
            A = livre.annotations(s)
        except Exception:                                   # noqa: BLE001
            continue
        out += [dict(a, chapitre=s) for a in A if (a.get("origine") or {}).get("demande") == d["id"]]
    return out


def conclut(d, sortie):
    A = posees(d)
    d.update(etat="decidee", resultat={"bilans": sortie.get("bilans") or [], "synthese": sortie.get("synthese") or "",
                                       "annotations": len(A)},
             decision={"proposition": "annotations", "d_office": True, "date": livre._maintenant()})


def decide(ident, corps):
    """{action: ecarter, annotations?: [id]} : ces annotations (toutes les ouvertes, sans liste) passent résolues
    sans révision — ce qu'on n'applique pas. (« classer » : l'ancien nom.)"""
    d = reecriture.lit(SLUG_KB, ident)
    if corps.get("action") not in ("ecarter", "classer"):
        raise ValueError("action : ecarter")
    choix = set(corps.get("annotations") or [])
    n = 0
    for a in posees(d):
        if a.get("etat") == "ouverte" and (not choix or a["id"] in choix):
            livre.modifie_annotation(a["chapitre"], a["id"], {"etat": "resolue"})
            n += 1
    d["decision"] = dict(d.get("decision") or {}, ecartees=(d.get("decision") or {}).get("ecartees", 0) + n,
                         ecartees_le=livre._maintenant())
    reecriture._ecrit(SLUG_KB, d)
    return d


def applique(ident, corps):
    """Appliquer la relecture : {annotations: [id], consigne?, poser?, modele?} — une révision par chapitre
    concerné, en série (l'un après l'autre), chacune ne traitant que les annotations choisies de son chapitre."""
    from . import serie
    d = reecriture.lit(SLUG_KB, ident)
    choix = set(corps.get("annotations") or [])
    par = {}
    for a in posees(d):
        if a["id"] in choix and a.get("etat") == "ouverte":
            par.setdefault(a["chapitre"], []).append(a["id"])
    if not par:
        raise ValueError("aucune annotation ouverte choisie")
    cons = ("Traite les annotations de la relecture critique (listées dans le message) : règle chaque problème qu'elle "
            "signale — une répétition se coupe ici au profit de l'autre chapitre, avec un renvoi [chap:…] ; un écart à une "
            "règle se corrige ; un fait douteux se reprend d'après les fiches. Ne change rien d'autre que ce qu'elles demandent.")
    if (corps.get("consigne") or "").strip():
        cons += "\n\n" + corps["consigne"].strip()
    s = serie.cree({"etapes": [{"chapitre": ch, "action": "reviser", "consigne": cons, "annotations": ids} for ch, ids in par.items()],
                    "version": "essai", "poser": corps.get("poser") is not False, "modele": corps.get("modele")})
    d = reecriture.lit(SLUG_KB, ident)
    app = list((d.get("decision") or {}).get("applications") or [])
    app.append({"serie": s["id"], "date": livre._maintenant(), "chapitres": {ch: len(ids) for ch, ids in par.items()},
                "annotations": [i for ids in par.values() for i in ids]})
    d["decision"] = dict(d.get("decision") or {}, applications=app)
    reecriture._ecrit(SLUG_KB, d)
    return {"serie": s, "chapitres": {ch: len(ids) for ch, ids in par.items()}}
