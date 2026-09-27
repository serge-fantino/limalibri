# -*- coding: utf-8 -*-
"""Les renvois : une fiche cite ses voisines ([[lien]]) ; les voisines, elles, ne la citent pas
encore. Claude propose, pour chacune, où poser le renvoi inverse et comment le dire.

Une demande de type « renvois » vit dans kb/demandes/<id>.json. Claude lit la fiche et chacune
de ses voisines (sans web), et rend, par voisine : la section où le renvoi a sa place, le
paragraphe après lequel (ou à la fin duquel) il vient — désigné par ses premiers mots —, le
mode (une phrase ajoutée au paragraphe, ou un paragraphe nouveau) et le texte, qui porte
[[fiche]]. Une voisine où le renvoi n'aurait pas de sens est laissée, avec la raison.

Retenir écrit dans les fiches voisines, et seulement ce qui est coché : le reste du fichier
est intact ; chaque insertion va au journal de la base (kb/journal.jsonl). Le paragraphe
complété perd sa marque de confiance (son texte a changé).
"""
import re
import json
import time
import secrets

from claude_agent_sdk import ClaudeAgentOptions

from . import livre, kb, reecriture

SLUG_KB = "_kb"

SCHEMA = {
    "type": "object",
    "properties": {
        "renvois": {"type": "array", "items": {"type": "object", "properties": {
            "fiche": {"type": "string"},
            "section": {"type": "string"},
            "apres": {"type": "string"},
            "mode": {"type": "string", "enum": ["phrase", "paragraphe"]},
            "texte": {"type": "string"},
            "raison": {"type": "string"}},
            "required": ["fiche", "section", "apres", "mode", "texte", "raison"]}},
        "ignorees": {"type": "array", "items": {"type": "object", "properties": {
            "fiche": {"type": "string"}, "raison": {"type": "string"}}, "required": ["fiche", "raison"]}}},
    "required": ["renvois"]}

SYSTEME = """Tu travailles sur la base de connaissance d'un livre de vulgarisation en français : des
fiches (kb/fiches/<slug>.md), dossiers thématiques qui se citent par [[slug]].

Une fiche vient d'entrer dans la base. Elle cite des voisines ; les voisines ne la citent pas
encore. Pour chacune, tu proposes UN renvoi vers elle, posé à l'endroit exact où un lecteur de la
voisine en aurait besoin : là où la voisine touche au sujet de la fiche nouvelle, l'effleure, ou
s'arrête avant lui.

Lis la fiche nouvelle, puis chaque voisine en entier (Read). Pour chaque voisine, rends :
- section : l'identifiant {#id} de la section où le renvoi a sa place (sans les accolades) ;
- apres : les premiers mots (dix à quinze, recopiés exactement) du paragraphe concerné ;
- mode : « phrase » (une phrase ajoutée à la fin de ce paragraphe, le cas ordinaire) ou
  « paragraphe » (un paragraphe court inséré après lui, si le renvoi demande plus d'une phrase) ;
- texte : la phrase ou le paragraphe, en français, dans le ton de la voisine, qui contient
  [[slug-de-la-fiche-nouvelle]] et dit ce qu'on y trouve — pas « voir aussi » sec, mais une
  raison de s'y rendre. Une phrase suffit presque toujours ;
- raison : pourquoi là.

Si un renvoi n'a pas de sens dans une voisine (elle ne touche pas au sujet), mets-la dans
`ignorees` avec la raison. N'invente aucun fait : le renvoi dit ce que contient la fiche
nouvelle, rien d'autre. Tu ne modifies rien toi-même."""


def voisines(slug):
    """Les fiches que cite la fiche, qui ne la citent pas encore."""
    _, corps = kb._lit(slug)
    connues = {f["slug"] for f in kb.index()}
    cites = [c for c in dict.fromkeys(m.group(1).strip() for m in kb.LIEN.finditer(corps)) if c in connues and c != slug]
    out = []
    for v in cites:
        _, cv = kb._lit(v)
        if not any(m.group(1).strip() == slug for m in kb.LIEN.finditer(cv)):
            out.append(v)
    return out


def cree(corps):
    slug = (corps.get("fiche") or "").strip()
    kb._lit(slug)
    vs = [v for v in (corps.get("voisines") or voisines(slug))]
    if not vs:
        raise ValueError("aucune voisine sans renvoi : toutes les fiches qu'elle cite la citent déjà")
    d = {"id": "l-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "renvois", "portee": "renvois", "mode": "lecture",
         "consigne": (corps.get("consigne") or "").strip(),
         "modele_choisi": reecriture._choix_modele(corps),
         "cible": {"fiche": slug, "voisines": vs},
         "etat": "en_cours", "cree": livre._maintenant(),
         "budget": {"recherches": 0, "pages": 0, "limites": reecriture.limites("pistes")}}
    d["titre"] = titre_de(d)
    L = ["# La fiche nouvelle : kb/fiches/%s.md" % slug, "\n# Ses voisines, sans renvoi vers elle"]
    for v in vs:
        _, cv = kb._lit(v)
        L.append("\n## kb/fiches/%s.md — sections :" % v)
        L += ["%s- %s {#%s}" % ("  " * (s["niveau"] - 2), s["titre"], s["id"]) for s in kb._structure(cv)[1]]
    if d["consigne"]:
        L.append("\n## Précision de l'auteur\n" + d["consigne"])
    from . import refs
    L.append(refs.annexe(d["consigne"]))
    d["contexte"] = {"systeme": SYSTEME, "message": "\n".join(L)}
    reecriture._ecrit(SLUG_KB, d)
    import asyncio
    t = asyncio.get_running_loop().create_task(_execute(d["id"]))
    reecriture._taches.add(t)
    t.add_done_callback(reecriture._taches.discard)
    return d


def titre_de(d):
    return "Renvois vers « %s » (%d voisine(s))" % (d["cible"]["fiche"], len(d["cible"].get("voisines") or []))


async def _execute(ident):
    d = reecriture.lit(SLUG_KB, ident)
    outils = ["Read", "Grep", "Glob"]
    lim = d.get("budget", {}).get("limites") or reecriture.limites("pistes")
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON, thinking=reecriture.PENSEE,
        tools=outils, allowed_tools=outils, max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": SCHEMA},
        hooks=reecriture.garde(d, lim), model=reecriture.modele("pistes", d))
    await reecriture._lance(SLUG_KB, d, options, d["contexte"]["message"], conclut)


# ------------------------------------------------------------------ trouver l'endroit, insérer

def _plat(s):
    return re.sub(r"[^a-z0-9]+", " ", kb._plat(re.sub(r"\[\[([^\]|#]+)[^\]]*\]\]", r"\1", s or ""))).strip()


def _place(md, section, apres):
    """Dans le texte d'une fiche : (i, j) les lignes du paragraphe visé, et (a, b) la section.
    Le paragraphe est trouvé par ses premiers mots ; à défaut, None (fin de section)."""
    lignes = md.split("\n")
    debut, niveau = None, None
    for i, l in enumerate(lignes):
        m = kb.TITRE.match(l)
        if m and m.group(3) == section:
            debut, niveau = i, len(m.group(1))
            break
    if debut is None:
        return None, None
    fin = len(lignes)
    for i in range(debut + 1, len(lignes)):
        m = kb.TITRE.match(lignes[i])
        if m and len(m.group(1)) <= niveau:
            fin = i
            break
    cle = _plat(apres)[:60]
    i = debut + 1
    while i < fin:
        if not lignes[i].strip():
            i += 1
            continue
        j = i
        while j + 1 < fin and lignes[j + 1].strip() and not kb.TITRE.match(lignes[j + 1]):
            j += 1
        bloc = " ".join(lignes[i:j + 1])
        if cle and (_plat(bloc).startswith(cle[:40]) or cle[:40] in _plat(bloc)):
            return (i, j), (debut, fin)
        i = j + 1
    return None, (debut, fin)


def apercu(md, r):
    par, sec = _place(md, r["section"], r["apres"])
    lignes = md.split("\n")
    return {"section_trouvee": sec is not None, "paragraphe_trouve": par is not None,
            "paragraphe": " ".join(lignes[par[0]:par[1] + 1])[:600] if par else None}


def insere(slug, r):
    """Pose un renvoi dans une fiche. Rend la ligne de journal."""
    p = kb.dossier() / (slug + ".md")
    md = p.read_text(encoding="utf-8")
    par, sec = _place(md, r["section"], r["apres"])
    lignes = md.split("\n")
    texte = " ".join(r["texte"].split())
    # une liste, un tableau, une citation : le renvoi vient après le bloc, jamais dedans
    structure = par and re.match(r"^\s*([-*+]\s|\d+[.)]\s|\||>)", lignes[par[0]])
    if par and r["mode"] == "phrase" and not structure:
        lignes[par[1]] = lignes[par[1]].rstrip() + " " + texte
        ou = "fin du paragraphe « %s… »" % " ".join(lignes[par[0]].split())[:60]
    elif par:
        lignes[par[1] + 1:par[1] + 1] = ["", texte]
        ou = "après le paragraphe « %s… »" % " ".join(lignes[par[0]].split())[:60]
    elif sec:
        k = sec[1]
        while k > sec[0] + 1 and not lignes[k - 1].strip():
            k -= 1
        lignes[k:k] = ["", texte]
        ou = "fin de la section {#%s}" % r["section"]
    else:
        while lignes and not lignes[-1].strip():
            lignes.pop()
        lignes += ["", texte]
        ou = "fin de la fiche (section {#%s} introuvable)" % r["section"]
    p.write_text("\n".join(lignes).rstrip("\n") + "\n", encoding="utf-8")
    e = {"type": "renvoi", "fiche": slug, "section": r["section"], "ou": ou, "texte": texte,
         "date": livre._maintenant()}
    with (livre.LIVRE / "kb" / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return e


def conclut(d, sortie):
    vs = set(d["cible"]["voisines"])
    out = []
    for r in sortie.get("renvois") or []:
        r = dict(r)
        r["fiche"] = re.sub(r"^.*/|\.md$|\[\[|\]\]", "", r.get("fiche", "").strip())
        r["section"] = (re.findall(r"[a-z0-9][a-z0-9-]*", (r.get("section") or "").lower()) or [""])[0]
        if r["fiche"] not in vs:
            continue
        _, cv = kb._lit(r["fiche"])
        r.update(apercu(cv, r))
        if "[[%s" % d["cible"]["fiche"] not in r["texte"]:
            r["texte"] = r["texte"].rstrip() + " [[%s]]" % d["cible"]["fiche"]
        out.append(r)
    d.update(etat="prete", resultat={"renvois": out, "ignorees": sortie.get("ignorees") or []})


def decide(ident, corps):
    """{action: inserer|rejeter, renvois: [{i, texte?}], motif}."""
    d = reecriture.lit(SLUG_KB, ident)
    if d["etat"] != "prete":
        raise reecriture.Conflit("la demande n'attend pas de décision (%s)" % d["etat"])
    if corps.get("action") == "rejeter":
        d.update(etat="decidee", decision={"proposition": None, "motif": corps.get("motif", ""), "date": livre._maintenant()})
        reecriture._ecrit(SLUG_KB, d)
        return d
    R = d["resultat"]["renvois"]
    faits = []
    for x in corps.get("renvois") or []:
        i = x.get("i")
        if not isinstance(i, int) or not 0 <= i < len(R):
            raise ValueError("renvoi inconnu : %s" % i)
        r = dict(R[i], texte=x.get("texte") or R[i]["texte"])
        faits.append(dict(insere(r["fiche"], r), i=i))
    if not faits:
        raise ValueError("aucun renvoi coché")
    d.update(etat="decidee", decision={"proposition": "renvois", "faits": faits, "date": livre._maintenant()})
    reecriture._ecrit(SLUG_KB, d)
    return d


# ------------------------------------------------------------------ relue

def marque_relue(slug):
    """Une fiche écrite par Claude, relue par l'auteur : « etat: brouillon » -> « etat: relue »."""
    p = kb.dossier() / (slug + ".md")
    md = p.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", md, re.S)
    if not m:
        raise ValueError("fiche sans en-tête")
    tete = m.group(1)
    jour = livre._maintenant()[:10]
    if re.search(r"^etat:", tete, re.M):
        tete = re.sub(r"^etat:.*$", "etat: relue", tete, flags=re.M)
    else:
        tete += "\netat: relue"
    tete = re.sub(r"^relue:.*\n?", "", tete, flags=re.M).rstrip("\n") + "\nrelue: %s" % jour
    p.write_text("---\n%s\n---\n" % tete + md[m.end():], encoding="utf-8")
    with (livre.LIVRE / "kb" / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "relue", "fiche": slug, "date": livre._maintenant()}, ensure_ascii=False) + "\n")
    return {"fiche": slug, "etat": "relue", "voisines_sans_renvoi": voisines(slug)}
