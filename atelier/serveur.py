# -*- coding: utf-8 -*-
"""Le serveur de l'atelier.

    poetry run uvicorn atelier.serveur:app --reload --port 8765

L'API vit sous /api ; tout le reste sert le front (front/), sans étape de build.
"""
import sys
import pathlib
import subprocess
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from . import livre, reecriture, regles, essai, verification, edition, validation, verrou, kb, creation, confiance, pistes, file, renvois, export, references, sources

FRONT = pathlib.Path(__file__).resolve().parent.parent / "front"

app = FastAPI(title="Atelier")

# Un dossier qui n'est pas encore un livre le devient : livre.yaml et structure.yaml vides.
for nom in livre.initialise() + regles.initialise():
    print("atelier : %s créé dans %s" % (nom, livre.LIVRE))
if reecriture.interrompues():
    print("atelier : des demandes en cours ont été interrompues par le redémarrage (marquées en erreur)")


@app.on_event("startup")
async def _reprend_la_file():
    """Au démarrage : si l'enchaînement est activé, la file repart d'elle-même."""
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
            "defaut": {g: reecriture.modele(g) for g in ("verification", "reecriture", "fiche", "pistes", "reference")},
            "limites": {g: reecriture.limites(g) for g in ("verification", "reecriture", "fiche", "pistes", "reference")}}


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


@app.post("/api/fiches/demandes")
async def cree_fiche(request: Request):
    """Lancer une création de fiche : {question, slug?, chapitres?, consigne?, longueur?, modele?,
    depuis?, sources_initiales?}. Claude cherche en tâche de fond."""
    try:
        return creation.cree(await request.json())
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/oeuvres")
def oeuvres():
    """Toutes les œuvres : base centrale, bibliographies des chapitres, sources des fiches."""
    return kb.oeuvres()


@app.get("/api/oeuvres/statuts")
def statuts_oeuvres():
    return {"statuts": sources.STATUTS, "base": sources.existe()}


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
    """La file d'attente : réglage (auto, simultanées), en cours, en attente."""
    return file.etat()


@app.put("/api/file")
async def file_reglage(request: Request):
    """{auto?, simultanees?} — écrit dans livre.yaml ; activer l'enchaînement lance la suivante."""
    c = await request.json()
    m = livre.meta()
    livre.ecrit_meta({"claude": {"file": {k: c[k] for k in ("auto", "simultanees", "creer_d_office") if k in c}}}, m["_version"])
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


@app.post("/api/fiches/{slug}/relue")
def marque_relue(slug: str):
    """Une fiche écrite par Claude, relue : son état passe de brouillon à relue."""
    try:
        return renvois.marque_relue(slug)
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
        if ident.startswith("f-"):
            return creation.decide(ident, await request.json())
        if ident.startswith("p-"):
            return pistes.decide(ident, await request.json())
        if ident.startswith("l-"):
            return renvois.decide(ident, await request.json())
        if ident.startswith("r-"):
            return references.decide(ident, await request.json())
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
