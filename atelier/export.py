# -*- coding: utf-8 -*-
"""La base de connaissance en un document : une version imprimable (HTML autonome), et son PDF.

Le document : une couverture (titre du livre, « base de connaissance », synopsis, date, nombre
de fiches), un sommaire par cluster thématique (les communautés du graphe), puis chaque fiche
(sa confiance, son texte, les fiches qui la citent), et en annexe la bibliographie des œuvres
exploitées par les fiches. Tous les liens tiennent dans le document : une fiche vers une autre,
vers une section d'une autre, une citation vers son œuvre, le sommaire vers chaque fiche ; les
DOI restent des liens vers l'extérieur.

Le PDF est imprimé par Chrome (ou Chromium) sans interface, qui garde les hyperliens. Faute de
Chrome, la version imprimable s'imprime depuis le navigateur (⌘P, « Enregistrer au format PDF »).
"""
import os
import re
import html
import shutil
import asyncio
import datetime
import tempfile

import markdown

from . import livre, kb

CHROMES = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           "/Applications/Chromium.app/Contents/MacOS/Chromium",
           "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]

CSS = """
@page{size:A4;margin:18mm 16mm 20mm}
*{box-sizing:border-box}
body{font-family:"Iowan Old Style",Palatino,Georgia,serif;font-size:10.5pt;line-height:1.45;color:#1f1c17;margin:0}
a{color:#8a5a2b;text-decoration:none}
.couverture{height:250mm;display:flex;flex-direction:column;justify-content:center;page-break-after:always;padding:0 8mm}
.couverture .sur{font-family:system-ui,sans-serif;font-size:9pt;letter-spacing:.2em;text-transform:uppercase;color:#8a5a2b}
.couverture h1{font-size:34pt;font-weight:normal;margin:.2em 0 .1em}
.couverture .sous{font-size:14pt;color:#6b6357;margin:0 0 1.2em}
.couverture .kb{font-size:18pt;margin:1.4em 0 .6em}
.couverture .synopsis{font-size:11pt;max-width:140mm;border-left:3px solid #8a5a2b;padding-left:5mm}
.couverture .meta{font-family:system-ui,sans-serif;font-size:9pt;color:#6b6357;margin-top:2.5em}
.couverture img{max-height:70mm;max-width:100mm;margin-bottom:1.5em;object-fit:contain;align-self:flex-start}
.sommaire{page-break-after:always}
.sommaire h2{font-weight:normal;font-size:20pt}
.sommaire h3{font-family:system-ui,sans-serif;font-size:9pt;letter-spacing:.08em;text-transform:uppercase;color:#8a5a2b;margin:1.2em 0 .3em}
.sommaire ol{margin:0;padding-left:2.2em}
.sommaire li{margin:.12em 0}
.sommaire .slug{font-family:system-ui,sans-serif;font-size:8pt;color:#6b6357}
.fiche{page-break-before:always}
.fiche h1{font-size:20pt;font-weight:normal;margin:0 0 .2em}
.fiche .sujet{color:#6b6357;margin:0 0 .6em}
.fiche .etiquette{font-family:system-ui,sans-serif;font-size:8pt;color:#6b6357}
.fiche .claude{color:#c4525a}
.confiance{font-size:9pt;margin:.4em 0 1em;padding:.4em .6em;background:#f3efe6;border-radius:3px}
.confiance b{font-family:system-ui,sans-serif;font-size:8pt;text-transform:uppercase;letter-spacing:.05em}
.fiche h2{font-size:13pt;margin:1.2em 0 .3em}
.fiche h3{font-size:11pt;margin:1em 0 .2em}
h2,h3{page-break-after:avoid}
table{border-collapse:collapse;font-size:9pt;margin:.6em 0}
td,th{border:1px solid #ddd6c8;padding:.2em .4em;vertical-align:top}
blockquote{border-left:3px solid #ddd6c8;margin-left:0;padding-left:.8em;color:#6b6357}
.hors{color:#6b6357;border-bottom:1px dashed #ddd6c8}
.mort{color:#c4525a}
cite a{font-style:normal;border-bottom:1px dotted #8a5a2b}
.renvois{font-family:system-ui,sans-serif;font-size:8.5pt;color:#6b6357;border-top:1px solid #ddd6c8;margin-top:1.5em;padding-top:.4em}
.biblio{page-break-before:always}
.biblio h2{font-weight:normal;font-size:20pt}
.biblio p{margin:.25em 0;padding-left:1.2em;text-indent:-1.2em;font-size:9pt}
.biblio .cle{font-family:system-ui,sans-serif;font-size:7.5pt;color:#6b6357}
"""


def _md(s):
    return re.sub(r"^<p>|</p>$", "", markdown.markdown(s or "").strip())


def _ancres(slug, h):
    """Les ancres d'une fiche, préfixées par son slug (deux fiches ont souvent une section
    « chiffres »), et ses liens réécrits vers les ancres du document."""
    h = re.sub(r'id="fs-([\w-]+)"', lambda m: 'id="fs-%s--%s"' % (slug, m.group(1)), h)
    h = re.sub(r'href="#fiches/([\w-]+)/([\w-]+)"', r'href="#fs-\1--\2"', h)
    h = re.sub(r'href="#fiches/([\w-]+)"', r'href="#fiche-\1"', h)
    h = re.sub(r'<span class="wiki-hors"[^>]*>(.*?)</span>', r'<span class="hors">\1</span>', h)
    h = re.sub(r'<span class="wiki-mort"[^>]*>(.*?)</span>', r'<span class="mort">\1</span>', h)
    h = re.sub(r'<cite data-cle="([\w-]+)">[^<]*</cite>', lambda m: '<cite><a href="#oeuvre-%s">%s</a></cite>' % (
        m.group(1), html.escape(_courte(m.group(1)))), h)
    return re.sub(r' data-(empreinte|section)="[^"]*"', "", h)


def _courte(cle):
    m = re.match(r"^([a-z-]+?)(\d{4})([a-z]?)$", cle)
    return "%s %s%s" % (m.group(1).capitalize(), m.group(2), m.group(3)) if m else cle


def _couverture_img():
    m = livre.meta()
    c = m.get("couverture")
    if not c:
        return ""
    p = livre.LIVRE / c
    if not p.exists():
        return ""
    import base64
    ext = p.suffix.lower().lstrip(".").replace("jpg", "jpeg")
    return '<img src="data:image/%s;base64,%s" alt="">' % (ext, base64.b64encode(p.read_bytes()).decode())


def imprimable():
    m = livre.meta()
    I = kb.index()
    par = {f["slug"]: f for f in I}
    jour = datetime.date.today()
    # le sommaire : par cluster thématique, sinon alphabétique
    try:
        g = kb.graphe()
        groupes = [(" · ".join(c["mots"][:3]) or "cluster %d" % (c["id"] + 1),
                    sorted((n["id"] for n in g["noeuds"] if n["type"] == "fiche" and n["cluster"] == c["id"]),
                           key=lambda s: par[s]["titre"].lower())) for c in g["clusters"]]
    except Exception:                                     # noqa: BLE001
        groupes = [("Toutes les fiches", sorted(par, key=lambda s: par[s]["titre"].lower()))]
    ordre = [s for _, ss in groupes for s in ss]
    O = {o["cle"]: o for o in kb.oeuvres()}
    citees = set()

    H = ['<!doctype html><html lang="%s"><head><meta charset="utf-8">' % (m.get("langue") or "fr"),
         "<title>%s — base de connaissance</title><style>%s</style></head><body>" % (html.escape(m.get("titre", "")), CSS)]
    H.append('<section class="couverture">%s<div class="sur">%s</div><h1>%s</h1>%s'
             '<div class="kb">Base de connaissance</div><div class="synopsis">%s</div>'
             '<div class="meta">%d fiches · %s · générée le %s</div></section>' % (
                 _couverture_img(), html.escape(m.get("auteur") or ""), html.escape(m.get("titre", "")),
                 '<p class="sous">%s</p>' % html.escape(m["sous_titre"]) if m.get("sous_titre") else "",
                 markdown.markdown(m.get("synopsis") or ""), len(I),
                 "%d clusters thématiques" % len(groupes) if len(groupes) > 1 else "",
                 jour.strftime("%d/%m/%Y")))
    H.append('<section class="sommaire"><h2>Sommaire</h2>')
    for nom, ss in groupes:
        H.append("<h3>%s</h3><ol>" % html.escape(nom))
        H += ['<li><a href="#fiche-%s">%s</a> <span class="slug">%s</span></li>' % (s, html.escape(par[s]["titre"]), s)
              for s in ss]
        H.append("</ol>")
    H.append('<h3>Annexe</h3><ol><li><a href="#bibliographie">Bibliographie des œuvres exploitées</a></li></ol></section>')
    heritage, slugs = kb._heritage_md(), set(par)          # une fois pour toutes (kb.fiche les recalcule)
    for s in ordre:
        h, c = fiche_html(s, par, slugs, heritage, O)
        H.append(h)
        citees |= c
    H.append('<section class="biblio" id="bibliographie"><h2>Bibliographie des œuvres exploitées</h2>')
    for k in sorted(citees):
        o = O.get(k)
        if not o:
            H.append('<p id="oeuvre-%s"><span class="cle">%s</span> — référence introuvable</p>' % (k, k))
            continue
        doi = ' <a href="https://doi.org/%s">doi:%s</a>' % (o["doi"], html.escape(o["doi"])) if o.get("doi") else ""
        url = ' <a href="%s">page</a>' % html.escape(o["url"]) if o.get("url") and not o.get("doi") else ""
        ou = ", ".join('<a href="#fiche-%s">%s</a>' % (x, x) for x in o["fiches"] if x in par)
        H.append('<p id="oeuvre-%s">%s%s%s <span class="cle">%s%s</span></p>' % (
            k, _md(o["ref"] or k), doi, url, k, " · " + ou if ou else ""))
    H.append("</section></body></html>")
    return "\n".join(H)


def fiche_html(s, par, slugs, heritage, O, inclus=None, chapitres_liens=False, avant_pied=""):
    """Une fiche en section (confiance, texte, renvois) ; rend (html, clés d'œuvres citées).
    inclus : les fiches présentes dans le document (un lien vers une autre devient du texte, marqué) ;
    chapitres_liens : les chapitres sont dans le document (l'édition complète) — liens vers eux."""
    meta, md = kb._lit(s)
    f = {"titre": par[s]["titre"], "meta": meta, "confiance": par[s]["confiance"],
         "entrants": par[s]["entrants"], "chapitres": par[s]["chapitres"], "liens": par[s].get("liens") or []}
    corps = _ancres(s, kb._rendu(md, slugs, heritage))
    if inclus is not None:                              # un lien vers une fiche absente : du texte, marqué
        corps = re.sub(r'<a href="#(?:fiche-|fs-)([\w-]+?)(?:--[\w-]+)?"[^>]*>(.*?)</a>',
                       lambda m: m.group(0) if m.group(1) in inclus else
                       '<span class="hors" title="fiche hors de cette édition">%s</span>' % m.group(2), corps)
    citees = set(re.findall(r'href="#oeuvre-([\w-]+)"', corps))
    dans = (lambda x: x in par) if inclus is None else (lambda x: x in inclus)
    etiq = ""
    if f["meta"].get("origine") == "claude":
        etiq = '<p class="etiquette claude">Écrite par Claude · état : %s</p>' % html.escape(f["meta"].get("etat", "?"))
    conf = "".join("<div><b>%s</b> %s</div>" % (html.escape(c["degre"]), _md(c["sur"])) for c in f["confiance"])
    sert = ""
    if chapitres_liens and f["chapitres"]:                 # en tête : les chapitres qu'elle sert, pour y revenir
        sert = '<p class="sert">Sert : %s</p>' % " · ".join(
            '<a href="#chap-%s">%s%s</a>' % (c["slug"], "ch. %s — " % c["numero"] if c.get("numero") else "", html.escape(c["title"]))
            for c in f["chapitres"])
    H = ['<section class="fiche" id="fiche-%s"><p class="etiquette">%s</p><h1>%s</h1>%s%s%s%s%s' % (
        s, s, html.escape(f["titre"]),
        '<p class="sujet">%s</p>' % html.escape(f["meta"]["sujet"]) if f["meta"].get("sujet") and f["meta"]["sujet"] != f["titre"] else "",
        sert, etiq, '<div class="confiance">%s</div>' % conf if conf else "", corps)]
    oeuvres = [o["cle"] for o in O.values() if s in o["fiches"]]
    citees |= set(oeuvres)
    pied = []
    if chapitres_liens:
        voisines = [x for x in f["liens"] if dans(x)]
        if voisines:
            pied.append("Voisines : " + ", ".join('<a href="#fiche-%s">%s</a>' % (x, html.escape(par[x]["titre"])) for x in voisines))
    if f["entrants"]:
        pied.append("Citée par : " + ", ".join('<a href="#fiche-%s">%s</a>' % (x, html.escape(par[x]["titre"])) for x in f["entrants"] if dans(x)))
    if f["chapitres"] and not chapitres_liens:
        pied.append("Chapitres : " + ", ".join(html.escape("%s %s" % (c.get("numero") or "", c["title"])) for c in f["chapitres"]))
    if oeuvres:
        pied.append("Œuvres : " + ", ".join('<a href="#oeuvre-%s">%s</a>' % (k, html.escape(_courte(k))) for k in sorted(oeuvres)))
    H.append(avant_pied)
    if pied:
        H.append('<div class="renvois">%s</div>' % "<br>".join(pied))
    H.append("</section>")
    return "".join(H), citees


def chrome():
    for p in [os.environ.get("ATELIER_CHROME", "")] + CHROMES:
        if p and os.path.exists(p):
            return p
    for n in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        w = shutil.which(n)
        if w:
            return w
    return None


async def pdf(quoi="kb", portee="utilisees"):
    """Rend (octets du PDF, nom de fichier) : la base de connaissance (kb), l'essai ou le récit. RuntimeError
    si aucun Chrome n'est disponible."""
    exe = chrome()
    if not exe:
        raise RuntimeError("Chrome ou Chromium introuvable : utiliser la version imprimable (⌘P) — "
                           "ou indiquer le programme par la variable ATELIER_CHROME")
    with tempfile.TemporaryDirectory() as tmp:
        src, out = os.path.join(tmp, "kb.html"), os.path.join(tmp, "kb.pdf")
        with open(src, "w", encoding="utf-8") as f:
            if quoi == "complet":                       # l'essai et la base de connaissance (atelier/compagnon.py)
                from . import compagnon
                f.write(compagnon.imprimable(portee))
            else:
                f.write(version_imprimable(quoi) if quoi in livre.VERSIONS else imprimable())
        proc = await asyncio.create_subprocess_exec(
            exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
            "--user-data-dir=" + os.path.join(tmp, "profil"), "--print-to-pdf=" + out, "file://" + src,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        # Chrome écrit le PDF puis reste parfois ouvert : on attend son « bytes written », et on le ferme
        err = []
        try:
            async def lit():
                while True:
                    ligne = await proc.stderr.readline()
                    if not ligne:
                        return
                    err.append(ligne.decode(errors="replace"))
                    if "bytes written to file" in err[-1]:
                        return
            await asyncio.wait_for(lit(), timeout=180)
        except asyncio.TimeoutError:
            raise RuntimeError("Chrome n'a pas fini en trois minutes")
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
        if not os.path.exists(out):
            raise RuntimeError("Chrome n'a pas produit de PDF : %s" % "".join(err)[-300:])
        with open(out, "rb") as f:
            donnees = f.read()
    m = livre.meta()
    nom = "%s — %s — %s.pdf" % (m.get("titre", "livre"), _nom_version(quoi) if quoi in livre.VERSIONS else
                                "essai et base de connaissance" if quoi == "complet" else "base de connaissance",
                                datetime.date.today().isoformat())
    return donnees, nom


# ------------------------------------------------------------------ l'essai, le récit

# Une version (l'essai, le récit) en un document : la page de garde du livre, la table des matières (le plan), puis chaque
# partie — son sens, son arc, sa question, la liste de ses chapitres — et ses chapitres. Un chapitre
# est rendu selon son avancement : le synopsis seul (rien d'écrit), le squelette de l'essai (des
# sections « à écrire »), le storyboard du récit (ses plans et leurs micro-récits), ou le texte,
# avec son statut (brief, brouillon, en relecture, validé) et l'état du harnais. La numérotation
# (réglage de l'essai) ne vaut que pour l'essai. En annexe, la bibliographie des œuvres citées.

STATUTS_LIB = {"outline": "brief", "draft": "brouillon", "revised": "en relecture", "locked": "validé"}

CSS_ESSAI = """
.toc{page-break-after:always}
.toc h2{font-weight:normal;font-size:20pt}
.toc .partie{font-family:system-ui,sans-serif;font-size:9pt;letter-spacing:.08em;text-transform:uppercase;color:#8a5a2b;margin:1.1em 0 .3em}
.toc .partie a{color:#8a5a2b}
.toc ol{list-style:none;margin:0;padding:0}
.toc li{display:flex;gap:.6em;align-items:baseline;margin:.18em 0}
.toc .n{min-width:1.6em;text-align:right;color:#6b6357}
.toc .per{font-size:9pt;color:#6b6357}
.toc .st{margin-left:auto}
.toc ol.toc-sec{margin:0 0 .3em 2.2em;font-size:9pt}
.toc ol.toc-sec li{margin:.05em 0}
.toc ol.toc-sec .n{min-width:2.6em;text-align:left;color:#8a5a2b}
.toc ol.toc-sec a{color:#1f1c17}
.st{font-family:system-ui,sans-serif;font-size:7.5pt;border:1px solid #ddd6c8;border-radius:3px;padding:0 .35em;white-space:nowrap;color:#6b6357}
.st.synopsis,.st.brief{border-color:#c0622f;color:#c0622f}
.st.squelette{border-color:#e8b64a;color:#a4561b}
.st.brouillon{border-color:#8a5a2b;color:#8a5a2b}
.st.relecture{border-color:#2d5f8a;color:#2d5f8a}
.st.valide{border-color:#2f6f4f;color:#2f6f4f}
.partie-page{page-break-before:always;padding-top:30mm}
.partie-page .sur{font-family:system-ui,sans-serif;font-size:9pt;letter-spacing:.2em;text-transform:uppercase;color:#8a5a2b}
.partie-page h1{font-size:28pt;font-weight:normal;margin:.2em 0 .6em}
.partie-page .champ{margin:.5em 0}
.partie-page .champ b{font-family:system-ui,sans-serif;font-size:8pt;text-transform:uppercase;letter-spacing:.06em;color:#6b6357;display:block}
.partie-page ol{margin:1.2em 0 0;padding-left:1.6em}
.chapitre{page-break-before:always}
.chapitre > header .n{font-family:system-ui,sans-serif;font-size:9pt;letter-spacing:.15em;text-transform:uppercase;color:#8a5a2b}
.chapitre > header h1{font-size:22pt;font-weight:normal;margin:.15em 0 .1em}
.chapitre > header .per{font-style:italic;color:#6b6357;margin:0 0 .4em}
.chapitre > header .etat{display:flex;gap:.5em;flex-wrap:wrap;align-items:center;margin:.3em 0 1.2em;font-family:system-ui,sans-serif;font-size:8pt;color:#6b6357;border-bottom:1px solid #ddd6c8;padding-bottom:.6em}
.chapitre .synopsis{border-left:3px solid #c0622f;padding-left:5mm;margin:1em 0}
.plan-sb{margin:1.1em 0;page-break-inside:avoid}
.plan-sb h2{font-size:13pt;font-weight:normal;margin:0 0 .15em}
.plan-sb h2 .id{font-family:system-ui,sans-serif;font-size:9pt;color:#8a5a2b;margin-right:.5em}
.plan-sb .cadre{font-family:system-ui,sans-serif;font-size:8pt;color:#6b6357;margin:0 0 .3em}
.plan-sb ol{margin:.2em 0 0;padding-left:1.4em}
.plan-sb li{font-style:italic;margin:.15em 0}
.st.storyboard{border-color:#e8b64a;color:#a4561b}
.chapitre .question{font-style:italic}
.chapitre .avertit{font-family:system-ui,sans-serif;font-size:8.5pt;color:#6b6357}
.chapitre h2{font-size:14pt;font-weight:normal;margin:1.4em 0 .4em}
.chapitre h3{font-size:12pt;margin:1.1em 0 .3em}
.chapitre h4{font-size:10.5pt;margin:1em 0 .2em}
.chapitre.numerote h2[data-num]::before,.chapitre.numerote h3[data-num]::before,.chapitre.numerote h4[data-num]::before{content:attr(data-num) "\\00a0\\00a0";color:#8a5a2b}
.chapitre.numerote-par p[data-num]::before{content:attr(data-num) "\\00a0";font-family:system-ui,sans-serif;font-size:7pt;color:#8a5a2b}
.chapitre p{text-align:justify;hyphens:auto}
.chapitre p em:only-child{color:#6b6357}
.chapitre .footnote{font-size:8.5pt;border-top:1px solid #ddd6c8;margin-top:1.5em}
.chapitre .footnote hr{display:none}
sup a{color:#8a5a2b}
.renvoi-chap{color:#8a5a2b;border-bottom:1px dotted #8a5a2b;white-space:nowrap}
.renvoi-ptr{white-space:nowrap}
.renvoi-mort{color:#c4525a}
"""


def _statut_chapitre(c, a):
    """(niveau, étiquettes) : niveau synopsis | squelette | texte | origine."""
    base = STATUTS_LIB.get(c.get("status") or "outline", c.get("status") or "brief")
    if a["niveau"] == "synopsis":
        return [("synopsis", "synopsis seul"), ("brief" if base == "brief" else base, base)]
    if a["niveau"] == "squelette":
        return [("squelette", "squelette · %d section(s) à écrire" % a["a_ecrire"])]
    if a["niveau"] == "storyboard":
        return [("storyboard", "storyboard · %d plan(s)" % a["plans"])]
    E = [({"brief": "brief", "brouillon": "brouillon", "en relecture": "relecture", "validé": "valide"}.get(base, "brouillon"), base)]
    if a["niveau"] == "origine":
        E.append(("", "texte d'origine, hors atelier"))
    if a.get("harnais"):
        E.append(("valide" if a["harnais"]["ok"] else "", a["harnais"]["lib"]))
    return E


def _avancement(c, version="essai"):
    """Ce qu'on peut montrer d'un chapitre dans une version : son texte, son squelette (essai), son
    storyboard (récit), ou son synopsis."""
    d = livre.dossier(c["slug"])
    pe = d / (version + ".md")
    brut = pe.read_text(encoding="utf-8") if pe.exists() else ""
    if brut.strip():
        paras = [l for l in brut.split("\n\n") if l.strip() and not l.lstrip().startswith("#")]
        vides = [l for l in paras if l.strip().startswith("*À écrire")]
        if paras and len(vides) == len(paras):
            return {"niveau": "squelette", "a_ecrire": len(vides)}
        a = {"niveau": "texte", "mots": len(re.sub(r"\^[a-z0-9]+|\[\^[^\]]+\]", "", brut).split())}
        try:
            from . import validation
            r = validation.etat(c["slug"])["resume"].get(version) or {}
            n = sum(v for k, v in r.items() if isinstance(v, int))
            if r.get("valide"):
                a["harnais"] = {"ok": r.get("valide") == n, "lib": "harnais : %d/%d paragraphes validés" % (r["valide"], n)}
        except Exception:                                  # noqa: BLE001 — pas de cadre : pas d'état
            pass
        return a
    try:
        h = livre.texte(c["slug"], version)["html"]      # l'héritage : le texte d'avant l'atelier
        h = re.sub(r'<div class="footnote">.*$', "", h, flags=re.S)
        return {"niveau": "origine", "mots": len(re.sub(r"<[^>]+>", " ", h).split())}
    except KeyError:
        pass
    if version == "recit" and c.get("beats"):
        return {"niveau": "storyboard", "plans": len(c["beats"])}
    return {"niveau": "synopsis"}


def _chapitre_html(c, version="essai"):
    """Le texte d'un chapitre, sans l'en-tête que livre.texte lui met, ancres préfixées par le slug."""
    h = livre.texte(c["slug"], version)["html"]
    h = re.sub(r"^\s*<h1>.*?</h1>\s*(<p><em>.*?</em></p>\s*)?(<hr\s*/?>)?", "", h, count=1, flags=re.S)
    s = c["slug"]
    h = re.sub(r'id="sec-([\w-]+)"', r'id="sec-%s--\1"' % s, h)
    h = re.sub(r'href="#sec-([\w-]+)"', r'href="#sec-%s--\1"' % s, h)
    h = re.sub(r'(id|href)="#?fn(ref)?:', lambda m: '%s="%sfn%s:%s-' % (m.group(1), "#" if m.group(1) == "href" else "", m.group(2) or "", s), h)
    h = re.sub(r'<a class="renvoi-chap" href="#([\w-]+)/essai/texte"', r'<a class="renvoi-chap" href="#chap-\1"', h)
    h = re.sub(r' data-(block|sec|section|chap)="[^"]*"', "", h)
    return re.sub(r'<cite data-cle="([\w-]+)">[^<]*</cite>',
                  lambda m: '<cite><a href="#oeuvre-%s">%s</a></cite>' % (m.group(1), html.escape(_courte(m.group(1)))), h)


def _nom_version(version):
    return ((livre.meta().get("versions") or {}).get(version) or {}).get("titre") or version.capitalize()


def _storyboard_html(beats):
    L = []
    for b in beats:
        cadre = " · ".join(str(b[k]) for k in ("lieu", "temps", "ambiance") if b.get(k))
        recits = "".join("<li>%s</li>" % html.escape(" ".join(str(r).split())) for r in b.get("recits") or [])
        L.append('<div class="plan-sb"><h2><span class="id">%s</span>%s</h2>%s%s</div>' % (
            html.escape(str(b.get("id", ""))), html.escape(b.get("title") or ""),
            '<p class="cadre">%s</p>' % html.escape(cadre) if cadre else "", "<ol>%s</ol>" % recits if recits else ""))
    return "".join(L)


def essai_imprimable():
    return version_imprimable("essai")


def version_imprimable(version="essai", compagnon=None):
    """compagnon (atelier/compagnon.py) : l'édition « essai + base de connaissance » — il ajoute un intitulé
    de couverture, des entrées de sommaire, un encart à la fin de chaque chapitre, l'annexe (la carte du
    livre, les fiches) et remplace la bibliographie par une bibliographie commune."""
    from . import plan
    if version not in livre.VERSIONS:
        raise KeyError(version)
    m = livre.meta()
    P = plan.lit()
    tous = {c["slug"]: c for c in livre.chapitres()}
    prefaces = [c for c in livre.structure().get("prefaces") or [] if version in (c.get("versions") or [version])]
    mode = (m.get("numerotation_essai") or "aucune") if version == "essai" else "aucune"
    nom = _nom_version(version) + (compagnon.intitule if compagnon else "")
    jour = datetime.date.today()
    # l'avancement de chaque chapitre, une fois
    chapitres = [dict(c, numero=None, partie=None) for c in prefaces]
    for p in P["parties"]:
        for c in p["chapitres"]:
            chapitres.append(dict(c, numero=tous.get(c["slug"], {}).get("numero"), partie=p["id"]))
    for c in chapitres:
        br = {}
        bp = livre.dossier(c["slug"]) / "brief.yaml"
        if bp.exists():
            import yaml
            br = yaml.safe_load(bp.read_text(encoding="utf-8")) or {}
        c.setdefault("synopsis", br.get("synopsis"))
        c.setdefault("question", br.get("question"))
        c["beats"] = br.get("beats") or []
        c["av"] = _avancement(c, version)
        c["etiq"] = _statut_chapitre(c, c["av"])
        c["corps"] = _chapitre_html(c, version) if c["av"]["niveau"] in ("texte", "origine", "squelette") else None
        # les sections numérotées (premier niveau), pour la table des matières quand la numérotation est active
        c["sections"] = re.findall(r'<h2 id="(sec-[\w-]+)" data-num="([^"]+)"[^>]*>(.*?)</h2>', c["corps"] or "", flags=re.S)
    ecrits = sum(1 for c in chapitres if c["av"]["niveau"] in ("texte", "origine"))
    mots = sum(c["av"].get("mots", 0) for c in chapitres)
    citees = set()
    for c in chapitres:
        citees.update(re.findall(r'href="#oeuvre-([\w-]+)"', c["corps"] or ""))

    def badges(c):
        return "".join('<span class="st %s">%s</span>' % (k, html.escape(v)) for k, v in c["etiq"])

    def num(c):
        return "%s" % c["numero"] if c.get("numero") else ""

    H = ['<!doctype html><html lang="%s"><head><meta charset="utf-8">' % (m.get("langue") or "fr"),
         "<title>%s — %s</title><style>%s%s%s</style></head><body>" % (html.escape(m.get("titre", "")), html.escape(nom.lower()), CSS, CSS_ESSAI,
                                                                         compagnon.css if compagnon else "")]
    # la page de garde
    H.append('<section class="couverture">%s<div class="sur">%s</div><h1>%s</h1>%s<div class="kb">%s</div>'
             '<div class="synopsis">%s</div><div class="meta">%d chapitres · %d rédigés%s · état au %s</div></section>' % (
                 _couverture_img(), html.escape(m.get("auteur") or ""), html.escape(m.get("titre", "")),
                 '<p class="sous">%s</p>' % html.escape(m["sous_titre"]) if m.get("sous_titre") else "", html.escape(nom),
                 markdown.markdown(P["livre"].get("idee") or m.get("synopsis") or ""), len(chapitres), ecrits,
                 " · %s mots" % format(mots, ",").replace(",", " ") if mots else "", jour.strftime("%d/%m/%Y")))
    # la table des matières : le plan
    H.append('<section class="toc"><h2>Table des matières</h2>')

    def ligne(c):
        secs = ""
        if mode != "aucune" and c["sections"]:
            secs = '<ol class="toc-sec">%s</ol>' % "".join(
                '<li><span class="n">%s</span><a href="#%s">%s</a></li>' % (n, i, re.sub(r"<[^>]+>", "", t).strip())
                for i, n, t in c["sections"])
        return '<li><span class="n">%s</span><span><a href="#chap-%s">%s</a>%s</span>%s</li>%s' % (
            num(c), c["slug"], html.escape(c.get("title") or c["slug"]),
            ' <span class="per">%s</span>' % html.escape(c["periode"]) if c.get("periode") else "",
            '<span class="st-groupe st">%s</span>' % html.escape(c["etiq"][0][1]) if c["etiq"] else "", secs)
    if prefaces:
        H.append("<ol>%s</ol>" % "".join(ligne(c) for c in chapitres if c["partie"] is None))
    for i, p in enumerate(P["parties"], 1):
        H.append('<div class="partie"><a href="#partie-%s">%s · %s</a></div><ol>%s</ol>' % (
            p["id"], _romain(i), html.escape(p["title"] or ""), "".join(ligne(c) for c in chapitres if c["partie"] == p["id"])))
    if compagnon:
        H.append(compagnon.sommaire())
    H.append('<div class="partie"><a href="#bibliographie">Bibliographie</a></div></section>' if citees or version == "essai" or compagnon else "</section>")

    def chapitre(c):
        a = c["av"]
        classes = "chapitre" + (" numerote" if mode in ("sections", "paragraphes") else "") + (" numerote-par" if mode == "paragraphes" else "")
        tete = '<header><div class="n">%s</div><h1>%s</h1>%s<div class="etat">%s%s</div></header>' % (
            "Chapitre %s" % num(c) if num(c) else "", html.escape(c.get("title") or c["slug"]),
            '<p class="per">%s</p>' % html.escape(c["periode"]) if c.get("periode") else "", badges(c),
            " · %d mots" % a["mots"] if a.get("mots") else "")
        if a["niveau"] in ("texte", "origine", "squelette"):
            corps = c["corps"]
            if a["niveau"] == "squelette":
                corps = '<p class="avertit">Le squelette de l\'essai : les sections prévues, chacune avec ce qu\'elle doit établir.</p>' + corps
        elif a["niveau"] == "storyboard":
            corps = ""
            if c.get("synopsis"):
                corps += '<div class="synopsis">%s</div>' % markdown.markdown(c["synopsis"])
            corps += '<p class="avertit">Le storyboard : les plans du chapitre, chacun avec son cadre et ses micro-récits, dans l\'ordre.</p>'
            corps += _storyboard_html(c["beats"])
        else:
            corps = ""
            if c.get("synopsis"):
                corps += '<div class="synopsis">%s</div>' % markdown.markdown(c["synopsis"])
            if c.get("question"):
                corps += '<p class="question">%s</p>' % html.escape(c["question"])
            if not corps:
                corps = '<p class="avertit">Ni texte ni synopsis pour l\'instant.</p>'
        if compagnon:
            corps += compagnon.apres_chapitre(c)
        return '<section class="%s" id="chap-%s">%s%s</section>' % (classes, c["slug"], tete, corps)

    for c in chapitres:
        if c["partie"] is None:
            H.append(chapitre(c))
    for i, p in enumerate(P["parties"], 1):
        champs = "".join('<div class="champ"><b>%s</b>%s</div>' % (lib, markdown.markdown(p[k])) for k, lib in
                         (("sens", "le sens"), ("arc", "l'arc"), ("question", "la question")) if p.get(k))
        liste = "".join('<li><a href="#chap-%s">%s</a> %s</li>' % (c["slug"], html.escape(c.get("title") or c["slug"]), badges(c))
                        for c in chapitres if c["partie"] == p["id"])
        H.append('<section class="partie-page" id="partie-%s"><div class="sur">Partie %s</div><h1>%s</h1>%s<ol>%s</ol></section>' % (
            p["id"], _romain(i), html.escape(p["title"] or ""), champs, liste))
        for c in chapitres:
            if c["partie"] == p["id"]:
                H.append(chapitre(c))
    if compagnon:                                   # l'annexe, puis une bibliographie commune
        H.append(compagnon.annexe())
        H.append(compagnon.bibliographie(citees, chapitres))
        H.append(compagnon.script())
        H.append("</body></html>")
        return "\n".join(H)
    # la bibliographie des œuvres citées (le récit n'en a pas, d'ordinaire)
    if not citees and version != "essai":
        H.append("</body></html>")
        return "\n".join(H)
    O = {o["cle"]: o for o in kb.oeuvres()} if (livre.LIVRE / "kb").exists() else {}
    refs = livre.sources()
    H.append('<section class="biblio" id="bibliographie"><h2>Bibliographie</h2>')
    if not citees:
        H.append('<p class="cle">Aucune œuvre citée dans le texte pour l\'instant.</p>')
    for k in sorted(citees):
        o = O.get(k) or {}
        ref = o.get("ref") and _md(o["ref"]) or refs.get(k)
        doi = ' <a href="https://doi.org/%s">doi:%s</a>' % (o["doi"], html.escape(o["doi"])) if o.get("doi") else ""
        H.append('<p id="oeuvre-%s">%s%s <span class="cle">%s</span></p>' % (k, ref or "<em>référence introuvable</em>", doi, k))
    H.append("</section></body></html>")
    return "\n".join(H)


def _romain(n):
    V = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    s = ""
    for v, r in V:
        while n >= v:
            s, n = s + r, n - v
    return s
