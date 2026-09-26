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

from . import livre

FRONT = pathlib.Path(__file__).resolve().parent.parent / "front"

app = FastAPI(title="Atelier")

# Un dossier qui n'est pas encore un livre le devient : livre.yaml et structure.yaml vides.
for nom in livre.initialise():
    print("atelier : %s créé dans %s" % (nom, livre.LIVRE))


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


@app.get("/api/chapitres/{slug}/{version}")
def chapitre(slug: str, version: str):
    try:
        return livre.texte(slug, version)
    except KeyError:
        raise HTTPException(404, "chapitre ou version inconnu : %s/%s" % (slug, version))


app.mount("/", StaticFiles(directory=FRONT, html=True), name="front")
