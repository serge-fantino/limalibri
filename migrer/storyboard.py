# -*- coding: utf-8 -*-
"""Reconstitue le storyboard d'un chapitre migré sans cadre, à partir de son récit seul.

    poetry run python3 migrer/storyboard.py le-corps le-sol …     ces chapitres
    poetry run python3 migrer/storyboard.py --tous                 tous ceux qui n'ont pas de plans
    poetry run python3 migrer/storyboard.py --tous --sec           la découpe seule, sans Claude ni écriture
    options : --modele claude-sonnet-5 (défaut) · --ecraser (refait un storyboard déjà reconstitué)
    ATELIER_LIVRE=… pour un autre livre

Deux temps :
  1. la découpe, déterministe : un plan par groupe de paragraphes entre deux « --- » du récit
     (A, B, C…). La règle vaut sans exception dans les chapitres dont le storyboard vient du
     cadre : chaque groupe y est un plan, et un seul. Chaque paragraphe (^id) est rattaché à
     son plan dans links.yaml — c'est ce qui fait la vue storyboard.
  2. Claude, un appel par chapitre, lit le récit et rend pour chaque plan son titre, son lieu,
     son temps, son ambiance, son attaque, sa chute, et un micro-récit par paragraphe — ce que
     le paragraphe montre, en une ligne. Le compte est vérifié plan par plan (une relance si
     faux). Pas d'assertions ni de séquence : il n'y a pas de verrou.

Le brief garde la trace : storyboard_origine (reconstitué depuis le texte, modèle, date). Un
storyboard venu d'un cadre (sans storyboard_origine) n'est jamais touché. Chaque appel est noté
au journal de consommation du livre.
"""
import os
import re
import sys
import json
import time
import asyncio
import pathlib
import datetime

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from atelier import livre, reecriture, consommation      # noqa: E402
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage   # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chapitre import dump                                # noqa: E402

MODELE = "claude-sonnet-5"
LETTRES = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CHAMPS = ("title", "lieu", "temps", "ambiance", "attaque", "chute")

SCHEMA = {
    "type": "object",
    "properties": {
        "suivi": {"type": "string"},
        "plans": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, **{k: {"type": "string"} for k in CHAMPS},
            "recits": {"type": "array", "items": {"type": "string"}}},
            "required": ["id", *CHAMPS, "recits"]}}},
    "required": ["suivi", "plans"]}

SYSTEME = """Tu reconstitues le storyboard d'un chapitre du récit d'un livre de vulgarisation (l'histoire
de la Terre et de la vie, racontée sans « nous », sans lecteur, sans histoire des découvertes). Le texte
est déjà écrit et découpé en plans ; tu décris ce qu'il fait, tu n'inventes rien et tu ne corriges rien.

Pour le chapitre :
- suivi : ce que le chapitre suit d'un bout à l'autre (un objet, un lieu, un fil), en une phrase courte.

Pour chaque plan (garde ses identifiants et son ordre) :
- title : un titre de 1 à 6 mots, concret, tiré du plan (« La mare », « Son propre plan »).
- lieu : où l'on est (« une cuvette de pierre sur une terre de volcans, à la surface »).
- temps : quand, et sur quelle durée (« un jour ; quelques heures », « le même »).
- ambiance : la tenue sensible du plan, en quelques mots.
- attaque : comment le plan s'ouvre (le premier geste du texte), en quelques mots.
- chute : comment il se ferme, en quelques mots.
- recits : EXACTEMENT un micro-récit par paragraphe du plan, dans l'ordre — ce que le paragraphe montre,
  en une ligne, sans majuscule initiale, au présent, sans citer le texte mot pour mot. Le compte est
  vérifié : autant de micro-récits que de paragraphes ([^id] dans le texte).

Tout en français. Ce que le texte ne dit pas, tu ne le dis pas."""


def exemples():
    """Deux storyboards venus d'un cadre, en modèle."""
    L = []
    for s in ("le-texte", "la-mer"):
        p = livre.dossier(s) / "brief.yaml"
        if not p.exists():
            continue
        b = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if b.get("storyboard_origine") or not b.get("beats"):
            continue
        L.append({"chapitre": s, "suivi": b.get("suivi", ""),
                  "plans": [{k: x.get(k) for k in ("id", *CHAMPS, "recits")} for x in b["beats"][:3]]})
    return L


def decoupe(slug):
    """[(lettre, [(bloc, texte)])] : un plan par groupe entre deux « --- »."""
    t = (livre.dossier(slug) / "recit.md").read_text(encoding="utf-8")
    plans = []
    for g in re.split(r"^---[ \t]*$", t, flags=re.M):
        paras = []
        for b in re.split(r"\n[ \t]*\n", g.strip()):
            m = re.search(r"[ \t]\^([a-z0-9]+)[ \t]*$", b)
            if m:
                paras.append((m.group(1), " ".join(b[:m.start()].split())))
        if paras:
            plans.append((LETTRES[len(plans)], paras))
    return plans


def message(slug, plans, erreur=None):
    c = next(x for x in livre.chapitres() if x["slug"] == slug)
    L = ["# Des storyboards du même livre, en modèle (extraits)",
         json.dumps(exemples(), ensure_ascii=False, indent=1), "",
         "# Le chapitre : %s%s" % (c["title"], " (%s)" % c["periode"] if c.get("periode") else ""), ""]
    for lettre, paras in plans:
        L.append("## Plan %s — %d paragraphe(s)" % (lettre, len(paras)))
        L += ["[^%s] %s" % (b, t) for b, t in paras]
        L.append("")
    if erreur:
        L.append("ATTENTION — ta réponse précédente était fausse : %s. Corrige-la." % erreur)
    return "\n".join(L)


def verifie(plans, sortie):
    attendus = {l: len(p) for l, p in plans}
    rendus = {p.get("id"): p for p in sortie.get("plans") or []}
    faux = []
    for l, n in attendus.items():
        p = rendus.get(l)
        if not p:
            faux.append("plan %s absent" % l)
        elif len(p.get("recits") or []) != n:
            faux.append("plan %s : %d micro-récits pour %d paragraphes" % (l, len(p.get("recits") or []), n))
    return "; ".join(faux)


async def demande(slug, plans, modele, erreur=None):
    options = ClaudeAgentOptions(max_buffer_size=reecriture.TAMPON, tools=[], allowed_tools=[], max_turns=3,
                                 setting_sources=[], cwd=str(livre.LIVRE), system_prompt=SYSTEME,
                                 output_format={"type": "json_schema", "schema": SCHEMA}, model=modele)
    t0, resultat, vu, err = time.time(), None, None, None
    try:
        async for m in query(prompt=message(slug, plans, erreur), options=options):
            if isinstance(m, AssistantMessage):
                vu = m.model
            elif isinstance(m, ResultMessage):
                resultat = m
        sortie = getattr(resultat, "structured_output", None) or (json.loads(resultat.result) if resultat and resultat.result else None)
        if not sortie:
            raise ValueError("aucune réponse structurée")
        return sortie
    except Exception as e:                          # noqa: BLE001
        err = "%s: %s" % (type(e).__name__, e)
        raise
    finally:
        consommation.note("migration", "storyboard", slug, chapitre=slug, phase="relance" if erreur else "initiale",
                          debut=consommation.debut_iso(t0), duree_s=round(time.time() - t0, 1), modele=vu, modele_choisi=modele,
                          issue="erreur" if err else "ok", erreur=err, tours=getattr(resultat, "num_turns", None),
                          jetons=reecriture.jetons(resultat), cout_usd=getattr(resultat, "total_cost_usd", None),
                          session=getattr(resultat, "session_id", None))


def ecrit(slug, plans, sortie, modele):
    d = livre.dossier(slug)
    pb = d / "brief.yaml"
    brut = pb.read_text(encoding="utf-8")
    tete = "".join(l + "\n" for l in brut.splitlines() if l.startswith("#") and "Storyboard reconstitué" not in l)
    tete = tete.replace("Pas encore de cadre : ni verrou ni storyboard.", "Pas encore de cadre : pas de verrou ; storyboard reconstitué depuis le texte.")
    b = yaml.safe_load(brut) or {"chapter": slug}
    jour = datetime.date.today().isoformat()
    tete += "# Storyboard reconstitué le %s depuis le récit seul (plans = groupes entre « --- »), par %s.\n\n" % (jour, modele)
    rendus = {p["id"]: p for p in sortie["plans"]}
    beats = []
    for l, paras in plans:
        p = rendus[l]
        beats.append({"id": l, **{k: " ".join(str(p.get(k) or "").split()) for k in CHAMPS},
                      "recits": [" ".join(r.split()) for r in p["recits"]]})
    b["suivi"] = " ".join((sortie.get("suivi") or "").split())
    b["storyboard_origine"] = {"par": "claude", "depuis": "le récit seul", "modele": modele, "date": jour}
    b["beats"] = beats
    pb.write_text(dump(tete, b), encoding="utf-8")
    liens = {bl: {"plan": l} for l, paras in plans for bl, _ in paras}
    (d / "links.yaml").write_text(dump("# Liens — %s. Bloc (^id) -> plan du storyboard (reconstitué depuis le texte ;\n"
                                       "# pas encore d'assertions : pas de verrou).\n\n" % slug, {"recit": liens}), encoding="utf-8")


def a_faire(slug, ecraser):
    d = livre.dossier(slug)
    if not (d / "recit.md").exists():
        return False
    b = yaml.safe_load((d / "brief.yaml").read_text(encoding="utf-8")) if (d / "brief.yaml").exists() else {}
    b = b or {}
    if b.get("beats") and not b.get("storyboard_origine"):
        return False                                  # un storyboard venu du cadre : jamais touché
    return ecraser or not b.get("beats")


async def un(slug, modele, sem, sec):
    plans = decoupe(slug)
    resume = "%d plans (%s)" % (len(plans), " ".join("%s:%d" % (l, len(p)) for l, p in plans))
    if sec:
        print("%-32s %s" % (slug, resume))
        return True
    async with sem:
        erreur = None
        for essai in range(2):
            try:
                sortie = await demande(slug, plans, modele, erreur)
            except Exception as e:                    # noqa: BLE001
                print("%-32s ÉCHEC — %s" % (slug, e))
                return False
            erreur = verifie(plans, sortie)
            if not erreur:
                ecrit(slug, plans, sortie, modele)
                print("%-32s %s — écrit%s" % (slug, resume, " (après relance)" if essai else ""))
                return True
        print("%-32s REFUS — %s" % (slug, erreur))
        return False


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    modele = MODELE
    if "--modele" in sys.argv:
        modele = sys.argv[sys.argv.index("--modele") + 1]
        args = [a for a in args if a != modele]
    ecraser, sec = "--ecraser" in sys.argv, "--sec" in sys.argv
    slugs = args or ([c["slug"] for c in livre.chapitres()] if "--tous" in sys.argv else [])
    if not slugs:
        sys.exit(__doc__)
    slugs = [s for s in slugs if a_faire(s, ecraser)]
    sem = asyncio.Semaphore(4)
    R = await asyncio.gather(*(un(s, modele, sem, sec) for s in slugs))
    print("%d/%d chapitre(s)%s" % (sum(R), len(R), " (à sec)" if sec else ""))


if __name__ == "__main__":
    asyncio.run(main())
