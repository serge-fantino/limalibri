# -*- coding: utf-8 -*-
"""Migre la bibliographie centrale de l'ancien dépôt vers book-atelier/kb/sources/, une œuvre par
fichier, et y ajoute les œuvres que la base ignorait.

    poetry run python3 migrer/sources.py              écrit (les œuvres déjà migrées sont gardées)
    poetry run python3 migrer/sources.py --sec        compte, sans écrire
    poetry run python3 migrer/sources.py --ecraser    remplace aussi les œuvres déjà migrées
    ATELIER_LIVRE=../../UnMonde/book-atelier poetry run python3 migrer/sources.py
                                                      un livre sans ancien dépôt : ses chapitres et ses fiches

Trois provenances, dans cet ordre :
  1. livre/bibliographie.md (l'ancien dépôt) : chaque entrée « ### cle », sa référence (reprise
     telle quelle), son DOI s'il y figure, ses « fiches: ». Statut « importee » : la base a été
     fusionnée depuis les fiches, jamais vérifiée œuvre par œuvre.
  2. les bibliographies des chapitres de l'atelier : une œuvre « centrale: false » (citée par une
     note, absente de la base) entre avec sa référence, son doute, et le statut « a_verifier ».
  3. les sources des fiches écrites par l'atelier (« ## Sources ») : une œuvre absente entre avec
     sa référence et son extrait en note, statut « a_verifier ».

Garanties, vérifiées avant d'écrire : chaque clé citée [@cle] par un essai de l'atelier existe
à l'arrivée ; aucune clé n'est prise deux fois. Lecture seule côté ancien dépôt.
"""
import os
import re
import sys
import pathlib
import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chapitre import SOURCE, CIBLE, Refus  # noqa: E402

os.environ.setdefault("ATELIER_LIVRE", str(CIBLE.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from atelier import sources, kb, livre  # noqa: E402

import yaml  # noqa: E402

JOUR = datetime.date.today().isoformat()


def centrale():
    depot, h = livre.heritage()
    txt = (depot / h["bibliographie"]).read_text(encoding="utf-8")
    out = {}
    for bloc in re.split(r"^### ", txt, flags=re.M)[1:]:
        lignes = [l.strip() for l in bloc.strip().splitlines() if l.strip()]
        cle = lignes[0]
        ref = " ".join(l for l in lignes[1:] if not l.lower().startswith("fiches:"))
        m = re.search(r"^fiches:\s*(.*)$", bloc, re.M)
        fiches = [x.strip() for x in (m.group(1).split(",") if m else []) if x.strip() not in ("", "—")]
        if cle in out:
            raise Refus("clé en double dans la base centrale : %s" % cle)
        out[cle] = {"ref": ref, "doi": sources.doi_de(ref), "fiches": fiches, "statut": "importee",
                    "origine": "base centrale de l'ancien dépôt (livre/bibliographie.md), migrée le %s" % JOUR}
    return out


def des_chapitres(base):
    out = {}
    for c in livre.chapitres():
        p = livre.dossier(c["slug"]) / "bibliographie.yaml"
        if not c.get("atelier") or not p.exists():
            continue
        for e in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("sources") or []:
            cle = str(e["cle"])
            if cle in base or cle in out:
                continue
            out[cle] = {"ref": e.get("ref") or cle, "doi": e.get("doi") or sources.doi_de(e.get("ref")),
                        "fiches": list(e.get("fiches") or []), "statut": "a_verifier", "doute": e.get("doute"),
                        "origine": "citée par l'essai (chapitre %s, notes %s), absente de la base centrale" % (
                            c["slug"], ", ".join(e.get("notes") or []) or "?")}
    return out


def des_fiches(base):
    out = {}
    for s in kb._slugs():
        meta, corps = kb._lit(s)
        for cle, r in kb._refs_de_fiche(corps).items():
            if cle in base or cle in out:
                if cle in base and s not in base[cle]["fiches"]:
                    base[cle]["fiches"].append(s)
                continue
            out[cle] = {"ref": r["ref"], "doi": r["doi"], "url": r["url"], "fiches": [s], "statut": "a_verifier",
                        "origine": "source de la fiche %s (écrite par l'atelier)" % s,
                        "notes": ("extrait relevé%s : « %s »" % ("" if r["verifie"] else " (non vérifié)", r["extrait"]))
                        if r.get("extrait") else None}
    return out


def main():
    # un livre sans ancien dépôt (UnMonde…) : pas de base centrale, seulement ses chapitres et ses fiches
    depot, h = livre.heritage()
    base = centrale() if depot and h.get("bibliographie") else {}
    chap = des_chapitres(base)
    fich = des_fiches(dict(base, **chap))
    tout = dict(base, **chap, **fich)
    # chaque [@cle] d'un essai de l'atelier doit exister à l'arrivée
    manquent = set()
    for c in livre.chapitres():
        p = livre.dossier(c["slug"]) / "essai.md"
        if c.get("atelier") and p.exists():
            manquent |= set(re.findall(r"\[@([\w-]+)\]", p.read_text(encoding="utf-8"))) - set(tout)
    if manquent:
        sys.exit("REFUS — clés citées par l'essai, introuvables : " + ", ".join(sorted(manquent)))
    print("%d œuvres : %d de la base centrale (dont %d avec DOI), %d citées par l'essai hors base, "
          "%d des fiches écrites ici" % (len(tout), len(base), sum(1 for o in base.values() if o["doi"]), len(chap), len(fich)))
    if "--sec" in sys.argv:
        return
    d = sources.dossier()
    d.mkdir(parents=True, exist_ok=True)
    n = gardees = 0
    for cle, o in sorted(tout.items()):
        if (d / (cle + ".yaml")).exists() and "--ecraser" not in sys.argv:
            gardees += 1
            continue
        sources.ecrit(cle, o)
        n += 1
    sources.journal({"type": "migration_sources", "ecrites": n, "gardees": gardees})
    print("écrit : %d œuvre(s) dans %s%s" % (n, livre.affiche(d),
                                               " ; gardées (déjà migrées) : %d" % gardees if gardees else ""))


if __name__ == "__main__":
    main()
