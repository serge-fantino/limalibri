# -*- coding: utf-8 -*-
"""La réécriture assistée : une demande, un contexte compilé, des propositions, une décision.

Une demande vit dans chapters/<slug>/demandes/<id>.json. Elle garde tout :
  cible        la portée (annotation | paragraphe | plan), les paragraphes visés et leur
               texte au moment de la demande, les annotations à traiter
  contexte     exactement ce que Claude a reçu (consigne système + message) — quand un
               texte déçoit, on peut relire ce qui a été demandé
  propositions ce que Claude rend (un texte par paragraphe, une note, les annotations traitées)
  decision     la proposition retenue, ou aucune, et le motif — les rejets restent : c'est
               ce qui apprend à l'atelier ce que l'auteur ne veut pas

Claude ne modifie jamais le texte. Retenir une proposition réécrit les paragraphes visés dans
recit.md (et seulement eux, ^id conservés), ajoute une ligne au journal des modifications
(chapters/<slug>/journal.jsonl) et résout les annotations traitées.
"""
import re
import json
import time
import asyncio
import secrets
import pathlib
import textwrap

from claude_agent_sdk import (query, ClaudeAgentOptions, ResultMessage, AssistantMessage, UserMessage,
                              TextBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock, HookMatcher)

from . import livre, regles

SKILL = pathlib.Path(__file__).resolve().parent.parent / "skills" / "reecriture.md"
PORTEES = ("annotation", "paragraphe", "plan")
MODES = ("retouche", "reecriture")
ANCRE_FIN = re.compile(r"[ \t]\^([a-z0-9]+)[ \t]*$")
_taches = set()          # les demandes en cours (garder une référence aux tâches asyncio)
_actives = set()         # les demandes dont la tâche tourne vraiment dans ce processus (voir verifie)
GRACE_S = 120            # le temps laissé à une demande partie pour compiler son contexte et joindre Claude

SCHEMA = {
    "type": "object",
    "properties": {"propositions": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "paragraphes": {"type": "array", "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "texte": {"type": "string"}},
                "required": ["id", "texte"]}},
            "note": {"type": "string"},
            "annotations_traitees": {"type": "array", "items": {"type": "string"}}},
        "required": ["paragraphes", "note", "annotations_traitees"]}}},
    "required": ["propositions"]}


class Conflit(Exception):
    pass


# ------------------------------------------------------------------ budget

# Ce qu'une demande peut dépenser : tours de modèle, recherches web, pages lues. Réglable dans
# livre.yaml (section « claude »). Au-delà, l'outil est refusé et Claude doit rendre sa
# réponse avec ce qu'il a ; « tours » garde trois tours de marge pour cette réponse.
LIMITES = {"verification": {"tours": 25, "recherches": 6, "pages": 12},
           "fiche": {"tours": 40, "recherches": 12, "pages": 25},
           "pistes": {"tours": 20, "recherches": 0, "pages": 0},
           "reference": {"tours": 14, "recherches": 3, "pages": 4},
           "naive": {"tours": 3, "recherches": 0, "pages": 0},
           "document": {"tours": 12, "recherches": 3, "pages": 5},
           "plan": {"tours": 24, "recherches": 0, "pages": 0},
           "conversation": {"tours": 30, "recherches": 4, "pages": 6},
           "redaction": {"tours": 40, "recherches": 0, "pages": 0},
           "reecriture": {"tours": 16, "recherches": 0, "pages": 0}}
# Un message du CLI peut porter un gros résultat d'outil (un PDF lu d'un bloc) : 1 Mo par défaut
# ne suffit pas. Et un PDF se lit par pages, jamais entier (voir le crochet).
TAMPON = 32 * 1024 * 1024
# Les derniers modèles ne renvoient pas le texte de leurs réflexions, sauf à le demander :
# résumé, il va au déroulé (de quoi suivre où va la demande).
PENSEE = {"type": "adaptive", "display": "summarized"}
PDF_PAGES_MAX = 6

ARRETE = (" Ne cherche plus : rends maintenant ta réponse structurée avec ce que tu as. Ce qui n'a pas "
          "pu être vérifié le reste (verdict « introuvable », ou verifie: false).")


MODELES = {"claude-opus-5-5": "Opus 5.5", "claude-sonnet-5": "Sonnet 5", "claude-haiku-4-5-20251001": "Haiku 4.5"}


def modele(genre, d=None):
    """Le modèle d'une demande : celui choisi pour elle, sinon celui du genre (claude.<genre>.modele
    dans livre.yaml), sinon celui du livre (claude.modele), sinon le défaut de Claude Code."""
    c = livre.meta().get("claude") or {}
    return (d or {}).get("modele_choisi") or (c.get(genre) or {}).get("modele") or c.get("modele") or None


def _choix_modele(corps):
    m = (corps.get("modele") or "").strip()
    if m and m not in MODELES:
        raise ValueError("modèle inconnu : %s" % m)
    return m or None


def limites(genre):
    lim = dict(LIMITES[genre])
    for k, v in ((livre.meta().get("claude") or {}).get(genre) or {}).items():
        if k in lim and isinstance(v, int):
            lim[k] = v
    return lim


def garde(d, lim):
    """Le crochet PreToolUse qui tient le budget de la demande : il compte les recherches et les
    pages, et refuse l'outil au-delà — Claude reçoit le refus et rend sa réponse."""
    b = d.setdefault("budget", {"recherches": 0, "pages": 0})
    b["limites"] = lim

    async def crochet(entree, tool_use_id, contexte):
        nom = entree.get("tool_name")
        if nom == "StructuredOutput":
            return {}
        raison = None
        entree_outil = entree.get("tool_input") or {}
        if nom == "Read" and str(entree_outil.get("file_path", "")).lower().endswith(".pdf"):
            pages = str(entree_outil.get("pages") or "")
            m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", pages)
            if not m or int(m.group(2) or m.group(1)) - int(m.group(1)) + 1 > PDF_PAGES_MAX:
                d.setdefault("_refuses", []).append(tool_use_id)
                d.setdefault("deroule", []).append({"t": time.strftime("%H:%M:%S"), "type": "limite",
                                                    "texte": "PDF lu d'un bloc : refusé (par pages, %d au plus)" % PDF_PAGES_MAX})
                return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                        "permissionDecisionReason": "Un PDF ne se lit pas d'un bloc : utilise Read avec pages (ex. « 1-3 », "
                        "%d pages au plus à la fois), en commençant par le résumé et les pages qui portent ce que tu "
                        "cherches. Si la lecture par pages échoue, cherche une version HTML (page de l'article, "
                        "PMC, arXiv) ou le résumé, plutôt que le PDF." % PDF_PAGES_MAX}}
        if len(d.get("_vus", [])) >= lim["tours"] - 3:
            raison = "Budget de tours atteint (%d)." % lim["tours"]
        elif nom == "WebSearch":
            if b["recherches"] >= lim["recherches"]:
                raison = "Budget de recherches web atteint (%d)." % lim["recherches"]
            else:
                b["recherches"] += 1
        elif nom == "WebFetch":
            if b["pages"] >= lim["pages"]:
                raison = "Budget de pages lues atteint (%d)." % lim["pages"]
            else:
                b["pages"] += 1
        if not raison:
            return {}
        b["refus"] = b.get("refus", 0) + 1
        d.setdefault("_refuses", []).append(tool_use_id)
        d.setdefault("deroule", []).append({"t": time.strftime("%H:%M:%S"), "type": "limite", "texte": raison})
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": raison + ARRETE}}
    return {"PreToolUse": [HookMatcher(matcher=None, hooks=[crochet])]}


def texte_budget(lim):
    if not lim.get("recherches") and not lim.get("pages"):
        return ""
    return ("\n## Budget\nAu plus %d recherches web (WebSearch) et %d pages lues (WebFetch) pour toute la "
            "demande. Au-delà, l'outil te sera refusé : garde de quoi conclure. Une assertion ne demande pas une "
            "revue de littérature — deux sources sérieuses qui concordent suffisent." % (lim["recherches"], lim["pages"]))


# ------------------------------------------------------------------ fichiers

def _dossier(slug):
    # « _kb » : les demandes qui n'appartiennent à aucun chapitre (la création d'une fiche)
    d = livre.LIVRE / "kb" / "demandes" if slug == "_kb" else livre.dossier(slug) / "demandes"
    d.parent.mkdir(parents=True, exist_ok=True)
    d.mkdir(exist_ok=True)
    return d


def lit(slug, ident):
    p = _dossier(slug) / (ident + ".json")
    if not p.exists():
        raise KeyError(ident)
    return json.loads(p.read_text(encoding="utf-8"))


def _ecrit(slug, d):
    from . import filiation
    filiation.inscrit(slug, d)                   # une demande née d'une autre : son origine, sa génération
    (_dossier(slug) / (d["id"] + ".json")).write_text(
        json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    from . import evenements                     # les pages ouvertes sont prévenues
    evenements.demande(slug, d)


def liste(slug):
    if slug != "_kb" and not livre.dossier(slug).is_dir():
        raise KeyError(slug)
    out = []
    for p in _dossier(slug).glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        if not d.get("titre"):
            d["_slug"] = slug
            d["titre"] = titre_de(d)
        out.append({k: d.get(k) for k in ("id", "type", "titre", "portee", "mode", "consigne", "etat", "cree",
                                          "remplacee_par", "relance_de", "modele_choisi")}
                   | {"modele": (d.get("execution") or {}).get("modele")}
                   | {"jetons": (d.get("execution") or {}).get("jetons"),
                      "cout_usd": (d.get("execution") or {}).get("cout_usd")}
                   | {"blocs": d["cible"].get("blocs") or [], "annotations": d["cible"].get("annotations") or [],
                      "assertions": d["cible"].get("assertions") or [],
                      "chapitres": d["cible"].get("chapitres") or [], "question": d["cible"].get("question"),
                      "fiche": d["cible"].get("fiche"), "cle": d["cible"].get("cle"), "version": d["cible"].get("version"),
                      "niveau": d["cible"].get("niveau"), "partie": d["cible"].get("partie"), "chapitre": d["cible"].get("chapitre"),
                      "plan": d["cible"].get("plan"), "decision": d.get("decision")})
    return sorted(out, key=lambda d: d["cree"], reverse=True)


def liste_toutes():
    """Les demandes de tous les chapitres de l'atelier, avec leur chapitre."""
    out = []
    for c in livre.chapitres():
        if not c.get("atelier"):
            continue
        for d in liste(c["slug"]):
            out.append(dict(d, chapitre=c["slug"], chapitre_titre=c["title"], chapitre_numero=c["numero"]))
    for d in liste("_kb"):
        out.append(dict(d, chapitre="_kb", chapitre_titre="Fiches", chapitre_numero=None))
    return sorted(out, key=lambda d: d["cree"], reverse=True)


def relance(slug, ident, consigne=None, modele_choisi=False):
    """Une nouvelle demande, même cible et même consigne (ou une consigne revue), sur l'état
    présent du livre : le contexte est recompilé (verrou, essai, storyboard du moment).
    L'ancienne, si elle attendait une décision, passe à « remplacée »."""
    d = lit(slug, ident)
    if d["etat"] == "en_cours":
        raise Conflit("la demande %s est encore en cours" % ident)
    from . import filiation
    if d.get("origine"):                         # la relance garde la filiation de la demande remplacée
        with filiation.depuis(d["origine"]):
            return _relance(slug, ident, d, consigne, modele_choisi)
    return _relance(slug, ident, d, consigne, modele_choisi)


def _relance(slug, ident, d, consigne, modele_choisi):
    c = d["cible"]
    consigne = d.get("consigne", "") if consigne is None else consigne
    mc = d.get("modele_choisi") if modele_choisi is False else modele_choisi
    if d.get("type") == "pistes":
        from . import pistes
        n = pistes.cree({"fiche": c["fiche"], "consigne": consigne, "modele": mc})
    elif d.get("type") == "renvois":
        from . import renvois
        n = renvois.cree({"fiche": c["fiche"], "consigne": consigne, "modele": mc})
    elif d.get("type") == "reference":
        from . import references
        n = references.cree({"cle": c["cle"], "consigne": consigne, "modele": mc})
    elif d.get("type") == "plan":
        from . import planif
        n = planif.cree(dict(c, consigne=consigne, modele=mc))
    elif d.get("type") == "document":
        from . import documents
        n = documents.cree({"cle": c["cle"], "consigne": consigne, "modele": mc})
    elif d.get("type") == "naive":
        from . import naif
        n = naif.cree(slug, {"version": c["version"], "modele": mc})
    elif d.get("type") == "fiche":
        from . import creation
        n = creation.cree({"question": c["question"], "slug": c.get("slug"), "chapitres": c.get("chapitres"),
                           "depuis": c.get("depuis"), "sources_initiales": c.get("sources_initiales"),
                           "longueur": d.get("longueur"), "consigne": consigne, "modele": mc})
    elif d.get("type") == "redaction":
        from . import redaction
        n = redaction.cree({"chapitre": c["chapitre"], "revision": d.get("mode") == "revision", "consigne": consigne,
                            "longueur": d.get("longueur"), "mots": d.get("mots"), "poser": d.get("poser"),
                            "remplacer": d.get("remplacer"), "modele": mc})
    elif d.get("type") == "verification":
        from . import verification
        n = verification.cree(slug, {"assertions": c.get("assertions"), "annotation": c.get("annotation"),
                                     "consigne": consigne, "modele": mc})
    else:
        corps = {"portee": d["portee"], "version": c.get("version", "recit"), "mode": d.get("mode", "retouche"),
                 "consigne": consigne, "nombre": d.get("nombre", 3), "consulter": d.get("consulter", True),
                 "blocs": c.get("blocs"), "plan": c.get("plan"), "modele": mc}
        if d["portee"] == "annotation":
            a = next((x for x in livre.annotations(slug) if x["id"] in (c.get("annotations") or [])), None)
            if a and a.get("etat") == "ouverte":
                corps["annotation"] = a["id"]
            else:                                 # l'annotation est résolue : on reprend le paragraphe
                corps["portee"] = "paragraphe"
        n = cree(slug, corps)
    n = lit(slug, n["id"])
    n["relance_de"] = ident
    _ecrit(slug, n)
    d["remplacee_par"] = n["id"]
    if d["etat"] in ("prete", "erreur", "en_attente"):   # relancée : l'ancienne est close (et sort de la file)
        d["etat"] = "remplacee"
    _ecrit(slug, d)
    return n


def classe(slug, ident):
    """Clore une demande en erreur sans la relancer (abandonnée)."""
    d = lit(slug, ident)
    if d["etat"] != "erreur":
        raise Conflit("seule une demande en erreur se classe (%s)" % d["etat"])
    d.update(etat="abandonnee", abandonnee=livre._maintenant())
    _ecrit(slug, d)
    return d


def _blocs(slug, version):
    """Les paragraphes d'une version, dans l'ordre : [(id, texte sans ancre)]."""
    texte = (livre.dossier(slug) / (version + ".md")).read_text(encoding="utf-8")
    out = []
    for b in re.split(r"\n[ \t]*\n", texte.strip("\n")):
        m = ANCRE_FIN.search(b.rstrip())
        if m:
            out.append((m.group(1), ANCRE_FIN.sub("", b.rstrip()).strip()))
    return out


# ------------------------------------------------------------------ déroulé

def _resume_outil(nom, entree):
    """Ce qu'un appel d'outil fait, en une ligne lisible."""
    e = entree or {}
    if nom == "WebSearch":
        return e.get("query", "")
    if nom == "WebFetch":
        return e.get("url", "")
    if nom in ("Read", "Glob", "Grep"):
        chemin = str(e.get("file_path") or e.get("path") or "")
        chemin = chemin.replace(str(livre.LIVRE) + "/", "")
        depot, _ = livre.heritage()
        if depot:
            chemin = chemin.replace(str(depot) + "/", "héritage/")
        motif = e.get("pattern", "")
        return " ".join(x for x in (motif and "« %s »" % motif, chemin) if x)
    return json.dumps(e, ensure_ascii=False)[:200]


CLES_JETONS = {"input_tokens": "entree", "output_tokens": "sortie",
               "cache_creation_input_tokens": "cache_cree", "cache_read_input_tokens": "cache_lu"}


def _cumule(total, usage):
    for k, v in (usage or {}).items():
        if k in CLES_JETONS and isinstance(v, (int, float)):
            total[CLES_JETONS[k]] = total.get(CLES_JETONS[k], 0) + int(v)


def jetons(resultat):
    """Les jetons d'une demande finie : entrée, sortie, cache créé, cache relu (et par modèle)."""
    if resultat is None:
        return None
    total = {}
    _cumule(total, getattr(resultat, "usage", None))
    par_modele = {}
    for nom, u in (getattr(resultat, "model_usage", None) or {}).items():
        u = dict(u) if not isinstance(u, dict) else u
        par_modele[nom] = {k: v for k, v in u.items() if isinstance(v, (int, float))}
    if par_modele:
        total["par_modele"] = par_modele
    return total or None


def _extrait_resultat(nom, contenu):
    """Ce qu'un outil a rendu, en quelques lignes : de quoi suivre sans tout recopier."""
    if not nom or nom == "StructuredOutput":
        return None
    if isinstance(contenu, list):
        contenu = " ".join(x.get("text", "") for x in contenu if isinstance(x, dict) and x.get("type") == "text")
    texte = " ".join(str(contenu or "").split())
    if not texte:
        return None
    if nom == "Read":                                   # un fichier lu : sa taille, pas son contenu
        return "%d caractères lus" % len(texte)
    if nom in ("Grep", "Glob"):
        return texte[:300] + ("…" if len(texte) > 300 else "")
    return texte[:700] + ("…" if len(texte) > 700 else "")


def trace(d, m):
    """Ajoute au déroulé de la demande ce que Claude vient de faire (outil, texte, réflexion).
    Rend True si quelque chose a été ajouté."""
    avant = len(d.setdefault("deroule", []))
    quand = time.strftime("%H:%M:%S")
    if isinstance(m, AssistantMessage) and m.model and d.get("modele_en_cours") != m.model:
        d["modele_en_cours"] = m.model
    sid = getattr(m, "session_id", None)
    if sid and d.get("session_id") != sid:
        d["session_id"] = sid                  # de quoi reprendre la session si elle s'arrête
    if isinstance(m, AssistantMessage) and getattr(m, "usage", None):
        # le compteur en direct : chaque réponse du modèle ajoute ses jetons
        encours = d.setdefault("jetons_en_cours", {})
        mid = getattr(m, "message_id", None)
        if mid is None or mid not in d.setdefault("_vus", []):
            _cumule(encours, m.usage)
            if mid:
                d["_vus"].append(mid)
    if isinstance(m, AssistantMessage):
        for b in m.content:
            if isinstance(b, ToolUseBlock):
                if b.name == "StructuredOutput":      # la réponse finale elle-même, pas une étape
                    continue
                detail = _resume_outil(b.name, b.input)
                d.setdefault("_outils", {})[b.id] = [b.name, detail]
                d["deroule"].append({"t": quand, "type": "outil", "nom": b.name, "detail": detail})
            elif isinstance(b, TextBlock) and b.text.strip():
                d["deroule"].append({"t": quand, "type": "texte", "texte": b.text.strip()[:2000]})
            elif isinstance(b, ThinkingBlock) and b.thinking.strip():
                d["deroule"].append({"t": quand, "type": "pensee", "texte": b.thinking.strip()[:4000]})
    elif isinstance(m, UserMessage) and isinstance(m.content, list):
        for b in m.content:
            if isinstance(b, ToolResultBlock) and b.is_error:
                if b.tool_use_id in d.get("_refuses", []):
                    continue                     # refusé par le budget : déjà au déroulé
                texte = b.content if isinstance(b.content, str) else json.dumps(b.content, ensure_ascii=False)
                nom, detail = d.get("_outils", {}).get(b.tool_use_id, [None, None])
                if nom == "WebFetch" and detail not in d.setdefault("inaccessibles", []):
                    d["inaccessibles"].append(detail)
                d["deroule"].append({"t": quand, "type": "echec", "texte": ((detail + " — ") if detail else "") + (texte or "")[:300]})
            elif isinstance(b, ToolResultBlock):
                nom, detail = d.get("_outils", {}).get(b.tool_use_id, [None, None])
                if nom == "WebFetch" and detail not in d.setdefault("pages", []):
                    d["pages"].append(detail)
                extrait = _extrait_resultat(nom, b.content)
                if extrait:
                    d["deroule"].append({"t": quand, "type": "resultat", "nom": nom, "texte": extrait})
    return len(d["deroule"]) > avant or bool(d.get("jetons_en_cours"))


def interrompues():
    """Au démarrage : une demande restée « en cours » a perdu sa tâche (serveur relancé)."""
    n = 0
    base = livre.LIVRE / "chapters"
    tous = list(base.glob("*/demandes/*.json")) if base.exists() else []
    tous += list((livre.LIVRE / "kb" / "demandes").glob("*.json"))
    for p in tous:
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("etat") == "en_cours":
            d.update(etat="erreur", erreur="interrompue : le serveur a été relancé pendant le travail — la reprendre ou la relancer")
            p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            n += 1
    return n


def tache(coro):
    """Lancer une coroutine sur la boucle du serveur — depuis la boucle (route async) comme depuis un fil
    de travail : FastAPI fait tourner les routes synchrones (def) hors de la boucle, où
    asyncio.get_running_loop() échoue ; la demande restait alors « en cours » sans que Claude parte.
    Rend une tâche (ou un Future) : .cancelled(), .exception(), add_done_callback."""
    try:
        boucle = asyncio.get_running_loop()
    except RuntimeError:
        boucle = None
    if boucle is None:
        from . import evenements
        if evenements._boucle is None:
            raise RuntimeError("pas de boucle asyncio pour lancer la tâche")
        f = asyncio.run_coroutine_threadsafe(coro, evenements._boucle)
        _taches.add(f)
        f.add_done_callback(_taches.discard)
        return f
    t = boucle.create_task(coro)
    _taches.add(t)
    t.add_done_callback(_taches.discard)
    return t


def perdue(slug, d):
    """Une demande « en cours » dont aucune tâche ne tourne : sa tâche est morte sans rien écrire
    (une exception avant l'appel à Claude, par exemple). On laisse GRACE_S à une demande qui vient de
    partir, le temps qu'elle compile son contexte."""
    if d.get("etat") != "en_cours" or d.get("id") in _actives:
        return False
    try:
        age = time.time() - (_dossier(slug) / (d["id"] + ".json")).stat().st_mtime
    except OSError:
        return False
    return age > GRACE_S


def verifie(slug=None, ident=None):
    """Confronter l'état écrit à l'état réel : une demande « en cours » perdue passe en erreur (elle se
    reprend si elle a une session, sinon elle se relance). Toutes, ou une seule. Rend les identifiants
    corrigés."""
    from . import file
    cibles = [(slug, lit(slug, ident))] if ident else [(s, x) for s, x in file._toutes() if x.get("etat") == "en_cours"]
    corrigees = []
    for s, d in cibles:
        if perdue(s, d):
            d.update(etat="erreur", erreur="perdue : la tâche ne tourne plus (aucune trace depuis %s) — la reprendre ou la relancer"
                     % time.strftime("%d/%m %H:%M", time.localtime((_dossier(s) / (d["id"] + ".json")).stat().st_mtime)))
            _ecrit(s, d)
            corrigees.append(d["id"])
    if corrigees:
        from . import serie
        try:
            serie.avance()
            file.suivante()
        except Exception as e:                   # noqa: BLE001
            print("atelier : vérification —", e)
    return corrigees


def titre_de(d):
    """Une phrase qui dit de quoi parle une demande (pour les listes)."""
    try:
        at = livre.atelier(d.get("_slug") or "")
    except KeyError:
        at = None
    if d.get("type") == "fiche":
        from . import creation
        return creation.titre_de(d)
    if d.get("type") == "pistes":
        from . import pistes
        return pistes.titre_de(d)
    if d.get("type") == "renvois":
        from . import renvois
        return renvois.titre_de(d)
    if d.get("type") == "reference":
        from . import references
        return references.titre_de(d)
    if d.get("type") == "naive":
        from . import naif
        return naif.titre_de(d)
    if d.get("type") == "document":
        return "Texte original de %s" % d["cible"].get("cle")
    if d.get("type") == "redaction":
        from . import redaction
        return "redaction", redaction.SCHEMA, redaction.conclut, None
    if d.get("type") == "plan":
        from . import planif
        return planif.titre_de(d)
    if d.get("type") == "verification":
        morceaux = []
        for a in d["cible"].get("assertions", []):
            x = (at or {}).get("assertions", {}).get(a, {}) if at else {}
            morceaux.append("%s « %s »" % (a, (x.get("texte") or "")[:60] + ("…" if len(x.get("texte") or "") > 60 else "")))
        return "Vérifier " + " ; ".join(morceaux)
    textes = d["cible"].get("textes") or {}
    debut = next(iter(textes.values()), "")
    debut = " ".join(debut.split())[:70] + ("…" if len(debut) > 70 else "")
    if d.get("portee") == "plan":
        titre = ((at or {}).get("brief", {}) if at else {})
        beat = next((b for b in titre.get("beats", []) if b["id"] == d["cible"].get("plan")), {})
        return "Réécrire le plan %s — %s" % (d["cible"].get("plan"), beat.get("title", ""))
    if d.get("portee") == "annotation":
        return "Réécrire selon l'annotation, dans « %s »" % debut
    return "Réécrire le paragraphe « %s »" % debut


# ------------------------------------------------------------------ contexte

def _regles(version):
    return regles.texte_pour_claude(version) or "(aucun garde-fou : regles/%s.md absent)" % version


def compile_contexte(slug, d):
    """La consigne système (le gabarit rempli) et le message : tout ce que Claude reçoit."""
    m = livre.meta()
    at = livre.atelier(slug)
    version = d["cible"]["version"]
    blocs = _blocs(slug, version)
    ordre = [b for b, _ in blocs]
    textes = dict(blocs)
    essai = dict(_blocs(slug, "essai")) if (livre.dossier(slug) / "essai.md").exists() else {}
    liens = at["links"].get(version, {})
    beats = {b["id"]: b for b in at["brief"].get("beats", [])}
    par_plan = {}
    for b in ordre:
        if liens.get(b, {}).get("plan"):
            par_plan.setdefault(liens[b]["plan"], []).append(b)

    systeme = SKILL.read_text(encoding="utf-8")
    systeme = re.sub(r"<!--.*?-->\n*", "", systeme, flags=re.S)
    role = ((m.get("versions") or {}).get(version) or {}).get("role", "")
    for k, v in (("titre", m.get("titre", "")), ("version", version), ("role", role),
                 ("nombre", str(d["nombre"])), ("regles", _regles(version))):
        systeme = systeme.replace("{{%s}}" % k, v)

    L = []
    br = at["brief"]
    c = next((x for x in livre.chapitres() if x["slug"] == slug), {})
    L.append("# Chapitre « %s »%s" % (c.get("title", slug),
                                      " — %s" % c["periode"] if c.get("periode") else ""))
    for titre, champs in (("Intention", br.get("intent")), ("Tenue", br.get("tenue"))):
        if champs:
            L.append("\n## %s\n" % titre + "\n".join("- %s : %s" % (k.replace("_", " "), v)
                                                    for k, v in champs.items()))
    if br.get("interdits"):
        L.append("\n## Mots interdits dans ce chapitre\n" + ", ".join(br["interdits"]))
    if br.get("constraints"):
        L.append("\n## Contraintes du storyboard\n" + "\n".join("- " + x for x in br["constraints"]))

    reservees = list(br.get("derogations") or [])
    reservees += [a["texte"] for a in at["assertions"].values() if "R14" in (a.get("note") or "")]

    cibles = d["cible"]["blocs"]
    plans = []
    for b in cibles:
        p = liens.get(b, {}).get("plan")
        if p and p not in plans:
            plans.append(p)
    for p in plans:
        bt = beats.get(p, {})
        L.append("\n## Plan %s — %s" % (p, bt.get("title", "")))
        for k in ("lieu", "temps", "ambiance", "attaque", "chute", "note"):
            if bt.get(k):
                L.append("- %s : %s" % (k, bt[k]))

    i0, i1 = ordre.index(cibles[0]), ordre.index(cibles[-1])
    if i0 > 0:
        L.append("\n## Paragraphe précédent (ne pas réécrire)\n\n" + textes[ordre[i0 - 1]])

    L.append("\n## À réécrire — %d paragraphe(s)" % len(cibles))
    for b in cibles:
        l = liens.get(b, {})
        rang = par_plan.get(l.get("plan"), []).index(b) if l.get("plan") else -1
        recits = beats.get(l.get("plan"), {}).get("recits") or []
        L.append("\n### ^%s — plan %s, paragraphe %d" % (b, l.get("plan", "?"), rang + 1))
        if 0 <= rang < len(recits):
            L.append("micro-récit : %s" % recits[rang])
        seq = beats.get(l.get("plan"), {}).get("sequence") or []
        if 0 <= rang < len(seq):
            L.append("séquence déclarée pour ce paragraphe : %s" % seq[rang])
        if l.get("ajout"):
            L.append("ajout hors verrou : aucune assertion, ni chiffre ni cause")
        for a in l.get("assertions", []):
            x = at["assertions"].get(a, {})
            L.append("assertion %s (%s) : %s" % (a, x.get("statut", "?"), x.get("texte", "?")))
            # ce que l'essai (la version sourcée) en dit, et l'écart connu : de quoi répondre à
            # une question de fond sans aller chercher dans sa mémoire
            for e in (x.get("essai") or [])[:2]:
                if e["bloc"] in essai:
                    ex = essai[e["bloc"]]
                    ex = re.sub(r"\[\^[^\]]+\]|\[@[^\]]+\]", "", ex)
                    L.append("  essai (%s) : %s" % (e["appui"], ex[:700] + (" …" if len(ex) > 700 else "")))
            if x.get("ecart"):
                L.append("  ÉCART connu (%s) : %s" % (x["ecart"]["type"], x["ecart"]["texte"]))
        L.append("\ntexte actuel :\n\n" + textes[b])

    if i1 < len(ordre) - 1:
        L.append("\n## Paragraphe suivant (ne pas réécrire)\n\n" + textes[ordre[i1 + 1]])

    annots = [a for a in livre.annotations(slug) if a["id"] in d["cible"]["annotations"]]
    if annots:
        L.append("\n## Annotations de l'auteur à traiter")
        titres = {e["id"]: e["titre"] for e in regles.lit(version)["elements"] if e["type"] == "regle"}
        for a in annots:
            L.append("- [%s] (%s, ^%s)%s : %s" % (
                a["id"], a["type"], a["bloc"],
                " sur « %s »" % a["citation"] if a.get("citation") else " sur tout le paragraphe",
                a.get("texte") or "(sans commentaire)"))
            for r in a.get("regles") or []:
                L.append("  règle invoquée : %s — %s" % (r, titres.get(r, "(règle inconnue)")))
    present = " ".join(textes[b] for b in cibles)
    reservees = [r for r in reservees if r.strip(" «»\"") and r.strip(" «»\"")[:25] in present]
    if reservees:
        L.append("\n## Formules réservées présentes : ne pas les reformuler\n"
                 + "\n".join("- " + r for r in reservees))
    if d.get("consulter"):
        depot, h = livre.heritage()
        L.append("\n## Consulter le livre (lecture seule)\n\nTu peux lire et chercher dans les "
                 "fichiers du livre (dossier courant) : chapters/%s/ (recit.md, essai.md, verrou.yaml, "
                 "bibliographie.yaml, annotations.jsonl), les autres chapitres, regles/, les fiches "
                 "scientifiques kb/fiches/.%s Consulte-les "
                 "quand une annotation pose une question de fond ou qu'un raccord l'exige ; cite le "
                 "fichier dans ta note. Tu ne modifies rien." % (
                     slug, " La bibliographie du livre est dans kb/sources/ (une œuvre par fichier)."
                     if (livre.LIVRE / "kb" / "sources").is_dir() else
                     " Le dépôt d'origine (%s) contient la bibliographie centrale (%s)." % (
                         depot, h.get("bibliographie", "")) if depot else ""))
    L.append("\n## Demande\n\nmode : %s\n%s" % (d["mode"], d.get("consigne") or
             "(pas de consigne : répondre aux annotations, et sinon améliorer selon les règles)"))
    from . import refs                          # les références collées dans la consigne ou les annotations
    L.append(refs.annexe(d.get("consigne"), *[a.get("texte") for a in livre.annotations(slug)
                                              if a["id"] in (d["cible"].get("annotations") or [])]))
    return systeme, "\n".join(L)


# ------------------------------------------------------------------ cycle de vie

def cree(slug, corps):
    portee = corps.get("portee")
    version = corps.get("version", "recit")
    mode = corps.get("mode", "retouche")
    if portee not in PORTEES or mode not in MODES:
        raise ValueError("portée ou mode inconnu")
    if version != "recit":
        raise ValueError("seul le récit se réécrit pour l'instant")
    at = livre.atelier(slug)
    ordre = [b for b, _ in _blocs(slug, version)]
    annots = [a for a in livre.annotations(slug) if a["version"] == version]
    if portee == "annotation":
        a = next((x for x in annots if x["id"] == corps.get("annotation")), None)
        if not a:
            raise ValueError("annotation inconnue")
        blocs, a_traiter = [a["bloc"]], [a["id"]]
    elif portee == "paragraphe":
        blocs = [b for b in corps.get("blocs", []) if b in ordre]
        if not blocs:
            raise ValueError("paragraphe inconnu")
        a_traiter = [x["id"] for x in annots if x["bloc"] in blocs and x["etat"] == "ouverte"]
    else:
        plan = corps.get("plan")
        blocs = [b for b in ordre if at["links"]["recit"].get(b, {}).get("plan") == plan]
        if not blocs:
            raise ValueError("plan inconnu")
        a_traiter = [x["id"] for x in annots if x["bloc"] in blocs and x["etat"] == "ouverte"]
    textes = dict(_blocs(slug, version))
    d = {"id": "d-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "reecriture", "portee": portee, "mode": mode,
         "consigne": (corps.get("consigne") or "").strip(),
         "nombre": max(1, min(4, int(corps.get("nombre", 3)))),
         "consulter": bool(corps.get("consulter")),
         "modele_choisi": _choix_modele(corps),
         "cible": {"version": version, "blocs": blocs, "annotations": a_traiter,
                   "plan": corps.get("plan"), "textes": {b: textes[b] for b in blocs}},
         "etat": "en_cours", "cree": livre._maintenant()}
    systeme, message = compile_contexte(slug, d)
    d["contexte"] = {"systeme": systeme, "message": message}
    d["_slug"] = slug
    d["titre"] = titre_de(d)
    d.pop("_slug")
    _ecrit(slug, d)
    from . import file
    return file.part(slug, d, "reecriture", "_execute", slug, d["id"])


async def _execute(slug, ident):
    d = lit(slug, ident)
    # sans outils, Claude ne voit que le contexte compilé ; « consulter » lui ouvre le livre
    # en lecture seule (et le dépôt d'héritage), au prix de quelques tours de plus
    lecture = ["Read", "Grep", "Glob"] if d.get("consulter") else []
    lim = limites("reecriture")
    if not lecture:
        lim["tours"] = 3
    depot, _ = livre.heritage()
    options = ClaudeAgentOptions(
        max_buffer_size=TAMPON, thinking=PENSEE,
        tools=lecture, allowed_tools=lecture, max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), add_dirs=[str(depot)] if (lecture and depot) else [],
        system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": SCHEMA},
        hooks=garde(d, lim) if lecture else None, model=modele("reecriture", d))
    await _lance(slug, d, options, d["contexte"]["message"], _conclut)


def _conclut(d, sortie):
    props = []
    attendus = d["cible"]["blocs"]
    for i, p in enumerate((sortie or {}).get("propositions", []), 1):
        # seuls comptent les paragraphes visés, non vides (Claude en ajoute parfois un vide)
        par = {}
        for x in p["paragraphes"]:
            b, texte = x["id"].strip().lstrip("^"), " ".join(x["texte"].split())
            if b in attendus and texte:
                par[b] = texte
        props.append({"id": "p%d" % i, "paragraphes": par, "note": p.get("note", ""),
                      "annotations_traitees": [a for a in p.get("annotations_traitees", [])
                                               if a in d["cible"]["annotations"]],
                      "complete": set(par) == set(attendus)})
    if not props:
        raise ValueError("aucune proposition rendue")
    d.update(etat="prete", propositions=props)


def _additionne(a, b):
    """Deux comptes de jetons (une demande et sa reprise) mis bout à bout."""
    if not a or not b:
        return a or b
    out = {k: a.get(k, 0) + b.get(k, 0) for k in set(a) | set(b) if k != "par_modele"}
    pm = {}
    for src in (a.get("par_modele") or {}, b.get("par_modele") or {}):
        for nom, u in src.items():
            cible = pm.setdefault(nom, {})
            for k, v in u.items():
                cible[k] = cible.get(k, 0) + v
    if pm:
        out["par_modele"] = pm
    return out


async def _lance(slug, d, options, prompt, conclut, reprise=False, apres=None):
    """Fait tourner Claude sur une demande : le déroulé s'écrit au fil de l'eau ; la réponse
    structurée passe par conclut(d, sortie) ; l'échec garde la session, pour la reprendre."""
    t0 = time.time()
    _actives.add(d["id"])
    modele, resultat = None, None
    b0 = {k: (d.get("budget") or {}).get(k, 0) for k in ("recherches", "pages", "refus")}   # ce que cette exécution consomme
    try:
        async for m in query(prompt=prompt, options=options):
            if isinstance(m, AssistantMessage):
                modele = m.model
            elif isinstance(m, ResultMessage):
                resultat = m
            if trace(d, m):
                _ecrit(slug, d)                  # le déroulé se lit pendant le travail
        sortie = getattr(resultat, "structured_output", None)
        if not sortie and resultat and resultat.result:
            sortie = json.loads(resultat.result)
        if not sortie:
            raise ValueError("aucune réponse structurée")
        conclut(d, sortie)
        d.pop("erreur", None)
    except Exception as e:                     # noqa: BLE001 — l'erreur est rendue à l'auteur
        d.update(etat="erreur", erreur="%s: %s" % (type(e).__name__, e))
    ex = {"duree_s": round(time.time() - t0, 1), "modele": modele,
          "cout_usd": getattr(resultat, "total_cost_usd", None),
          "tours": getattr(resultat, "num_turns", None), "jetons": jetons(resultat)}
    from . import consommation
    b = d.get("budget") or {}
    consommation.note("demande", d.get("type") or "reecriture", d["id"], chapitre=slug,
                      phase="reprise" if prompt == REPRISE else "encore" if reprise else "initiale",
                      debut=consommation.debut_iso(t0), duree_s=ex["duree_s"], modele=modele,
                      modele_choisi=getattr(options, "model", None), issue="erreur" if d.get("etat") == "erreur" else "ok",
                      erreur=d.get("erreur"), tours=ex["tours"], jetons=ex["jetons"], cout_usd=ex["cout_usd"],
                      web={k: max(0, (b.get(k) or 0) - b0[k]) for k in b0}, session=d.get("session_id"))
    avant = d.get("execution") if reprise else None
    if avant:
        ex = {"duree_s": round((avant.get("duree_s") or 0) + ex["duree_s"], 1),
              "modele": ex["modele"] or avant.get("modele"),
              "cout_usd": (avant.get("cout_usd") or 0) + (ex["cout_usd"] or 0) or None,
              "tours": (avant.get("tours") or 0) + (ex["tours"] or 0) or None,
              "jetons": _additionne(avant.get("jetons"), ex["jetons"]),
              "reprises": avant.get("reprises", 0) + 1}
    d["execution"] = ex
    for k in ("_vus", "_outils", "_refuses"):
        d.pop(k, None)
    if apres:
        apres(slug, d)
    _ecrit(slug, d)
    _actives.discard(d["id"])
    from . import serie                          # les séries avancent à la fin de chaque demande
    try:
        serie.avance()
    except Exception as e:                       # noqa: BLE001 — une série ne doit pas casser la demande finie
        print("atelier : série —", e)
    if True:                                     # la file : la suivante (d'une série, ou si l'enchaînement est activé)
        from . import file
        try:
            file.suivante()
        except Exception as e:                   # noqa: BLE001 — la file ne doit pas casser la demande finie
            print("atelier : file d'attente —", e)


REPRISE = ("Tu t'es arrêté avant d'avoir rendu ta réponse. Ne fais plus aucune recherche ni lecture : "
           "rends maintenant ta réponse structurée, avec ce que tu as déjà trouvé dans cette session. "
           "Ce que tu n'as pas pu vérifier le reste : dis-le (verdict « introuvable », ou verifie: false).")


def reprise(slug, ident):
    """Reprendre une demande arrêtée (tours épuisés, serveur relancé…) dans sa session : Claude
    y retrouve tout ce qu'il a lu, et rend sa réponse sans nouvelle recherche."""
    d = lit(slug, ident)
    if d["etat"] != "erreur":
        raise Conflit("seule une demande en erreur se reprend")
    if not d.get("session_id"):
        raise ValueError("pas de session enregistrée pour cette demande : la relancer")
    d.update(etat="en_cours", lancee=livre._maintenant())
    d["erreur_avant_reprise"] = d.pop("erreur", None)
    d.setdefault("deroule", []).append({"t": time.strftime("%H:%M:%S"), "type": "reprise",
                                        "texte": "reprise de la session — réponse demandée, sans nouvelle recherche"})
    _ecrit(slug, d)
    t = tache(_reprend(slug, ident))
    return d


def _genre(d):
    """(nom du budget, schéma, conclusion, après) selon le type de la demande."""
    if d.get("type") == "verification":
        from . import verification
        return "verification", verification.SCHEMA, verification.conclut, verification.au_carnet
    if d.get("type") == "fiche":
        from . import creation
        return "fiche", creation.SCHEMA, creation.conclut, None
    if d.get("type") == "pistes":
        from . import pistes
        return "pistes", pistes.SCHEMA, pistes.conclut, None
    if d.get("type") == "renvois":
        from . import renvois
        return "pistes", renvois.SCHEMA, renvois.conclut, None
    if d.get("type") == "reference":
        from . import references
        return "reference", references.SCHEMA, references.conclut, None
    if d.get("type") == "naive":
        from . import naif
        return "naive", naif.SCHEMA, naif.conclut, None
    if d.get("type") == "document":
        from . import documents
        return "document", documents.SCHEMA, documents.conclut, None
    if d.get("type") == "plan":
        from . import planif
        return "plan", planif.schema(d["cible"]["niveau"]), planif.conclut, None
    return "reecriture", SCHEMA, _conclut, None


async def _reprend(slug, ident):
    d = lit(slug, ident)
    _, schema, conclut, apres = _genre(d)
    depot, _ = livre.heritage()
    options = ClaudeAgentOptions(
        max_buffer_size=TAMPON, thinking=PENSEE,
        tools=[], allowed_tools=[], max_turns=4, setting_sources=[],
        cwd=str(livre.LIVRE), add_dirs=[str(depot)] if depot else [],
        system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": schema},
        resume=d["session_id"], model=_modele_de(d))
    await _lance(slug, d, options, REPRISE, conclut, reprise=True, apres=apres)


def _modele_de(d):
    """Une session se poursuit avec le modèle qui l'a commencée."""
    return (d.get("execution") or {}).get("modele") or d.get("modele_en_cours") or \
        modele(_genre(d)[0], d)


ENCORE = ("Poursuis ta recherche là où tu en es : tout ce que tu as cherché, lu et conclu plus haut dans cette "
          "session reste valable. Tu disposes de %d recherches web et %d pages lues de plus. Ne relis pas ce qui "
          "est déjà lu ; va à ce qui manque encore, ou à ce qui reste douteux dans ta réponse précédente.%s "
          "Puis rends ta réponse structurée complète, mise à jour — elle remplace la précédente.")


def encore(slug, ident, consigne=""):
    """Chercher encore : rouvrir la session d'une vérification (arrêtée, ou dont la réponse ne suffit
    pas) avec un budget neuf. Claude garde tout ce qu'il a lu ; la nouvelle réponse remplace l'ancienne."""
    d = lit(slug, ident)
    if d.get("type") not in ("verification", "fiche", "reference"):
        raise ValueError("« poursuivre la recherche » ne vaut que pour une vérification ou une fiche")
    if d["etat"] not in ("erreur", "prete"):
        raise Conflit("seule une vérification en erreur ou à décider peut chercher encore")
    if not d.get("session_id"):
        raise ValueError("pas de session enregistrée pour cette demande : la relancer")
    b = d.setdefault("budget", {"recherches": 0, "pages": 0})
    av = b.setdefault("avant", {"recherches": 0, "pages": 0, "refus": 0})
    for k in ("recherches", "pages", "refus"):
        av[k] = av.get(k, 0) + (b.pop(k, 0) or 0)
    b.update(recherches=0, pages=0)
    b["encore"] = b.get("encore", 0) + 1
    if d.get("resultat"):                       # la réponse d'avant reste lisible, pour comparer
        d.setdefault("resultats_precedents", []).append({"date": livre._maintenant(), "resultat": d["resultat"]})
    d.pop("apercu", None)
    consigne = " ".join((consigne or "").split())
    d["etat"] = "en_cours"
    if d.get("erreur"):
        d["erreur_avant_reprise"] = d.pop("erreur")
    d.setdefault("deroule", []).append({"t": time.strftime("%H:%M:%S"), "type": "reprise",
                                        "texte": "chercher encore — budget neuf" + (" : " + consigne if consigne else "")})
    _ecrit(slug, d)
    from . import file
    return file.part(slug, d, "reecriture", "_encore", slug, ident, consigne)


async def _encore(slug, ident, consigne):
    d = lit(slug, ident)
    genre, schema, conclut, apres = _genre(d)
    lim = limites(genre)
    depot, _ = livre.heritage()
    outils = ["Read", "Grep", "Glob", "WebSearch", "WebFetch"]
    options = ClaudeAgentOptions(
        max_buffer_size=TAMPON, thinking=PENSEE,
        tools=outils, allowed_tools=outils, max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), add_dirs=[str(depot)] if depot else [],
        system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": schema},
        hooks=garde(d, lim), resume=d["session_id"], model=_modele_de(d))
    prompt = ENCORE % (lim["recherches"], lim["pages"], (" Précision de l'auteur : " + consigne) if consigne else "")
    await _lance(slug, d, options, prompt, conclut, reprise=True, apres=apres)


def _reecrit(slug, version, nouveaux):
    """Remplace le texte de paragraphes dans <version>.md ; tout le reste est intact."""
    p = livre.dossier(slug) / (version + ".md")
    morceaux = re.split(r"\n[ \t]*\n", p.read_text(encoding="utf-8").strip("\n"))
    faits = set()
    for i, b in enumerate(morceaux):
        m = ANCRE_FIN.search(b.rstrip())
        if m and m.group(1) in nouveaux:
            texte = textwrap.fill(" ".join(nouveaux[m.group(1)].split()), width=100,
                                  break_long_words=False, break_on_hyphens=False)
            morceaux[i] = texte + " ^" + m.group(1)
            faits.add(m.group(1))
    if faits != set(nouveaux):
        raise Conflit("paragraphe(s) introuvable(s) : " + ", ".join(sorted(set(nouveaux) - faits)))
    p.write_text("\n\n".join(morceaux) + "\n", encoding="utf-8")


def decide(slug, ident, corps):
    d = lit(slug, ident)
    if d["etat"] != "prete":
        raise Conflit("demande %s : rien à décider (%s)" % (ident, d["etat"]))
    choix = corps.get("proposition")
    motif = (corps.get("motif") or "").strip()
    quand = livre._maintenant()
    if choix:
        prop = next((p for p in d["propositions"] if p["id"] == choix), None)
        if not prop:
            raise KeyError(choix)
        version = d["cible"]["version"]
        actuels = dict(_blocs(slug, version))
        for b, avant in d["cible"]["textes"].items():
            if " ".join(actuels.get(b, "").split()) != " ".join(avant.split()):
                raise Conflit("le paragraphe ^%s a changé depuis la demande" % b)
        nouveaux = {b: t for b, t in prop["paragraphes"].items() if b in d["cible"]["blocs"]}
        _reecrit(slug, version, nouveaux)
        with (livre.dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
            for b, t in nouveaux.items():
                f.write(json.dumps({"date": quand, "type": "texte", "version": version, "bloc": b,
                                    "avant": d["cible"]["textes"][b], "apres": t,
                                    "source": ident, "proposition": choix, "motif": motif},
                                   ensure_ascii=False) + "\n")
        for a in prop["annotations_traitees"]:
            livre._ajoute(slug, {"id": a, "etat": "resolue", "resolue_par": ident, "modifie": quand})
    d["decision"] = {"proposition": choix, "motif": motif, "date": quand}
    d["etat"] = "decidee"
    _ecrit(slug, d)
    return d
