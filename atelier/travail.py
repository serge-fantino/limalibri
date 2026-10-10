# -*- coding: utf-8 -*-
"""Le travail en cours, chapitre par chapitre : les demandes en file, en cours, à décider, et les manques
que les rédactions ont signalés.

Une demande de chapitre appartient à son chapitre. Une demande de la base est rattachée aux chapitres
qu'elle sert :
    redaction, plan   le chapitre visé (cible.chapitre)
    fiche             les chapitres de la question (cible.chapitres), sinon ceux de la réponse
    pistes            les chapitres des pistes proposées, sinon ceux qui utilisent la fiche creusée
Les autres (références, textes originaux, renvois) et celles qui ne servent aucun chapitre vont dans
« sans chapitre » : c'est souvent la première chose à couper.

Les manques ouverts d'un chapitre : ceux de sa rédaction (ou révision) la plus récente — une révision
rend sa propre liste, qui remplace la précédente.
"""
import json

from . import livre

EN_FILE = ("en_attente",)
EN_COURS = ("en_cours",)
A_DECIDER = ("prete", "a_confirmer")
SANS = "_sans"


def _toutes():
    """(slug, demande complète) : la base, puis les chapitres."""
    out = []
    kb = livre.LIVRE / "kb" / "demandes"
    if kb.exists():
        out += [("_kb", p) for p in kb.glob("*.json")]
    ch = livre.LIVRE / "chapters"
    if ch.exists():
        out += [(p.parent.parent.name, p) for p in ch.glob("*/demandes/*.json")]
    R = []
    for s, p in out:
        try:
            R.append((s, json.loads(p.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            pass
    return R


def chapitres_de(slug, d, utilisees=None):
    """Les chapitres qu'une demande sert (liste, éventuellement vide)."""
    if slug != "_kb":
        return [slug]
    c = d.get("cible") or {}
    t = d.get("type")
    if t in ("redaction", "plan") and c.get("chapitre"):
        return [c["chapitre"]]
    if t == "fiche":
        L = list(c.get("chapitres") or [])
        if not L:
            L = [x.get("slug") for x in (d.get("resultat") or {}).get("chapitres") or [] if isinstance(x, dict)]
        return [x for x in L if x]
    if t == "pistes":
        L = sorted({ch for p in (d.get("resultat") or {}).get("pistes") or [] for ch in p.get("chapitres") or []})
        if not L and utilisees is not None:
            L = utilisees.get(c.get("fiche"), [])
        return L
    return []


def _utilisees():
    """fiche -> les chapitres qui la citent dans leur brief."""
    import yaml
    out = {}
    for c in livre.chapitres():
        p = livre.dossier(c["slug"]) / "brief.yaml"
        try:
            br = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}
        except (OSError, yaml.YAMLError):
            continue
        for f in br.get("fiches") or []:
            out.setdefault(str(f), []).append(c["slug"])
    return out


def _resume(slug, d):
    return {"id": d["id"], "slug": slug, "type": d.get("type"), "etat": d.get("etat"),
            "titre": (d.get("titre") or d["id"])[:120], "cree": d.get("cree"), "rang": d.get("rang")}


def par_chapitre(toutes=None):
    """{chapitre: {en_file, en_cours, a_decider: [demande], manques: n, demandes: {id}}} — avec SANS
    pour ce qui ne sert aucun chapitre. Les « demandes » (tous états) servent à imputer les coûts."""
    T = toutes if toutes is not None else _toutes()
    U = _utilisees()
    connus = {c["slug"] for c in livre.chapitres()}
    out = {}
    redac = {}

    def case(ch):
        return out.setdefault(ch, {"en_file": [], "en_cours": [], "a_decider": [], "manques": 0, "demandes": set()})

    for s, d in T:
        chs = [x for x in chapitres_de(s, d, U) if x in connus] or [SANS]
        e = d.get("etat")
        for ch in chs:
            k = case(ch)
            k["demandes"].add(d["id"])
            if e in EN_FILE:
                k["en_file"].append(_resume(s, d))
            elif e in EN_COURS:
                k["en_cours"].append(_resume(s, d))
            elif e in A_DECIDER:
                k["a_decider"].append(_resume(s, d))
        if d.get("type") == "redaction" and e == "decidee" and chs[0] != SANS:
            if d.get("cree", "") > redac.get(chs[0], ("", 0))[0]:
                redac[chs[0]] = (d.get("cree", ""), len((d.get("resultat") or {}).get("manques") or []))
    for ch, (_, n) in redac.items():
        case(ch)["manques"] = n
    for k in out.values():
        k["en_file"].sort(key=lambda x: (x.get("rang") or 0, x.get("cree") or ""))
    return out


def public(P):
    """Pour l'API : sans les ensembles d'identifiants."""
    return {ch: {k: v for k, v in x.items() if k != "demandes"} | {"n_demandes": len(x["demandes"])}
            for ch, x in P.items()}
