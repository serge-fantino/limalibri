# LimaLibri — instructions de travail

LimaLibri (« la lime du livre ») est un atelier d'écriture de livres : un serveur Python (FastAPI) et un front
web sans build, qui travaillent sur **un dossier de livre**, avec Claude comme aide d'atelier : il propose,
l'auteur retient. Tout le projet est en français : le code (noms, commentaires), l'interface, la documentation,
et les réponses.

## Le principe : l'outil d'un côté, les livres de l'autre

- **Ce dépôt ne contient que l'outil.** Les livres vivent ailleurs, chacun dans son dossier (souvent dans un
  autre dépôt git). L'atelier ne connaît un livre que par `ATELIER_LIVRE`, que `run.sh` lui passe.
- **Ce qui est propre à un livre vit dans son dossier** : `livre.yaml` (titre, versions, réglages de Claude,
  publication), `structure.yaml` (le plan), `regles/<version>.md` (les garde-fous d'écriture), `frise.yaml`,
  `objectifs.yaml`, `kb/` (fiches, sources, demandes de la base), `chapters/<slug>/` (textes, brief, verrou,
  liens, annotations, demandes). Le code reste générique : une idée propre à un livre devient de la
  configuration du livre, pas du code (en cours : des capacités déclarées par le livre).
- **Dépôt public** : jamais de contenu de livre, de chemin personnel, de clé ou de journal dans ce dépôt.
  La configuration de l'utilisateur va dans `CLAUDE.local.md` (ignoré par git).

## Lancer

```bash
./limalibri <dossier du livre> [port] [--no-open]     # ou ./run.sh, ou LIMALIBRI_LIVRE=<dossier>
```

Poetry installe les dépendances au premier lancement (`.venv/` dans le projet). Le serveur tourne avec
`--reload`. Les demandes à Claude passent par le SDK Claude Agent (Claude Code connecté).

## L'architecture

`atelier/` (le paquet Python s'appelle toujours `atelier` : LimaLibri est le projet, l'atelier le lieu) :

| | modules |
|---|---|
| le livre | `livre` (accès, `livre.yaml`, textes rendus, annotations), `plan`, `essai`, `kb`, `sources`, `regles`, `verrou`, `avancement`, `validation`, `versions` (git du livre) |
| les demandes à Claude | `reecriture` (le moteur commun : `_lance`, budgets, déroulé, relance, `tache`), `file` (file d'attente, lots), `filiation`, `serie`, `capacites` (le catalogue), `outils_livre` (outils MCP donnés à Claude : `annoter`) |
| les sortes de demandes | `verification` (v-), `creation` (fiche, f-), `pistes` (p-), `renvois` (l-), `references` (r-), `documents` (o-), `planif` (s-), `redaction` (e-), `naif` (n-), `conversation` (c-), `cadrage` (k-), `relecture` (q-), `storyboard` (b-), `narration` (récit, t-), réécriture (d-) |
| le pilotage | `objectifs`, `suivi`, `travail`, `execution`, `cadrage`, `pilotage` |
| la sortie | `export` (PDF, imprimable), `compagnon` (essai + base), `public` (le site public statique, Cloudflare Pages), `frise` |
| le serveur | `serveur` (routes FastAPI), `evenements` (SSE) |

`front/atelier.js` est un seul fichier (plus de 600 Ko) avec ses helpers (`el`, `api`, `poste`, `tiroir`,
`enModale`, `ouvreDemande`…) ; `front/atelier.css` porte la palette (`--bg`, `--fg`, `--mut`, `--acc`,
`--rule`, `--bar`) en clair et en sombre. Le préfixe d'une demande dit où elle vit : `[fplrosekqbt]-` dans
`kb/demandes`, le reste dans `chapters/<slug>/demandes` (`slugDe` côté front).

Le récit et son storyboard sont **alignés ligne à ligne** : une ligne = un micro-récit et son paragraphe
(`links.yaml` porte le plan et, quand on a touché le plan à la main, le rang). Insérer, déplacer, retirer
vaut pour les deux côtés (`narration.paragraphe`, `livre.forme_plan`).

## Règles de travail

- **Ne commiter que sur demande.** L'utilisateur dit quand ; ne pas le demander à chaque fois.
- **Ne jamais modifier le serveur pendant qu'une demande à Claude tourne.** Le `--reload` redémarre le
  serveur et tue les demandes en cours (elles passent « interrompue » : du temps et de l'argent perdus).
  Avant de toucher à `atelier/*.py` d'un serveur en service, vérifier qu'aucune demande n'est `en_cours`
  dans les livres servis (`kb/demandes/*.json`, `chapters/*/demandes/*.json`), et **que la vérification
  bloque** la copie dans la même commande (`if grep -l … ; then exit 1; fi`), pas seulement qu'elle affiche.
- **Développer et tester sur une copie**, jamais sur le vrai livre : copier le dossier du livre ailleurs,
  et lancer un serveur de test dessus (`ATELIER_LIVRE=<copie>`, autre port). Avant de lancer ce serveur,
  **neutraliser les demandes de la copie** (renommer `kb/demandes`, `kb/plans`, `kb/series`,
  `chapters/*/demandes`) : au démarrage, la file et les plans relancent ce qui attend — de vraies demandes
  à Claude, payantes. Ne jamais importer `atelier.serveur` sans `ATELIER_LIVRE` pointé sur une copie.
- **Vérifier dans un navigateur** (Chrome sans tête et le protocole DevTools) : une capture et l'absence
  d'erreur JS, pas seulement `node --check`. Un `confirm()` bloque Chrome sans tête : tester ces actions
  par l'API.
- **`front/atelier.js` : ne jamais l'écraser à l'aveugle.** Un `open(p, "w").write(open(p).read())` mal placé
  l'a déjà vidé ; vérifier sa taille avant de l'installer.
- **YAML** : dans une liste entre crochets ou accolades, une date avec virgule s'écrit entre guillemets
  (`"13,8 Ga"`), sinon la virgule coupe la valeur. Les fichiers du livre s'écrivent avec `livre.yaml_rt()`
  (ruamel) pour garder commentaires et mise en forme.
- **Une erreur de configuration se dit, elle ne casse pas** : les fichiers édités à la main (`frise.yaml`,
  règles…) rendent des avertissements lisibles plutôt qu'une page vide.
- **Le README** décrit chaque fonction pour l'auteur : le compléter en même temps que le code.
