# -*- coding: utf-8 -*-
"""Les planches d'un chapitre : des dessins (SVG) qui accompagnent le texte, dans LimaLibri, le PDF et le site public.

    chapters/<slug>/planches/<id>.svg      le dessin (l'identifiant : minuscules, chiffres, tirets)
    chapters/<slug>/planches.yaml          facultatif, dans l'ordre des planches :

      escalier-des-masses:
        titre: L'escalier des masses
        legende: La chaîne monte de deux en deux jusqu'à l'hélium 4…
        etat: en construction              # à dessiner, en construction, retenue
        brief: {montre: …, pourquoi: …, sources: [...]}   # ce que Claude a proposé (dessin.py), pour la dessiner
        fiches: [nucleosynthese-primordiale]               # facultatif : les fiches dont elle tire ses données

Une planche est liée aux fiches qu'elle déclare (« fiches » ; un dessin de Claude retenu y ajoute celles que citent
les sources de ses éléments) et à celles que citent les sources de son brief ; la page de la fiche, dans LimaLibri
et sur le site public, les montre en retour. Elle reste une pièce du chapitre (son numéro, sa place dans le texte).

Le texte (récit ou essai) appelle une planche par « @planche/<id> » dans un paragraphe : l'appel devient
« planche 5.1 » (le numéro du chapitre, puis le rang de la planche), et la planche s'insère après ce paragraphe,
la première fois qu'il l'appelle. Les paragraphes et l'alignement du récit ne changent pas. Une planche appelée
sans dessin, ou un planches.yaml illisible, se disent (avertissements) ; rien ne casse.
"""
import re

import yaml

from . import livre

FICHIER = "planches.yaml"
ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
APPEL = re.compile(r"@planche/([a-z0-9][a-z0-9-]*[a-z0-9]|[a-z0-9])")
FICHE = re.compile(r"@fiche/([a-z0-9][a-z0-9-]*[a-z0-9]|[a-z0-9])")
ETATS = ("à dessiner", "en construction", "retenue")


def _meta(slug):
    """({id: {titre, legende, etat}}, [avertissements])."""
    p = livre.dossier(slug) / FICHIER
    if not p.exists():
        return {}, []
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        return {}, ["%s illisible : %s" % (FICHIER, " ".join(str(e).split()))]
    if not isinstance(doc, dict):
        return {}, ["%s : une planche par clé (id: {titre, legende, etat})" % FICHIER]
    M, A = {}, []
    for k, v in doc.items():
        k = str(k)
        if not ID.match(k):
            A.append("identifiant « %s » : minuscules, chiffres et tirets" % k)
            continue
        v = v if isinstance(v, dict) else {}
        etat = str(v.get("etat") or "en construction").strip()
        brief = v.get("brief") if isinstance(v.get("brief"), dict) else {}
        if etat not in ETATS:
            A.append("%s : état « %s » inconnu (%s)" % (k, etat, " ou ".join(ETATS)))
            etat = "en construction"
        M[k] = {"titre": str(v.get("titre") or "").strip(), "legende": " ".join(str(v.get("legende") or "").split()),
                "etat": etat, "brief": {kk: vv for kk, vv in brief.items() if vv},
                "liees": [str(f).removeprefix("@fiche/").strip() for f in (v.get("fiches") or []) if str(f).strip()]
                if isinstance(v.get("fiches"), list) else []}
    return M, A


def liste(slug):
    """{"planches": [{id, numero, titre, legende, etat, fichier, existe}], "avertissements": [...]}."""
    d = livre.dossier(slug)
    M, A = _meta(slug)
    fichiers = sorted(p.stem for p in (d / "planches").glob("*.svg") if ID.match(p.stem)) if (d / "planches").is_dir() else []
    ids = list(M) + [x for x in fichiers if x not in M]
    connues = fiches_connues()
    c = next((x for x in livre.chapitres_seuls() if x["slug"] == slug), {})
    L = []
    for i, k in enumerate(ids, 1):
        m = M.get(k) or {"titre": "", "legende": "", "etat": "en construction", "brief": {}, "liees": []}
        existe = k in fichiers
        if not existe and m["etat"] != "à dessiner":
            A.append("%s : pas de dessin (planches/%s.svg)" % (k, k))
        L.append(dict(m, id=k, titre=m["titre"] or k.replace("-", " ").capitalize(),
                      numero="%s.%d" % (c["numero"], i) if c.get("numero") else str(i),
                      fichier="chapters/%s/planches/%s.svg" % (slug, k), existe=existe, fiches=_fiches(m, connues)))
    return {"planches": L, "avertissements": A}


def fiches_connues():
    d = livre.LIVRE / "kb" / "fiches"
    return {p.stem for p in d.glob("*.md")} if d.is_dir() else set()


def fiches_citees(sources, connues=None):
    """Les fiches que citent des sources, dans l'ordre : « @fiche/<slug> », ou « fiche <slug> » quand c'est une fiche
    du livre (Claude écrit parfois ses sources en clair)."""
    connues = fiches_connues() if connues is None else connues
    out = []
    for t in sources or []:
        t = str(t or "")
        for f in FICHE.findall(t) + [x for x in re.findall(r"\bfiches?\s+«?\s*([a-z0-9][a-z0-9-]*[a-z0-9])", t) if x in connues]:
            if f not in out:
                out.append(f)
    return out


def _fiches(m, connues=None):
    """Les fiches d'une planche : [{slug, lien}] — « déclarée » (planches.yaml, fiches) ou « source » (son brief)."""
    out = {f: "déclarée" for f in m.get("liees") or []}
    for f in fiches_citees((m.get("brief") or {}).get("sources"), connues):
        out.setdefault(f, "source")
    return [{"slug": f, "lien": l} for f, l in out.items()]


def detail(slug, ident):
    """Tout sur une planche, pour sa page : la planche, où le texte l'appelle, les demandes qui l'ont faite,
    ses dessins archivés, le dessin (date, taille)."""
    import os
    from . import reecriture
    p = next((x for x in liste(slug)["planches"] if x["id"] == ident), None)
    if not p:
        raise KeyError(ident)
    appels = []
    for version in ("recit", "essai"):
        if not (livre.dossier(slug) / (version + ".md")).exists():
            continue
        for b, txt in reecriture._blocs(slug, version):
            if ident in APPEL.findall(txt):
                court = " ".join(APPEL.sub(lambda a: "[planche %s]" % p["numero"] if a.group(1) == ident else a.group(0), txt).split())
                i = court.find("[planche %s]" % p["numero"])
                a, z = max(0, i - 170), i + 70
                appels.append({"version": version, "bloc": b,
                               "extrait": ("…" if a else "") + court[a:z] + ("…" if z < len(court) else "")})
    origine = (p.get("brief") or {}).get("demande")
    D = []
    for d in reecriture.liste("_kb"):
        if d.get("type") != "planche" or d.get("chapitre") != slug:
            continue
        cible = (reecriture.lit("_kb", d["id"]).get("cible") or {}).get("planche")
        if cible == ident or d["id"] == origine or ident in ((d.get("decision") or {}).get("planches") or []):
            D.append({k: d.get(k) for k in ("id", "mode", "etat", "cree", "consigne", "modele", "cout_usd", "decision", "titre")})
    D.sort(key=lambda x: x.get("cree") or "")
    # le dessin en place : celui de la dernière demande « dessiner » retenue (sinon : fait à la main)
    fabrique = None
    for x in reversed(D):
        if x["mode"] == "dessiner" and (x.get("decision") or {}).get("proposition") == "posee":
            R = reecriture.lit("_kb", x["id"]).get("resultat") or {}
            fabrique = {"demande": x["id"], "modele": x.get("modele"), "date": (x.get("decision") or {}).get("date"),
                        "cout_usd": x.get("cout_usd"), "consigne": x.get("consigne"),
                        **{k: R.get(k) for k in ("regards", "elements", "blancs", "remarques", "notes", "taille")}}
            break
    h = livre.dossier(slug) / "planches" / "historique"
    archives = []
    for f in sorted(h.glob(ident + "-*.svg"), reverse=True) if h.is_dir() else []:
        t = f.stem[len(ident) + 1:]
        if re.fullmatch(r"\d{8}T\d{6}", t):
            archives.append({"nom": f.name, "date": "%s-%s-%s %s:%s" % (t[:4], t[4:6], t[6:8], t[9:11], t[11:13])})
    dessin = None
    if p["existe"]:
        f = livre.dossier(slug) / "planches" / (ident + ".svg")
        import datetime
        dessin = {"modifie": datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M"),
                  "octets": f.stat().st_size}
    c = next((x for x in livre.chapitres_seuls() if x["slug"] == slug), {})
    return dict(p, chapitre={"slug": slug, "numero": c.get("numero"), "titre": c.get("title")},
                appels=appels, demandes=D, archives=archives, dessin=dessin, fabrique=fabrique)


def archive(slug, nom):
    if not re.fullmatch(r"[a-z0-9-]+-\d{8}T\d{6}\.svg", nom or ""):
        raise KeyError(nom)
    p = livre.dossier(slug) / "planches" / "historique" / nom
    if not p.is_file():
        raise KeyError(nom)
    return p


def lie_fiches(slug, ident, fiches):
    """Les fiches déclarées d'une planche (planches.yaml, « fiches ») ; une liste vide retire la clé."""
    from ruamel.yaml.comments import CommentedMap
    if ident not in {p["id"] for p in liste(slug)["planches"]}:
        raise KeyError(ident)
    F = []
    for f in fiches or []:
        f = str(f).removeprefix("@fiche/").strip()
        if not ID.match(f):
            raise ValueError("fiche « %s » : minuscules, chiffres et tirets" % f)
        if f not in F:
            F.append(f)

    def change(doc):
        e = doc.get(ident)
        if not isinstance(e, dict):
            e = CommentedMap()
            doc[ident] = e
        if F:
            e["fiches"] = F
        else:
            e.pop("fiches", None)
    _ecrit_meta(slug, change)
    return detail(slug, ident)


def toutes():
    """Les planches du livre, chapitre par chapitre : [{chapitre, numero, titre, planches: [...], avertissements}]."""
    out = []
    for c in livre.chapitres_seuls():
        d = livre.dossier(c["slug"])
        if not ((d / FICHIER).exists() or (d / "planches").is_dir()):
            continue
        L = liste(c["slug"])
        if L["planches"] or L["avertissements"]:
            out.append({"chapitre": c["slug"], "numero": c.get("numero"), "titre": c.get("title"), **L})
    return out


def de_fiche(fiche):
    """Les planches liées à une fiche, dans tout le livre : [{chapitre, numero, id, titre, etat, existe, lien}]."""
    out = []
    for c in livre.chapitres_seuls():
        d = livre.dossier(c["slug"])
        if not ((d / FICHIER).exists() or (d / "planches").is_dir()):
            continue
        for p in liste(c["slug"])["planches"]:
            l = next((x["lien"] for x in p["fiches"] if x["slug"] == fiche), None)
            if l:
                out.append({"chapitre": c["slug"], "numero": p["numero"], "id": p["id"], "titre": p["titre"],
                            "etat": p["etat"], "existe": p["existe"], "lien": l})
    return out


def chemin(slug, ident):
    if not ID.match(ident or ""):
        raise KeyError(ident)
    p = livre.dossier(slug) / "planches" / (ident + ".svg")
    if not p.is_file():
        raise KeyError(ident)
    return p


def src_api(slug, ident):
    return "/api/planches/%s/%s.svg" % (slug, ident)


def insere(slug, html, src=src_api):
    """Les appels « @planche/<id> » d'un texte rendu : un renvoi « planche 5.1 », et la planche après le paragraphe."""
    if "@planche/" not in html:
        return html
    P = {p["id"]: p for p in liste(slug)["planches"]}
    vues = set()

    def para(m):
        bloc, fig = m.group(0), []

        def appel(a):
            k = a.group(1)
            p = P.get(k)
            if p and not p["existe"]:
                return '<span class="planche-absente" title="pas encore de dessin">planche %s (à dessiner)</span>' % p["numero"]
            if not p:
                return '<span class="planche-absente" title="pas de planche « %s » dans ce chapitre">planche « %s » ?</span>' % (k, k)
            if k not in vues:
                vues.add(k)
                fig.append(figure(slug, p, src(slug, k)))
            return '<a class="renvoi-planche" href="#planche-%s-%s" data-slug="%s" data-planche="%s">planche %s</a>' % (
                slug, k, slug, k, p["numero"])
        bloc = APPEL.sub(appel, bloc)
        return bloc + "".join(fig)
    return re.sub(r"<(p|li)\b[^>]*>.*?</\1>", para, html, flags=re.S)


def _ecrit_meta(slug, change):
    """planches.yaml relu, changé (change(doc)), réécrit en gardant sa forme (ruamel)."""
    from ruamel.yaml.comments import CommentedMap
    p = livre.dossier(slug) / FICHIER
    y = livre.yaml_rt()
    doc = y.load(p.read_text(encoding="utf-8")) if p.exists() else None
    if not isinstance(doc, dict):
        doc = CommentedMap()
    r = change(doc)
    with open(p, "w", encoding="utf-8") as f:
        y.dump(doc, f)
    return r


def ajoute_propositions(slug, props, demande):
    """Des propositions retenues (dessin.py) : une entrée « à dessiner » chacune, avec son brief. Rend leurs ids."""
    from ruamel.yaml.comments import CommentedMap

    def change(doc):
        ids = []
        for q in props:
            k, n = q["id"], 2
            while k in doc:
                k, n = "%s-%d" % (q["id"], n), n + 1
            e = CommentedMap()
            e["titre"] = q.get("titre") or k
            e["etat"] = "à dessiner"
            b = CommentedMap()
            for kk in ("genre", "montre", "pourquoi", "ou", "manques"):
                if q.get(kk):
                    b[kk] = q[kk]
            if q.get("sources"):
                b["sources"] = list(q["sources"])
            b["demande"] = demande
            e["brief"] = b
            doc[k] = e
            ids.append(k)
        return ids
    ids = _ecrit_meta(slug, change)
    return ids


def ecrit_dessin(slug, ident, svg, titre, legende, demande, fiches=()):
    """Retenir un dessin : planches/<id>.svg (l'ancien dans planches/historique/), le titre et la légende s'ils manquent
    ou si la planche était à dessiner ; « à dessiner » passe « en construction »."""
    if not ID.match(ident or ""):
        raise ValueError("identifiant de planche invalide : %s" % ident)
    d = livre.dossier(slug) / "planches"
    d.mkdir(exist_ok=True)
    f = d / (ident + ".svg")
    archive = None
    if f.exists():
        h = d / "historique"
        h.mkdir(exist_ok=True)
        archive = h / ("%s-%s.svg" % (ident, livre._maintenant()[:19].replace(":", "").replace("-", "")))
        archive.write_bytes(f.read_bytes())
    f.write_text(svg if svg.endswith("\n") else svg + "\n", encoding="utf-8")

    def change(doc):
        from ruamel.yaml.comments import CommentedMap
        e = doc.get(ident)
        if not isinstance(e, dict):
            e = CommentedMap()
            doc[ident] = e
        neuve = str(e.get("etat") or "") in ("", "à dessiner")
        if titre and (neuve or not e.get("titre")):
            e["titre"] = titre
        if legende and (neuve or not e.get("legende")):
            e["legende"] = legende
        if neuve:
            e["etat"] = "en construction"
        F = [str(x) for x in (e.get("fiches") or [])]
        if any(f not in F for f in fiches):              # les fiches que cite le dessin : liées, sans doublon
            e["fiches"] = F + [f for f in fiches if f not in F]
    _ecrit_meta(slug, change)
    return {"fichier": "chapters/%s/planches/%s.svg" % (slug, ident),
            "archive": str(archive.relative_to(livre.LIVRE)) if archive else None}


def change_etat(slug, ident, etat):
    if etat not in ETATS:
        raise ValueError("état inconnu : %s (%s)" % (etat, ", ".join(ETATS)))
    if ident not in {p["id"] for p in liste(slug)["planches"]}:
        raise KeyError(ident)

    def change(doc):
        from ruamel.yaml.comments import CommentedMap
        e = doc.get(ident)
        if not isinstance(e, dict):
            e = CommentedMap()
            doc[ident] = e
        e["etat"] = etat
    _ecrit_meta(slug, change)
    return liste(slug)


def figure(slug, p, src):
    import html as h
    etat = ' <span class="planche-etat">en construction</span>' if p["etat"] != "retenue" else ""
    # l'image ouvre le dessin seul, en grand (sur un téléphone : pour zoomer) ; le PDF retire le lien
    return ('<figure class="planche" id="planche-%s-%s"><a class="planche-lien" href="%s" target="_blank" rel="noopener">'
            '<img src="%s" alt="%s"></a><figcaption><b>Planche %s — %s.</b>%s%s</figcaption></figure>') % (
                slug, p["id"], src, src, h.escape(p["titre"], quote=True), p["numero"], h.escape(p["titre"]),
                " " + h.escape(p["legende"]) if p["legende"] else "", etat)
