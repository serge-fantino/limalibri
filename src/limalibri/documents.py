# -*- coding: utf-8 -*-
"""Récupérer le texte original d'une œuvre : Claude cherche une version en accès libre, le serveur
la télécharge et la range dans le livre (kb/documents/<cle>/).

Une demande de type « document » vit dans kb/demandes/<id>.json. Claude cherche (WebSearch,
WebFetch) où l'œuvre est lisible librement : PubMed Central, arXiv, bioRxiv, HAL, le dépôt de
l'auteur ou de son institution, l'éditeur quand l'article est en accès libre. Il rend des
candidats — l'adresse directe du fichier, la version (publiée, acceptée, prépublication), la
source, la licence si elle est dite — sans rien télécharger lui-même.

L'auteur choisit un candidat ; le serveur le télécharge (un navigateur ordinaire, une minute,
80 Mo au plus), vérifie que c'est bien un PDF (ou une page), en extrait le texte, et le range.
Les bibliothèques pirates (Sci-Hub, LibGen, Anna's Archive, Z-Library…) sont refusées, par Claude
et par le serveur.
"""
import re
import time
import secrets
import urllib.parse
import urllib.request

from claude_agent_sdk import ClaudeAgentOptions

from . import livre, reecriture, sources

SLUG_KB = "_kb"
INTERDITS = ("sci-hub", "scihub", "libgen", "library.lol", "annas-archive", "z-lib", "zlibrary", "1lib",
             "booksc", "bookfi", "sci-net", "nexus")

SCHEMA = {
    "type": "object",
    "properties": {
        "candidats": {"type": "array", "items": {"type": "object", "properties": {
            "url": {"type": "string"}, "type": {"type": "string", "enum": ["pdf", "html"]},
            "version": {"type": "string", "enum": ["publiee", "acceptee", "preprint", "autre"]},
            "source": {"type": "string"}, "licence": {"type": "string"},
            "confiance": {"type": "string", "enum": ["haute", "moyenne", "basse"]}, "note": {"type": "string"}},
            "required": ["url", "type", "version", "source", "confiance"]}},
        "libre": {"type": "boolean"},
        "resume": {"type": "string"}},
    "required": ["candidats", "libre", "resume"]}

SYSTEME = """Tu cherches, pour une œuvre d'une bibliographie, une version de son texte intégral LISIBLE
LIBREMENT, et l'adresse directe du fichier. Tu ne télécharges rien : tu rends des candidats.

Où chercher, dans cet ordre : PubMed Central (europepmc.org, ncbi.nlm.nih.gov/pmc), arXiv, bioRxiv,
medRxiv, HAL, Zenodo, le dépôt institutionnel de l'auteur ou sa page, l'éditeur quand l'article
est en accès libre (licence CC, « open access »), Internet Archive pour un ouvrage ancien du domaine
public. Pour un PDF, donne l'adresse du fichier lui-même (arXiv : /pdf/…), pas la page qui le
présente. Préfère le PDF de l'éditeur quand l'article est en accès libre (PLOS : le lien
« article/file?id=…&type=printable »). Pour PubMed Central, donne l'adresse de l'article
(…/pmc/articles/PMCxxxxxx/) : le serveur en tire le texte intégral.
Sinon, une page HTML qui porte le texte intégral.

Interdit, sans exception : Sci-Hub, LibGen, Anna's Archive, Z-Library et toute bibliothèque pirate.
Si le texte n'existe que derrière un mur payant, dis-le (libre: false) : l'auteur téléversera son
exemplaire.

Pour chaque candidat : l'adresse, le type (pdf ou html), la version (publiee, acceptee = manuscrit
accepté, preprint, autre), la source, la licence si elle est écrite, ta confiance que ce soit bien
CETTE œuvre (titre, auteurs, année vérifiés sur la page), et une note brève. Trois candidats au
plus, le meilleur d'abord. Mesure : deux ou trois recherches suffisent."""


def cree(corps, lancer=True):
    cle = (corps.get("cle") or "").strip()
    o = sources.lit(cle)
    d = {"id": "o-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "document", "portee": "document", "mode": "recherche",
         "consigne": (corps.get("consigne") or "").strip(),
         "modele_choisi": reecriture._choix_modele(corps),
         "cible": {"cle": cle, "ref": o.get("ref")},
         "etat": "en_attente", "cree": livre._maintenant(), "rang": time.time()}
    d["titre"] = "Texte original de %s" % cle
    reecriture._ecrit(SLUG_KB, d)
    if not lancer:
        return d
    from . import file
    return file.part(SLUG_KB, d, "documents", "demarre", d["id"])


def demarre(ident):
    d = reecriture.lit(SLUG_KB, ident)
    o = sources.lit(d["cible"]["cle"])
    L = ["# L'œuvre : %s" % d["cible"]["cle"], "Référence : %s" % o.get("ref")]
    for k in ("doi", "url"):
        if o.get(k):
            L.append("%s : %s" % (k, o[k]))
    deja = [x.get("source") for x in o.get("documents") or []]
    if deja:
        L.append("Déjà rangés : %s" % ", ".join(str(x) for x in deja))
    if d.get("consigne"):
        L.append("\nPrécision de l'auteur : " + d["consigne"])
    d.update(etat="en_cours", lancee=livre._maintenant(),
             budget={"recherches": 0, "pages": 0, "limites": reecriture.limites("document")},
             contexte={"systeme": SYSTEME, "message": "\n".join(L) + _refs(d)})
    reecriture._ecrit(SLUG_KB, d)
    import asyncio
    t = reecriture.tache(_execute(ident))
    return d


def _refs(d):
    from . import refs
    return refs.annexe(d.get("consigne"))


async def _execute(ident):
    d = reecriture.lit(SLUG_KB, ident)
    outils = ["WebSearch", "WebFetch"]
    lim = d["budget"]["limites"]
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON, thinking=reecriture.PENSEE,
        tools=outils, allowed_tools=outils, max_turns=lim["tours"] + 2, setting_sources=[],
        cwd=str(livre.LIVRE), system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": SCHEMA},
        hooks=reecriture.garde(d, lim), model=reecriture.modele("document", d))
    await reecriture._lance(SLUG_KB, d, options, d["contexte"]["message"], conclut)


def interdit(url):
    h = (urllib.parse.urlparse(url).hostname or "").lower()
    return any(x in h for x in INTERDITS)


def conclut(d, sortie):
    C = [c for c in sortie.get("candidats") or [] if c.get("url", "").startswith("http") and not interdit(c["url"])]
    d.update(etat="prete", resultat={"candidats": C, "libre": sortie.get("libre", bool(C)), "resume": sortie.get("resume", "")})


# ------------------------------------------------------------------ télécharger (le serveur, pas Claude)

def telecharge(url):
    """(octets, nom, type) — comme un navigateur ordinaire, une minute, 80 Mo au plus."""
    if interdit(url):
        raise ValueError("source refusée (bibliothèque pirate)")
    if not url.startswith(("http://", "https://")):
        raise ValueError("une adresse http(s)")
    m = re.match(r"https?://arxiv\.org/abs/(.+)$", url)            # arXiv : la page -> le PDF
    if m:
        url = "https://arxiv.org/pdf/%s" % m.group(1)
    m = re.search(r"(?:ncbi\.nlm\.nih\.gov/pmc|pmc\.ncbi\.nlm\.nih\.gov)/articles/(PMC\d+)", url)
    if m:                                                           # PMC : ses PDF sont gardés contre les robots ; le texte intégral XML ne l'est pas
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/%s/fullTextXML" % m.group(1)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if interdit(r.geturl()):
            raise ValueError("redirigé vers une source refusée")
        donnees = r.read(sources.TAILLE_MAX + 1)
        type_ = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        final = r.geturl()
    if len(donnees) > sources.TAILLE_MAX:
        raise ValueError("document trop gros")
    nom = urllib.parse.unquote(urllib.parse.urlparse(final).path.rsplit("/", 1)[-1]) or "document"
    if donnees.startswith(b"%PDF"):
        nom = re.sub(r"\.pdf$", "", nom, flags=re.I) + ".pdf"
    elif "xml" in type_ and b"<article" in donnees[:5000]:
        nom = re.sub(r"\W+", "-", nom) + ".xml"
    elif "html" in type_:
        texte = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", donnees.decode("utf-8", "replace"))))
        if len(texte) < 4000 or re.search(r"(?i)captcha|preparing to download|enable javascript|access denied|just a moment", texte[:3000]):
            raise ValueError("page trop courte ou page d'attente (%d caractères de texte) — pas le texte intégral" % len(texte))
        nom = re.sub(r"\.(html?|php|aspx?|pdf)$", "", nom, flags=re.I) + ".html"
    else:
        raise ValueError("ni un PDF ni une page (type : %s) — un mur, une page d'accueil ?" % (type_ or "?"))
    return donnees, nom, final


def range_url(cle, url, par="auteur"):
    donnees, nom, final = telecharge(url)
    return sources.ajoute_document(cle, cle + "-" + nom, donnees, final, par=par)


def decide(ident, corps):
    """{action: telecharger, i} ou {action: rejeter}. Télécharger range le candidat dans le livre."""
    d = reecriture.lit(SLUG_KB, ident)
    if d["etat"] != "prete":
        raise reecriture.Conflit("la demande n'attend pas de décision (%s)" % d["etat"])
    if corps.get("action") == "rejeter":
        d.update(etat="decidee", decision={"proposition": None, "date": livre._maintenant()})
        reecriture._ecrit(SLUG_KB, d)
        return d
    i = corps.get("i")
    C = d["resultat"]["candidats"]
    if not isinstance(i, int) or not 0 <= i < len(C):
        raise ValueError("candidat inconnu")
    try:
        range_url(d["cible"]["cle"], C[i]["url"], par="demande %s" % ident)
    except Exception as e:                        # noqa: BLE001 — le candidat échoue, la demande reste ouverte
        C[i]["echec"] = "%s" % e
        reecriture._ecrit(SLUG_KB, d)
        raise ValueError("téléchargement impossible : %s" % e)
    d.update(etat="decidee", decision={"proposition": "telecharge", "i": i, "url": C[i]["url"], "date": livre._maintenant()})
    reecriture._ecrit(SLUG_KB, d)
    return d
