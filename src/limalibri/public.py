# -*- coding: utf-8 -*-
"""Le site public d'un livre : un mini-site statique, en lecture seule, pour suivre sa progression et le lire.

Généré depuis LimaLibri, publié tel quel (« en l'état ») : le suivi (où en est chaque chapitre, dans chaque
version ; les objectifs ; les dernières avancées), le récit et l'essai de chaque chapitre écrit, avec leur
statut (brouillon, relu, validé), les fiches que les chapitres citent, la bibliographie. Rien d'autre : ni
coûts, ni consignes, ni demandes, ni annotations. Le développement reste local ; le site n'est qu'une image.

    genere()   écrit le site dans un dossier hors du dépôt (~/.cache/limalibri-public/<livre>/site) — l'aperçu
    publie()   le génère, puis le déploie sur Cloudflare Pages (wrangler pages deploy), projet du livre

livre.yaml, section facultative :
    publication:
      projet: un-monde                  # le projet Cloudflare Pages (par défaut : le titre, en slug)
      adresse: un-monde.awen-project.org   # le domaine, pour l'afficher (il se rattache dans Cloudflare)
"""
import re
import json
import html
import shutil
import asyncio
import hashlib
import pathlib
import subprocess
import unicodedata

from . import livre, kb, avancement

STATUT = {"outline": "en préparation", "draft": "brouillon", "revised": "relu", "locked": "validé"}
NIVEAU = {"vide": "à venir", "synopsis": "synopsis", "brief": "préparé", "brouillon": "brouillon", "relu": "relu", "valide": "validé"}
NOM_VERSION = {"essai": "Essai", "recit": "Récit"}
EVENEMENTS = {"essai_redige": "essai écrit", "essai_revise": "essai révisé", "recit_redige": "récit écrit",
              "storyboard_pose": "storyboard posé"}


def _slug(s):
    s = unicodedata.normalize("NFKD", s or "livre").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "livre"


def config():
    m = livre.meta()
    p = m.get("publication") or {}
    return {"projet": p.get("projet") or _slug(m.get("titre")), "adresse": p.get("adresse") or "",
            "wrangler": p.get("wrangler") or ""}


def racine():
    return pathlib.Path.home() / ".cache" / "limalibri-public" / ("%s-%s" % (livre.LIVRE.parent.name, livre.LIVRE.name))


def sortie():
    return racine() / "site"


def derniere():
    p = racine() / "derniere.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ------------------------------------------------------------------ les PDF
# Les mêmes que dans LimaLibri (limalibri/export.py : Chrome sans tête) : faits une fois, gardés dans le cache tant
# que les fichiers du livre n'ont pas changé — l'aperçu reste rapide, la publication les emporte.

PDFS = [("recit", "recit", None, "Le récit"), ("essai", "essai", None, "L'essai"),
        ("essai-et-fiches", "complet", "utilisees", "L'essai et ses fiches")]


def _empreinte_livre():
    L = livre.LIVRE
    fichiers = sorted(list(L.glob("chapters/*/*.md")) + list(L.glob("chapters/*/*.yaml")) + list(L.glob("chapters/*/planches/*.svg"))
                      + list(L.glob("kb/fiches/*.md"))
                      + list(L.glob("kb/sources/*.yaml")) + [L / "livre.yaml", L / "structure.yaml", L / "synopsis.yaml", L / "frise.yaml"])
    ici = pathlib.Path(__file__).resolve().parent             # et le code qui les dessine : un PDF refait quand l'export change
    fichiers += [ici / "export.py", ici / "compagnon.py", ici / "public.py", ici.parents[1] / "front" / "limalibri.js"]
    h = hashlib.sha1()
    for f in fichiers:
        if f.exists():
            s = f.stat()
            h.update(("%s:%s:%s;" % (f, s.st_mtime_ns, s.st_size)).encode())
    return h.hexdigest()[:16]


def version_livre():
    """La version marquée du livre (onglet « révisions ») : « v2 », « v2+ » s'il a changé depuis, « » sans version."""
    from . import versions
    try:
        E = versions.etat()
        if not E.get("actif") or not E.get("tags"):
            return ""
        t = E["tags"][0]
        apres = E["modifie"] or versions._git("rev-list", "--count", t["tag"] + "..HEAD", "--", E["chemin"],
                                              cwd=E["racine"]).strip() not in ("", "0")
    except Exception:                                       # noqa: BLE001 — sans git : pas de version
        return ""
    return t["nom"] + ("+" if apres else "")


def nom_pdf(nom, version, date):
    """« un-monde-recit-v2.pdf » ; changé depuis la version : « un-monde-recit-v2-2026-10-17.pdf » ; sans version : la date."""
    v = version.rstrip("+")
    suite = [v] if v else []
    if not v or version.endswith("+"):
        suite.append(date[:10])
    return "-".join([_slug(livre.meta().get("titre")), nom] + [_slug(x) for x in suite if x]) + ".pdf"


def pdfs(versions_ecrites):
    """[{fichier, titre, octets, date}] : les PDF du livre, refaits seulement si le livre a changé."""
    from . import export
    d = racine() / "pdf"
    d.mkdir(parents=True, exist_ok=True)
    pm = d / "pdf.json"
    meta = json.loads(pm.read_text(encoding="utf-8")) if pm.exists() else {}
    emp = _empreinte_livre()
    vl = version_livre()
    out = []
    for nom, quoi, portee, titre in PDFS:
        if quoi in livre.VERSIONS and quoi not in versions_ecrites or quoi == "complet" and "essai" not in versions_ecrites:
            continue
        f = d / ("%s.pdf" % nom)
        m = meta.get(nom) or {}
        if not (f.exists() and m.get("empreinte") == emp):
            try:
                donnees, _ = asyncio.run(export.pdf(quoi, portee or "utilisees"))
            except Exception as e:                          # noqa: BLE001 — sans Chrome : le site sans ce PDF
                m = {"erreur": "%s" % e}
                meta[nom] = m
                continue
            f.write_bytes(donnees)
            m = {"empreinte": emp, "date": livre._maintenant()}
            meta[nom] = m
        date = m.get("date", "")
        out.append({"fichier": f.name, "titre": titre, "octets": f.stat().st_size, "date": date,
                    "publie": nom_pdf(nom, vl, date), "version": vl})
    pm.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# ------------------------------------------------------------------ le gabarit

CSS = """
:root{--fond:#f8f6f1;--texte:#1f1c17;--mut:#6b6357;--filet:#ddd6c8;--acc:#8a5a2b;--carte:#fffdf8;--barre:#ece6da;
  --essai:#2d5f8a;--recit:#8a5a2b;--ok:#2f6f4f;--trait:#8a5a2b;--trait2:#2d5f8a;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="clair"]){--fond:#16140f;--texte:#ece6da;--mut:#a39a8b;--filet:#3a352c;
  --acc:#e0a96d;--carte:#1e1b15;--barre:#2b271f;--essai:#7fb0dc;--recit:#e0a96d;--ok:#7cc29c;--trait:#e0a96d;--trait2:#7fb0dc;color-scheme:dark}}
:root[data-theme="sombre"]{--fond:#16140f;--texte:#ece6da;--mut:#a39a8b;--filet:#3a352c;--acc:#e0a96d;--carte:#1e1b15;
  --barre:#2b271f;--essai:#7fb0dc;--recit:#e0a96d;--ok:#7cc29c;--trait:#e0a96d;--trait2:#7fb0dc;color-scheme:dark}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--fond);color:var(--texte);font:var(--lec-taille,17px)/1.65 "Iowan Old Style",Charter,Georgia,serif}
a{color:var(--acc)}
.ui,nav,.meta,.barre-haut,.pied,.chip,.carte-ch,.suivi,.evts,h1.titre-livre+p{font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:var(--lec-largeur,42rem);margin:0 auto;padding:1rem 16px 4rem}
.barre-haut{position:sticky;top:0;z-index:2;background:var(--fond);border-bottom:1px solid var(--filet);
  display:flex;gap:.6rem;align-items:center;padding:.55rem 16px;font-size:.85rem;overflow-x:auto;white-space:nowrap}
.barre-haut a{text-decoration:none}
.barre-haut .bascule{margin-left:auto;display:flex;border:1px solid var(--filet);border-radius:999px;overflow:hidden}
.barre-haut .bascule a,.barre-haut .bascule span{padding:.15rem .7rem}
.barre-haut .bascule .ici{background:var(--acc);color:var(--fond)}
.barre-haut .bascule .absent{color:var(--mut);opacity:.6}
h1{font-size:1.9rem;line-height:1.2;margin:1.2rem 0 .4rem;font-weight:normal}
h2{font-size:1.3rem;font-weight:normal;margin:2rem 0 .6rem}
h3{font-size:1.05rem;margin:1.4rem 0 .4rem}
.sur{font-family:system-ui,sans-serif;font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--mut);margin:2.2rem 0 .6rem}
.meta{color:var(--mut);font-size:.85rem}
.chip{display:inline-block;font-size:.72rem;border:1px solid var(--filet);border-radius:999px;padding:.05rem .55rem;margin:.1rem .25rem .1rem 0;color:var(--mut);white-space:nowrap}
.chip.brouillon{border-color:#c9a25a;color:#a4561b}.chip.relu{border-color:var(--essai);color:var(--essai)}.chip.valide{border-color:var(--ok);color:var(--ok)}
.texte p{margin:0 0 1em;text-align:left;hyphens:auto}
.texte hr{border:0;text-align:center;margin:1.6rem 0}.texte hr::after{content:"⁂";color:var(--mut)}
.texte h2.intertitre-plan .num{margin-right:.35em}.texte p.tete{font-style:italic}.texte p.tete + hr{margin:2.4rem 0 0}.texte p.tete + hr::after{content:none}
.texte img{max-width:100%}
.texte table{display:block;overflow-x:auto;font-size:.85rem;border-collapse:collapse}
.texte td,.texte th{border:1px solid var(--filet);padding:.2rem .4rem}
.texte blockquote{margin:1em 0;padding-left:1em;border-left:3px solid var(--filet);color:var(--mut)}
.footnote{font-size:.85rem;color:var(--mut);border-top:1px solid var(--filet);margin-top:2rem;padding-top:.6rem}
.footnote hr{display:none}
a.cite{text-decoration:none;font-family:system-ui,sans-serif;font-size:.78em;color:var(--mut)}
a.cite::before{content:"["}a.cite::after{content:"]"}
.hors{border-bottom:1px dotted var(--mut)}
.pied{display:flex;justify-content:space-between;gap:1rem;border-top:1px solid var(--filet);margin-top:3rem;padding-top:1rem;font-size:.9rem}
.pied a{text-decoration:none;max-width:48%}
.score{display:flex;align-items:baseline;gap:.6rem;margin:.6rem 0 .2rem}
.score b{font-size:2.2rem;font-weight:500}
.jauge{height:.55rem;background:var(--barre);border-radius:999px;overflow:hidden;display:flex}
.jauge i{display:block;height:100%}
.jauge.essai i{background:var(--essai)}.jauge.recit i{background:var(--recit)}
.etapes{display:grid;grid-template-columns:repeat(auto-fill,minmax(9rem,1fr));gap:.3rem .9rem;margin:.6rem 0;font-size:.8rem;color:var(--mut)}
.etapes .jauge{height:.3rem;margin-top:.15rem}
.suivi .version{background:var(--carte);border:1px solid var(--filet);border-radius:10px;padding:.8rem 1rem;margin:.7rem 0}
.suivi .version h3{margin:0;font-family:system-ui,sans-serif;font-size:.95rem}
.objectif{background:var(--carte);border:1px solid var(--filet);border-radius:10px;padding:.7rem 1rem;margin:.6rem 0;font-family:system-ui,sans-serif;font-size:.9rem}
.objectif .jauge i{background:var(--ok)}
.evts{list-style:none;padding:0;margin:0;font-size:.88rem}
.evts li{padding:.35rem 0;border-bottom:1px solid var(--filet);display:flex;gap:.6rem}
.evts .date{color:var(--mut);min-width:5.5rem}
.partie{margin:1.6rem 0 .4rem}
.partie summary{cursor:pointer;color:var(--mut);font-size:.9rem;list-style:none}
.partie summary::-webkit-details-marker{display:none}
.partie summary::before{content:"▸ ";}
details[open].partie summary::before{content:"▾ ";}
.carte-ch{display:block;background:var(--carte);border:1px solid var(--filet);border-radius:10px;padding:.7rem .9rem;margin:.5rem 0;font-size:.9rem}
.carte-ch .t{font-family:"Iowan Old Style",Charter,Georgia,serif;font-size:1.08rem;color:var(--texte)}
.carte-ch .n{color:var(--mut);margin-right:.4rem}
.carte-ch .liens{display:flex;gap:.5rem;margin-top:.45rem;flex-wrap:wrap}
.carte-ch .liens a,.carte-ch .liens span{border:1px solid var(--filet);border-radius:6px;padding:.15rem .6rem;text-decoration:none;font-size:.82rem}
.carte-ch .liens span{color:var(--mut);opacity:.7}
.carte-ch .statuts{margin-top:.4rem;opacity:.85;font-size:.85em}
.commencer{display:grid;grid-template-columns:repeat(auto-fit,minmax(14rem,1fr));gap:.6rem;margin:1.4rem 0 .4rem}
.commencer a{display:block;background:var(--carte);border:1px solid var(--acc);border-radius:10px;padding:.7rem .9rem;text-decoration:none}
.commencer b{font-family:system-ui,sans-serif;font-weight:600}
.commencer .meta{display:block;color:var(--mut);font-size:.85rem}
.suivi#ou-en-est{margin-top:3rem;border-top:1px solid var(--filet)}
.par-chapitre summary{cursor:pointer}
.ch-prog{display:grid;grid-template-columns:1.8rem 1fr;gap:0 .3rem;padding:.35rem 0;border-bottom:1px solid var(--filet);font-size:.85rem}
.ch-prog .n{color:var(--mut)}
.ch-prog .mini{grid-column:2}
.mini{display:grid;grid-template-columns:3.4rem 1fr 2.6rem;gap:.4rem;align-items:center;font-size:.75rem;color:var(--mut);margin-top:.3rem}
.fiches-liste a{display:block;padding:.4rem 0;border-bottom:1px solid var(--filet);text-decoration:none}
.fiches-liste .meta{display:block}
.confiance{font-family:system-ui,sans-serif;font-size:.82rem;color:var(--mut);background:var(--carte);border:1px solid var(--filet);border-radius:8px;padding:.5rem .8rem;margin:.8rem 0}
.biblio p{font-size:.88rem;margin:.5rem 0;padding-left:1.2rem;text-indent:-1.2rem}
.biblio p:target{background:var(--barre)}
.biblio .liens-src{font-family:system-ui,sans-serif;font-size:.78rem;white-space:nowrap}
.biblio .ou{display:block;text-indent:0;font-family:system-ui,sans-serif;font-size:.75rem;color:var(--mut);margin-top:.15rem}
.biblio .ou a{color:var(--mut)}
.avert{font-family:system-ui,sans-serif;font-size:.82rem;color:var(--mut);border-left:3px solid var(--acc);padding:.3rem .8rem;margin:1rem 0}
.theme{margin-left:auto;font:inherit;font-size:.8rem;background:none;color:var(--mut);border:1px solid var(--filet);
  border-radius:999px;padding:.12rem .65rem;cursor:pointer;flex:none}
.barre-haut .bascule+.lecture{margin-left:.4rem}
.lecture{margin-left:auto;font:inherit;font-size:.8rem;background:none;color:var(--mut);border:1px solid var(--filet);
  border-radius:999px;padding:.12rem .65rem;cursor:pointer;flex:none}
.lecture+.theme{margin-left:.4rem}
.lecture-pop{position:fixed;z-index:5;right:12px;top:2.9rem;background:var(--carte);border:1px solid var(--filet);border-radius:10px;
  padding:.7rem .8rem;box-shadow:0 6px 24px rgba(0,0,0,.18);font-family:system-ui,-apple-system,sans-serif;font-size:.82rem;min-width:15rem}
.lecture-pop[hidden]{display:none}
.lecture-pop .ligne{display:flex;align-items:center;gap:.4rem;margin:.35rem 0}
.lecture-pop .nom{color:var(--mut);min-width:4.2rem}
.lecture-pop button{font:inherit;background:none;color:var(--texte);border:1px solid var(--filet);border-radius:6px;padding:.15rem .55rem;cursor:pointer}
.lecture-pop button.actif{background:var(--acc);color:var(--fond);border-color:var(--acc)}
.lecture-pop .val{min-width:2.6rem;text-align:center;color:var(--mut)}
.lecture-pop .raz{border:0;color:var(--acc);padding:0;margin-top:.2rem}
@media (max-width:480px){.barre-haut{gap:.45rem;padding:.5rem 12px}.barre-haut .meta{display:none}.theme .lib{display:none}
  .barre-haut .bascule a,.barre-haut .bascule span{padding:.15rem .55rem}}
/* la carte des fiches (le dessin vient de l'édition « essai + base », limalibri/compagnon.py) */
.carte-defile{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:.4rem -16px 1.2rem;padding:0 16px}
.carte{position:relative;margin:.6em 0 1em;font-size:12px}
.carte svg{position:absolute;left:0;top:0;overflow:visible}
.carte path{fill:none;stroke:var(--trait);stroke-width:.22;opacity:.5}
.carte path.ff{stroke:var(--trait2);stroke-dasharray:.8 .6;opacity:.4}
.carte .nd{position:absolute;display:block;font-family:system-ui,sans-serif;font-size:6.6pt;line-height:4.4mm;height:4.4mm;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--texte);text-decoration:none}
.carte .nd.ch{text-align:right;color:var(--acc);font-weight:600}
.carte .nd.ici{font-weight:700}
.carte .nd .num{color:var(--mut);font-weight:normal}
.carte.focus path{opacity:.08}.carte.focus path.on{opacity:.95;stroke-width:.4}
.carte.focus .nd{opacity:.3}.carte.focus .nd.on{opacity:1}
.pastille-c{display:inline-block;width:.6rem;height:.6rem;border-radius:50%;margin-right:.35rem;vertical-align:middle}
.cluster h3{font-family:system-ui,sans-serif;font-size:.9rem;font-weight:600;margin:1.6rem 0 .2rem}
.legende{font-family:system-ui,sans-serif;font-size:.8rem;color:var(--mut)}
/* la frise (le dessin vient de LimaLibri) */
.frise-barre{display:flex;flex-wrap:wrap;gap:.5rem .9rem;align-items:center;margin:.8rem 0;font-size:.85rem}
.frise-barre select{font:inherit;background:var(--carte);color:var(--texte);border:1px solid var(--filet);border-radius:6px;padding:.2rem .4rem;max-width:100%}
.frise-barre label[hidden]{display:none}
.frise-zone{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--filet);border-radius:10px;background:var(--carte);
  padding:.4rem 0;margin:0 -16px;width:calc(100% + 32px)}
@media (min-width:56rem){main:has(.frise-zone){max-width:min(96vw,80rem)}.frise-zone{margin:0;width:100%}}
.frise-svg{display:block;font-family:system-ui,-apple-system,sans-serif}
.frise-svg .fr-axe line{stroke:var(--mut)}
.frise-svg .fr-axe text,.frise-svg .fr-lib{fill:var(--mut);font-size:10.5px}
.frise-svg .fr-seg{opacity:.55}
.frise-svg .fr-seg-lib,.frise-svg .fr-val,.frise-svg .fr-titre{fill:var(--texte);font-size:10.5px}
.frise-svg .fr-titre{font-size:11.5px}
@media (max-width:620px){.frise-svg .fr-lib{font-size:9px}.frise-svg .fr-titre{font-size:10.5px}.frise-svg .fr-axe text{font-size:9.5px}}
.frise-svg .fr-rep{fill:var(--acc)}
.frise-svg .fr-rep-ligne{stroke:var(--acc);stroke-dasharray:2 3;opacity:.35}
.frise-svg a.fr-item:hover .fr-titre{fill:var(--acc);text-decoration:underline}
.frise-svg .fr-fleche{fill:none;stroke:var(--mut);stroke-width:1.1;opacity:.55}
.frise-svg .fr-fleche.arriere{stroke:#c0622f;opacity:.85}
.frise-svg .fl-tete{fill:var(--mut)}.frise-svg .fl-tete.arriere{fill:#c0622f}
.frise-legende{display:flex;flex-wrap:wrap;gap:.3rem .9rem;font-size:.78rem;color:var(--mut);margin:.7rem 0}
.frise-svg .fr-item.ici rect,.frise-svg .fr-item.ici circle{stroke:var(--acc);stroke-width:2.5}
.frise-svg .fr-item.ici .fr-titre{font-weight:700;fill:var(--acc)}
figure.planche{margin:1.6rem 0}
figure.planche img{display:block;width:100%;height:auto;border:1px solid var(--filet);border-radius:8px;background:#fffdf8}
figure.planche figcaption{font-family:system-ui,sans-serif;font-size:.8rem;color:var(--mut);margin-top:.45rem;line-height:1.45}
figure.planche figcaption b{color:var(--texte);font-weight:600}
.planche-etat{font-style:italic}
a.renvoi-planche{font-family:system-ui,sans-serif;font-size:.85em}
.planches-fiche{display:grid;grid-template-columns:repeat(auto-fill,minmax(13rem,1fr));gap:1rem;margin:.4rem 0 1.4rem}
.planches-fiche a{display:flex;flex-direction:column;gap:.35rem;text-decoration:none;color:var(--texte);font-family:system-ui,sans-serif;font-size:.8rem;line-height:1.35}
.planches-fiche img{width:100%;aspect-ratio:4/3;object-fit:contain;background:#fffdf8;border:1px solid var(--filet);border-radius:8px}
.planches-fiche i{color:var(--mut)}
.planche-absente{color:#c0622f}
.mini-frise{background:var(--carte);border:1px solid var(--filet);border-radius:10px;padding:.5rem .8rem .3rem;margin:.6rem 0 1.4rem}
.mini-frise .sur{margin:0 0 .2rem}
.mini-frise .mini-tete{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.3rem .6rem;margin-bottom:.2rem}
.mini-frise .mini-tete .sur{margin:0}
.mini-echelle{font:inherit;font-size:.75rem;background:var(--fond);color:var(--texte);border:1px solid var(--filet);border-radius:6px;
  padding:.1rem .3rem;max-width:100%}
.mini-frise p{margin:.15rem 0;font-size:.78rem}
.mini-svg{display:block;overflow:visible}
.mini-svg .mini-axe{stroke:var(--filet)}
.mini-svg .mini-autre{stroke:var(--mut);opacity:.55}
.mini-svg .mini-ici{fill:var(--acc)}
.mini-svg .mini-lib{fill:var(--mut);font-size:10px;font-family:system-ui,sans-serif}
.frise-legende i{display:inline-block;width:.7rem;height:.7rem;border-radius:2px;margin-right:.35rem;vertical-align:-1px}
footer.site{font-family:system-ui,sans-serif;font-size:.75rem;color:var(--mut);text-align:center;padding:2rem 16px}
"""


THEME = """<script>try{var r=document.documentElement,t=localStorage.getItem("theme");if(t)r.dataset.theme=t;
var l=JSON.parse(localStorage.getItem("lecture")||"{}");if(l.taille)r.style.setProperty("--lec-taille",l.taille+"px");
if(l.largeur)r.style.setProperty("--lec-largeur",l.largeur+"rem")}catch(e){}</script>"""
BOUTON_THEME = ('<button class="lecture" type="button" title="taille du texte et largeur de la colonne">Aa</button>'
                '<button class="theme" type="button" title="thème : celui du système, clair, sombre">◐ auto</button>'
                '<div class="lecture-pop" hidden><div class="ligne"><span class="nom">Taille</span><button data-t="-1">A−</button>'
                '<span class="val" data-v="taille"></span><button data-t="1">A+</button></div>'
                '<div class="ligne"><span class="nom">Largeur</span><button data-l="34">étroite</button><button data-l="42">moyenne</button>'
                '<button data-l="54">large</button></div><button class="raz" type="button">réinitialiser</button></div>')
SCRIPT = """<script>
(function(){var M=["auto","clair","sombre"],r=document.documentElement;
function lib(){var t=r.dataset.theme||"auto";document.querySelectorAll(".theme").forEach(function(b){b.innerHTML=(t=="clair"?"☀":t=="sombre"?"☾":"◐")+'<span class="lib"> '+t+"</span>"})}
document.addEventListener("click",function(e){if(!e.target.closest(".theme"))return;var t=M[(M.indexOf(r.dataset.theme||"auto")+1)%3];
if(t=="auto")delete r.dataset.theme;else r.dataset.theme=t;try{t=="auto"?localStorage.removeItem("theme"):localStorage.setItem("theme",t)}catch(x){}lib()});lib();
var L={};try{L=JSON.parse(localStorage.getItem("lecture")||"{}")}catch(x){}
function pose(){var ta=L.taille||17,la=L.largeur||42;r.style.setProperty("--lec-taille",ta+"px");r.style.setProperty("--lec-largeur",la+"rem");
try{(L.taille||L.largeur)?localStorage.setItem("lecture",JSON.stringify(L)):localStorage.removeItem("lecture")}catch(x){}
document.querySelectorAll('[data-v="taille"]').forEach(function(v){v.textContent=ta+" px"});
document.querySelectorAll("[data-l]").forEach(function(b){b.classList.toggle("actif",+b.dataset.l==la)})}
document.addEventListener("click",function(e){var p=document.querySelector(".lecture-pop");if(!p)return;
if(e.target.closest(".lecture")){p.hidden=!p.hidden;return}
var b=e.target.closest(".lecture-pop button");
if(b){if(b.dataset.t)L.taille=Math.max(13,Math.min(26,(L.taille||17)+ +b.dataset.t));
else if(b.dataset.l)L.largeur=+b.dataset.l;else if(b.classList.contains("raz"))L={};pose();return}
if(!e.target.closest(".lecture-pop"))p.hidden=true});pose();
document.querySelectorAll(".carte").forEach(function(c){function f(e){var n=e.target.closest("[data-n]");if(!n)return;var id=n.getAttribute("data-n"),v={};v[id]=1;
c.classList.add("focus");c.querySelectorAll("path").forEach(function(p){var on=p.getAttribute("data-a")==id||p.getAttribute("data-b")==id;p.classList.toggle("on",on);
if(on){v[p.getAttribute("data-a")]=1;v[p.getAttribute("data-b")]=1}});c.querySelectorAll("[data-n]").forEach(function(x){x.classList.toggle("on",!!v[x.getAttribute("data-n")])})}
c.addEventListener("mouseover",f);c.addEventListener("mouseleave",function(){c.classList.remove("focus")})})})();
</script>"""


def _page(titre, corps, base, barre="", description=""):
    if not barre:
        barre = '<nav class="barre-haut"><span class="meta">%s</span></nav>' % html.escape(livre.meta().get("titre") or "")
    barre = barre.replace("</nav>", BOUTON_THEME + "</nav>", 1)
    return """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title>%s%s<link rel="stylesheet" href="%sstyle.css"></head>
<body>%s<main>%s</main><footer class="site">%s — publié en l'état, depuis LimaLibri · %s</footer>%s%s</body></html>
""" % (html.escape(titre), '<meta name="description" content="%s">' % html.escape(description) if description else "", THEME,
       base, barre, corps, html.escape(livre.meta().get("titre") or ""), livre._maintenant()[:10], SCRIPT,
       # la visionneuse des planches (front/visionneuse.js, copiée à la racine du site), là où il y en a
       '<script src="%svisionneuse.js" defer></script>' % base if 'class="planche-lien"' in corps else "")


# ------------------------------------------------------------------ le site

class Site:
    def __init__(self):
        from . import plan, suivi
        self.meta = livre.meta()
        self.chapitres = [c for c in livre.chapitres()]
        self.par_slug = {c["slug"]: c for c in self.chapitres}
        self.plan = plan.lit()
        self.suivi = {v: suivi.suivi(v) for v in livre.VERSIONS}
        self.sources = livre.sources()
        self.cites = set()
        self.cite_ou = {}                                   # clé -> {(libellé, adresse depuis la racine)}
        self.planches = set()                               # (chapitre, planche) appelées par les textes publiés
        self.planche_ou = {}                                # (chapitre, planche) -> (libellé, page) où elle paraît
        # les textes publiés : chaque chapitre écrit, dans chaque version
        self.textes = {}
        for c in self.chapitres:
            for v in livre.VERSIONS:
                if avancement.niveau(c, v) in ("brouillon", "relu", "valide"):
                    try:
                        h = livre.texte(c["slug"], v)["html"]
                        self.textes[(c["slug"], v)] = livre.intertitres_recit(c["slug"], h) if v == "recit" else h
                    except KeyError:
                        pass
        # les fiches : celles que les chapitres citent (leurs briefs)
        I = kb.index()
        self.fiches = {f["slug"]: f for f in I}
        des = kb._fiches_de_tous_les_chapitres()
        self.fiches_de = {s: [x for x in c["fiches"] if x in self.fiches] for s, c in des.items()}
        self.inclus = {x for L in self.fiches_de.values() for x in L}
        from . import frise
        F = frise.lit()
        self.frise = F if F.get("existe") and any(c.get("place") for c in F["chapitres"]) else None

    # ---------------------------------------------------------------- la carte des fiches
    @property
    def compagnon(self):
        if not hasattr(self, "_compagnon"):
            from .compagnon import Compagnon
            self._compagnon = Compagnon("utilisees")
        return self._compagnon

    def carte(self, h, base):
        """Une carte du compagnon, ses liens (#fiche-…, #chap-…) vers les pages du site."""
        h = re.sub(r'href="#fiche-([\w-]+)"', lambda m: 'href="%sfiches/%s.html"' % (base, m.group(1)), h)
        h = re.sub(r'href="#chap-([\w-]+)"', lambda m: 'href="%schapitres/%s/essai.html"' % (base, m.group(1))
                   if (m.group(1), "essai") in self.textes else 'href="%sindex.html"' % base, h)
        return '<div class="carte-defile">%s</div>' % h if h else ""

    # ---------------------------------------------------------------- les liens
    def liens(self, h, base, ou=None):
        def fiche(m):
            s = m.group(2)
            if s in self.inclus:
                return '<a%s href="%sfiches/%s.html"' % (m.group(1), base, s)
            return '<a class="hors" title="fiche non publiée"'
        h = re.sub(r'<a((?: class="[^"]*")?) href="#fiches/([\w-]+)[^"]*"', fiche, h)

        def chap(m):
            s, v = m.group(1), m.group(2)
            if (s, v) in self.textes:
                return '<a class="renvoi-chap" href="%schapitres/%s/%s.html"' % (base, s, v)
            return '<a class="hors" title="chapitre pas encore écrit"'
        h = re.sub(r'<a class="renvoi-chap" href="#([\w-]+)/(essai|recit)[^"]*"', chap, h)
        h = re.sub(r'<a href="#([\w-]+)/(essai|recit)[^"]*"', chap, h)

        def cite(m):
            k = m.group(1)
            self.cites.add(k)
            if ou:
                self.cite_ou.setdefault(k, set()).add(ou)
            from .export import _courte
            return '<a class="cite" href="%sbibliographie.html#%s">%s</a>' % (base, k, html.escape(_courte(k)))
        h = re.sub(r'<cite data-cle="([^"]+)">[^<]*</cite>', cite, h)
        h = re.sub(r'(src|href)="/api/planches/([\w-]+)/([\w-]+)\.svg"',
                   lambda m: (self.planches.add((m.group(2), m.group(3))),
                              ou and self.planche_ou.setdefault((m.group(2), m.group(3)), ou),
                              '%s="%splanches/%s/%s.svg"' % (m.group(1), base, m.group(2), m.group(3)))[2], h)
        return re.sub(r'\sdata-(?:empreinte|block|num|section)="[^"]*"', "", h)

    # ---------------------------------------------------------------- les morceaux
    def statut(self, c, v):
        n = avancement.niveau(c, v)
        cls = {"brouillon": "brouillon", "relu": "relu", "valide": "valide"}.get(n, "")
        return '<span class="chip %s">%s · %s</span>' % (cls, NOM_VERSION[v].lower(), NIVEAU.get(n, n))

    def jauge(self, pct, v=""):
        return '<div class="jauge %s"><i style="width:%s%%"></i></div>' % (v, max(0, min(100, round(pct or 0))))

    def bloc_suivi(self):
        H = ['<section class="suivi" id="ou-en-est"><h2>Où en est le livre</h2>']
        for v in livre.VERSIONS:
            S = self.suivi[v]
            rep = " ".join('<span class="chip">%s · %d</span>' % (NIVEAU.get(k, k), n) for k, n in S["repartition"].items() if n)
            et = "".join('<div>%s · %d %%%s</div>' % (html.escape(e["titre"]), round(100 * e["moyenne"] / e["max"]) if e["max"] else 0,
                                                       self.jauge(100 * e["moyenne"] / e["max"] if e["max"] else 0, v))
                         for e in S["etapes"].values())
            H.append('<div class="version"><h3>%s</h3><div class="score"><b>%d %%</b><span class="meta">sur %d chapitres</span></div>%s'
                     '<div class="etapes">%s</div><div>%s</div></div>' % (
                         NOM_VERSION[v], round(S["score"]), len(S["chapitres"]), self.jauge(S["score"], v), et, rep))
        O = [o for v in livre.VERSIONS for o in self.suivi[v].get("objectifs") or [] if o.get("etat") == "actif"]
        if O:
            H.append('<p class="sur">Objectifs en cours</p>')
            for o in O:
                H.append('<div class="objectif"><div>%s</div><div class="meta">%s · %s%s</div>%s</div>' % (
                    html.escape(o["titre"]), NOM_VERSION.get(o.get("version"), ""), html.escape(o.get("perimetre_libelle") or ""),
                    " · atteint" if o.get("atteint") else " · %d %%" % round(o.get("progression") or 0),
                    self.jauge(o.get("progression") or 0)))
        E = self.evenements()
        if E:
            H.append('<p class="sur">Dernières avancées</p><ul class="evts">')
            for e in E:
                c = self.par_slug.get(e.get("chapitre"))
                if not c:
                    continue
                v = "recit" if e["type"].startswith(("recit", "storyboard")) else "essai"
                t = html.escape(c["title"])
                if (c["slug"], v) in self.textes:
                    t = '<a href="chapitres/%s/%s.html">%s</a>' % (c["slug"], v, t)
                H.append('<li><span class="date">%s</span><span>%s — %s%s</span></li>' % (
                    e["date"][:10], t, EVENEMENTS[e["type"]], " · %d mots" % e["mots"] if e.get("mots") else ""))
            H.append("</ul>")
        H.append(self.par_chapitre())
        H.append("</section>")
        return "".join(H)

    def par_chapitre(self):
        score = {v: {c["slug"]: c["score"] for c in self.suivi[v]["chapitres"]} for v in livre.VERSIONS}
        L = []
        for c in self.chapitres:
            if not any(c["slug"] in score[v] for v in ("recit", "essai")):
                continue
            L.append('<div class="ch-prog"><span class="n">%s</span><span class="t">%s</span>%s</div>' % (
                c.get("numero") or "", html.escape(c["title"]), "".join(
                    '<span class="mini"><span>%s</span>%s<span>%d %%</span></span>' % (
                        NOM_VERSION[v].lower(), self.jauge(score[v].get(c["slug"], 0), v), round(score[v].get(c["slug"], 0)))
                    for v in ("recit", "essai"))))
        return '<details class="par-chapitre"><summary class="sur">Par chapitre</summary>%s</details>' % "".join(L) if L else ""

    def evenements(self, n=12):
        p = livre.LIVRE / "journal.jsonl"
        if not p.exists():
            return []
        L = []
        for l in p.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(l)
            except ValueError:
                continue
            if e.get("type") in EVENEMENTS and e.get("date"):
                L.append(e)
        return sorted(L, key=lambda e: e["date"], reverse=True)[:n]

    def sommaire(self):
        H = ['<p class="sur">Sommaire</p>']
        for p in self.plan["parties"]:
            H.append('<details class="partie" open><summary>%s</summary>%s</details>' % (
                html.escape(p["title"]), '<p class="meta">%s</p>' % html.escape(p["sens"]) if p.get("sens") else ""))
            for pc in p["chapitres"]:
                c = self.par_slug.get(pc["slug"])
                if not c:
                    continue
                liens = "".join(('<a href="chapitres/%s/%s.html">%s</a>' % (c["slug"], v, NOM_VERSION[v]))
                                if (c["slug"], v) in self.textes else '<span>%s · à venir</span>' % NOM_VERSION[v]
                                for v in ("recit", "essai"))
                H.append('<div class="carte-ch"><span class="n">%s</span><span class="t">%s</span>%s'
                         '<div class="liens">%s</div><div class="statuts">%s%s</div></div>' % (
                             c.get("numero") or "", html.escape(c["title"]),
                             '<div class="meta">%s</div>' % html.escape(c["periode"]) if c.get("periode") else "",
                             liens, self.statut(c, "recit"), self.statut(c, "essai")))
        return "".join(H)

    def quand_pdf(self, p):
        j = "/".join(reversed(p["date"][:10].split("-")))
        v = p.get("version") or ""
        if not v:
            return "du %s" % j
        if v.endswith("+"):
            return "version %s, mise à jour du %s" % (v[:-1], j)
        return "version %s · %s" % (v, j)

    def commencer(self):
        """Commencer la lecture : le premier chapitre écrit de chaque version."""
        ordre = [c["slug"] for c in self.chapitres]
        A = []
        for v in ("recit", "essai"):
            s = next((x for x in ordre if (x, v) in self.textes), None)
            if s:
                A.append('<a href="chapitres/%s/%s.html"><b>Lire %s</b><span class="meta">ch. %s · %s</span></a>' % (
                    s, v, "le récit" if v == "recit" else "l'essai", self.par_slug[s].get("numero") or "",
                    html.escape(self.par_slug[s]["title"])))
        return '<div class="commencer">%s</div>' % "".join(A) if A else ""

    # ---------------------------------------------------------------- les pages
    def accueil(self):
        m = self.meta
        corps = ['<h1 class="titre-livre">%s</h1>' % html.escape(m.get("titre") or "")]
        if m.get("sous_titre"):
            corps.append('<p class="meta">%s</p>' % html.escape(m["sous_titre"]))
        if m.get("auteur"):
            corps.append('<p class="meta">%s</p>' % html.escape(m["auteur"]))
        for k in ("synopsis", "quatrieme"):
            if m.get(k):
                corps.append("".join("<p>%s</p>" % html.escape(x.strip()) for x in str(m[k]).split("\n\n") if x.strip()))
                break
        corps.append('<p class="avert">Deux versions alignées chapitre pour chapitre : le <b>récit</b>, qui raconte, '
                     'et l\'<b>essai</b>, qui explique ; les <a href="fiches/index.html">fiches</a> rassemblent ce sur quoi '
                     'l\'essai s\'appuie. Un livre en cours d\'écriture, publié en l\'état : chaque chapitre dit où il en est '
                     '(brouillon, relu, validé) — <a href="#ou-en-est">où en est le livre</a>.</p>')
        corps.append(self.commencer())
        corps.append(self.sommaire())
        if getattr(self, "pdf", None):
            corps.append('<p class="sur">À télécharger</p><div class="fiches-liste">%s</div>' % "".join(
                '<a href="pdf/%s" download="%s">%s<span class="meta">PDF · %s Mo · %s</span></a>' % (
                    p["publie"], p["publie"], html.escape(p["titre"]), str(round(p["octets"] / 1e6, 1)).replace(".", ","),
                    html.escape(self.quand_pdf(p)))
                for p in self.pdf))
        corps.append('<p class="sur">Et aussi</p><p class="ui">%s<a href="fiches/index.html">Les fiches (%d)</a> · '
                     '<a href="bibliographie.html">La bibliographie</a></p>' % (
                         '<a href="frise.html">La frise</a> · ' if self.frise else "", len(self.inclus)))
        corps.append(self.bloc_suivi())
        return _page(m.get("titre") or "Livre", "".join(corps), "", description=str(m.get("synopsis") or "")[:200])

    def chapitre(self, slug, v, ordre):
        c = self.par_slug[slug]
        base = "../../"
        autre = "essai" if v == "recit" else "recit"
        bascule = "".join(('<span class="ici">%s</span>' % NOM_VERSION[x]) if x == v else
                          ('<a href="%s.html">%s</a>' % (x, NOM_VERSION[x]) if (slug, x) in self.textes
                           else '<span class="absent">%s</span>' % NOM_VERSION[x]) for x in ("recit", "essai"))
        barre = '<nav class="barre-haut"><a href="%sindex.html">← %s</a><span class="meta">ch. %s</span><span class="bascule">%s</span></nav>' % (
            base, html.escape(self.meta.get("titre") or "Sommaire"), c.get("numero") or "", bascule)
        mots = len(re.sub(r"<[^>]+>", " ", self.textes[(slug, v)]).split())
        corps = ['<p class="meta">%s · %s mots</p>' % (self.statut(c, v), format(mots, ",").replace(",", " ")),
                 self.mini_frise(slug, base),
                 '<article class="texte">%s</article>' % self.liens(self.textes[(slug, v)], base,
                                                                     ("%s ch. %s" % (NOM_VERSION[v].lower(), c.get("numero") or ""),
                                                                      "chapitres/%s/%s.html" % (slug, v)))]
        if v == "essai" and self.fiches_de.get(slug):
            corps.append('<p class="sur">Les fiches de ce chapitre</p><div class="fiches-liste">%s</div>' % "".join(
                '<a href="%sfiches/%s.html">%s%s</a>' % (base, s, self.compagnon.pastille(s), html.escape(self.fiches[s]["titre"]))
                for s in self.fiches_de[slug]))
            corps.append('<p class="legende">Le chapitre, ses fiches, et leurs voisines (les fiches qu\'elles citent ou qui '
                         'les citent).</p>' + self.carte(self.compagnon.carte_chapitre(slug), base))
        L = [s for s in ordre if (s, v) in self.textes]
        i = L.index(slug)
        prec = '<a href="../%s/%s.html">← %s</a>' % (L[i - 1], v, html.escape(self.par_slug[L[i - 1]]["title"])) if i > 0 else "<span></span>"
        suiv = '<a href="../%s/%s.html">%s →</a>' % (L[i + 1], v, html.escape(self.par_slug[L[i + 1]]["title"])) if i + 1 < len(L) else "<span></span>"
        corps.append('<nav class="pied">%s%s</nav>' % (prec, suiv))
        return _page("%s — %s" % (c["title"], NOM_VERSION[v]), "".join(corps), base, barre)

    def fiche(self, s):
        base = "../"
        f = kb.fiche(s)
        barre = '<nav class="barre-haut"><a href="%sindex.html">← %s</a><a href="index.html">Fiches</a></nav>' % (
            base, html.escape(self.meta.get("titre") or "Sommaire"))
        corps = ['<p class="sur">Fiche</p><h1>%s</h1>' % html.escape(f["titre"])]
        sujet = (f.get("meta") or {}).get("sujet")
        if sujet and sujet != f["titre"]:
            corps.append('<p class="meta">%s</p>' % html.escape(sujet))
        sert = [c for c in f.get("chapitres") or [] if c.get("slug") in self.par_slug]
        if sert:
            corps.append('<p class="meta">Sert : %s</p>' % " · ".join(
                ('<a href="%schapitres/%s/essai.html">%s</a>' % (base, c["slug"], html.escape(c["title"])))
                if (c["slug"], "essai") in self.textes else html.escape(c["title"]) for c in sert))
        conf = f.get("confiance") or []
        if conf:
            corps.append('<div class="confiance">%s</div>' % "".join(
                "<div><b>%s</b> %s</div>" % (html.escape(x.get("degre", "")), html.escape(x.get("sur", ""))) for x in conf))
        corps.append('<article class="texte">%s</article>' % self.liens(f.get("html") or "", base, ("fiche · " + f["titre"], "fiches/%s.html" % s)))
        # les planches tirées de cette fiche, là où un texte publié les montre
        from . import planches
        P = [p for p in planches.de_fiche(s) if (p["chapitre"], p["id"]) in self.planche_ou]
        if P:
            corps.append('<p class="sur">Planches</p><div class="planches-fiche">%s</div>' % "".join(
                '<a href="%s%s#planche-%s-%s"><img src="%splanches/%s/%s.svg" alt="%s" loading="lazy">'
                '<span><b>Planche %s</b> — %s <i>· %s</i></span></a>' % (
                    base, self.planche_ou[(p["chapitre"], p["id"])][1], p["chapitre"], p["id"], base, p["chapitre"], p["id"],
                    html.escape(p["titre"], quote=True), p["numero"], html.escape(p["titre"]),
                    html.escape(self.planche_ou[(p["chapitre"], p["id"])][0])) for p in P))
        vois = [x for x in [l.get("cible") if isinstance(l, dict) else l for l in f.get("liens") or []] + list(f.get("entrants") or [])
                if x in self.inclus and x != s]
        if vois:
            corps.append('<p class="sur">Voisines</p><div class="fiches-liste">%s</div>' % "".join(
                '<a href="%s.html">%s</a>' % (x, html.escape(self.fiches[x]["titre"])) for x in dict.fromkeys(vois)))
        return _page(f["titre"], "".join(corps), base, barre)

    def index_fiches(self):
        base = "../"
        barre = '<nav class="barre-haut"><a href="%sindex.html">← %s</a></nav>' % (base, html.escape(self.meta.get("titre") or "Sommaire"))
        sert = {}
        for ch, L in self.fiches_de.items():
            for x in L:
                sert.setdefault(x, []).append(ch)
        K = self.compagnon
        corps = ['<h1>Les fiches</h1><p class="meta">%d fiches : ce sur quoi l\'essai s\'appuie, une par question, rangées par '
                 'cluster thématique.</p>' % len(self.inclus),
                 '<p class="sur">La carte</p><p class="legende">Pour chaque cluster : à gauche les chapitres, dans l\'ordre du '
                 'livre ; à droite ses fiches. Un trait plein : le chapitre s\'appuie sur la fiche ; en pointillé : une fiche en '
                 'cite une autre. Chaque nom est un lien ; la carte défile de côté sur un téléphone.</p>']
        for c in K.clusters:
            fs = [x for x in K.ordre if K.cluster.get(x) == c["id"]]
            if fs:
                corps.append('<div class="cluster"><h3>%s%s</h3>%s</div>' % (
                    K.pastille(fs[0]), html.escape(K.nom_cluster(c)), self.carte(K.carte_cluster(c), base)))
        corps.append('<p class="sur">Toutes les fiches</p>')
        for c in K.clusters:
            fs = [x for x in K.ordre if K.cluster.get(x) == c["id"] and x in self.inclus]
            if not fs:
                continue
            corps.append('<div class="cluster"><h3>%s%s</h3><div class="fiches-liste">' % (K.pastille(fs[0]), html.escape(K.nom_cluster(c))))
            for s in fs:
                chs = [self.par_slug[x] for x in sert.get(s, []) if x in self.par_slug]
                corps.append('<a href="%s.html">%s<span class="meta">%s</span></a>' % (
                    s, html.escape(self.fiches[s]["titre"]), " · ".join("ch. %s" % c2["numero"] for c2 in chs if c2.get("numero"))))
            corps.append("</div></div>")
        return _page("Fiches — %s" % (self.meta.get("titre") or ""), "".join(corps), base, barre)

    def bibliographie(self):
        barre = '<nav class="barre-haut"><a href="index.html">← %s</a></nav>' % html.escape(self.meta.get("titre") or "Sommaire")
        from . import sources as SRC
        O = SRC.toutes() if SRC.existe() else {}
        tri = lambda k: unicodedata.normalize("NFKD", re.sub(r"<[^>]+>|[«»\"'“”(]", "", self.sources[k])).encode("ascii", "ignore").decode().strip().lower()
        L = sorted((k for k in self.cites if k in self.sources), key=tri)        # dans l'ordre du texte affiché (auteur)
        corps = ['<h1>Bibliographie</h1><p class="meta">%d œuvres citées dans les textes et les fiches publiés. Chacune mène à '
                 'sa source quand elle est en ligne, et dit où le livre la cite.</p><div class="biblio">' % len(L)]
        for k in L:
            o = O.get(k) or {}
            liens = []
            url, doi = (o.get("url") or "").strip(), (o.get("doi") or "").strip()
            if url and not (doi and doi.lower() in url.lower()):
                liens.append('<a href="%s" rel="noopener" target="_blank">source ↗</a>' % html.escape(url, quote=True))
            if doi:
                liens.append('<a href="https://doi.org/%s" rel="noopener" target="_blank">doi:%s</a>' % (
                    html.escape(doi, quote=True), html.escape(doi)))
            ou = sorted(self.cite_ou.get(k, ()), key=lambda x: (not x[0].startswith(("récit", "essai")),
                                                                 int(re.sub(r"\D", "", x[0]) or 0) if x[0].startswith(("récit", "essai")) else 0, x[0]))
            citee = " · ".join('<a href="%s">%s</a>' % (h, html.escape(lib)) for lib, h in ou)
            corps.append('<p id="%s">%s%s%s</p>' % (
                k, self.sources[k], ' <span class="liens-src">%s</span>' % " · ".join(liens) if liens else "",
                '<span class="ou">citée dans : %s</span>' % citee if citee else ""))
        corps.append("</div>")
        return _page("Bibliographie — %s" % (self.meta.get("titre") or ""), "".join(corps), "", barre)

    def donnees_frise(self):
        """window.FRISE : la frise du livre, chaque chapitre avec le lien de son texte publié (depuis la racine)."""
        F = dict(self.frise)
        for c in F["chapitres"]:
            v = "recit" if (c["slug"], "recit") in self.textes else "essai" if (c["slug"], "essai") in self.textes else None
            c["lien"] = "chapitres/%s/%s.html" % (c["slug"], v) if v else None
        F.pop("fichier", None)
        return "window.FRISE = %s;\n" % json.dumps(F, ensure_ascii=False)

    def mini_frise(self, slug, base):
        """Le bandeau d'un chapitre : où il se place (dessiné par frise.js), et ses frises internes."""
        if not self.frise:
            return ""
        internes = [f for f in self.frise["frises"] if f.get("chapitre") == slug]
        liens = "".join(' · <a href="%sfrise.html?frise=%s">%s</a>' % (base, f["id"], html.escape(f["titre"])) for f in internes)
        return ('<div class="mini-frise ui"><span class="sur">Dans le temps</span><div class="mini-zone" data-slug="%s" data-base="%s"></div>'
                '<p class="meta mini-texte"></p><p class="meta"><a href="%sfrise.html?ch=%s">la frise du livre →</a>%s</p></div>'
                '<script src="%sfrise-donnees.js"></script><script src="%sfrise.js"></script>') % (slug, base, base, slug, liens, base, base)

    def page_frise(self):
        """La frise du livre (frise.yaml) : la même que dans LimaLibri, dessinée par le même moteur."""
        barre = '<nav class="barre-haut"><a href="index.html">← %s</a></nav>' % html.escape(self.meta.get("titre") or "Sommaire")
        corps = ['<h1>La frise</h1><p class="meta">Où se place chaque chapitre dans le temps de l\'histoire. Plusieurs échelles '
                 'pour la même histoire ; les frises internes suivent un chapitre. Touchez un chapitre pour le lire.</p>',
                 '<div class="frise-barre ui"><select id="fr-frise"></select><select id="fr-echelle"></select>'
                 '<label><input type="checkbox" id="fr-bandes" checked> bandes</label>'
                 '<label><input type="checkbox" id="fr-reperes" checked> repères</label>'
                 '<label><input type="checkbox" id="fr-fleches"> flèches</label></div>',
                 '<div class="frise-zone" id="fr-zone"></div><div class="frise-notes ui" id="fr-notes"></div>',
                 '<script src="frise-donnees.js"></script><script src="frise.js"></script>']
        return _page("La frise — %s" % (self.meta.get("titre") or ""), "".join(corps), "", barre)

    def etat(self):
        return {"titre": self.meta.get("titre"), "genere": livre._maintenant(),
                "versions": {v: {"score": self.suivi[v]["score"], "repartition": self.suivi[v]["repartition"]} for v in livre.VERSIONS},
                "chapitres": [{"slug": c["slug"], "numero": c.get("numero"), "titre": c["title"],
                               "niveaux": {v: avancement.niveau(c, v) for v in livre.VERSIONS},
                               "publie": [v for v in livre.VERSIONS if (c["slug"], v) in self.textes]} for c in self.chapitres],
                "fiches": len(self.inclus)}


def script_frise():
    """Le moteur de dessin de LimaLibri (front/limalibri.js, de COULEURS_FRISE à pageFrise), et la page publique."""
    js = (pathlib.Path(__file__).resolve().parents[2] / "front" / "limalibri.js").read_text(encoding="utf-8")
    a, b = js.index("const COULEURS_FRISE"), js.index("async function pageFrise")
    return js[a:b] + PAGE_FRISE


PAGE_FRISE = r"""
// l'échelle retenue par le lecteur (le bandeau des chapitres et la page Frise la partagent)
function echelleRetenue(F) {
  var id = null; try { id = localStorage.getItem("frise-echelle"); } catch (e) {}
  return F.echelles.find(function (e) { return e.id === id; }) || F.echelles[0];
}
function retientEchelle(id) { try { localStorage.setItem("frise-echelle", id); } catch (e) {} }

// le bandeau d'un chapitre : tous les chapitres en traits discrets, celui-ci en évidence, sur l'échelle choisie
function miniFrises() {
  var F = window.FRISE;
  document.querySelectorAll(".mini-zone").forEach(function (div) {
    var slug = div.dataset.slug, base = div.dataset.base || "";
    var c = F.chapitres.find(function (x) { return x.slug === slug; });
    var txt = div.parentNode.querySelector(".mini-texte");
    var places = F.chapitres.filter(function (x) { return x.place; });
    if (!c || !c.place) { txt.textContent = "Ce chapitre n'est pas placé sur la frise."; div.hidden = true; return; }
    var ech = echelleRetenue(F);
    var bloc = div.parentNode, sel = bloc.querySelector(".mini-echelle");
    if (!sel && F.echelles.length > 1) {                    // le sélecteur de vue : une fois par bandeau
      sel = document.createElement("select"); sel.className = "mini-echelle"; sel.title = "l'échelle de la frise";
      F.echelles.forEach(function (e) { var o = document.createElement("option"); o.value = e.id; o.textContent = e.titre; sel.append(o); });
      sel.onchange = function () { retientEchelle(sel.value); miniFrises(); };
      var tete = document.createElement("div"); tete.className = "mini-tete";
      bloc.querySelector(".sur").replaceWith(tete);
      var s = document.createElement("span"); s.className = "sur"; s.textContent = "Dans le temps";
      tete.append(s, sel);
    }
    if (sel) sel.value = ech.id;
    var svg = miniSvg(F, ech, c, Math.max(div.clientWidth, 260));
    var lien = document.createElement("a"); lien.href = base + "frise.html?ch=" + slug; lien.title = "la frise du livre"; lien.append(svg);
    div.replaceChildren(lien);
    txt.textContent = c.place.texte.replace(/…/g, "").replace(/^ → | → $/g, "");
  });
}

// le dessin du bandeau : tous les chapitres en traits discrets, celui-ci en évidence (le site et le PDF)
function miniSvg(F, ech, c, W) {
    var slug = c.slug, places = F.chapitres.filter(function (x) { return x.place; });
    var ts = []; places.forEach(function (x) { ts.push(x.place.debut, x.place.fin); });
    var E = echelleFrise(ech, F, ts);
    var G = 6, L = W - 12;
    var X = function (t) { return G + Math.max(0, Math.min(1, E.x(t))) * L; };
    var svg = svgEl("svg", { width: W, height: 58, class: "mini-svg" });
    var bande = (F.bandes || []).find(function (b) { return b.rendu !== "gradient" && (!ech.bandes || ech.bandes.indexOf(b.id) >= 0); });
    if (bande) bande.segments.forEach(function (s, i) {
      var a = X(Math.min(s.debut, s.fin)), b = X(Math.max(s.debut, s.fin));
      var r = svgEl("rect", { x: a, y: 6, width: Math.max(b - a, 1), height: 7, fill: s.couleur || COULEURS_FRISE[i % COULEURS_FRISE.length], opacity: 0.45 });
      r.append(svgEl("title", {}, s.nom)); svg.append(r);
    });
    svg.append(svgEl("line", { x1: G, x2: G + L, y1: 30, y2: 30, class: "mini-axe" }));
    places.forEach(function (x) {
      if (x.slug === slug) return;
      var a = x.place.debut == null ? G : X(x.place.debut), b = x.place.fin == null ? G + L : X(x.place.fin);
      svg.append(svgEl("line", { x1: (a + b) / 2, x2: (a + b) / 2, y1: 25, y2: 35, class: "mini-autre" }));
    });
    var a = c.place.debut == null ? G : X(c.place.debut), b = c.place.fin == null ? G + L : X(c.place.fin);
    svg.append(svgEl("rect", { x: Math.min(a, b - 5), y: 23, width: Math.max(b - a, 6), height: 14, rx: 3, class: "mini-ici" }));
    var k = E.ticks, premier = k[0], dernier = k[k.length - 1];
    if (premier) svg.append(svgEl("text", { x: G, y: 54, class: "mini-lib" }, premier.texte || libelleT(premier.t, F, E.variable)));
    if (dernier) svg.append(svgEl("text", { x: G + L, y: 54, "text-anchor": "end", class: "mini-lib" }, dernier.texte || libelleT(dernier.t, F, E.variable)));
    return svg;
}
if (!document.getElementById("fr-zone") && window.FRISE) {
  miniFrises();
  var m_; window.addEventListener("resize", function () { clearTimeout(m_); m_ = setTimeout(miniFrises, 150); });
}

(function () {
  var F = window.FRISE, $ = function (i) { return document.getElementById(i); };
  if (!$("fr-zone")) return;
  var Q = new URLSearchParams(location.search), ici = Q.get("ch");
  var sf = $("fr-frise"), se = $("fr-echelle"), zone = $("fr-zone"), notes = $("fr-notes");
  var opt = function (s, v, t) { var o = document.createElement("option"); o.value = v; o.textContent = t; s.append(o); };
  opt(sf, "", "Les chapitres");
  F.frises.forEach(function (f) { opt(sf, f.id, f.titre); });
  if (Q.get("frise") && F.frises.some(function (f) { return f.id === Q.get("frise"); })) sf.value = Q.get("frise");
  var parties = Array.from(new Set(F.chapitres.map(function (c) { return c.partie; })));
  function echelles() {
    var fr = F.frises.find(function (f) { return f.id === sf.value; });
    return fr ? [fr.echelle] : F.echelles;
  }
  function remplit() {
    se.replaceChildren();
    echelles().forEach(function (e, i) { opt(se, String(i), "échelle : " + e.titre); });
    if (!sf.value) se.value = String(Math.max(0, F.echelles.indexOf(echelleRetenue(F))));
    var fr = F.frises.find(function (f) { return f.id === sf.value; });
    $("fr-fleches").checked = fr ? fr.rendu === "fleche" : F.rendu === "fleche";
    ["fr-bandes", "fr-reperes"].forEach(function (i) { $(i).parentNode.hidden = !!fr; });
  }
  function dessine() {
    var fr = F.frises.find(function (f) { return f.id === sf.value; });
    var ech = echelles()[Number(se.value)] || echelles()[0];
    var items = fr ? fr.evenements.map(function (e, i) {
      return { debut: e.debut, fin: e.fin == null ? e.debut : e.fin, titre: e.titre, sous: [e.date, e.texte].filter(Boolean).join(" — "),
        couleur: COULEURS_FRISE[1], ordre: i, lien: e.lien };
    }) : F.chapitres.filter(function (c) { return c.place; }).map(function (c, i) {
      return { debut: c.place.debut, fin: c.place.fin, ouvert_debut: c.place.ouvert_debut, ouvert_fin: c.place.ouvert_fin,
        approx: c.place.approx, titre: ((c.numero || "") + " " + c.titre).trim(), sous: c.place.texte,
        couleur: COULEURS_FRISE[parties.indexOf(c.partie) % COULEURS_FRISE.length], ordre: i, lien: c.lien, ici: c.slug === ici };
    });
    var bandes = fr || !$("fr-bandes").checked ? [] : F.bandes.filter(function (b) { return !ech.bandes || ech.bandes.indexOf(b.id) >= 0; });
    zone.replaceChildren(dessineFrise(F, ech, items, { bandes: bandes, reperes: !fr && $("fr-reperes").checked ? F.reperes : [],
      fleches: $("fr-fleches").checked, largeur: Math.max(zone.clientWidth - 4, 340) }));
    notes.replaceChildren();
    if (fr) { if (fr.note) { var p = document.createElement("p"); p.className = "meta"; p.textContent = fr.note; notes.append(p); } return; }
    var leg = document.createElement("p"); leg.className = "frise-legende";
    parties.forEach(function (p, k) {
      var c0 = F.chapitres.find(function (c) { return c.partie === p; });
      var s = document.createElement("span"), i = document.createElement("i");
      i.style.background = COULEURS_FRISE[k % COULEURS_FRISE.length];
      s.append(i, (c0 && c0.partie_titre) || "hors partie"); leg.append(s);
    });
    notes.append(leg);
    var sans = F.chapitres.filter(function (c) { return !c.place; });
    if (sans.length) {
      var h = document.createElement("p"); h.className = "sur"; h.textContent = "Hors de la frise (" + sans.length + ")"; notes.append(h);
      var ul = document.createElement("p"); ul.className = "meta";
      ul.textContent = sans.map(function (c) { return ((c.numero || "") + " " + c.titre).trim(); }).join(" · ");
      notes.append(ul);
    }
  }
  sf.onchange = function () { remplit(); dessine(); };
  se.onchange = function () { if (!sf.value) retientEchelle(F.echelles[Number(se.value)].id); dessine(); };
  ["fr-bandes", "fr-reperes", "fr-fleches"].forEach(function (i) { $(i).onchange = dessine; });
  var minuteur; window.addEventListener("resize", function () { clearTimeout(minuteur); minuteur = setTimeout(dessine, 150); });
  remplit(); dessine();
})();
"""


def genere(avec_pdf=True):
    """Écrit le site dans son dossier (remplacé en entier) ; rend un résumé."""
    S = Site()
    S.pdf = pdfs({v for (_, v) in S.textes}) if avec_pdf else []
    d = sortie()
    tmp = d.with_name("site.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    ecrit = lambda chemin, texte: ((tmp / chemin).parent.mkdir(parents=True, exist_ok=True), (tmp / chemin).write_text(texte, encoding="utf-8"))
    ecrit("style.css", CSS)
    shutil.copy2(pathlib.Path(__file__).resolve().parents[2] / "front" / "visionneuse.js", tmp / "visionneuse.js")
    ordre = [c["slug"] for c in S.chapitres]
    for (slug, v) in S.textes:
        ecrit("chapitres/%s/%s.html" % (slug, v), S.chapitre(slug, v, ordre))
    for s in S.inclus:
        ecrit("fiches/%s.html" % s, S.fiche(s))
    ecrit("fiches/index.html", S.index_fiches())
    ecrit("index.html", S.accueil())                 # après les textes et les fiches : les citations sont recueillies
    ecrit("bibliographie.html", S.bibliographie())
    if S.frise:
        ecrit("frise.html", S.page_frise())
        ecrit("frise-donnees.js", S.donnees_frise())
        ecrit("frise.js", script_frise())
    ecrit("etat.json", json.dumps(S.etat(), ensure_ascii=False, indent=1))
    from . import planches
    for slug, k in S.planches:
        try:
            src = planches.chemin(slug, k)
        except KeyError:
            continue
        (tmp / "planches" / slug).mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, tmp / "planches" / slug / (k + ".svg"))
    for p in S.pdf:
        (tmp / "pdf").mkdir(exist_ok=True)
        shutil.copy2(racine() / "pdf" / p["fichier"], tmp / "pdf" / p["publie"])
    shutil.rmtree(d, ignore_errors=True)
    tmp.rename(d)
    n = sum(1 for _ in d.rglob("*.html"))
    return {"dossier": str(d), "pages": n, "textes": len(S.textes), "fiches": len(S.inclus), "oeuvres": len(S.cites & set(S.sources)),
            "pdf": [p["publie"] for p in S.pdf]}


# ------------------------------------------------------------------ publier

def _wrangler(cfg):
    if cfg.get("wrangler"):
        return [cfg["wrangler"]]
    w = shutil.which("wrangler")
    return [w] if w else ["npx", "--yes", "wrangler@4"]


def publie():
    """Génère le site, puis le déploie sur Cloudflare Pages ; crée le projet la première fois."""
    cfg = config()
    g = genere()
    w = _wrangler(cfg)
    env = dict(__import__("os").environ, CI="1", WRANGLER_SEND_METRICS="false")   # jamais de question : LimaLibri ne peut pas répondre
    deploie = w + ["pages", "deploy", g["dossier"], "--project-name", cfg["projet"], "--branch", "main", "--commit-dirty=true"]
    sortie_, cree = "", False
    # le projet d'abord : sans lui, wrangler demanderait lequel choisir (impossible ici). Déjà créé : il le dit, on continue.
    marque = racine() / ("projet-%s.ok" % cfg["projet"])
    if not marque.exists():
        c = subprocess.run(w + ["pages", "project", "create", cfg["projet"], "--production-branch", "main"],
                           capture_output=True, text=True, timeout=180, env=env)
        sc = (c.stdout or "") + (c.stderr or "")
        sortie_ += sc + "\n"
        if c.returncode == 0 or re.search(r"already exists|8000002|existe", sc, re.I):
            cree = c.returncode == 0
            racine().mkdir(parents=True, exist_ok=True)
            marque.write_text(livre._maintenant(), encoding="utf-8")
    r = subprocess.run(deploie, capture_output=True, text=True, timeout=900, env=env)
    sortie_ += (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 and re.search(r"not found|does not exist|8000007|non-interactive", sortie_, re.I):
        c = subprocess.run(w + ["pages", "project", "create", cfg["projet"], "--production-branch", "main"],
                           capture_output=True, text=True, timeout=180, env=env)
        cree = c.returncode == 0
        sortie_ += "\n" + (c.stdout or "") + (c.stderr or "")
        if cree:
            r = subprocess.run(deploie, capture_output=True, text=True, timeout=900, env=env)
            sortie_ += "\n" + (r.stdout or "") + (r.stderr or "")
    urls = re.findall(r"https://[\w.-]+\.pages\.dev", sortie_)
    res = dict(g, ok=r.returncode == 0, projet=cfg["projet"], adresse=cfg["adresse"],
               url="https://%s.pages.dev" % cfg["projet"] if r.returncode == 0 else None,   # l'adresse stable du site
               url_deploiement=urls[-1] if urls else None,                                 # celle de ce déploiement-ci
               projet_cree=cree, date=livre._maintenant(),
               journal=re.sub(r"\x1b\[[0-9;]*m", "", sortie_)[-3000:])
    if not res["ok"] and re.search(r"not authenticated|wrangler login|Authentication error|10000", sortie_, re.I):
        res["erreur"] = "wrangler n'est pas connecté à Cloudflare : lance « npx wrangler login » une fois dans un terminal"
    elif not res["ok"]:
        res["erreur"] = "le déploiement a échoué (voir le journal)"
    racine().mkdir(parents=True, exist_ok=True)
    (racine() / "derniere.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
