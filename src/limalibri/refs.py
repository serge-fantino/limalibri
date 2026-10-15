# -*- coding: utf-8 -*-
"""Les références aux artefacts du livre : une adresse courte, qu'on copie dans LimaLibri et qu'on
colle dans une consigne, une annotation ou une question — Claude reçoit la partie visée.

    @fiche/luca                                 une fiche
    @fiche/luca#vient-avant-lui                 une section de fiche
    @oeuvre/coale2024                           une œuvre de la bibliographie
    @chapitre/la-mer                            un chapitre (synopsis, question, fiches, plan)
    @chapitre/la-mer/essai#monde-etrange        une section de l'essai
    @chapitre/la-mer/essai^b54b                 un paragraphe de l'essai
    @chapitre/la-mer/recit^c022                 un paragraphe du récit
    @chapitre/la-mer/plan/A                     un plan du storyboard
    @chapitre/la-mer/assertion/1.9              une assertion du verrou
    @chapitre/la-mer/note/la-mer-soleil-70      une note de l'essai
    @chapitre/la-mer/annotation/a-3a61ae        une annotation
    @partie/p1                                  une partie du plan
    @regle/recit/R11                            un garde-fou

Résoudre donne : un titre, le fichier (pour que Claude lise autour, avec Read), l'extrait exact
(le texte de la partie visée), et l'adresse de la vue dans LimaLibri. Une référence qui ne se
résout pas est signalée, jamais inventée.
"""
import re

import yaml

from . import livre

MOTIF = re.compile(r"(?<![\w\[])@(fiche|oeuvre|chapitre|partie|regle)/([\w./#^:-]+[\w-])")
EXTRAIT_MAX = 6000


def trouve(texte):
    """Les références d'un texte, dans l'ordre, sans doublon."""
    return list(dict.fromkeys("@%s/%s" % (m.group(1), m.group(2)) for m in MOTIF.finditer(texte or "")))


def _section_md(md, sid):
    """Le texte d'une section « ## … {#sid} » (jusqu'à la suivante de même niveau ou plus haute)."""
    lignes = md.split("\n")
    debut = niveau = None
    for i, l in enumerate(lignes):
        m = re.match(r"^(#{1,6})\s+.*\{#([\w-]+)\}\s*$", l)
        if m and m.group(2) == sid:
            debut, niveau = i, len(m.group(1))
            break
    if debut is None:
        return None
    fin = len(lignes)
    for j in range(debut + 1, len(lignes)):
        m = re.match(r"^(#{1,6})\s", lignes[j])
        if m and len(m.group(1)) <= niveau:
            fin = j
            break
    return "\n".join(lignes[debut:fin]).strip()


def _bloc(slug, version, bloc):
    from . import edition
    try:
        return edition.lit_bloc(slug, version, bloc)["texte"]
    except KeyError:
        return None


def resout(ref):
    """{ref, type, titre, fichier, extrait, vue, ok} — ok faux si rien ne correspond."""
    m = MOTIF.fullmatch(ref.strip())
    if not m:
        return {"ref": ref, "ok": False, "erreur": "syntaxe inconnue"}
    genre, chemin = m.group(1), m.group(2)
    r = {"ref": ref, "type": genre, "ok": False}
    try:
        if genre == "fiche":
            from . import kb
            slug, _, sec = chemin.partition("#")
            meta, corps = kb._lit(slug)
            titre = kb._structure(corps)[0] or slug
            r.update(fichier="kb/fiches/%s.md" % slug, vue="fiches/%s%s" % (slug, "/" + sec if sec else ""))
            if sec:
                x = _section_md(corps, sec)
                if x is None:
                    return dict(r, erreur="section « %s » introuvable dans la fiche %s" % (sec, slug))
                r.update(titre="fiche « %s », section %s" % (titre, sec), extrait=x)
            else:
                r.update(titre="fiche « %s »" % titre, extrait="sujet : %s\nconfiance : %s\nsections : %s" % (
                    meta.get("sujet", ""), meta.get("confiance", ""),
                    " · ".join("%s {#%s}" % (s["titre"], s["id"]) for s in kb._structure(corps)[1])),
                    note="la fiche entière : la lire (Read)")
        elif genre == "oeuvre":
            from . import sources
            o = sources.lit(chemin)
            ext = ["référence : %s" % o.get("ref"), "statut : %s" % o.get("statut")]
            if o.get("doi"):
                ext.append("DOI : %s" % o["doi"])
            for c in (o.get("citations") or [])[:10]:
                ext.append("citation : « %s »%s" % (c["texte"][:400], " (p. %s)" % c["page"] if c.get("page") else ""))
            T = sources.textes(chemin)
            if T:
                ext.append("texte intégral dans le livre : %s" % ", ".join("kb/documents/%s/%s.texte.txt" % (chemin, f) for f, _ in T))
            r.update(titre="œuvre %s" % chemin, fichier="kb/sources/%s.yaml" % chemin, extrait="\n".join(ext), vue="biblio/%s" % chemin)
        elif genre == "partie":
            from . import plan
            P = plan.lit()
            p = next((x for x in P["parties"] if x["id"] == chemin), None)
            if not p:
                return dict(r, erreur="partie inconnue")
            ext = ["sens : %s" % (p.get("sens") or ""), "arc : %s" % (p.get("arc") or ""), "question : %s" % (p.get("question") or "")]
            ext += ["- %s — %s : %s" % (c["slug"], c["title"], (c.get("synopsis") or "")[:300]) for c in p["chapitres"]]
            r.update(titre="partie « %s »" % p["title"], fichier="synopsis.yaml", extrait="\n".join(ext), vue="plan/p/%s" % chemin)
        elif genre == "regle":
            from . import regles
            version, _, rid = chemin.partition("/")
            e = next((x for x in regles.lit(version)["elements"] if x["id"] == rid), None)
            if not e:
                return dict(r, erreur="règle inconnue")
            r.update(titre="garde-fou %s — %s (%s)" % (rid, e["titre"], version), fichier="regles/%s.md" % version,
                     extrait=re.sub(r"```controle.*?```", "", e["texte"], flags=re.S).strip(), vue="livre/regles/%s/%s" % (version, rid))
        else:
            r.update(**_chapitre(chemin))
    except KeyError as e:
        return dict(r, erreur="introuvable : %s" % e)
    if r.get("extrait") and len(r["extrait"]) > EXTRAIT_MAX:
        r["extrait"] = r["extrait"][:EXTRAIT_MAX] + "\n[…] (la suite dans le fichier)"
    r["ok"] = bool(r.get("titre"))
    return r


def _chapitre(chemin):
    """@chapitre/<slug>[/essai|recit[#section|^bloc]][/plan|assertion|note|annotation/<id>]"""
    m = re.match(r"^([\w-]+)(?:/(.*))?$", chemin)
    slug, reste = m.group(1), m.group(2) or ""
    c = next((x for x in livre.chapitres() if x["slug"] == slug), None)
    if not c:
        raise KeyError(slug)
    d = livre.dossier(slug)
    nom = "chapitre %s « %s »" % (c.get("numero") or "", c["title"])
    m = re.match(r"^(essai|recit)(?:([#^])([\w-]+))?$", reste)
    if m:
        v, sep, x = m.group(1), m.group(2), m.group(3)
        f = "chapters/%s/%s.md" % (slug, v)
        vue = "%s/%s" % (slug, "essai/texte" if v == "essai" else "recit/texte")
        if sep == "^":
            t = _bloc(slug, v, x)
            if t is None:
                raise KeyError("paragraphe ^%s" % x)
            return {"titre": "%s, %s, paragraphe ^%s" % (nom, v, x), "fichier": f, "extrait": t, "vue": vue}
        if sep == "#":
            t = _section_md((d / (v + ".md")).read_text(encoding="utf-8"), x)
            if t is None:
                raise KeyError("section %s" % x)
            return {"titre": "%s, %s, section %s" % (nom, v, x), "fichier": f, "extrait": re.sub(r"\s\^[a-z0-9]+\s*$", "", t, flags=re.M), "vue": vue}
        return {"titre": "%s, %s" % (nom, v), "fichier": f, "extrait": "le texte entier : le lire (Read)", "vue": vue}
    m = re.match(r"^(plan|assertion|note|annotation)/(.+)$", reste)
    if m:
        genre, x = m.groups()
        at = livre.atelier(slug)
        if genre == "plan":
            b = next((p for p in (at["brief"].get("beats") or []) if str(p.get("id")) == x), None)
            if not b:
                raise KeyError("plan %s" % x)
            return {"titre": "%s, plan %s — %s" % (nom, x, b.get("title", "")), "fichier": "chapters/%s/brief.yaml" % slug,
                    "extrait": yaml.safe_dump(b, allow_unicode=True, sort_keys=False, width=100), "vue": "%s/recit/storyboard" % slug}
        if genre == "assertion":
            a = at["assertions"].get(x)
            if not a:
                raise KeyError("assertion %s" % x)
            ext = "%s (%s) : %s" % (x, a.get("statut"), a.get("texte"))
            if a.get("note"):
                ext += "\nnote du verrou : %s" % a["note"]
            if a.get("ecart"):
                ext += "\nécart : %s" % a["ecart"].get("texte")
            return {"titre": "%s, assertion %s" % (nom, x), "fichier": "chapters/%s/verrou.yaml" % slug, "extrait": ext,
                    "vue": "%s/recit/storyboard" % slug}
        if genre == "note":
            md = (d / "essai.md").read_text(encoding="utf-8")
            n = re.search(r"^\[\^%s\]:\s*(.+?)(?=^\[\^|^#|\Z)" % re.escape(x), md, re.S | re.M)
            if not n:
                raise KeyError("note %s" % x)
            return {"titre": "%s, note %s" % (nom, x), "fichier": "chapters/%s/essai.md" % slug,
                    "extrait": " ".join(n.group(1).split()), "vue": "%s/essai/notes" % slug}
        a = next((y for y in livre.annotations(slug) if y["id"] == x), None)
        if not a:
            raise KeyError("annotation %s" % x)
        return {"titre": "%s, annotation %s (%s, %s)" % (nom, x, a["type"], a["etat"]), "fichier": "chapters/%s/annotations.jsonl" % slug,
                "extrait": "sur « %s » (%s ^%s) : %s" % (a.get("citation") or "", a["version"], a["bloc"], a.get("texte") or ""),
                "vue": "%s/%s" % (slug, "essai/texte" if a["version"] == "essai" else "recit/texte")}
    if reste:
        raise KeyError(reste)
    br = {}
    if (d / "brief.yaml").exists():
        br = yaml.safe_load((d / "brief.yaml").read_text(encoding="utf-8")) or {}
    ext = ["période : %s" % (c.get("periode") or ""), "synopsis : %s" % (br.get("synopsis") or ""),
           "question : %s" % (br.get("question") or ""), "fiches : %s" % ", ".join(str(x) for x in br.get("fiches") or [])]
    if (d / "essai.md").exists():
        from . import essai
        try:
            P = essai.plan(slug)

            def f(s, ind, L):
                if s["id"]:
                    L.append("%s%s {#%s}" % ("  " * ind, s["titre"], s["id"]))
                for e in s["enfants"]:
                    f(e, ind + 1, L)
            L = []
            f(P["arbre"], 0, L)
            ext.append("sections de l'essai :\n" + "\n".join(L))
        except Exception:                          # noqa: BLE001
            pass
    return {"titre": nom, "fichier": "chapters/%s/" % slug, "extrait": "\n".join(ext), "vue": "plan/c/%s" % slug}


def annexe(*textes):
    """La section de contexte donnée à Claude pour les références d'une consigne (vide s'il n'y en a pas)."""
    R = [resout(r) for r in trouve("\n".join(t or "" for t in textes))]
    if not R:
        return ""
    L = ["\n## Les références données par l'auteur (la partie visée ; le fichier pour lire autour)"]
    for r in R:
        if not r["ok"]:
            L.append("\n### %s — introuvable (%s)" % (r["ref"], r.get("erreur", "")))
            continue
        L.append("\n### %s — %s\nfichier : %s%s\n%s" % (r["ref"], r["titre"], r.get("fichier", ""),
                                                      " (%s)" % r["note"] if r.get("note") else "", r.get("extrait", "")))
    return "\n".join(L)
