# -*- coding: utf-8 -*-
"""Les fiches : la base de connaissance du livre (kb/fiches/<slug>.md).

Une fiche est un dossier thématique, partagé entre chapitres : un en-tête (type, sujet,
confiance), un titre « # », des sections à identifiant stable {#id}, et des liens
[[autre-fiche]] (ou [[fiche#section]], [[fiche|texte]]) vers ses voisines.

Ce qui la relie au reste du livre est calculé, jamais recopié dans la fiche :
  · les fiches qui la citent (leurs [[liens]]) ;
  · les chapitres qui l'utilisent (« fiches: » de leur brief.yaml) ;
  · les œuvres qui y sont exploitées : celles des bibliographies de chapitre (avec les notes
    de l'essai qui les citent), et le compte de la bibliographie centrale d'héritage.
Un lien vers un fichier qui n'est pas une fiche (le cadre poétique de l'ancien dépôt…) est
résolu dans l'héritage, en lecture seule, s'il y existe.
"""
import re
import html as _html

import yaml
import markdown

from . import livre

LIEN = re.compile(r"\[\[([^\]|#]+)(?:#([^\]|]*))?(?:\|([^\]]*))?\]\]")
TITRE = re.compile(r"^(#{1,6})\s+(.*?)(?:\s*\{#([\w-]+)\})?\s*$")


def dossier():
    return livre.LIVRE / "kb" / "fiches"


def _entete(texte):
    """L'en-tête « --- … --- », lu ligne à ligne (il n'est pas toujours du YAML strict)."""
    m = re.match(r"^---\n(.*?)\n---\n", texte, re.S)
    if not m:
        return {}, texte
    meta = {}
    for l in m.group(1).splitlines():
        k, _, v = l.partition(":")
        if _ and re.fullmatch(r"[\w-]+", k.strip()):
            meta[k.strip()] = v.strip()
    return meta, texte[m.end():]


def _lit(slug):
    p = dossier() / (slug + ".md")
    if not re.fullmatch(r"[\w-]+", slug) or not p.exists():
        raise KeyError(slug)
    return _entete(p.read_text(encoding="utf-8"))


def _structure(corps):
    """Titre (# …) et sections (## … {#id}), hors blocs de code."""
    titre, sections, code = None, [], False
    for l in corps.splitlines():
        if l.lstrip().startswith("```"):
            code = not code
            continue
        m = None if code else TITRE.match(l)
        if not m:
            continue
        if len(m.group(1)) == 1:
            titre = titre or m.group(2)
        else:
            sections.append({"id": m.group(3), "titre": m.group(2), "niveau": len(m.group(1))})
    return titre, sections


def confiance(texte):
    """« établi (a, b) · débattu (c) » -> [{degre: établi, sur: a, b}, …] — les pastilles."""
    out = []
    for morceau in re.split(r"\s+·\s+", texte or ""):
        m = re.match(r"^\s*([^(]+?)\s*(?:\((.*)\))?\s*$", morceau, re.S)
        if m and m.group(1):
            out.append({"degre": m.group(1).strip(), "sur": (m.group(2) or "").strip()})
    return out


def _slugs():
    return sorted(p.stem for p in dossier().glob("*.md")) if dossier().exists() else []


def _chapitres_par_fiche():
    out = {}
    for c in livre.chapitres():
        p = livre.dossier(c["slug"]) / "brief.yaml"
        if not c.get("atelier") or not p.exists():
            continue
        for f in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("fiches") or []:
            out.setdefault(str(f), []).append({"slug": c["slug"], "title": c["title"], "numero": c.get("numero")})
    return out


def _centrale_par_fiche():
    """fiche -> clés de la bibliographie centrale d'héritage qui y sont exploitées."""
    depot, h = livre.heritage()
    p = depot / h["bibliographie"] if depot and h.get("bibliographie") else None
    out = {}
    if not p or not p.exists():
        return out
    for bloc in re.split(r"^### ", p.read_text(encoding="utf-8"), flags=re.M)[1:]:
        cle = bloc.strip().splitlines()[0].strip()
        m = re.search(r"^fiches:\s*(.*)$", bloc, re.M)
        for f in (m.group(1).split(",") if m else []):
            if f.strip() not in ("", "—"):
                out.setdefault(f.strip(), []).append(cle)
    return out


def index():
    """Toutes les fiches, avec de quoi les chercher et les ranger."""
    slugs = _slugs()
    chap = _chapitres_par_fiche()
    entrants, fiches = {}, []
    for s in slugs:
        meta, corps = _lit(s)
        titre, sections = _structure(corps)
        sortants = sorted({m.group(1).strip() for m in LIEN.finditer(corps)})
        for x in sortants:
            entrants.setdefault(x, set()).add(s)
        fiches.append({"slug": s, "titre": titre or s, "sujet": meta.get("sujet", ""),
                       "confiance": confiance(meta.get("confiance")), "type": meta.get("type", ""),
                       "sections": len(sections), "mots": len(corps.split()),
                       "liens": [x for x in sortants if x in slugs], "chapitres": chap.get(s, [])})
    for f in fiches:
        f["entrants"] = sorted(entrants.get(f["slug"], set()) - {f["slug"]})
    return fiches


def _heritage_md():
    """nom -> chemin (relatif) des fichiers Markdown de l'ancien dépôt, pour résoudre un [[lien]]
    qui ne vise pas une fiche (le cadre poétique, un passage…)."""
    depot, _ = livre.heritage()
    out = {}
    if depot:
        for p in depot.rglob("*.md"):
            if not {"_to_delete", ".obsidian", "node_modules", "build"} & set(p.parts):
                out.setdefault(p.stem, str(p.relative_to(depot)))
    return out


def _rendu(corps, slugs, heritage):
    """Le corps de la fiche en HTML : sans son titre (affiché à part), intertitres ancrés
    (id « fs-<id> »), liens [[…]] vers les fiches ou, hors fiches, marqués comme tels."""
    corps = re.sub(r"^# [^\n]*\n", "", corps, count=1, flags=re.M)

    def wiki(m):
        cible, sec, texte = m.group(1).strip(), (m.group(2) or "").strip(), (m.group(3) or "").strip()
        lib = _html.escape(texte or cible)
        if cible in slugs:
            return '<a class="wiki" href="#fiches/%s%s">%s</a>' % (cible, "/" + sec if sec else "", lib)
        h = heritage.get(cible)
        return '<span class="wiki-hors" title="%s">%s</span>' % (
            _html.escape("hors des fiches : %s (ancien dépôt, lecture seule)" % h if h else "lien mort : aucune fiche « %s »" % cible), lib)
    corps = LIEN.sub(wiki, corps)
    h = markdown.markdown(corps, extensions=["footnotes", "tables", "attr_list"])
    return re.sub(r'<h([2-6]) id="([\w-]+)">', r'<h\1 id="fs-\2" data-section="\2">', h)


def fiche(slug):
    """Une fiche : son texte, sa structure, et tout ce qui la relie au livre."""
    meta, corps = _lit(slug)
    titre, sections = _structure(corps)
    slugs = set(_slugs())
    heritage = _heritage_md()
    depot, _ = livre.heritage()
    liens, vus = [], set()
    for m in LIEN.finditer(corps):
        cible = m.group(1).strip()
        if cible in vus:
            continue
        vus.add(cible)
        h = None if cible in slugs else heritage.get(cible)
        liens.append({"cible": cible, "fiche": cible in slugs, "heritage": h,
                      "heritage_abs": str(depot / h) if h and depot else None})
    entrants = []
    for s in sorted(slugs - {slug}):
        _, c = _lit(s)
        if any(m.group(1).strip() == slug for m in LIEN.finditer(c)):
            entrants.append(s)
    # les œuvres : celles des chapitres migrés (avec les notes qui les citent), puis la base centrale
    oeuvres = {}
    for c in livre.chapitres():
        p = livre.dossier(c["slug"]) / "bibliographie.yaml"
        if not c.get("atelier") or not p.exists():
            continue
        for e in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("sources") or []:
            if slug in (e.get("fiches") or []):
                o = oeuvres.setdefault(e["cle"], {"cle": e["cle"], "ref": e.get("ref", ""), "doi": e.get("doi"),
                                                  "chapitres": []})
                o["chapitres"].append({"slug": c["slug"], "title": c["title"], "notes": e.get("notes") or []})
    centrale = _centrale_par_fiche().get(slug, [])
    return {"slug": slug, "titre": titre or slug, "meta": meta, "confiance": confiance(meta.get("confiance")),
            "md": corps, "html": _rendu(corps, slugs, heritage), "sections": sections,
            "fichier": str(dossier() / (slug + ".md")), "liens": liens, "entrants": entrants,
            "chapitres": _chapitres_par_fiche().get(slug, []),
            "oeuvres": sorted(oeuvres.values(), key=lambda o: o["cle"]),
            "oeuvres_centrales": {"total": len(centrale),
                                  "hors_chapitres": sorted(set(centrale) - set(oeuvres))}}
