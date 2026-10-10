# -*- coding: utf-8 -*-
"""Marquer une version du livre dans git — seulement si le livre est dans un dépôt.

Le livre peut être son propre dépôt (book-atelier/.git) : ses tags sont « v1 », « v2 »… Ou vivre dans un
dépôt plus grand (un monorepo) : ses tags portent alors le nom du livre (« unmonde/v1 »), et le commit ne
prend QUE le dossier du livre — le reste du dépôt, et ce qui y est déjà indexé, n'est pas touché. Rien
n'est jamais poussé : le tag reste local.

Marquer :  git add -A -- <livre> ; git commit -m … -- <livre> (s'il y a du neuf) ; git tag -a <tag>.
Depuis un tag : les fichiers changés du livre (commités ou non) et les mots de chaque essai, alors et
maintenant.
"""
import re
import subprocess

from . import livre

NOM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,40}$")


def _git(*args, cwd=None, verifie=True):
    r = subprocess.run(["git", *args], cwd=str(cwd or livre.LIVRE), capture_output=True, text=True, timeout=60)
    if verifie and r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "git a échoué").strip()[:500])
    return r.stdout


def _racine():
    try:
        return _git("rev-parse", "--show-toplevel", verifie=True).strip() or None
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return None


def _chemin(racine):
    import os
    return os.path.relpath(str(livre.LIVRE.resolve()), racine)


def prefixe(racine=None):
    """« » si le livre est son dépôt ; sinon le nom de son dossier (« unmonde/ »)."""
    import pathlib
    racine = racine or _racine()
    if not racine or pathlib.Path(racine).resolve() == livre.LIVRE.resolve():
        return ""
    nom = livre.LIVRE.name if livre.LIVRE.name != "book-atelier" else livre.LIVRE.parent.name
    return re.sub(r"[^a-z0-9-]+", "-", nom.lower()).strip("-") + "/"


def etat():
    """{actif, racine, chemin, prefixe, modifie (fichiers du livre non commités), tags: [{tag, date, message}]}"""
    racine = _racine()
    if not racine:
        return {"actif": False}
    ch = _chemin(racine)
    pre = prefixe(racine)
    modifs = [l for l in _git("status", "--porcelain", "--untracked-files=all", "--", ch, cwd=racine).splitlines() if l.strip()]
    tags = []
    sortie = _git("for-each-ref", "--sort=-creatordate", "--format=%(refname:short)\t%(creatordate:iso-strict)\t%(contents:subject)",
                  "refs/tags/" + pre if pre else "refs/tags", cwd=racine)
    for l in sortie.splitlines():
        t, d, m = (l.split("\t") + ["", ""])[:3]
        if pre or "/" not in t:
            tags.append({"tag": t, "nom": t[len(pre):], "date": d, "message": m})
    return {"actif": True, "racine": racine, "chemin": ch, "prefixe": pre, "modifie": len(modifs), "tags": tags,
            "suivant": "v%d" % (1 + max([int(m.group(1)) for x in tags for m in [re.match(r"v(\d+)$", x["nom"])] if m] or [0]))}


def marque(nom, message):
    """Commiter le dossier du livre (s'il a changé) et le tagger. Rend {tag, commit, commite}."""
    racine = _racine()
    if not racine:
        raise ValueError("le livre n'est pas dans un dépôt git")
    nom = (nom or "").strip()
    if not NOM.match(nom):
        raise ValueError("nom de version : lettres, chiffres, . _ - (ex. v1)")
    tag = prefixe(racine) + nom
    if _git("tag", "--list", tag, cwd=racine).strip():
        raise ValueError("la version « %s » existe déjà" % tag)
    ch = _chemin(racine)
    message = " ".join((message or "").split()) or "version %s" % nom
    titre = livre.meta().get("titre") or livre.LIVRE.parent.name
    _git("add", "-A", "--", ch, cwd=racine)
    commite = bool(_git("diff", "--cached", "--name-only", "--", ch, cwd=racine).strip())
    if commite:                                    # seulement le livre : « -- chemin » laisse le reste de l'index
        _git("commit", "-m", "%s — %s" % (titre, message), "--", ch, cwd=racine)
    _git("tag", "-a", tag, "-m", "%s — %s" % (titre, message), cwd=racine)
    commit = _git("rev-parse", "--short", tag + "^{commit}", cwd=racine).strip()
    from . import kb
    try:
        kb.journal({"type": "version_marquee", "tag": tag, "commit": commit, "message": message})
    except Exception:                               # noqa: BLE001
        pass
    return {"tag": tag, "nom": nom, "commit": commit, "commite": commite, "date": livre._maintenant()}


def _mots(texte):
    texte = re.sub(r"\^[a-z0-9]+|\[\^[^\]]+\]|\[@[\w-]+\]|\{#[^}]+\}", "", texte or "")
    return len(re.findall(r"\w+", texte))


def depuis(tag, version="essai"):
    """Ce qui a changé dans le livre depuis un tag : fichiers (ajoutés, modifiés, supprimés), et les mots du
    texte de chaque chapitre, alors et maintenant."""
    racine = _racine()
    if not racine:
        raise ValueError("le livre n'est pas dans un dépôt git")
    if not _git("tag", "--list", tag, cwd=racine).strip():
        raise KeyError(tag)
    ch = _chemin(racine)
    F = {"ajoutes": 0, "modifies": 0, "supprimes": 0}
    for l in _git("diff", "--name-status", tag, "--", ch, cwd=racine).splitlines():
        k = l[:1]
        F["ajoutes" if k == "A" else "supprimes" if k == "D" else "modifies"] += 1
    F["ajoutes"] += len([l for l in _git("ls-files", "--others", "--exclude-standard", "--", ch, cwd=racine).splitlines() if l])
    import os
    C, total = [], {"avant": 0, "apres": 0}
    for c in livre.chapitres():
        p = livre.dossier(c["slug"]) / (version + ".md")
        rel = os.path.relpath(str(p.resolve()), racine)
        avant = subprocess.run(["git", "show", "%s:%s" % (tag, rel)], cwd=racine, capture_output=True, text=True).stdout
        apres = p.read_text(encoding="utf-8") if p.exists() else ""
        a, b = _mots(avant), _mots(apres)
        total["avant"] += a
        total["apres"] += b
        if avant != apres:
            C.append({"slug": c["slug"], "numero": c.get("numero"), "titre": c["title"], "avant": a, "apres": b})
    return {"tag": tag, "fichiers": F, "chapitres": C,
            "mots": total}
