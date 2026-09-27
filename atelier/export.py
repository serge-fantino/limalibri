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
        meta, md = kb._lit(s)
        f = {"titre": par[s]["titre"], "meta": meta, "confiance": par[s]["confiance"],
             "entrants": par[s]["entrants"], "chapitres": par[s]["chapitres"]}
        corps = _ancres(s, kb._rendu(md, slugs, heritage))
        citees |= set(re.findall(r'href="#oeuvre-([\w-]+)"', corps))
        etiq = ""
        if f["meta"].get("origine") == "claude":
            etiq = '<p class="etiquette claude">Écrite par Claude · état : %s</p>' % html.escape(f["meta"].get("etat", "?"))
        conf = "".join("<div><b>%s</b> %s</div>" % (html.escape(c["degre"]), _md(c["sur"])) for c in f["confiance"])
        H.append('<section class="fiche" id="fiche-%s"><p class="etiquette">%s</p><h1>%s</h1>%s%s%s%s' % (
            s, s, html.escape(f["titre"]),
            '<p class="sujet">%s</p>' % html.escape(f["meta"]["sujet"]) if f["meta"].get("sujet") and f["meta"]["sujet"] != f["titre"] else "",
            etiq, '<div class="confiance">%s</div>' % conf if conf else "", corps))
        oeuvres = [o["cle"] for o in O.values() if s in o["fiches"]]
        citees |= set(oeuvres)
        pied = []
        if f["entrants"]:
            pied.append("Citée par : " + ", ".join('<a href="#fiche-%s">%s</a>' % (x, html.escape(par[x]["titre"])) for x in f["entrants"] if x in par))
        if f["chapitres"]:
            pied.append("Chapitres : " + ", ".join(html.escape("%s %s" % (c.get("numero") or "", c["title"])) for c in f["chapitres"]))
        if oeuvres:
            pied.append("Œuvres : " + ", ".join('<a href="#oeuvre-%s">%s</a>' % (k, html.escape(_courte(k))) for k in sorted(oeuvres)))
        if pied:
            H.append('<div class="renvois">%s</div>' % "<br>".join(pied))
        H.append("</section>")
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


def chrome():
    for p in [os.environ.get("ATELIER_CHROME", "")] + CHROMES:
        if p and os.path.exists(p):
            return p
    for n in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        w = shutil.which(n)
        if w:
            return w
    return None


async def pdf():
    """Rend (octets du PDF, nom de fichier). RuntimeError si aucun Chrome n'est disponible."""
    exe = chrome()
    if not exe:
        raise RuntimeError("Chrome ou Chromium introuvable : utiliser la version imprimable (⌘P) — "
                           "ou indiquer le programme par la variable ATELIER_CHROME")
    with tempfile.TemporaryDirectory() as tmp:
        src, out = os.path.join(tmp, "kb.html"), os.path.join(tmp, "kb.pdf")
        with open(src, "w", encoding="utf-8") as f:
            f.write(imprimable())
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
    nom = "%s — base de connaissance — %s.pdf" % (m.get("titre", "livre"), datetime.date.today().isoformat())
    return donnees, nom
