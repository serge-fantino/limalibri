# -*- coding: utf-8 -*-
"""La filiation des demandes : qui a engendré qui, et jusqu'où.

Une demande lancée par l'auteur est de génération 0. Une demande née d'une autre — les fiches d'un
« creuser » retenues, la vérification des sources qu'une fiche n'a pas pu lire, les actions proposées
par l'assistant — porte son « origine » (l'identifiant de la mère) et sa « generation » (celle de la
mère + 1) ; la mère garde la liste de ses « enfants ».

Deux plafonds, dans livre.yaml (claude.file), pour que l'arbre ne s'étende pas sans fin :
  profondeur   une demande de génération ≥ profondeur n'engendre plus rien (2 par défaut : un
               « creuser » → ses fiches → leurs vérifications de sources, et pas plus loin) ;
  enfants      une demande engendre au plus tant de demandes (4 par défaut).
Ce que l'auteur lance lui-même n'est pas plafonné : il repart de la génération 0.
"""
import contextlib
import contextvars

from . import livre, reecriture

PROFONDEUR, ENFANTS = 2, 4


def reglage():
    f = (livre.meta().get("claude") or {}).get("file") or {}
    def entier(k, defaut):
        try:
            return max(0, int(f.get(k, defaut)))
        except (TypeError, ValueError):
            return defaut
    return {"profondeur": entier("profondeur", PROFONDEUR), "enfants": entier("enfants", ENFANTS)}


def _mere(origine):
    """(slug, demande) de la mère ; (None, None) pour une conversation ou une mère introuvable."""
    from . import file
    try:
        return file._trouve(origine)
    except KeyError:
        return None, None


def _vivante(ident):
    """Un enfant compte s'il n'a été ni remplacé (relancé) ni retiré."""
    _, d = _mere(ident)
    return d is not None and d.get("etat") not in ("remplacee", "retiree")


def place(origine):
    """Ce que la demande `origine` peut encore engendrer : {generation (des enfants), permis, motif}.
    Une conversation de l'assistant est une mère de génération 0, sans compte d'enfants (elle a le sien)."""
    R = reglage()
    _, m = _mere(origine)
    gen = (m.get("generation") or 0) + 1 if m else 1
    deja = sum(1 for e in (m.get("enfants") or []) if _vivante(e)) if m else 0
    if gen > R["profondeur"]:
        return {"generation": gen, "permis": 0,
                "motif": "profondeur atteinte : génération %d, plafond %d (claude.file.profondeur)" % (gen, R["profondeur"])}
    permis = max(0, R["enfants"] - deja) if m else R["enfants"]
    return {"generation": gen, "permis": permis,
            "motif": None if permis else "plafond atteint : %d enfants au plus par demande (claude.file.enfants)" % R["enfants"]}


_courante = contextvars.ContextVar("origine", default=None)


@contextlib.contextmanager
def depuis(origine):
    """Les demandes créées dans ce bloc sont filles d'`origine` (reecriture._ecrit l'inscrit à leur
    première écriture : la filiation est là avant tout départ, et aucune tâche ne l'écrase)."""
    jeton = _courante.set(origine)
    try:
        yield
    finally:
        _courante.reset(jeton)


def inscrit(slug, d):
    """Appelé par reecriture._ecrit : une demande neuve, écrite dans un bloc depuis(), reçoit son origine."""
    o = _courante.get()
    if not o or d.get("id") == o or "origine" in d or (reecriture._dossier(slug) / (d["id"] + ".json")).exists():
        return                                   # seulement à la toute première écriture
    ms, m = _mere(o)
    d["origine"] = o
    d["generation"] = (m.get("generation") or 0) + 1 if m else 1
    if m is not None and d["id"] not in (m.get("enfants") or []):
        m["enfants"] = list(m.get("enfants") or []) + [d["id"]]
        reecriture._ecrit(ms, m)
