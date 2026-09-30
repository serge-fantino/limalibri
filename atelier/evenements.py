# -*- coding: utf-8 -*-
"""Le fil des événements : le serveur prévient les pages ouvertes (Server-Sent Events, /api/evenements).

Plutôt que d'interroger le serveur à intervalles réguliers, une page ouvre une connexion que le serveur
garde ouverte, et il y pousse un message quand quelque chose change :

    demande        une demande est créée ou change d'état (en_attente, en_cours, prete, decidee, erreur…)
    progres        une demande qui tourne avance (son déroulé) — au plus une fois par seconde et par demande
    serie          une série avance
    conversation   une conversation avec l'assistant change (au plus une fois par seconde, sauf changement d'état)

Les demandes s'écrivent parfois depuis un fil de travail (une route synchrone) : le message passe alors
par la boucle principale. À l'arrêt du serveur (rechargement compris), les flux ouverts sont fermés, pour
ne pas retenir le redémarrage ; les pages se reconnectent d'elles-mêmes.
"""
import json
import time
import asyncio

_abonnes = set()            # une asyncio.Queue par page connectée
_boucle = None
_derniers = {}              # clé -> (état, instant du dernier message)


def branche(boucle):
    global _boucle
    _boucle = boucle


def _pousse(msg):
    for q in list(_abonnes):
        if q.qsize() < 1000:
            q.put_nowait(msg)


def publie(type_, **data):
    if not _abonnes or _boucle is None:
        return
    msg = "event: %s\ndata: %s\n\n" % (type_, json.dumps(data, ensure_ascii=False))
    try:
        ici = asyncio.get_running_loop() is _boucle
    except RuntimeError:
        ici = False
    if ici:
        _pousse(msg)
    else:
        _boucle.call_soon_threadsafe(_pousse, msg)


def change(cle, etat, evt_etat, evt_progres, **data):
    """Un objet écrit : un changement d'état part tout de suite ; sinon, un « progrès » au plus par seconde."""
    t = time.time()
    av = _derniers.get(cle)
    if av is None or av[0] != etat:
        _derniers[cle] = (etat, t)
        publie(evt_etat, etat=etat, **data)
    elif evt_progres and t - av[1] >= 1:
        _derniers[cle] = (etat, t)
        publie(evt_progres, etat=etat, **data)


def demande(slug, d):
    change("d:" + str(d.get("id")), d.get("etat"), "demande", "progres", id=d.get("id"), slug=slug,
           type=d.get("type"), titre=d.get("titre"), etapes=len(d.get("deroule") or []))


def ferme():
    """À l'arrêt : chaque flux ouvert reçoit sa fin."""
    for q in list(_abonnes):
        q.put_nowait(None)


def sur_les_signaux():
    """Le serveur attend que les connexions se ferment AVANT de lancer son arrêt : un flux ouvert le
    retiendrait (et le rechargement automatique avec). On ferme donc les flux dès le signal d'arrêt,
    puis on rend la main au gestionnaire d'origine (celui d'uvicorn)."""
    import signal
    for sig in (signal.SIGINT, signal.SIGTERM):
        avant = signal.getsignal(sig)

        def gestionnaire(s, frame, avant=avant):
            if _boucle is not None:
                _boucle.call_soon_threadsafe(ferme)
            if callable(avant):
                avant(s, frame)
        signal.signal(sig, gestionnaire)


async def flux(request):
    q = asyncio.Queue()
    _abonnes.add(q)
    try:
        yield "retry: 3000\n\n"
        yield "event: bonjour\ndata: {}\n\n"
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=20)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    break
                yield ": ping\n\n"                     # garde la connexion ouverte
                continue
            if msg is None:
                break
            yield msg
    finally:
        _abonnes.discard(q)
