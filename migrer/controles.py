# -*- coding: utf-8 -*-
"""Reporte les contrôles mécaniques de l'ancien harnais dans les garde-fous d'un livre.

    poetry run python3 migrer/controles.py              le livre par défaut (UneVie/book-atelier)
    poetry run python3 migrer/controles.py --sec        montre, sans écrire
    ATELIER_LIVRE=… poetry run python3 migrer/controles.py

Un garde-fou (regles/<version>.md, une section « ## R8 — … ») peut porter un ou plusieurs
contrôles, écrits en fin de section :

    ```controle
    libelle: adresse au lecteur
    motif: \\b(le lecteur|du lecteur|vous )\\b
    plafond: 0
    ```

Le motif est une expression régulière (insensible à la casse), cherchée phrase par phrase ;
le plafond est le nombre toléré par chapitre ; « niveau: avertissement » en fait un relevé qui
ne bloque pas (le filet de relecture). Les contrôles se lisent et se modifient comme le reste
du garde-fou.

Sources (ancien dépôt, lecture seule) : recit/outils/style.py (R4, R8, R11, R12, R13),
recit/outils/cadre.py (les interdits : R11, annonces, tics), recit/outils/relecture.py (le filet),
livre/outils/style.py (essai R1-R5, et les tics « méta » et « et c'est »). Une section qui porte
déjà un contrôle n'en reçoit pas d'autre (rejouer le script ne duplique rien).
"""
import os
import re
import sys
import pathlib
import importlib.util

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chapitre import SOURCE, CIBLE  # noqa: E402

os.environ.setdefault("ATELIER_LIVRE", str(CIBLE.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from atelier import livre  # noqa: E402


def _module(nom, chemin):
    sys.path.insert(0, str(SOURCE / "outils"))
    spec = importlib.util.spec_from_file_location(nom, SOURCE / chemin)
    m = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, ["x", "--resume"]
    try:
        spec.loader.exec_module(m)
    finally:
        sys.argv = argv
    return m


def bloc(libelle, motif, plafond=0, niveau=None):
    L = ["```controle", "libelle: %s" % libelle, "motif: %s" % motif]
    L.append("plafond: %s" % plafond if plafond is not None else "plafond: aucun")
    if niveau:
        L.append("niveau: %s" % niveau)
    return "\n".join(L + ["```"])


def plan():
    """{version: {titre de section (début) : [blocs]}}, et les sections à créer."""
    style_r = _module("style_r", "recit/outils/style.py").REGLES
    style_e = _module("style_e", "livre/outils/style.py").REGLES
    filet = _module("filet", "recit/outils/relecture.py").REGLES
    bannis = _module("cadre", "recit/outils/cadre.py").BANNIS_GLOBAUX
    recit, essai = {}, {}
    for cle, lib, motif, plafond in style_r:
        recit.setdefault(cle + " —", []).append(bloc(lib, motif, plafond))
    for motif, lib in bannis:
        if lib.startswith("R11"):
            recit.setdefault("R11 —", []).append(bloc(lib, motif, 0))
        else:
            recit.setdefault("Interdits permanents", []).append(bloc(lib, motif, 0))
    recit["Le filet de relecture"] = [bloc(lib, motif, None, "avertissement") for cle, lib, motif in filet]
    for cle, lib, motif, plafond in style_e:
        if cle in ("R1", "R2", "R3", "R4", "R5"):
            essai.setdefault(cle + " —", []).append(bloc(lib, motif, plafond))
        else:                                     # R6 (méta sur le livre), R7 (« et c'est ») : des tics comptés
            essai.setdefault("Les tics, comptés", []).append(bloc(lib, motif, plafond))
    return {"recit": recit, "essai": essai}


FILET = """## Le filet de relecture

Des heuristiques, pas des règles : les endroits où un lecteur risque de devoir deviner
(pronom sans référent, ellipse, nombre sans unité, absence annoncée). Faux positifs assumés —
chaque relevé se juge ; aucun ne bloque la validation. Le vrai contrôle reste la lecture naïve.
"""


def applique(version, P, ecrit):
    p = livre.LIVRE / "regles" / (version + ".md")
    if not p.exists():
        return "regles/%s.md absent" % version
    texte = p.read_text(encoding="utf-8")
    if "Le filet de relecture" in P and "## Le filet de relecture" not in texte:
        texte = texte.rstrip("\n") + "\n\n" + FILET
    parts = re.split(r"^(## .+)$", texte, flags=re.M)
    faits = []
    for i in range(1, len(parts), 2):
        titre = parts[i][3:].strip()
        cle = next((k for k in P if titre.startswith(k)), None)
        if not cle or "```controle" in parts[i + 1]:
            continue
        corps = parts[i + 1].rstrip("\n")
        parts[i + 1] = corps + "\n\n" + "\n\n".join(P[cle]) + "\n\n"
        faits.append("%s (%d)" % (titre[:40], len(P[cle])))
    if ecrit and faits:
        p.write_text("".join(parts).rstrip("\n") + "\n", encoding="utf-8")
    manquent = [k for k in P if not any(parts[i][3:].strip().startswith(k) for i in range(1, len(parts), 2))]
    return "%s : %s%s" % (version, ", ".join(faits) or "rien à ajouter",
                          " — sections introuvables : " + ", ".join(manquent) if manquent else "")


def main():
    P = plan()
    for v in ("recit", "essai"):
        print(applique(v, P[v], "--sec" not in sys.argv))


if __name__ == "__main__":
    main()
