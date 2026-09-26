# -*- coding: utf-8 -*-
"""Pose dans le verrou les liens assertion -> essai, et les écarts.

    poetry run python3 migrer/liens_essai.py la-mer analyse.json      importe une analyse
    poetry run python3 migrer/liens_essai.py la-mer analyse.json --sec   montre sans écrire

L'analyse est un JSON { "<id assertion>": { "essai": [{"bloc", "appui", "note"?}],
"ecart": str|null, "type_ecart"?: str } } — produite par une passe de lecture (modèle
ou humain). Chaque assertion du verrou reçoit alors :

    essai:                    les blocs de l'essai qui l'étayent
    - bloc: e82a
      appui: direct           direct | partiel
      note: la-mer-echappement   si l'appui est dans la note appelée par le bloc
    ecart:                    si l'essai ne dit rien, ou autre chose
      type: absent            absent | valeur | nuance | contradiction
      texte: …

Refuse un bloc qui n'existe pas dans essai.md, un id d'assertion inconnu, un appui
hors vocabulaire. Une assertion marquée `valide: true` à la main n'est pas touchée.
"""
import re
import sys
import json
import datetime
import pathlib
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chapitre import CIBLE, ANCRE, blocs, dump, Refus  # noqa: E402

APPUIS = {"direct", "partiel"}
ECARTS = {"absent", "valeur", "nuance", "contradiction"}


def importe(slug, analyse, source):
    d = CIBLE / slug
    brut = (d / "verrou.yaml").read_text(encoding="utf-8")
    tete = "".join(l + "\n" for l in brut.splitlines() if l.startswith("#"))
    v = yaml.safe_load(brut)
    ids_essai = {m.group(1) for b, anc in blocs((d / "essai.md").read_text(encoding="utf-8"))
                 for m in [ANCRE.search(b.rstrip())] if anc and m}
    par_id = {a["id"]: a for s in v["sections"] for a in s["assertions"]}
    inconnus = sorted(set(analyse) - set(par_id))
    if inconnus:
        raise Refus("assertions inconnues du verrou : " + ", ".join(inconnus))
    stats = {"direct": 0, "partiel seul": 0, "sans appui": 0, "écarts": 0, "gardées": 0}
    for i, a in par_id.items():
        if a.get("valide"):
            stats["gardées"] += 1
            continue
        r = analyse.get(i)
        if r is None:
            continue
        liens = []
        for l in r.get("essai") or []:
            if l["bloc"] not in ids_essai:
                raise Refus("%s : bloc ^%s absent de essai.md" % (i, l["bloc"]))
            if l["appui"] not in APPUIS:
                raise Refus("%s : appui inconnu « %s »" % (i, l["appui"]))
            deja = next((x for x in liens if x["bloc"] == l["bloc"]), None)
            if deja:                      # même bloc, par le texte et par la note : un seul lien
                if l["appui"] == "direct":
                    deja["appui"] = "direct"
                if l.get("note") and not deja.get("note"):
                    deja["note"] = l["note"]
                continue
            liens.append({k: l[k] for k in ("bloc", "appui", "note") if l.get(k)})
        a.pop("essai", None)
        a.pop("ecart", None)
        if liens:
            a["essai"] = liens
        if r.get("ecart"):
            ty = r.get("type_ecart") or "absent"
            if ty not in ECARTS:
                raise Refus("%s : type d'écart inconnu « %s »" % (i, ty))
            a["ecart"] = {"type": ty, "texte": r["ecart"]}
            stats["écarts"] += 1
        if any(l["appui"] == "direct" for l in liens):
            stats["direct"] += 1
        elif liens:
            stats["partiel seul"] += 1
        else:
            stats["sans appui"] += 1
    v["liens_essai"] = {"source": source, "date": datetime.date.today().isoformat()}
    # l'ordre des clés : liens_essai avant les sections
    v = {k: v[k] for k in ["chapter", "preambule", "liens_essai", "sections"] if k in v}
    return dump(tete + "\n", v), stats


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.exit(__doc__)
    slug, chemin = args
    analyse = json.loads(pathlib.Path(chemin).read_text(encoding="utf-8"))
    try:
        texte, stats = importe(slug, analyse, "analyse par lecture (modèle), %s" % pathlib.Path(chemin).name)
    except Refus as e:
        sys.exit("REFUS — %s" % e)
    print("  ".join("%s %d" % kv for kv in stats.items()))
    if "--sec" not in sys.argv:
        (CIBLE / slug / "verrou.yaml").write_text(texte, encoding="utf-8")
        print("écrit :", (CIBLE / slug / "verrou.yaml"))


if __name__ == "__main__":
    main()
