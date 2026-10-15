# -*- coding: utf-8 -*-
"""Le serveur de l'atelier.

    poetry run uvicorn atelier.serveur:app --reload --port 8765

L'API vit sous /api ; tout le reste sert le front (front/), sans étape de build.
"""
import sys
import pathlib
import subprocess
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import livre, reecriture, regles, essai, verification, edition, validation, verrou, kb, creation, confiance, pistes, file, renvois, export, references, sources, harnais, naif, documents, plan, planif, refs, conversation, consommation, redaction, suivi, serie, evenements, objectifs, execution, capacites, cadrage, pilotage
from . import versions as depot          # git : marquer une version du livre (le nom « versions » est pris)

FRONT = pathlib.Path(__file__).resolve().parent.parent / "front"

app = FastAPI(title="Atelier")


@app.middleware("http")
async def _sans_cache_du_front(request, appel):
    """Le front (index, atelier.js, atelier.css) : toujours revalidé. Sans cette directive, le navigateur
    gardait un atelier.js périmé après une mise à jour ; avec, il redemande et reçoit un 304 si rien n'a changé."""
    r = await appel(request)
    if not request.url.path.startswith("/api/"):
        r.headers["Cache-Control"] = "no-cache"
    return r

# Un dossier qui n'est pas encore un livre le devient : livre.yaml et structure.yaml vides.
for nom in livre.initialise() + regles.initialise():
    print("atelier : %s créé dans %s" % (nom, livre.LIVRE))
if reecriture.interrompues():
    print("atelier : des demandes en cours ont été interrompues par le redémarrage (marquées en erreur)")
conversation.interrompues()


@app.on_event("startup")
async def _branche_les_evenements():
    import asyncio
    evenements.branche(asyncio.get_running_loop())
    try:
        evenements.sur_les_signaux()            # les flux se ferment dès le signal d'arrêt
    except ValueError:                          # hors du fil principal (tests) : sans objet
        pass


@app.on_event("shutdown")
async def _ferme_les_evenements():
    evenements.ferme()                          # les flux ouverts ne retiennent pas le redémarrage


@app.get("/api/evenements")
async def fil_evenements(request: Request):
    """Le fil des événements (Server-Sent Events) : demandes, progrès, séries, conversations."""
    return StreamingResponse(evenements.flux(request), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.on_event("startup")
async def _reprend_la_file():
    """Au démarrage : les séries et les plans d'abord (une étape interrompue les arrête, ou les bloque — leurs
    demandes en file attendent alors), puis la file repart (les lots actifs, et le reste si l'enchaînement
    est activé). Dans l'autre ordre, la suivante d'un plan interrompu partait avant qu'il soit bloqué."""
    try:
        serie.avance()                          # une série dont l'étape a été interrompue s'arrête, et le dit
        pilotage.avance()                       # un plan d'objectif aussi (bloqué sur l'action interrompue)
    except Exception as e:                      # noqa: BLE001
        print("atelier : séries —", e)
    try:
        file.suivante()
    except Exception as e:                      # noqa: BLE001
        print("atelier : file d'attente —", e)


def _meta(m):
    return dict(m, dossier=livre.affiche(livre.LIVRE), editables=list(livre.EDITABLES),
                chemins={n: str(livre.LIVRE / n) for n in ("livre.yaml", "structure.yaml")})


@app.get("/api/livre")
def meta():
    """Ce qui décrit le livre, plus son dossier (pour savoir sur quoi l'atelier travaille)."""
    return _meta(livre.meta())


@app.put("/api/livre")
async def ecrit_meta(request: Request):
    """Modifie des champs de livre.yaml : {"champs": {...}, "version": "<empreinte lue>"}."""
    corps = await request.json()
    try:
        return _meta(livre.ecrit_meta(corps.get("champs") or {}, corps.get("version", "")))
    except livre.Conflit as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(400, "champ non modifiable ici : %s" % e)


@app.post("/api/livre/couverture")
async def couverture(request: Request, nom: str, version: str):
    try:
        return _meta(livre.ecrit_couverture(nom, await request.body(), version))
    except livre.Conflit as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(400, str(e))


@app.get("/api/regles")
def lit_regles():
    """Les garde-fous d'écriture de chaque version (regles/<version>.md)."""
    return regles.toutes()


def _regles_ecrit(f):
    try:
        return f()
    except regles.Conflit as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(404, "élément inconnu : %s" % e)


@app.put("/api/regles/{version}/{ident}")
async def modifie_regle(version: str, ident: str, request: Request):
    c = await request.json()
    return _regles_ecrit(lambda: regles.modifie(version, ident, c.get("titre"), c.get("texte", ""),
                                                c.get("empreinte", "")))


@app.post("/api/regles/{version}")
async def ajoute_regle(version: str, request: Request):
    c = await request.json()
    if not (c.get("titre") or "").strip():
        raise HTTPException(400, "une règle a un titre")
    return _regles_ecrit(lambda: regles.ajoute(version, c["titre"], c.get("texte", ""), c.get("empreinte", "")))


@app.delete("/api/regles/{version}/{ident}")
def supprime_regle(version: str, ident: str, empreinte: str):
    return _regles_ecrit(lambda: regles.supprime(version, ident, empreinte))


@app.get("/api/livre/fichier")
def fichier(chemin: str):
    try:
        return FileResponse(livre.fichier(chemin))
    except KeyError:
        raise HTTPException(404, "fichier absent du livre : %s" % chemin)


@app.post("/api/ouvrir")
def ouvrir(chemin: str):
    """Ouvre un fichier du livre dans l'application par défaut du poste (l'atelier est local)."""
    try:
        p = livre.fichier(chemin)
    except KeyError:
        raise HTTPException(404, "fichier absent du livre : %s" % chemin)
    cmd = ["open", str(p)] if sys.platform == "darwin" else ["xdg-open", str(p)]
    subprocess.Popen(cmd)
    return {"ouvert": str(p)}


@app.get("/api/structure")
def structure():
    return livre.structure()


@app.get("/api/chapitres")
def chapitres():
    """Les chapitres dans l'ordre, avec leur avancement par version (vide … valide)."""
    from . import avancement
    return [dict(c, avancement=avancement.tous(c)) for c in livre.chapitres()]


@app.get("/api/sources")
def sources_html():
    return livre.sources()


@app.get("/api/chapitres/{slug}/atelier")
def atelier(slug: str):
    try:
        return livre.atelier(slug)
    except KeyError:
        raise HTTPException(404, "chapitre pas encore migré : %s" % slug)


@app.get("/api/chapitres/{slug}/annotations")
def annotations(slug: str):
    try:
        return livre.annotations(slug)
    except KeyError:
        raise HTTPException(404, "chapitre pas encore migré : %s" % slug)


@app.post("/api/chapitres/{slug}/annotations")
async def cree_annotation(slug: str, request: Request):
    try:
        return livre.cree_annotation(slug, await request.json())
    except KeyError:
        raise HTTPException(404, "chapitre pas encore migré : %s" % slug)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.patch("/api/chapitres/{slug}/annotations/{ident}")
async def modifie_annotation(slug: str, ident: str, request: Request):
    try:
        return livre.modifie_annotation(slug, ident, await request.json())
    except KeyError:
        raise HTTPException(404, "annotation inconnue : %s" % ident)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/chapitres/{slug}/annotations/{ident}")
def supprime_annotation(slug: str, ident: str):
    try:
        livre.supprime_annotation(slug, ident)
        return {"supprime": ident}
    except KeyError:
        raise HTTPException(404, "annotation inconnue : %s" % ident)


@app.put("/api/chapitres/{slug}/brief")
async def modifie_brief(slug: str, request: Request):
    """L'en-tête du storyboard : {champs: {"suivi": …, "intent.tension": …, …}, empreinte}."""
    c = await request.json()
    try:
        return livre.modifie_brief(slug, c.get("champs") or {}, c.get("empreinte", ""), c.get("motif", ""))
    except livre.Conflit as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/chapitres/{slug}/plans/{pid}")
async def modifie_plan(slug: str, pid: str, request: Request):
    """Recadrer un plan du storyboard : {champs: {...}, recits: {rang: texte}, empreinte}."""
    c = await request.json()
    try:
        return livre.modifie_plan(slug, pid, c.get("champs") or {}, c.get("recits") or {},
                                  c.get("empreinte", ""), c.get("motif", ""))
    except livre.Conflit as e:
        raise HTTPException(409, str(e))
    except KeyError:
        raise HTTPException(404, "plan inconnu : %s" % pid)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/chapitres/{slug}/storyboard/{op}")
async def forme_storyboard(slug: str, op: str, request: Request):
    """La forme du storyboard : recit_ajoute | recit_retire | recit_deplace | plan_ajoute | plan_retire —
    {plan, rang?, vers?, texte?, title?, apres?, empreinte}."""
    c = await request.json()
    try:
        return livre.forme_plan(slug, op, c, c.get("empreinte", ""), c.get("motif", ""))
    except livre.Conflit as e:
        raise HTTPException(409, str(e))
    except KeyError:
        raise HTTPException(404, "plan inconnu : %s" % c.get("plan"))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/chapitres/{slug}/essai/plan")
def plan_essai(slug: str):
    """L'arbre de l'essai : sections (à toute profondeur) et paragraphes."""
    try:
        return essai.plan(slug)
    except KeyError:
        raise HTTPException(404, "pas d'essai dans l'atelier pour : %s" % slug)


@app.post("/api/chapitres/{slug}/essai/structure")
async def structure_essai(slug: str, request: Request):
    """Réorganiser l'essai : {op: deplace|renomme|niveau|insere|supprime, …, empreinte}."""
    c = await request.json()
    e = c.get("empreinte", "")
    ops = {
        "deplace": lambda: essai.deplace(slug, e, c["quoi"], c["cible"]),
        "renomme": lambda: essai.renomme(slug, e, c["section"], c["titre"]),
        "niveau": lambda: essai.niveau(slug, e, c["section"], int(c["delta"])),
        "insere": lambda: essai.insere_section(slug, e, c["titre"], c.get("niveau", 2), c["cible"]),
        "supprime": lambda: essai.supprime_section(slug, e, c["section"]),
    }
    if c.get("op") not in ops:
        raise HTTPException(400, "opération inconnue : %s" % c.get("op"))
    try:
        return ops[c["op"]]()
    except essai.Conflit as ex:
        raise HTTPException(409, str(ex))
    except KeyError as ex:
        raise HTTPException(404, "inconnu : %s" % ex)
    except ValueError as ex:
        raise HTTPException(400, str(ex))


@app.get("/api/chapitres/{slug}/demandes")
def demandes(slug: str):
    try:
        return reecriture.liste(slug)
    except KeyError:
        raise HTTPException(404, "chapitre pas encore migré : %s" % slug)


@app.post("/api/chapitres/{slug}/demandes")
async def cree_demande(slug: str, request: Request):
    """Lance une réécriture : Claude travaille en tâche de fond, la page interroge l'état."""
    try:
        return reecriture.cree(slug, await request.json())
    except KeyError:
        raise HTTPException(404, "chapitre pas encore migré : %s" % slug)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/annotations")
def toutes_les_annotations():
    """Les annotations de tout le livre, avec leur chapitre."""
    return livre.toutes_annotations()


@app.get("/api/demandes")
def toutes_les_demandes():
    """Les demandes de tout le livre, avec leur chapitre."""
    return reecriture.liste_toutes()


@app.post("/api/demandes/verifier")
def verifie_demandes():
    """Confronter l'état des demandes « en cours » à leurs tâches réelles ; les perdues passent en erreur."""
    return {"corrigees": reecriture.verifie()}


@app.post("/api/chapitres/{slug}/demandes/{ident}/verifier")
def verifie_demande(slug: str, ident: str):
    try:
        c = reecriture.verifie(slug, ident)
        return dict(reecriture.lit(slug, ident), corrigee=bool(c))
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)


@app.post("/api/chapitres/{slug}/demandes/{ident}/reprise")
async def reprise(slug: str, ident: str):
    """Reprendre une demande arrêtée dans sa session : Claude rend sa réponse sans chercher plus."""
    try:
        return reecriture.reprise(slug, ident)
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/chapitres/{slug}/demandes/{ident}/encore")
async def encore(slug: str, ident: str, request: Request):
    """Chercher encore : la session de la vérification, rouverte avec un budget neuf. {consigne}"""
    c = await request.json()
    try:
        return reecriture.encore(slug, ident, c.get("consigne", ""))
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/modeles")
def modeles():
    """Les modèles qu'on peut choisir, et ceux que le livre retient par défaut."""
    return {"modeles": reecriture.MODELES,
            "defaut": {g: reecriture.modele(g) for g in ("verification", "reecriture", "fiche", "pistes", "reference", "naive", "document", "plan",
                                                               "redaction", "cadrage")}
                       | {g: reecriture.modele(g) or "claude-fable-5-1" for g in ("relecture", "storyboard", "recit")},   # Fable, sauf réglage
            "limites": {g: reecriture.limites(g) for g in ("verification", "reecriture", "fiche", "pistes", "reference", "naive", "document", "plan",
                                                           "conversation", "redaction", "cadrage", "relecture", "storyboard", "recit")}}


@app.get("/api/fiches")
def fiches():
    """Les fiches de la base de connaissance (kb/fiches/), avec leurs liens."""
    return kb.index()


@app.get("/api/fiches-graphe")
def fiches_graphe(resolution: float = 1.0, oeuvres: float = 0.5, chapitres: float = 0.5):
    """Le graphe des fiches (liens, œuvres partagées, chapitres) et ses clusters thématiques."""
    return kb.graphe(max(0.2, min(3.0, resolution)), max(0.0, oeuvres), max(0.0, chapitres))


@app.get("/api/fiches/demandes")
def fiches_demandes():
    """Les demandes de création de fiche (kb/demandes/)."""
    return reecriture.liste("_kb")


def _filles(c):
    """Le contexte d'une demande lancée depuis une autre ({origine, sujet}) : filiation et sujet notés."""
    import contextlib
    from . import filiation
    pile = contextlib.ExitStack()
    if c.get("origine"):
        pile.enter_context(filiation.depuis(c["origine"]))
    if c.get("sujet"):
        pile.enter_context(filiation.marque(sujet=" ".join(str(c["sujet"]).split())))
    return pile


@app.get("/api/demandes/{ident}/filles")
def filles(ident: str):
    """Les demandes nées d'une demande : leur état, leur sujet, la fiche créée."""
    return reecriture.filles(ident)


@app.post("/api/fiches/demandes")
async def cree_fiche(request: Request):
    """Lancer une création de fiche : {question, slug?, chapitres?, consigne?, longueur?, modele?,
    depuis?, sources_initiales?, origine?, sujet?}. Claude cherche en tâche de fond. origine : la demande
    d'où elle vient (une proposition de plan, une rédaction) — la fiche en est la fille ; sujet : le manque
    qu'elle traite, tel que la mère l'a écrit (pour que la mère dise où en est chacun de ses sujets)."""
    c = await request.json()
    try:
        with _filles(c):
            return creation.cree(c)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/oeuvres")
def oeuvres():
    """Toutes les œuvres : base centrale, bibliographies des chapitres, sources des fiches."""
    return kb.oeuvres()


@app.get("/api/oeuvres/statuts")
def statuts_oeuvres():
    return {"statuts": sources.STATUTS, "base": sources.existe()}


@app.get("/api/refs")
def refs_resout(texte: str = "", ref: str = ""):
    """Résoudre les références d'un texte (ou une seule) : [{ref, ok, titre, fichier, extrait, vue}]."""
    return [refs.resout(r) for r in ([ref] if ref else refs.trouve(texte))]


@app.get("/api/consommation")
def consommation_stats(depuis: str = "", jusqua: str = ""):
    """Les statistiques du journal de consommation (consommation.jsonl), sur une période AAAA-MM-JJ."""
    return consommation.stats(depuis or None, jusqua or None)


@app.get("/api/consommation/journal")
def consommation_journal():
    """Le journal brut, à télécharger (une ligne JSON par exécution de Claude)."""
    from fastapi.responses import FileResponse, PlainTextResponse
    f = consommation.fichier()
    if not f.exists():
        return PlainTextResponse("", media_type="application/x-ndjson")
    return FileResponse(f, media_type="application/x-ndjson", filename=consommation.NOM)


@app.get("/api/objectifs")
def objectifs_liste():
    """Les objectifs (bruts, dans l'ordre de priorité) et la définition des critères."""
    return {"objectifs": objectifs.lit_tous(), **objectifs.definitions()}


@app.post("/api/objectifs")
async def objectif_cree(request: Request):
    """{titre, version, perimetre: {type: livre|partie|chapitres, …}, criteres: [{id, valeur}], intention?, echeance?,
    budget?, marquer?: {nom, message}} — marquer : la version actuelle est d'abord taguée dans git, et devient le
    départ de l'objectif (rien n'est créé si le tag échoue)."""
    c = await request.json()
    try:
        objectifs._propre(c)                            # valider avant de toucher à git
        m = c.get("marquer")
        dep = depot.marque(m.get("nom"), m.get("message") or "avant l'objectif « %s »" % c.get("titre")) if m else None
        o = objectifs.cree(c)
        return objectifs.pose_depart(o["id"], dep) if dep else o
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(409, "git : %s" % e)


@app.post("/api/storyboards")
async def cree_storyboard(request: Request):
    """Le storyboard d'un chapitre du récit, depuis son essai : {chapitre, consigne?, modele?, poser?}."""
    from . import storyboard
    try:
        return storyboard.cree(await request.json())
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/recits")
async def cree_recit(request: Request):
    """Le récit d'un chapitre depuis son storyboard : {chapitre, plan?, rang?, consigne?, modele?, poser?}."""
    from . import narration
    try:
        return narration.cree(await request.json())
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/relectures")
async def cree_relecture(request: Request):
    """Une relecture critique : {partie | chapitres, version?, consigne?, modele?} — Claude annote ce qu'il trouve."""
    from . import relecture
    try:
        return relecture.cree(await request.json())
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/relectures/{ident}/appliquer")
async def relecture_applique(ident: str, request: Request):
    """Appliquer une relecture : {annotations: [id], consigne?, poser?, modele?} — une série de révisions, une par
    chapitre concerné, chacune ne traitant que les annotations choisies."""
    from . import relecture
    try:
        return relecture.applique(ident, await request.json())
    except KeyError:
        raise HTTPException(404, "relecture inconnue : %s" % ident)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/relectures/{ident}/annotations")
def relecture_annotations(ident: str):
    """Les annotations posées par une relecture critique, chapitre par chapitre, avec leur état."""
    from . import relecture
    try:
        return relecture.posees(reecriture.lit("_kb", ident))
    except KeyError:
        raise HTTPException(404, "relecture inconnue : %s" % ident)


@app.get("/api/capacites")
def capacites_liste():
    """Le catalogue : ce que l'atelier sait faire (capacités, propositions de cadre), avec le coût moyen dans ce livre."""
    return capacites.catalogue()


@app.post("/api/objectifs/{ident}/cadrer")
async def objectif_cadre(ident: str, request: Request):
    """Cadrer un objectif avec Claude : {consigne?, modele?} — une demande « cadrage », dans la file."""
    try:
        return cadrage.cree(ident, await request.json())
    except KeyError:
        raise HTTPException(404, "objectif inconnu : %s" % ident)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/objectifs/{ident}/pilotage")
def objectif_pilotage(ident: str):
    """Le pilotage d'un objectif : son plan retenu (s'il y en a un) et ses cadrages (le plus récent en entier)."""
    K = sorted((x for x in reecriture.liste("_kb") if x.get("type") == "cadrage"), key=lambda x: x["cree"], reverse=True)
    K = [x for x in K if (reecriture.lit("_kb", x["id"]).get("cible") or {}).get("objectif") == ident]
    dernier = reecriture.lit("_kb", K[0]["id"]) if K else None
    if dernier:
        dernier.pop("contexte", None)
    P = pilotage.lit(ident)
    if P:                                              # chaque demande lancée : son état réel, sa place dans la file
        rangs = {x["id"]: x["rang"] for x in file.etat()["en_attente"]}
        for ph in P["phases"]:
            for a in ph["actions"]:
                if a.get("demande"):
                    d = pilotage._etat_demande(a)
                    dec = (d or {}).get("decision") or {}
                    a["vivant"] = {"etat": d and d.get("etat"), "rang": rangs.get(a["demande"]),
                                   "titre": d and d.get("titre"), "cout": ((d or {}).get("execution") or {}).get("cout_usd"),
                                   "issue": None if not d or d.get("etat") != "decidee" else
                                   "rejetee" if dec.get("proposition") is None else "retenue"}
    if P:                                              # le budget de l'objectif, pour le comparer au plan
        o = next((x for x in objectifs.lit_tous() if x.get("id") == ident), {})
        P["budget"] = o.get("budget")
    return {"plan": P, "cadrages": [{k: x.get(k) for k in ("id", "etat", "cree", "titre")} for x in K],
            "cadrage": dernier, "catalogue": capacites.catalogue()}


@app.post("/api/objectifs/{ident}/pilotage/retenir")
async def objectif_retient(ident: str, request: Request):
    """{demande, actions: [id], cadre: [index], couper: [id], edits?, options?} — le plan retenu (prêt)."""
    try:
        return pilotage.retient(ident, await request.json())
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except pilotage.Conflit as e:
        raise HTTPException(409, str(e))
    except (ValueError, reecriture.Conflit) as e:
        raise HTTPException(400, str(e))


@app.post("/api/objectifs/{ident}/pilotage/actions/{aid}/{op}")
def objectif_action(ident: str, aid: str, op: str):
    """Une action du plan : fait (une tâche de l'auteur), sauter, relancer (une action en erreur)."""
    try:
        return pilotage.geste_action(ident, aid, op)
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except pilotage.Conflit as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/objectifs/{ident}/pilotage/{op}")
def objectif_geste(ident: str, op: str):
    """Le plan : demarrer, pause, continuer (après un point d'arrêt), arreter."""
    try:
        return pilotage.geste(ident, op)
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except pilotage.Conflit as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/objectifs/{ident}/plan")
def objectif_plan(ident: str):
    """Le plan d'exécution d'un objectif : ses écarts, traduits en travail (Claude ou auteur), avec coût et état."""
    try:
        return execution.plan(ident)
    except KeyError:
        raise HTTPException(404, "objectif inconnu : %s" % ident)


@app.post("/api/objectifs/{ident}/executer")
async def objectif_execute(ident: str, request: Request):
    """{items: [id], poser?, modele?, consigne?, forcer?} — les éléments de Claude retenus deviennent une série."""
    try:
        return execution.execute(ident, await request.json())
    except KeyError:
        raise HTTPException(404, "objectif inconnu : %s" % ident)
    except OverflowError as e:
        raise HTTPException(409, "budget : %s" % e)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/objectifs/{ident}/depart")
async def objectif_depart(ident: str, request: Request):
    """Le départ d'un objectif : {tag} (une version déjà marquée) ou {nom, message} (marquer maintenant)."""
    c = await request.json()
    try:
        if c.get("tag"):
            t = next((x for x in depot.etat().get("tags") or [] if x["tag"] == c["tag"]), None)
            if not t:
                raise ValueError("version inconnue : %s" % c["tag"])
            dep = {"tag": t["tag"], "date": t["date"]}
        else:
            o = next(x for x in objectifs.lit_tous() if x.get("id") == ident)
            dep = depot.marque(c.get("nom"), c.get("message") or "départ de l'objectif « %s »" % o.get("titre"))
        return objectifs.pose_depart(ident, dep)
    except (KeyError, StopIteration):
        raise HTTPException(404, "objectif inconnu : %s" % ident)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(409, "git : %s" % e)


@app.get("/api/versions")
def versions_etat():
    """Le livre dans git : actif ?, préfixe des tags, fichiers non commités, versions marquées, nom suivant."""
    return depot.etat()


@app.post("/api/versions")
async def versions_marque(request: Request):
    """Marquer la version actuelle : {nom, message} — commit du seul dossier du livre, puis tag (local)."""
    c = await request.json()
    try:
        return depot.marque(c.get("nom"), c.get("message"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(409, "git : %s" % e)


@app.get("/api/versions/historique")
def versions_historique(n: int = 25):
    """Les derniers commits qui touchent le dossier du livre (avec leurs tags)."""
    return depot.historique(n)


@app.get("/api/versions/depuis")
def versions_depuis(tag: str, version: str = "essai"):
    """Ce qui a changé depuis une version marquée : fichiers, mots du texte par chapitre."""
    try:
        return depot.depuis(tag, version)
    except KeyError:
        raise HTTPException(404, "version inconnue : %s" % tag)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/objectifs/ordre")
async def objectifs_ordre(request: Request):
    """{ids: [...]} — l'ordre de priorité."""
    return {"objectifs": objectifs.ordonne((await request.json()).get("ids") or [])}


@app.put("/api/objectifs/{ident}")
async def objectif_modifie(ident: str, request: Request):
    try:
        return objectifs.modifie(ident, await request.json())
    except KeyError:
        raise HTTPException(404, "objectif inconnu : %s" % ident)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/objectifs/{ident}/juge")
async def objectif_juge(ident: str, request: Request):
    """L'intention, jugée : {atteint, note?}."""
    try:
        return objectifs.juge(ident, await request.json())
    except KeyError:
        raise HTTPException(404, "objectif inconnu : %s" % ident)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/objectifs/{ident}")
def objectif_supprime(ident: str):
    try:
        return objectifs.supprime(ident)
    except KeyError:
        raise HTTPException(404, "objectif inconnu : %s" % ident)


@app.get("/api/suivi/{version}")
def suivi_version(version: str):
    """Le suivi d'une version : chaque chapitre noté par étapes, le livre, et ce qu'il reste à faire."""
    try:
        return suivi.suivi(version)
    except KeyError:
        raise HTTPException(404, "version inconnue : %s" % version)


@app.get("/api/frise")
def frise_livre():
    """La frise du livre (frise.yaml) : échelles, bandes, repères, la place de chaque chapitre, les frises internes."""
    from . import frise
    return frise.lit()


@app.post("/api/frise/amorcer")
def frise_amorcer():
    """Écrit un premier frise.yaml depuis les périodes des chapitres ; jamais par-dessus un fichier existant."""
    from . import frise
    try:
        return frise.amorce()
    except FileExistsError:
        raise HTTPException(409, "frise.yaml existe déjà : on l'édite à la main")


@app.get("/api/publication")
def publication():
    """Le site public du livre : sa configuration, sa dernière publication, s'il a un aperçu."""
    from . import public
    return {"config": public.config(), "derniere": public.derniere(), "apercu": (public.sortie() / "index.html").exists(),
            "dossier": str(public.sortie())}


@app.post("/api/publication/apercu")
def publication_apercu():
    """Génère le site public (sans le publier) : l'aperçu, servi sous /apercu-public/."""
    from . import public
    return public.genere()


@app.post("/api/publication/publier")
def publication_publier():
    """Génère le site public et le déploie sur Cloudflare Pages (wrangler)."""
    from . import public
    return public.publie()


@app.get("/apercu-public/{chemin:path}")
def apercu_public(chemin: str):
    from . import public
    base = public.sortie().resolve()
    p = (base / (chemin or "index.html")).resolve()
    if p.is_dir():
        p = p / "index.html"
    if base not in p.parents and p != base or not p.is_file():
        raise HTTPException(404, "pas dans l'aperçu : %s" % chemin)
    return FileResponse(p)


@app.get("/api/series")
def series():
    return serie.liste()


@app.post("/api/series")
async def serie_cree(request: Request):
    """Enchaîner des actions sur des chapitres : {chapitres, actions: [brief, ecrire, naif], version?, consigne?, longueur?, modele?}."""
    try:
        return serie.cree(await request.json())
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/series/{ident}/{op}")
def serie_op(ident: str, op: str):
    try:
        if op == "arreter":
            return serie.arrete(ident)
        if op == "reprendre":
            return serie.reprend(ident)
    except KeyError:
        raise HTTPException(404, "série inconnue")
    raise HTTPException(404, "opération inconnue")


@app.get("/api/suivi/{version}/{slug}")
def suivi_chapitre(version: str, slug: str):
    """Le suivi d'un chapitre : sa note par étapes et ses prochaines actions."""
    try:
        return suivi.un(version, slug)
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)


@app.post("/api/redaction")
async def redaction_cree(request: Request):
    """Écrire l'essai d'un chapitre depuis son brief : {chapitre, consigne?, longueur?, modele?, poser?, remplacer?}."""
    try:
        return redaction.cree(await request.json())
    except KeyError as e:
        raise HTTPException(404, "chapitre inconnu : %s" % e)
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/chapitres/{slug}/manques")
def manques_chapitre(slug: str):
    """Ce qui manque à l'essai d'un chapitre : manques des rédactions, phrases qui parlent de la base."""
    return redaction.manques(slug)


@app.get("/api/chapitres/{slug}/historique")
def historique_essai(slug: str):
    """Les versions de l'essai d'un chapitre : écritures, révisions, restaurations, et ce qu'elles ont remplacé."""
    return redaction.historique(slug)


@app.get("/api/chapitres/{slug}/historique/{nom}")
def historique_version(slug: str, nom: str):
    try:
        return redaction.version_archivee(slug, nom)
    except KeyError:
        raise HTTPException(404, "version inconnue")


@app.post("/api/chapitres/{slug}/historique/{nom}/restaurer")
def historique_restaure(slug: str, nom: str):
    """Remettre une version archivée (la présente est archivée à son tour)."""
    try:
        return redaction.restaure(slug, nom)
    except KeyError:
        raise HTTPException(404, "version inconnue")


@app.post("/api/redaction/serie")
async def redaction_serie(request: Request):
    """Écrire l'essai de plusieurs chapitres, l'un après l'autre : {partie?, chapitres?, poser?, consigne?, longueur?, modele?}."""
    try:
        return redaction.serie(await request.json())
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/conversations")
def conversations():
    return conversation.liste()


@app.post("/api/conversations")
async def conversation_cree(request: Request):
    """Une conversation neuve : {question?, ici?, modele?}. Avec une question, Claude répond aussitôt."""
    try:
        return conversation.cree(await request.json())
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/conversations/{ident}")
def conversation_lit(ident: str):
    try:
        return conversation.lit(ident)
    except KeyError:
        raise HTTPException(404, "conversation inconnue")


@app.post("/api/conversations/{ident}")
async def conversation_demande(ident: str, request: Request):
    """Un tour de plus : {question, ici?}."""
    try:
        return conversation.demande(ident, await request.json())
    except KeyError:
        raise HTTPException(404, "conversation inconnue")
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/conversations/{ident}")
def conversation_supprime(ident: str):
    try:
        conversation.supprime(ident)
        return {"ok": True}
    except KeyError:
        raise HTTPException(404, "conversation inconnue")
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))


@app.post("/api/conversations/{ident}/tours/{n}/actions/{i}")
async def conversation_action(ident: str, n: int, i: int, request: Request):
    """Lancer une action proposée (paramètres revus éventuellement) : elle devient une demande."""
    try:
        return conversation.lance(ident, n, i, await request.json())
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/plan")
def plan_lit():
    """Le plan et le synopsis : le livre, ses parties, ses chapitres."""
    return plan.lit()


@app.post("/api/plan")
async def plan_op(request: Request):
    """Une opération sur le plan : {op, ...}.
    livre {champs} · partie_ajoute {titre, apres?} · partie {id, champs} · partie_deplace {id, sens} ·
    partie_supprime {id} · chapitre_ajoute {partie, titre, apres?} · chapitre {slug, champs} ·
    chapitre_deplace {slug, partie?, sens?} · chapitre_supprime {slug}"""
    c = await request.json()
    op = c.get("op")
    try:
        if op == "livre":
            return plan.modifie_livre(c.get("champs") or {})
        if op == "partie_ajoute":
            plan.ajoute_partie(c.get("titre"), c.get("apres"), c.get("champs"))
        elif op == "partie":
            plan.modifie_partie(c["id"], c.get("champs") or {})
        elif op == "partie_deplace":
            plan.deplace_partie(c["id"], int(c.get("sens") or 0))
        elif op == "partie_supprime":
            plan.supprime_partie(c["id"])
        elif op == "chapitre_ajoute":
            plan.ajoute_chapitre(c["partie"], c.get("titre"), c.get("slug"), c.get("apres"), c.get("champs"))
        elif op == "chapitre":
            plan.modifie_chapitre(c["slug"], c.get("champs") or {})
        elif op == "chapitre_deplace":
            plan.deplace_chapitre(c["slug"], c.get("partie"), int(c.get("sens") or 0))
        elif op == "chapitre_supprime":
            plan.supprime_chapitre(c["slug"])
        else:
            raise ValueError("opération inconnue : %s" % op)
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return plan.lit()


@app.post("/api/plan/propose")
async def plan_propose(request: Request):
    """Demander une proposition à Claude : {niveau: livre|partie|chapitre, partie?, chapitre?, consigne?, modele?}."""
    c = await request.json()
    try:
        return planif.cree(c)
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/oeuvres/{cle}")
def oeuvre_detail(cle: str):
    """Tout sur une œuvre : la base, où elle est citée, ses documents, ses citations, ses vérifications,
    les doublons possibles, les demandes et le journal."""
    import json as _json
    O = {o["cle"]: o for o in kb.oeuvres()}
    if cle not in O:
        raise HTTPException(404, "œuvre inconnue : %s" % cle)
    base = sources.toutes().get(cle)
    ds = [d for d in reecriture.liste("_kb") if d.get("cle") == cle] if (livre.LIVRE / "kb").exists() else []
    j = livre.LIVRE / "kb" / "journal.jsonl"
    journal = [e for e in (_json.loads(l) for l in j.read_text(encoding="utf-8").splitlines() if l.strip())
               if e.get("cle") == cle] if j.exists() else []
    return {"oeuvre": O[cle], "base": base, "usages": references.usages(cle),
            "candidats": [{"cle": c, "pourquoi": p, "ref": sources.toutes()[c].get("ref")} for c, p in references.candidats(cle, base)] if base else [],
            "demandes": ds, "journal": journal[-40:]}


@app.post("/api/oeuvres/{cle}/documents")
async def televerse_document(cle: str, request: Request, nom: str = "document.pdf"):
    """Téléverser le document d'une œuvre (corps brut ; ?nom=fichier.pdf)."""
    try:
        return sources.ajoute_document(cle, nom, await request.body(), "téléversé par l'auteur")
    except KeyError:
        raise HTTPException(404, "œuvre absente de kb/sources : %s" % cle)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/oeuvres/{cle}/documents/url")
async def document_depuis_url(cle: str, request: Request):
    """Télécharger le document d'une œuvre depuis une adresse : {url}."""
    c = await request.json()
    try:
        return documents.range_url(cle, (c.get("url") or "").strip())
    except KeyError:
        raise HTTPException(404, "œuvre absente de kb/sources : %s" % cle)
    except Exception as e:                       # noqa: BLE001 — réseau, mur, type
        raise HTTPException(400, "téléchargement impossible : %s" % e)


@app.get("/api/oeuvres/{cle}/documents/{fichier}")
def lit_document(cle: str, fichier: str):
    try:
        p = sources.dossier_documents(cle) / fichier
    except KeyError:
        raise HTTPException(404, "œuvre inconnue")
    if "/" in fichier or not p.exists():
        raise HTTPException(404, "document inconnu")
    return FileResponse(p, media_type=sources.TYPES_DOC.get(p.suffix.lower(), "application/octet-stream"),
                        headers={"Content-Disposition": "inline"})


@app.delete("/api/oeuvres/{cle}/documents/{fichier}")
def retire_document(cle: str, fichier: str):
    try:
        return sources.supprime_document(cle, fichier)
    except KeyError:
        raise HTTPException(404, "inconnu")


@app.post("/api/oeuvres/{cle}/original")
async def cherche_original(cle: str, request: Request):
    """Chercher le texte original en accès libre : {consigne?, modele?}. Claude propose, l'auteur choisit."""
    c = await request.json()
    try:
        return documents.cree({"cle": cle, "consigne": c.get("consigne"), "modele": c.get("modele")})
    except KeyError:
        raise HTTPException(404, "œuvre absente de kb/sources : %s" % cle)


@app.post("/api/oeuvres/{cle}/citations")
async def ajoute_citation(cle: str, request: Request):
    """Une citation (le passage mot pour mot) : {texte, page?, usage?}."""
    c = await request.json()
    try:
        return sources.ajoute_citation(cle, c.get("texte"), c.get("page"), c.get("usage"))
    except KeyError:
        raise HTTPException(404, "œuvre absente de kb/sources : %s" % cle)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/oeuvres/{cle}/citations/{i}")
def retire_citation(cle: str, i: int):
    try:
        return sources.supprime_citation(cle, i)
    except KeyError:
        raise HTTPException(404, "inconnue")


@app.put("/api/oeuvres/{cle}")
async def modifie_oeuvre(cle: str, request: Request):
    """Modifier une œuvre de kb/sources à la main : {champs: {ref, doi, url, statut, doute, notes}, motif}."""
    c = await request.json()
    try:
        return sources.modifie(cle, c.get("champs") or {}, c.get("motif", ""))
    except KeyError:
        raise HTTPException(404, "œuvre inconnue : %s" % cle)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/oeuvres")
async def ajoute_oeuvre(request: Request):
    """Ajouter une œuvre à la base (une œuvre « hors base ») : {cle, ref, doi?, url?, origine?, doute?}."""
    c = await request.json()
    try:
        return sources.ajoute(c.get("cle"), {k: c[k] for k in ("ref", "doi", "url", "origine", "doute", "notes", "fiches") if c.get(k)},
                              c.get("motif", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/oeuvres/{cle}/verification")
async def verifie_oeuvre(cle: str, request: Request):
    """Vérifier une référence (tout de suite) : {consigne?, modele?}."""
    c = await request.json()
    try:
        return references.cree({"cle": cle, "consigne": c.get("consigne"), "modele": c.get("modele")})
    except KeyError:
        raise HTTPException(404, "œuvre absente de kb/sources : %s — l'y ajouter d'abord" % cle)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/oeuvres/verifications")
async def verifie_oeuvres(request: Request):
    """Vérifier un lot : {cles: [...], modele?} — mises en attente dans la file (lancées à la main,
    ou enchaînées si l'option est activée)."""
    c = await request.json()
    faites = []
    for cle in c.get("cles") or []:
        try:
            faites.append(references.cree({"cle": cle, "modele": c.get("modele")}, lancer=False)["id"])
        except KeyError:
            continue
    file.suivante()
    return {"en_attente": faites}


@app.post("/api/fiches/{slug}/confiance")
async def lit_confiance(slug: str, request: Request):
    """Lancer la lecture de la confiance par paragraphe d'une fiche : {modele?}."""
    c = await request.json()
    try:
        return confiance.lance(slug, reecriture._choix_modele(c))
    except KeyError:
        raise HTTPException(404, "fiche inconnue : %s" % slug)
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/file")
def file_etat():
    """La file d'attente : réglage (auto, simultanées), en cours, en attente. Les demandes « en cours »
    perdues (tâche morte) sont d'abord ramenées à leur état réel."""
    reecriture.verifie()
    return file.etat()


@app.put("/api/file")
async def file_reglage(request: Request):
    """{auto?, simultanees?} — écrit dans livre.yaml ; activer l'enchaînement lance la suivante."""
    c = await request.json()
    m = livre.meta()
    livre.ecrit_meta({"claude": {"file": {k: c[k] for k in ("auto", "simultanees", "creer_d_office", "profondeur", "enfants") if k in c}}}, m["_version"])
    file.suivante()
    return file.etat()


@app.post("/api/file/{ident}/lance")
def file_lance(ident: str):
    try:
        return file.lance(ident)
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/file/{ident}/retire")
def file_retire(ident: str):
    try:
        return file.retire(ident)
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))


@app.post("/api/fiches/{slug}/renvois")
async def propose_renvois(slug: str, request: Request):
    """Proposer les renvois vers une fiche dans les voisines qu'elle cite. {consigne?, modele?, voisines?}"""
    c = await request.json()
    try:
        return renvois.cree({"fiche": slug, **{k: c[k] for k in ("consigne", "modele", "voisines") if k in c}})
    except KeyError:
        raise HTTPException(404, "fiche inconnue : %s" % slug)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/fiches/{slug}/renvois")
def voisines_sans_renvoi(slug: str):
    try:
        return {"voisines": renvois.voisines(slug)}
    except KeyError:
        raise HTTPException(404, "fiche inconnue : %s" % slug)


@app.get("/api/kb/imprimable", response_class=HTMLResponse)
def kb_imprimable():
    """La base de connaissance en un document HTML autonome, à imprimer (⌘P) ou à lire."""
    return export.imprimable()


@app.get("/api/essai/imprimable", response_class=HTMLResponse)
def essai_imprimable():
    """L'essai en un document HTML autonome : page de garde, table des matières, parties et chapitres."""
    return export.version_imprimable("essai")


@app.get("/api/recit/imprimable", response_class=HTMLResponse)
def recit_imprimable():
    """Le récit en un document HTML autonome : page de garde, table des matières, parties et chapitres."""
    return export.version_imprimable("recit")


@app.get("/api/complet/imprimable", response_class=HTMLResponse)
def complet_imprimable(portee: str = "utilisees"):
    """L'essai et la base de connaissance en un document HTML : chaque chapitre avec ses fiches et sa mini-carte,
    la carte du livre (cliquable, vivante au survol), les fiches (avec les chapitres qu'elles servent), une
    bibliographie commune. portee : utilisees (les fiches des briefs) ou toutes."""
    from . import compagnon
    return compagnon.imprimable(portee)


@app.get("/api/complet/pdf")
async def complet_pdf(portee: str = "utilisees"):
    """La même édition en PDF (Chrome sans interface), liens internes gardés."""
    from urllib.parse import quote
    try:
        donnees, nom = await export.pdf("complet", portee)
    except RuntimeError as e:
        raise HTTPException(501, str(e))
    return Response(donnees, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''%s" % quote(nom)})


@app.get("/api/essai/pdf")
async def essai_pdf():
    """L'essai en PDF (Chrome sans interface), liens internes gardés."""
    return await _pdf_version("essai")


@app.get("/api/recit/pdf")
async def recit_pdf():
    """Le récit en PDF."""
    return await _pdf_version("recit")


async def _pdf_version(quoi):
    from urllib.parse import quote
    try:
        donnees, nom = await export.pdf(quoi)
    except RuntimeError as e:
        raise HTTPException(501, str(e))
    return Response(donnees, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''%s" % quote(nom)})


@app.get("/api/kb/pdf")
async def kb_pdf():
    """La base de connaissance en PDF (Chrome sans interface), liens internes gardés."""
    from urllib.parse import quote
    try:
        donnees, nom = await export.pdf()
    except RuntimeError as e:
        raise HTTPException(501, str(e))
    return Response(donnees, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''%s" % quote(nom)})


@app.get("/api/fiches/{slug}/consequences")
def consequences(slug: str):
    """Ce qui dépend d'une fiche : fiches qui la citent, chapitres, œuvres."""
    try:
        return kb.consequences(slug)
    except KeyError:
        raise HTTPException(404, "fiche inconnue : %s" % slug)


@app.post("/api/fiches/{slug}/supprimer")
async def supprime_fiche(slug: str, request: Request):
    """Le ménage : {liens: laisser|retirer, motif}. La fiche va à kb/corbeille/."""
    c = await request.json()
    if c.get("liens", "laisser") not in ("laisser", "retirer"):
        raise HTTPException(400, "liens : laisser ou retirer")
    try:
        return kb.supprime(slug, c.get("liens", "laisser"), (c.get("motif") or "").strip())
    except KeyError:
        raise HTTPException(404, "fiche inconnue : %s" % slug)


@app.get("/api/fiches/{slug}/liens-proposes")
def liens_proposes(slug: str):
    """Les liens retour proposés par Claude à la création de la fiche, pas encore écrits."""
    try:
        return renvois.liens_proposes(slug)
    except FileNotFoundError:
        raise HTTPException(404, "fiche inconnue : %s" % slug)


@app.post("/api/fiches/{slug}/relue")
async def marque_relue(slug: str, request: Request):
    """Une fiche écrite par Claude, relue : son état passe de brouillon à relue ; {liens_retour: true}
    écrit aussi le lien retour dans les fiches voisines proposées à la création."""
    try:
        corps = await request.json()
    except Exception:                               # noqa: BLE001 — un appel sans corps
        corps = {}
    try:
        return renvois.marque_relue(slug, bool(corps.get("liens_retour")))
    except KeyError:
        raise HTTPException(404, "fiche inconnue : %s" % slug)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/chapitres/{slug}/demandes/{ident}/classer")
def classe_demande(slug: str, ident: str):
    """Clore une demande en erreur sans la relancer."""
    try:
        return reecriture.classe(slug, ident)
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))


@app.post("/api/fiches/{slug}/pistes")
async def creuse(slug: str, request: Request):
    """Creuser une fiche : Claude propose des fiches complémentaires. {consigne?, modele?}"""
    c = await request.json()
    try:
        with _filles(c):
            return pistes.cree({"fiche": slug, "consigne": c.get("consigne"), "modele": c.get("modele")})
    except KeyError:
        raise HTTPException(404, "fiche inconnue : %s" % slug)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/fiches/{slug}/confiance")
def etat_confiance(slug: str):
    return confiance.etat(slug)


@app.get("/api/fiches/{slug}")
def fiche(slug: str):
    """Une fiche : texte, sections, liens sortants et entrants, chapitres, œuvres."""
    try:
        return kb.fiche(slug)
    except KeyError:
        raise HTTPException(404, "fiche inconnue : %s" % slug)


@app.get("/api/chapitres/{slug}/recherches")
def recherches(slug: str):
    """Le carnet de recherche du chapitre."""
    return verification.carnet(slug)


@app.post("/api/chapitres/{slug}/demandes/{ident}/relance")
async def relance(slug: str, ident: str, request: Request):
    """Relancer une demande sur l'état présent du livre : {consigne (facultatif)}."""
    c = await request.json()
    try:
        return reecriture.relance(slug, ident, c.get("consigne"), c.get("modele", False))
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/chapitres/{slug}/demandes/{ident}")
def demande(slug: str, ident: str):
    try:
        d = reecriture.lit(slug, ident)
        d["fichier"] = str(reecriture._dossier(slug) / (ident + ".json"))
        return d
    except KeyError:
        raise HTTPException(404, "demande inconnue : %s" % ident)


@app.post("/api/chapitres/{slug}/verifications")
async def cree_verification(slug: str, request: Request):
    """Vérifier des assertions : Claude cherche (livre, puis web), rend verdicts et propositions."""
    try:
        return verification.cree(slug, await request.json())
    except KeyError:
        raise HTTPException(404, "chapitre pas encore migré : %s" % slug)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/chapitres/{slug}/demandes/{ident}/decision")
async def decide(slug: str, ident: str, request: Request):
    try:
        if ident.startswith("v-"):
            return verification.decide(slug, ident, await request.json())
        if ident.startswith("f-"):
            return creation.decide(ident, await request.json())
        if ident.startswith("p-"):
            return pistes.decide(ident, await request.json())
        if ident.startswith("l-"):
            return renvois.decide(ident, await request.json())
        if ident.startswith("r-"):
            return references.decide(ident, await request.json())
        if ident.startswith("n-"):
            return naif.decide(slug, ident, await request.json())
        if ident.startswith("o-"):
            return documents.decide(ident, await request.json())
        if ident.startswith("s-"):
            return planif.decide(ident, await request.json())
        if ident.startswith("e-"):
            return redaction.decide(ident, await request.json())
        if ident.startswith("k-"):
            return cadrage.decide(ident, await request.json())
        if ident.startswith("q-"):
            from . import relecture
            return relecture.decide(ident, await request.json())
        if ident.startswith("b-"):
            from . import storyboard
            return storyboard.decide(ident, await request.json())
        if ident.startswith("t-"):
            from . import narration
            return narration.decide(ident, await request.json())
        return reecriture.decide(slug, ident, await request.json())
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


def _edition(f):
    try:
        return f()
    except edition.Conflit as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))


@app.get("/api/chapitres/{slug}/{version}/blocs/{bloc}")
def lit_bloc(slug: str, version: str, bloc: str):
    """Le Markdown d'un paragraphe, pour le corriger."""
    return _edition(lambda: edition.lit_bloc(slug, version, bloc))


@app.put("/api/chapitres/{slug}/{version}/blocs/{bloc}")
async def modifie_bloc(slug: str, version: str, bloc: str, request: Request):
    """Corriger un paragraphe : {texte, avant (le texte lu), motif}."""
    c = await request.json()
    return _edition(lambda: edition.modifie_bloc(slug, version, bloc, c.get("texte", ""), c.get("avant", ""),
                                                 c.get("motif", "")))


@app.post("/api/chapitres/{slug}/{version}/blocs/{bloc}/apres")
async def insere_bloc(slug: str, version: str, bloc: str, request: Request):
    c = await request.json()
    return _edition(lambda: edition.insere_bloc(slug, version, bloc, c.get("texte", ""), c.get("motif", ""), c.get("micro", "")))


@app.delete("/api/chapitres/{slug}/{version}/blocs/{bloc}")
async def supprime_bloc(slug: str, version: str, bloc: str, request: Request):
    c = await request.json()
    return _edition(lambda: edition.supprime_bloc(slug, version, bloc, c.get("avant", ""), c.get("motif", ""), bool(c.get("force"))))


@app.post("/api/chapitres/{slug}/recit/paragraphes/{op}")
async def paragraphe_recit(slug: str, op: str, request: Request):
    """Le récit à la main, rangé par plan : ajoute {plan, rang, texte} | retire {bloc, avant, force?} | deplace {bloc, vers}."""
    from . import narration
    c = await request.json()
    try:
        return narration.paragraphe(slug, op, c)
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/chapitres/{slug}/harnais/{version}")
def harnais_rapport(slug: str, version: str):
    """Les portes d'une version d'un chapitre : ok ou non, et chaque relevé."""
    try:
        return harnais.rapport(slug, version)
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)


@app.post("/api/chapitres/{slug}/harnais/{version}/naif")
async def harnais_naif(slug: str, version: str, request: Request):
    """Lancer une lecture naïve : {modele?}."""
    c = await request.json()
    try:
        return naif.cree(slug, {"version": version, "modele": c.get("modele")})
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/chapitres/{slug}/harnais/{version}/valider")
async def harnais_valide(slug: str, version: str, request: Request):
    """Valider la version : l'état présent devient la référence. {motif} si une porte bloque."""
    c = await request.json()
    try:
        return harnais.valide(slug, version, c.get("motif", ""))
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/chapitres/{slug}/validation")
def etat_validation(slug: str):
    """Ce qui a changé depuis la dernière validation, paragraphe par paragraphe."""
    try:
        return validation.etat(slug)
    except KeyError:
        raise HTTPException(404, "chapitre pas encore migré : %s" % slug)


@app.post("/api/chapitres/{slug}/validation")
async def marque_valide(slug: str, request: Request):
    """Marquer validé : {version, blocs (facultatif : sinon toute la version)}."""
    c = await request.json()
    try:
        return validation.marque_valide(slug, c.get("version", "recit"), c.get("blocs"), c.get("par", "auteur"))
    except KeyError:
        raise HTTPException(404, "chapitre pas encore migré : %s" % slug)


def _verrou(f):
    try:
        return f()
    except verrou.Conflit as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/chapitres/{slug}/assertions/{ident}")
async def modifie_assertion(slug: str, ident: str, request: Request):
    """Modifier une assertion : {champs: {texte, statut, note}, motif, empreinte}."""
    c = await request.json()
    return _verrou(lambda: verrou.modifie(slug, ident, c.get("champs") or {}, c.get("motif", ""), c.get("empreinte", "")))


@app.post("/api/chapitres/{slug}/assertions")
async def ajoute_assertion(slug: str, request: Request):
    """Ajouter une assertion : {apres | bloc | plan, texte, statut, porte_par: [blocs du récit], motif,
    empreinte}. Sans « apres », la place se déduit du paragraphe ou du plan (voir verrou._ancre)."""
    c = await request.json()
    return _verrou(lambda: verrou.ajoute(slug, c.get("apres", ""), c.get("texte", ""), c.get("statut", "obligatoire"),
                                         c.get("porte_par") or [], c.get("motif", ""), c.get("empreinte", ""),
                                         bloc=c.get("bloc"), plan=c.get("plan")))


@app.post("/api/chapitres/{slug}/assertions/{ident}/liens")
async def liens_assertion(slug: str, ident: str, request: Request):
    """Liens : {version: recit|essai, bloc, action: attacher|detacher, appui (essai), empreinte}."""
    c = await request.json()
    v, b, act = c.get("version"), c.get("bloc", ""), c.get("action")
    if v == "recit":
        f = verrou.attache_recit if act == "attacher" else verrou.detache_recit
        return _verrou(lambda: f(slug, ident, b))
    if act == "attacher":
        return _verrou(lambda: verrou.attache_essai(slug, ident, b, c.get("appui", "direct"), c.get("empreinte", "")))
    return _verrou(lambda: verrou.detache_essai(slug, ident, b, c.get("empreinte", "")))


@app.get("/api/versions")
def versions():
    """Le livre dans git : changements non versionnés, historique."""
    return edition.versions()


@app.post("/api/versions")
async def enregistre_version(request: Request):
    """Enregistrer une version : un commit des seuls fichiers du livre."""
    c = await request.json()
    return _edition(lambda: edition.enregistre(c.get("message", "")))


@app.get("/api/chapitres/{slug}/{version}")
def chapitre(slug: str, version: str):
    try:
        return livre.texte(slug, version)
    except KeyError:
        raise HTTPException(404, "chapitre ou version inconnu : %s/%s" % (slug, version))


app.mount("/", StaticFiles(directory=FRONT, html=True), name="front")
