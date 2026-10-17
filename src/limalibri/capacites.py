# -*- coding: utf-8 -*-
"""Les capacités de LimaLibri : tout ce qu'on peut demander à Claude (ou à l'auteur), en un seul endroit.

Une capacité a un identifiant, ce qu'elle fait, ses paramètres, le genre de demande qu'elle crée (pour
le budget, le modèle et le coût moyen) et ce qu'il faut à la fin (une décision de l'auteur ?). Le
catalogue sert à trois choses :
  · le cadrage d'un objectif (limalibri/cadrage.py) : Claude compose son plan avec ces capacités et rien
    d'autre — c'est ce qui le rend exécutable ;
  · le pilotage (limalibri/pilotage.py) : chaque action d'un plan se lance par lance() ;
  · la page « Capacités » de l'interface : ce que LimaLibri sait faire, ce que ça coûte dans ce livre.

Paramètres : « ! » obligatoire ; chapitre, partie, fiche sont vérifiés contre le livre.
"""
from . import livre

SLUG_KB = "_kb"

# id -> (libellé, ce qu'elle fait, genre (budget, coût), paramètres, fin, par)
#   fin : « decision » — le résultat attend l'auteur ; « pose » — il s'écrit dans le livre ; « lecture » — un rapport
CATALOGUE = {
    "fiche": ("créer une fiche",
              "Claude cherche (web compris, sources lues) et écrit une fiche de la base pour répondre à une question.",
              "fiche", {"question": "texte!", "slug": "texte", "chapitres": "chapitres", "longueur": "courte|moyenne|longue",
                        "consigne": "texte"}, "pose", "claude"),
    "creuser": ("creuser une fiche",
                "Claude lit une fiche et propose des fiches complémentaires (des pistes), sans web ; l'auteur retient les pistes.",
                "pistes", {"fiche": "fiche!", "consigne": "texte"}, "decision", "claude"),
    "renvois": ("relier une fiche",
                "Claude propose les liens d'une fiche avec ses voisines (renvois dans le texte).",
                "renvois", {"fiche": "fiche!", "consigne": "texte"}, "decision", "claude"),
    "reference": ("vérifier une référence",
                  "Claude retrouve une œuvre citée (titre, auteurs, DOI, accès) et la vérifie.",
                  "reference", {"cle": "texte!", "consigne": "texte"}, "decision", "claude"),
    "texte_original": ("lire le texte original",
                       "Claude cherche et lit le texte original d'une œuvre de la bibliographie.",
                       "document", {"cle": "texte!", "consigne": "texte"}, "decision", "claude"),
    "brief": ("développer le brief d'un chapitre",
              "Claude propose le synopsis, la question, les fiches et le déroulé d'un chapitre (sans web).",
              "plan", {"chapitre": "chapitre!", "consigne": "texte"}, "decision", "claude"),
    "plan_partie": ("développer une partie du plan",
                    "Claude propose le sens, l'arc et les chapitres d'une partie.",
                    "plan", {"partie": "partie!", "consigne": "texte"}, "decision", "claude"),
    "plan_livre": ("revoir la structure du livre",
                   "Claude propose une structure du livre : parties, chapitres, ordre — l'auteur retient ce qu'il veut.",
                   "plan", {"consigne": "texte"}, "decision", "claude"),
    "ecrire": ("écrire l'essai d'un chapitre",
               "Claude rédige l'essai d'un chapitre depuis son brief et ses fiches (sans web), posé dans le livre ; un essai "
               "déjà écrit est remplacé (archivé dans l'historique, restaurable) — pour le retravailler, c'est `reviser`.",
               "redaction", {"chapitre": "chapitre!", "consigne": "texte", "longueur": "courte|moyenne|longue"}, "pose", "claude"),
    "reviser": ("réviser l'essai d'un chapitre",
                "Claude retravaille l'essai d'un chapitre selon une consigne (couper, resserrer, intégrer de nouvelles "
                "fiches, faire passer des portes du harnais) et traite ses annotations ouvertes (il dit lesquelles il "
                "règle : elles passent résolues) ; la version d'avant est archivée.",
                "redaction", {"chapitre": "chapitre!", "consigne": "texte!", "mots": "nombre"}, "pose", "claude"),
    "relire": ("relecture critique",
               "Claude relit en entier une partie (ou des chapitres), en connaissant les règles et le reste du livre, et "
               "ANNOTE chaque constat sur son paragraphe : répétition (avec l'autre chapitre), écart à une règle, "
               "incohérence, fait douteux, manque de recherche, clarté, rythme. Fable par défaut. La révision du chapitre "
               "lit ensuite ses annotations et les traite.",
               "relecture", {"partie": "partie", "chapitres": "chapitres", "consigne": "texte"}, "pose", "claude"),
    "storyboard": ("storyboard d'un chapitre du récit",
                   "Claude prépare les plans du récit d'un chapitre depuis son essai (déjà révisé) et son verrou : lieu, temps, "
                   "ambiance, attaque, chute, les assertions que chaque plan met en scène, les micro-récits — selon les règles "
                   "du récit (la voix, le registre). Chaque assertion obligatoire doit être portée. Fable par défaut.",
                   "storyboard", {"chapitre": "chapitre!", "consigne": "texte"}, "pose", "claude"),
    "ecrire_recit": ("écrire le récit d'un chapitre",
                     "Claude écrit le récit d'un chapitre depuis son storyboard — tout le chapitre, un plan, ou un seul "
                     "paragraphe (son rang dans le plan) : un paragraphe par micro-récit, les assertions du plan dans "
                     "l'ordre de sa séquence, les faits pris dans l'essai, selon les règles du récit. Fable par défaut.",
                     "recit", {"chapitre": "chapitre!", "plan": "texte", "rang": "nombre", "consigne": "texte"}, "pose", "claude"),
    "proposer_planches": ("proposer des planches",
                          "Claude lit un chapitre (essai, récit, fiches) et propose des planches — des schémas ou des courbes "
                          "qui font voir ce que le texte déroule : ce que chacune montre, pourquoi, où le texte l'appellerait, "
                          "ses sources et ce qui manque pour la sourcer. L'auteur retient : elles entrent « à dessiner ».",
                          "planche", {"chapitre": "chapitre!", "consigne": "texte"}, "decision", "claude"),
    "dessiner_planche": ("dessiner une planche",
                         "Claude dessine une planche du chapitre en SVG, depuis son brief, en la regardant (il la voit rendue "
                         "dans un navigateur, et corrige chevauchements et débordements) ; tout ce qu'elle affiche est sourcé, "
                         "le reste laissé en blanc. Retenir écrit le dessin (l'ancien archivé) ; la planche reste « en "
                         "construction » jusqu'à ce que l'auteur la retienne.",
                         "planche", {"chapitre": "chapitre!", "planche": "texte!", "consigne": "texte"}, "pose", "claude"),
    "naif": ("lecture naïve",
             "Un lecteur qui n'a lu ni le cadre ni le reste du livre relève chaque endroit où il doit deviner.",
             "naive", {"chapitre": "chapitre!"}, "lecture", "claude"),
    "verifier": ("vérifier des assertions",
                 "Claude vérifie des assertions du verrou d'un chapitre (livre, puis web) et propose des corrections.",
                 "verification", {"chapitre": "chapitre!", "assertions": "liste!", "consigne": "texte"}, "decision", "claude"),
    "auteur": ("une tâche de l'auteur",
               "Ce que seul l'auteur peut faire : décider, relire, passer en relu, trancher une question ; le plan attend qu'il le marque fait.",
               None, {"texte": "texte!", "chapitre": "chapitre"}, "auteur", "auteur"),
}

# Ce que chaque capacité produit ou modifie dans le livre : (à la réponse de Claude, à la décision de l'auteur).
# La demande elle-même (kb/demandes/ ou chapters/<slug>/demandes/) et consommation.jsonl s'écrivent toujours.
ARTEFACTS = {
    "fiche": (["créée d'office : kb/fiches/<slug>.md (à confirmer) et sa confiance par paragraphe",
               "kb/sources/<cle>.yaml : ses sources (à vérifier) et leurs citations"],
              ["kb/fiches/<slug>.md (brouillon) et kb/sources/<cle>.yaml",
               "chapters/<ch>/brief.yaml : la fiche ajoutée aux fiches des chapitres cochés",
               "kb/fiches/<voisine>.md : « Voir aussi » (liens retour, si demandés)",
               "demandes de vérification des sources non lues (filles)",
               "rejeter une fiche créée d'office : à la corbeille, liens retirés"]),
    "creuser": ([], ["une demande de fiche par piste retenue (rien d'écrit dans le livre)"]),
    "renvois": ([], ["kb/fiches/<voisine>.md : une phrase ou un paragraphe de renvoi par lien retenu"]),
    "reference": ([], ["kb/sources/<cle>.yaml : référence, DOI, statut (vérifiée, corrigée, introuvable…), citations",
                       "chapters/<ch>/bibliographie.yaml des chapitres qui la citent"]),
    "texte_original": ([], ["kb/documents/<cle>/ : le texte téléchargé et son texte extrait",
                            "kb/sources/<cle>.yaml : documents, citations recontrôlées"]),
    "brief": ([], ["chapters/<slug>/brief.yaml : synopsis, question, fiches",
                   "amorcer : chapters/<slug>/essai.md (squelette) et verrou.yaml (assertions)"]),
    "plan_partie": ([], ["structure.yaml : la partie, ses chapitres, leur ordre ; synopsis.yaml : sens, arc, question",
                         "nouveaux chapitres : chapters/<slug>/brief.yaml"]),
    "plan_livre": ([], ["synopsis.yaml : idée, arc ; structure.yaml : parties, chapitres, ordre",
                        "nouveaux chapitres : chapters/<slug>/brief.yaml"]),
    "ecrire": (["posé d'office : chapters/<slug>/essai.md, statut brouillon"],
               ["chapters/<slug>/essai.md ; la version d'avant dans chapters/<slug>/historique/"]),
    "reviser": (["posé d'office : chapters/<slug>/essai.md ; l'ancienne version archivée ; les annotations réglées passent résolues"],
                ["chapters/<slug>/essai.md ; la version d'avant dans chapters/<slug>/historique/ (restaurable)"]),
    "relire": (["chapters/<ch>/annotations.jsonl : les constats, posés en annotations (auteur « relecture critique »)"],
               ["classer : toutes ses annotations encore ouvertes passent résolues"]),
    "storyboard": (["posé d'office : chapters/<slug>/brief.yaml — beats (les plans), intent, tenue ; l'ancien dans historique/"],
                   ["chapters/<slug>/brief.yaml — beats, intent, tenue (synopsis, question, fiches gardés) ; l'ancien dans historique/"]),
    "ecrire_recit": (["posé d'office : chapters/<slug>/recit.md (les paragraphes de la portée remplacés, le reste gardé) et "
                      "links.yaml (plan, assertions, ajout) ; l'ancien récit dans historique/"],
                     ["chapters/<slug>/recit.md et links.yaml ; l'ancien récit dans chapters/<slug>/historique/"]),
    "proposer_planches": ([], ["chapters/<slug>/planches.yaml : une entrée « à dessiner » par planche retenue, avec son brief"]),
    "dessiner_planche": (["posé d'office (dans un plan) : chapters/<slug>/planches/<id>.svg ; l'ancien dessin dans planches/historique/"],
                         ["chapters/<slug>/planches/<id>.svg (l'ancien dans planches/historique/) ; planches.yaml : titre, "
                          "légende, « en construction »"]),
    "naif": ([], ["chapters/<slug>/<version>.md : les paragraphes corrigés (relevés appliqués)",
                  "chapters/<slug>/annotations.jsonl : les relevés gardés en annotations",
                  "chapters/<slug>/relectures.json : la lecture enregistrée (la porte « naïf » du harnais)"]),
    "verifier": (["chapters/<slug>/recherches.jsonl : le carnet de recherche"],
                 ["chapters/<slug>/essai.md : paragraphe complété ou ajouté, notes",
                  "chapters/<slug>/verrou.yaml : assertion corrigée, nuancée, vérifiée",
                  "chapters/<slug>/bibliographie.yaml : œuvres nouvelles"]),
    "auteur": ([], ["ce que l'auteur fait lui-même"]),
}

# Ce qu'un cadrage peut proposer de changer au cadre (appliqué si l'auteur l'accepte)
CADRE = {
    "regle": "une règle d'écriture nouvelle, ajoutée à regles/<version>.md (garde-fous) ; toutes les demandes la suivent",
    "regle_revue": "réécrire une règle ou une section existante de regles/<version>.md (cible : son identifiant, R5 ou "
                   "la-voix, interdits-permanents…) : titre (facultatif) et texte nouveau, en entier",
    "critere": "un critère mesuré ajouté à l'objectif (objectifs.yaml), un de ceux que l'atelier sait mesurer",
    "consigne": "une consigne commune (objectifs.yaml), ajoutée à toutes les actions de Claude lancées pour cet objectif",
}


def tout():
    """Le catalogue de LimaLibri, plus les capacités propres au livre (capacites.yaml, capacites_livre.py)."""
    from . import capacites_livre
    C = dict(CATALOGUE)
    for k, c in capacites_livre.toutes().items():
        C[k] = capacites_livre.pour_catalogue(c)
    return C


def artefacts(cap):
    if cap in ARTEFACTS:
        return ARTEFACTS[cap]
    from . import capacites_livre
    c = capacites_livre.toutes().get(cap)
    return capacites_livre.artefacts(c) if c else ([], [])


def _chapitres():
    return {c["slug"] for c in livre.chapitres()}


def _fiches():
    from . import kb
    try:
        return {f["slug"] for f in kb.index()}
    except Exception:                                   # noqa: BLE001
        return set()


def _parties():
    from . import plan
    return {p.get("id") for p in plan.lit()["parties"]}


def valide(cap, params, connus=None):
    """Les problèmes d'une action (liste vide : lançable)."""
    C = tout()
    if cap not in C:
        return ["capacité inconnue : %s" % cap]
    P = params or {}
    K = connus or {"chapitres": _chapitres(), "fiches": _fiches(), "parties": _parties()}
    out = []
    for k, t in C[cap][3].items():
        v = P.get(k)
        if t.endswith("!") and v in (None, "", []):
            out.append("paramètre manquant : %s" % k)
            continue
        if v in (None, "", []):
            continue
        t = t.rstrip("!")
        if t == "chapitre" and v not in K["chapitres"]:
            out.append("chapitre inconnu : %s" % v)
        elif t == "chapitres":
            out += ["chapitre inconnu : %s" % x for x in (v or []) if x not in K["chapitres"]]
        elif t == "fiche" and v not in K["fiches"]:
            out.append("fiche inconnue : %s" % v)
        elif t == "partie" and v not in K["parties"]:
            out.append("partie inconnue : %s" % v)
        elif t == "nombre" and not str(v).isdigit():
            out.append("%s : un nombre" % k)
    if cap == "relire" and not P.get("partie") and not P.get("chapitres"):
        out.append("relire : une partie, ou des chapitres")
    if cap == "fiche" and P.get("slug") and P["slug"] in K["fiches"]:
        out.append("la fiche « %s » existe déjà : la compléter ou la creuser plutôt" % P["slug"])
    return out


def lance(cap, params, consigne_commune="", options=None):
    """Lancer une action ; rend (slug du dossier de la demande, demande). Les auteur ne se lancent pas."""
    P = dict(params or {})
    O = options or {}
    cons = "\n\n".join(x for x in ((P.get("consigne") or "").strip(), (consigne_commune or "").strip()) if x)
    if cap not in CATALOGUE:                            # une capacité propre au livre (sa primitive : plan_de_tete)
        from . import capacites_livre, narration
        capacites_livre.une(cap)
        return SLUG_KB, narration.cree({"chapitre": P["chapitre"], "capacite": cap, "consigne": cons,
                                         "modele": O.get("modele"), "poser": O.get("poser", True)})
    if cap == "fiche":
        from . import creation
        return SLUG_KB, creation.cree({"question": P["question"], "slug": P.get("slug"), "chapitres": P.get("chapitres") or [],
                                       "longueur": P.get("longueur"), "consigne": cons, "modele": O.get("modele")})
    if cap == "creuser":
        from . import pistes
        return SLUG_KB, pistes.cree({"fiche": P["fiche"], "consigne": cons})
    if cap == "renvois":
        from . import renvois
        return SLUG_KB, renvois.cree({"fiche": P["fiche"], "consigne": cons})
    if cap == "reference":
        from . import references
        return SLUG_KB, references.cree({"cle": P["cle"], "consigne": cons})
    if cap == "texte_original":
        from . import documents
        return SLUG_KB, documents.cree({"cle": P["cle"], "consigne": cons})
    if cap in ("brief", "plan_partie", "plan_livre"):
        from . import planif
        niveau = {"brief": "chapitre", "plan_partie": "partie", "plan_livre": "livre"}[cap]
        return SLUG_KB, planif.cree({"niveau": niveau, "chapitre": P.get("chapitre"), "partie": P.get("partie"), "consigne": cons})
    if cap == "ecrire":
        from . import redaction
        # écrire, dans un plan, c'est réécrire de zéro : un essai existant est remplacé (et archivé)
        return SLUG_KB, redaction.cree({"chapitre": P["chapitre"], "consigne": cons, "longueur": P.get("longueur"),
                                         "remplacer": True, "poser": O.get("poser", True), "modele": O.get("modele")})
    if cap == "reviser":
        from . import redaction
        return SLUG_KB, redaction.cree({"chapitre": P["chapitre"], "revision": True, "consigne": cons, "mots": P.get("mots"),
                                         "poser": O.get("poser", True), "modele": O.get("modele")})
    if cap == "storyboard":
        from . import storyboard
        return SLUG_KB, storyboard.cree({"chapitre": P["chapitre"], "consigne": cons, "modele": O.get("modele"),
                                          "poser": O.get("poser", True)})
    if cap == "ecrire_recit":
        from . import narration
        return SLUG_KB, narration.cree({"chapitre": P["chapitre"], "plan": P.get("plan"), "rang": P.get("rang"), "consigne": cons,
                                         "modele": O.get("modele"), "poser": O.get("poser", True)})
    if cap == "relire":
        from . import relecture
        return SLUG_KB, relecture.cree({"partie": P.get("partie"), "chapitres": P.get("chapitres") or [], "consigne": cons,
                                         "version": O.get("version") or "essai", "modele": O.get("modele")})
    if cap in ("proposer_planches", "dessiner_planche"):
        from . import dessin
        return SLUG_KB, dessin.cree({"chapitre": P["chapitre"], "mode": "proposer" if cap == "proposer_planches" else "dessiner",
                                      "planche": P.get("planche"), "consigne": cons, "modele": O.get("modele"),
                                      "poser": O.get("poser", True)})
    if cap == "naif":
        from . import naif
        return P["chapitre"], naif.cree(P["chapitre"], {"version": O.get("version") or "essai"})
    if cap == "verifier":
        from . import verification
        return P["chapitre"], verification.cree(P["chapitre"], {"assertions": P.get("assertions") or [], "consigne": cons})
    raise ValueError("capacité non lançable : %s" % cap)


def cout(cap, moyennes=None):
    """(dollars, secondes) moyens d'une capacité dans ce livre."""
    g = tout().get(cap, (None,) * 6)[2]
    if not g:
        return (0.0, 0)
    from . import execution
    M = moyennes or execution._moyennes()
    return M.get(g, (0.6, 120))


def catalogue():
    from . import execution, capacites_livre
    M = execution._moyennes()
    L = capacites_livre.lit()
    return {"capacites": [{"id": k, "libelle": v[0], "quoi": v[1], "genre": v[2], "params": v[3], "fin": v[4], "par": v[5],
                           "au_resultat": artefacts(k)[0], "a_la_decision": artefacts(k)[1], "livre": k not in CATALOGUE,
                           "cout": round(cout(k, M)[0], 2) if v[2] else None, "duree_s": round(cout(k, M)[1]) if v[2] else None}
                          for k, v in tout().items()],
            "cadre": [{"type": k, "quoi": v} for k, v in CADRE.items()],
            "livre": {"fichier": capacites_livre.FICHIER, "existe": L["existe"], "avertissements": L["avertissements"],
                      "capacites": [{"id": k, "libelle": c["libelle"], "quoi": pour_livre(c), "primitive": c["primitive"],
                                     "plan": c["plan"]["id"], "titre": c["plan"]["titre"], "mots": c["mots"],
                                     "sauf": c.get("sauf") or []}
                                    for k, c in L["capacites"].items()]}}


def pour_livre(c):
    from . import capacites_livre
    return capacites_livre.pour_catalogue(c)[1]


def texte_pour_claude():
    """Le catalogue, tel que Claude le lit dans un cadrage."""
    M = None
    L = []
    for k, v in tout().items():
        c = cout(k, M) if v[2] else None
        L.append("- `%s` — %s. %s Paramètres : %s.%s%s" % (
            k, v[0], v[1], ", ".join("%s (%s)" % (p, t) for p, t in v[3].items()),
            {"decision": " Le résultat attend la décision de l'auteur.", "pose": " Le résultat s'écrit dans le livre.",
             "lecture": " Rend un rapport.", "auteur": ""}[v[4]],
            " Coût moyen ici : ~%.2f $, ~%d min." % (c[0], max(1, round(c[1] / 60))) if c else ""))
        a, b = artefacts(k)
        if a or b:
            L.append("  Écrit : " + " ; ".join(a + b) + ".")
    L.append("\nPropositions de cadre (appliquées si l'auteur les accepte) :")
    L += ["- `%s` : %s" % (k, v) for k, v in CADRE.items()]
    return "\n".join(L)
