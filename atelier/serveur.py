# -*- coding: utf-8 -*-
"""Le serveur de l'atelier.

    poetry run uvicorn atelier.serveur:app --reload --port 8765

L'API vit sous /api ; tout le reste sert le front (front/), sans étape de build.
"""
import sys
import pathlib
import subprocess
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import livre, reecriture, regles, essai, verification, edition, validation, verrou

FRONT = pathlib.Path(__file__).resolve().parent.parent / "front"

app = FastAPI(title="Atelier")

# Un dossier qui n'est pas encore un livre le devient : livre.yaml et structure.yaml vides.
for nom in livre.initialise() + regles.initialise():
    print("atelier : %s créé dans %s" % (nom, livre.LIVRE))
if reecriture.interrompues():
    print("atelier : des demandes en cours ont été interrompues par le redémarrage (marquées en erreur)")


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
    return livre.chapitres()


@app.get("/api/sources")
def sources():
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
            "defaut": {g: reecriture.modele(g) for g in ("verification", "reecriture")},
            "limites": {g: reecriture.limites(g) for g in ("verification", "reecriture")}}


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
        return reecriture.lit(slug, ident)
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
        return reecriture.decide(slug, ident, await request.json())
    except KeyError as e:
        raise HTTPException(404, "inconnu : %s" % e)
    except reecriture.Conflit as e:
        raise HTTPException(409, str(e))


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
    return _edition(lambda: edition.insere_bloc(slug, version, bloc, c.get("texte", ""), c.get("motif", "")))


@app.delete("/api/chapitres/{slug}/{version}/blocs/{bloc}")
async def supprime_bloc(slug: str, version: str, bloc: str, request: Request):
    c = await request.json()
    return _edition(lambda: edition.supprime_bloc(slug, version, bloc, c.get("avant", ""), c.get("motif", "")))


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
