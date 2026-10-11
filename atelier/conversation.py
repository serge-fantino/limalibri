# -*- coding: utf-8 -*-
"""Parler avec Claude du livre : une conversation qui lit tout (textes, cadres, fiches, bibliographie,
garde-fous, le web avec mesure) et répond — sans rien écrire. Quand une réponse appelle du travail,
Claude le propose sous forme d'actions (une fiche, une vérification, une réécriture, une lecture
naïve, un plan, creuser une fiche) ; l'auteur les lance d'un clic, elles deviennent des demandes
ordinaires.

Une conversation vit dans kb/conversations/<id>.json : ses tours (question, où l'auteur était,
déroulé, réponse, actions, jetons) et la session de Claude, reprise d'un tour à l'autre — Claude
garde ce qu'il a déjà lu.
"""
import json
import time
import asyncio
import secrets

from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

from . import livre, reecriture, refs

TYPES_ACTION = ("fiche", "verification", "reecriture", "revision", "naive", "plan", "pistes")

SCHEMA = {
    "type": "object",
    "properties": {
        "reponse": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "string", "enum": list(TYPES_ACTION)},
            "titre": {"type": "string"}, "pourquoi": {"type": "string"},
            "chapitre": {"type": "string"}, "consigne": {"type": "string"},
            "question": {"type": "string"}, "slug": {"type": "string"},
            "chapitres": {"type": "array", "items": {"type": "string"}},
            "assertions": {"type": "array", "items": {"type": "string"}},
            "blocs": {"type": "array", "items": {"type": "string"}},
            "portee": {"type": "string", "enum": ["paragraphe", "plan", "annotation"]},
            "plan": {"type": "string"}, "annotation": {"type": "string"},
            "version": {"type": "string", "enum": ["recit", "essai"]},
            "niveau": {"type": "string", "enum": ["livre", "partie", "chapitre"]},
            "partie": {"type": "string"}, "fiche": {"type": "string"}, "mots": {"type": "integer"}},
            "required": ["type", "titre", "pourquoi"]}}},
    "required": ["reponse", "actions"]}

SYSTEME = """Tu es l'interlocuteur de l'auteur du livre « {titre} », dans son atelier. Il te pose des
questions sur le livre — ce qu'il dit, où, avec quelles sources, ce qui manque, ce qui se contredit —
ou te demande de l'aide pour décider du travail à faire. Tu réponds en français.

## Le livre (répertoire courant, en lecture seule)
- `livre.yaml` : titre, synopsis, réglages. `structure.yaml` : l'ordre des chapitres et des parties.
  `synopsis.yaml` (s'il existe) : le plan hiérarchique, parties et chapitres, avec leurs fiches.
- `chapters/<slug>/` : `essai.md` (la version démonstrative, avec notes `[^cle]`), `recit.md` (la
  version narrative), chaque paragraphe finit par son ancre ` ^id` ; `brief.yaml` (synopsis, question,
  fiches, plans du storyboard) ; `verrou.yaml` (les assertions du chapitre, identifiants stables) ;
  `links.yaml` (paragraphe -> plan et assertions) ; `annotations.jsonl` (les remarques de l'auteur) ;
  `bibliographie.yaml` ; `validations.json` (le harnais) ; `journal.jsonl`.
- `kb/fiches/<slug>.md` : la base de connaissance scientifique — la source première. Liens `[[slug]]`.
- `kb/sources/<cle>.yaml` : la bibliographie (une œuvre par fichier : référence, statut, citations) ;
  `kb/documents/<cle>/` : les textes originaux rangés (`*.texte.txt`).
- `regles/<version>.md` : les garde-fous de chaque version.
{heritage}
## Comment travailler
- Cherche dans le livre d'abord (Grep, Glob, Read) ; le web (WebSearch, WebFetch) seulement pour ce que
  le livre ne dit pas, avec mesure, et en le disant.
- Ne lis que ce qu'il faut : Grep pour trouver, Read ciblé ensuite. Le budget est compté.
- Tu n'écris ni ne modifies aucun fichier. Tu réponds, et tu proposes. Une exception : quand l'auteur te
  le demande, tu peux ANNOTER des paragraphes avec l'outil « annoter » (mcp__atelier__annoter : chapitre,
  version, ancre du paragraphe, extrait exact, constat) — une annotation ne touche pas au texte ; la
  révision du chapitre la lira. Jamais sans qu'il l'ait demandé.
- Sois exact : un fait non vérifié est dit non vérifié. Distingue ce que le livre dit, ce que les fiches
  établissent, et ce que tu en penses.

## Ta réponse (le champ `reponse`)
En Markdown sobre : paragraphes courts, listes quand elles aident. Désigne chaque morceau du livre dont
tu parles par sa référence, que l'auteur pourra suivre d'un clic :
  @fiche/<slug>  @fiche/<slug>#<section>  @oeuvre/<cle>  @partie/<id>  @regle/<version>/<Rn>
  @chapitre/<slug>  @chapitre/<slug>/essai#<section>  @chapitre/<slug>/essai^<bloc>  @chapitre/<slug>/recit^<bloc>
  @chapitre/<slug>/plan/<id>  @chapitre/<slug>/assertion/<id>  @chapitre/<slug>/note/<cle>  @chapitre/<slug>/annotation/<id>
N'invente jamais une référence : seulement des identifiants que tu as lus.

## Les actions (le champ `actions`)
Quand la réponse appelle un travail, propose-le — l'auteur décide et lance. Rien s'il n'y a rien à faire ;
trois au plus d'ordinaire, six au plus quand on te demande de regrouper (des manques, des pistes) : alors
une action couvre plusieurs points, une fiche existante se « creuse » plutôt qu'on n'en crée une voisine,
et ce que le texte peut dire comme une incertitude n'appelle aucune fiche. Chaque action : `type`, `titre` (court), `pourquoi` (une phrase), et ses paramètres :
- `fiche` — créer une fiche : `question` (la question qu'elle doit traiter), `slug` proposé, `chapitres`
  concernés, `consigne`.
- `pistes` — creuser une fiche existante (ce qui lui manque, les fiches à créer) : `fiche`, `consigne`.
- `verification` — vérifier des assertions d'un chapitre sur les sources : `chapitre`, `assertions`
  (identifiants du verrou) ou `annotation`, `consigne`.
- `reecriture` — réécrire des paragraphes du récit : `chapitre`, `portee` (paragraphe, plan, annotation),
  `blocs` ou `plan` ou `annotation`, `consigne` (ce qu'il faut changer, précisément).
- `revision` — réviser l'essai d'un chapitre déjà écrit, en entier : couper, resserrer, recentrer, retirer ce qui
  sort du périmètre : `chapitre`, `consigne` (précise : ce qu'il faut couper, garder, déplacer, avec des
  références @chapitre/<slug>/essai^<bloc> si besoin), `mots` (la longueur visée, facultatif). Claude relit et
  retravaille ; l'auteur relit avant de poser ; la version d'avant est archivée (historique du chapitre).
- `naive` — une lecture naïve d'un chapitre (un lecteur sans contexte relève où il doit deviner) :
  `chapitre`, `version`.
- `plan` — une proposition de plan : `niveau` (livre, partie, chapitre), `partie` ou `chapitre`, `consigne`.
Une consigne peut porter des références (@…) : la demande lira la partie visée.
{actions_ok}"""


def _dossier():
    p = livre.LIVRE / "kb" / "conversations"
    p.mkdir(parents=True, exist_ok=True)
    return p


def lit(ident):
    p = _dossier() / (ident + ".json")
    if not p.exists():
        raise KeyError(ident)
    return json.loads(p.read_text(encoding="utf-8"))


def _ecrit(c):
    c["modifie"] = livre._maintenant()
    (_dossier() / (c["id"] + ".json")).write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    from . import evenements
    evenements.change("c:" + c["id"], c.get("etat"), "conversation", "conversation", id=c["id"])


def liste():
    L = []
    for p in _dossier().glob("*.json"):
        c = json.loads(p.read_text(encoding="utf-8"))
        L.append({"id": c["id"], "titre": c.get("titre"), "cree": c.get("cree"), "modifie": c.get("modifie"),
                  "tours": len(c.get("tours") or []), "etat": c.get("etat")})
    return sorted(L, key=lambda x: x.get("modifie") or "", reverse=True)


def supprime(ident):
    c = lit(ident)
    if c.get("etat") == "en_cours":
        raise reecriture.Conflit("Claude est en train de répondre")
    (_dossier() / (ident + ".json")).unlink()


def interrompues():
    """Au démarrage : un tour resté « en cours » a perdu sa tâche."""
    d = livre.LIVRE / "kb" / "conversations"
    for p in d.glob("*.json") if d.exists() else []:
        c = json.loads(p.read_text(encoding="utf-8"))
        if c.get("etat") == "en_cours":
            c["etat"] = "pret"
            if c.get("tours"):
                c["tours"][-1].update(etat="erreur", erreur="interrompu : le serveur a été relancé — reposer la question")
            p.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")


def _systeme():
    m = livre.meta()
    depot, _ = livre.heritage()
    her = ("- L'ancien dépôt du livre (héritage, lecture seule) : `%s` — les versions d'origine, les notes de "
           "recherche. À consulter si le livre renvoie au-delà de lui-même.\n" % depot) if depot else ""
    return SYSTEME.format(titre=m.get("titre", ""), heritage=her, actions_ok="")


def _carte():
    """Le livre en bref, au premier tour : chapitres et fiches, pour que Claude sache où chercher."""
    from . import kb
    L = ["# Le livre en bref", "", "## Les chapitres (numéro, slug, titre, partie)"]
    for c in livre.chapitres():
        L.append("- %s %s — %s%s%s" % (c.get("numero") or "·", c["slug"], c["title"],
                                       " (partie : %s)" % c["partie_titre"] if c.get("partie_titre") else "",
                                       "" if c.get("atelier") else " [pas encore dans l'atelier]"))
    try:
        F = kb.index()
        L += ["", "## Les fiches (%d) : slug — titre" % len(F)]
        L += ["- %s — %s" % (f["slug"], f["titre"]) for f in F]
    except Exception:                                  # noqa: BLE001 — pas de base : pas de fiches
        pass
    return "\n".join(L)


def _message(c, t):
    L = []
    if len(c["tours"]) == 1 or not c.get("session_id"):
        L += [_carte(), ""]
    if t.get("ici"):
        L.append("L'auteur regarde en ce moment : %s" % t["ici"])
    L += ["", "## La question de l'auteur", t["question"]]
    a = refs.annexe(t["question"], t.get("ici"))
    return "\n".join(L) + a


def cree(corps):
    c = {"id": "c-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "titre": None, "cree": livre._maintenant(), "etat": "pret", "tours": [],
         "modele_choisi": reecriture._choix_modele(corps)}
    _ecrit(c)
    if (corps.get("question") or "").strip():
        return demande(c["id"], corps)
    return c


def demande(ident, corps):
    """Un tour : la question part, Claude répond en tâche de fond ; la page interroge l'état."""
    c = lit(ident)
    if c.get("etat") == "en_cours":
        raise reecriture.Conflit("Claude est en train de répondre")
    q = (corps.get("question") or "").strip()
    if not q:
        raise ValueError("une question")
    if corps.get("modele") is not None and not c.get("session_id"):
        c["modele_choisi"] = reecriture._choix_modele(corps)
    t = {"question": q, "ici": (corps.get("ici") or "").strip() or None, "date": livre._maintenant(),
         "etat": "en_cours", "deroule": []}
    c["tours"].append(t)
    c["titre"] = c.get("titre") or " ".join(q.split())[:80]
    c["etat"] = "en_cours"
    _ecrit(c)
    tache = reecriture.tache(_execute(ident))
    return c


async def _execute(ident):
    c = lit(ident)
    t = c["tours"][-1]
    lim = reecriture.limites("conversation")
    outils = ["Read", "Grep", "Glob", "WebSearch", "WebFetch"]
    depot, _ = livre.heritage()
    modele = c.get("modele_session") or reecriture.modele("conversation", {"modele_choisi": c.get("modele_choisi")})
    from . import outils_livre
    srv = outils_livre.serveur(ident, None, None, auteur="assistant")
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON, thinking=reecriture.PENSEE,
        tools=outils, allowed_tools=outils + outils_livre.OUTILS, mcp_servers={outils_livre.NOM: srv},
        max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), add_dirs=[str(depot)] if depot else [],
        system_prompt=_systeme(), output_format={"type": "json_schema", "schema": SCHEMA},
        hooks=reecriture.garde(t, lim), model=modele, resume=c.get("session_id"))
    t0, resultat = time.time(), None
    try:
        async for m in query(prompt=_message(c, t), options=options):
            if isinstance(m, ResultMessage):
                resultat = m
            if reecriture.trace(t, m):
                if t.get("session_id"):
                    c["session_id"] = t["session_id"]
                _ecrit(c)
        sortie = getattr(resultat, "structured_output", None)
        if not sortie and resultat and resultat.result:
            sortie = json.loads(resultat.result)
        if not sortie:
            raise ValueError("aucune réponse structurée")
        t.update(etat="fini", reponse=sortie.get("reponse", ""),
                 actions=[a for a in sortie.get("actions") or [] if a.get("type") in TYPES_ACTION][:6])
    except Exception as e:                         # noqa: BLE001 — l'erreur est rendue à l'auteur
        t.update(etat="erreur", erreur="%s: %s" % (type(e).__name__, e))
    modele_vu = t.get("modele_en_cours")
    t["execution"] = {"duree_s": round(time.time() - t0, 1), "modele": modele_vu,
                      "cout_usd": getattr(resultat, "total_cost_usd", None),
                      "tours": getattr(resultat, "num_turns", None), "jetons": reecriture.jetons(resultat)}
    from . import consommation
    b = t.get("budget") or {}
    consommation.note("conversation", "conversation", ident, phase="tour", tour=len(c["tours"]),
                      debut=consommation.debut_iso(t0), duree_s=t["execution"]["duree_s"], modele=modele_vu,
                      modele_choisi=modele, issue="erreur" if t.get("etat") == "erreur" else "ok", erreur=t.get("erreur"),
                      tours=t["execution"]["tours"], jetons=t["execution"]["jetons"], cout_usd=t["execution"]["cout_usd"],
                      web={k: b.get(k, 0) for k in ("recherches", "pages", "refus")}, session=t.get("session_id") or c.get("session_id"))
    for k in ("_vus", "_outils", "_refuses", "session_id"):
        t.pop(k, None)
    if modele_vu and not c.get("modele_session"):
        c["modele_session"] = modele_vu            # une session se poursuit avec son modèle
    c["etat"] = "pret"
    _ecrit(c)


# ------------------------------------------------------------------ les actions : des demandes ordinaires

def lance(ident, n, i, corps):
    """Lancer l'action i du tour n (paramètres éventuellement revus par l'auteur) : la demande
    correspondante est créée ; l'action garde son identifiant."""
    c = lit(ident)
    try:
        a = c["tours"][n]["actions"][i]
    except (IndexError, KeyError, TypeError):
        raise ValueError("action inconnue")
    if a.get("lancee"):
        raise reecriture.Conflit("action déjà lancée : %s" % a["lancee"]["id"])
    p = dict(a)
    p.update({k: v for k, v in (corps or {}).items() if k != "type"})
    from . import filiation
    with filiation.depuis(ident):
        return _lance_action(ident, n, i, a, p)


def _lance_action(ident, n, i, a, p):
    ty = a["type"]
    base = {"consigne": p.get("consigne") or "", "modele": p.get("modele")}
    if ty == "fiche":
        from . import creation
        d, slug = creation.cree(dict(base, question=p.get("question") or a["titre"], slug=p.get("slug"),
                                     chapitres=p.get("chapitres") or [])), "_kb"
    elif ty == "pistes":
        from . import pistes
        d, slug = pistes.cree(dict(base, fiche=p.get("fiche"))), "_kb"
    elif ty == "revision":
        from . import redaction
        if not p.get("chapitre"):
            raise ValueError("l'action ne dit pas son chapitre")
        d, slug = redaction.cree(dict(base, chapitre=p["chapitre"], revision=True, mots=p.get("mots"))), "_kb"
    elif ty == "plan":
        from . import planif
        d, slug = planif.cree(dict(base, niveau=p.get("niveau"), partie=p.get("partie"), chapitre=p.get("chapitre"))), "_kb"
    else:
        slug = p.get("chapitre")
        if not slug:
            raise ValueError("l'action ne dit pas son chapitre")
        if ty == "verification":
            from . import verification
            d = verification.cree(slug, dict(base, assertions=p.get("assertions") or [], annotation=p.get("annotation")))
        elif ty == "naive":
            from . import naif
            d = naif.cree(slug, {"version": p.get("version") or "recit", "modele": p.get("modele")})
        else:
            d = reecriture.cree(slug, dict(base, portee=p.get("portee") or "paragraphe", blocs=p.get("blocs") or [],
                                           plan=p.get("plan"), annotation=p.get("annotation"), mode="reecriture"))
    c = lit(ident)                                  # relu : un tour a pu s'écrire entre-temps
    c["tours"][n]["actions"][i]["lancee"] = {"id": d["id"], "slug": slug, "date": livre._maintenant()}
    _ecrit(c)
    return {"demande": d, "slug": slug}
