# -*- coding: utf-8 -*-
"""Migre les fiches scientifiques (science/*.md de l'ancien dépôt) vers book-atelier/kb/fiches/.

    poetry run python3 migrer/fiches.py              toutes les fiches
    poetry run python3 migrer/fiches.py luca petm    certaines
    poetry run python3 migrer/fiches.py --sec        vérifie sans écrire
    poetry run python3 migrer/fiches.py --ecraser    remplace aussi les fiches déjà migrées

Une fiche est un dossier thématique, partagé entre chapitres : en-tête (type, sujet,
confiance), un titre « # », des sections « ## », « ### »… et des liens [[autre-fiche]] vers
les fiches voisines. La migration la recopie telle quelle, à une chose près : chaque
intertitre reçoit un identifiant stable {#id}, comme les intertitres de l'essai — pour
viser une section (une assertion, une note, un lien du wiki) qui survive à un changement
de titre.

Garanties, vérifiées avant toute écriture (le script refuse sinon) :
  · le texte, identifiants retirés, est identique à la source ;
  · les identifiants sont uniques dans la fiche ;
  · les [[liens]] visent des fiches qui existent (sinon : signalés, pas refusés).

Une fiche déjà migrée n'est pas remplacée sans --ecraser : elle se travaille dans
l'atelier. Lecture seule côté source.
"""
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chapitre import SOURCE, CIBLE, Refus  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from atelier.essai import ident_section  # noqa: E402

KB = CIBLE.parent / "kb" / "fiches"
INTERTITRE = re.compile(r"^(#{2,6})\s+(.*?)\s*$")
AVEC_ID = re.compile(r"\s*\{#[\w-]+\}\s*$")
LIEN = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
NUMERO = re.compile(r"^(\d+(\.\d+)*\.?|[a-z]\.|[IVX]+\.)\s+")


def identifie(texte):
    """Pose {#id} sur chaque intertitre (hors blocs de code). Rend (texte, n posés)."""
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


def migre(p, connues):
    source = p.read_text(encoding="utf-8")
    texte, n = identifie(source)
    retire = re.sub(r" \{#[\w-]+\}$", "", texte, flags=re.M)
    if retire != source:
        raise Refus("%s : le texte change hors identifiants" % p.name)
    ids = re.findall(r"\{#([\w-]+)\}", texte)
    if len(ids) != len(set(ids)):
        raise Refus("%s : identifiant de section en double" % p.name)
    morts = sorted({m.group(1).strip() for m in LIEN.finditer(texte)} - connues)
    return texte, n, morts


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src = SOURCE / "science"
    tous = sorted(src.glob("*.md"))
    connues = {p.stem for p in tous}
    choisies = [src / (a + ".md") for a in args] if args else tous
    for p in choisies:
        if not p.exists():
            sys.exit("REFUS — fiche inconnue : %s" % p.stem)
    sortie, total, gardees = {}, 0, []
    for p in choisies:
        try:
            texte, n, morts = migre(p, connues)
        except Refus as e:
            sys.exit("REFUS — %s" % e)
        total += n
        if morts:
            print("  %s : lien(s) vers une fiche inexistante : %s" % (p.stem, ", ".join(morts)))
        if (KB / p.name).exists() and "--ecraser" not in sys.argv:
            gardees.append(p.stem)
            continue
        sortie[p.name] = texte
    print("%d fiche(s), %d intertitre(s) identifié(s)" % (len(choisies), total))
    if "--sec" in sys.argv:
        return
    KB.mkdir(parents=True, exist_ok=True)
    for nom, texte in sortie.items():
        (KB / nom).write_text(texte, encoding="utf-8")
    print("écrit : %d fiche(s) dans %s" % (len(sortie), KB.relative_to(CIBLE.parents[2])))
    if gardees:
        print("gardées (déjà migrées ; --ecraser pour les remplacer) : " + ", ".join(gardees))


if __name__ == "__main__":
    main()
