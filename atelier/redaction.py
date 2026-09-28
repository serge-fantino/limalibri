# -*- coding: utf-8 -*-
"""Écrire l'essai d'un chapitre à partir de son brief : Claude rédige, l'auteur pose.

Une demande de type « redaction » vit dans kb/demandes/<id>.json (préfixe e-), avec son chapitre.
Claude travaille uniquement à partir de ce que le livre sait déjà :
  · le brief du chapitre (synopsis, question, fiches) et, s'il est amorcé, son squelette (les
    sections « à écrire ») et son verrou (les assertions à établir) ;
  · les fiches du chapitre (kb/fiches/), qu'il lit, et les autres fiches au besoin ;
  · les chapitres déjà écrits (le précédent surtout, pour la continuité) ;
  · le plan du livre (l'idée, la partie, les chapitres voisins) et les garde-fous de l'essai.
Pas de web : ce que les fiches n'établissent pas, il ne l'écrit pas. Il le rend en « manques » —
une fiche à créer, une fiche à creuser —, que l'auteur lance d'un clic.

Poser écrit chapters/<slug>/essai.md (un ^id par paragraphe, un {#id} par intertitre), remplace le
squelette s'il y en avait un, et passe le chapitre en brouillon. Un essai déjà rédigé n'est jamais
remplacé sans le dire (remplacer: true).

La série : une demande par chapitre, dans l'ordre du plan, chacune partant quand la précédente a
fini (sans dépendre de l'enchaînement automatique de la file) ; « poser d'office » écrit chaque
chapitre dès sa réponse, pour que le suivant puisse le lire.
"""
import re
import json
import time
import secrets

import yaml
from claude_agent_sdk import ClaudeAgentOptions

from . import livre, reecriture, avancement

SLUG_KB = "_kb"
LONGUEURS = {"courte": "1 500 à 2 500 mots", "moyenne": "3 000 à 4 500 mots", "longue": "5 000 à 7 000 mots"}

SCHEMA = {
    "type": "object",
    "properties": {
        "texte": {"type": "string"},
        "manques": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["fiche", "creuser"]},
            "question": {"type": "string"}, "pourquoi": {"type": "string"},
            "fiche": {"type": "string"}, "section": {"type": "string"}},
            "required": ["type", "question"]}},
        "fiches_lues": {"type": "array", "items": {"type": "string"}},
        "remarques": {"type": "string"}},
    # le moins de champs obligatoires possible : une réponse refusée pour un détail oblige Claude à
    # réécrire tout le chapitre (dix minutes)
    "required": ["texte"]}

SYSTEME = """Tu écris l'essai d'un chapitre du livre « {titre} » : la version qui explique — le pourquoi et
le comment, avec ses sources et ses notes. Tu écris en français, pour un lecteur curieux sans
formation particulière.

## Ta matière, et seulement elle
- Les fiches de la base (kb/fiches/<slug>.md) : lis TOUTES les fiches du chapitre avant d'écrire,
  puis d'autres si le chapitre en a besoin (Grep dans kb/fiches/). Elles sont ta source première.
- Les chapitres déjà écrits du livre (chapters/<slug>/essai.md) : le précédent surtout, pour
  enchaîner sans répéter, et pour le ton.
- Le brief du chapitre ; son squelette et son verrou s'il y en a (voir le message).
Tu n'as pas le web. Un fait que ni les fiches ni les chapitres écrits n'établissent, tu ne l'écris
pas : tu le signales dans « manques » (une fiche à créer, avec la question qu'elle devrait
traiter ; ou une fiche existante à creuser). Mieux vaut une section plus courte qu'un fait inventé.

## La forme
- Pas de titre de chapitre (il est dans la structure). Des sections « ## Titre », sous-sections
  « ### » si besoin ; si un squelette est donné, suis ses sections, dans l'ordre (tu peux les
  retitrer).
- Des paragraphes pleins, séparés par une ligne vide.
- Les sources : [@cle], seulement des clés que tu as lues dans les fiches (ou dans kb/sources/).
  N'invente jamais une clé.
- Les notes : [^{slug}-mot] dans le texte, définies à la fin sous « ## Notes » ([^{slug}-mot]: …).
- Un renvoi à un autre chapitre : [chap:<slug>] (la liste des chapitres est dans le message), jamais
  « chapitre 3 » en dur — le numéro est calculé à l'assemblage.
- Une section « Ce qu'on ne sait pas » (ce qui reste incertain, avec son degré) et une section
  finale « Ce que ce chapitre démontre », comme les chapitres déjà écrits, si le chapitre s'y prête.
- Longueur visée : {longueur}.

## Les garde-fous de l'essai
{regles}

## Ta réponse
- texte : le chapitre entier, en Markdown, notes comprises.
- manques : ce qu'il faudrait savoir de plus (trois à six au plus, les plus utiles) — type « fiche »
  (question à traiter) ou « creuser » (fiche existante, et ce qu'il lui manque).
- fiches_lues : les slugs des fiches que tu as lues.
- remarques : ce que l'auteur doit savoir (un choix de plan, une tension entre deux fiches, une
  section faible)."""


# ------------------------------------------------------------------ créer, lancer

def _chapitre(slug):
    c = next((x for x in livre.chapitres() if x["slug"] == slug), None)
    if not c:
        raise KeyError(slug)
    return c


def cree(corps, lancer=True):
    slug = (corps.get("chapitre") or "").strip()
    c = _chapitre(slug)
    niv = avancement.niveau(c, "essai")
    if niv in ("brouillon", "relu", "valide") and not corps.get("remplacer"):
        raise ValueError("l'essai de « %s » est déjà rédigé (%s) : le réécrire depuis ses paragraphes, "
                         "ou demander explicitement de le remplacer" % (c["title"], niv))
    if niv == "vide":
        raise ValueError("« %s » n'a ni synopsis ni brief : il n'y a rien à développer" % c["title"])
    ouverte = next((x for x in reecriture.liste(SLUG_KB) if x.get("type") == "redaction" and x.get("chapitre") == slug
                    and x.get("etat") in ("en_cours", "en_attente", "prete")), None)
    if ouverte:
        raise reecriture.Conflit("une rédaction de « %s » est déjà %s : %s" % (
            c["title"], {"en_cours": "en cours", "en_attente": "en attente", "prete": "à décider"}[ouverte["etat"]], ouverte["id"]))
    d = {"id": "e-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "redaction", "portee": "chapitre", "mode": "ecriture",
         "consigne": (corps.get("consigne") or "").strip(),
         "longueur": corps.get("longueur") if corps.get("longueur") in LONGUEURS else "moyenne",
         "modele_choisi": reecriture._choix_modele(corps),
         "poser": bool(corps.get("poser")), "remplacer": bool(corps.get("remplacer")),
         "serie": corps.get("serie"),
         "cible": {"chapitre": slug, "version": "essai", "niveau": niv},
         "etat": "en_attente", "cree": livre._maintenant(), "rang": time.time() + corps.get("_rang", 0) * 1e-3}
    d["titre"] = "Écrire l'essai — %s%s" % ("%s. " % c["numero"] if c.get("numero") else "", c["title"])
    reecriture._ecrit(SLUG_KB, d)
    return demarre(d["id"]) if lancer else d


def serie(corps):
    """Une demande par chapitre à écrire (synopsis ou brief, pas de texte), dans l'ordre du plan ;
    la première part, les suivantes attendent leur tour."""
    choisis = set(corps.get("chapitres") or [])
    pid = corps.get("partie")
    ouverts = {x.get("chapitre") for x in reecriture.liste(SLUG_KB)
               if x.get("type") == "redaction" and x.get("etat") in ("en_cours", "en_attente", "prete")}
    cs = [c for c in livre.chapitres() if (not pid or c.get("partie") == pid) and (not choisis or c["slug"] in choisis)
          and c["slug"] not in ouverts and avancement.niveau(c, "essai") in ("synopsis", "brief")]
    if not cs:
        raise ValueError("aucun chapitre à écrire (il faut un synopsis ou un brief, et pas encore de texte)")
    sid = "serie-" + time.strftime("%Y%m%d-%H%M%S")
    ds = [cree(dict(corps, chapitre=c["slug"], serie=sid, _rang=i), lancer=False) for i, c in enumerate(cs)]
    demarre(ds[0]["id"])
    return {"serie": sid, "demandes": [x["id"] for x in ds], "chapitres": [c["slug"] for c in cs]}


def suivante_de_serie():
    """Une série avance d'elle-même : si aucune de ses demandes ne tourne, la suivante part."""
    d = livre.LIVRE / "kb" / "demandes"
    if not d.exists():
        return None
    ds = [json.loads(p.read_text(encoding="utf-8")) for p in d.glob("e-*.json")]
    for s in sorted({x["serie"] for x in ds if x.get("serie")}):
        membres = sorted((x for x in ds if x.get("serie") == s), key=lambda x: x.get("rang", 0))
        if any(x["etat"] == "en_cours" for x in membres):
            continue
        attente = [x for x in membres if x["etat"] == "en_attente"]
        if attente:
            return demarre(attente[0]["id"])
    return None


def demarre(ident):
    d = reecriture.lit(SLUG_KB, ident)
    d.update(etat="en_cours", lancee=livre._maintenant(),
             budget={"recherches": 0, "pages": 0, "limites": reecriture.limites("redaction")})
    systeme, message = compile_contexte(d)
    d["contexte"] = {"systeme": systeme, "message": message}
    reecriture._ecrit(SLUG_KB, d)
    import asyncio
    t = asyncio.get_running_loop().create_task(_execute(ident))
    reecriture._taches.add(t)
    t.add_done_callback(reecriture._taches.discard)
    return d


def _yaml(p):
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}


def compile_contexte(d):
    from . import plan, refs
    slug = d["cible"]["chapitre"]
    m = livre.meta()
    P = plan.lit()
    systeme = SYSTEME.format(titre=m.get("titre", ""), slug=slug, longueur=LONGUEURS[d["longueur"]],
                             regles=reecriture._regles("essai"))
    ordre = [c for p in P["parties"] for c in p["chapitres"]]
    i = next(k for k, c in enumerate(ordre) if c["slug"] == slug)
    c = ordre[i]
    p = next(p for p in P["parties"] if any(x["slug"] == slug for x in p["chapitres"]))
    L = ["# Le livre : %s" % m.get("titre", "")]
    for k, lib in (("idee", "Idée"), ("arc", "Arc")):
        if P["livre"].get(k):
            L.append("%s : %s" % (lib, P["livre"][k]))
    L += ["", "# La partie : %s" % p["title"]]
    for k in ("sens", "arc", "question"):
        if p.get(k):
            L.append("%s : %s" % (k, p[k]))
    L += ["", "# Le chapitre à écrire : %d. %s%s" % (i + 1, c["title"], " (%s)" % c["periode"] if c.get("periode") else ""),
          "Synopsis : %s" % (c.get("synopsis") or "(aucun)"), "Question : %s" % (c.get("question") or "(aucune)"),
          "Ses fiches — à lire toutes : %s" % (", ".join("kb/fiches/%s.md" % f for f in c.get("fiches") or []) or
                                              "aucune : trouve-les dans kb/fiches/ (Grep), et dis-le dans les remarques")]
    br = _yaml(livre.dossier(slug) / "brief.yaml")
    if br.get("boucle"):
        L.append("Boucle : %s" % br["boucle"])
    pe = livre.dossier(slug) / "essai.md"
    if pe.exists() and avancement.squelette(pe.read_text(encoding="utf-8")):
        L += ["", "## Son squelette (les sections prévues, chacune avec ce qu'elle doit établir) — à suivre",
              re.sub(r"[ \t]\^[a-z0-9]+[ \t]*$", "", pe.read_text(encoding="utf-8"), flags=re.M).strip()]
    elif pe.exists() and d.get("remplacer"):
        L += ["", "## L'essai actuel (à remplacer) : chapters/%s/essai.md — lis-le avant d'écrire" % slug]
    V = [a for s in _yaml(livre.dossier(slug) / "verrou.yaml").get("sections") or [] for a in s.get("assertions") or []
         if a.get("statut") != "retiree"]
    if V:
        L += ["", "## Son verrou : ce que le chapitre doit établir"] + ["- %s %s%s" % (
            a["id"], a["texte"], " (%s)" % a["note"] if a.get("note") else "") for a in V]
    L += ["", "# Les chapitres voisins"]
    for j in (i - 2, i - 1, i + 1):
        if 0 <= j < len(ordre):
            v = ordre[j]
            ecrit = avancement.niveau(v, "essai") in ("brouillon", "relu", "valide")
            L.append("- %d. %s — %s%s" % (j + 1, v["title"], (v.get("synopsis") or "")[:300],
                                          " [écrit : chapters/%s/essai.md%s]" % (v["slug"], " — lis-le" if j == i - 1 else "")
                                          if ecrit else " [pas encore écrit]"))
    L += ["", "# Tous les chapitres (pour les renvois [chap:<slug>])"] + ["- %s — %s" % (v["slug"], v["title"]) for v in ordre]
    ecrits = [v["slug"] for v in ordre if v["slug"] != slug and avancement.niveau(v, "essai") in ("brouillon", "relu", "valide")]
    if ecrits:
        L.append("Tous les chapitres déjà écrits (chapters/<slug>/essai.md) : %s" % ", ".join(ecrits))
    if d.get("consigne"):
        L += ["", "# La consigne de l'auteur", d["consigne"]]
    return systeme, "\n".join(L) + refs.annexe(d.get("consigne"))


async def _execute(ident):
    d = reecriture.lit(SLUG_KB, ident)
    outils = ["Read", "Grep", "Glob"]
    lim = d["budget"]["limites"]
    depot, _ = livre.heritage()
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON, thinking=reecriture.PENSEE,
        tools=outils, allowed_tools=outils, max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), add_dirs=[str(depot)] if depot else [], system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": SCHEMA},
        hooks=reecriture.garde(d, lim), model=reecriture.modele("redaction", d))
    await reecriture._lance(SLUG_KB, d, options, d["contexte"]["message"], conclut)


# ------------------------------------------------------------------ la réponse

def _normalise(texte, slug):
    t = texte.replace("\r\n", "\n").strip()
    # les clés de notes portent le slug du chapitre (invariant du livre) : on les préfixe s'il le faut
    t = re.sub(r"\[\^(?!%s-)([^\]]+)\]" % re.escape(slug), lambda m: "[^%s-%s]" % (slug, m.group(1)), t)
    t = re.sub(r"\A#\s+[^\n]*\n+", "", t)                         # pas de titre de chapitre
    t = re.sub(r"[ \t]\^[a-z0-9]+[ \t]*$", "", t, flags=re.M)      # les ancres, c'est nous qui les posons
    return t.strip() + "\n"


def conclut(d, sortie):
    from . import sources
    t = _normalise(sortie.get("texte") or "", d["cible"]["chapitre"])
    if len(t.split()) < 150:
        raise ValueError("texte trop court (%d mots)" % len(t.split()))
    connues = set(sources.toutes()) if sources.existe() else set(livre.sources())
    cles = sorted(set(livre.CITATION.findall(t)))
    appels = set(re.findall(r"\[\^([^\]]+)\](?!:)", t))
    defs = set(re.findall(r"^\[\^([^\]]+)\]:", t, re.M))
    R = {"texte": t, "mots": len(re.sub(r"\[\^[^\]]+\]|\[@[\w-]+\]", "", t).split()),
         "sections": re.findall(r"^##\s+(.+)$", t, re.M),
         "citations": cles, "citations_inconnues": [k for k in cles if connues and k not in connues],
         "notes_orphelines": sorted((appels - defs) | (defs - appels)),
         "manques": [m for m in sortie.get("manques") or [] if m.get("question")],
         "fiches_lues": sortie.get("fiches_lues") or [], "remarques": sortie.get("remarques") or "",
         "html": livre.rendu(t, {})}
    d.update(etat="prete", resultat=R)
    if d.get("poser"):
        try:
            pose(d["cible"]["chapitre"], t, remplacer=d.get("remplacer"), demande=d["id"])
            d.update(etat="decidee", decision={"proposition": "posee", "d_office": True, "date": livre._maintenant()})
        except Exception as e:                    # noqa: BLE001 — la proposition reste à décider
            d["erreur_pose"] = "%s" % e


# ------------------------------------------------------------------ poser

def _ancre(slug, texte):
    """Un ^id à la fin de chaque paragraphe (pas les intertitres, les notes, les tableaux)."""
    pris = set()
    for v in livre.VERSIONS:
        p = livre.dossier(slug) / (v + ".md")
        if p.exists() and v != "essai":
            pris |= set(re.findall(r"\^([a-z0-9]+)\s*$", p.read_text(encoding="utf-8"), re.M))
    out = []
    for b in re.split(r"\n[ \t]*\n", texte.strip("\n")):
        tete = b.lstrip()
        if tete.startswith(("#", "[^", "|", "```", "<!--")) or re.fullmatch(r"-{3,}|\*{3,}", tete.strip()):
            out.append(b)
            continue
        while True:
            i = secrets.token_hex(2)
            if i not in pris and not i.isdigit() and not re.fullmatch(r"\d+e\d+", i):
                break
        pris.add(i)
        out.append(b.rstrip() + " ^" + i)
    return "\n\n".join(out) + "\n"


def pose(slug, texte, remplacer=False, demande=None):
    from . import essai, plan
    c = _chapitre(slug)
    d = livre.dossier(slug)
    d.mkdir(parents=True, exist_ok=True)
    pe = d / "essai.md"
    ancien = pe.read_text(encoding="utf-8") if pe.exists() else ""
    if ancien.strip() and not avancement.squelette(ancien) and not remplacer:
        raise reecriture.Conflit("l'essai a été rédigé entre-temps : rien n'est remplacé")
    pe.write_text(_ancre(slug, texte), encoding="utf-8")
    n = essai.pose_identifiants(slug)
    y, doc = plan._lit_structure()
    _, _, x = plan._chapitre(doc, slug)
    vs = list(x.get("versions") or [])
    if "essai" not in vs:
        x["versions"] = vs + ["essai"]
    if (x.get("status") or "outline") == "outline":
        x["status"] = "draft"
    plan._ecrit_structure(y, doc)
    e = {"type": "essai_redige", "chapitre": slug, "demande": demande, "mots": len(texte.split()),
         "remplace": "squelette" if ancien.strip() and avancement.squelette(ancien) else ("texte" if ancien.strip() else None)}
    plan.journal(e)
    with (d / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(e, date=livre._maintenant()), ensure_ascii=False) + "\n")
    return {"chapitre": slug, "titre": c["title"], "intertitres": n}


def decide(ident, corps):
    d = reecriture.lit(SLUG_KB, ident)
    if d["etat"] != "prete":
        raise reecriture.Conflit("la demande n'attend pas de décision (%s)" % d["etat"])
    if corps.get("action") == "rejeter":
        d.update(etat="decidee", decision={"proposition": None, "motif": corps.get("motif", ""), "date": livre._maintenant()})
    else:
        r = pose(d["cible"]["chapitre"], d["resultat"]["texte"], remplacer=d.get("remplacer") or corps.get("remplacer"), demande=ident)
        d.update(etat="decidee", decision={"proposition": "posee", "date": livre._maintenant(), **r})
    reecriture._ecrit(SLUG_KB, d)
    return d
