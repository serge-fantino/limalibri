# -*- coding: utf-8 -*-
"""La frise d'un livre : où se place chaque chapitre dans le temps de son histoire, et des frises internes.

Tout vit dans frise.yaml, à la racine du livre (un fichier à éditer à la main ; LimaLibri le lit, l'amorce, le
dessine). Une seule variable de temps par livre : t, en années depuis l'origine de l'histoire (le Big Bang pour Un
Monde, la formation de la Terre pour Une Vie…). Les dates s'écrivent en clair et sont converties :

    "1e-43 s"  "10⁻³⁶ s"  "3 min"  "380 000 ans"  "4,5 Ga"  "66 Ma"     une durée, lue selon temps.lecture
    "il y a 66 Ma"  "dans mille ans"  "aujourd'hui"                       par rapport au présent
    "après 1 s"  "à 9,2 Ga"                                                 depuis l'origine
    "an 1781"  "an -500"   (ou un nombre, dans une frise en années)         une année du calendrier

frise.yaml :
    temps:     {age: 13.8 Ga, lecture: depuis_origine | avant_present, annee_presente: 2026, origine: "le Big Bang"}
    echelles:  [{id, titre, type: lineaire | log | fixe, variable: depuis_origine | avant_present | annee,
                 domaine: [a, b], graduations: [date | {date, texte}], bandes: [ids]}]
    bandes:    [{id, titre, rendu: segments | gradient, segments: [{nom, debut, fin, couleur}],
                 points: [[date, valeur], …], couleurs: [c1, c2], format: "z ≈ {v}"}]
    reperes:   [{date, titre, fiche?}]
    chapitres: {slug: {debut, fin, approx?, note?} | {non_date: true, note?}}
    rendu:     barres | fleche          (la frise des chapitres ; fleche : l'ordre de lecture, ses retours en arrière)
    frises:    [{id, titre, chapitre?, echelle: {…}, rendu: simple | fleche, evenements: [{date | debut/fin, titre,
                 texte?, lien?}]}]

« fixe » : des intervalles réguliers — chaque chapitre (ou événement) a la même place, quelle que soit sa durée ;
le reste (bandes, repères) se place entre eux par interpolation.
"""
import re
import datetime

import yaml

from . import livre

NOM = "frise.yaml"
SEC_AN = 365.25 * 86400
UNITES = [  # (motif, années)
    (r"milliards? d['’]ann[ée]es?|ga|gyr", 1e9), (r"millions? d['’]ann[ée]es?|ma|myr", 1e6),
    (r"milliers? d['’]ann[ée]es?|ka|kyr", 1e3), (r"ans?|ann[ée]es?|yr", 1.0), (r"jours?|j", 1 / 365.25),
    (r"heures?|h", 3600 / SEC_AN), (r"minutes?|min", 60 / SEC_AN), (r"secondes?|s", 1 / SEC_AN)]
MOTS = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "dix": 10, "cent": 100, "mille": 1000}
EXPOSANTS = str.maketrans("⁻⁰¹²³⁴⁵⁶⁷⁸⁹", "-0123456789")


def fichier():
    return livre.LIVRE / NOM


def _brut():
    p = fichier()
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else None


# ------------------------------------------------------------------ les dates

def _nombre(s):
    """Un nombre écrit en clair : 4,5 · 380 000 · 10⁻⁴³ · 1e-43 · ~3 · cent mille. Rend (valeur, reste) ou None."""
    s = s.strip().translate(EXPOSANTS)
    s = re.sub(r"^[~≈]\s*", "", s)
    m = re.match(r"(\d+(?:[  ]\d{3})*(?:[.,]\d+)?)\s*(?:[×x·]\s*)?10\^?\s*(-?\d+)", s)       # 3 × 10-5, 3·10^-5
    if m and ("10" in s[m.start(2) - 3:m.start(2)] or "^" in s):
        return float(m.group(1).replace(" ", "").replace(" ", "").replace(",", ".")) * 10 ** int(m.group(2)), s[m.end():]
    m = re.match(r"10\^?(-\d+|\d+)(?!\d)", s)                                                 # 10-43 (après ⁻), 10^6
    if m and len(m.group(1).lstrip("-")) >= 1 and (m.group(1).startswith("-") or "^" in m.group(0)):
        return 10 ** int(m.group(1)), s[m.end():]
    m = re.match(r"(\d+(?:[  ]\d{3})*(?:[.,]\d+)?(?:e-?\d+)?)", s, re.I)
    if m:
        return float(m.group(1).replace(" ", "").replace(" ", "").replace(",", ".")), s[m.end():]
    mots = re.match(r"((?:(?:un|une|deux|trois|quatre|cinq|dix|cent|mille)\s*)+)", s, re.I)
    if mots:
        v, cour = 0, 0
        for w in mots.group(1).lower().split():
            n = MOTS[w]
            if n >= 100:
                cour = (cour or 1) * n
                if n == 1000:
                    v, cour = v + cour, 0
            else:
                cour += n
        return float(v + cour), s[mots.end():]
    return None


def _unite(reste):
    r = reste.strip().lower()
    for motif, ans in UNITES:
        m = re.match(r"(?:%s)(?![a-zà-ü])" % motif, r)
        if m:
            return ans, r[m.end():]
    return None, r


class Temps:
    """Les conversions d'un livre : tout en t = années depuis l'origine."""

    def __init__(self, cfg):
        cfg = cfg or {}
        self.lecture = cfg.get("lecture") or "depuis_origine"
        self.annee = int(cfg.get("annee_presente") or datetime.date.today().year)
        a = cfg.get("age")
        self.age = self.duree(a) if isinstance(a, str) else float(a) if a else None

    def duree(self, s):
        """Une durée en années (« 4,5 Ga », « 3 min ») ; None si on ne la lit pas."""
        n = _nombre(str(s))
        if not n:
            return None
        v, reste = n
        u, _ = _unite(reste)
        return v * u if u else None

    def lit(self, x, variable=None):
        """Une date (texte ou nombre) → t (années depuis l'origine) ; None : ouvert ou illisible."""
        if x is None or x == "":
            return None
        if isinstance(x, (int, float)):
            if variable == "annee":
                return self._annee(float(x))
            return float(x) if self.lecture == "depuis_origine" else self._avant(float(x))
        s = " ".join(str(x).split()).lower()
        s = re.sub(r"\([^)]*\)", "", s).strip()
        if re.fullmatch(r"(aujourd['’]hui|maintenant|le pr[ée]sent)", s):
            return self.age
        m = re.match(r"an\s+(-?\d+)$", s) or (re.match(r"(-?\d{3,4})$", s) if variable == "annee" else None)
        if m:
            return self._annee(float(m.group(1)))
        for pref, f in (("il y a", self._avant), ("dans", self._apres), ("après", lambda d: d), ("à", lambda d: d)):
            if s.startswith(pref + " "):
                d = self.duree(s[len(pref) + 1:])
                return f(d) if d is not None else None
        if s.endswith(" devant"):
            d = self.duree(s[:-7])
            return self._apres(d) if d is not None else None
        d = self.duree(s)
        if d is None:
            return None
        return d if self.lecture == "depuis_origine" else self._avant(d)

    def _avant(self, d):
        return (self.age - d) if self.age is not None else -d

    def _apres(self, d):
        return (self.age + d) if self.age is not None else d

    def _annee(self, y):
        return self._avant(self.annee - y)


# ------------------------------------------------------------------ la frise, lue

def _chapitres_du_livre():
    from . import avancement
    out = []
    for c in livre.chapitres():
        out.append({"slug": c["slug"], "numero": c.get("numero"), "titre": c["title"], "periode": c.get("periode") or "",
                    "partie": c.get("partie"), "partie_titre": c.get("partie_titre"),
                    "niveau": {v: avancement.niveau(c, v) for v in livre.VERSIONS}})
    return out


def _echelle(e, T, avert, nom):
    v = e.get("variable") or ("annee" if (e.get("type") == "lineaire" and e.get("unite") == "annee") else T.lecture)
    d = [T.lit(x, v) for x in (e.get("domaine") or [])]
    if e.get("domaine") and (len(d) != 2 or None in d):
        avert.append("%s : domaine illisible %r" % (nom, e.get("domaine")))
        d = None
    grads = []
    for g in e.get("graduations") or []:                  # une date, ou {date, texte} : un libellé à soi (« 1er déc. »)
        date, lib = (g.get("date"), g.get("texte")) if isinstance(g, dict) else (g, None)
        t = T.lit(date, v)
        if t is None:
            avert.append("%s : graduation illisible %r" % (nom, date))
        else:
            grads.append({"t": t, "texte": lib})
    return {"id": e.get("id") or nom, "titre": e.get("titre") or e.get("id") or nom, "type": e.get("type") or "lineaire",
            "variable": v, "domaine": d or None, "graduations": grads, "bandes": e.get("bandes")}


def lit():
    """La frise du livre, toutes ses dates converties en t ; avec ce qui n'a pas pu être lu."""
    B = _brut()
    if B is None:
        return {"existe": False, "fichier": str(fichier()), "chapitres_livre": _chapitres_du_livre()}
    T = Temps(B.get("temps"))
    avert = []
    echelles = [_echelle(e, T, avert, "échelle %d" % (i + 1)) for i, e in enumerate(B.get("echelles") or [])] or \
        [{"id": "fixe", "titre": "intervalles réguliers", "type": "fixe", "variable": T.lecture, "domaine": None, "graduations": []}]
    bandes = []
    for b in B.get("bandes") or []:
        x = {"id": b.get("id"), "titre": b.get("titre") or b.get("id"), "rendu": b.get("rendu") or "segments",
             "couleurs": b.get("couleurs") or ["#2d5f8a", "#c0622f"], "format": b.get("format") or "{v}"}
        if x["rendu"] == "gradient":
            x["points"] = []
            for src in b.get("points") or []:
                try:
                    t_, v_ = T.lit(src[0]), float(src[1])
                except (TypeError, ValueError, IndexError):
                    t_, v_ = None, None
                if t_ is None:
                    avert.append("bande %s : point illisible %r (une date avec une virgule s'écrit entre guillemets : "
                                 "[\"1,1 Ga\", 5.3])" % (x["id"], src))
                else:
                    x["points"].append({"t": t_, "v": v_, "texte": str(src[0])})
        else:
            x["segments"] = []
            for s in b.get("segments") or []:
                d, f = T.lit(s.get("debut")), T.lit(s.get("fin"))
                if d is None or f is None:
                    avert.append("bande %s : segment « %s » illisible" % (x["id"], s.get("nom")))
                    continue
                x["segments"].append({"nom": s.get("nom") or "", "debut": d, "fin": f, "couleur": s.get("couleur")})
        bandes.append(x)
    reperes = []
    for r in B.get("reperes") or []:
        t = T.lit(r.get("date"))
        if t is None:
            avert.append("repère « %s » : date illisible %r" % (r.get("titre"), r.get("date")))
            continue
        reperes.append({"t": t, "titre": r.get("titre") or "", "fiche": r.get("fiche"), "texte": str(r.get("date"))})
    C = _chapitres_du_livre()
    places = B.get("chapitres") or {}
    for c in C:
        p = places.get(c["slug"])
        if p is None:
            c.update(place=None, note="pas encore dans frise.yaml")
            continue
        if p.get("non_date"):
            c.update(place=None, non_date=True, note=p.get("note") or "")
            continue
        d, f = T.lit(p.get("debut")), T.lit(p.get("fin"))
        if d is None and f is None:
            avert.append("chapitre %s : ni début ni fin lisibles" % c["slug"])
            c.update(place=None, note="dates illisibles")
            continue
        c.update(place={"debut": d, "fin": f, "ouvert_debut": d is None, "ouvert_fin": f is None, "approx": bool(p.get("approx")),
                        "texte": "%s → %s" % (p.get("debut") or "…", p.get("fin") or "…")}, note=p.get("note") or "")
    frises = []
    for i, fr in enumerate(B.get("frises") or []):
        ech = _echelle(fr.get("echelle") or {}, T, avert, "frise %s" % (fr.get("id") or i + 1))
        ev = []
        for e in fr.get("evenements") or []:
            d = T.lit(e.get("date", e.get("debut")), ech["variable"])
            f = T.lit(e.get("fin"), ech["variable"]) if e.get("fin") is not None else None
            if d is None:
                avert.append("frise %s : « %s » sans date lisible" % (fr.get("id"), e.get("titre")))
                continue
            ev.append({"debut": d, "fin": f, "titre": e.get("titre") or "", "texte": e.get("texte") or "", "lien": e.get("lien"),
                       "date": str(e.get("date", e.get("debut")))})
        frises.append({"id": fr.get("id") or "frise-%d" % (i + 1), "titre": fr.get("titre") or fr.get("id"),
                       "chapitre": fr.get("chapitre"), "rendu": fr.get("rendu") or "simple", "echelle": ech, "evenements": ev,
                       "note": fr.get("note") or ""})
    return {"existe": True, "fichier": str(fichier()), "temps": {"age": T.age, "lecture": T.lecture, "annee": T.annee,
                                                                    "origine": (B.get("temps") or {}).get("origine") or ""},
            "titre": B.get("titre") or "", "rendu": B.get("rendu") or "barres", "echelles": echelles, "bandes": bandes,
            "reperes": reperes, "chapitres": C, "frises": frises, "avertissements": avert}


# ------------------------------------------------------------------ amorcer : depuis les périodes des chapitres

def lit_periode(texte, T):
    """« 4,5 → 4,4 milliards d'années », « ~10⁻³⁶ à 10⁻³² s », « dès ~280 Ma », « aujourd'hui → dans mille ans »…
    → (debut, fin) en texte normalisé pour frise.yaml, ou None."""
    s = " ".join((texte or "").split())
    s = re.sub(r"\([^)]*\)", "", s).strip(" ;,.")
    s = re.split(r"\s*;\s*", s)[0]
    if not s:
        return None
    sl = s.lower()
    if sl in ("futur", "le futur", "l'avenir"):
        return ("aujourd'hui", None)
    if re.fullmatch(r"aujourd['’]hui", sl):
        return ("aujourd'hui", "aujourd'hui")
    ouvert_debut = bool(re.match(r"(avant|jusqu['’]à)\s", sl))
    ouvert_fin = bool(re.match(r"(dès|depuis|après)\s", sl))
    s = re.sub(r"^(avant|jusqu['’]à|dès|depuis|après|vers)\s+", "", s, flags=re.I)     # la casse gardée : « Ma », « Ga »
    morceaux = re.split(r"\s*(?:→|->|\sà\s)\s*", s)
    if len(morceaux) > 2:
        return None
    devant = s.lower().endswith(" devant")
    if devant:
        morceaux = [re.sub(r"\s+devant$", "", m, flags=re.I) for m in morceaux]
    # l'unité finale vaut pour un premier nombre qui n'en a pas (« 47 000 à 380 000 ans »)
    _, fin_unite = (None, None)
    dernier = morceaux[-1]
    n = _nombre(dernier)
    unite_txt = ""
    if n:
        u, _ = _unite(n[1])
        if u:
            unite_txt = n[1].strip()
    out = []
    for m in morceaux:
        m = m.strip()
        if re.fullmatch(r"aujourd['’]hui", m, re.I):
            out.append("aujourd'hui")
            continue
        if m.lower().startswith("dans "):
            d = T.duree(m[5:])
            out.append(m if d is not None else None)
            continue
        n = _nombre(m)
        if not n:
            out.append(None)
            continue
        u, _ = _unite(n[1])
        txt = m if u else ("%s %s" % (m, unite_txt) if unite_txt else None)
        if txt and devant:
            txt = "dans " + txt
        out.append(txt)
    if any(x is None for x in out):
        return None
    if len(out) == 1:
        return (None, out[0]) if ouvert_debut else (out[0], None) if ouvert_fin else (out[0], out[0])
    return out[0], out[1]


GABARIT = """# La frise du livre — à éditer à la main ; LimaLibri la dessine (Plan → frise).
# Toutes les dates s'écrivent en clair : "4,5 Ga", "il y a 66 Ma", "10⁻³⁶ s", "3 min", "an 1781", "aujourd'hui", "dans mille ans".
# Une durée seule se lit selon temps.lecture : depuis l'origine de l'histoire, ou avant le présent.
"""


def place_de(periode, T):
    """La place que donne la période d'un chapitre (une entrée de frise.yaml) ; illisible : « à dater »."""
    r = lit_periode(periode or "", T)
    if not r:
        return {"non_date": True, "note": ("à dater — période : %s" % periode) if periode else "à dater"}
    x = {k: v for k, v in (("debut", r[0]), ("fin", r[1])) if v is not None}
    if "~" in periode or "≈" in periode:
        x["approx"] = True
    x["note"] = "d'après la période : %s" % periode
    return x


def place_chapitre(slug, ecrire=False, forcer=False):
    """Un chapitre sur la frise : sa place dans frise.yaml, celle que donne sa période, et si elle a été posée à la main
    (une note qui ne commence pas par « d'après la période » ni « à dater »). ecrire : la place d'après la période
    remplace la sienne, pour ce chapitre seul (le reste du fichier, commentaires compris, ne bouge pas) ; une place
    posée à la main n'est remplacée qu'avec forcer."""
    p = fichier()
    if not p.exists():
        raise FileNotFoundError(str(p))
    B = _brut()
    T = Temps(B.get("temps"))
    C = _chapitres_du_livre()
    c = next((x for x in C if x["slug"] == slug), None)
    if c is None:
        raise KeyError(slug)
    actuelle = (B.get("chapitres") or {}).get(slug)
    proposee = place_de(c["periode"], T)
    norm = lambda x: {k: (str(v) if not isinstance(v, bool) else v) for k, v in (x or {}).items()}
    main = actuelle is not None and not str((actuelle or {}).get("note") or "").startswith(("d'après la période", "à dater"))
    out = {"slug": slug, "periode": c["periode"], "actuelle": actuelle, "proposee": proposee, "main": main,
           "change": norm(actuelle) != norm(proposee), "ecrit": False}
    if ecrire and out["change"]:
        if main and not forcer:
            raise PermissionError("la place de ce chapitre a été posée à la main")
        from ruamel.yaml.comments import CommentedMap
        y = livre.yaml_rt()
        y.width = 100000                                     # ne replier aucune ligne : le reste du fichier ne bouge pas
        doc = y.load(p.read_text(encoding="utf-8"))
        ch = doc.get("chapitres")
        if not isinstance(ch, dict):
            doc["chapitres"] = ch = CommentedMap()
        val = CommentedMap(proposee)
        if slug in ch:
            ch[slug] = val
        else:                                                # à sa place dans l'ordre du livre
            ordre = [x["slug"] for x in C]
            avant = set(ordre[:ordre.index(slug)])
            pos = max((i + 1 for i, k in enumerate(ch) if k in avant), default=0)
            ch.insert(pos, slug, val)
        p.write_text(livre.rt_texte(y, doc), encoding="utf-8")
        out.update(actuelle=proposee, change=False, main=False, ecrit=True)
    return out


def amorce(ecraser=False):
    """Écrit un premier frise.yaml : le temps du livre, trois échelles, chaque chapitre placé d'après sa période
    (ou marqué « à dater »). Ne remplace jamais un fichier existant, sauf ecraser."""
    p = fichier()
    if p.exists() and not ecraser:
        raise FileExistsError(str(p))
    C = _chapitres_du_livre()
    textes = " ".join(c["periode"] for c in C).lower()
    avant = bool(re.search(r"milliards? d['’]ann[ée]es|millions d['’]ann[ée]es", textes)) and "s à" not in textes \
        and "⁻" not in textes
    lecture = "avant_present" if avant else "depuis_origine"
    T = Temps({"lecture": lecture, "age": "13,8 Ga" if lecture == "depuis_origine" else "4,57 Ga"})
    places = {c["slug"]: place_de(c["periode"], T) for c in C}
    n = sum(1 for x in places.values() if not x.get("non_date"))
    doc = {"titre": "Frise — %s" % (livre.meta().get("titre") or ""),
           "temps": {"origine": "le Big Bang" if lecture == "depuis_origine" else "la formation de la Terre",
                     "age": "13,8 Ga" if lecture == "depuis_origine" else "4,57 Ga", "lecture": lecture,
                     "annee_presente": datetime.date.today().year},
           "echelles": ([{"id": "log", "titre": "depuis le Big Bang (logarithmique)", "type": "log", "variable": "depuis_origine",
                          "domaine": ["1e-44 s", "100 Ga"]},
                         {"id": "lineaire", "titre": "depuis le Big Bang (linéaire)", "type": "lineaire", "variable": "depuis_origine",
                          "domaine": ["0 s", "20 Ga"]}] if lecture == "depuis_origine" else
                        [{"id": "lineaire", "titre": "il y a… (linéaire)", "type": "lineaire", "variable": "avant_present",
                          "domaine": ["il y a 4,6 Ga", "dans 2 Ga"]},
                         {"id": "log", "titre": "il y a… (logarithmique)", "type": "log", "variable": "avant_present",
                          "domaine": ["il y a 4,6 Ga", "il y a 1 an"]}])
           + [{"id": "fixe", "titre": "un intervalle par chapitre", "type": "fixe"}],
           "rendu": "barres", "bandes": [], "reperes": [], "chapitres": places, "frises": []}
    p.write_text(GABARIT + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    return {"fichier": str(p), "chapitres": len(C), "dates": n}
