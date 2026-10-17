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


INTERTITRE = re.compile(r"^(#{2,6})\s+(.*?)\s*$")
AVEC_ID = re.compile(r"\s*\{#[\w-]+\}\s*$")
NUMERO = re.compile(r"^(\d+(\.\d+)*\.?|[a-z]\.|[IVX]+\.)\s+")


def identifie(texte):
    """Pose {#id} sur chaque intertitre qui n'en a pas (hors blocs de code). Rend (texte, n posés)."""
    from .essai import ident_section
    lignes = texte.split("\n")
    pris = {m.group(1) for m in re.finditer(r"\{#([\w-]+)\}", texte)}
    code, n = False, 0
    for i, l in enumerate(lignes):
        if l.lstrip().startswith("```"):
            code = not code
            continue
        m = None if code else INTERTITRE.match(l)
        if not m or AVEC_ID.search(l):
            continue
        titre = re.sub(r"[*_`]", "", NUMERO.sub("", m.group(2)))     # « 2. **Où c'est rangé** » -> « Où c'est rangé »
        lignes[i] = "%s {#%s}" % (l.rstrip(), ident_section(titre or m.group(2), pris))
        n += 1
    return "\n".join(lignes), n


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
    for c in livre.chapitres_seuls():
        p = livre.dossier(c["slug"]) / "brief.yaml"
        if not c.get("atelier") or not p.exists():
            continue
        for f in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("fiches") or []:
            out.setdefault(str(f), []).append({"slug": c["slug"], "title": c["title"], "numero": c.get("numero")})
    return out


def _centrale_par_fiche():
    """fiche -> clés des œuvres qui y sont exploitées : kb/sources/ s'il existe, sinon la
    bibliographie centrale d'héritage."""
    from . import sources as S
    if S.existe():
        out = {}
        for cle, o in S.toutes().items():
            for f in o.get("fiches") or []:
                out.setdefault(f, []).append(cle)
        return out
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
                       "origine": meta.get("origine"), "etat": meta.get("etat"),
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


def empreinte_bloc(texte):
    import hashlib
    return hashlib.sha1(" ".join(texte.split()).encode()).hexdigest()[:12]


def blocs(corps):
    """Les blocs du corps, dans l'ordre : [(texte, section_id, est_titre)]. Un bloc est ce qui
    est séparé par une ligne vide ; un bloc de code reste entier ; le titre « # » est omis."""
    corps = re.sub(r"^# [^\n]*\n", "", corps, count=1, flags=re.M)
    brut, cur, code = [], [], False
    for l in corps.split("\n"):
        if l.lstrip().startswith("```"):
            code = not code
        if not l.strip() and not code:
            if cur:
                brut.append("\n".join(cur))
            cur = []
        else:
            cur.append(l)
    if cur:
        brut.append("\n".join(cur))
    out, sec = [], None
    for b in brut:
        m = TITRE.match(b) if "\n" not in b else None
        if m and len(m.group(1)) > 1:
            sec = m.group(3) or sec
            out.append((b, sec, True))
        elif not re.fullmatch(r"\s*(-{3,}|\*{3,})\s*", b):
            out.append((b, sec, False))
        else:
            out.append((b, sec, True))
    return out


def _rendu(corps, slugs, heritage):
    """Le corps de la fiche en HTML : sans son titre (affiché à part), intertitres ancrés
    (id « fs-<id> »), liens [[…]] vers les fiches ou, hors fiches, marqués comme tels, et
    [@cle] en citations. Chaque bloc porte son empreinte (data-empreinte) : la confiance
    par paragraphe s'y accroche, et se perd si le texte change."""
    def wiki(m):
        cible, sec, texte = m.group(1).strip(), (m.group(2) or "").strip(), (m.group(3) or "").strip()
        lib = _html.escape(texte or cible)
        if cible in slugs:
            return '<a class="wiki" href="#fiches/%s%s">%s</a>' % (cible, "/" + sec if sec else "", lib)
        h = heritage.get(cible)
        if h:
            return '<span class="wiki-hors" title="%s">%s</span>' % (
                _html.escape("hors des fiches : %s (ancien dépôt, lecture seule)" % h), lib)
        return '<span class="wiki-mort" data-cible="%s" title="%s">%s</span>' % (
            _html.escape(cible), _html.escape("aucune fiche « %s » — clic : la créer" % cible), lib)

    morceaux = []
    for texte, _, titre in blocs(corps):
        h = markdown.markdown(LIEN.sub(wiki, texte), extensions=["tables", "attr_list"])
        if not titre:
            h = re.sub(r"^<(p|ul|ol|table|blockquote|pre|div|dl)\b",
                       r'<\1 data-empreinte="%s"' % empreinte_bloc(texte), h.strip(), count=1)
        morceaux.append(h)
    h = "\n".join(morceaux)
    # [@cle], et [@a, @b] / [@a; @b] : une citation par clé
    h = re.sub(r"\[(@[\w-]+(?:\s*[,;]\s*@[\w-]+)*)\]",
               lambda m: " ".join('<cite data-cle="%s">%s</cite>' % (k, k) for k in re.findall(r"@([\w-]+)", m.group(1))), h)
    return re.sub(r'<h([2-6]) id="([\w-]+)">', r'<h\1 id="fs-\2" data-section="\2">', h)


# ------------------------------------------------------------------ la confiance par paragraphe

# kb/fiches/<slug>.confiance.json, à côté de la fiche : {empreinte d'un paragraphe -> degré,
# raison}. Donnée par une lecture de Claude (à la demande) ou à la création d'une fiche.
# Un paragraphe dont le texte change perd sa marque : l'empreinte ne correspond plus.
DEGRES = ("établi", "débattu", "récent", "hypothèse", "projeté", "raisonnement")


def _fichier_confiance(slug):
    return dossier() / (slug + ".confiance.json")


def confiance_par(slug):
    import json
    p = _fichier_confiance(slug)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def ecrit_confiance(slug, donnees):
    import json
    _fichier_confiance(slug).write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ les œuvres (la bibliographie)

def _refs_de_fiche(corps):
    """Les sources d'une fiche écrite par LimaLibri : « - `cle` — référence … — « extrait » »."""
    out = {}
    m = re.search(r"^## Sources[^\n]*\n(.*?)(?=^## |\Z)", corps, re.S | re.M)
    for l in (m.group(1).splitlines() if m else []):
        x = re.match(r"^- `([\w-]+)` — (.*)$", l.strip())
        if not x:
            continue
        reste = x.group(2)
        ext = re.search(r" — « (.*) »", reste)
        ref = reste[:ext.start()] if ext else reste
        doi = re.search(r"DOI (10\.\S+)", ref)
        url = re.search(r"<(https?://[^>]+)>", ref)
        ref = re.sub(r"\s*<https?://[^>]+>", "", ref).replace(" *(non vérifié)*", "").strip()
        out[x.group(1)] = {"ref": ref, "doi": doi.group(1).rstrip(".") if doi else None,
                           "url": url.group(1) if url else None, "extrait": ext.group(1) if ext else None,
                           "verifie": "(non vérifié)" not in l}
    return out


def oeuvres():
    """Toutes les œuvres du livre : la bibliographie centrale (héritage), celles des chapitres
    (bibliographie.yaml, avec les notes de l'essai), celles des fiches écrites par LimaLibri.
    Une œuvre, une clé ; ce qui la cite est rassemblé."""
    out = {}

    def oeuvre(cle):
        return out.setdefault(cle, {"cle": cle, "ref": "", "doi": None, "url": None, "centrale": False,
                                    "fiches": [], "chapitres": [], "extraits": [], "doute": None,
                                    "statut": None, "verification": None, "doublon_de": None, "notes": None})
    from . import sources as S
    if S.existe():                               # la bibliographie du livre : kb/sources/
        for cle, x in S.toutes().items():
            o = oeuvre(cle)
            o.update({k: x.get(k) for k in ("ref", "doi", "url", "statut", "verification", "doublon_de", "doute", "notes", "origine",
                                            "documents", "citations")})
            o["ref"] = o["ref"] or ""
            o["centrale"] = True                 # « dans la base »
            o["fiches"] = list(x.get("fiches") or [])
    depot, h = livre.heritage()
    p = depot / h["bibliographie"] if depot and h.get("bibliographie") and not S.existe() else None
    if p and p.exists():
        for bloc in re.split(r"^### ", p.read_text(encoding="utf-8"), flags=re.M)[1:]:
            lignes = [l.strip() for l in bloc.strip().splitlines() if l.strip()]
            o = oeuvre(lignes[0])
            o["centrale"] = True
            corps = [l for l in lignes[1:] if not l.lower().startswith("fiches:")]
            o["ref"] = " ".join(corps)
            d = re.search(r"DOI (10\.\S+)", o["ref"])
            o["doi"] = d.group(1).rstrip(".") if d else None
            m = re.search(r"^fiches:\s*(.*)$", bloc, re.M)
            o["fiches"] = [x.strip() for x in (m.group(1).split(",") if m else []) if x.strip() not in ("", "—")]
    for c in livre.chapitres_seuls():
        pb = livre.dossier(c["slug"]) / "bibliographie.yaml"
        if not c.get("atelier") or not pb.exists():
            continue
        for e in (yaml.safe_load(pb.read_text(encoding="utf-8")) or {}).get("sources") or []:
            o = oeuvre(str(e["cle"]))
            o["ref"] = o["ref"] or e.get("ref") or ""
            o["doi"] = o["doi"] or e.get("doi")
            o["doute"] = o["doute"] or e.get("doute")
            for f in e.get("fiches") or []:
                if f not in o["fiches"]:
                    o["fiches"].append(f)
            if not o["centrale"] and o["statut"] is None:
                o["statut"] = "hors_base"
            o["chapitres"].append({"slug": c["slug"], "title": c["title"], "numero": c.get("numero"),
                                   "notes": e.get("notes") or [], "citation": e.get("citation")})
    for s in _slugs():
        _, corps = _lit(s)
        for cle, r in _refs_de_fiche(corps).items():
            o = oeuvre(cle)
            if not o["centrale"] and o["statut"] is None:
                o["statut"] = "hors_base"
            o["ref"] = o["ref"] or r["ref"]
            o["doi"] = o["doi"] or r["doi"]
            o["url"] = o["url"] or r["url"]
            if s not in o["fiches"]:
                o["fiches"].append(s)
            o["extraits"].append({"fiche": s, "extrait": r["extrait"], "verifie": r["verifie"]})
    return sorted(out.values(), key=lambda o: o["cle"])


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
    for c in livre.chapitres_seuls():
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
            "confiance_par": confiance_par(slug),
            "fichier": str(dossier() / (slug + ".md")), "liens": liens, "entrants": entrants,
            "chapitres": _chapitres_par_fiche().get(slug, []),
            "oeuvres": sorted(oeuvres.values(), key=lambda o: o["cle"]),
            "oeuvres_centrales": {"total": len(centrale),
                                  "hors_chapitres": sorted(set(centrale) - set(oeuvres))}}


# ------------------------------------------------------------------ le graphe, et ses clusters

MOTS_VIDES = set("""avant apres alors aussi autre autres avec avoir cette celle celui ceux comme comment dans
depuis donc elle elles entre encore etre faire fait font leur leurs mais meme moins parce plus pour pourquoi
quand quel quelle quelles quels sans selon sont sous tout toute toutes tous tres vers deux trois premier
premiere chose choses question quoi ainsi celle-ci forme formes monde emporte faite faits dire
peut peuvent fois entre-temps pendant chaque combien apporte apportee retire""".split())


def _plat(s):
    import unicodedata
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _fiches_de_tous_les_chapitres():
    """slug de chapitre -> ses fiches : le brief s'il est migré, sinon l'en-tête du chapitre
    de l'essai dans l'héritage (lecture seule)."""
    depot, h = livre.heritage()
    rep = depot / h.get("chapitres", {}).get("essai", "") if depot else None
    out = {}
    for c in livre.chapitres_seuls():
        liste = None
        p = livre.dossier(c["slug"]) / "brief.yaml"
        if c.get("atelier") and p.exists():
            liste = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("fiches")
        elif rep and (rep / (c["slug"] + ".md")).exists():
            m = re.search(r"^fiches:\s*\[(.*)\]", (rep / (c["slug"] + ".md")).read_text(encoding="utf-8")[:3000], re.M)
            liste = [x.strip() for x in m.group(1).split(",")] if m else None
        if liste:
            out[c["slug"]] = {"titre": c["title"], "numero": c.get("numero"), "atelier": bool(c.get("atelier")),
                              "fiches": [str(x) for x in liste]}
    return out


def graphe(resolution=1.0, poids_oeuvres=0.5, poids_chapitres=0.5):
    """Les fiches et leurs liens, et des clusters thématiques (communautés de Louvain).

    Trois sortes de liens, pondérés pour le calcul des clusters :
      lien        un [[lien]] entre deux fiches (1 ; 2 s'il va dans les deux sens)
      oeuvres     deux fiches exploitent les mêmes œuvres (poids_oeuvres par œuvre partagée)
      chapitre    deux fiches listées par un même chapitre (poids_chapitres par chapitre)
    Les chapitres sont aussi rendus comme nœuds (reliés à leurs fiches), mais n'entrent pas
    dans le calcul : ils prennent la couleur du cluster majoritaire de leurs fiches."""
    import itertools
    import collections
    import networkx as nx

    I = index()
    slugs = {f["slug"] for f in I}
    G = nx.Graph()
    G.add_nodes_from(sorted(slugs))            # un ordre fixe : les clusters ne changent pas d'un appel à l'autre
    aretes = collections.defaultdict(lambda: {"lien": 0, "oeuvres": 0, "chapitre": 0})

    def ajoute(a, b, sorte, n=1):
        if a != b and a in slugs and b in slugs:
            aretes[tuple(sorted((a, b)))][sorte] += n

    for f in I:
        for x in f["liens"]:
            ajoute(f["slug"], x, "lien")
    parcle = collections.defaultdict(set)
    for fs, cles in _centrale_par_fiche().items():
        for k in cles:
            parcle[k].add(fs)
    for fs in parcle.values():
        for a, b in itertools.combinations(sorted(fs), 2):
            ajoute(a, b, "oeuvres")
    chapitres = _fiches_de_tous_les_chapitres()
    for c in chapitres.values():
        for a, b in itertools.combinations(sorted(set(c["fiches"])), 2):
            ajoute(a, b, "chapitre")
    for (a, b), s in sorted(aretes.items()):
        G.add_edge(a, b, weight=s["lien"] + poids_oeuvres * s["oeuvres"] + poids_chapitres * s["chapitre"])

    comms = nx.community.louvain_communities(G, weight="weight", resolution=resolution, seed=7)
    comms = sorted(comms, key=len, reverse=True)
    cluster = {s: i for i, c in enumerate(comms) for s in c}
    degre = dict(G.degree(weight="weight"))

    # les mots d'un cluster : fréquents chez lui, rares ailleurs (titres et sujets)
    par = {f["slug"]: f for f in I}
    forme, doc = {}, {}
    for f in sorted(I, key=lambda f: f["slug"]):
        mots = set()
        for m in re.findall(r"[\w-]+", f["titre"] + " " + f["sujet"]):      # « l'œil » -> « œil »
            p = _plat(m).strip("-")
            if len(p) >= 5 and p not in MOTS_VIDES and not p.isdigit() and "-t-" not in p:
                mots.add(p)
                forme.setdefault(p, m.strip("-"))
        doc[f["slug"]] = mots
    df = collections.Counter(m for ms in doc.values() for m in ms)
    import math
    clusters = []
    for i, c in enumerate(comms):
        tf = collections.Counter(m for s in c for m in doc[s])
        score = {m: n * math.log(len(I) / df[m]) for m, n in tf.items() if n >= 2} or \
            {m: n * math.log(len(I) / df[m]) for m, n in tf.items()}
        mots = [forme[m] for m, _ in sorted(score.items(), key=lambda x: (-round(x[1], 6), x[0]))[:4]]
        phares = sorted(c, key=lambda s: (-degre.get(s, 0), s))[:3]
        clusters.append({"id": i, "taille": len(c), "mots": mots, "phares": phares,
                         "titres": [par[s]["titre"] for s in phares]})

    noeuds = [{"id": f["slug"], "type": "fiche", "titre": f["titre"], "cluster": cluster[f["slug"]],
               "degre": round(degre.get(f["slug"], 0), 1), "mots": f["mots"], "confiance": f["confiance"]}
              for f in I]
    liens = [{"source": a, "target": b, **s} for (a, b), s in aretes.items()]
    for slug, c in chapitres.items():
        fs = [x for x in c["fiches"] if x in slugs]
        if not fs:
            continue
        maj = collections.Counter(cluster[x] for x in fs).most_common(1)[0][0]
        noeuds.append({"id": "ch:" + slug, "type": "chapitre", "titre": c["titre"], "numero": c["numero"],
                       "atelier": c["atelier"], "cluster": maj, "degre": len(fs)})
        liens += [{"source": "ch:" + slug, "target": x, "lien": 0, "oeuvres": 0, "chapitre": 1, "sorte": "appartient"}
                  for x in fs]
    for c in clusters:
        c["chapitres"] = sorted((n["numero"] or 0, n["titre"]) for n in noeuds
                                if n["type"] == "chapitre" and n["cluster"] == c["id"])
    return {"noeuds": noeuds, "liens": liens, "clusters": clusters,
            "modularite": round(nx.community.modularity(G, comms, weight="weight"), 3),
            "parametres": {"resolution": resolution, "poids_oeuvres": poids_oeuvres, "poids_chapitres": poids_chapitres}}


# ------------------------------------------------------------------ l'en-tête d'une fiche ; le ménage

def pose_entete(slug, champs):
    """Écrit des champs dans l'en-tête d'une fiche (les autres lignes intactes). None retire."""
    p = dossier() / (slug + ".md")
    md = p.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", md, re.S)
    if not m:
        raise ValueError("fiche sans en-tête")
    lignes = m.group(1).split("\n")
    for cle, v in champs.items():
        i = next((n for n, l in enumerate(lignes) if l.split(":", 1)[0].strip() == cle), None)
        if v is None:
            if i is not None:
                del lignes[i]
        elif i is None:
            lignes.append("%s: %s" % (cle, v))
        else:
            lignes[i] = "%s: %s" % (cle, v)
    p.write_text("---\n%s\n---\n" % "\n".join(lignes) + md[m.end():], encoding="utf-8")


def journal(e):
    import json
    with (livre.LIVRE / "kb" / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(e, date=livre._maintenant()), ensure_ascii=False) + "\n")


def consequences(slug):
    """Ce qui dépend d'une fiche : les fiches qui la citent (et combien de fois), les chapitres
    qui la listent, les œuvres des bibliographies de chapitre qui y sont rattachées."""
    _lit(slug)
    citee = []
    for s in _slugs():
        if s == slug:
            continue
        n = sum(1 for m in LIEN.finditer(_lit(s)[1]) if m.group(1).strip() == slug)
        if n:
            citee.append({"fiche": s, "liens": n})
    chapitres, oeuvres = [], []
    for c in livre.chapitres_seuls():
        if not c.get("atelier"):
            continue
        br = livre.dossier(c["slug"]) / "brief.yaml"
        if br.exists() and slug in [str(x) for x in (yaml.safe_load(br.read_text(encoding="utf-8")) or {}).get("fiches") or []]:
            chapitres.append({"slug": c["slug"], "title": c["title"]})
        bi = livre.dossier(c["slug"]) / "bibliographie.yaml"
        if bi.exists():
            for e in (yaml.safe_load(bi.read_text(encoding="utf-8")) or {}).get("sources") or []:
                if slug in (e.get("fiches") or []):
                    oeuvres.append({"cle": e["cle"], "chapitre": c["slug"]})
    return {"fiche": slug, "citee_par": citee, "chapitres": chapitres, "oeuvres": oeuvres}


def supprime(slug, liens="laisser", motif=""):
    """Le ménage : la fiche va à la corbeille (kb/corbeille/, récupérable, avec sa confiance),
    sort des briefs et des bibliographies ; les [[liens]] qui la visaient restent (morts, en
    rouge : « créer ») ou sont défaits (le texte gardé), au choix. Tout va au journal."""
    import shutil
    C = consequences(slug)
    corbeille = livre.LIVRE / "kb" / "corbeille"
    corbeille.mkdir(parents=True, exist_ok=True)
    horo = livre._maintenant()[:19].replace(":", "").replace("-", "")
    shutil.move(str(dossier() / (slug + ".md")), str(corbeille / ("%s-%s.md" % (slug, horo))))
    c = dossier() / (slug + ".confiance.json")
    if c.exists():
        shutil.move(str(c), str(corbeille / ("%s-%s.confiance.json" % (slug, horo))))
    for ch in C["chapitres"]:
        fs = [str(x) for x in (livre.atelier(ch["slug"]).get("brief") or {}).get("fiches") or [] if str(x) != slug]
        livre.modifie_brief(ch["slug"], {"fiches": fs}, livre.empreinte_brief(ch["slug"]),
                            motif="fiche %s supprimée%s" % (slug, " — " + motif if motif else ""))
    y = livre.yaml_rt()
    for ch in {o["chapitre"] for o in C["oeuvres"]}:
        p = livre.dossier(ch) / "bibliographie.yaml"
        doc = y.load(p.read_text(encoding="utf-8"))
        for e in doc.get("sources") or []:
            if slug in (e.get("fiches") or []):
                reste = [x for x in e["fiches"] if x != slug]
                if reste:
                    e["fiches"] = reste
                else:
                    del e["fiches"]
        p.write_text(livre.rt_texte(y, doc), encoding="utf-8")
    from . import sources as S
    if S.existe():
        S.retire_fiche(slug)
    defaits = 0
    if liens == "retirer":
        for x in C["citee_par"]:
            p = dossier() / (x["fiche"] + ".md")
            md = p.read_text(encoding="utf-8")

            def texte(m):
                return (m.group(3) or m.group(1)).strip()
            nouveau = re.sub(r"\[\[(%s)(?:#([^\]|]*))?(?:\|([^\]]*))?\]\]" % re.escape(slug), texte, md)
            if nouveau != md:
                p.write_text(nouveau, encoding="utf-8")
                defaits += x["liens"]
    journal({"type": "suppression", "fiche": slug, "motif": motif, "liens": liens, "liens_defaits": defaits,
             "chapitres": [c["slug"] for c in C["chapitres"]], "citee_par": [c["fiche"] for c in C["citee_par"]],
             "corbeille": "kb/corbeille/%s-%s.md" % (slug, horo)})
    return dict(C, supprimee=True, liens_defaits=defaits, corbeille="kb/corbeille/%s-%s.md" % (slug, horo))
