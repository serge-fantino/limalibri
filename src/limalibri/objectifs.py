# -*- coding: utf-8 -*-
"""Les objectifs du livre : jusqu'où on veut aller, mesuré dans les fichiers.

Ils vivent dans objectifs.yaml, à la racine du livre, dans l'ordre de priorité :

    objectifs:
      - id: o-3f2a
        titre: La Terre relue
        version: essai
        perimetre: {type: partie, partie: p6}        # ou {type: livre}, ou {type: chapitres, chapitres: [...]}
        criteres:                                    # tous, sur chaque chapitre du périmètre
          - {id: niveau, valeur: relu}
          - {id: manques, valeur: 0}
        intention: Le chapitre 18 tient sans parler de la base.   # jugée par l'auteur, pas mesurée
        echeance: 2026-11-01
        budget: 30                                   # dollars, depuis la création de l'objectif
        cree: 2026-10-10T…
        etat: actif                                  # ou archive
        jugement: {atteint: true, note: …, date: …}  # l'intention, quand l'auteur l'a jugée

Un objectif est atteint quand chaque critère tient sur chaque chapitre du périmètre — et, s'il a une
intention, quand l'auteur l'a jugée atteinte. La progression compte les couples (chapitre, critère)
tenus. La dépense : les demandes qui servent le périmètre (limalibri/travail.py), depuis la création.
L'évaluation est recalculée à chaque fois ; seule trace écrite, l'historique : quand la mesure d'un
objectif change (progression, critères tenus, atteinte), un point s'ajoute à objectifs-suivi.jsonl — d'où
la courbe d'avancement. Le départ d'un objectif peut être une version marquée dans git
(limalibri/versions.py) : depart: {tag, commit, date} ; la carte dit alors ce qui a changé depuis.
"""
import json
import time
import secrets

import yaml

from . import livre, avancement

ORDRE_NIVEAUX = list(avancement.NIVEAUX)

# id -> (libellé, sens, valeur par défaut, versions, aide)
CRITERES = {
    "niveau": ("niveau", "≥", "relu", ("essai", "recit"), "l'avancement du chapitre : brief, brouillon, relu, validé"),
    "score": ("score de suivi", "≥", 80, ("essai", "recit"), "la note du suivi, en %"),
    "manques": ("manques ouverts", "≤", 0, ("essai",), "les manques signalés par la rédaction ou la révision la plus récente"),
    "controles": ("portes du harnais passées", "=", True, ("essai", "recit"), "toutes les portes bloquantes"),
    "naif": ("lecture naïve à jour", "=", True, ("essai", "recit"), "une lecture naïve du texte tel qu'il est"),
    "annotations": ("annotations ouvertes", "≤", 0, ("essai", "recit"), "les annotations encore ouvertes sur cette version"),
    "fiches": ("fiches au brief", "≥", 2, ("essai", "recit"), "le nombre de fiches choisies pour le chapitre"),
    "a_decider": ("demandes à décider", "≤", 0, ("essai", "recit"), "résultats de Claude qui attendent ta décision"),
}


def _fichier():
    return livre.LIVRE / "objectifs.yaml"


def lit_tous():
    p = _fichier()
    if not p.exists():
        return []
    try:
        return list((yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("objectifs") or [])
    except yaml.YAMLError:
        return []


def _ecrit(L, quoi, o):
    _fichier().write_text(yaml.safe_dump({"objectifs": L}, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    from . import kb
    try:
        kb.journal({"type": "objectif_" + quoi, "objectif": o.get("id"), "titre": o.get("titre")})
    except Exception:                                   # noqa: BLE001 — le journal est un plus
        pass


def _propre(corps, avant=None):
    """Valider ce que l'auteur a saisi ; rend l'objectif normalisé."""
    o = dict(avant or {})
    titre = " ".join((corps.get("titre") if "titre" in corps else o.get("titre") or "").split())
    if not titre:
        raise ValueError("un titre")
    version = corps.get("version", o.get("version", "essai"))
    if version not in ("essai", "recit"):
        raise ValueError("version : essai ou recit")
    pe = corps.get("perimetre", o.get("perimetre")) or {"type": "livre"}
    if pe.get("type") == "partie":
        from . import plan
        if pe.get("partie") not in {p.get("id") for p in plan.lit()["parties"]}:
            raise ValueError("partie inconnue : %s" % pe.get("partie"))
        pe = {"type": "partie", "partie": pe["partie"]}
    elif pe.get("type") == "chapitres":
        connus = {c["slug"] for c in livre.chapitres()}
        chs = [c for c in pe.get("chapitres") or [] if c in connus]
        if not chs:
            raise ValueError("au moins un chapitre")
        pe = {"type": "chapitres", "chapitres": chs}
    else:
        pe = {"type": "livre"}
    C = []
    for c in corps.get("criteres", o.get("criteres")) or []:
        k = c.get("id")
        if k not in CRITERES or version not in CRITERES[k][3]:
            continue
        v = c.get("valeur", CRITERES[k][2])
        if k == "niveau":
            if v not in ORDRE_NIVEAUX:
                raise ValueError("niveau inconnu : %s" % v)
        elif CRITERES[k][1] == "=":
            v = True
        else:
            v = int(v)
        C.append({"id": k, "valeur": v})
    intention = " ".join((corps.get("intention", o.get("intention")) or "").split()) or None
    if not C and not intention:
        raise ValueError("au moins un critère, ou une intention")
    budget = corps.get("budget", o.get("budget"))
    budget = float(budget) if budget not in (None, "") else None
    echeance = (corps.get("echeance", o.get("echeance")) or None)
    o.update(titre=titre, version=version, perimetre=pe, criteres=C, intention=intention,
             echeance=str(echeance) if echeance else None, budget=budget)
    if intention != (avant or {}).get("intention"):
        o.pop("jugement", None)                         # une intention réécrite se rejuge
    return {k: v for k, v in o.items() if v is not None}


def cree(corps):
    L = lit_tous()
    o = _propre(corps)
    o.update(id="o-" + secrets.token_hex(2), cree=livre._maintenant(), etat="actif")
    L.append(o)
    _ecrit(L, "cree", o)
    return o


def _trouve(L, ident):
    for i, o in enumerate(L):
        if o.get("id") == ident:
            return i, o
    raise KeyError(ident)


def modifie(ident, corps):
    L = lit_tous()
    i, o = _trouve(L, ident)
    if "etat" in corps:
        if corps["etat"] not in ("actif", "archive"):
            raise ValueError("état : actif ou archive")
        o["etat"] = corps["etat"]
        L[i] = o
    else:
        L[i] = _propre(corps, o)
    _ecrit(L, "modifie", L[i])
    return L[i]


def juge(ident, corps):
    """L'intention, jugée par l'auteur : {atteint: bool, note}."""
    L = lit_tous()
    i, o = _trouve(L, ident)
    if not o.get("intention"):
        raise ValueError("cet objectif n'a pas d'intention à juger")
    o["jugement"] = {"atteint": bool(corps.get("atteint")), "note": (corps.get("note") or "").strip() or None,
                     "date": livre._maintenant()}
    L[i] = o
    _ecrit(L, "juge", o)
    return o


def ajoute_consigne(ident, texte):
    """Une consigne commune (d'un cadrage retenu) : ajoutée à toutes les actions de Claude de l'objectif."""
    L = lit_tous()
    i, o = _trouve(L, ident)
    texte = " ".join((texte or "").split())
    if texte and texte not in (o.get("consigne") or ""):
        o["consigne"] = ((o.get("consigne") or "") + "\n" + texte).strip()
    L[i] = o
    _ecrit(L, "consigne", o)
    return o


def supprime(ident):
    L = lit_tous()
    i, o = _trouve(L, ident)
    del L[i]
    _ecrit(L, "supprime", o)
    return {"supprime": ident}


def ordonne(ids):
    """La priorité : l'ordre donné ; les objectifs absents de la liste gardent leur place relative, après."""
    L = lit_tous()
    rang = {x: k for k, x in enumerate(ids)}
    L.sort(key=lambda o: rang.get(o.get("id"), len(rang)))
    _ecrit(L, "ordonne", {})
    return L


# ------------------------------------------------------------------ l'évaluation

def perimetre(o, chapitres):
    pe = o.get("perimetre") or {"type": "livre"}
    if pe["type"] == "partie":
        return [c for c in chapitres if c.get("partie") == pe.get("partie")]
    if pe["type"] == "chapitres":
        s = set(pe.get("chapitres") or [])
        return [c for c in chapitres if c["slug"] in s]
    return list(chapitres)


def libelle_perimetre(o, chapitres_suivi):
    pe = o.get("perimetre") or {"type": "livre"}
    if pe["type"] == "partie":
        c = next((c for c in chapitres_suivi if c.get("partie") == pe.get("partie")), None)
        return "partie « %s »" % (c.get("partie_titre") if c else pe.get("partie"))
    if pe["type"] == "chapitres":
        n = len(pe.get("chapitres") or [])
        return "%d chapitre%s" % (n, "s" if n > 1 else "")
    return "tout le livre"


def _tient(k, attendu, c, T):
    """(tenu, valeur mesurée) d'un critère sur un chapitre du suivi."""
    m = c.get("mesures") or {}
    t = T.get(c["slug"]) or {}
    if k == "niveau":
        v = m.get("niveau") or "vide"
        return ORDRE_NIVEAUX.index(v) >= ORDRE_NIVEAUX.index(attendu), v
    if k == "score":
        return (m.get("score") or 0) >= attendu, m.get("score") or 0
    if k == "manques":
        v = t.get("manques") or 0
        return v <= attendu, v
    if k == "controles":
        return bool(m.get("controles")), "%d porte(s) en échec" % m.get("portes_ko", 0) if m.get("ecrit") else "rien d'écrit"
    if k == "naif":
        return bool(m.get("naif")), "à jour" if m.get("naif") else "à faire"
    if k == "annotations":
        v = m.get("annotations") or 0
        return v <= attendu, v
    if k == "fiches":
        v = m.get("fiches") or 0
        return v >= attendu, v
    if k == "a_decider":
        v = len(t.get("a_decider") or [])
        return v <= attendu, v
    return True, None


def _depense(o, T, chs):
    """Le coût des demandes qui servent le périmètre, depuis la création de l'objectif."""
    ids = set().union(*[(T.get(c["slug"]) or {}).get("demandes") or set() for c in chs]) if chs else set()
    p = livre.LIVRE / "consommation.jsonl"
    if not ids or not p.exists():
        return 0.0
    depuis, total = o.get("cree") or "", 0.0
    for ligne in p.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(ligne)
        except ValueError:
            continue
        if e.get("ident") in ids and (e.get("date") or "") >= depuis:
            total += e.get("cout_usd") or 0
    return round(total, 2)


def evalue(o, S, T):
    """Un objectif, mesuré sur le suivi S de sa version et le travail T par chapitre."""
    chs = perimetre(o, S["chapitres"])
    crit, lignes, tenus, total = [], [], 0, 0
    for cr in o.get("criteres") or []:
        lib, sens, _, _, aide = CRITERES[cr["id"]]
        crit.append({"id": cr["id"], "valeur": cr["valeur"], "libelle": lib, "sens": sens, "aide": aide,
                     "attendu": "%s %s" % (sens, cr["valeur"]) if sens != "=" else "", "tenus": 0, "total": len(chs)})
    for c in chs:
        ecarts = []
        for k, cr in enumerate(o.get("criteres") or []):
            ok, v = _tient(cr["id"], cr["valeur"], c, T)
            total += 1
            if ok:
                tenus += 1
                crit[k]["tenus"] += 1
            else:
                ecarts.append({"critere": cr["id"], "libelle": crit[k]["libelle"], "attendu": crit[k]["attendu"], "mesure": v})
        lignes.append({"slug": c["slug"], "numero": c.get("numero"), "titre": c["titre"], "niveau": c.get("niveau"),
                       "score": c.get("score"), "ecarts": ecarts})
    mesure = (tenus == total) if total else True
    j = o.get("jugement") or {}
    intention_ok = not o.get("intention") or bool(j.get("atteint"))
    jours = None
    if o.get("echeance"):
        try:
            jours = int((time.mktime(time.strptime(str(o["echeance"])[:10], "%Y-%m-%d")) - time.time()) // 86400) + 1
        except ValueError:
            pass
    return dict(o, perimetre_libelle=libelle_perimetre(o, S["chapitres"]), criteres_eval=crit,
                progression=round(100 * tenus / total) if total else (100 if intention_ok else 0),
                mesure_atteinte=mesure, atteint=mesure and intention_ok, chapitres=lignes,
                restants=sum(1 for l in lignes if l["ecarts"]), depense=_depense(o, T, chs), jours=jours)


def _suivi_fichier():
    return livre.LIVRE / "objectifs-suivi.jsonl"


def _points():
    """id -> [points], dans l'ordre."""
    p, out = _suivi_fichier(), {}
    if p.exists():
        for l in p.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(l)
            except ValueError:
                continue
            out.setdefault(e.get("id"), []).append(e)
    return out


def _point(e):
    return {"progression": e["progression"], "atteint": e["atteint"],
            "tenus": {c["id"]: c["tenus"] for c in e["criteres_eval"]}, "chapitres": len(e["chapitres"]),
            "restants": e["restants"]}


def _note(E, H):
    """Ajouter un point aux objectifs actifs dont la mesure a changé depuis le dernier."""
    neufs = []
    for e in E:
        if e.get("etat") == "archive":
            continue
        pt = _point(e)
        der = (H.get(e["id"]) or [None])[-1]
        if der is None or {k: der.get(k) for k in pt} != pt:
            x = dict(pt, id=e["id"], date=livre._maintenant(), depense=e["depense"])
            neufs.append(x)
            H.setdefault(e["id"], []).append(x)
    if neufs:
        with _suivi_fichier().open("a", encoding="utf-8") as f:
            for x in neufs:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")


def evalue_tous(version, S, T):
    E = [evalue(o, S, T) for o in lit_tous() if o.get("version", "essai") == version]
    H = _points()
    try:
        _note(E, H)
    except OSError:
        pass
    for e in E:
        pts = H.get(e["id"]) or []
        e["historique"] = [{"date": p["date"], "progression": p["progression"], "tenus": p.get("tenus"),
                            "restants": p.get("restants")} for p in pts]
    return E


def pose_depart(ident, depart):
    """Le départ de l'objectif : une version git marquée {tag, commit, date}."""
    L = lit_tous()
    i, o = _trouve(L, ident)
    o["depart"] = {k: depart.get(k) for k in ("tag", "commit", "date") if depart.get(k)}
    L[i] = o
    _ecrit(L, "depart", o)
    return o


def definitions():
    return {"criteres": [{"id": k, "libelle": v[0], "sens": v[1], "defaut": v[2], "versions": list(v[3]), "aide": v[4]}
                         for k, v in CRITERES.items()], "niveaux": ORDRE_NIVEAUX}
