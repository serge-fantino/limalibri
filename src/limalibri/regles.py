# -*- coding: utf-8 -*-
"""Les garde-fous d'écriture d'un livre : regles/<version>.md.

Un fichier par version. Chaque section « ## … » est un élément :
  « ## R14 — Une formule ne sert qu'une fois »   une règle, d'identifiant R14 (stable)
  « ## La voix »                                 une section de contexte

Le fichier entier est donné à Claude pour toute réécriture de la version. Une règle peut
être citée par une annotation (par son identifiant). LimaLibri modifie une section à la
fois et réécrit le fichier en gardant le reste tel quel ; si le fichier a changé ailleurs
depuis sa lecture, il refuse plutôt que d'écraser.
"""
import re
import hashlib
import pathlib

from . import livre

MODELES = pathlib.Path(__file__).resolve().parents[2] / "modeles" / "regles"
ENTETE = re.compile(r"^---\n.*?\n---\n", re.S)
ID_REGLE = re.compile(r"^(R\d+[a-z]?) — (.+)$")


class Conflit(Exception):
    pass


def _fichier(version):
    return livre.LIVRE / "regles" / (version + ".md")


def _empreinte(p):
    return hashlib.sha1(p.read_bytes()).hexdigest()[:12] if p.exists() else ""


def _decoupe(texte):
    """(tête, [(titre de section, corps)]) — la tête va jusqu'au premier « ## »."""
    parts = re.split(r"^## (.+)$", texte, flags=re.M)
    return parts[0], [(parts[i].strip(), parts[i + 1].strip("\n")) for i in range(1, len(parts), 2)]


CONTROLE = re.compile(r"```controle\n(.*?)```", re.S)


def controles(corps):
    """Les contrôles mécaniques d'une section : ```controle libelle / motif / plafond / niveau```."""
    out = []
    for m in CONTROLE.finditer(corps):
        c = {}
        for ligne in m.group(1).splitlines():
            k, sep, v = ligne.partition(": ")
            if sep:
                c[k.strip()] = v.strip()
        if not c.get("motif"):
            continue
        pl = c.get("plafond", "0")
        c["plafond"] = None if pl in ("aucun", "", "none") else int(pl)
        c["niveau"] = c.get("niveau") or "bloquant"
        try:
            re.compile(c["motif"])
        except re.error as e:
            c["erreur"] = str(e)
        out.append(c)
    return out


def _element(titre, corps):
    m = ID_REGLE.match(titre)
    if m:
        return {"id": m.group(1), "type": "regle", "titre": m.group(2).strip(), "texte": corps.strip(),
                "controles": controles(corps)}
    ident = re.sub(r"[^a-z0-9]+", "-", titre.lower()).strip("-")[:40] or "section"
    return {"id": ident, "type": "section", "titre": titre, "texte": corps.strip(), "controles": controles(corps)}


def lit(version):
    p = _fichier(version)
    if not p.exists():
        return {"version": version, "empreinte": "", "fichier": None, "elements": []}
    tete, secs = _decoupe(p.read_text(encoding="utf-8"))
    corps_tete = ENTETE.sub("", tete, count=1)
    titre = re.search(r"^# (.+)$", corps_tete, re.M)
    intro = re.sub(r"^# .+$", "", corps_tete, count=1, flags=re.M).strip()
    return {"version": version, "empreinte": _empreinte(p), "fichier": str(p),
            "titre": titre.group(1) if titre else version, "intro": intro,
            "elements": [_element(t, c) for t, c in secs]}


def toutes():
    versions = list((livre.meta().get("versions") or {"recit": {}}).keys())
    return {v: lit(v) for v in versions}


def texte_pour_claude(version):
    p = _fichier(version)
    if not p.exists():
        return ""
    # les contrôles mécaniques (motifs) ne disent rien à Claude : ils sont retirés
    return CONTROLE.sub("", ENTETE.sub("", p.read_text(encoding="utf-8"), count=1)).strip()


def _ecrit(version, empreinte, transforme):
    p = _fichier(version)
    if _empreinte(p) != empreinte:
        raise Conflit("regles/%s.md a changé depuis son ouverture" % version)
    tete, secs = _decoupe(p.read_text(encoding="utf-8"))
    secs = transforme(secs)
    morceaux = [tete.rstrip("\n") + "\n"]
    for t, c in secs:
        morceaux.append("\n## %s\n\n%s\n" % (t, c.strip("\n")))
    p.write_text("".join(morceaux), encoding="utf-8")
    return lit(version)


def _titre_de(el):
    return "%s — %s" % (el["id"], el["titre"]) if el["type"] == "regle" else el["titre"]


def modifie(version, ident, titre, texte, empreinte):
    def t(secs):
        out, trouve = [], False
        for h, c in secs:
            e = _element(h, c)
            if e["id"] == ident:
                trouve = True
                e = dict(e, titre=(titre or e["titre"]).strip(), texte=texte.strip())
                out.append((_titre_de(e), e["texte"]))
            else:
                out.append((h, c))
        if not trouve:
            raise KeyError(ident)
        return out
    return _ecrit(version, empreinte, t)


def ajoute(version, titre, texte, empreinte):
    """Une règle nouvelle, au numéro suivant le plus grand ; placée après la dernière règle."""
    if not _fichier(version).exists():
        (_fichier(version).parent).mkdir(parents=True, exist_ok=True)
        _fichier(version).write_text("# Garde-fous d'écriture — %s\n" % version, encoding="utf-8")
        empreinte = _empreinte(_fichier(version))
    cree = {}

    def t(secs):
        els = [_element(h, c) for h, c in secs]
        nums = [int(re.match(r"R(\d+)", e["id"]).group(1)) for e in els if e["type"] == "regle"]
        ident = "R%d" % (max(nums, default=0) + 1)
        e = {"id": ident, "type": "regle", "titre": titre.strip(), "texte": (texte or titre).strip()}
        cree.update(e)
        derniere = max((i for i, x in enumerate(els) if x["type"] == "regle"), default=len(els) - 1)
        return secs[:derniere + 1] + [(_titre_de(e), e["texte"])] + secs[derniere + 1:]
    etat = _ecrit(version, empreinte, t)
    return dict(etat, cree=cree)


def supprime(version, ident, empreinte):
    def t(secs):
        out = [(h, c) for h, c in secs if _element(h, c)["id"] != ident]
        if len(out) == len(secs):
            raise KeyError(ident)
        return out
    return _ecrit(version, empreinte, t)


def initialise():
    """Un livre sans garde-fous reçoit le modèle de chaque version déclarée."""
    crees = []
    for v in (livre.meta().get("versions") or {"recit": {}}):
        p, m = _fichier(v), MODELES / (v + ".md")
        if not p.exists() and m.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(m.read_text(encoding="utf-8"), encoding="utf-8")
            crees.append("regles/%s.md" % v)
    return crees
