# -*- coding: utf-8 -*-
"""Le storyboard d'un chapitre du récit, depuis son essai : Claude propose les plans ; l'auteur les retient.

Une demande « storyboard » (kb/demandes/b-*.json ; capacité « storyboard »). Claude reçoit les règles du
récit (la voix, le registre), la partie du chapitre (son sens, son arc), le chapitre (synopsis, question),
son essai — la version qui explique, déjà révisée —, son verrou (les assertions, obligatoires ou non), le
storyboard du chapitre précédent (pour enchaîner) et le synopsis du suivant. Il lit ce qu'il veut dans le
livre (Read, Grep). Pas de web. Fable par défaut : c'est un travail d'écriture.

Il rend l'intention du chapitre pour le récit, sa tenue (le ton propre au chapitre), et ses plans — chacun :
id (A, B…), titre, lieu, temps, ambiance, attaque, chute, assertions (les identifiants du verrou qu'il met
en scène), séquence (l'ordre où il les dit), micro-récits (un par paragraphe à venir), ajouts (le nombre
de paragraphes hors verrou permis). C'est le lien avec l'essai : la rigueur passe par les assertions — le
contrôle vérifie que chaque assertion obligatoire est portée par un plan, et que les identifiants existent.

Retenir (ou poser d'office, depuis un plan d'objectif) écrit brief.yaml : beats, intent, tenue — le reste du
brief (synopsis, question, fiches) est gardé ; l'ancien storyboard est archivé dans historique/.
"""
import re
import json
import time
import secrets

from claude_agent_sdk import ClaudeAgentOptions

from . import livre, reecriture

SLUG_KB = "_kb"
DEFAUT = "claude-fable-5-1"

SYSTEME = """Tu es le metteur en scène du récit du livre « {titre} ». Le livre a deux versions alignées chapitre
pour chapitre : l'essai, qui explique, et le récit, qui raconte. Tu prépares le STORYBOARD d'un chapitre du
récit : pas son texte, ses plans — ce que chaque plan montre, où, quand, sur quel ton, comment il s'ouvre et
se ferme, ce qu'il établit, et ses micro-récits (une phrase par paragraphe à venir, qui dit ce que le
paragraphe fera voir).

La rigueur vient de l'essai : chaque plan met en scène des assertions du verrou du chapitre (leurs
identifiants), et toutes les assertions obligatoires doivent être portées par un plan. Le récit ne dit
rien que l'essai n'établisse ; il le fait voir, autrement. Les règles du récit, ci-dessous, priment pour la
forme : la voix, le registre, ce qui est interdit.

Lis l'essai du chapitre (chapters/<slug>/essai.md) en entier ; le storyboard du chapitre précédent est
dans le message, pour enchaîner (une attaque qui reprend sa chute, un motif qui revient). Tu peux lire les
fiches (kb/fiches/) et les autres storyboards (chapters/*/brief.yaml). Pas de web.

Rends :
- intention : ce que le chapitre raconte, pour le récit, en deux ou trois phrases ;
- tenue : le ton propre à ce chapitre, dans la voix du livre ;
- plans : de 3 à 8, chacun avec id (A, B, C…), title, lieu, temps, ambiance, attaque, chute, assertions
  (identifiants du verrou), sequence (l'ordre où le plan dit ses assertions ; « ajout : … » pour un
  paragraphe hors verrou), recits (un micro-récit par paragraphe, dans l'ordre), ajouts (nombre de
  paragraphes hors verrou permis, 0 à 2) ;
- remarques : ce que tu as laissé de côté, les assertions difficiles à faire voir, les choix de forme.
Tout en français.

## Les règles du récit
{regles}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "intention": {"type": "string"}, "tenue": {"type": "string"},
        "plans": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "title": {"type": "string"}, "lieu": {"type": "string"}, "temps": {"type": "string"},
            "ambiance": {"type": "string"}, "attaque": {"type": "string"}, "chute": {"type": "string"},
            "assertions": {"type": "array", "items": {"type": "string"}},
            "sequence": {"type": "array", "items": {"type": "string"}},
            "recits": {"type": "array", "items": {"type": "string"}},
            "ajouts": {"type": "integer"}},
            "required": ["id", "title", "recits"]}},
        "remarques": {"type": "string"}},
    "required": ["plans"]}


def _yaml(p):
    import yaml
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}


def _verrou(slug):
    return [a for s in _yaml(livre.dossier(slug) / "verrou.yaml").get("sections") or [] for a in s.get("assertions") or []
            if a.get("statut") != "retiree"]


def cree(corps):
    slug = (corps.get("chapitre") or "").strip()
    c = next((x for x in livre.chapitres() if x["slug"] == slug), None)
    if not c:
        raise ValueError("chapitre inconnu : %s" % slug)
    if not (livre.dossier(slug) / "essai.md").exists():
        raise ValueError("le chapitre n'a pas d'essai : le storyboard part de l'essai")
    choisi = reecriture._choix_modele(corps)
    d = {"id": "b-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "storyboard", "portee": "storyboard", "mode": "ecriture",
         "consigne": (corps.get("consigne") or "").strip(),
         "modele_choisi": choisi or (None if reecriture.modele("storyboard") else DEFAUT),
         "poser": bool(corps.get("poser")),
         "cible": {"chapitre": slug, "version": "recit"},
         "etat": "en_attente", "cree": livre._maintenant(), "rang": time.time()}
    d["titre"] = "Storyboard — %s%s" % ("%s. " % c["numero"] if c.get("numero") else "", c["title"])
    reecriture._ecrit(SLUG_KB, d)
    from . import file
    return file.part(SLUG_KB, d, "storyboard", "demarre", d["id"])


def compile_contexte(d):
    from . import plan, regles
    slug = d["cible"]["chapitre"]
    systeme = SYSTEME.format(titre=livre.meta().get("titre", ""), regles=regles.texte_pour_claude("recit") or "(aucune)")
    P = plan.lit()
    ordre = [(p, c) for p in P["parties"] for c in p["chapitres"]]
    i = next(k for k, (_, c) in enumerate(ordre) if c["slug"] == slug)
    p, c = ordre[i]
    intention = livre.intention_version("recit")
    L = (["# Le récit, selon l'auteur (son intention : elle donne le ton et l'arc de chaque chapitre)", intention, ""]
         if intention else []) + [
         "# Le chapitre : %s — %s" % (slug, c["title"]), "Synopsis : %s" % (c.get("synopsis") or "(aucun)"),
         "Question : %s" % (c.get("question") or "(aucune)"), "Son essai : chapters/%s/essai.md (à lire en entier)" % slug,
         "", "# Sa partie : %s" % p["title"]] + ["%s : %s" % (k, p[k]) for k in ("sens", "arc", "question") if p.get(k)]
    V = _verrou(slug)
    L += ["", "# Son verrou : les assertions (obligatoires : à porter toutes)"]
    L += ["- %s [%s] %s" % (a["id"], a.get("statut", "?"), " ".join((a.get("texte") or "").split())) for a in V] or ["(pas de verrou : appuie-toi sur l'essai)"]
    if i > 0:
        pc = ordre[i - 1][1]
        bp = _yaml(livre.dossier(pc["slug"]) / "brief.yaml")
        L += ["", "# Le chapitre précédent : %s — %s" % (pc["slug"], pc["title"])]
        if bp.get("beats"):
            L += ["Son storyboard (pour enchaîner) :"] + ["- %s %s — attaque : %s · chute : %s" % (
                b.get("id"), b.get("title"), b.get("attaque") or "—", b.get("chute") or "—")
                for b in bp["beats"] if not livre.en_tete(b)]
        else:
            L.append("Pas encore de storyboard. Synopsis : %s" % (pc.get("synopsis") or "—"))
    if i + 1 < len(ordre):
        nc = ordre[i + 1][1]
        L += ["", "# Le chapitre suivant : %s — %s · synopsis : %s" % (nc["slug"], nc["title"], nc.get("synopsis") or "—")]
    tete = [b for b in _yaml(livre.dossier(slug) / "brief.yaml").get("beats") or [] if livre.en_tete(b)]
    from . import capacites_livre
    a_part = [c for c in capacites_livre.toutes().values() if c["plan"]["id"] not in {str(b.get("id")) for b in tete}]
    if a_part:
        L += ["", "# Réservé : %s — un texte à part, écrit par sa propre demande après le récit. Ne crée aucun plan "
              "pour lui (identifiant réservé : %s) ; ton premier plan ouvre le récit." % (
                  ", ".join("« %s »" % c["plan"]["titre"] for c in a_part), ", ".join(c["plan"]["id"] for c in a_part))]
    if tete:
        L += ["", "# À part : le chapitre s'ouvre sur %s (un texte à part, en tête, dans une autre voix, qui ne porte "
              "pas d'assertion). Il n'est pas de ton ressort : ne le planifie pas, il reste tel quel ; ton premier plan "
              "le suit." % ", ".join("« %s »" % (b.get("title") or b.get("id")) for b in tete)]
    if d.get("consigne"):
        L += ["", "# La consigne de l'auteur", d["consigne"]]
    from . import refs
    L.append(refs.annexe(d.get("consigne")))
    return systeme, "\n".join(L)


def demarre(ident):
    d = reecriture.lit(SLUG_KB, ident)
    d.update(etat="en_cours", lancee=livre._maintenant(),
             budget={"recherches": 0, "pages": 0, "limites": reecriture.limites("storyboard")})
    systeme, message = compile_contexte(d)
    d["contexte"] = {"systeme": systeme, "message": message}
    reecriture._ecrit(SLUG_KB, d)
    return reecriture.tache(_execute(ident))


async def _execute(ident):
    d = reecriture.lit(SLUG_KB, ident)
    outils = ["Read", "Grep", "Glob"]
    lim = d["budget"]["limites"]
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON, thinking=reecriture.PENSEE,
        tools=outils, allowed_tools=outils, max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": SCHEMA},
        hooks=reecriture.garde(d, lim), model=reecriture.modele("storyboard", d))
    await reecriture._lance(SLUG_KB, d, options, d["contexte"]["message"], conclut)


def controle(slug, plans):
    """Les assertions : inconnues (pas dans le verrou), obligatoires non portées."""
    V = {a["id"]: a for a in _verrou(slug)}
    portees = {str(x) for p in plans for x in p.get("assertions") or []}
    return {"inconnues": sorted(x for x in portees if V and x not in V),
            "non_portees": [x for x, a in V.items() if a.get("statut") == "obligatoire" and x not in portees],
            "verrou": len(V)}


def conclut(d, sortie):
    plans = []
    for k, p in enumerate(sortie.get("plans") or []):
        q = {kk: p[kk] for kk in ("id", "title", "lieu", "temps", "ambiance", "attaque", "chute") if p.get(kk)}
        q["id"] = str(p.get("id") or chr(65 + k))
        for kk in ("assertions", "sequence", "recits"):
            if p.get(kk):
                q[kk] = [" ".join(str(x).split()) for x in p[kk]]
        if p.get("ajouts") is not None:
            q["ajouts"] = int(p["ajouts"])
        plans.append(q)
    R = {"intention": sortie.get("intention") or "", "tenue": sortie.get("tenue") or "", "plans": plans,
         "remarques": sortie.get("remarques") or "", "controle": controle(d["cible"]["chapitre"], plans)}
    d.update(etat="prete", resultat=R)
    if d.get("poser"):
        try:
            pose(d["cible"]["chapitre"], R, d["id"])
            d.update(etat="decidee", decision={"proposition": "posee", "d_office": True, "date": livre._maintenant()})
        except Exception as e:                          # noqa: BLE001 — la proposition reste à décider
            d["erreur_pose"] = "%s" % e


def pose(slug, R, demande):
    """Écrit le storyboard dans brief.yaml (beats, intent, tenue), le reste du brief gardé ; l'ancien archivé."""
    p = livre.dossier(slug) / "brief.yaml"
    y = livre.yaml_rt()
    doc = y.load(p.read_text(encoding="utf-8")) if p.exists() else None
    if doc is None:
        from ruamel.yaml.comments import CommentedMap
        doc = CommentedMap()
    if doc.get("beats"):
        h = livre.dossier(slug) / "historique"
        h.mkdir(exist_ok=True)
        (h / ("storyboard-%s.json" % time.strftime("%Y%m%d-%H%M%S"))).write_text(
            json.dumps({"beats": json.loads(json.dumps(doc["beats"], default=str)), "intent": doc.get("intent"),
                        "tenue": doc.get("tenue")}, ensure_ascii=False, indent=1), encoding="utf-8")
    # les plans d'en-tête (l'ouverture, une capacité du livre) ne sont pas du ressort du storyboard : ils restent, en tête
    # — ni un plan qui en porte l'identifiant sans en être un (écrit par Claude d'après la règle) : écarté
    from . import capacites_livre
    tete = [b for b in doc.get("beats") or [] if livre.en_tete(b)]
    ids = {str(b.get("id")) for b in tete} | {c["plan"]["id"] for c in capacites_livre.toutes().values()}
    doc["beats"] = tete + [x for x in R["plans"] if str(x.get("id")) not in ids]
    # intent et tenue sont des dictionnaires dans le brief (« faire_comprendre », « point_focal »…) : la vue et la
    # réécriture les lisent clé par clé — un texte s'y range sous une clé
    if R.get("intention"):
        doc["intent"] = {"faire_comprendre": R["intention"]}
    if R.get("tenue"):
        doc["tenue"] = {"ton": R["tenue"]}
    p.write_text(livre.rt_texte(y, doc), encoding="utf-8")
    e = {"type": "storyboard_pose", "chapitre": slug, "demande": demande, "plans": len(R["plans"]),
         "recits": sum(len(x.get("recits") or []) for x in R["plans"])}
    with (livre.dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(e, date=livre._maintenant()), ensure_ascii=False) + "\n")
    from . import plan
    plan.journal(e)
    return e


def decide(ident, corps):
    """{action: retenir | rejeter, motif?}."""
    d = reecriture.lit(SLUG_KB, ident)
    if d["etat"] != "prete":
        raise reecriture.Conflit("le storyboard n'attend pas de décision (%s)" % d["etat"])
    if corps.get("action") == "rejeter":
        d.update(etat="decidee", decision={"proposition": None, "motif": (corps.get("motif") or "").strip(), "date": livre._maintenant()})
    else:
        e = pose(d["cible"]["chapitre"], d["resultat"], ident)
        d.update(etat="decidee", decision={"proposition": "posee", "date": livre._maintenant(), **e})
    reecriture._ecrit(SLUG_KB, d)
    return d
