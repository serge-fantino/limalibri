# -*- coding: utf-8 -*-
"""Où en est un chapitre, dans une version : un seul mot, lu dans ses fichiers.

    vide       ni synopsis, ni texte
    synopsis   le synopsis (ou la question) du brief, rien d'écrit
    brief      préparé pour l'écriture : le squelette de l'essai (sections « à écrire »), ou son
               verrou ; pour le récit, son storyboard
    brouillon  du texte (statut outline ou draft)
    relu       du texte, statut revised
    valide     du texte, statut locked

Le statut (outline, draft, revised, locked) est celui de structure.yaml : il vaut pour le
chapitre, le niveau le précise par version.
"""
import re

import yaml

from . import livre

NIVEAUX = ("vide", "synopsis", "brief", "brouillon", "relu", "valide")
PAR_STATUT = {"revised": "relu", "locked": "valide"}


def _yaml(p):
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {} if p.exists() else {}
    except yaml.YAMLError:
        return {}


def squelette(brut):
    """Vrai si l'essai n'a que des sections « à écrire »."""
    paras = [b for b in re.split(r"\n[ \t]*\n", brut) if b.strip() and not b.lstrip().startswith("#")]
    return bool(paras) and all(b.strip().startswith("*À écrire") for b in paras)


def niveau(c, version):
    d = livre.dossier(c["slug"])
    p = d / (version + ".md")
    brut = p.read_text(encoding="utf-8") if p.exists() else ""
    if brut.strip():
        if version == "essai" and squelette(brut):
            return "brief"
        return PAR_STATUT.get(c.get("status"), "brouillon")
    if not d.is_dir():                                # hors atelier : le texte d'origine, s'il existe
        depot, h = livre.heritage()
        dv = (h.get("chapitres") or {}).get(version)
        if depot and dv and (depot / dv / (c["slug"] + ".md")).exists():
            return PAR_STATUT.get(c.get("status"), "brouillon")
        return "vide"
    br = _yaml(d / "brief.yaml")
    if version == "recit" and br.get("beats"):
        return "brief"
    if version == "essai" and any(s.get("assertions") for s in _yaml(d / "verrou.yaml").get("sections") or []):
        return "brief"
    if br.get("synopsis") or br.get("question"):
        return "synopsis"
    return "vide"


def tous(c):
    return {v: niveau(c, v) for v in livre.VERSIONS}
