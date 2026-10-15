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
CHAMPS = ("ref", "doi", "url", "fiches", "statut", "origine", "verification", "verifications", "doublon_de", "doute",
          "notes", "documents", "citations")
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
    """La référence en HTML (une ligne), pour les citations de LimaLibri."""
    import markdown
    o = toutes().get(cle)
    if not o:
        return None
    return re.sub(r"^<p>|</p>$", "", markdown.markdown(o.get("ref") or cle).strip())


# ------------------------------------------------------------------ les documents : le texte original

# kb/documents/<cle>/ : les fichiers (pdf, html, txt) et, pour chacun, son texte extrait
# (<nom>.texte.txt, par pdftotext, pages séparées par un saut de page). Leur description est
# dans l'œuvre : documents: [{fichier, source, date, taille, pages, type, par}].
TYPES_DOC = {".pdf": "application/pdf", ".html": "text/html", ".htm": "text/html", ".txt": "text/plain", ".xml": "application/xml",
             ".epub": "application/epub+zip"}
TAILLE_MAX = 80 * 1024 * 1024


def dossier_documents(cle):
    _chemin(cle)
    return livre.LIVRE / "kb" / "documents" / cle


def _nom_fichier(nom):
    import unicodedata
    base, ext = os.path.splitext(os.path.basename(nom or "document"))
    base = unicodedata.normalize("NFD", base)
    base = re.sub(r"[^\w.-]+", "-", "".join(c for c in base if unicodedata.category(c) != "Mn")).strip("-")[:80]
    return (base or "document") + ext.lower()


def _texte_de(p):
    """Le texte d'un document : pdftotext pour un PDF (pages séparées par \\f), le texte brut sinon."""
    import subprocess
    import shutil
    if p.suffix.lower() == ".pdf":
        exe = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
        if not os.path.exists(exe):
            return None
        r = subprocess.run([exe, str(p), "-"], capture_output=True, timeout=120)     # l'ordre de lecture (colonnes à la suite)
        return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else None
    if p.suffix.lower() in (".html", ".htm", ".xml"):
        t = p.read_text(encoding="utf-8", errors="replace")
        t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", t)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
    if p.suffix.lower() == ".txt":
        return p.read_text(encoding="utf-8", errors="replace")
    return None


def ajoute_document(cle, nom, donnees, source, par="auteur"):
    """Range un document de l'œuvre, en extrait le texte, et le décrit dans l'œuvre."""
    import hashlib
    import datetime
    if len(donnees) > TAILLE_MAX:
        raise ValueError("document trop gros (%d Mo, plafond %d)" % (len(donnees) // 2 ** 20, TAILLE_MAX // 2 ** 20))
    nom = _nom_fichier(nom)
    ext = os.path.splitext(nom)[1]
    if ext not in TYPES_DOC:
        raise ValueError("type de document non pris en charge : %s (pdf, html, xml, txt, epub)" % (ext or "?"))
    if ext == ".pdf" and not donnees.startswith(b"%PDF"):
        raise ValueError("ce fichier ne commence pas comme un PDF (page d'accueil, mur payant ?)")
    o = dict(lit(cle))
    d = dossier_documents(cle)
    d.mkdir(parents=True, exist_ok=True)
    p = d / nom
    n = 2
    while p.exists():
        p = d / ("%s-%d%s" % (os.path.splitext(nom)[0], n, ext))
        n += 1
    p.write_bytes(donnees)
    texte = _texte_de(p)
    if texte:
        (d / (p.name + ".texte.txt")).write_text(texte, encoding="utf-8")
    e = {"fichier": p.name, "source": source, "date": datetime.date.today().isoformat(), "taille": len(donnees),
         "sha256": hashlib.sha256(donnees).hexdigest()[:16], "type": TYPES_DOC[ext], "par": par,
         "pages": texte.count("\f") + 1 if texte and ext == ".pdf" else None, "texte": bool(texte)}
    o["documents"] = list(o.get("documents") or []) + [{k: v for k, v in e.items() if v is not None}]
    ecrit(cle, o)
    journal({"type": "document_ajoute", "cle": cle, "fichier": p.name, "source": source, "par": par})
    reverifie_citations(cle)
    return lit(cle)


def supprime_document(cle, fichier):
    o = dict(lit(cle))
    docs = [x for x in o.get("documents") or [] if x.get("fichier") != fichier]
    if len(docs) == len(o.get("documents") or []):
        raise KeyError(fichier)
    d = dossier_documents(cle)
    for f in (d / fichier, d / (fichier + ".texte.txt")):
        if f.exists():
            f.unlink()
    o["documents"] = docs
    ecrit(cle, o)
    journal({"type": "document_retire", "cle": cle, "fichier": fichier})
    reverifie_citations(cle)
    return lit(cle)


def textes(cle):
    """[(fichier, [texte de chaque page])] pour les documents de l'œuvre qui ont un texte."""
    out = []
    d = livre.LIVRE / "kb" / "documents" / cle
    for x in (toutes().get(cle) or {}).get("documents") or []:
        p = d / (x["fichier"] + ".texte.txt")
        if p.exists():
            out.append((x["fichier"], p.read_text(encoding="utf-8", errors="replace").split("\f")))
    return out


# ------------------------------------------------------------------ les citations : ce qu'on cite mot pour mot

# citations: [{texte, page, usage, origine, date, controle: {etat: trouvee|absente|sans_document, fichier, page}}]
def _plat(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ﬁ", "fi").replace("ﬂ", "fl")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def controle(cle, texte):
    """Une citation est-elle dans un document de l'œuvre ? Cherche mot pour mot (ponctuation, casse,
    accents et césures ignorés), puis sur un début de phrase suffisant."""
    T = textes(cle)
    if not T:
        return {"etat": "sans_document"}
    cible = _plat(texte)
    if len(cible) < 12:
        return {"etat": "trop_courte"}
    for f, pages in T:
        for i, pg in enumerate(pages):
            plat = _plat(re.sub(r"(\w)-\n(\w)", r"\1\2", pg))          # la césure de fin de ligne
            if cible in plat or (len(cible) > 80 and cible[:80] in plat):
                return {"etat": "trouvee", "fichier": f, "page": i + 1}
    return {"etat": "absente"}


def ajoute_citation(cle, texte, page=None, usage=None, origine="auteur"):
    import datetime
    texte = " ".join((texte or "").split()).strip("«» \"“”")
    if len(texte) < 8:
        raise ValueError("une citation : le passage, mot pour mot")
    o = dict(lit(cle))
    C = list(o.get("citations") or [])
    if any(_plat(c.get("texte")) == _plat(texte) for c in C):
        return lit(cle)
    c = {"texte": texte, "page": page or None, "usage": usage or None, "origine": origine,
         "date": datetime.date.today().isoformat(), "controle": controle(cle, texte)}
    C.append({k: v for k, v in c.items() if v is not None})
    o["citations"] = C
    ecrit(cle, o)
    journal({"type": "citation_ajoutee", "cle": cle, "texte": texte[:200], "origine": origine})
    return lit(cle)


def supprime_citation(cle, i):
    o = dict(lit(cle))
    C = list(o.get("citations") or [])
    if not 0 <= i < len(C):
        raise KeyError(i)
    x = C.pop(i)
    o["citations"] = C
    ecrit(cle, o)
    journal({"type": "citation_retiree", "cle": cle, "texte": x.get("texte", "")[:200]})
    return lit(cle)


def reverifie_citations(cle):
    o = dict(lit(cle))
    if not o.get("citations"):
        return o
    o["citations"] = [dict(c, controle=controle(cle, c["texte"])) for c in o["citations"]]
    ecrit(cle, o)
    return lit(cle)
