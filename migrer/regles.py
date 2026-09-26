# -*- coding: utf-8 -*-
"""Extrait les garde-fous d'écriture d'Une Vie de son ancien dépôt vers regles/<version>.md.

    poetry run python3 migrer/regles.py          écrit UneVie/book-atelier/regles/{recit,essai}.md
    poetry run python3 migrer/regles.py --sec    affiche le compte sans écrire

Récit : recit/README.md (tout le guide sauf l'outillage — harnais, circuit —, les quinze règles
R1–R15 en sections propres) + recit/cadre/00-interdits.md (les tics plafonnés).
Essai : livre/revision-01.md §1 (les tics comptés, les six règles R1–R6).

Le texte des règles est repris tel quel ; seule la forme change : une section « ## Rn — titre »
par règle, pour qu'une règle soit adressable (annotations, réécriture, page du livre).
Refuse d'écraser un fichier existant : les règles se modifient ensuite dans l'atelier.
"""
import re
import sys
import datetime
import pathlib

AWEN = pathlib.Path(__file__).resolve().parents[3]
SOURCE = AWEN / "noosphereV2" / "Books" / "UneVie-book"
CIBLE = AWEN / "UneVie" / "book-atelier" / "regles"
ENTETE = re.compile(r"^---\n.*?\n---\n", re.S)
REGLE = re.compile(r"^\*\*(R\d+) — (.+?)\*\*\s*(.*)$", re.S)


def sections(texte, niveau="## "):
    parts = re.split(r"^" + re.escape(niveau) + r"(.+)$", texte, flags=re.M)
    return [(parts[i].strip(), parts[i + 1].strip()) for i in range(1, len(parts), 2)]


def regles_en_gras(bloc):
    """« **R1 — Titre.** texte… » (un paragraphe par règle, suite éventuelle) -> [(id, titre, texte)]."""
    out = []
    for para in re.split(r"\n\s*\n", bloc):
        m = REGLE.match(para.strip())
        if m:
            titre = m.group(2).strip().rstrip(".")
            out.append([m.group(1), titre, m.group(3).strip()])
        elif out:
            out[-1][2] += "\n\n" + para.strip()
    return out


def fichier(version, titre, source, morceaux):
    jour = datetime.date.today().isoformat()
    L = ["---", "version: %s" % version, "source: %s (extrait le %s)" % (source, jour), "---", "",
         "# Garde-fous d'écriture — %s" % titre, "",
         "Ces règles sont données telles quelles à Claude pour toute réécriture de cette version,",
         "et peuvent être citées par une annotation. Une règle est une section « ## Rn — titre » ;",
         "son identifiant est stable (on ajoute, on ne renumérote pas). Les autres sections",
         "(la voix, les interdits) sont du contexte.", ""]
    for h, corps in morceaux:
        L += ["## " + h, "", corps.strip(), ""]
    return "\n".join(L).rstrip() + "\n"


def recit():
    readme = ENTETE.sub("", (SOURCE / "recit" / "README.md").read_text(encoding="utf-8"), count=1)
    # tout le guide, dans son ordre, sauf ce qui décrit l'outillage (harnais, circuit) :
    # la découpe, le chapitre 21, ce que le récit ne prend pas… guident aussi l'écriture
    morceaux = []
    for nom, corps in sections(readme):
        if nom in ("Le harnais", "Le circuit"):
            continue
        if nom == "Les quinze règles":
            for rid, titre, texte in regles_en_gras(corps):
                morceaux.append(("%s — %s" % (rid, titre), texte))
        else:
            morceaux.append((nom, corps))
    interdits = ENTETE.sub("", (SOURCE / "recit" / "cadre" / "00-interdits.md").read_text(encoding="utf-8"), count=1)
    interdits = re.sub(r"^# .*\n+", "", interdits.strip())
    interdits = re.sub(r"^## ", "### ", interdits, flags=re.M)      # sous-sections du bloc
    morceaux.append(("Interdits permanents — les tics plafonnés", interdits))
    return fichier("recit", "récit", "noosphereV2/Books/UneVie-book/recit/README.md + recit/cadre/00-interdits.md",
                   morceaux)


def essai():
    rev = (SOURCE / "livre" / "revision-01.md").read_text(encoding="utf-8")
    s1 = dict(sections(rev)).get("1. Le style — les tics, comptés", "")
    sous = sections("\n" + s1, "### ")
    tete = s1.split("### ", 1)[0].strip()
    morceaux = [("Les tics, comptés", tete)]
    for nom, corps in sous:
        if nom.startswith("Les six règles"):
            for rid, titre, texte in regles_en_gras(corps):
                morceaux.append(("%s — %s" % (rid, titre), texte))
        elif nom.startswith("L'instrument"):
            morceaux.append(("L'instrument", corps))
    return fichier("essai", "essai", "noosphereV2/Books/UneVie-book/livre/revision-01.md §1", morceaux)


def main():
    CIBLE.mkdir(parents=True, exist_ok=True)
    for nom, contenu in (("recit.md", recit()), ("essai.md", essai())):
        n = len(re.findall(r"^## R\d+ — ", contenu, re.M))
        p = CIBLE / nom
        print("%s : %d règles, %d mots" % (nom, n, len(contenu.split())))
        if "--sec" in sys.argv:
            continue
        if p.exists():
            print("  existe déjà, non écrasé :", p)
            continue
        p.write_text(contenu, encoding="utf-8")
        print("  écrit :", p.relative_to(AWEN))


if __name__ == "__main__":
    main()
