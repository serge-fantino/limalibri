# -*- coding: utf-8 -*-
"""La correction directe d'un paragraphe (récit ou essai), et les versions du livre (git).

Corriger : on lit le Markdown d'un paragraphe (sans son ^id), on le modifie, on l'écrit.
Le paragraphe garde son identifiant ; tout le reste du fichier est intact. Si le paragraphe a
changé entre la lecture et l'écriture, on refuse. Chaque correction est notée au journal du
chapitre (avant, après, motif) — la trace fine, par paragraphe.

L'essai accepte aussi un paragraphe nouveau (après un autre) et la suppression d'un
paragraphe — refusée s'il étaie une assertion du verrou. Le récit aussi, rangé par plan
(atelier/narration.py : le nouveau paragraphe entre dans le plan de celui d'avant ; retirer un
paragraphe qui porte des assertions demande de le confirmer).

Les versions : un commit git des seuls fichiers du livre, quand l'auteur le demande — jamais
automatiquement, et jamais au-delà du dossier du livre.
"""
import re
import json
import secrets
import subprocess
import textwrap

from . import livre

ANCRE = re.compile(r"[ \t]\^([a-z0-9]+)[ \t]*$")
STRUCTURE_MD = re.compile(r"^\s*([-*+]\s|>|\||\d+[.)]\s|#)", re.M)


class Conflit(Exception):
    pass


def _fichier(slug, version):
    if version not in livre.VERSIONS:
        raise KeyError(version)
    p = livre.dossier(slug) / (version + ".md")
    if not p.exists():
        raise KeyError(slug)
    return p


def _morceaux(p):
    return re.split(r"\n[ \t]*\n", p.read_text(encoding="utf-8").strip("\n"))


def _trouve(morceaux, bloc):
    for i, m in enumerate(morceaux):
        a = ANCRE.search(m.rstrip())
        if a and a.group(1) == bloc:
            return i
    raise KeyError(bloc)


def _sans_ancre(m):
    return ANCRE.sub("", m.rstrip())


def _norm(s):
    return " ".join((s or "").split())


def _forme(texte, bloc):
    """Le texte du paragraphe, prêt à écrire : un paragraphe simple est replié à 100 colonnes ;
    une liste, une citation ou un tableau garde ses lignes."""
    texte = re.sub(r"\s*\^[a-z0-9]{4,}\s*$", "", texte.strip())
    if not STRUCTURE_MD.search(texte):
        texte = textwrap.fill(" ".join(texte.split()), width=100, break_long_words=False, break_on_hyphens=False)
    return texte + " ^" + bloc


def _journal(slug, e):
    with (livre.dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(e, date=livre._maintenant()), ensure_ascii=False) + "\n")


def lit_bloc(slug, version, bloc):
    ms = _morceaux(_fichier(slug, version))
    return {"version": version, "bloc": bloc, "texte": _sans_ancre(ms[_trouve(ms, bloc)])}


def modifie_bloc(slug, version, bloc, texte, avant, motif=""):
    p = _fichier(slug, version)
    ms = _morceaux(p)
    i = _trouve(ms, bloc)
    actuel = _sans_ancre(ms[i])
    if _norm(actuel) != _norm(avant):
        raise Conflit("le paragraphe ^%s a changé depuis son ouverture" % bloc)
    if not _norm(texte):
        raise ValueError("un paragraphe vide : le supprimer plutôt")
    if _norm(texte) == _norm(actuel):
        return lit_bloc(slug, version, bloc)
    ms[i] = _forme(texte, bloc)
    p.write_text("\n\n".join(ms) + "\n", encoding="utf-8")
    _journal(slug, {"type": "texte", "version": version, "bloc": bloc, "avant": actuel,
                    "apres": _sans_ancre(ms[i]), "source": "correction", "motif": motif})
    return lit_bloc(slug, version, bloc)


def _nouvel_id(slug):
    pris = set()
    for v in livre.VERSIONS:
        p = livre.dossier(slug) / (v + ".md")
        if p.exists():
            pris |= set(re.findall(r"\^([a-z0-9]+)\s*$", p.read_text(encoding="utf-8"), re.M))
    while True:
        i = secrets.token_hex(2)
        if i not in pris and not i.isdigit() and not re.fullmatch(r"\d+e\d+", i):   # « 5e56 » serait un nombre en YAML
            return i


def insere_bloc(slug, version, apres, texte, motif="", micro=""):
    if version == "recit":                       # le récit est rangé par plan : le nouveau suit celui d'avant dans son plan
        from . import narration
        G = narration._groupes(slug)
        pid, k = next(((p, r) for p, g in G.items() for r, x in narration._effectifs(g) if x[0] == apres), (None, None))
        if pid is None:
            raise KeyError(apres)
        r = narration.paragraphe(slug, "ajoute", {"plan": pid, "rang": k, "texte": texte or "…", "micro": micro, "motif": motif})
        return lit_bloc(slug, version, r["bloc"])
    p = _fichier(slug, version)
    ms = _morceaux(p)
    i = _trouve(ms, apres)
    bloc = _nouvel_id(slug)
    ms.insert(i + 1, _forme(texte or "…", bloc))
    p.write_text("\n\n".join(ms) + "\n", encoding="utf-8")
    _journal(slug, {"type": "texte", "version": version, "bloc": bloc, "avant": None,
                    "apres": texte, "apres_bloc": apres, "source": "correction", "motif": motif})
    return lit_bloc(slug, version, bloc)


def supprime_bloc(slug, version, bloc, avant, motif="", force=False):
    if version == "recit":
        from . import narration, reecriture
        try:
            narration.paragraphe(slug, "retire", {"bloc": bloc, "avant": avant, "force": force, "motif": motif})
        except reecriture.Conflit as e:
            raise Conflit(str(e))
        return {"supprime": bloc}
    at = livre.atelier(slug)
    portees = sorted(a for a, x in at["assertions"].items() if any(l["bloc"] == bloc for l in x.get("essai") or []))
    if portees:
        raise ValueError("ce paragraphe étaie %s dans le verrou : le garder, ou relier ces assertions ailleurs d'abord"
                         % ", ".join(portees))
    p = _fichier(slug, version)
    ms = _morceaux(p)
    i = _trouve(ms, bloc)
    actuel = _sans_ancre(ms[i])
    if _norm(actuel) != _norm(avant):
        raise Conflit("le paragraphe ^%s a changé depuis son ouverture" % bloc)
    del ms[i]
    p.write_text("\n\n".join(ms) + "\n", encoding="utf-8")
    _journal(slug, {"type": "texte", "version": version, "bloc": bloc, "avant": actuel, "apres": None,
                    "source": "correction", "motif": motif})
    return {"supprime": bloc}


# ------------------------------------------------------------------ versions (git)

def _git(*args, check=True):
    r = subprocess.run(["git", "-C", str(livre.LIVRE), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return r.stdout


def versions():
    """L'état du dossier du livre dans git : ce qui n'est pas encore versionné, et l'historique."""
    try:
        racine = _git("rev-parse", "--show-toplevel").strip()
    except RuntimeError:
        return {"git": False}
    changes = [l for l in _git("status", "--porcelain", "--", ".").splitlines() if l.strip()]
    hist = []
    for l in _git("log", "-n", "10", "--format=%h|%ad|%an|%s", "--date=format:%Y-%m-%d %H:%M", "--", ".").splitlines():
        h, d, a, s = (l.split("|", 3) + ["", "", "", ""])[:4]
        hist.append({"hash": h, "date": d, "auteur": a, "message": s})
    return {"git": True, "racine": racine, "branche": _git("branch", "--show-current").strip(),
            "changements": [{"etat": l[:2].strip(), "fichier": l[3:]} for l in changes], "historique": hist}


def enregistre(message):
    """Un commit des seuls fichiers du livre (le reste du dépôt n'est pas touché)."""
    message = " ".join((message or "").split())
    if not message:
        raise ValueError("un message décrit la version")
    _git("add", "-A", "--", ".")
    if not _git("diff", "--cached", "--name-only", "--", ".").strip():
        raise ValueError("rien à versionner")
    _git("commit", "-m", message, "--only", "--", ".")
    return versions()
