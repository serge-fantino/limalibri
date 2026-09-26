# -*- coding: utf-8 -*-
"""Importe la colonne vertébrale : ordre.md + en-têtes des chapitres -> structure.yaml.

    poetry run python3 migrer/structure.py            écrit UneVie/book-atelier/structure.yaml
    poetry run python3 migrer/structure.py --sec      affiche sans écrire

Lecture seule côté source : l'ancien dépôt (noosphereV2/Books/UneVie-book) n'est
jamais modifié. Le parseur d'ordre.md est celui de la source (outils/manifeste.py),
importé tel quel, pour qu'il n'y ait qu'une seule lecture du manifeste.

Aucun numéro n'est écrit : comme dans la source, le numéro est la position.
"""
import re
import sys
import json
import pathlib
import datetime
import yaml

AWEN = pathlib.Path(__file__).resolve().parents[3]
SOURCE = AWEN / "noosphereV2" / "Books" / "UneVie-book"
CIBLE = AWEN / "UneVie" / "book-atelier" / "structure.yaml"

sys.path.insert(0, str(SOURCE / "outils"))
import manifeste  # noqa: E402

ENTETE = re.compile(r"^---\n(.*?)\n---\n", re.S)
ROMAIN = re.compile(r"^([IVXLC]+)\.\s*(.*)$")


def entete(p):
    if not p.exists():
        return None
    # Les en-têtes de la source ne sont pas du YAML strict (« : » dans les valeurs) :
    # une clé par ligne, la valeur est tout ce qui suit le premier deux-points.
    m = ENTETE.match(p.read_text(encoding="utf-8"))
    d = {}
    for ligne in (m.group(1).splitlines() if m else []):
        k, sep, v = ligne.partition(":")
        if sep and k.strip() and not k.startswith((" ", "\t")):
            d[k.strip()] = v.strip().strip('"')
    return d


def statut(slug, relus):
    """Statut dérivé de l'état réel du récit — à affiner à la main ensuite.

    draft    : texte présent, pas de cadre
    revised  : cadre complet (verrou + storyboard + habillage)
    locked   : n'est jamais dérivé ; c'est une décision de l'auteur
    """
    cadre = SOURCE / "recit" / "cadre"
    complet = all((cadre / (slug + s)).exists()
                  for s in (".md", ".storyboard.md", ".habillage.md"))
    return "revised" if complet else "draft"


def chapitre(c, relus):
    livre = entete(SOURCE / "livre" / "chapitres" / (c.slug + ".md"))
    recit = entete(SOURCE / "recit" / "chapitres" / (c.slug + ".md"))
    tete = recit or livre or {}
    d = {"slug": c.slug, "title": tete.get("titre", c.slug)}
    if tete.get("periode"):
        d["periode"] = tete["periode"]
    d["versions"] = [v for v, e in (("recit", recit), ("essai", livre)) if e is not None]
    d["status"] = statut(c.slug, relus)
    if c.slug in relus:
        d["naif"] = relus[c.slug]["empreinte"]
    return d


def construit():
    m = manifeste.charge()
    rel = SOURCE / "recit" / "cadre" / "relecture.json"
    relus = json.loads(rel.read_text(encoding="utf-8")) if rel.exists() else {}

    parts, courante, prefaces = [], None, []
    for c in m.chapitres:
        if c.preface:
            if (SOURCE / "recit" / "chapitres" / (c.slug + ".md")).exists():
                prefaces.append(chapitre(c, relus))
            continue
        if courante is None or courante["_nom"] != c.partie:
            r = ROMAIN.match(c.partie or "")
            courante = {"_nom": c.partie,
                        "id": "p%d" % (len(parts) + 1),
                        "title": r.group(2) if r else (c.partie or "")}
            courante["chapters"] = []
            parts.append(courante)
        courante["chapters"].append(chapitre(c, relus))
    for p in parts:
        del p["_nom"]
    return {"prefaces": prefaces, "parts": parts}


def main():
    s = construit()
    tete = ("# Une vie — colonne vertébrale de l'atelier.\n"
            "# Importé de noosphereV2/Books/UneVie-book/ordre.md le %s.\n"
            "# Ordre = position dans ce fichier ; aucun numéro n'y est stocké.\n"
            "# Petit et déclaratif : des références, jamais du contenu.\n\n"
            % datetime.date.today().isoformat())
    texte = tete + yaml.safe_dump(s, allow_unicode=True, sort_keys=False, width=100)
    if "--sec" in sys.argv:
        print(texte)
        return
    CIBLE.write_text(texte, encoding="utf-8")
    n = sum(len(p["chapters"]) for p in s["parts"])
    print("%s : %d parties, %d chapitres, %d préface(s)"
          % (CIBLE.relative_to(AWEN), len(s["parts"]), n, len(s["prefaces"])))


if __name__ == "__main__":
    main()
