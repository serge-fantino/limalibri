# -*- coding: utf-8 -*-
"""L'état de validation : ce qui a changé depuis la dernière validation, paragraphe par paragraphe.

chapters/<slug>/validations.json garde, pour chaque version, l'empreinte de chaque paragraphe
au moment où il a été validé (par la boucle de validation, ou marqué validé par l'auteur).
L'état d'un paragraphe se calcule en comparant son texte d'aujourd'hui à cette empreinte :

    valide     le texte n'a pas changé depuis sa validation
    modifie    le texte a changé (correction, réécriture retenue, vérification appliquée…)
    nouveau    le paragraphe n'existait pas à la dernière validation
    cadre      le texte n'a pas changé, mais son cadre oui : son plan du storyboard, ou une
               assertion qu'il porte (verrou), a été modifié depuis — d'après le journal

La référence de départ est l'état du chapitre à sa migration dans l'atelier (le dernier état
validé par le cycle de l'ancien dépôt), relu dans git ; faute de git, l'état présent.
"""
import re
import json
import hashlib
import subprocess

from . import livre

ANCRE = re.compile(r"[ \t]\^([a-z0-9]+)[ \t]*$")


def _empreinte(texte):
    return hashlib.sha1(" ".join(texte.split()).encode()).hexdigest()[:12]


def _blocs(texte):
    out = {}
    for m in re.split(r"\n[ \t]*\n", texte.strip("\n")):
        a = ANCRE.search(m.rstrip())
        if a:
            out[a.group(1)] = _empreinte(ANCRE.sub("", m.rstrip()))
    return out


def _fichier(slug):
    return livre.dossier(slug) / "validations.json"


def _git(*args):
    r = subprocess.run(["git", "-C", str(livre.LIVRE), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _reference_initiale(slug):
    """L'état à la migration : le premier commit qui contient le chapitre, s'il y en a un."""
    ref = {"par": "migration", "versions": {}}
    for v in livre.VERSIONS:
        p = livre.dossier(slug) / (v + ".md")
        if not p.exists():
            continue
        rel = str(p.relative_to(livre.LIVRE))
        commits = (_git("log", "--diff-filter=A", "--format=%h|%aI", "--", rel) or "").split()
        texte, date = None, None
        if commits:
            h, date = commits[-1].split("|", 1)
            texte = _git("show", "%s:./%s" % (h, rel))
            ref["commit"] = h
        if texte is None:
            texte, date = p.read_text(encoding="utf-8"), livre._maintenant()
        ref["date"] = date
        ref["versions"][v] = {b: {"empreinte": e, "date": date, "par": "migration"} for b, e in _blocs(texte).items()}
    return ref


def reference(slug):
    f = _fichier(slug)
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    ref = _reference_initiale(slug)
    f.write_text(json.dumps(ref, ensure_ascii=False, indent=1), encoding="utf-8")
    return ref


def _cadres_modifies(slug, depuis):
    """Plans (récit) et assertions (verrou) dont le cadre a changé depuis une date, d'après le journal."""
    plans, assertions, brief = set(), set(), False
    j = livre.dossier(slug) / "journal.jsonl"
    if not j.exists():
        return plans, assertions, brief
    for ligne in j.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(ligne)
        except ValueError:
            continue
        if (e.get("date") or "") <= (depuis or ""):
            continue
        if e.get("type") == "storyboard" and e.get("plan"):
            plans.add(e["plan"])
        elif e.get("type") == "brief":
            brief = True
        elif e.get("type") == "verrou" and e.get("assertion"):
            assertions.add(e["assertion"])
    return plans, assertions, brief


def etat(slug):
    """L'état de chaque paragraphe de chaque version, et le résumé du chapitre."""
    ref = reference(slug)
    at = livre.atelier(slug)
    out = {"base": {k: ref.get(k) for k in ("par", "date", "commit")}, "versions": {}, "resume": {}}
    for v in livre.VERSIONS:
        p = livre.dossier(slug) / (v + ".md")
        if not p.exists():
            continue
        refv = ref.get("versions", {}).get(v, {})
        dates = [x["date"] for x in refv.values()] or [ref.get("date") or ""]
        plans, assertions, brief = _cadres_modifies(slug, min(dates))
        liens = at["links"].get(v, {})
        etats = {}
        for b, e in _blocs(p.read_text(encoding="utf-8")).items():
            r = refv.get(b)
            if not r:
                etats[b] = {"etat": "nouveau"}
            elif r["empreinte"] != e:
                etats[b] = {"etat": "modifie", "depuis": r["date"]}
            else:
                l = liens.get(b, {})
                raisons = []
                if v == "recit" and l.get("plan") in plans:
                    raisons.append("plan %s du storyboard" % l["plan"])
                touchees = sorted(set(l.get("assertions") or []) & assertions)
                if touchees:
                    raisons.append("verrou %s" % ", ".join(touchees))
                etats[b] = {"etat": "cadre", "raisons": raisons} if raisons else {"etat": "valide", "depuis": r["date"]}
        out["versions"][v] = etats
        compte = {}
        for x in etats.values():
            compte[x["etat"]] = compte.get(x["etat"], 0) + 1
        out["resume"][v] = dict(compte, brief_modifie=brief if v == "recit" else False)
    out["a_revalider"] = sum(n for r in out["resume"].values() for k, n in r.items()
                             if k in ("modifie", "nouveau", "cadre"))
    return out


def marque_valide(slug, version, blocs=None, par="auteur"):
    """Prend l'état présent comme référence (pour une version, ou certains paragraphes)."""
    ref = reference(slug)
    p = livre.dossier(slug) / (version + ".md")
    presents = _blocs(p.read_text(encoding="utf-8"))
    refv = ref.setdefault("versions", {}).setdefault(version, {})
    quand = livre._maintenant()
    for b, e in presents.items():
        if blocs is None or b in blocs:
            refv[b] = {"empreinte": e, "date": quand, "par": par}
    if blocs is None:                              # une version entière : les disparus sortent
        for b in list(refv):
            if b not in presents:
                del refv[b]
    _fichier(slug).write_text(json.dumps(ref, ensure_ascii=False, indent=1), encoding="utf-8")
    with (livre.dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "validation", "version": version, "blocs": blocs or "tous", "par": par,
                            "date": quand}, ensure_ascii=False) + "\n")
    return etat(slug)
