# -*- coding: utf-8 -*-
"""La bibliographie du livre : kb/sources/<cle>.yaml, une œuvre par fichier.

    cle: coale2024
    ref: Coale, T.H., Loconte, V. … « Nitrogen-fixing organelle in a marine alga ». *Science* 384 (2024).
    doi: 10.1126/science.adk1075        # lu sur une page, jamais de mémoire
    url:
    fiches: [nitroplaste, plaste]        # où l'œuvre est exploitée (les fiches en prose ne la citent pas par clé)
    statut: importee                     # voir STATUTS
    origine: base centrale de l'ancien dépôt (livre/bibliographie.md), migrée le 2026-09-27
    verification: {date, demande, verdict, resume}   # la dernière vérification retenue
    doublon_de:                          # si l'œuvre est la même qu'une autre clé
    doute:                               # une réserve sur l'identification
    notes:

La clé est l'identité de l'œuvre, stable : c'est elle que citent les notes de l'essai ([@cle])
et les fiches. Chaque changement va au journal de la base (kb/journal.jsonl).
"""
import os
import re
import json

import yaml

from . import livre

STATUTS = {
    "importee": "importée — venue de la base centrale, jamais vérifiée une à une",
    "a_verifier": "à vérifier — hors base, douteuse, ou relevée par Claude",
    "verifiee": "vérifiée — l'œuvre existe, la référence est juste",
    "corrigee": "corrigée — l'œuvre existe, la référence a été rectifiée",
    "introuvable": "introuvable — aucune trace fiable de l'œuvre",
    "mal_attribuee": "mal attribuée — l'œuvre existe, mais ne dit pas ce qu'on lui fait dire",
    "doublon": "doublon — la même œuvre qu'une autre clé",
}
CHAMPS = ("ref", "doi", "url", "fiches", "statut", "origine", "verification", "doublon_de", "doute", "notes")
_cache = {"cle": None, "val": None}


def dossier():
    return livre.LIVRE / "kb" / "sources"


def existe():
    return dossier().is_dir()


def _chemin(cle):
    if not re.fullmatch(r"[\w-]+", cle or ""):
        raise KeyError(cle)
    return dossier() / (cle + ".yaml")


def doi_de(ref):
    m = re.search(r"\b(10\.\d{4,9}/[^\s,;)»<]*[^\s,;)».<])", ref or "")
    return m.group(1) if m else None


def toutes():
    """cle -> œuvre, relues seulement si un fichier a changé (1 000 fichiers : on garde en mémoire)."""
    d = dossier()
    if not d.is_dir():
        return {}
    entrees = [e for e in os.scandir(d) if e.name.endswith(".yaml")]
    empreinte = (len(entrees), max((e.stat().st_mtime_ns for e in entrees), default=0))
    if _cache["cle"] == (str(d), empreinte):
        return _cache["val"]
    Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    out = {}
    for e in entrees:
        with open(e.path, encoding="utf-8") as f:
            x = yaml.load(f, Loader=Loader) or {}
        x["cle"] = str(x.get("cle") or e.name[:-5])
        out[x["cle"]] = x
    _cache.update(cle=(str(d), empreinte), val=out)
    return out


def lit(cle):
    p = _chemin(cle)
    if not p.exists():
        raise KeyError(cle)
    return toutes().get(cle) or yaml.safe_load(p.read_text(encoding="utf-8"))


def ecrit(cle, oeuvre, entete=None):
    """Écrit une œuvre (champs dans l'ordre de CHAMPS ; un champ vide est omis)."""
    d = {"cle": cle}
    for k in CHAMPS:
        v = oeuvre.get(k)
        if v not in (None, "", [], {}):
            d[k] = v
    dossier().mkdir(parents=True, exist_ok=True)
    texte = (entete or "") + yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=100)
    _chemin(cle).write_text(texte, encoding="utf-8")
    _cache["cle"] = None


def journal(e):
    with (livre.LIVRE / "kb" / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(e, date=livre._maintenant()), ensure_ascii=False) + "\n")


def modifie(cle, champs, motif=""):
    """Modifier une œuvre à la main : ref, doi, url, statut, doute, notes, doublon_de."""
    o = dict(lit(cle))
    avant = {}
    for k, v in champs.items():
        if k not in ("ref", "doi", "url", "statut", "doute", "notes", "doublon_de", "fiches"):
            raise ValueError("champ non modifiable : %s" % k)
        if k == "statut" and v not in STATUTS:
            raise ValueError("statut inconnu : %s" % v)
        if k == "doi" and v:
            v = re.sub(r"^(doi:?\s*|https?://(dx\.)?doi\.org/)", "", str(v).strip(), flags=re.I)
        v = v.strip() if isinstance(v, str) else v
        if o.get(k) != v:
            avant[k] = o.get(k)
            o[k] = v
    if avant:
        ecrit(cle, o)
        journal({"type": "source", "cle": cle, "avant": avant, "apres": {k: o.get(k) for k in avant}, "motif": motif})
    return lit(cle)


def ajoute(cle, oeuvre, motif=""):
    cle = (cle or "").strip()
    if not re.fullmatch(r"[a-z0-9][\w-]*", cle):
        raise ValueError("une clé : minuscules, chiffres, tirets (nom du premier auteur + année)")
    if _chemin(cle).exists():
        raise ValueError("la clé « %s » existe déjà" % cle)
    o = dict(oeuvre)
    o.setdefault("statut", "a_verifier")
    o["doi"] = o.get("doi") or doi_de(o.get("ref"))
    ecrit(cle, o)
    journal({"type": "source_ajoutee", "cle": cle, "origine": o.get("origine"), "motif": motif})
    return lit(cle)


def retire_fiche(slug):
    """Une fiche supprimée : elle sort des « fiches » des œuvres."""
    n = 0
    for cle, o in toutes().items():
        if slug in (o.get("fiches") or []):
            o = dict(o, fiches=[x for x in o["fiches"] if x != slug])
            ecrit(cle, o)
            n += 1
    return n


_cache_html = {"cle": None, "val": None}


def tout_html():
    """cle -> référence en HTML, pour toutes les œuvres (gardé en mémoire tant que rien ne change)."""
    import markdown
    T = toutes()
    if _cache_html["cle"] == _cache["cle"] and _cache_html["val"] is not None:
        return _cache_html["val"]
    val = {c: re.sub(r"^<p>|</p>$", "", markdown.markdown(o.get("ref") or c).strip()) for c, o in T.items()}
    _cache_html.update(cle=_cache["cle"], val=val)
    return val


def html(cle):
    """La référence en HTML (une ligne), pour les citations de l'atelier."""
    import markdown
    o = toutes().get(cle)
    if not o:
        return None
    return re.sub(r"^<p>|</p>$", "", markdown.markdown(o.get("ref") or cle).strip())
