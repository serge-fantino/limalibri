# -*- coding: utf-8 -*-
"""La bibliographie d'un chapitre : les œuvres citées par les notes de son essai.

    poetry run python3 migrer/bibliographie.py la-mer analyse.json
    poetry run python3 migrer/bibliographie.py la-mer analyse.json --sec

L'analyse (lecture des notes, par modèle ou à la main) est une liste JSON d'objets
{cle, centrale, ref, doi, citation: "cle"|"clair", notes: [...], doute}. Le script la
vérifie contre la source avant d'écrire chapters/<slug>/bibliographie.yaml :

  · une entrée `centrale` existe bien dans livre/bibliographie.md (l'ancien dépôt),
    et sa référence est reprise de là, pas de l'analyse ;
  · chaque note citée existe dans essai.md ;
  · chaque [@cle] de l'essai figure dans la liste (rien d'oublié).

Un DOI n'est écrit que s'il est dans la note ou dans la base centrale ; il n'est pas
vérifié (l'API Crossref est bloquée par le proxy). Le lien doi.org en est dérivé.
Aucune écriture dans l'ancien dépôt : une œuvre `centrale: false` est à y ajouter.
"""
import re
import sys
import json
import datetime
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chapitre import CIBLE, SOURCE, dump, Refus  # noqa: E402

sys.path.insert(0, str(SOURCE / "livre" / "outils"))
import appareil  # noqa: E402

CHAMPS = ("cle", "ref", "doi", "centrale", "citation", "notes", "doute")


def construit(slug, analyse):
    essai = (CIBLE / slug / "essai.md").read_text(encoding="utf-8")
    notes = set(re.findall(r"^\[\^([^\]]+)\]:", essai, re.M))
    citees = set(re.findall(r"\[@([\w-]+)\]", essai))
    base = appareil.charge_bibliographie()

    out, vues = [], set()
    for e in analyse:
        cle = e["cle"]
        if cle in vues:
            raise Refus("clé en double dans l'analyse : %s" % cle)
        vues.add(cle)
        if e.get("centrale"):
            if cle not in base:
                raise Refus("%s : dite centrale, absente de livre/bibliographie.md" % cle)
            e["ref"] = base[cle]["ref"]                 # la base fait foi
        elif cle in base:
            raise Refus("%s : dite nouvelle, mais la clé existe déjà dans la base" % cle)
        for n in e.get("notes", []):
            if n not in notes:
                raise Refus("%s : note inconnue [^%s]" % (cle, n))
        if e.get("citation") not in ("cle", "clair"):
            raise Refus("%s : citation « %s » (attendu cle|clair)" % (cle, e.get("citation")))
        d = {k: e[k] for k in CHAMPS if e.get(k) not in (None, "", [])}
        d["centrale"] = bool(e.get("centrale"))
        if d.get("doi"):
            d["doi"] = re.sub(r"^(doi:?\s*|https?://(dx\.)?doi\.org/)", "", d["doi"], flags=re.I)
        out.append(d)
    oubliees = sorted(citees - vues)
    if oubliees:
        raise Refus("citées par l'essai mais absentes de l'analyse : " + ", ".join(oubliees))
    return sorted(out, key=lambda d: d["cle"])


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.exit(__doc__)
    slug, chemin = args
    analyse = json.loads(pathlib.Path(chemin).read_text(encoding="utf-8"))
    try:
        entrees = construit(slug, analyse)
    except Refus as e:
        sys.exit("REFUS — %s" % e)
    n = len(entrees)
    cen = sum(e["centrale"] for e in entrees)
    print("%d œuvres : %d dans la base centrale, %d à y ajouter, %d avec DOI, %d citées en clair"
          % (n, cen, n - cen, sum(1 for e in entrees if e.get("doi")),
             sum(1 for e in entrees if e["citation"] == "clair")))
    if "--sec" in sys.argv:
        return
    tete = ("# Bibliographie — %s. Les œuvres citées par les notes de l'essai.\n"
            "# Tirée le %s de livre/bibliographie.md (entrées « centrale: true », référence\n"
            "# reprise telle quelle) et d'une lecture des notes (%s).\n"
            "# centrale: false = absente de la base centrale, à y ajouter.\n"
            "# citation: clair = la note cite l'œuvre en toutes lettres, sans clé [@…].\n"
            "# doi : recopié de la note ou de la base, jamais vérifié (Crossref bloqué).\n\n"
            % (slug, datetime.date.today().isoformat(), pathlib.Path(chemin).name))
    p = CIBLE / slug / "bibliographie.yaml"
    p.write_text(dump(tete, {"chapter": slug, "sources": entrees}), encoding="utf-8")
    print("écrit :", p)


if __name__ == "__main__":
    main()
