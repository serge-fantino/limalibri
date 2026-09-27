# -*- coding: utf-8 -*-
"""Migre un chapitre de l'ancien dépôt vers UneVie/book-atelier/chapters/<slug>/.

    poetry run python3 migrer/chapitre.py la-mer
    poetry run python3 migrer/chapitre.py la-mer --sec     vérifie sans écrire
    poetry run python3 migrer/chapitre.py la-mer --ecraser remplace aussi brief, textes et liens
    poetry run python3 migrer/chapitre.py --texte le-corps le-sol …   les textes seuls (voir plus bas)
    poetry run python3 migrer/chapitre.py --texte --tous            tous les chapitres sans dossier

Produit, à partir du cadre, du storyboard, de l'habillage et des deux chapitres :

    brief.yaml    fiches, intention, tenue, budget, interdits, plans     <- cadre + storyboard
                  (fiches : l'en-tête « fiches: » du chapitre de l'essai)
    verrou.yaml   les assertions, par section, avec statut et note       <- cadre §1
    recit.md      la prose du récit, un ^id par paragraphe                <- recit/chapitres
    essai.md      la prose de l'essai (ex-« livre »), un ^id par bloc     <- livre/chapitres
    links.yaml    bloc du récit -> plan + assertions                     <- marqueurs <!--A: …-->

Garanties, vérifiées avant toute écriture (le script refuse sinon) :
  · le texte, ancres retirées, est identique à la source ;
  · l'habillage et le chapitre posé ont les mêmes paragraphes ;
  · chaque assertion citée par un marqueur ou un plan existe dans le verrou.

Les ^id sont dérivés du slug, de la version et du rang : rejouer la migration
avant tout travail sur le texte redonne les mêmes. Après, ils vivent leur vie.
Lecture seule côté source.

--texte : pour un chapitre qui n'a pas encore de cadre (ni verrou, ni storyboard, ni habillage),
seulement ses deux textes. Écrit recit.md et essai.md (ancrés, mêmes garanties : le texte ancré
redonne la source), un brief minimal (les fiches de l'en-tête de l'essai, et sa « boucle » s'il
en a une) et un links.yaml vide. Le verrou et le storyboard viendront avec le cadre, par une
migration complète (--ecraser garde alors le verrou et ses liens vers l'essai). Ne touche pas un
chapitre qui a déjà son dossier.
"""
import os
import re
import sys
import hashlib
import pathlib
import datetime
import yaml

AWEN = pathlib.Path(__file__).resolve().parents[3]
SOURCE = AWEN / "noosphereV2" / "Books" / "UneVie-book"
CIBLE = pathlib.Path(os.environ.get("ATELIER_LIVRE", AWEN / "UneVie" / "book-atelier")) / "chapters"

ENTETE = re.compile(r"^---\n.*?\n---\n", re.S)
ANCRE = re.compile(r"[ \t]\^([a-z0-9]+)$")


class Refus(Exception):
    pass


# ---------------------------------------------------------------- texte et blocs

def corps(p):
    """Le corps d'un chapitre posé : sans en-tête, sans titre, sans ligne de période.

    Le titre et la période vivent dans structure.yaml ; les répéter ici ferait deux
    sources pour une même donnée."""
    t = ENTETE.sub("", p.read_text(encoding="utf-8"), count=1)
    m = re.match(r"\s*# [^\n]*\n(\s*\*[^\n]*\*\s*\n)?\s*---\s*\n+", t)    # la période peut manquer (préface)
    if not m:
        raise Refus("%s : en-tête « # Titre / *période* / --- » introuvable" % p)
    return t[m.end():].rstrip("\n") + "\n"


def blocs(texte):
    """Découpe en blocs séparés par une ligne vide. Rend (texte, ancrable)."""
    out = []
    for b in re.split(r"\n[ \t]*\n", texte.strip("\n")):
        tete = b.lstrip()
        ancrable = not (tete.startswith("#") or re.fullmatch(r"-{3,}|\*{3,}", tete.strip())
                        or tete.startswith("[^") or tete.startswith("|")
                        or tete.startswith("```") or tete.startswith("<!--"))   # un commentaire (FIGURE, BROUILLON)
        out.append((b, ancrable))
    return out


def ident(slug, version, rang, pris):
    # Quatre caractères, jamais tout en chiffres (lisible à côté d'une assertion « 1.1 »).
    for sel in range(1000):
        h = hashlib.sha1(("%s:%s:%d:%d" % (slug, version, rang, sel)).encode()).hexdigest()[:4]
        if h not in pris and not h.isdigit() and not re.fullmatch(r"\d+e\d+", h):   # « 5e56 » serait un nombre en YAML
            pris.add(h)
            return h
    raise Refus("collision d'identifiants")


def ancre(slug, version, texte, pris):
    """Pose un ^id à la fin de chaque bloc ancrable. Rend (texte ancré, [ids])."""
    sortie, ids, rang = [], [], 0
    for b, ancrable in blocs(texte):
        if ancrable:
            rang += 1
            i = ident(slug, version, rang, pris)
            ids.append(i)
            b = b.rstrip() + " ^" + i
        sortie.append(b)
    return "\n\n".join(sortie) + "\n", ids


def desancre(texte):
    return "\n".join(ANCRE.sub("", l) for l in texte.split("\n"))


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- cadre

def sections_md(texte, niveau="## "):
    """{titre: contenu} pour les titres d'un niveau donné."""
    parts = re.split(r"^" + re.escape(niveau) + r"(.+)$", texte, flags=re.M)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts), 2)}


def cle(label):
    # Les accents restent : YAML les accepte, et l'atelier affiche la clé telle quelle.
    return re.sub(r"[\s'’]+", "_", label.lower().strip(" .:—")).strip("_")


def etiquettes(texte):
    """Paragraphes « **Étiquette** — texte » -> dict ; le reste est ignoré."""
    d = {}
    for p in re.split(r"\n\s*\n|\n(?=\*\*)", texte):
        m = re.match(r"\s*\*\*(.+?)\*\*\s*[—:-]?\s*(.*)", p, re.S)
        if m:
            d[cle(m.group(1))] = norm(m.group(2))
    return d


def budget(texte):
    m = re.search(r"```budget\n(.*?)```", texte, re.S)
    if not m:
        return {}, [], []
    b, derog, interdits = {}, [], []
    for ligne in m.group(1).splitlines():
        k, _, v = ligne.partition(":")
        k, v = k.strip(), v.strip()
        if k == "derogations":
            derog = [v] if v else []
        elif k == "interdits":
            interdits = [x.strip() for x in v.split(",") if x.strip()]
        elif k:
            t = re.fullmatch(r"(\d+)\s*\+-\s*(\d+)", v)
            b[k] = {"cible": int(t.group(1)), "tolerance": int(t.group(2))} if t else int(v)
    return b, derog, interdits


STATUT = {"!": "obligatoire", "~": "supprimable", "✗": "retiree"}
ASSERTION = re.compile(r"^([!~✗])(\d+\.\d+[a-z]?)\s+(.*)$")
NOTE = re.compile(r"^(.*?)\s*((?:\[[^\]]*\]\s*)+)$", re.S)


def verrou(texte):
    v = sections_md(texte)
    cle1 = next(k for k in v if "Verrou" in k)
    corps_v = v[cle1]
    preambule = corps_v.split("### ", 1)[0]
    preambule = "\n\n".join(p for p in re.split(r"\n\s*\n", preambule.strip())
                            if not p.startswith("Extrait du texte") and "`!` obligatoire" not in p)
    sections = []
    for titre, contenu in sections_md(corps_v, "### ").items():
        m = re.match(r"§(\w+)\s*—\s*(.*)", titre)
        sec = {"id": m.group(1) if m else titre, "title": m.group(2) if m else titre,
               "assertions": []}
        bloc = re.search(r"```\n(.*?)```", contenu, re.S)
        courante = None
        for ligne in (bloc.group(1).splitlines() if bloc else []):
            a = ASSERTION.match(ligne)
            if a:
                courante = {"id": a.group(2), "statut": STATUT[a.group(1)], "_brut": a.group(3)}
                sec["assertions"].append(courante)
            elif courante and ligne.strip():
                courante["_brut"] += " " + ligne.strip()
        for a in sec["assertions"]:
            brut = norm(a.pop("_brut"))
            n = NOTE.match(brut)
            a["texte"] = n.group(1) if n else brut
            if n:
                a["note"] = " ".join(x.strip("[] ") for x in re.findall(r"\[[^\]]*\]", n.group(2)))
        sections.append(sec)
    return {"preambule": preambule.strip()} if preambule.strip() else {}, sections


# ---------------------------------------------------------------- storyboard

PLAN = re.compile(r"```plan (\w+)\s*—\s*(.*?)\n(.*?)```", re.S)


def plans(texte):
    out = []
    for lettre, titre, contenu in PLAN.findall(texte):
        champs, cour = {}, None
        for ligne in contenu.splitlines():
            m = re.match(r"^(\w+):\s*(.*)$", ligne)
            if m and not ligne.startswith((" ", "\t")):
                cour = m.group(1)
                champs[cour] = m.group(2).strip()
            elif cour and ligne.strip():
                champs[cour] += " " + ligne.strip()
        p = {"id": lettre, "title": titre.strip()}
        for k in ("lieu", "temps", "ambiance", "attaque", "chute"):
            if k in champs:
                p[k] = champs[k]
        p["assertions"] = champs.get("assertions", "")
        if "ajouts" in champs:
            p["ajouts"] = int(champs["ajouts"])
        if "sequence" in champs:
            p["sequence"] = [s.strip() for s in champs["sequence"].split("/")]
        if "recits" in champs:
            p["recits"] = [s.strip() for s in champs["recits"].split("|")]
        if "note" in champs:
            p["note"] = champs["note"]
        out.append(p)
    return out


def developpe(spec, ordre):
    """« 1.* », « 3.1-3.14 », « 2.1,2.4 » -> ids du verrou, dans l'ordre du verrou."""
    ids = []
    for morceau in [m.strip() for m in spec.split(",") if m.strip()]:
        if morceau.endswith(".*"):
            ids += [i for i in ordre if i.startswith(morceau[:-1])]
        elif "-" in morceau:
            a, b = morceau.split("-")
            if a not in ordre or b not in ordre:
                raise Refus("plage %s hors verrou" % morceau)
            ids += ordre[ordre.index(a):ordre.index(b) + 1]
        else:
            if morceau not in ordre:
                raise Refus("assertion %s hors verrou" % morceau)
            ids.append(morceau)
    return ids


# ---------------------------------------------------------------- liens

MARQUEUR = re.compile(r"\s*<!--(\w+):\s*([^>]*?)\s*-->\s*$")


def liens_habillage(hab, ids_recit, ordre):
    """Les marqueurs de l'habillage, reportés sur les ^id du récit, rang pour rang."""
    paras = [b for b, anc in blocs(ENTETE.sub("", hab, count=1)) if anc]
    if len(paras) != len(ids_recit):
        raise Refus("habillage : %d paragraphes, récit posé : %d" % (len(paras), len(ids_recit)))
    liens = {}
    for p, i in zip(paras, ids_recit):
        m = MARQUEUR.search(p)
        if not m:
            raise Refus("paragraphe sans marqueur : %s…" % norm(p)[:60])
        plan, val = m.group(1), m.group(2)
        if val == "+":
            liens[i] = {"plan": plan, "ajout": True}
        elif val == "tr":
            liens[i] = {"plan": plan, "transition": True}
        else:
            a = [x.strip() for x in val.split(",") if x.strip()]
            for x in a:
                if x not in ordre:
                    raise Refus("marqueur %s : assertion %s hors verrou" % (plan, x))
            liens[i] = {"plan": plan, "assertions": a}
    return paras, liens


# ---------------------------------------------------------------- yaml

class Bloc(str):
    pass


def _repr_str(d, s):
    if "\n" in s:
        return d.represent_scalar("tag:yaml.org,2002:str", s, style="|")
    return d.represent_scalar("tag:yaml.org,2002:str", s)


yaml.SafeDumper.add_representer(str, _repr_str)


def dump(entete, data):
    return entete + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)


# ---------------------------------------------------------------- migration

def migre(slug):
    cad = SOURCE / "recit" / "cadre"
    src = {"cadre": cad / (slug + ".md"),
           "storyboard": cad / (slug + ".storyboard.md"),
           "habillage": cad / (slug + ".habillage.md"),
           "recit": SOURCE / "recit" / "chapitres" / (slug + ".md"),
           "essai": SOURCE / "livre" / "chapitres" / (slug + ".md")}
    for k, p in src.items():
        if not p.exists():
            raise Refus("source absente (%s) : %s" % (k, p.relative_to(AWEN)))
    lire = lambda k: src[k].read_text(encoding="utf-8")
    rel = lambda k: str(src[k].relative_to(AWEN))
    jour = datetime.date.today().isoformat()

    # verrou
    cadre = ENTETE.sub("", lire("cadre"), count=1)
    notes_v, sections = verrou(cadre)
    ordre = [a["id"] for s in sections for a in s["assertions"]]
    if len(set(ordre)) != len(ordre):
        raise Refus("identifiant d'assertion en double dans le verrou")
    garde_verrou(slug, sections)

    # brief
    sec = sections_md(cadre)
    trouve = lambda mot: next((v for k, v in sec.items() if mot in k), "")
    b, derog, interdits = budget(cadre)
    sb = ENTETE.sub("", lire("storyboard"), count=1)
    sb_sec = sections_md(sb)
    beats = plans(sb)
    for p in beats:
        p["assertions"] = developpe(p["assertions"], ordre)
    contraintes = [norm(l[2:]) for l in sb_sec.get("Interdits propres au storyboard", "").splitlines()
                   if l.startswith("- ")]
    fiches = re.search(r"^fiches:\s*\[(.*)\]", (ENTETE.match(lire("essai")) or re.match("", "")).group(0), re.M)
    brief = {"chapter": slug,
             "intent": etiquettes(trouve("Intention")),
             "tenue": etiquettes(trouve("Tenue")),
             "suivi": sb_sec.get("Ce qui est suivi", "").strip().rstrip("-").strip(),
             "budget": b}
    if fiches:                               # les fiches de kb/fiches/ (en-tête du chapitre de l'essai)
        brief = {"chapter": slug, "fiches": [x.strip() for x in fiches.group(1).split(",") if x.strip()],
                 **{k: v for k, v in brief.items() if k != "chapter"}}
    if derog:
        brief["derogations"] = derog
    brief["interdits"] = interdits
    brief["constraints"] = contraintes
    brief["beats"] = beats

    # textes
    pris = set()
    recit_src, essai_src = corps(src["recit"]), corps(src["essai"])
    recit, ids_r = ancre(slug, "recit", recit_src, pris)
    essai, ids_e = ancre(slug, "essai", essai_src, pris)
    for nom, a, s in (("recit", recit, recit_src), ("essai", essai, essai_src)):
        if norm(desancre(a)) != norm(s) or desancre(a).strip() != s.strip():
            raise Refus("%s : le texte ancré ne redonne pas la source" % nom)

    # liens
    paras_hab, liens = liens_habillage(lire("habillage"), ids_r, ordre)
    for p_hab, (p_rec, anc) in zip(paras_hab, [x for x in blocs(recit_src) if x[1]]):
        if norm(MARQUEUR.sub("", p_hab)) != norm(p_rec):
            raise Refus("habillage et récit posé divergent : %s…" % norm(p_rec)[:60])
    plans_ids = {p["id"] for p in beats}
    for i, l in liens.items():
        if l["plan"] not in plans_ids:
            raise Refus("marqueur vers un plan inconnu : %s" % l["plan"])

    provenance = "# Importé le %s depuis :\n%s\n" % (
        jour, "".join("#   %s\n" % rel(k) for k in src))
    fichiers = {
        "brief.yaml": dump("# Brief — %s. Le contrat du chapitre : ce que le texte doit faire.\n"
                           % slug + provenance + "\n", brief),
        "verrou.yaml": dump("# Verrou — %s. Une assertion par entrée ; ids stables, on ajoute 5.9a,\n"
                            "# on ne renumérote pas. Une assertion retirée garde son motif et sa date.\n"
                            % slug + provenance + "\n",
                            dict({"chapter": slug}, **notes_v, **GARDE_TETE, sections=sections)),
        "links.yaml": dump("# Liens — %s. Bloc (^id) -> plan du brief + assertions du verrou.\n"
                           "# ajout: true = paragraphe hors verrou, autorisé par le quota du plan.\n"
                           % slug + provenance + "\n",
                           {"recit": liens}),
        "recit.md": recit,
        "essai.md": essai,
    }
    stats = {"assertions": len(ordre), "plans": len(beats),
             "blocs récit": len(ids_r), "blocs essai": len(ids_e),
             "ajouts": sum(1 for l in liens.values() if l.get("ajout"))}
    return fichiers, stats


# Champs du verrou qui ne viennent pas de la source : les liens vers l'essai et les
# écarts, posés par l'analyse (migrer/liens_essai.py) puis validés dans l'atelier.
# Une re-migration les reprend, assertion par assertion.
PROPRES_ATELIER = ("essai", "ecart")


def garde_verrou(slug, sections):
    GARDE_TETE.clear()
    p = CIBLE / slug / "verrou.yaml"
    if not p.exists():
        return
    ancien = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    par_id = {a["id"]: a for s in ancien.get("sections", []) for a in s["assertions"]}
    for s in sections:
        for a in s["assertions"]:
            for k in PROPRES_ATELIER:
                if k in par_id.get(a["id"], {}):
                    a[k] = par_id[a["id"]][k]
    for k in ("liens_essai",):
        if k in ancien:
            GARDE_TETE[k] = ancien[k]


GARDE_TETE = {}


def migre_texte(slug):
    """Les deux textes seuls, pour un chapitre sans cadre."""
    src = {"recit": SOURCE / "recit" / "chapitres" / (slug + ".md"),
           "essai": SOURCE / "livre" / "chapitres" / (slug + ".md")}
    for k, p in src.items():
        if not p.exists():
            raise Refus("source absente (%s) : %s" % (k, p.relative_to(AWEN)))
    pris, textes, stats = set(), {}, {}
    for v, p in src.items():
        s = corps(p)
        a, ids = ancre(slug, v, s, pris)
        if norm(desancre(a)) != norm(s) or desancre(a).strip() != s.strip():
            raise Refus("%s : le texte ancré ne redonne pas la source" % v)
        textes[v + ".md"], stats["blocs " + v] = a, len(ids)
    tete = (ENTETE.match(src["essai"].read_text(encoding="utf-8")) or re.match("", "")).group(0)   # pas du YAML strict : ligne à ligne
    brief = {"chapter": slug}
    f = re.search(r"^fiches:\s*\[(.*)\]", tete, re.M)
    if f:
        brief["fiches"] = [x.strip() for x in f.group(1).split(",") if x.strip()]
    b = re.search(r"^boucle:\s*(.+)$", tete, re.M)
    if b:
        brief["boucle"] = " ".join(b.group(1).split())
    provenance = "# Importé le %s (textes seuls, sans cadre) depuis :\n%s\n" % (
        datetime.date.today().isoformat(), "".join("#   %s\n" % p.relative_to(AWEN) for p in src.values()))
    fichiers = dict(textes)
    fichiers["brief.yaml"] = dump("# Brief — %s. Pas encore de cadre : ni verrou ni storyboard.\n" % slug + provenance + "\n", brief)
    fichiers["links.yaml"] = "recit: {}\n"
    stats["fiches"] = len(brief.get("fiches") or [])
    return fichiers, stats


def _identifie_essai(slug):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    os.environ.setdefault("ATELIER_LIVRE", str(CIBLE.parent))
    from atelier import essai as _essai
    return _essai.pose_identifiants(slug)


def main_texte():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--tous" in sys.argv:
        s = yaml.safe_load((CIBLE.parent / "structure.yaml").read_text(encoding="utf-8")) or {}
        args = [c["slug"] for c in (s.get("prefaces") or []) + [c for p in s.get("parts") or [] for c in p.get("chapters") or []]]
    faits, refus = 0, 0
    for slug in args:
        d = CIBLE / slug
        if d.exists():
            print("%-32s déjà dans l'atelier — laissé" % slug)
            continue
        try:
            fichiers, stats = migre_texte(slug)
        except Refus as e:
            print("%-32s REFUS — %s" % (slug, e))
            refus += 1
            continue
        print("%-32s %s" % (slug, "  ".join("%s %d" % kv for kv in stats.items())))
        if "--sec" in sys.argv:
            continue
        d.mkdir(parents=True)
        for nom, contenu in fichiers.items():
            (d / nom).write_text(contenu, encoding="utf-8")
        n = _identifie_essai(slug)
        faits += 1
    print("%d chapitre(s) migré(s)%s%s" % (faits, ", %d refus" % refus if refus else "", " (à sec)" if "--sec" in sys.argv else ""))


def main():
    if "--texte" in sys.argv:
        return main_texte()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    slug = args[0]
    try:
        fichiers, stats = migre(slug)
    except Refus as e:
        sys.exit("REFUS — %s" % e)
    print("  ".join("%s %d" % kv for kv in stats.items()))
    if "--sec" in sys.argv:
        return
    d = CIBLE / slug
    d.mkdir(parents=True, exist_ok=True)
    # le texte et le storyboard se travaillent dans l'atelier après migration : une
    # re-migration ne les écrase pas sans --ecraser (le verrou, lui, fusionne ses champs)
    proteges = ("brief.yaml", "recit.md", "essai.md", "links.yaml")
    gardes = [n for n in proteges if (d / n).exists() and "--ecraser" not in sys.argv]
    for nom, contenu in fichiers.items():
        if nom in gardes:
            continue
        (d / nom).write_text(contenu, encoding="utf-8")
    print("écrit : %s/{%s}" % (d.relative_to(AWEN), ",".join(n for n in fichiers if n not in gardes)))
    if gardes:
        print("gardés (déjà travaillés dans l'atelier ; --ecraser pour les remplacer) : " + ", ".join(gardes))
    # chaque intertitre de l'essai reçoit un identifiant stable ({#id}), une fois pour toutes
    import os
    os.environ.setdefault("ATELIER_LIVRE", str(CIBLE.parent))
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from atelier import essai as _essai
    n = _essai.pose_identifiants(slug)
    if n:
        print("essai : %d intertitre(s) identifié(s)" % n)


if __name__ == "__main__":
    main()
