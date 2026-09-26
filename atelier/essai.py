# -*- coding: utf-8 -*-
"""La structure de l'essai : sections hiérarchiques, déplacements, intertitres.

L'essai reste du Markdown. Sa hiérarchie est celle de ses intertitres (## , ###, ####…),
à la profondeur que le propos demande. Chaque intertitre porte un identifiant stable,
écrit dans le titre même :

    ## D'où vient l'eau {#vient-eau}

— syntaxe standard (attr_list, pandoc) : la section survit à un changement de titre ou de
place, comme un paragraphe survit par son ^id. Le numéro d'une section (1.2.3) n'est jamais
stocké : il se calcule à l'affichage, depuis la position.

Le fichier est lu comme une suite d'unités séparées par une ligne vide : un intertitre, un
paragraphe (^id), ou autre chose (filet, définition de note…) qui voyage avec sa section.
Toute opération réécrit le fichier depuis ces unités, sans toucher à leur texte ; elle est
refusée si le fichier a changé depuis sa lecture, et notée au journal.
"""
import re
import json
import hashlib
import unicodedata

from . import livre

TITRE = re.compile(r"^(#{2,6})\s+(.*?)(?:\s*\{#([\w-]+)\})?\s*$")
ANCRE = re.compile(r"[ \t]\^([a-z0-9]+)[ \t]*$")
VIDES = set("le la les l d de du des un une et ou a au aux en ce ces qu que qui ne pas "
            "on son sa ses se sur par pour dans est sont".split())


class Conflit(Exception):
    pass


def _fichier(slug):
    p = livre.dossier(slug) / "essai.md"
    if not p.exists():
        raise KeyError(slug)
    return p


def empreinte(slug):
    return hashlib.sha1(_fichier(slug).read_bytes()).hexdigest()[:12]


def ident_section(titre, pris):
    s = unicodedata.normalize("NFD", titre.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    mots = [m for m in re.split(r"[^a-z0-9]+", s.replace("'", " ").replace("’", " ")) if m and m not in VIDES]
    base = "-".join(mots[:3])
    if len(base) < 8:                       # « Ce qu'on ne sait pas » -> pas « sait » seul
        tous = [m for m in re.split(r"[^a-z0-9]+", s) if m]
        base = "-".join(tous[:5]) or "section"
    i, n = base, 2
    while i in pris:
        i, n = "%s-%d" % (base, n), n + 1
    pris.add(i)
    return i


# ------------------------------------------------------------------ unités

def unites(texte):
    out = []
    for brut in re.split(r"\n[ \t]*\n", texte.strip("\n")):
        lignes = brut.strip("\n")
        m = TITRE.match(lignes) if "\n" not in lignes else None
        if m:
            out.append({"kind": "titre", "niveau": len(m.group(1)), "titre": m.group(2).strip(),
                        "id": m.group(3), "brut": lignes})
            continue
        a = ANCRE.search(lignes.rstrip())
        out.append({"kind": "bloc", "id": a.group(1), "brut": lignes} if a else {"kind": "autre", "brut": lignes})
    return out


def _texte(us):
    for u in us:
        if u["kind"] == "titre":
            u["brut"] = "%s %s {#%s}" % ("#" * u["niveau"], u["titre"], u["id"])
    return "\n\n".join(u["brut"] for u in us) + "\n"


def _lit(slug):
    return unites(_fichier(slug).read_text(encoding="utf-8"))


def _ecrit(slug, attendue, us, op):
    if empreinte(slug) != attendue:
        raise Conflit("essai.md a changé depuis son ouverture")
    _fichier(slug).write_text(_texte(us), encoding="utf-8")
    with (livre.dossier(slug) / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(op, type="structure", version="essai", date=livre._maintenant()),
                           ensure_ascii=False) + "\n")
    return plan(slug)


def pose_identifiants(slug):
    """Donne un identifiant à chaque intertitre qui n'en a pas. Rend le nombre posé."""
    us = _lit(slug)
    pris = {u["id"] for u in us if u["kind"] == "titre" and u["id"]}
    n = 0
    for u in us:
        if u["kind"] == "titre" and not u["id"]:
            u["id"] = ident_section(u["titre"], pris)
            n += 1
    if n:
        _fichier(slug).write_text(_texte(us), encoding="utf-8")
    return n


# ------------------------------------------------------------------ le plan (l'arbre)

def _premiers_mots(brut, n=14):
    t = ANCRE.sub("", brut)
    t = re.sub(r"\[\^[^\]]+\]|\[@[^\]]+\]|[*_`]", "", t)
    mots = t.split()
    return " ".join(mots[:n]) + (" …" if len(mots) > n else "")


def plan(slug):
    """L'arbre : l'ouverture (paragraphes avant le premier intertitre), puis les sections,
    chacune avec ses paragraphes et ses sous-sections. Les notes n'y figurent pas."""
    us = _lit(slug)
    c = next((x for x in livre.chapitres() if x["slug"] == slug), {})
    secs, nums = livre.numerotation(_fichier(slug).read_text(encoding="utf-8"),
                                    c.get("numero") if c.get("numero") is not None else "P")
    racine = {"id": None, "niveau": 1, "titre": "(ouverture)", "blocs": [], "enfants": []}
    pile = [racine]
    notes = 0
    for u in us:
        if u["kind"] == "titre":
            while pile[-1]["niveau"] >= u["niveau"]:
                pile.pop()
            s = {"id": u["id"], "niveau": u["niveau"], "titre": u["titre"], "blocs": [], "enfants": [],
                 "num": secs.get(u["id"], {}).get("num")}
            pile[-1]["enfants"].append(s)
            pile.append(s)
        elif u["kind"] == "bloc":
            appels = len(re.findall(r"\[\^[^\]]+\](?!:)", u["brut"]))
            pile[-1]["blocs"].append({"id": u["id"], "debut": _premiers_mots(u["brut"]), "notes": appels,
                                      "num": nums.get(u["id"])})
        elif u["brut"].startswith("[^"):
            notes += 1
    return {"empreinte": empreinte(slug), "arbre": racine, "definitions_de_notes": notes,
            "numerotation": livre.meta().get("numerotation_essai") or "aucune"}


# ------------------------------------------------------------------ opérations

def _index(us, kind, ident):
    for i, u in enumerate(us):
        if u["kind"] == kind and u.get("id") == ident:
            return i
    raise KeyError(ident)


def _fin_section(us, i):
    """Index (exclu) de la fin de la section qui commence à l'intertitre i."""
    niv = us[i]["niveau"]
    for j in range(i + 1, len(us)):
        if us[j]["kind"] == "titre" and us[j]["niveau"] <= niv:
            return j
    return len(us)


def _position(us, cible):
    """Où insérer : {"type": bloc|section, "id": …, "place": avant|apres|debut|fin}."""
    kind = "titre" if cible["type"] == "section" else "bloc"
    i = _index(us, kind, cible["id"])
    place = cible.get("place", "apres")
    if kind == "bloc":
        return i if place == "avant" else i + 1
    if place == "avant":
        return i
    if place == "debut":
        return i + 1
    return _fin_section(us, i)                  # fin (ou après) : à la fin de la section


def deplace(slug, attendue, quoi, cible):
    us = _lit(slug)
    if quoi["type"] == "bloc":
        i = _index(us, "bloc", quoi["id"])
        morceau = [us.pop(i)]
    else:
        i = _index(us, "titre", quoi["id"])
        j = _fin_section(us, i)
        if cible["type"] == "section":
            dedans = {u["id"] for u in us[i:j] if u["kind"] == "titre"}
            if cible["id"] in dedans:
                raise ValueError("une section ne se déplace pas dans elle-même")
        elif cible["id"] in {u.get("id") for u in us[i:j]}:
            raise ValueError("une section ne se déplace pas dans elle-même")
        morceau = us[i:j]
        del us[i:j]
    k = _position(us, cible)
    us[k:k] = morceau
    return _ecrit(slug, attendue, us, {"op": "deplace", "quoi": quoi, "cible": cible})


def renomme(slug, attendue, ident, titre):
    us = _lit(slug)
    u = us[_index(us, "titre", ident)]
    avant, u["titre"] = u["titre"], " ".join(titre.split())
    if not u["titre"]:
        raise ValueError("un intertitre a un titre")
    return _ecrit(slug, attendue, us, {"op": "renomme", "section": ident, "avant": avant, "apres": u["titre"]})


def niveau(slug, attendue, ident, delta):
    """Monte (delta -1) ou descend (+1) une section d'un niveau, sous-sections comprises."""
    us = _lit(slug)
    i = _index(us, "titre", ident)
    j = _fin_section(us, i)
    titres = [u for u in us[i:j] if u["kind"] == "titre"]
    if any(not 2 <= u["niveau"] + delta <= 6 for u in titres):
        raise ValueError("niveau hors limites (## à ######)")
    for u in titres:
        u["niveau"] += delta
    return _ecrit(slug, attendue, us, {"op": "niveau", "section": ident, "delta": delta})


def insere_section(slug, attendue, titre, niv, cible):
    us = _lit(slug)
    pris = {u["id"] for u in us if u["kind"] == "titre" and u["id"]}
    titre = " ".join((titre or "").split())
    if not titre:
        raise ValueError("un intertitre a un titre")
    u = {"kind": "titre", "niveau": max(2, min(6, int(niv))), "titre": titre, "id": ident_section(titre, pris)}
    k = _position(us, cible)
    us[k:k] = [u]
    return _ecrit(slug, attendue, us, {"op": "insere", "section": u["id"], "titre": titre, "cible": cible})


def supprime_section(slug, attendue, ident):
    """Retire l'intertitre ; son contenu rejoint la section précédente."""
    us = _lit(slug)
    i = _index(us, "titre", ident)
    titre = us[i]["titre"]
    del us[i]
    return _ecrit(slug, attendue, us, {"op": "supprime", "section": ident, "titre": titre})
