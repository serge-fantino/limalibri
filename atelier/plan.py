# -*- coding: utf-8 -*-
"""Le plan et le synopsis, niveau par niveau : le livre, ses parties, ses chapitres.

Trois étages, qui se tiennent :
  le livre      synopsis court (livre.yaml), idée maîtresse, synopsis développé, arc (synopsis.yaml)
  une partie    son titre et ses chapitres (structure.yaml) ; son sens, son arc, sa question (synopsis.yaml)
  un chapitre   son titre, sa période (structure.yaml) ; son synopsis, sa question, ses fiches
                (chapters/<slug>/brief.yaml — le chapitre existe dès son synopsis, avant tout texte)

structure.yaml reste petit et déclaratif (l'ordre, les titres, les identifiants) ; le contenu du
synopsis vit à côté. Toute écriture garde la mise en forme (aller-retour YAML) et va au journal du
livre (journal.jsonl à la racine). Un chapitre qui a du texte ne se supprime pas ici.
"""
import re
import json
import shutil

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from . import livre

CHAMPS_LIVRE = ("idee", "developpe", "arc")
CHAMPS_PARTIE = ("sens", "arc", "question")
CHAMPS_CHAPITRE_BRIEF = ("synopsis", "question", "fiches")
STATUTS = ("outline", "draft", "revised", "locked")


def _fichier_synopsis():
    return livre.LIVRE / "synopsis.yaml"


def _lit_synopsis():
    p = _fichier_synopsis()
    y = livre.yaml_rt()
    doc = y.load(p.read_text(encoding="utf-8")) if p.exists() else None
    if doc is None:
        doc = CommentedMap()
        doc.yaml_set_start_comment("Le synopsis du livre, étage par étage (le livre, ses parties). Les chapitres ont le\n"
                                   "leur dans leur brief.yaml ; l'ordre et les titres sont dans structure.yaml.")
    doc.setdefault("livre", CommentedMap())
    doc.setdefault("parties", CommentedMap())
    return y, doc


def _ecrit_synopsis(y, doc):
    _fichier_synopsis().write_text(livre.rt_texte(y, doc), encoding="utf-8")


def _lit_structure():
    y = livre.yaml_rt()
    p = livre.LIVRE / "structure.yaml"
    doc = y.load(p.read_text(encoding="utf-8")) or CommentedMap()
    if doc.get("parts") is None:
        doc["parts"] = CommentedSeq()
    if doc.get("prefaces") is None:
        doc["prefaces"] = CommentedSeq()
    return y, doc


def _ecrit_structure(y, doc):
    (livre.LIVRE / "structure.yaml").write_text(livre.rt_texte(y, doc), encoding="utf-8")


def journal(e):
    with (livre.LIVRE / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(e, date=livre._maintenant()), ensure_ascii=False) + "\n")


def _brief(slug):
    p = livre.dossier(slug) / "brief.yaml"
    y = livre.yaml_rt()
    doc = y.load(p.read_text(encoding="utf-8")) if p.exists() else None
    return p, y, doc if doc is not None else CommentedMap([("chapter", slug)])


def _a_du_texte(slug):
    for v in livre.VERSIONS:
        p = livre.dossier(slug) / (v + ".md")
        if p.exists() and p.read_text(encoding="utf-8").strip():
            return True
    return False


# ------------------------------------------------------------------ lire

def lit():
    """Tout le plan : le livre, puis chaque partie avec son synopsis et ses chapitres."""
    m = livre.meta()
    _, syn = _lit_synopsis()
    s = livre.structure()
    parties = []
    for p in s["parts"]:
        ps = syn["parties"].get(p["id"]) or {}
        chs = []
        for c in p.get("chapters") or []:
            br = {}
            bp = livre.dossier(c["slug"]) / "brief.yaml"
            if bp.exists():
                import yaml
                br = yaml.safe_load(bp.read_text(encoding="utf-8")) or {}
            chs.append({"slug": c["slug"], "title": c.get("title"), "periode": c.get("periode"),
                        "status": c.get("status"), "versions": c.get("versions") or [],
                        "synopsis": br.get("synopsis"), "question": br.get("question"),
                        "fiches": [str(x) for x in br.get("fiches") or []],
                        "a_texte": _a_du_texte(c["slug"]), "dossier": livre.dossier(c["slug"]).is_dir()})
        parties.append({"id": p["id"], "title": p.get("title"), **{k: ps.get(k) for k in CHAMPS_PARTIE}, "chapitres": chs})
    return {"livre": {"titre": m.get("titre"), "synopsis": m.get("synopsis"),
                      **{k: syn["livre"].get(k) for k in CHAMPS_LIVRE}},
            "parties": parties, "versions": list((m.get("versions") or {}).keys())}


# ------------------------------------------------------------------ le livre

def modifie_livre(champs):
    if "synopsis" in champs:
        m = livre.meta()
        livre.ecrit_meta({"synopsis": champs["synopsis"]}, m["_version"])
    y, syn = _lit_synopsis()
    change = {}
    for k in CHAMPS_LIVRE:
        if k in champs:
            v = (champs[k] or "").strip()
            if (syn["livre"].get(k) or "") != v:
                change[k] = v
                syn["livre"][k] = livre.LiteralScalarString(v + "\n") if "\n" in v else v
    if change:
        _ecrit_synopsis(y, syn)
        journal({"type": "synopsis_livre", "champs": list(change)})
    return lit()


# ------------------------------------------------------------------ les parties

def _partie(doc, pid):
    for i, p in enumerate(doc["parts"]):
        if str(p.get("id")) == pid:
            return i, p
    raise KeyError(pid)


def ajoute_partie(titre, apres=None, champs=None):
    titre = (titre or "").strip()
    if not titre:
        raise ValueError("une partie a un titre")
    y, doc = _lit_structure()
    pris = {str(p.get("id")) for p in doc["parts"]}
    n = 1
    while "p%d" % n in pris:
        n += 1
    pid = "p%d" % n
    nouvelle = CommentedMap([("id", pid), ("title", titre), ("chapters", CommentedSeq())])
    pos = len(doc["parts"]) if apres is None else _partie(doc, apres)[0] + 1
    doc["parts"].insert(pos, nouvelle)
    _ecrit_structure(y, doc)
    if champs:
        modifie_partie(pid, champs)
    journal({"type": "partie_ajoutee", "partie": pid, "titre": titre})
    return pid


def modifie_partie(pid, champs):
    if "title" in champs:
        y, doc = _lit_structure()
        _, p = _partie(doc, pid)
        t = (champs["title"] or "").strip()
        if t and t != p.get("title"):
            p["title"] = t
            _ecrit_structure(y, doc)
    y, syn = _lit_synopsis()
    ps = syn["parties"].get(pid)
    if ps is None:
        syn["parties"][pid] = ps = CommentedMap()
    change = []
    for k in CHAMPS_PARTIE:
        if k in champs:
            v = (champs[k] or "").strip()
            if (ps.get(k) or "") != v:
                ps[k] = livre.LiteralScalarString(v + "\n") if "\n" in v else v
                change.append(k)
    if change:
        _ecrit_synopsis(y, syn)
    journal({"type": "partie_modifiee", "partie": pid, "champs": [k for k in champs]})
    return lit()


def deplace_partie(pid, sens):
    y, doc = _lit_structure()
    i, p = _partie(doc, pid)
    j = i + (1 if sens > 0 else -1)
    if 0 <= j < len(doc["parts"]):
        doc["parts"].pop(i)
        doc["parts"].insert(j, p)
        _ecrit_structure(y, doc)
        journal({"type": "partie_deplacee", "partie": pid, "position": j})
    return lit()


def supprime_partie(pid):
    y, doc = _lit_structure()
    i, p = _partie(doc, pid)
    if p.get("chapters"):
        raise ValueError("la partie a des chapitres : les déplacer ou les supprimer d'abord")
    doc["parts"].pop(i)
    _ecrit_structure(y, doc)
    ys, syn = _lit_synopsis()
    if pid in syn["parties"]:
        del syn["parties"][pid]
        _ecrit_synopsis(ys, syn)
    journal({"type": "partie_supprimee", "partie": pid})
    return lit()


# ------------------------------------------------------------------ les chapitres

def _slug(s):
    import unicodedata
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return "-".join(re.findall(r"[a-z0-9]+", s))[:50]


def _chapitre(doc, slug):
    for p in doc["parts"]:
        for i, c in enumerate(p.get("chapters") or []):
            if c.get("slug") == slug:
                return p, i, c
    raise KeyError(slug)


def ajoute_chapitre(pid, titre, slug=None, apres=None, champs=None):
    titre = (titre or "").strip()
    if not titre:
        raise ValueError("un chapitre a un titre")
    y, doc = _lit_structure()
    _, p = _partie(doc, pid)
    pris = {c.get("slug") for q in doc["parts"] for c in q.get("chapters") or []} | \
           {c.get("slug") for c in doc.get("prefaces") or []}
    base = _slug(slug or titre) or "chapitre"
    slug, n = base, 2
    while slug in pris or livre.dossier(slug).exists():
        slug, n = "%s-%d" % (base, n), n + 1
    versions = list((livre.meta().get("versions") or {"recit": {}}).keys())
    c = CommentedMap([("slug", slug), ("title", titre)])
    if champs and champs.get("periode"):
        c["periode"] = champs["periode"].strip()
    c["versions"] = CommentedSeq(versions)
    c["status"] = "outline"
    if p.get("chapters") is None:
        p["chapters"] = CommentedSeq()
    pos = len(p["chapters"]) if apres is None else next(
        (i + 1 for i, x in enumerate(p["chapters"]) if x.get("slug") == apres), len(p["chapters"]))
    p["chapters"].insert(pos, c)
    _ecrit_structure(y, doc)
    livre.dossier(slug).mkdir(parents=True, exist_ok=True)
    bp, yb, br = _brief(slug)
    br.setdefault("chapter", slug)
    bp.write_text(livre.rt_texte(yb, br), encoding="utf-8")
    if champs:
        modifie_chapitre(slug, {k: v for k, v in champs.items() if k != "periode"})
    journal({"type": "chapitre_ajoute", "chapitre": slug, "partie": pid, "titre": titre})
    return slug


def modifie_chapitre(slug, champs):
    y, doc = _lit_structure()
    _, _, c = _chapitre(doc, slug)
    change = False
    for k in ("title", "periode", "status"):
        if k in champs:
            v = (champs[k] or "").strip()
            if k == "status" and v not in STATUTS:
                raise ValueError("statut : %s" % " | ".join(STATUTS))
            if (c.get(k) or "") != v:
                if v:
                    c[k] = v
                elif k in c:
                    del c[k]
                change = True
    if change:
        _ecrit_structure(y, doc)
    bch = {k: champs[k] for k in CHAMPS_CHAPITRE_BRIEF if k in champs}
    if bch:
        livre.dossier(slug).mkdir(parents=True, exist_ok=True)
        bp, yb, br = _brief(slug)
        for k, v in bch.items():
            if k == "fiches":
                v = [x.strip() for x in (v if isinstance(v, list) else re.split(r"[,\n]", v or "")) if x and x.strip()]
                inconnues = [x for x in v if not (livre.LIVRE / "kb" / "fiches" / (x + ".md")).exists()]
                if inconnues:
                    raise ValueError("fiche(s) inconnue(s) : %s" % ", ".join(inconnues))
                br[k] = CommentedSeq(v)
            else:
                v = (v or "").strip()
                br[k] = livre.LiteralScalarString(v + "\n") if "\n" in v else v
        bp.write_text(livre.rt_texte(yb, br), encoding="utf-8")
        with (livre.dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "brief", "champ": ",".join(bch), "date": livre._maintenant(),
                                "motif": "synopsis"}, ensure_ascii=False) + "\n")
    journal({"type": "chapitre_modifie", "chapitre": slug, "champs": list(champs)})
    return lit()


def deplace_chapitre(slug, pid=None, sens=0):
    """Monter / descendre dans sa partie (sens ±1), ou passer à une autre partie (à la fin)."""
    y, doc = _lit_structure()
    p, i, c = _chapitre(doc, slug)
    if pid and pid != p.get("id"):
        _, q = _partie(doc, pid)
        p["chapters"].pop(i)
        if q.get("chapters") is None:
            q["chapters"] = CommentedSeq()
        q["chapters"].append(c)
    elif sens:
        j = i + (1 if sens > 0 else -1)
        if not 0 <= j < len(p["chapters"]):
            # au bord d'une partie : passer à la voisine
            k = [str(x.get("id")) for x in doc["parts"]].index(str(p.get("id"))) + (1 if sens > 0 else -1)
            if 0 <= k < len(doc["parts"]):
                q = doc["parts"][k]
                p["chapters"].pop(i)
                if q.get("chapters") is None:
                    q["chapters"] = CommentedSeq()
                q["chapters"].insert(0 if sens > 0 else len(q["chapters"]), c)
        else:
            p["chapters"].pop(i)
            p["chapters"].insert(j, c)
    _ecrit_structure(y, doc)
    journal({"type": "chapitre_deplace", "chapitre": slug})
    return lit()


def supprime_chapitre(slug):
    if _a_du_texte(slug):
        raise ValueError("le chapitre a du texte : il ne se supprime pas depuis le plan")
    y, doc = _lit_structure()
    p, i, _ = _chapitre(doc, slug)
    p["chapters"].pop(i)
    _ecrit_structure(y, doc)
    d = livre.dossier(slug)
    if d.exists():
        corbeille = livre.LIVRE / "corbeille"
        corbeille.mkdir(exist_ok=True)
        shutil.move(str(d), str(corbeille / ("%s-%s" % (slug, livre._maintenant()[:19].replace(":", "")))))
    journal({"type": "chapitre_supprime", "chapitre": slug})
    return lit()
