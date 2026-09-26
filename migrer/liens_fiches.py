# -*- coding: utf-8 -*-
"""Pose les liens vers les fiches (kb/fiches/) d'un chapitre déjà migré.

    poetry run python3 migrer/liens_fiches.py la-mer le-texte     certains chapitres
    poetry run python3 migrer/liens_fiches.py                     tous les chapitres migrés
    poetry run python3 migrer/liens_fiches.py --sec               montre sans écrire

Deux liens, qui existaient dans l'ancien dépôt sans être repris :

  brief.yaml          fiches: [...]   les fiches du chapitre, depuis l'en-tête « fiches: » du
                                      chapitre de l'essai (livre/chapitres/<slug>.md). Les deux
                                      chapitres nés de la scission du 2026-09-19 (la-mer,
                                      l-inventaire) n'en ont pas : leur liste est celle du
                                      chapitre d'avant la scission, répartie selon les œuvres
                                      que citent leurs notes (DERIVEES ci-dessous).
  bibliographie.yaml  fiches: [...]   par œuvre, les fiches où elle est exploitée — la ligne
                                      « fiches: » de la bibliographie centrale.

Écriture en aller-retour (commentaires et mise en forme gardés). Un brief qui a déjà sa
liste n'est pas touché. Refuse une fiche qui n'existe pas dans kb/fiches/ (signalée).
"""
import os
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chapitre import SOURCE, CIBLE, ENTETE  # noqa: E402

os.environ.setdefault("ATELIER_LIVRE", str(CIBLE.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from atelier import livre  # noqa: E402

KB = CIBLE.parent / "kb" / "fiches"

# L'ancien chapitre 1 (« L'inventaire fermé ») listait : l-inventaire, la-lune, origine-de-l-eau,
# monde-archeen, l-hydrogene-qui-part, co2-et-temperature. Réparti par les œuvres citées
# (origine-de-l-eau : 27 œuvres de la-mer ; co2-et-temperature : 4 de l-inventaire…) et par
# les sections de l'essai (la Lune et la fuite de l'hydrogène sont dans la-mer).
DERIVEES = {
    "la-mer": ["origine-de-l-eau", "la-lune", "l-hydrogene-qui-part", "serre-humide"],
    "l-inventaire": ["l-inventaire", "co2-et-temperature", "monde-archeen", "l-hydrogene-qui-part"],
}


def fiches_du_chapitre(slug):
    if slug in DERIVEES:
        return DERIVEES[slug], "déduites (scission du 2026-09-19 : liste de l'ancien chapitre 1, répartie)"
    p = SOURCE / "livre" / "chapitres" / (slug + ".md")
    m = ENTETE.match(p.read_text(encoding="utf-8")) if p.exists() else None
    f = re.search(r"^fiches:\s*\[(.*)\]", m.group(0), re.M) if m else None
    if not f:
        return [], "aucune dans l'en-tête du chapitre"
    return [x.strip() for x in f.group(1).split(",") if x.strip()], "en-tête du chapitre de l'essai"


def fiches_des_oeuvres():
    txt = (SOURCE / "livre" / "bibliographie.md").read_text(encoding="utf-8")
    out = {}
    for bloc in re.split(r"^### ", txt, flags=re.M)[1:]:
        cle = bloc.strip().splitlines()[0].strip()
        m = re.search(r"^fiches:\s*(.*)$", bloc, re.M)
        if m and m.group(1).strip() not in ("", "—"):
            out[cle] = [x.strip() for x in m.group(1).split(",") if x.strip()]
    return out


def pose(slug, oeuvres, connues, ecrit):
    y = livre.yaml_rt()
    rapport = []
    # le brief
    pb = CIBLE / slug / "brief.yaml"
    brief = y.load(pb.read_text(encoding="utf-8"))
    liste, origine = fiches_du_chapitre(slug)
    hors = [f for f in liste if f not in connues]
    liste = [f for f in liste if f in connues]
    if brief.get("fiches"):
        rapport.append("brief : déjà %d fiche(s), gardé" % len(brief["fiches"]))
    else:
        pos = list(brief.keys()).index("chapter") + 1 if "chapter" in brief else 0
        brief.insert(pos, "fiches", liste, comment="fiches de kb/fiches/ : %s" % origine)
        rapport.append("brief : %d fiche(s) (%s)" % (len(liste), origine))
        if ecrit:
            pb.write_text(livre.rt_texte(y, brief), encoding="utf-8")
    if hors:
        rapport.append("hors kb (non posées) : " + ", ".join(hors))
    # la bibliographie
    pbib = CIBLE / slug / "bibliographie.yaml"
    if pbib.exists():
        bib = y.load(pbib.read_text(encoding="utf-8"))
        n = 0
        for e in bib.get("sources") or []:
            f = [x for x in oeuvres.get(str(e["cle"]), []) if x in connues]
            if f and list(e.get("fiches") or []) != f:
                e["fiches"] = f
                n += 1
        rapport.append("bibliographie : %d œuvre(s) reliée(s) à leurs fiches, sur %d" % (n, len(bib.get("sources") or [])))
        if ecrit and n:
            pbib.write_text(livre.rt_texte(y, bib), encoding="utf-8")
    return rapport


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    slugs = args or sorted(p.name for p in CIBLE.iterdir() if (p / "brief.yaml").exists())
    connues = {p.stem for p in KB.glob("*.md")}
    if not connues:
        sys.exit("REFUS — kb/fiches/ vide : lancer d'abord migrer/fiches.py")
    oeuvres = fiches_des_oeuvres()
    for s in slugs:
        print("== %s" % s)
        for l in pose(s, oeuvres, connues, "--sec" not in sys.argv):
            print("   " + l)


if __name__ == "__main__":
    main()
