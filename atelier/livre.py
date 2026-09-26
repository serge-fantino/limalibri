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
import hashlib
import pathlib
import functools
import yaml
import markdown
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

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
EDITABLES = ("titre", "sous_titre", "auteur", "langue", "synopsis", "quatrieme", "couverture")


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
    y = YAML()
    y.preserve_quotes = True
    y.width = 100
    doc = y.load(p.read_text(encoding="utf-8")) or {}
    for k, v in champs.items():
        v = v.strip() if isinstance(v, str) else v
        if v == "":
            v = None
        elif isinstance(v, str) and "\n" in v:
            v = LiteralScalarString(v + "\n")
        doc[k] = v
    s = io.StringIO()
    y.dump(doc, s)
    p.write_text(s.getvalue(), encoding="utf-8")
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
    return out


def rendu(md, numeros):
    """Markdown -> HTML. Chaque ^id devient data-block sur son <p> ou son <li>."""
    md = ANCRE.sub(lambda m: " §blk:%s§" % m.group(1), md)
    md = RENVOI.sub(lambda m: str(numeros.get(m.group(1), m.group(0))), md)
    html = markdown.markdown(md, extensions=["footnotes", "tables"])
    html = re.sub(r"<(p|li)>((?:(?!</?\1>).)*?)" + JETON.pattern,
                  lambda m: '<%s data-block="%s">%s%s' % (m.group(1), m.group(3), m.group(2), m.group(4)),
                  html, flags=re.S)
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
    if p.exists():
        brut = p.read_text(encoding="utf-8")
        tete = "# %s\n\n*%s*\n\n---\n\n" % (c["title"], c.get("periode", "")) if c.get("periode") \
            else "# %s\n\n---\n\n" % c["title"]
        md = tete + brut
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
            "html": rendu(md, numeros), "origine": affiche(p)}


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
    links = lire("links.yaml")
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
            "links": links, "bibliographie": lire("bibliographie.yaml").get("sources", [])}


@functools.lru_cache(maxsize=1)
def sources():
    """clé -> référence complète (HTML), depuis la bibliographie centrale d'héritage.

    Format : « ### cle », une ou plusieurs lignes de référence, « fiches: … ».
    Lecture seule, en attendant la migration vers kb/sources."""
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
