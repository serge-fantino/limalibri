# Atelier — Une vie

L'outillage d'écriture du livre *Une vie* : une application web (serveur Python + front sans
build) qui travaille sur la représentation du livre dans `UneVie/book-atelier/`.

- `docs/cadrage.md` — l'objectif et les pistes d'architecture
- `docs/audit.md` — ce que l'existant fait déjà, ce qui ne colle pas, les décisions proposées
- `docs/essai-structure.md` — proposition : l'essai en texte + métadonnées, et la base de faits

## Stack

- **Serveur** : Python, FastAPI + uvicorn. Toute la chaîne existante (manifeste, cadre, style,
  cycle, appareil) est en Python et doit être réutilisée, pas réécrite.
- **Front** : HTML/CSS/JS en modules ES, servis tels quels. Palette et gestes repris du lecteur
  (`noosphereV2/Books/UneVie-book/outils/lecteur.gabarit.html`).
- **Données** : fichiers texte versionnés dans git (YAML, Markdown, JSONL). Pas de base.

## Lancer

```bash
./run.sh                                              # le livre par défaut : UneVie/book-atelier
./run.sh ../../UneVie/book-atelier                    # un livre, par son dossier (relatif au dossier courant)
./run.sh ~/livres/autre 9000 --no-open                # autre livre, autre port, sans navigateur
```

Un livre est un dossier avec `structure.yaml` (l'ordre des chapitres) et `livre.yaml` (ce
qui le décrit, et un éventuel dépôt d'« héritage » lu en lecture seule). Un dossier qui ne
les a pas les reçoit, vides, au démarrage ; un dossier inexistant est créé après confirmation.

## Ce que l'atelier écrit

La **page du livre** (ouverture de l'appli, ou clic sur le titre) modifie `livre.yaml` sur
place : titre, sous-titre, auteur, langue, synopsis, quatrième, couverture (`media/`). Chaque
champ s'enregistre seul ; les commentaires du fichier sont conservés (ruamel.yaml). Si le
fichier a changé ailleurs depuis l'ouverture de la page, l'écriture est refusée (409) et la
page se recharge : l'atelier n'écrase jamais une modification faite à la main. Rien n'est
commité automatiquement. Le serveur le
reçoit par la variable `ATELIER_LIVRE`. Les scripts de `migrer/` restent propres à
l'import d'Une Vie depuis son ancien dépôt.

À la main :

```bash
poetry install                                        # une fois
poetry run python3 migrer/structure.py                # ordre.md -> book-atelier/structure.yaml
poetry run python3 migrer/chapitre.py la-mer          # un chapitre -> book-atelier/chapters/la-mer/
poetry run python3 migrer/liens_essai.py la-mer <analyse.json>   # liens verrou -> essai, écarts
poetry run python3 migrer/bibliographie.py la-mer <analyse.json>  # bibliographie du chapitre
poetry run uvicorn atelier.serveur:app --reload --port 8765
```

Puis <http://localhost:8765>. Le récit d'un chapitre migré montre ses plans en marge ; un
clic sur un paragraphe ouvre sa fiche : plan, micro-récit, assertions du verrou.

## Les trois lieux

| | rôle | l'atelier… |
|---|---|---|
| `noosphereV2/Books/UneVie-book/` | le dépôt d'origine, ses outils et son cycle | le lit, n'y écrit jamais |
| `UneVie/book-atelier/` | la nouvelle représentation du livre | la lit et l'écrit |
| `tools/atelier/` | l'application | — |
