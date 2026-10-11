# -*- coding: utf-8 -*-
"""Accès à un livre vu par l'atelier.

Le livre est un dossier (ATELIER_LIVRE, par défaut UneVie/book-atelier) qui porte :
  livre.yaml       ce qui décrit le livre (titre, auteur, synopsis, couverture, héritage)
  structure.yaml   l'ordre et le découpage des chapitres
  chapters/<slug>/ un chapitre migré (brief, verrou, liens, recit.md, essai.md ancrés en ^id)

Un chapitre pas encore migré est lu dans le dépôt d'« héritage » déclaré par
livre.yaml, en lecture seule. Un livre sans héritage n'a que ses chapitres migrés.
"""
import io
import os
import re
import json
import secrets
import hashlib
import datetime
import pathlib
import functools
import yaml
import markdown
import html as html_lib
from ruamel.yaml import YAML
from ruamel.yaml.constructor import RoundTripConstructor
from ruamel.yaml.scalarstring import LiteralScalarString
from ruamel.yaml.comments import CommentedMap

AWEN = pathlib.Path(__file__).resolve().parents[3]
LIVRE = pathlib.Path(os.environ.get("ATELIER_LIVRE", AWEN / "UneVie" / "book-atelier")).resolve()

VERSIONS = ("recit", "essai")
ENTETE = re.compile(r"^---\n.*?\n---\n", re.S)
ANCRE = re.compile(r"[ \t]\^([a-z0-9]+)[ \t]*$", re.M)
JETON = re.compile(r"\s*§blk:([a-z0-9]+)§\s*(</(?:p|li)>)")
CITATION = re.compile(r"\[@([\w-]+)\]")
RENVOI = re.compile(r"\[chap:([a-z0-9-]+)\]")


# ------------------------------------------------------------------ le livre (livre.yaml)

GABARIT_LIVRE = """# Le livre — ce qui le décrit en entier. L'ordre et le découpage des chapitres sont
# dans structure.yaml ; ici, l'identité du livre et ce qu'il faut pour le publier
# (page de titre, EPUB, couverture). Les chemins sont relatifs à ce dossier.
# Modifiable dans l'atelier (page du livre) ou à la main.

titre: {titre}
sous_titre: null
auteur: null
langue: fr

# Les versions du texte, alignées chapitre pour chapitre.
versions:
  recit:
    titre: Récit
    role: raconte

synopsis: null
quatrieme: null

# Image de couverture (chemin relatif, ex. media/couverture.jpg).
couverture: null
"""

GABARIT_STRUCTURE = """# L'ordre et le découpage des chapitres. Ordre = position dans ce fichier ;
# aucun numéro n'y est stocké. Petit et déclaratif : des références, jamais du contenu.

prefaces: []
parts: []
"""

# Les champs que la page du livre peut modifier ; le reste (versions, héritage) se
# change à la main, dans le fichier.
EDITABLES = ("titre", "sous_titre", "auteur", "langue", "synopsis", "quatrieme", "couverture",
             "numerotation_essai", "claude", "versions")
CLAUDE_GENRES = {"verification": ("tours", "recherches", "pages", "modele"), "reecriture": ("tours", "modele"),
                 "fiche": ("tours", "recherches", "pages", "modele"), "pistes": ("tours", "modele"),
                 "reference": ("tours", "recherches", "pages", "modele"), "naive": ("modele",),
                 "document": ("tours", "recherches", "pages", "modele"), "plan": ("tours", "modele"),
                 "conversation": ("tours", "recherches", "pages", "modele"), "redaction": ("tours", "modele"),
                 "cadrage": ("tours", "modele"), "relecture": ("tours", "modele"),
                 "storyboard": ("tours", "modele"), "recit": ("tours", "modele")}
NUMEROTATIONS = ("aucune", "sections", "paragraphes")


def initialise():
    """Fait d'un dossier un livre : livre.yaml et structure.yaml s'ils manquent.
    Ne touche jamais un fichier existant. Rend la liste de ce qui a été créé."""
    LIVRE.mkdir(parents=True, exist_ok=True)
    crees = []
    for nom, contenu in (("livre.yaml", GABARIT_LIVRE.format(titre=LIVRE.name)),
                         ("structure.yaml", GABARIT_STRUCTURE)):
        p = LIVRE / nom
        if not p.exists():
            p.write_text(contenu, encoding="utf-8")
            crees.append(nom)
    return crees


class _Lecteur(RoundTripConstructor):
    """Lecture aller-retour où « 07e2 » ou « 5e56 » restent du texte : chez nous, ce sont des
    identifiants de paragraphe, pas des nombres (YAML 1.2 y verrait 700.0 et 5e+56)."""


def _nombre_ou_identifiant(self, node):
    brut = self.construct_scalar(node)
    if re.fullmatch(r"[0-9]+[eE][0-9]+", str(brut)):
        return str(brut)
    return RoundTripConstructor.construct_yaml_float(self, node)


_Lecteur.add_constructor("tag:yaml.org,2002:float", _nombre_ou_identifiant)


def yaml_rt():
    """Un YAML qui garde commentaires et mise en forme. Toute lecture/écriture « aller-retour »
    passe par ici (voir _Lecteur). À l'écriture, un tel identifiant est mis entre guillemets."""
    y = YAML()
    y.Constructor = _Lecteur
    y.preserve_quotes = True
    y.width = 100
    return y


def rt_texte(y, doc):
    """Le document en texte, sans la directive %YAML que la version 1.1 ajoute."""
    s = io.StringIO()
    y.dump(doc, s)
    return re.sub(r"\A%YAML 1\.1\n---\n?", "", s.getvalue())


def _version(p):
    return hashlib.sha1(p.read_bytes()).hexdigest()[:12] if p.exists() else ""


def meta():
    p = LIVRE / "livre.yaml"
    m = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}
    m.setdefault("titre", LIVRE.name)
    m["_version"] = _version(p)
    return m


class Conflit(Exception):
    pass


def intention_version(version):
    """Ce que l'auteur dit d'une version dans livre.yaml (son titre, son rôle) : l'intention à donner à Claude."""
    v = (meta().get("versions") or {}).get(version) or {}
    role = " ".join(str(v.get("role") or "").split())
    return ("%s — %s" % (v.get("titre") or version, role)) if role else ""


def ecrit_meta(champs, version):
    """Modifie des champs de livre.yaml en gardant ses commentaires et sa mise en forme.

    `version` est l'empreinte du fichier tel que la page l'a lu : si le fichier a changé
    entre-temps (édité à la main, ou par Claude), on refuse plutôt que d'écraser."""
    p = LIVRE / "livre.yaml"
    if _version(p) != version:
        raise Conflit("livre.yaml a changé depuis son ouverture")
    inconnus = set(champs) - set(EDITABLES)
    if inconnus:
        raise KeyError(", ".join(sorted(inconnus)))
    if champs.get("numerotation_essai", "aucune") not in NUMEROTATIONS:
        raise KeyError("numerotation_essai : %s" % "|".join(NUMEROTATIONS))
    y = yaml_rt()
    doc = y.load(p.read_text(encoding="utf-8")) or {}
    if "versions" in champs:                  # le titre et le rôle des deux versions — l'atelier n'en connaît pas d'autres
        vs = champs.pop("versions") or {}
        cible = doc.get("versions")
        if cible is None:
            doc["versions"] = cible = CommentedMap()
        for v, d in vs.items():
            if v not in VERSIONS:
                raise KeyError("versions : seules %s sont prises en charge" % ", ".join(VERSIONS))
            x = cible.get(v)
            if x is None:
                cible[v] = x = CommentedMap()
            for k in ("titre", "role"):
                if k in (d or {}):
                    t = " ".join(str(d[k] or "").split())
                    if t:
                        x[k] = t
                    else:
                        x.pop(k, None)
    if "claude" in champs:                    # les réglages de Claude : fusionnés, commentaires gardés
        c = champs.pop("claude") or {}
        cible = doc.get("claude")
        if cible is None:
            doc["claude"] = cible = CommentedMap()
        if "modele" in c:
            if c["modele"]:
                cible["modele"] = str(c["modele"])
            else:
                cible.pop("modele", None)
        if "file" in c:                          # la file d'attente : {auto, simultanees}
            fi = cible.get("file")
            if fi is None:
                cible["file"] = fi = CommentedMap()
            for k, v in (c.get("file") or {}).items():
                if k in ("auto", "creer_d_office"):
                    fi[k] = bool(v)
                elif k == "simultanees":
                    fi["simultanees"] = max(1, int(v))
                elif k in ("profondeur", "enfants"):    # les plafonds de la filiation (atelier/filiation.py)
                    fi[k] = max(0, min(9, int(v)))
                else:
                    raise KeyError("claude.file.%s" % k)
        for g, cles in CLAUDE_GENRES.items():
            for k, v in (c.get(g) or {}).items():
                if k not in cles:
                    raise KeyError("claude.%s.%s" % (g, k))
                sous = cible.get(g)
                if sous is None:
                    cible[g] = sous = CommentedMap()
                if v in (None, ""):
                    sous.pop(k, None)
                else:
                    sous[k] = str(v) if k == "modele" else max(0, int(v))
    for k, v in champs.items():
        v = v.strip() if isinstance(v, str) else v
        if v == "":
            v = None
        elif isinstance(v, str) and "\n" in v:
            v = LiteralScalarString(v + "\n")
        doc[k] = v
    p.write_text(rt_texte(y, doc), encoding="utf-8")
    return meta()


IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def ecrit_couverture(nom, donnees, version):
    ext = pathlib.Path(nom).suffix.lower()
    if ext not in IMAGES:
        raise KeyError("format d'image non pris en charge : %s" % ext)
    d = LIVRE / "media"
    d.mkdir(exist_ok=True)
    for ancien in d.glob("couverture.*"):
        ancien.unlink()
    (d / ("couverture" + ext)).write_bytes(donnees)
    return ecrit_meta({"couverture": "media/couverture" + ext}, version)


def fichier(chemin):
    """Un fichier du livre, par chemin relatif — jamais hors du dossier du livre."""
    p = (LIVRE / chemin).resolve()
    if LIVRE not in p.parents or not p.is_file():
        raise KeyError(chemin)
    return p


def heritage():
    """(dossier du dépôt d'héritage, sa config) — ou (None, {}) pour un livre sans passé."""
    h = meta().get("heritage") or {}
    if not h.get("depot"):
        return None, {}
    return (LIVRE / h["depot"]).resolve(), h


def affiche(p):
    """Un chemin lisible : relatif au dossier commun du livre, sinon absolu."""
    for base in (LIVRE.parent.parent, LIVRE.parent):
        try:
            return str(p.relative_to(base))
        except ValueError:
            pass
    return str(p)


def structure():
    s = yaml.safe_load((LIVRE / "structure.yaml").read_text(encoding="utf-8")) or {}
    s.setdefault("prefaces", [])
    s["parts"] = s.get("parts") or []
    return s


def dossier(slug):
    return LIVRE / "chapters" / slug


def chapitres():
    """Tous les chapitres dans l'ordre, numéro injecté depuis la position."""
    s = structure()
    out = [dict(c, numero=None, partie=None, partie_titre=None) for c in s.get("prefaces", [])]
    n = 0
    for p in s["parts"]:
        for c in p["chapters"]:
            n += 1
            out.append(dict(c, numero=n, partie=p["id"], partie_titre=p["title"]))
    for c in out:
        c["atelier"] = dossier(c["slug"]).is_dir()
        c["annotations"] = sum(1 for a in annotations(c["slug"]) if a.get("etat") == "ouverte") \
            if c["atelier"] else 0
        if c["atelier"]:
            from . import validation
            try:
                c["a_revalider"] = validation.etat(c["slug"])["a_revalider"]
            except Exception:                     # noqa: BLE001 — un état illisible ne bloque pas la liste
                c["a_revalider"] = None
    return out


RENVOI_SECTION = re.compile(r"\[sec:([\w-]+)\]")


def numerotation(brut, chapitre):
    """Les numéros de l'essai, calculés depuis la position — jamais stockés.
    Sections : chapitre.section.sous-section (1.2.3) ; paragraphes : §chapitre.rang (§1.23)."""
    from .essai import unites
    compteurs, sections, blocs, k = [0] * 8, {}, {}, 0
    for u in unites(brut):
        if u["kind"] == "titre" and u["id"] and u["id"] != "notes":
            n = u["niveau"]
            compteurs[n] += 1
            for j in range(n + 1, 8):
                compteurs[j] = 0
            sections[u["id"]] = {"num": ".".join([str(chapitre)] + [str(compteurs[j]) for j in range(2, n + 1)]),
                                 "titre": u["titre"]}
        elif u["kind"] == "bloc":
            k += 1
            blocs[u["id"]] = "§%s.%d" % (chapitre, k)
    return sections, blocs


# Les renvois à un autre chapitre, [chap:<slug>] : un vrai lien, et une forme qui se lit.
#   « au chapitre [chap:x] »          -> au chapitre 12              (le numéro seul, après « chapitre »)
#   « dans [chap:x] », « de [chap:x] » -> dans le chapitre 12, du chapitre 12
#   « …au fer [chap:x]. »              -> …au fer (→ chap. 12).      (un renvoi posé seul, comme une citation)
# Le titre du chapitre est au survol ; le lien mène au chapitre (dans le PDF, à sa page). Le texte source
# n'est pas touché : la forme se décide au rendu.
PREPOSITIONS = {"dans": "dans le chapitre", "de": "du chapitre", "à": "au chapitre", "par": "par le chapitre",
                "sur": "sur le chapitre", "avec": "avec le chapitre", "voir": "voir le chapitre", "après": "après le chapitre",
                "avant": "avant le chapitre", "depuis": "depuis le chapitre", "cf.": "cf. chapitre", "en": "au chapitre"}


def _titres_chapitres():
    s = structure()
    return {c["slug"]: c.get("title") or c["slug"] for c in (s.get("prefaces") or []) + [x for p in s["parts"] for x in p.get("chapters") or []]}


def renvois_chapitres(md, numeros, titres=None):
    if "[chap:" not in md:
        return md
    titres = titres if titres is not None else _titres_chapitres()

    def lien(slug, texte):
        if slug not in numeros:
            return '<span class="renvoi-mort" title="chapitre inconnu : %s">[chap:%s]</span>' % (slug, slug)
        return '<a class="renvoi-chap" href="#%s/essai/texte" data-chap="%s" title="%s">%s</a>' % (
            slug, slug, html_lib.escape(titres.get(slug, slug), quote=True), texte)

    def prep(m):                                   # « dans [chap:x] » -> « dans le chapitre [chap:x] »
        mot = m.group(1)
        dit = PREPOSITIONS[mot.lower()]
        return (dit[0].upper() + dit[1:] if mot[0].isupper() else dit) + m.group(2)
    md = re.sub(r"(?<![\w'’])(dans|de|à|par|sur|avec|voir|après|avant|depuis|cf\.|en)(\s+)(?=\[chap:)", prep, md, flags=re.I)
    # après « chapitre(s) » : le numéro seul (et « chapitres [chap:a] et [chap:b] »)
    md = re.sub(r"(chapitres?|chap\.)(\s+)((?:\[chap:[a-z0-9-]+\](?:\s*(?:,|et|à|-)\s*)?)+)",
                lambda m: m.group(1) + m.group(2) + RENVOI.sub(lambda r: lien(r.group(1), str(numeros.get(r.group(1), "?"))), m.group(3)),
                md, flags=re.I)
    # seul : un renvoi explicite, entre parenthèses
    return RENVOI.sub(lambda r: '<span class="renvoi-ptr">(→ %s)</span>' % lien(r.group(1), "chap. %s" % numeros.get(r.group(1), "?"))
                      if r.group(1) in numeros else lien(r.group(1), ""), md)


def rendu(md, numeros, structure=None):
    """Markdown -> HTML. Chaque ^id devient data-block sur son <p> ou son <li>.

    `structure` (essai) : (sections, blocs) numérotés — les intertitres reçoivent
    data-section et data-num, les paragraphes data-num, et [sec:id] devient un renvoi."""
    md = ANCRE.sub(lambda m: " §blk:%s§" % m.group(1), md)
    md = renvois_chapitres(md, numeros)
    sections, nums = structure or ({}, {})
    mode = meta().get("numerotation_essai") or "aucune"

    def renvoi(m):
        s = sections.get(m.group(1))
        if not s:
            return m.group(0)
        texte = s["num"] if mode != "aucune" else s["titre"]
        return '<a class="renvoi" href="#sec-%s" data-sec="%s">%s</a>' % (m.group(1), m.group(1), texte)
    md = RENVOI_SECTION.sub(renvoi, md)
    ext = ["footnotes", "tables"] + (["attr_list"] if structure else [])
    html = markdown.markdown(md, extensions=ext)
    html = re.sub(r"<(p|li)>((?:(?!</?\1>).)*?)" + JETON.pattern,
                  lambda m: '<%s data-block="%s"%s>%s%s' % (
                      m.group(1), m.group(3),
                      ' data-num="%s"' % nums[m.group(3)] if m.group(3) in nums else "",
                      m.group(2), m.group(4)),
                  html, flags=re.S)
    if structure:
        html = re.sub(r'<h([2-6]) id="([\w-]+)">',
                      lambda m: '<h%s id="sec-%s" data-section="%s"%s>' % (
                          m.group(1), m.group(2), m.group(2),
                          ' data-num="%s"' % sections[m.group(2)]["num"] if m.group(2) in sections else ""),
                      html)
    return CITATION.sub(r'<cite data-cle="\1">\1</cite>', html)


def texte(slug, version):
    if version not in VERSIONS:
        raise KeyError(version)
    tous = {c["slug"]: c for c in chapitres()}
    if slug not in tous:
        raise KeyError(slug)
    c = tous[slug]
    numeros = {s: x["numero"] for s, x in tous.items() if x["numero"]}
    p = dossier(slug) / (version + ".md")
    structure = None
    if p.exists():
        brut = p.read_text(encoding="utf-8")
        tete = "# %s\n\n*%s*\n\n---\n\n" % (c["title"], c.get("periode", "")) if c.get("periode") \
            else "# %s\n\n---\n\n" % c["title"]
        md = tete + brut
        if version == "essai":
            structure = numerotation(brut, c["numero"] if c["numero"] is not None else "P")
    else:
        depot, h = heritage()
        dossier_v = (h.get("chapitres") or {}).get(version)
        if not depot or not dossier_v:
            raise KeyError(slug)
        p = depot / dossier_v / (slug + ".md")
        if not p.exists():
            raise KeyError(slug)
        md = ENTETE.sub("", p.read_text(encoding="utf-8"), count=1)
    return {"slug": slug, "version": version, "atelier": c["atelier"],
            "html": rendu(md, numeros, structure), "origine": affiche(p),
            "numerotation": meta().get("numerotation_essai") or "aucune"}


def atelier(slug):
    """Brief, verrou (à plat, par id) et liens d'un chapitre migré."""
    d = dossier(slug)
    if not d.is_dir():
        raise KeyError(slug)
    lire = lambda n: yaml.safe_load((d / n).read_text(encoding="utf-8")) if (d / n).exists() else {}
    verrou = lire("verrou.yaml")
    assertions = {}
    for s in verrou.get("sections", []):
        for a in s["assertions"]:
            assertions[a["id"]] = dict(a, section=s["id"])
    links = lire("links.yaml") or {}
    links.setdefault("recit", {})
    links["recit"] = links["recit"] or {}
    # l'essai n'a pas de liens propres : ils vivent dans le verrou (assertion -> blocs),
    # on en dérive l'index inverse bloc -> assertions pour la lecture de l'essai
    essai = {}
    for i, a in assertions.items():
        for l in a.get("essai", []):
            e = essai.setdefault(l["bloc"], {"assertions": [], "appuis": {}})
            e["assertions"].append(i)
            e["appuis"][i] = l["appui"]
    links["essai"] = essai
    return {"brief": lire("brief.yaml"), "verrou": verrou, "assertions": assertions,
            "links": links, "bibliographie": lire("bibliographie.yaml").get("sources", []),
            "empreinte_brief": empreinte_brief(slug),
            "empreinte_verrou": hashlib.sha1((d / "verrou.yaml").read_bytes()).hexdigest()[:12]
            if (d / "verrou.yaml").exists() else ""}


@functools.lru_cache(maxsize=1)
def sources():
    """clé -> référence complète (HTML) : kb/sources/ s'il existe (la bibliographie du livre),
    sinon la bibliographie centrale d'héritage (« ### cle », référence, « fiches: … »)."""
    from . import sources as S
    if S.existe():
        return S.tout_html()
    depot, h = heritage()
    if not depot or not h.get("bibliographie"):
        return {}
    p = depot / h["bibliographie"]
    if not p.exists():
        return {}
    out = {}
    for bloc in re.split(r"^### ", p.read_text(encoding="utf-8"), flags=re.M)[1:]:
        lignes = [l.strip() for l in bloc.strip().splitlines() if l.strip()]
        corps = [l for l in lignes[1:] if not l.lower().startswith("fiches:")]
        if lignes and corps:
            html = markdown.markdown(" ".join(corps))
            out[lignes[0]] = re.sub(r"^<p>|</p>$", "", html.strip())
    return out


# ------------------------------------------------------------------ annotations

# chapters/<slug>/annotations.jsonl — un journal en ajout seul. Chaque ligne est un
# événement sur une annotation (création, modification, suppression) ; l'état courant
# s'obtient en rejouant le journal, la dernière valeur de chaque champ l'emporte.
# L'ancre est {version, bloc, citation, avant, apres} : le paragraphe par son ^id, la
# phrase par son texte et quelques caractères de contexte — jamais par un décalage.

TYPES_ANNOTATION = ("remarque", "question", "a-reecrire")
ETATS_ANNOTATION = ("ouverte", "resolue")
MODIFIABLES_ANNOTATION = ("texte", "type", "etat", "regles", "citation", "avant", "apres")   # l'ancre : pour rattacher une orpheline


def _journal(slug):
    d = dossier(slug)
    if not d.is_dir():
        raise KeyError(slug)
    return d / "annotations.jsonl"


def _maintenant():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def annotations(slug):
    p = _journal(slug)
    etat = {}
    if p.exists():
        for ligne in p.read_text(encoding="utf-8").splitlines():
            if not ligne.strip():
                continue
            e = json.loads(ligne)
            i = e.get("id")
            if e.get("supprime"):
                etat.pop(i, None)
            elif i in etat:
                etat[i].update({k: v for k, v in e.items() if k != "id"})
            else:
                etat[i] = e
    return list(etat.values())


def _ajoute(slug, evenement):
    with _journal(slug).open("a", encoding="utf-8") as f:
        f.write(json.dumps(evenement, ensure_ascii=False) + "\n")


def cree_annotation(slug, a):
    if a.get("version") not in VERSIONS or not a.get("bloc"):
        raise ValueError("une annotation vise une version (recit|essai) et un bloc")
    if a.get("type", "remarque") not in TYPES_ANNOTATION:
        raise ValueError("type inconnu : %s" % a.get("type"))
    e = {"id": "a-" + secrets.token_hex(3),
         "version": a["version"], "bloc": a["bloc"],
         "citation": a.get("citation") or "", "avant": a.get("avant") or "",
         "apres": a.get("apres") or "",
         "texte": (a.get("texte") or "").strip(), "type": a.get("type", "remarque"),
         "regles": [r for r in (a.get("regles") or []) if isinstance(r, str)],
         "etat": "ouverte", "auteur": a.get("auteur") or meta().get("auteur") or "auteur",
         "cree": _maintenant()}
    if isinstance(a.get("origine"), dict):              # posée par Claude : sa demande, la sorte de constat, sa gravité
        e["origine"] = {k: v for k, v in a["origine"].items() if v}
    _ajoute(slug, e)
    return e


def modifie_annotation(slug, ident, champs):
    if ident not in {a["id"] for a in annotations(slug)}:
        raise KeyError(ident)
    inconnus = set(champs) - set(MODIFIABLES_ANNOTATION)
    if inconnus:
        raise ValueError("champ non modifiable : %s" % ", ".join(sorted(inconnus)))
    if champs.get("type", "remarque") not in TYPES_ANNOTATION:
        raise ValueError("type inconnu : %s" % champs["type"])
    if champs.get("etat", "ouverte") not in ETATS_ANNOTATION:
        raise ValueError("état inconnu : %s" % champs["etat"])
    _ajoute(slug, dict(champs, id=ident, modifie=_maintenant()))
    return next(a for a in annotations(slug) if a["id"] == ident)


def supprime_annotation(slug, ident):
    if ident not in {a["id"] for a in annotations(slug)}:
        raise KeyError(ident)
    _ajoute(slug, {"id": ident, "supprime": True, "modifie": _maintenant()})


# ------------------------------------------------------------------ storyboard (brief.yaml)

# Le storyboard vit dans brief.yaml (beats). L'atelier en modifie les plans — lieu, temps,
# ambiance, attaque, chute, note, séquence, micro-récits — en gardant la mise en forme du
# fichier, et note chaque changement au journal. La réécriture relit brief.yaml à chaque
# demande : recadrer le storyboard, c'est recadrer ce que Claude recevra.

CHAMPS_PLAN = ("title", "lieu", "temps", "ambiance", "attaque", "chute", "note", "sequence", "ajouts")


def empreinte_brief(slug):
    return _version(dossier(slug) / "brief.yaml")


def modifie_plan(slug, pid, champs, recits, empreinte, motif=""):
    p = dossier(slug) / "brief.yaml"
    if _version(p) != empreinte:
        raise Conflit("brief.yaml a changé depuis son ouverture")
    inconnus = set(champs) - set(CHAMPS_PLAN)
    if inconnus:
        raise ValueError("champ de plan non modifiable : %s" % ", ".join(sorted(inconnus)))
    y = yaml_rt()
    doc = y.load(p.read_text(encoding="utf-8"))
    plan = next((b for b in doc.get("beats", []) if b.get("id") == pid), None)
    if plan is None:
        raise KeyError(pid)
    changes = []
    for k, v in champs.items():
        if k == "sequence":
            v = [s.strip() for s in (v if isinstance(v, list) else str(v).split("/")) if s.strip()]
        elif k == "ajouts":
            try:
                v = max(0, int(str(v).strip() or 0))
            except ValueError:
                raise ValueError("ajouts : un nombre de paragraphes hors verrou (0, 1, 2…)")
        else:
            v = (v or "").strip() or None
        avant = plan.get(k)
        if (list(avant) if isinstance(avant, list) else avant) != v:
            changes.append({"champ": k, "avant": list(avant) if isinstance(avant, list) else avant, "apres": v})
            if v is None:
                plan.pop(k, None)
            else:
                plan[k] = v
    for i, texte in (recits or {}).items():
        i = int(i)
        liste = plan.get("recits") or []
        if not 0 <= i < len(liste):
            raise ValueError("micro-récit %d hors du plan %s" % (i + 1, pid))
        texte = " ".join((texte or "").split())
        if texte and texte != liste[i]:
            changes.append({"champ": "recits[%d]" % i, "avant": liste[i], "apres": texte})
            liste[i] = texte
    if changes:
        p.write_text(rt_texte(y, doc), encoding="utf-8")
        quand = _maintenant()
        with (dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
            for c in changes:
                f.write(json.dumps(dict(c, date=quand, type="storyboard", plan=pid, motif=motif),
                                   ensure_ascii=False) + "\n")
    return {"changes": changes, "empreinte": empreinte_brief(slug)}


# La forme du storyboard, à la main : ajouter, retirer, déplacer un micro-récit ; ajouter ou retirer un plan.
# Une ligne, c'est un micro-récit et son paragraphe : les paragraphes du récit suivent leur micro-récit (leur
# rang, dans links.yaml, est mis à jour) ; retirer un micro-récit retire son paragraphe (texte au journal).

def forme_plan(slug, op, corps, empreinte, motif=""):
    p = dossier(slug) / "brief.yaml"
    if _version(p) != empreinte:
        raise Conflit("brief.yaml a changé depuis son ouverture")
    y = yaml_rt()
    doc = y.load(p.read_text(encoding="utf-8"))
    beats = doc.get("beats")
    if beats is None:
        from ruamel.yaml.comments import CommentedSeq
        beats = doc["beats"] = CommentedSeq()
    pid = str(corps.get("plan") or "")
    plan = next((b for b in beats if str(b.get("id")) == pid), None)
    if op.startswith("recit_") and plan is None:
        raise KeyError(pid)
    liste = list(plan.get("recits") or []) if plan is not None else []
    rang = int(corps.get("rang") or 0)                     # 0, 1… : la position dans le plan
    e = {"op": op, "plan": pid}
    if op == "recit_ajoute":
        texte = " ".join((corps.get("texte") or "").split())
        if not texte:
            raise ValueError("un micro-récit ne peut pas être vide")
        rang = max(0, min(rang, len(liste)))
        liste.insert(rang, texte)
        e.update(rang=rang, apres=texte)
    elif op == "recit_retire":
        if not 0 <= rang < len(liste):
            raise ValueError("micro-récit %d hors du plan %s" % (rang + 1, pid))
        from . import narration
        narration.retrait_permis(slug, pid, rang, corps.get("force"))
        e.update(rang=rang, avant=liste.pop(rang))
    elif op == "recit_deplace":
        vers = int(corps.get("vers"))
        if not (0 <= rang < len(liste) and 0 <= vers < len(liste)):
            raise ValueError("déplacement hors du plan %s" % pid)
        liste.insert(vers, liste.pop(rang))
        e.update(rang=rang, vers=vers)
    elif op == "plan_ajoute":
        pris = {str(b.get("id")) for b in beats}
        nid = next(c for c in (chr(65 + i) for i in range(26)) if c not in pris) if len(pris) < 26 else "P%d" % len(pris)
        from ruamel.yaml.comments import CommentedMap
        nouveau = CommentedMap()
        nouveau["id"] = nid
        nouveau["title"] = " ".join((corps.get("title") or "").split()) or "Nouveau plan"
        nouveau["recits"] = []
        apres = str(corps.get("apres") or "")
        i = next((k + 1 for k, b in enumerate(beats) if str(b.get("id")) == apres), len(beats))
        beats.insert(i, nouveau)
        e.update(plan=nid, apres=apres or None)
    elif op == "plan_retire":
        if plan is None:
            raise KeyError(pid)
        lp = dossier(slug) / "links.yaml"
        liens = (yaml.safe_load(lp.read_text(encoding="utf-8")) or {}).get("recit") or {} if lp.exists() else {}
        n = sum(1 for l in liens.values() if str((l or {}).get("plan")) == pid)
        if n:
            raise ValueError("le plan %s porte %d paragraphe(s) du récit : réécris ces paragraphes dans un autre plan d'abord" % (pid, n))
        beats.remove(plan)
        e.update(avant=plan.get("title"))
    else:
        raise ValueError("opération inconnue : %s" % op)
    if op.startswith("recit_"):
        plan["recits"] = liste
    p.write_text(rt_texte(y, doc), encoding="utf-8")
    if op.startswith("recit_"):                         # les paragraphes du récit suivent leur micro-récit
        from . import narration
        narration.suit_micro_recits(slug, pid, op, rang, corps.get("vers"), len(liste))
    with (dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(e, date=_maintenant(), type="storyboard", motif=motif), ensure_ascii=False) + "\n")
    return {"forme": e, "empreinte": empreinte_brief(slug)}


# L'en-tête du storyboard : ce qui est suivi, l'intention, la tenue, les contraintes, les mots
# interdits, les formules réservées. Mêmes garanties que pour un plan.
CHAMPS_BRIEF = ("suivi", "constraints", "interdits", "derogations", "fiches")
GROUPES_BRIEF = ("intent", "tenue")


def modifie_brief(slug, champs, empreinte, motif=""):
    p = dossier(slug) / "brief.yaml"
    if _version(p) != empreinte:
        raise Conflit("brief.yaml a changé depuis son ouverture")
    y = yaml_rt()
    doc = y.load(p.read_text(encoding="utf-8"))
    changes = []
    for cle, v in champs.items():
        groupe, _, sous = cle.partition(".")
        if not ((groupe in CHAMPS_BRIEF and not sous) or (groupe in GROUPES_BRIEF and sous)):
            raise ValueError("champ du brief non modifiable : %s" % cle)
        if groupe in ("constraints", "derogations"):
            v = [x.strip(" -") for x in (v if isinstance(v, list) else str(v).splitlines()) if x.strip(" -")]
        elif groupe == "interdits":
            v = [x.strip() for x in (v if isinstance(v, list) else str(v).split(",")) if x.strip()]
        elif groupe == "fiches":                 # des slugs de kb/fiches/, qui doivent exister
            v = [x.strip() for x in (v if isinstance(v, list) else re.split(r"[,\n]", str(v))) if x.strip()]
            inconnues = [x for x in v if not (LIVRE / "kb" / "fiches" / (x + ".md")).exists()]
            if inconnues:
                raise ValueError("fiche(s) inconnue(s) : %s" % ", ".join(inconnues))
        else:
            v = (v or "").strip()
            if "\n" in v:
                v = LiteralScalarString(v + "\n")
        cible = doc if not sous else doc.setdefault(groupe, {})
        k = groupe if not sous else sous
        avant = cible.get(k)
        avant_n = list(avant) if isinstance(avant, list) else (str(avant).strip() if avant is not None else None)
        apres_n = list(v) if isinstance(v, list) else str(v).strip()
        if avant_n != apres_n:
            changes.append({"champ": cle, "avant": avant_n, "apres": apres_n})
            cible[k] = v
    if changes:
        p.write_text(rt_texte(y, doc), encoding="utf-8")
        quand = _maintenant()
        with (dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
            for c in changes:
                f.write(json.dumps(dict(c, date=quand, type="brief", motif=motif), ensure_ascii=False) + "\n")
    return {"changes": changes, "empreinte": empreinte_brief(slug)}



def toutes_annotations():
    """Les annotations de tous les chapitres de l'atelier, avec leur chapitre."""
    out = []
    for c in chapitres():
        if c.get("atelier"):
            for a in annotations(c["slug"]):
                out.append(dict(a, chapitre=c["slug"], chapitre_titre=c["title"], chapitre_numero=c["numero"]))
    return out
