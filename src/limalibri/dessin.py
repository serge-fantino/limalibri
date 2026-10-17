# -*- coding: utf-8 -*-
"""Les planches, par Claude : les proposer pour un chapitre, puis les dessiner (une demande g-, dans kb/demandes).

    proposer   Claude lit le chapitre (essai, récit, fiches) et propose des planches : ce que chacune montre, pourquoi,
               où le texte l'appellerait, ses sources, et ce qui manque pour la sourcer. L'auteur retient : chaque
               planche retenue entre dans chapters/<slug>/planches.yaml, « à dessiner », avec ce brief.
    dessiner   Claude dessine une planche en SVG, depuis son brief (ou une consigne), et la REGARDE : l'outil
               « regarder » (mcp__limalibri__regarder) l'affiche dans Chrome et lui rend l'image ; il corrige ce qui
               déborde ou se chevauche avant de rendre. Retenir écrit chapters/<slug>/planches/<id>.svg (l'ancien
               dessin archivé dans planches/historique/), le titre et la légende ; la planche reste « en
               construction » jusqu'à ce que l'auteur la marque retenue.

Tout ce que la planche affiche vient de l'essai ou des fiches ; ce qui n'est pas sourcé est laissé en blanc, et dit.
Un dessin est contrôlé avant d'être retenu (XML lisible, une racine <svg> avec viewBox, ni script, ni lien externe).
"""
import re
import time
import base64
import asyncio
import secrets
import tempfile
import xml.etree.ElementTree as ET

from claude_agent_sdk import ClaudeAgentOptions, tool, create_sdk_mcp_server

from . import livre, reecriture, planches

SLUG_KB = "_kb"
NOM_OUTIL = "limalibri"
OUTIL_REGARDER = "mcp__%s__regarder" % NOM_OUTIL
REGARDS_MAX = 10
GENRES = ("schema", "courbe")

SCHEMA_PROPOSER = {
    "type": "object",
    "properties": {
        "propositions": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"},
            "titre": {"type": "string"},
            "genre": {"type": "string", "enum": list(GENRES)},
            "montre": {"type": "string"},
            "pourquoi": {"type": "string"},
            "ou": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
            "manques": {"type": "string"}},
            "required": ["id", "titre", "genre", "montre", "pourquoi", "sources"]}},
        "remarques": {"type": "string"}},
    "required": ["propositions"]}

SCHEMA_DESSINER = {
    "type": "object",
    "properties": {
        "svg": {"type": "string"},
        "titre": {"type": "string"},
        "legende": {"type": "string"},
        "elements": {"type": "array", "items": {"type": "object", "properties": {
            "quoi": {"type": "string"}, "source": {"type": "string"}}, "required": ["quoi", "source"]}},
        "blancs": {"type": "array", "items": {"type": "string"}},
        "regards": {"type": "integer"},
        "remarques": {"type": "string"}},
    "required": ["svg", "titre", "legende", "elements"]}

SOURCES = """Tout ce qu'une planche affiche — un nom, une valeur, une flèche, une relation — vient de l'essai du chapitre
ou de ses fiches, et tu sais dire d'où. Ce qui n'est pas sourcé n'est pas inventé : la planche le laisse en blanc
(un trait gris en pointillé, un « ? »), et le dit. Pas de web."""

SYSTEME_PROPOSER = """Tu proposes des planches pour un chapitre du livre « {titre} » : des dessins qui accompagnent le
texte (un schéma, une courbe) et font voir d'un coup d'œil ce que la prose déroule. Le livre a deux versions alignées
chapitre pour chapitre : l'essai, qui explique, et le récit, qui raconte ; une planche sert surtout l'essai.

Lis le chapitre (son essai, son récit) et ses fiches. Propose de une à quatre planches, les plus utiles d'abord : celles
qui montrent une structure, un ordre de grandeur, une chaîne, une évolution que le texte peine à faire tenir en tête.
Pas de planche décorative, pas de planche qui redit une phrase.

{sources}

Pour chacune : id (minuscules et tirets, court : « escalier-des-masses »), titre, genre (schema : un dessin de
structure ; courbe : des données sur des axes), montre (ce qu'on voit, précisément : les éléments, leur disposition,
ce qui est mis en avant), pourquoi (ce que le lecteur comprend mieux), ou (l'endroit du texte qui l'appellerait : une
référence @chapitre/<slug>/essai^xxxx ou @chapitre/<slug>/recit^xxxx), sources (les références des passages qui la
sourcent : @fiche/<slug>#<section>, @chapitre/<slug>/essai^xxxx), manques (ce qu'il faudrait sourcer d'abord pour la
dessiner en entier ; vide si rien). Ne reprends pas une planche que le chapitre a déjà. Tout en français."""

SYSTEME_DESSINER = """Tu dessines une planche pour un chapitre du livre « {titre} », en SVG : un dessin qui accompagne le
texte et sera imprimé dans le PDF du livre (A4, en pleine largeur de la colonne de texte), affiché dans l'atelier et sur
le site public (jusque sur un téléphone).

{sources}

## Le format
- Une seule racine <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 H" width="800" height="H"> (H selon le
  dessin, 400 à 700 en général), avec <title> et <desc> (ce que montre la planche, en une phrase).
- Un fond clair plein : <rect width="800" height="H" fill="#fffdf8"/> en premier.
- Les polices : font-family="system-ui, -apple-system, 'Segoe UI', sans-serif" pour les étiquettes ; le titre de la
  planche en "'Iowan Old Style', Charter, Georgia, serif", vers 24. Aucune taille de texte sous 11 : la planche est
  réduite d'environ un cinquième dans le PDF.
- La palette du livre : texte #1f1c17 ; gris #6b6357 ; filets #ddd6c8 ; brun (ce qui est mis en avant) #8a5a2b ;
  bleu #2d5f8a ; orange (ce qui casse, ce qui alerte) #c0622f ; gris clair (ce qui n'est pas sourcé, laissé en blanc)
  #b3a993. Des aplats doux (#e9e1d2, #dce6ef) plutôt que des couleurs vives.
- En haut : le titre, et un sous-titre d'une ligne. En bas, petit (11) : la convention des blancs s'il y en a, et les
  sources (auteurs, année ; la fiche et ses sections).
- Les identifiants internes (marker, pattern, gradient) commencent par l'id de la planche (« {planche}-fleche ») :
  plusieurs planches vivent dans la même page.
- Ni script, ni gestionnaire d'événement (onclick…), ni image ou police externe, ni lien hors du dessin.
- Écris des caractères, pas des entités : « ⁴He », « → », « ≈ », « ~10⁻⁵ ». Échappe seulement & < > dans le texte.

## La méthode
1. Lis le brief, puis l'essai du chapitre et les sections de fiches qui sourcent la planche.
2. Dessine, puis appelle l'outil `regarder` avec ton SVG : il l'affiche dans un navigateur et te rend l'image. Regarde
   vraiment : un texte qui en chevauche un autre, qui déborde de sa boîte ou du cadre, une flèche qui ne vise pas son
   objet, une légende qui coupe un trait, un alignement raté, un texte trop petit. Corrige, et regarde de nouveau.
   Au moins deux regards ; au plus {regards}.
3. Rends le SVG final (exactement celui que tu as regardé en dernier), son titre, une légende d'une ou deux phrases
   (ce que le lecteur doit y voir), la liste des éléments affichés avec leur source (en références :
   @fiche/<slug>#<section>, @chapitre/<slug>/essai^xxxx — la planche est liée aux fiches citées), ce que tu as laissé en blanc
   (blancs), le nombre de regards, et tes remarques (ce que tu n'as pas pu faire, ce qu'il faudrait sourcer).
Tout en français."""


# ------------------------------------------------------------------ le contrôle d'un dessin

def controle(svg):
    """Les défauts bloquants d'un SVG (liste vide : bon), et sa taille (largeur, hauteur)."""
    E = []
    s = (svg or "").strip()
    if not s:
        return ["le SVG est vide"], (800, 600)
    if re.search(r"<\s*script\b", s, re.I):
        E.append("un <script> : interdit")
    if re.search(r"<\s*foreignObject\b", s, re.I):
        E.append("un <foreignObject> : interdit")
    if re.search(r"\son[a-z]+\s*=", s, re.I):
        E.append("un gestionnaire d'événement (on…=) : interdit")
    if re.search(r"""(?:href|src)\s*=\s*["'](?!#|data:image/)""", s, re.I):
        E.append("un lien ou une image hors du dessin (href/src) : interdit — seuls « #id » et data:image/ sont permis")
    if re.search(r"url\(\s*['\"]?(?:https?:|//)", s, re.I):
        E.append("une ressource externe (url(http…)) : interdite")
    try:
        r = ET.fromstring(s)
    except ET.ParseError as e:
        return E + ["XML illisible : %s" % e], (800, 600)
    if not r.tag.endswith("svg"):
        E.append("la racine n'est pas <svg>")
    vb = (r.get("viewBox") or "").replace(",", " ").split()
    try:
        w, h = float(vb[2]), float(vb[3])
    except (IndexError, ValueError):
        E.append("pas de viewBox (« 0 0 800 H »)")
        try:
            w, h = float(r.get("width") or 800), float(r.get("height") or 600)
        except ValueError:
            w, h = 800, 600
    return E, (int(min(max(w, 100), 2000)), int(min(max(h, 100), 2000)))


def remarques_format(svg):
    """Ce qui ne bloque pas mais se voit : les textes trop petits pour l'A4."""
    petits = [float(x) for x in re.findall(r'font-size\s*[=:]\s*"?\s*([0-9.]+)', svg or "") if float(x) < 11]
    return ["%d texte(s) sous la taille 11 (le plus petit : %g) : peu lisible une fois réduit dans le PDF" % (len(petits), min(petits))] if petits else []


async def rendu_png(svg):
    """Le SVG affiché par Chrome sans tête : des octets PNG (ou RuntimeError)."""
    from . import export
    exe = export.chrome()
    if not exe:
        raise RuntimeError("Chrome introuvable : pas de rendu possible")
    _, (w, h) = controle(svg)
    with tempfile.TemporaryDirectory() as tmp:
        src, out = tmp + "/planche.svg", tmp + "/planche.png"
        with open(src, "w", encoding="utf-8") as f:
            f.write(svg)
        p = await asyncio.create_subprocess_exec(
            exe, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars", "--user-data-dir=" + tmp + "/profil",
            "--window-size=%d,%d" % (w, h), "--force-device-scale-factor=1.25", "--screenshot=" + out, "file://" + src,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(p.wait(), timeout=60)
        except asyncio.TimeoutError:
            p.kill()
            raise RuntimeError("le rendu n'a pas fini en une minute")
        try:
            with open(out, "rb") as f:
                return f.read()
        except OSError:
            raise RuntimeError("Chrome n'a pas produit d'image")


def serveur_regarder(d):
    return create_sdk_mcp_server(NOM_OUTIL, tools=[outil_regarder(d)])


def outil_regarder(d):
    """L'outil « regarder » d'une demande : il compte les regards dans la demande (son déroulé s'en sert)."""
    @tool("regarder", "Affiche ton SVG dans un navigateur et te rend l'image, pour que tu voies ton dessin : chevauchements, "
          "débordements, flèches, alignements, lisibilité. svg : le document SVG complet. Refusé, avec la raison, si le SVG "
          "est illisible ou contient ce qui est interdit (script, lien externe…).",
          {"type": "object", "properties": {"svg": {"type": "string"}}, "required": ["svg"]})
    async def regarder(a):
        svg = a.get("svg") or ""
        n = d.setdefault("_regards", 0)
        if n >= REGARDS_MAX:
            return {"content": [{"type": "text", "text": "REFUSÉ : %d regards au plus — rends ton dessin." % REGARDS_MAX}], "is_error": True}
        E, (w, h) = controle(svg)
        if E:
            return {"content": [{"type": "text", "text": "REFUSÉ, à corriger : " + " ; ".join(E)}], "is_error": True}
        try:
            png = await rendu_png(svg)
        except RuntimeError as e:
            return {"content": [{"type": "text", "text": "Pas de rendu : %s" % e}], "is_error": True}
        d["_regards"] = n + 1
        d.setdefault("deroule", []).append({"t": time.strftime("%H:%M:%S"), "type": "outil",
                                             "texte": "regarde son dessin (%d/%d)" % (n + 1, REGARDS_MAX)})
        notes = ["Rendu %d × %d (regard %d sur %d au plus)." % (w, h, n + 1, REGARDS_MAX)] + remarques_format(svg)
        return {"content": [{"type": "image", "data": base64.b64encode(png).decode(), "mimeType": "image/png"},
                            {"type": "text", "text": " ".join(notes)}]}
    return regarder


# ------------------------------------------------------------------ les demandes

def _chapitre(slug):
    c = next((x for x in livre.chapitres_seuls() if x["slug"] == slug), None)
    if not c:
        raise ValueError("chapitre inconnu : %s" % slug)
    if not livre.dossier(slug).is_dir():
        raise ValueError("le chapitre n'est pas dans l'atelier : %s" % slug)
    return c


def cree(corps):
    """{chapitre, mode: proposer | dessiner, planche? (dessiner), consigne?, modele?, poser?}."""
    slug = (corps.get("chapitre") or "").strip()
    c = _chapitre(slug)
    mode = corps.get("mode") or "proposer"
    if mode not in ("proposer", "dessiner"):
        raise ValueError("mode inconnu : %s" % mode)
    if not (livre.dossier(slug) / "essai.md").exists():
        raise ValueError("le chapitre n'a pas d'essai : une planche se source dans l'essai et ses fiches")
    cible = {"chapitre": slug}
    if mode == "dessiner":
        ident = (corps.get("planche") or "").strip()
        p = next((x for x in planches.liste(slug)["planches"] if x["id"] == ident), None)
        if not p:
            raise ValueError("planche inconnue dans ce chapitre : %s (la proposer, ou l'ajouter à planches.yaml)" % ident)
        cible["planche"] = ident
    d = {"id": "g-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
         "type": "planche", "portee": "planche", "mode": mode,
         "consigne": (corps.get("consigne") or "").strip(),
         "modele_choisi": reecriture._choix_modele(corps),
         "poser": bool(corps.get("poser")),
         "cible": cible, "etat": "en_attente", "cree": livre._maintenant(), "rang": time.time()}
    d["titre"] = titre_de(d, c)
    reecriture._ecrit(SLUG_KB, d)
    from . import file
    return file.part(SLUG_KB, d, "dessin", "demarre", d["id"])


def titre_de(d, c=None):
    slug = d["cible"]["chapitre"]
    c = c or next((x for x in livre.chapitres_seuls() if x["slug"] == slug), {"title": slug})
    ch = "%s%s" % ("%s. " % c["numero"] if c.get("numero") else "", c["title"])
    if d.get("mode") == "dessiner":
        return "Dessiner la planche « %s » — %s" % (d["cible"].get("planche"), ch)
    return "Proposer des planches — %s" % ch


def _fiches(slug):
    import yaml
    p = livre.dossier(slug) / "brief.yaml"
    br = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    return [f for f in (br or {}).get("fiches") or [] if (livre.LIVRE / "kb" / "fiches" / (f + ".md")).exists()]


def compile_contexte(d):
    from . import refs
    slug = d["cible"]["chapitre"]
    c = _chapitre(slug)
    titre = livre.meta().get("titre", "")
    L = ["# Le chapitre : %s — %s%s" % (slug, c["title"], " (%s)" % c["periode"] if c.get("periode") else ""),
         "Son essai : chapters/%s/essai.md" % slug]
    if (livre.dossier(slug) / "recit.md").exists():
        L.append("Son récit : chapters/%s/recit.md" % slug)
    F = _fiches(slug)
    if F:
        L += ["Ses fiches : " + ", ".join("kb/fiches/%s.md" % f for f in F)]
    P = planches.liste(slug)["planches"]
    if d["mode"] == "proposer":
        systeme = SYSTEME_PROPOSER.format(titre=titre, sources=SOURCES)
        schema = SCHEMA_PROPOSER
        if P:
            L += ["", "# Les planches qu'il a déjà (n'en propose pas une autre pareille)"] + [
                "- %s — %s (%s)%s" % (p["id"], p["titre"], p["etat"], " : " + p["brief"]["montre"] if (p.get("brief") or {}).get("montre") else "")
                for p in P]
    else:
        p = next(x for x in P if x["id"] == d["cible"]["planche"])
        systeme = SYSTEME_DESSINER.format(titre=titre, sources=SOURCES, planche=p["id"], regards=REGARDS_MAX)
        schema = SCHEMA_DESSINER
        L += ["", "# La planche à dessiner : %s — « %s » (planche %s)" % (p["id"], p["titre"], p["numero"])]
        B = p.get("brief") or {}
        for k, lib in (("genre", "Genre"), ("montre", "Ce qu'elle montre"), ("pourquoi", "Pourquoi"), ("ou", "Où le texte l'appelle"),
                       ("manques", "Ce qui manque pour la sourcer (à laisser en blanc)")):
            if B.get(k):
                L.append("%s : %s" % (lib, B[k]))
        if B.get("sources"):
            L.append("Ses sources : " + " ; ".join(B["sources"]))
        if p.get("fiches"):
            L.append("Ses fiches : " + ", ".join("kb/fiches/%s.md" % f["slug"] for f in p["fiches"]))
        if p["legende"]:
            L.append("Sa légende actuelle : " + p["legende"])
        if p["existe"]:
            L += ["", "# Son dessin actuel (à reprendre selon la consigne : garde ce qui va, corrige le reste)",
                  "Le fichier : %s" % p["fichier"]]
    if d.get("consigne"):
        L += ["", "# La consigne de l'auteur", d["consigne"]]
    L.append(refs.annexe(d.get("consigne")))
    return systeme, "\n".join(L), schema


def demarre(ident):
    d = reecriture.lit(SLUG_KB, ident)
    d.update(etat="en_cours", lancee=livre._maintenant(),
             budget={"recherches": 0, "pages": 0, "limites": reecriture.limites("planche")})
    systeme, message, _ = compile_contexte(d)
    d["contexte"] = {"systeme": systeme, "message": message}
    reecriture._ecrit(SLUG_KB, d)
    return reecriture.tache(_execute(ident))


async def _execute(ident):
    d = reecriture.lit(SLUG_KB, ident)
    outils = ["Read", "Grep", "Glob"]
    lim = d["budget"]["limites"]
    _, _, schema = compile_contexte(d)
    extra = {}
    if d["mode"] == "dessiner":
        extra = {"mcp_servers": {NOM_OUTIL: serveur_regarder(d)}}
    options = ClaudeAgentOptions(
        max_buffer_size=reecriture.TAMPON, thinking=reecriture.PENSEE,
        tools=outils, allowed_tools=outils + ([OUTIL_REGARDER] if extra else []), max_turns=lim["tours"] + 2,
        setting_sources=[], cwd=str(livre.LIVRE), system_prompt=d["contexte"]["systeme"],
        output_format={"type": "json_schema", "schema": schema},
        hooks=reecriture.garde(d, lim), model=reecriture.modele("planche", d), **extra)
    await reecriture._lance(SLUG_KB, d, options, d["contexte"]["message"], conclut)


def schema_de(d):
    return SCHEMA_DESSINER if d.get("mode") == "dessiner" else SCHEMA_PROPOSER


def _id(s):
    s = re.sub(r"[^a-z0-9]+", "-", livre_slug(s)).strip("-")[:60]
    return s or "planche"


def livre_slug(s):
    import unicodedata
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def conclut(d, sortie):
    if d.get("mode") == "dessiner":
        svg = (sortie.get("svg") or "").strip()
        E, taille = controle(svg)
        R = {"svg": svg, "titre": " ".join((sortie.get("titre") or "").split()),
             "legende": " ".join((sortie.get("legende") or "").split()),
             "elements": sortie.get("elements") or [], "blancs": sortie.get("blancs") or [],
             "regards": d.get("_regards", 0), "remarques": sortie.get("remarques") or "",
             "defauts": E, "notes": remarques_format(svg), "taille": list(taille)}
        d.update(etat="prete", resultat=R)
        if d.get("poser") and not E:
            try:
                e = pose_dessin(d)
                d.update(etat="decidee", decision={"proposition": "posee", "d_office": True, "date": livre._maintenant(), **e})
            except Exception as ex:                         # noqa: BLE001 — le dessin reste à décider
                d["erreur_pose"] = "%s" % ex
        return
    props = []
    for p in sortie.get("propositions") or []:
        q = {k: " ".join(str(p.get(k) or "").split()) for k in ("titre", "montre", "pourquoi", "ou", "manques")}
        q["id"] = _id(p.get("id") or q["titre"])
        q["genre"] = p.get("genre") if p.get("genre") in GENRES else "schema"
        q["sources"] = [" ".join(str(x).split()) for x in p.get("sources") or []]
        props.append(q)
    d.update(etat="prete", resultat={"propositions": props, "remarques": sortie.get("remarques") or ""})


def pose_dessin(d):
    slug, ident, R = d["cible"]["chapitre"], d["cible"]["planche"], d["resultat"]
    if R.get("defauts"):
        raise ValueError("le dessin a des défauts : " + " ; ".join(R["defauts"]))
    # les fiches que citent les sources de ses éléments : la planche leur est liée (planches.yaml, fiches)
    A = planches.ancres_citees(e.get("source") for e in R.get("elements") or [])
    fiches = list(dict.fromkeys(f for f, _ in A))
    ancres = ["%s#%s" % (f, s) for f, s in A if s]
    return planches.ecrit_dessin(slug, ident, R["svg"], R.get("titre"), R.get("legende"), d["id"], fiches=fiches, ancres=ancres)


def decide(ident, corps):
    """proposer : {retenir: [indices]} ; dessiner : {action: retenir | rejeter, motif?}."""
    d = reecriture.lit(SLUG_KB, ident)
    if d["etat"] != "prete":
        raise reecriture.Conflit("la demande n'attend pas de décision (%s)" % d["etat"])
    slug = d["cible"]["chapitre"]
    if d.get("mode") == "dessiner":
        if corps.get("action") == "rejeter":
            d.update(etat="decidee", decision={"proposition": None, "motif": (corps.get("motif") or "").strip(), "date": livre._maintenant()})
        else:
            e = pose_dessin(d)
            d.update(etat="decidee", decision={"proposition": "posee", "date": livre._maintenant(), **e})
    else:
        P = d["resultat"]["propositions"]
        choix = [i for i in corps.get("retenir") or [] if isinstance(i, int) and 0 <= i < len(P)]
        ids = planches.ajoute_propositions(slug, [P[i] for i in choix], d["id"])
        d.update(etat="decidee", decision={"proposition": "retenues" if ids else None, "planches": ids, "date": livre._maintenant()})
    reecriture._ecrit(SLUG_KB, d)
    return d
