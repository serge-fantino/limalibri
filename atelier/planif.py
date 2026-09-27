# -*- coding: utf-8 -*-
"""Les propositions de Claude pour le plan et le synopsis, niveau par niveau.

Une demande de type « plan » vit dans kb/demandes/<id>.json, avec son niveau :
  livre      proposer (ou reprendre) la structure : l'idée, l'arc, les parties et leurs
             chapitres, chacun avec un synopsis bref et ses fiches — depuis la base de
             connaissance (fiches, clusters) et le synopsis du livre
  partie     développer une partie : son sens, son arc, sa question, et ses chapitres
  chapitre   développer un chapitre : son synopsis, sa question, ses fiches (lues), le
             déroulé de son essai (les sections) et les assertions qu'il doit établir

Claude lit la base (Read, Grep, Glob sur kb/), sans web. Rien n'est écrit sans l'auteur : il
retient la proposition élément par élément (une partie, un chapitre, un champ). Pour un chapitre,
« amorcer l'essai » écrit en plus le squelette de l'essai (une section par étape du déroulé) et
un premier verrou (les assertions, chacune avec sa fiche) : de quoi commencer la rédaction.
"""
import re
import time
import secrets

from claude_agent_sdk import ClaudeAgentOptions

from . import livre, kb, reecriture, plan, creation

SLUG_KB = "_kb"

CHAP = {"type": "object", "properties": {
    "slug": {"type": "string"}, "titre": {"type": "string"}, "periode": {"type": "string"},
    "synopsis": {"type": "string"}, "question": {"type": "string"},
    "fiches": {"type": "array", "items": {"type": "string"}}},
    "required": ["titre", "synopsis"]}
SCHEMA = {
    "type": "object",
    "properties": {
        "livre": {"type": "object", "properties": {"idee": {"type": "string"}, "developpe": {"type": "string"},
                                                    "arc": {"type": "string"}}},
        "parties": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "titre": {"type": "string"}, "sens": {"type": "string"},
            "arc": {"type": "string"}, "question": {"type": "string"},
            "chapitres": {"type": "array", "items": CHAP}},
            "required": ["titre", "sens", "chapitres"]}},
        "chapitre": {"type": "object", "properties": {
            "synopsis": {"type": "string"}, "question": {"type": "string"},
            "fiches": {"type": "array", "items": {"type": "object", "properties": {
                "fiche": {"type": "string"}, "raison": {"type": "string"}}, "required": ["fiche", "raison"]}},
            "deroule": {"type": "array", "items": {"type": "object", "properties": {
                "titre": {"type": "string"}, "contenu": {"type": "string"}}, "required": ["titre", "contenu"]}},
            "assertions": {"type": "array", "items": {"type": "object", "properties": {
                "texte": {"type": "string"}, "fiche": {"type": "string"}}, "required": ["texte"]}}}},
        "manques": {"type": "array", "items": {"type": "string"}},
        "remarques": {"type": "string"}},
    "required": ["remarques"]}

def schema(niveau):
    """Le schéma d'un niveau : ce qu'il doit rendre est obligatoire (sinon un modèle rend le minimum)."""
    import copy
    s = copy.deepcopy(SCHEMA)
    if niveau == "livre":
        s["required"] = ["livre", "parties", "manques", "remarques"]
        s["properties"]["livre"]["required"] = ["idee", "developpe", "arc"]
    elif niveau == "partie":
        s["required"] = ["parties", "remarques"]
    else:
        s["required"] = ["chapitre", "manques", "remarques"]
        s["properties"]["chapitre"]["required"] = ["synopsis", "question", "fiches", "deroule", "assertions"]
        for k in ("livre", "parties"):
            del s["properties"][k]
    return s


SYSTEME = """Tu es l'atelier de plan du livre « {titre} », un livre de vulgarisation en français. Le livre
s'écrit de haut en bas : le livre (son idée, son arc), ses parties (le sens de chacune), ses chapitres
(le synopsis de chacun), puis le texte. Sous le livre, une base de connaissance : les fiches
(kb/fiches/<slug>.md), dossiers thématiques sourcés — le livre ne dit rien qu'une fiche ne porte.

Ton travail, à ce niveau-ci : {tache}

Règles :
- Le plan est un récit : chaque partie a une nécessité (pourquoi elle vient là), chaque chapitre
  une question à laquelle il répond et qui ouvre la suivante. Pas de catalogue.
- Appuie-toi sur les fiches : lis celles qui comptent (Read). Un chapitre cite ses fiches par leur
  slug exact. Un sujet sans fiche : signale-le dans `manques` (une fiche à créer), sans l'inventer.
- Garde ce qui existe quand c'est bon : une partie ou un chapitre existant garde son `id` ou son
  `slug` (recopie-les) ; un élément nouveau n'en a pas.
- Français, précis, sans emphase. Un synopsis de chapitre dit ce qui arrive, pas ce qu'on va
  expliquer.
- `remarques` : ce que tu as changé et pourquoi, en quelques phrases."""

TACHES = {
    "livre": "proposer la structure du livre — l'idée maîtresse (une phrase), l'arc d'ensemble, "
             "un synopsis développé (quelques paragraphes), puis les parties (trois à sept), chacune avec son "
             "sens, son arc et sa question, et ses chapitres, chacun avec un titre, une période si elle a un sens, "
             "un synopsis de deux ou trois phrases, sa question et ses fiches.",
    "partie": "développer UNE partie (désignée plus bas) : son sens (un paragraphe), son arc, sa question, et la "
              "liste de ses chapitres dans l'ordre, chacun avec son synopsis, sa question et ses fiches. Tu peux "
              "ajouter, retirer, fusionner ou réordonner ses chapitres ; ne touche pas aux autres parties. Rends une "
              "seule partie dans `parties`.",
    "chapitre": "développer UN chapitre (désigné plus bas) : son synopsis développé (ce qui arrive, dans l'ordre), "
                "sa question, ses fiches (lis-les, et dis pour chacune ce qu'elle apporte), le déroulé de son essai "
                "(les sections, dans l'ordre, chacune avec ce qu'elle établit) et les assertions qu'il doit établir "
                "— des faits précis, vérifiables, chacun avec la fiche qui le porte. Rends-le dans `chapitre`.",
}


def _texte_plan(P, focus_partie=None, focus_chapitre=None):
    L = ["## Le livre", "Synopsis court : %s" % (P["livre"].get("synopsis") or "(vide)")]
    for k, lib in (("idee", "Idée maîtresse"), ("arc", "Arc"), ("developpe", "Synopsis développé")):
        if P["livre"].get(k):
            L.append("%s : %s" % (lib, P["livre"][k]))
    L.append("\n## Le plan actuel" + ("" if P["parties"] else " : vide (aucune partie)"))
    for p in P["parties"]:
        marque = "  ← LA PARTIE À DÉVELOPPER" if p["id"] == focus_partie else ""
        L.append("\n### Partie %s — %s%s" % (p["id"], p["title"], marque))
        for k in plan.CHAMPS_PARTIE:
            if p.get(k):
                L.append("%s : %s" % (k, p[k]))
        for c in p["chapitres"]:
            m = "  ← LE CHAPITRE À DÉVELOPPER" if c["slug"] == focus_chapitre else ""
            L.append("- [%s] %s%s%s — %s%s" % (c["slug"], c["title"], " (%s)" % c["periode"] if c.get("periode") else "",
                                              m, (c.get("synopsis") or "(pas de synopsis)")[:400],
                                              " — fiches : %s" % ", ".join(c["fiches"]) if c.get("fiches") else ""))
    return "\n".join(L)


def cree(corps):
    niveau = corps.get("niveau")
    if niveau not in TACHES:
        raise ValueError("niveau : livre, partie ou chapitre")
    cible = {"niveau": niveau, "partie": corps.get("partie"), "chapitre": corps.get("chapitre")}
    P = plan.lit()
    if niveau == "partie" and not any(p["id"] == cible["partie"] for p in P["parties"]):
        raise KeyError(cible["partie"])
    if niveau == "chapitre" and not any(c["slug"] == cible["chapitre"] for p in P["parties"] for c in p["chapitres"]):
        raise KeyError(cible["chapitre"])
    d = {"id": "s-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "plan", "portee": "plan", "mode": "lecture",
         "consigne": (corps.get("consigne") or "").strip(),
         "modele_choisi": reecriture._choix_modele(corps), "cible": cible,
         "etat": "en_cours", "cree": livre._maintenant(),
         "budget": {"recherches": 0, "pages": 0, "limites": reecriture.limites("plan")}}
    d["titre"] = titre_de(d)
    systeme = SYSTEME.format(titre=livre.meta().get("titre", ""), tache=TACHES[niveau])
    L = [_texte_plan(P, cible.get("partie"), cible.get("chapitre"))]
    if niveau == "chapitre":
        c = next(c for p in P["parties"] for c in p["chapitres"] if c["slug"] == cible["chapitre"])
        L.append("\n## Le chapitre à développer : %s — %s\nSes fiches actuelles (à lire) : %s" % (
            c["slug"], c["title"], ", ".join("kb/fiches/%s.md" % f for f in c["fiches"]) or "aucune : choisis-les dans l'index"))
    try:
        g = kb.graphe()
        L.append("\n## Les clusters thématiques de la base\n" + "\n".join(
            "- %s : %s" % (" · ".join(x["mots"][:3]), ", ".join(x["phares"])) for x in g["clusters"]))
    except Exception:                               # noqa: BLE001
        pass
    L.append("\n## Les fiches (kb/fiches/<slug>.md)\n" + creation.index_texte())
    if d["consigne"]:
        L.append("\n## Précision de l'auteur\n" + d["consigne"])
    from . import refs
    L.append(refs.annexe(d["consigne"]))
    d["contexte"] = {"systeme": systeme, "message": "\n".join(L)}
    reecriture._ecrit(SLUG_KB, d)
    import asyncio
    t = asyncio.get_running_loop().create_task(_execute(d["id"]))
    reecriture._taches.add(t)
    t.add_done_callback(reecriture._taches.discard)
    return d


def titre_de(d):
    c = d["cible"]
    return {"livre": "Plan : la structure du livre", "partie": "Plan : développer la partie %s" % c.get("partie"),
            "chapitre": "Plan : développer le chapitre %s" % c.get("chapitre")}[c["niveau"]]


async def _execute(ident):
    d = reecriture.lit(SLUG_KB, ident)
    outils = ["Read", "Grep", "Glob"]
    lim = d["budget"]["limites"]
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON, thinking=reecriture.PENSEE,
        tools=outils, allowed_tools=outils, max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": schema(d["cible"]["niveau"])},
        hooks=reecriture.garde(d, lim), model=reecriture.modele("plan", d))
    await reecriture._lance(SLUG_KB, d, options, d["contexte"]["message"], conclut)


def conclut(d, sortie):
    connues = {f["slug"] for f in kb.index()}
    P = plan.lit()
    ids = {p["id"] for p in P["parties"]}
    slugs = {c["slug"] for p in P["parties"] for c in p["chapitres"]}
    R = dict(sortie)
    for p in R.get("parties") or []:
        if p.get("id") not in ids:
            p["id"] = None
        for c in p.get("chapitres") or []:
            if c.get("slug") not in slugs:
                c["slug"] = None
            c["fiches"] = [f for f in c.get("fiches") or [] if f in connues]
    ch = R.get("chapitre") or {}
    if ch:
        ch["fiches"] = [f for f in ch.get("fiches") or [] if f.get("fiche") in connues]
    d.update(etat="prete", resultat=R)


# ------------------------------------------------------------------ retenir

def decide(ident, corps):
    """{action: retenir|rejeter, livre: [champs], parties: {i: [champs]}, chapitres: {"i.j": true},
    chapitre: [champs], amorce: bool}."""
    d = reecriture.lit(SLUG_KB, ident)
    if d["etat"] != "prete":
        raise reecriture.Conflit("la demande n'attend pas de décision (%s)" % d["etat"])
    if corps.get("action") == "rejeter":
        d.update(etat="decidee", decision={"proposition": None, "motif": corps.get("motif", ""), "date": livre._maintenant()})
        reecriture._ecrit(SLUG_KB, d)
        return d
    R, faits = d["resultat"], []
    # le livre
    L = R.get("livre") or {}
    ch = {k: L[k] for k in corps.get("livre") or [] if L.get(k)}
    if ch:
        plan.modifie_livre(ch)
        faits.append("livre : " + ", ".join(ch))
    # les parties et leurs chapitres, dans l'ordre de la proposition
    for i, p in enumerate(R.get("parties") or []):
        champs = corps.get("parties", {}).get(str(i))
        retenus = [j for j, _ in enumerate(p.get("chapitres") or []) if corps.get("chapitres", {}).get("%d.%d" % (i, j))]
        if champs is None and not retenus:
            continue
        pid = p.get("id")
        vals = {"title" if k == "titre" else k: p.get(k) for k in (champs or []) if p.get(k)}
        if not pid:
            pid = plan.ajoute_partie(p["titre"], champs={k: v for k, v in vals.items() if k != "title"})
            faits.append("partie %s créée" % pid)
        elif vals:
            plan.modifie_partie(pid, vals)
            faits.append("partie %s : %s" % (pid, ", ".join(vals)))
        ordre = []
        for j in retenus:
            c = p["chapitres"][j]
            champs_c = {"synopsis": c.get("synopsis"), "question": c.get("question"), "fiches": c.get("fiches") or []}
            if c.get("slug"):
                plan.modifie_chapitre(c["slug"], dict(champs_c, title=c["titre"], periode=c.get("periode") or ""))
                plan.deplace_chapitre(c["slug"], pid=pid)
                ordre.append(c["slug"])
                faits.append("chapitre %s mis à jour" % c["slug"])
            else:
                s = plan.ajoute_chapitre(pid, c["titre"], champs=dict(champs_c, periode=c.get("periode")))
                ordre.append(s)
                faits.append("chapitre %s créé" % s)
        ordonne(pid, ordre)
    # un chapitre
    C = R.get("chapitre") or {}
    slug = d["cible"].get("chapitre")
    if C and slug:
        champs = {}
        for k in corps.get("chapitre") or []:
            if k == "fiches":
                champs["fiches"] = [f["fiche"] for f in C.get("fiches") or []]
            elif C.get(k):
                champs[k] = C[k]
        if champs:
            plan.modifie_chapitre(slug, champs)
            faits.append("chapitre %s : %s" % (slug, ", ".join(champs)))
        if corps.get("amorce"):
            faits += amorce(slug, C)
    d.update(etat="decidee", decision={"proposition": "retenue", "faits": faits, "date": livre._maintenant()})
    reecriture._ecrit(SLUG_KB, d)
    return d


def ordonne(pid, ordre):
    """Les chapitres retenus d'une partie, dans l'ordre de la proposition (les autres restent après)."""
    if not ordre:
        return
    y, doc = plan._lit_structure()
    _, p = plan._partie(doc, pid)
    chs = list(p.get("chapters") or [])
    rang = {s: i for i, s in enumerate(ordre)}
    chs.sort(key=lambda c: rang.get(c.get("slug"), len(ordre)))
    p["chapters"].clear()
    p["chapters"].extend(chs)
    plan._ecrit_structure(y, doc)


# ------------------------------------------------------------------ amorcer l'essai

def amorce(slug, C):
    """Le squelette de l'essai (une section par étape du déroulé, un paragraphe « à écrire ») et un
    premier verrou (les assertions, chacune avec sa fiche). Refusé si l'essai a déjà du texte."""
    from . import edition, essai
    d = livre.dossier(slug)
    faits = []
    m = livre.meta()
    if "essai" not in (m.get("versions") or {}):
        y = livre.yaml_rt()
        p = livre.LIVRE / "livre.yaml"
        doc = y.load(p.read_text(encoding="utf-8"))
        doc["versions"]["essai"] = {"titre": "Essai", "role": "explique — le pourquoi et le comment du récit, avec notes et sources"}
        p.write_text(livre.rt_texte(y, doc), encoding="utf-8")
        faits.append("version « essai » ajoutée au livre")
    pe = d / "essai.md"
    if pe.exists() and pe.read_text(encoding="utf-8").strip():
        faits.append("essai déjà commencé : squelette non écrit")
    else:
        pris, L = set(), []
        for s in C.get("deroule") or []:
            sid = essai.ident_section(s["titre"], pris)
            bloc = edition._nouvel_id(slug)
            L += ["## %s {#%s}" % (s["titre"].strip(), sid), "",
                  "*À écrire — %s* ^%s" % (" ".join(s["contenu"].split()), bloc), ""]
            pe.write_text("\n".join(L), encoding="utf-8")     # écrit au fil : _nouvel_id voit les ^id déjà pris
        faits.append("squelette de l'essai : %d section(s)" % len(C.get("deroule") or []))
    pv = d / "verrou.yaml"
    if C.get("assertions") and not pv.exists():
        import yaml
        sec = {"id": "A", "title": "Ce que le chapitre établit", "assertions": []}
        for i, a in enumerate(C["assertions"], 1):
            x = {"id": "1.%d" % i, "statut": "obligatoire", "texte": " ".join(a["texte"].split())}
            if a.get("fiche"):
                x["note"] = "fiche %s" % a["fiche"]
            sec["assertions"].append(x)
        pv.write_text("# Verrou — %s. Amorcé depuis le synopsis (%s).\n\n" % (slug, livre._maintenant()[:10]) +
                      yaml.safe_dump({"chapter": slug, "sections": [sec]}, allow_unicode=True, sort_keys=False, width=100),
                      encoding="utf-8")
        faits.append("verrou amorcé : %d assertion(s)" % len(sec["assertions"]))
    if not (d / "links.yaml").exists():
        (d / "links.yaml").write_text("recit: {}\n", encoding="utf-8")
    y, doc = plan._lit_structure()
    _, _, c = plan._chapitre(doc, slug)
    vs = list(c.get("versions") or [])
    if "essai" not in vs:
        c["versions"] = vs + ["essai"]
    if c.get("status") == "outline":
        c["status"] = "draft"
    plan._ecrit_structure(y, doc)
    plan.journal({"type": "essai_amorce", "chapitre": slug, "faits": faits})
    return faits
