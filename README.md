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
commité automatiquement.

La barre de la page a deux modes pour le texte : **annoter** (sélectionner un passage) et
**corriger** (cliquer un paragraphe pour le modifier sur place ; `atelier/edition.py`). Une
correction garde le ^id du paragraphe, refuse d'écraser un paragraphe changé ailleurs, et est
notée au journal du chapitre (avant, après, motif). L'essai accepte aussi un paragraphe
nouveau et la suppression (refusée si le paragraphe étaie le verrou) ; le récit garde ses
paragraphes, dont le découpage suit le storyboard. **⎇ versions** fait, à la demande, un
commit git des seuls fichiers du livre — jamais automatiquement.

Le **verrou** se modifie dans le détail d'une assertion (`atelier/verrou.py`) : texte, statut
(obligatoire, supprimable, retirée — avec motif), note ; « ＋ assertion après » crée un
identifiant suffixé (1.8a, 1.8b…) sans renuméroter ; « ＋ assertion » sur une ligne du
storyboard l'ajoute à la fin de la liste du paragraphe (même vide : elle se place après celles
des paragraphes précédents du plan, et le paragraphe cesse d'être un « ajout ») ; les paragraphes du récit qui la portent et
ceux de l'essai qui l'étaient s'attachent et se détachent. L'ancien texte reste dans la note,
chaque changement est au journal (et rend « cadre modifié » les paragraphes qui la portent).

Note technique : les écritures « aller-retour » en YAML (`livre.yaml_rt`) lisent `07e2` ou
`5e56` comme du texte — ce sont des ^id de paragraphe, que YAML 1.2 prendrait pour des nombres —
et les écrivent entre guillemets ; l'atelier ne crée plus d'identifiant de cette forme.

L'**état de validation** (`atelier/validation.py`) compare chaque paragraphe à son empreinte
de dernière validation : **modifié**, **nouveau**, ou **cadre modifié** (son plan du storyboard
ou une assertion qu'il porte a changé depuis, d'après le journal). La référence de départ est
l'état à la migration, relu dans git. Marques dans la marge, compte dans la barre (◐) et le
sommaire ; « considérer comme relu (sans vérification) » — un paragraphe ou une version —
avance la référence sans rien vérifier. C'est
la liste que la future boucle de validation reprendra.

Les **annotations** (récit, et essai en mode texte) : sélectionner un passage fait apparaître
« ✎ annoter » ; type remarque / question / à réécrire ; surlignage par la Custom Highlight
API (aucun nœud ajouté au texte). Elles s'écrivent dans `chapters/<slug>/annotations.jsonl`,
en ajout seul. Une annotation dont la citation ne se retrouve plus est « orpheline » : listée,
jamais perdue, rattachable à son paragraphe.

Les **garde-fous d'écriture** sont dans `regles/<version>.md` du livre ; un livre neuf reçoit
les modèles de `modeles/regles/` (inspirés d'Une Vie). La page du livre les montre et les
modifie ; une annotation peut citer une règle, ou en créer une.

La **réécriture** (récit) part d'une annotation (↻ réécrire), d'un paragraphe (son panneau)
ou d'un plan (détail du plan). Le serveur compile le contexte — la consigne
`skills/reecriture.md`, les garde-fous `regles/<version>.md`, le brief, le plan,
les assertions du verrou et ce qu'en dit l'essai, les paragraphes voisins, les annotations —
et le confie à Claude par l'Agent SDK (`claude-agent-sdk`, le compte Claude Code du poste).
L'option « Claude peut consulter le livre » (cochée par défaut) lui ouvre le dossier du livre
et le dépôt d'héritage en lecture seule (Read, Grep, Glob) : il peut aller lire une fiche ou
un autre chapitre, et cite ce qu'il a consulté. Décochée, il ne voit que le contexte compilé.

La colonne de gauche a deux volets repliables : **Livre** (le sommaire) et **Chapitre** (le
plan de l'essai, ou les plans du récit). Une barre sous l'en-tête règle l'affichage du
chapitre : pour le récit, l'interrupteur storyboard ; pour l'essai, texte · notes ·
bibliographie et la numérotation (aucune, sections, paragraphes — calculée à l'affichage).

Le **plan de l'essai** (identifiants `{#id}` dans les intertitres, posés par la migration) :
glisser-déposer un paragraphe ou une section entière, monter/descendre d'un niveau, renommer,
insérer ou retirer un intertitre (`atelier/essai.py`). Le titre choisi se synchronise entre le
plan et le texte ; un double-clic sur un intertitre du texte le renomme. Aucun identifiant ne
change ; chaque opération est au journal.

Les **fiches** (bouton « Fiches » de l'en-tête) : la base de connaissance du livre,
`kb/fiches/`, lue comme un wiki. `#fiches` est l'index (recherche, filtres : utilisées par un
chapitre, sans lien entrant) ; `#fiches/<slug>[/<section>]` ouvre une fiche : sa confiance en
pastilles (établi, débattu, récent…, détail au survol ou déplié), son texte avec les
`[[liens]]` cliquables, son plan à gauche, et à droite ce qui la relie au livre — les
chapitres qui la listent, les fiches qu'elle cite et qui la citent, les œuvres qu'y exploite
l'essai avec un lien vers chaque note qui les cite. Un lien hors fiches (le cadre poétique de
l'ancien dépôt) est marqué, et s'ouvre en lecture seule dans l'éditeur (`atelier/kb.py`).

La **vérification** (🔎 sur une assertion ou une annotation) confie à Claude, avec WebSearch et
WebFetch en plus de la lecture du livre, la recherche des sources selon les règles du livre
(`skills/verification.md`) : verdict par assertion avec extraits, passage proposé pour l'essai
(emplacement modifiable), œuvres à ajouter, changements du verrou, avis sur le récit.
Retenir écrit l'essai, la bibliographie du chapitre et le verrou (`atelier/verification.py`).
Depuis une annotation, on coche les assertions à vérifier (pré-cochées : celles que la citation
vise), plutôt que tout le paragraphe.

Chaque demande a un **budget** (`claude:` dans livre.yaml — tours, recherches web, pages lues ;
par défaut 25 / 6 / 12 pour une vérification). Le **modèle** se règle au même endroit (celui du livre, et au
besoin par genre de demande) et sur la page du livre, section Claude ; chaque demande peut en
choisir un autre, pour elle seule. Un crochet PreToolUse compte les appels et
refuse l'outil au-delà : Claude rend alors sa réponse avec ce qu'il a. Le budget consommé est
affiché avec les jetons.

Chaque demande garde sa **session** Claude (`session_id`). Une demande arrêtée (tours épuisés,
serveur relancé) se **reprend** : la session est rouverte, Claude y retrouve tout ce qu'il a lu
et rend sa réponse sans nouvelle recherche (« ⏵ reprendre et finir »). Une vérification arrêtée,
ou dont la réponse ne suffit pas, peut aussi **poursuivre la recherche** : la même session
continue, avec tout ce que Claude a déjà lu et conclu, et une rallonge de tours et de
recherches (précision facultative). C'est ainsi qu'on dépasse le plafond de tours par étapes,
en relisant la réponse à chaque étape ; la réponse précédente reste lisible, repliée. La mémoire d'une vérification à
l'autre est le **carnet de recherche** du chapitre (`recherches.jsonl` : verdicts, sources lues
avec extraits, pages inaccessibles), rendu dans le contexte des vérifications suivantes.

Une demande se **relance** sur l'état présent du livre (même cible, consigne revue si besoin,
contexte recompilé) ; l'ancienne, si elle attendait une décision, passe à « remplacée ». La
liste des demandes se filtre (réécritures · recherches ; ouvertes · closes) et se lit pour le
chapitre ou pour tout le livre, classée par chapitre.

Chaque demande enregistre ses **jetons** (entrée, cache créé, cache relu, sortie, et par
modèle), avec un compteur en direct pendant le travail ; la liste donne les totaux.

Chaque **demande** (réécriture ou vérification) enregistre son **déroulé** pendant le travail
(recherches, pages lues, fichiers ouverts, ce que Claude écrit en chemin) : le tiroir le montre
en direct, puis en entier. Le travail continue côté serveur si l'on change de vue ; une demande
qui aboutit est signalée. Un redémarrage du serveur (dont le rechargement automatique quand le
code change) interrompt les demandes en cours : elles sont marquées « interrompues ».

Le **storyboard** se recadre dans la vue Récit (mode storyboard) : double-clic sur un micro-récit,
champs du plan dans son détail. Écrit dans `brief.yaml` (mise en forme gardée), noté au
journal ; la réécriture suivante lit le nouveau cadre. Une re-migration du chapitre ne
remplace plus brief, textes ni liens sans `--ecraser`. Claude rend des propositions structurées ; le tiroir (↻ dans l'en-tête) les
montre mot à mot. « Retenir » réécrit les paragraphes visés (^id conservés), écrit le
journal, résout les annotations traitées ; « aucune ne convient » garde le motif. Claude ne
touche jamais au texte lui-même. Le serveur le
reçoit par la variable `ATELIER_LIVRE`. Les scripts de `migrer/` restent propres à
l'import d'Une Vie depuis son ancien dépôt.

À la main :

```bash
poetry install                                        # une fois
poetry run python3 migrer/structure.py                # ordre.md -> book-atelier/structure.yaml
poetry run python3 migrer/chapitre.py la-mer          # un chapitre -> book-atelier/chapters/la-mer/
poetry run python3 migrer/liens_essai.py la-mer <analyse.json>   # liens verrou -> essai, écarts
poetry run python3 migrer/bibliographie.py la-mer <analyse.json>  # bibliographie du chapitre
poetry run python3 migrer/fiches.py                   # science/*.md -> book-atelier/kb/fiches/
poetry run python3 migrer/liens_fiches.py             # fiches des chapitres et des œuvres
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
