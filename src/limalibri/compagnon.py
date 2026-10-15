# -*- coding: utf-8 -*-
"""L'édition « essai + base de connaissance » : l'essai, et en annexe les fiches qui le portent, reliés.

Le document part de l'essai imprimable (limalibri/export.py, version_imprimable) et y ajoute :
  · à la fin de chaque chapitre, « Pour aller plus loin » : ses fiches (son brief), les fiches qui
    partagent ses sources, et une mini-carte — le chapitre, ses fiches, leurs voisines ;
  · l'annexe : la carte du livre (une carte par cluster thématique : les chapitres à gauche dans l'ordre
    du livre, les fiches à droite, les liens), puis les fiches, par cluster — chacune dit en tête les
    chapitres qu'elle sert (des liens), et en pied ses voisines et qui la cite ;
  · une bibliographie commune : chaque œuvre dit les chapitres et les fiches qui la citent.
L'essai ne nomme jamais ses fiches (règle R8) : cet appareil est hors du texte, en encart et en annexe.

Portée : « utilisees » (les fiches des briefs des chapitres) ou « toutes ». Un lien vers une fiche hors
de l'édition devient du texte, marqué. Les cartes sont calculées ici (une disposition fixe, en mm) : les
traits en SVG, les étiquettes en liens HTML posés dessus — le PDF de Chrome les garde cliquables. La
version HTML y ajoute un peu de vie : survoler un nœud allume ses liens et éteint le reste.
"""
import re
import html
import collections

from . import livre, kb, export

LARGEUR = 178           # mm : la largeur utile d'une page A4 (marges de 16 mm)
LIGNE = 4.6             # mm : la hauteur d'une ligne d'étiquette
COULEURS = ["#8a5a2b", "#2d5f8a", "#2f6f4f", "#7a6ad0", "#c0622f", "#a4561b", "#5b7a2f", "#8a2b5a", "#2b7a8a", "#6b6357"]

CSS = """
.plus-loin{margin-top:2em;border-top:2px solid #ddd6c8;padding-top:.6em;page-break-inside:avoid;font-family:system-ui,sans-serif;font-size:8.5pt}
.plus-loin h2{font-family:system-ui,sans-serif;font-size:9pt;letter-spacing:.12em;text-transform:uppercase;color:#8a5a2b;font-weight:normal;margin:0 0 .4em}
.plus-loin p{text-align:left;margin:.25em 0}
.plus-loin .lib{color:#6b6357}
.pastille-c{display:inline-block;width:2.2mm;height:2.2mm;border-radius:50%;margin-right:1mm;vertical-align:middle}
.carte{position:relative;margin:.8em 0 1.2em;page-break-inside:avoid}
.carte svg{position:absolute;left:0;top:0;overflow:visible}
.carte path{fill:none;stroke:#8a5a2b;stroke-width:.22;opacity:.45}
.carte path.ff{stroke:#2d5f8a;stroke-dasharray:.8 .6;opacity:.35}
.carte .nd{position:absolute;display:block;font-family:system-ui,sans-serif;font-size:6.6pt;line-height:4.4mm;height:4.4mm;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#1f1c17;text-decoration:none}
.carte .nd.ch{text-align:right;color:#8a5a2b;font-weight:600}
.carte .nd.ici{background:#f3efe6;border-radius:2px;padding:0 1mm}
.carte .nd .num{color:#6b6357;font-weight:normal}
.carte.focus path{opacity:.06}
.carte.focus path.on{opacity:.95;stroke-width:.45}
.carte.focus .nd{opacity:.35}
.carte.focus .nd.on{opacity:1}
.carte-cluster h3{font-family:system-ui,sans-serif;font-size:10pt;margin:1.2em 0 .1em}
.carte-cluster .mut{font-family:system-ui,sans-serif;font-size:8pt;color:#6b6357;margin:0}
.annexe-tete{page-break-before:always}
.annexe-tete h1{font-size:24pt;font-weight:normal;margin:0 0 .3em}
.annexe-tete .intro{font-size:10pt;color:#4a4339}
table.clusters{width:100%;font-family:system-ui,sans-serif;font-size:8pt}
table.clusters td{vertical-align:top}
.fiche .sert{font-family:system-ui,sans-serif;font-size:8.5pt;margin:0 0 .6em;padding:.3em .5em;border-left:3px solid #8a5a2b;background:#faf8f4}
.cluster-page{page-break-before:always;padding-top:20mm}
.cluster-page .sur{font-family:system-ui,sans-serif;font-size:9pt;letter-spacing:.2em;text-transform:uppercase;color:#8a5a2b}
.cluster-page h1{font-size:22pt;font-weight:normal;margin:.2em 0 .6em}
.biblio .ou{font-family:system-ui,sans-serif;font-size:7.5pt;color:#6b6357}
@media screen{body{max-width:200mm;margin:0 auto;padding:0 6mm}}
"""

SCRIPT = """<script>
// la carte, vivante (version HTML) : survoler un nœud allume ses liens et ses voisins
document.querySelectorAll('.carte').forEach(function (c) {
  c.addEventListener('mouseover', function (e) {
    var n = e.target.closest('[data-n]'); if (!n) return;
    var id = n.getAttribute('data-n'), voisins = {};
    voisins[id] = 1;
    c.classList.add('focus');
    c.querySelectorAll('path').forEach(function (p) {
      var on = p.getAttribute('data-a') === id || p.getAttribute('data-b') === id;
      p.classList.toggle('on', on);
      if (on) { voisins[p.getAttribute('data-a')] = 1; voisins[p.getAttribute('data-b')] = 1; }
    });
    c.querySelectorAll('[data-n]').forEach(function (x) { x.classList.toggle('on', !!voisins[x.getAttribute('data-n')]); });
  });
  c.addEventListener('mouseleave', function () { c.classList.remove('focus'); });
});
</script>"""


class Compagnon:
    def __init__(self, portee="utilisees"):
        self.portee = portee if portee in ("utilisees", "toutes") else "utilisees"
        self.intitule = " et base de connaissance"
        self.css = CSS
        I = kb.index()
        self.par = {f["slug"]: f for f in I}
        self.chapitres_fiches = {s: [x for x in c["fiches"] if x in self.par]
                                 for s, c in kb._fiches_de_tous_les_chapitres().items()}
        utilisees = {x for L in self.chapitres_fiches.values() for x in L}
        self.inclus = set(self.par) if self.portee == "toutes" else utilisees
        try:
            g = kb.graphe()
            self.cluster = {n["id"]: n["cluster"] for n in g["noeuds"] if n["type"] == "fiche"}
            self.clusters = [c for c in g["clusters"] if any(self.cluster.get(x) == c["id"] for x in self.inclus)]
        except Exception:                                   # noqa: BLE001 — sans graphe : un seul groupe
            self.cluster = {x: 0 for x in self.par}
            self.clusters = [{"id": 0, "mots": ["toutes les fiches"]}]
        self.ordre = [x for c in self.clusters for x in sorted((x for x in self.inclus if self.cluster.get(x) == c["id"]),
                                                               key=lambda s: self.par[s]["titre"].lower())]
        self.chapitres = {c["slug"]: c for c in livre.chapitres()}
        self.rang = {c["slug"]: i for i, c in enumerate(livre.chapitres())}
        self.O = {o["cle"]: o for o in kb.oeuvres()}
        self.citees_fiches = {}                          # clé d'œuvre -> fiches qui la citent (rempli par annexe)

    # ---------------------------------------------------------------- de quoi nommer
    def nom_cluster(self, c):
        return " · ".join(c.get("mots", [])[:3]) or "cluster %d" % (c["id"] + 1)

    def couleur(self, slug):
        return COULEURS[self.cluster.get(slug, 0) % len(COULEURS)]

    def pastille(self, slug):
        return '<span class="pastille-c" style="background:%s"></span>' % self.couleur(slug)

    def lien_fiche(self, slug):
        return '%s<a href="#fiche-%s">%s</a>' % (self.pastille(slug), slug, html.escape(self.par[slug]["titre"]))

    def lien_chapitre(self, slug):
        c = self.chapitres.get(slug, {})
        return '<a href="#chap-%s">%s%s</a>' % (slug, "ch. %s — " % c["numero"] if c.get("numero") else "",
                                                 html.escape(c.get("title") or slug))

    # ---------------------------------------------------------------- les cartes
    def _carte(self, gauche, milieu, droite, aretes, ici=None, larg=(46, 66, 56)):
        """Une carte en trois colonnes (droite facultative) : [(id, libellé, href, classe)] ; aretes : (a, b, sorte).
        Les colonnes ont la même hauteur ; leurs lignes s'y répartissent."""
        cols = [L for L in (gauche, milieu, droite) if L]
        n = max(len(L) for L in cols)
        H = round(n * LIGNE + 1, 1)
        lg, lm, ld = larg
        ecart = (LARGEUR - lg - lm - (ld if droite else 0)) / (2 if droite else 1)
        xs = [0, lg + ecart, lg + ecart + lm + ecart]
        pos, E = {}, []

        def place(L, k, largeur, classe):
            pas = H / max(len(L), 1)
            for i, (nid, lib, href, cl) in enumerate(L):
                y = round(i * pas + (pas - LIGNE) / 2, 2)
                pos[nid] = (xs[k], y, largeur)
                E.append('<a class="nd %s%s%s" data-n="%s" href="%s" style="left:%smm;top:%smm;width:%smm" title="%s">%s</a>' % (
                    classe, " " + cl if cl else "", " ici" if nid == ici else "", html.escape(nid), href, xs[k], y, largeur,
                    html.escape(re.sub(r"<[^>]+>", "", lib)), lib))
        place(gauche, 0, lg, "ch" if gauche and gauche[0][0].startswith("ch:") else "")
        place(milieu, 1, lm, "")
        if droite:
            place(droite, 2, ld, "")
        P = []
        for a, b, sorte in aretes:
            if a not in pos or b not in pos:
                continue
            (xa, ya, wa), (xb, yb, wb) = pos[a], pos[b]
            ya, yb = ya + LIGNE / 2, yb + LIGNE / 2
            if xa == xb:                                   # dans la même colonne : un arc à gauche
                x = xa - 0.6
                dx = min(18, 2 + abs(yb - ya) * 0.35)
                d = "M%.1f %.1f C%.1f %.1f %.1f %.1f %.1f %.1f" % (x, ya, x - dx, ya, x - dx, yb, x, yb)
            else:
                if xa > xb:
                    (xa, ya, wa), (xb, yb, wb) = (xb, yb, wb), (xa, ya, wa)
                x1, x2 = xa + wa + 0.8, xb - 0.8
                m = (x1 + x2) / 2
                d = "M%.1f %.1f C%.1f %.1f %.1f %.1f %.1f %.1f" % (x1, ya, m, ya, m, yb, x2, yb)
            P.append('<path class="%s" data-a="%s" data-b="%s" d="%s"/>' % (sorte, html.escape(a), html.escape(b), d))
        return ('<div class="carte" style="height:%smm;width:%smm"><svg viewBox="0 0 %s %s" style="width:%smm;height:%smm">%s</svg>%s</div>'
                % (H, LARGEUR, LARGEUR, H, LARGEUR, H, "".join(P), "".join(E)))

    def _noeud_fiche(self, s):
        return ("f:" + s, '%s%s' % (self.pastille(s), html.escape(self.par[s]["titre"])), "#fiche-" + s, "")

    def _noeud_chapitre(self, slug):
        c = self.chapitres.get(slug, {})
        lib = '%s<span class="num">%s</span>' % (html.escape(c.get("title") or slug), " · %s" % c["numero"] if c.get("numero") else "")
        return ("ch:" + slug, lib, "#chap-" + slug, "")

    def carte_chapitre(self, slug):
        """Le chapitre, ses fiches, et leurs voisines (les fiches qu'elles citent ou qui les citent)."""
        fs = [x for x in self.chapitres_fiches.get(slug, []) if x in self.inclus]
        if not fs:
            return ""
        compte = collections.Counter()
        for x in fs:
            for y in (self.par[x].get("liens") or []) + (self.par[x].get("entrants") or []):
                if y in self.inclus and y not in fs:
                    compte[y] += 1
        voisines = [y for y, _ in sorted(compte.items(), key=lambda kv: (-kv[1], self.par[kv[0]]["titre"].lower()))[:10]]
        fs = sorted(fs, key=lambda x: (self.cluster.get(x, 0), self.par[x]["titre"].lower()))
        aretes = [("ch:" + slug, "f:" + x, "") for x in fs]
        for x in fs:
            for y in self.par[x].get("liens") or []:
                if y in voisines or y in fs:
                    aretes.append(("f:" + x, "f:" + y, "ff"))
            for y in self.par[x].get("entrants") or []:
                if y in voisines:
                    aretes.append(("f:" + y, "f:" + x, "ff"))
        return self._carte([self._noeud_chapitre(slug)], [self._noeud_fiche(x) for x in fs],
                           [self._noeud_fiche(y) for y in voisines], aretes, ici="ch:" + slug)

    def carte_cluster(self, c):
        """Un cluster : ses chapitres (dans l'ordre du livre) et ses fiches (rangées par le rang moyen de leurs
        chapitres, pour croiser le moins de traits)."""
        fs = [x for x in self.ordre if self.cluster.get(x) == c["id"]]
        chs = sorted({ch for ch, L in self.chapitres_fiches.items() for x in L if x in fs}, key=lambda s: self.rang.get(s, 999))
        ix = {ch: i for i, ch in enumerate(chs)}

        def centre(x):
            r = [ix[ch] for ch in chs if x in self.chapitres_fiches.get(ch, [])]
            return sum(r) / len(r) if r else len(chs)
        fs = sorted(fs, key=lambda x: (centre(x), self.par[x]["titre"].lower()))
        aretes = [("ch:" + ch, "f:" + x, "") for ch in chs for x in self.chapitres_fiches.get(ch, []) if x in fs]
        aretes += [("f:" + x, "f:" + y, "ff") for x in fs for y in self.par[x].get("liens") or [] if y in fs]
        if not chs:
            return self._carte([self._noeud_fiche(x) for x in fs], [], [], aretes, larg=(LARGEUR, 0, 0))
        return self._carte([self._noeud_chapitre(ch) for ch in chs], [self._noeud_fiche(x) for x in fs], [], aretes,
                           larg=(64, 90, 0))

    # ---------------------------------------------------------------- les accroches de l'essai
    def sommaire(self):
        L = ['<div class="partie"><a href="#annexe">Annexe — la base de connaissance</a></div>',
             '<ol><li><span class="n"></span><a href="#carte">Carte du livre</a></li></ol>']
        for c in self.clusters:
            fs = [x for x in self.ordre if self.cluster.get(x) == c["id"]]
            L.append('<div class="partie"><a href="#cluster-%d">%s %s</a></div><ol>%s</ol>' % (
                c["id"], self.pastille(fs[0]) if fs else "", html.escape(self.nom_cluster(c)),
                "".join('<li><span class="n"></span><a href="#fiche-%s">%s</a></li>' % (x, html.escape(self.par[x]["titre"])) for x in fs)))
        return "".join(L)

    def apres_chapitre(self, c):
        slug = c["slug"]
        fs = [x for x in self.chapitres_fiches.get(slug, []) if x in self.inclus]
        cles = set(re.findall(r'href="#oeuvre-([\w-]+)"', c.get("corps") or ""))
        partagent = sorted({x for k in cles for x in (self.O.get(k) or {}).get("fiches") or []
                            if x in self.inclus and x not in fs}, key=lambda s: self.par[s]["titre"].lower())
        if not fs and not partagent:
            return ""
        L = ['<aside class="plus-loin"><h2>Pour aller plus loin</h2>']
        if fs:
            L.append('<p><span class="lib">Les fiches de ce chapitre : </span>%s</p>' % " · ".join(self.lien_fiche(x) for x in fs))
        if partagent:
            L.append('<p><span class="lib">Ses sources se retrouvent aussi dans : </span>%s</p>' % " · ".join(self.lien_fiche(x) for x in partagent))
        L.append(self.carte_chapitre(slug))
        L.append("</aside>")
        return "".join(L)

    def annexe(self):
        heritage, slugs = kb._heritage_md(), set(self.par)
        n = len(self.inclus)
        H = ['<section class="annexe-tete" id="annexe"><h1>La base de connaissance</h1>',
             '<p class="intro">Les %d fiches %s : ce que le livre sait, à quel point il y croit, qui le dit. Une fiche sert '
             'plusieurs chapitres ; elle dit en tête lesquels. La carte les montre ensemble, par cluster thématique : '
             'chaque nom est un lien.</p>' % (n, "sur lesquelles l'essai s'appuie" if self.portee == "utilisees" else "de la base")]
        # le tableau des clusters
        H.append('<table class="clusters"><tr><th>Cluster</th><th>Fiches</th><th>Chapitres</th></tr>')
        for c in self.clusters:
            fs = [x for x in self.ordre if self.cluster.get(x) == c["id"]]
            chs = sorted({ch for ch, L in self.chapitres_fiches.items() for x in L if x in fs}, key=lambda s: self.rang.get(s, 999))
            H.append('<tr><td>%s<a href="#cluster-%d">%s</a></td><td>%d</td><td>%s</td></tr>' % (
                self.pastille(fs[0]) if fs else "", c["id"], html.escape(self.nom_cluster(c)), len(fs),
                ", ".join('<a href="#chap-%s">%s</a>' % (ch, self.chapitres.get(ch, {}).get("numero") or ch) for ch in chs)))
        H.append("</table></section>")
        # la carte du livre : une par cluster
        H.append('<section id="carte"><h2 style="font-weight:normal;font-size:18pt;margin:1em 0 .2em">Carte du livre</h2>'
                 '<p class="mut" style="font-family:system-ui,sans-serif;font-size:8pt;color:#6b6357">À gauche les chapitres, '
                 'dans l\'ordre du livre ; à droite les fiches du cluster ; un trait plein : le chapitre s\'appuie sur la fiche ; '
                 'en pointillé : une fiche en cite une autre. Chaque nom mène à son texte.</p>')
        for c in self.clusters:
            H.append('<div class="carte-cluster"><h3>%s %s</h3>%s</div>' % (
                self.pastille(next((x for x in self.ordre if self.cluster.get(x) == c["id"]), "")),
                html.escape(self.nom_cluster(c)), self.carte_cluster(c)))
        H.append("</section>")
        # les fiches, par cluster
        for c in self.clusters:
            fs = [x for x in self.ordre if self.cluster.get(x) == c["id"]]
            H.append('<section class="cluster-page" id="cluster-%d"><div class="sur">Cluster</div><h1>%s %s</h1><ol>%s</ol></section>' % (
                c["id"], self.pastille(fs[0]) if fs else "", html.escape(self.nom_cluster(c)),
                "".join("<li>%s</li>" % self.lien_fiche(x) for x in fs)))
            for s in fs:
                h, cites = export.fiche_html(s, self.par, slugs, heritage, self.O, inclus=self.inclus, chapitres_liens=True)
                H.append(h)
                for k in cites:
                    self.citees_fiches.setdefault(k, set()).add(s)
        return "".join(H)

    def bibliographie(self, citees, chapitres):
        par_cle = collections.defaultdict(list)
        for c in chapitres:
            for k in set(re.findall(r'href="#oeuvre-([\w-]+)"', c.get("corps") or "")):
                par_cle[k].append(c["slug"])
        refs = livre.sources()
        cles = sorted(set(citees) | set(self.citees_fiches))
        H = ['<section class="biblio" id="bibliographie"><h2>Bibliographie</h2>'
             '<p class="cle">L\'essai et les fiches de cette édition : chaque œuvre dit qui la cite.</p>']
        for k in cles:
            o = self.O.get(k) or {}
            ref = o.get("ref") and export._md(o["ref"]) or refs.get(k)
            doi = ' <a href="https://doi.org/%s">doi:%s</a>' % (o["doi"], html.escape(o["doi"])) if o.get("doi") else ""
            ou = [", ".join('<a href="#chap-%s">ch. %s</a>' % (s, self.chapitres.get(s, {}).get("numero") or s)
                            for s in sorted(par_cle.get(k, []), key=lambda s: self.rang.get(s, 999)))]
            ou.append(", ".join('<a href="#fiche-%s">%s</a>' % (s, s) for s in sorted(self.citees_fiches.get(k, []))))
            ou = " · ".join(x for x in ou if x)
            H.append('<p id="oeuvre-%s">%s%s <span class="cle">%s</span>%s</p>' % (
                k, ref or "<em>référence introuvable</em>", doi, k, ' <span class="ou">— %s</span>' % ou if ou else ""))
        H.append("</section>")
        return "".join(H)

    def script(self):
        return SCRIPT


def imprimable(portee="utilisees"):
    return export.version_imprimable("essai", compagnon=Compagnon(portee))
