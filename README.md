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

Le **graphe** (`#fiches/graphe`, onglet de l'index) : les fiches en cercles, les chapitres
en carrés reliés à leurs fiches, trois sortes de liens — `[[lien]]`, œuvres partagées (la
bibliographie centrale), même chapitre — à afficher ou non. Les couleurs sont des **clusters
thématiques** : communautés de Louvain (networkx) sur ces liens pondérés, calculées par le
serveur (`/api/fiches-graphe`), nommées par leurs mots propres (titres et sujets) et leurs
fiches les plus liées. Curseurs : résolution (nombre de clusters), poids des œuvres et des
chapitres. Glisser, zoomer, survoler (les voisins), cliquer (le détail), double-cliquer
(ouvrir) ; un clic dans la légende isole un cluster. La disposition est gardée d'une visite
à l'autre.

**Créer une fiche** est une demande à Claude, comme une vérification (`atelier/creation.py`,
`skills/fiche.md`) : une question, les chapitres qu'elle sert, une longueur, un modèle. Elle
part de l'index des fiches (« ◇ nouvelle fiche… »), des fiches d'un chapitre (« il manque une
fiche… »), ou d'une vérification (« en faire une fiche… », avec ses sources). Claude lit
d'abord les fiches voisines — s'il en trouve une qui couvre déjà la question, il le dit
(doublon) —, cherche dans son budget (`claude.fiche` de livre.yaml : 40 tours, 12 recherches,
25 pages par défaut), et rend une fiche : question, confiance par degré, sections sourcées
`[@cle]`, ce que le livre peut en tirer, sources avec extraits, voisines, chapitres. Le tiroir
la montre comme dans le wiki, paragraphes sans source signalés en marge, liens morts et clés
inconnues relevés. « Créer » l'écrit dans `kb/fiches/<slug>.md` (en-tête `origine: claude`,
`etat: brouillon`, sections identifiées) et l'ajoute aux fiches des chapitres cochés ; les
liens inverses sont proposés, pas écrits. Ces demandes vivent dans `kb/demandes/`. Reprendre,
poursuivre la recherche et relancer fonctionnent comme pour une vérification.

La **confiance par paragraphe** d'une fiche : « ◐ lire la confiance par paragraphe » demande à
Claude (sans outils ni recherche, modèle de `claude.fiche`) un degré pour chaque paragraphe —
établi, débattu, récent, hypothèse, projeté, ou raisonnement — et une raison brève, d'après son
texte et la ligne de confiance de la fiche (`atelier/confiance.py`). Le résultat va dans
`kb/fiches/<slug>.confiance.json`, jamais dans la fiche : chaque paragraphe y est désigné par
l'empreinte de son texte, et perd sa marque s'il change. Affiché en marge (couleur, raison au
survol), avec une légende et un interrupteur. Une fiche créée par Claude reçoit d'office le
degré qu'il a donné à chaque section.

La **bibliographie** (`#biblio`, troisième onglet des fiches) rassemble toutes les œuvres : la
base centrale (ancien dépôt), les bibliographies des chapitres, les sources des fiches écrites
ici (`/api/oeuvres`). Recherche et filtres : citées par l'essai, sources des fiches, hors base,
sans DOI, douteuses. Partout — essai, notes, fiches, aperçus —, **un clic sur une citation
ouvre son œuvre** dans la colonne de droite : référence, DOI ou recherche, les notes de l'essai
et les fiches qui la citent, les extraits relevés. Un `[[lien]]` vers une fiche qui n'existe
pas (en rouge) propose de la créer.

**Creuser une fiche** (« ◇ creuser… » sous sa confiance) : Claude lit la fiche, cherche ce
qu'elle effleure sans le traiter, et, pour chaque piste, vérifie dans la base (Grep, index,
voisines, cluster du graphe) si elle est déjà couverte, avant de la classer : **nouvelle**,
**à compléter** (telle fiche, telle section) ou **déjà couverte** (`atelier/pistes.py`,
`skills/pistes.md`). Pas de web : c'est une lecture (budget `claude.pistes`, 20 tours). Le
tiroir montre les pistes par statut, avec la section qui les appelle, la priorité et les
chapitres servis ; on coche, on retouche la question, et chaque piste cochée lance une
création de fiche — qui revérifie le doublon avant d'écrire. Les demandes de pistes d'une
fiche sont listées dans sa colonne de droite.

La **file d'attente** (`atelier/file.py`) : les fiches retenues depuis « creuser » ne partent
pas toutes seules, elles sont **en attente**. On les lance à la main (▶, dans Fiches › En création
ou dans leur tiroir), ou on les retire. L'**enchaînement automatique** est une option
à activer explicitement (case « enchaîner automatiquement », ou `claude.file.auto` dans
livre.yaml ; `simultanees`, 1 par défaut) : les demandes en attente partent alors l'une après
l'autre, la suivante quand la précédente a fini, et la file reprend après un redémarrage. Le
contexte d'une demande est compilé à son lancement : elle voit les fiches créées entre-temps.

L'onglet **En création** (`#fiches/creation`) sépare le travail en cours du stock (onglet
Liste) : demandes de la base en cours, en attente, à décider, en erreur, puis les dernières
closes ; la page et les compteurs (bouton Fiches, onglet) se mettent à jour d'eux-mêmes. Une
demande en erreur se clôt en la relançant (elle passe à « remplacée ») ou en la **classant**
(« abandonnée »). La Liste marque les fiches écrites par Claude (brouillon, relue) et les filtre.

Une fiche écrite par Claude se **marque comme relue** (« ✓ », son en-tête passe de `etat:
brouillon` à `etat: relue`). Les **renvois** (`atelier/renvois.py`) : pour une fiche, les
voisines qu'elle cite et qui ne la citent pas encore ; « ⇄ renvois… » (sur la fiche, ou après
sa création) demande à Claude, sans web, où poser dans chacune une phrase qui renvoie vers
elle — la section, le paragraphe (par ses premiers mots), phrase en fin de paragraphe ou
paragraphe après — et comment la dire. Le tiroir montre le paragraphe visé ; on retouche, on
coche, on insère : le reste de la fiche est intact, et l'insertion va à `kb/journal.jsonl`.

Une création qui part voit aussi les **fiches proposées mais pas encore créées** (rendues, en
attente de décision) : elle ne les double pas, et peut les signaler comme doublon.

**Créer d'office** (option de la file, à cocher explicitement, `claude.file.creer_d_office`) : une
création lancée depuis la file écrit sa fiche dès la réponse de Claude, à l'état `a_confirmer`,
sans toucher aux briefs — elle est visible, citable par les suivantes, et signalée aux autres
demandes comme non relue. On la **confirme** (elle passe en brouillon et rejoint les chapitres
cochés) ou on ne la garde pas (corbeille), depuis sa demande (onglet En création, groupe « À
confirmer ») ou depuis la fiche.

**Supprimer une fiche** (le ménage, « supprimer… » sur la fiche) : l'atelier montre d'abord ce
qui en dépend — les fiches qui la citent, les chapitres qui la listent, les œuvres rattachées.
La fiche va à `kb/corbeille/` (récupérable, avec sa confiance), sort des briefs et des
bibliographies ; les liens qui la visaient restent (morts, en rouge, qui proposent de la
recréer) ou sont défaits, le texte gardé, au choix. Tout va à `kb/journal.jsonl`.

Les vues des fiches ont la **barre de vue** du récit et de l'essai : liste · en création · graphe ·
bibliographie, puis, sur une fiche, ses actions (creuser, renvois, supprimer), et les actions sur la
base : nouvelle fiche, **⎙ PDF** et version **imprimable** (`atelier/export.py`, `/api/kb/pdf`,
`/api/kb/imprimable`). Le document : une couverture (titre, « base de connaissance », synopsis,
date, nombre de fiches), un sommaire par cluster thématique, chaque fiche (confiance, texte, fiches
qui la citent, chapitres, œuvres), la bibliographie des œuvres exploitées en annexe ; tous les liens
(fiche à fiche, vers une section, citation vers son œuvre, sommaire) tiennent dans le document. Le PDF
est imprimé par Chrome sans interface (`ATELIER_CHROME` pour un autre chemin) ; sans Chrome, la
version imprimable s'imprime depuis le navigateur. De quoi faire relire la base par un tiers.

La **bibliographie du livre** vit dans `kb/sources/<cle>.yaml`, une œuvre par fichier
(`atelier/sources.py`) : clé stable, référence, DOI (lu, jamais de mémoire), fiches où l'œuvre est
exploitée, **statut** — importée (venue de la base centrale, jamais vérifiée une à une), à vérifier,
vérifiée, corrigée, introuvable, mal attribuée, doublon —, origine, dernière vérification. Migrée par
`migrer/sources.py` (base centrale de l'ancien dépôt, œuvres citées hors base par l'essai, sources
des fiches). Une fiche créée y fait entrer ses sources, à vérifier. Sur une œuvre : ✎ modifier
(journal), ＋ ajouter à la base (une œuvre hors base), et **🔎 vérifier la référence**
(`atelier/references.py`) : Claude retrouve l'œuvre (éditeur, PubMed, arXiv…), cherche un doublon
parmi les œuvres proches, et contrôle à chaque endroit qui la cite (notes de l'essai, fiches) ce
qu'on lui fait dire ; verdict confirmée, corrigée, introuvable, mal attribuée ou doublon (budget
`claude.reference` : 14 tours, 3 recherches, 4 pages). Retenir écrit l'œuvre (référence, DOI,
statut, la vérification) et la bibliographie des chapitres qui la citent. La vue bibliographie
filtre par statut ; « vérifier la sélection » met en file une vérification par œuvre affichée.

Le **harnais** (« ✓ harnais » dans la barre d'un chapitre, `atelier/harnais.py`) : les portes qu'une
version doit passer avant d'être validée, reprises de l'ancien cycle. Récit : verrou (obligatoires
portées, retirées absentes, paragraphes hors verrou, quotas d'ajouts), séquence déclarée par plan,
budget (mots, paragraphes, phrases longues, tics plafonnés du brief), mots interdits, garde-fous,
filet de relecture (avertissement), répétitions (groupes de quatre mots), formules réservées (R14),
lecture naïve. Essai : appui du verrou (et les écarts, en avertissement), appareil (notes appelées
et définies, citations présentes dans kb/sources et non problématiques, renvois, sections),
garde-fous, répétitions, lecture naïve. Chaque relevé désigne son paragraphe (un clic y mène) et
sa règle. Les **contrôles** des garde-fous vivent dans `regles/<version>.md`, en fin de règle :
un bloc ```controle (libelle, motif, plafond, niveau), lisible et modifiable comme la règle
(`migrer/controles.py` y a reporté les motifs de l'ancien harnais) ; ils sont retirés de ce qu'on
donne à Claude. La **lecture naïve** (`atelier/naif.py`) : Claude lit le texte du chapitre et rien
d'autre, et relève chaque endroit où il doit deviner (référent, ellipse, formule cassée, chiffre,
contradiction, à relire) avec une reformulation minimale ; relevé par relevé, on l'applique (le
paragraphe est corrigé, au journal), on en fait une annotation, ou on l'ignore ; clore enregistre
la lecture sur le texte corrigé (`relectures.json`) — la porte se rouvre dès qu'un mot change.
**Valider** prend l'état présent comme référence ; si une porte bloque, il faut dire pourquoi.

La **page d'une œuvre** (`#biblio/<cle>`, « page ↗ » dans la liste et l'aperçu) rassemble tout :
sa référence et son statut ; ses **documents** (`kb/documents/<cle>/`, le texte original rangé dans le
livre, avec son texte extrait par pdftotext) — téléverser un fichier, le télécharger depuis une
adresse, ou **⤓ texte original** : Claude cherche une version en accès libre (PMC, arXiv, dépôts,
éditeur en libre accès ; jamais une bibliothèque pirate, refusée aussi par le serveur), propose des
candidats, et le serveur télécharge celui qu'on choisit (`atelier/documents.py` ; les PDF de PMC,
gardés contre les robots, sont remplacés par le texte intégral XML d'Europe PMC) ; ses **citations**,
les passages cités mot pour mot, chacune contrôlée contre les documents (trouvée, page N ; absente ;
pas de document) — une vérification retenue et une fiche créée y ajoutent leurs extraits ; ses
**vérifications** (la dernière, l'historique, celles en cours, chacune liée à sa demande) ; où elle
est citée (notes de l'essai, fiches, bibliographies de chapitre) ; les doublons possibles ; son
historique (journal). Une vérification de référence lit d'abord le texte rangé dans le livre.

Le **plan** (bouton « Plan » de l'en-tête, `atelier/plan.py`, `atelier/planif.py`) : le livre
s'écrit de haut en bas. `#plan` — le livre : synopsis court (livre.yaml), idée maîtresse, arc,
synopsis développé (`synopsis.yaml`), et la structure (parties et chapitres, rangés à la main :
monter, descendre, changer de partie, ajouter, supprimer un chapitre sans texte). `#plan/p/<id>`
— une partie : titre, sens, arc, question (synopsis.yaml), ses chapitres. `#plan/c/<slug>` — un
chapitre : titre, période, statut, question, synopsis, fiches (dans son brief.yaml : le chapitre
existe dès son synopsis, avant tout texte). À chaque niveau, **✦ une proposition de Claude**
(lecture du plan et des fiches, sans web) : la structure du livre (idée, arc, parties, chapitres
avec synopsis et fiches, sujets sans fiche), le développement d'une partie, celui d'un chapitre
(synopsis, question, fiches lues, déroulé de l'essai, assertions). On retient élément par élément ;
une partie ou un chapitre existant garde son identifiant. Pour un chapitre, **amorcer l'essai**
écrit le squelette de l'essai (une section par étape du déroulé) et un premier verrou (les
assertions, chacune avec sa fiche) : de quoi commencer la rédaction.

Les **vérifications lisent les fiches d'abord** : la consigne leur donne les fiches du
chapitre et l'index entier, avec la règle d'y chercher avant le web ; la réponse dit quelles
fiches ont servi et à quoi (« fiches consultées »).

Depuis le texte, une pastille « ◇ fiche » ouvre la fiche **en aperçu** dans la colonne de
droite, sans quitter le chapitre (← revient, les `[[liens]]` s'y suivent, « pleine page » va au
wiki). Les pastilles sont posées : sur chaque œuvre de la bibliographie (ses fiches), sur
chaque note (les fiches des œuvres qu'elle cite), dans le détail d'un paragraphe de l'essai
(les fiches de ses notes), et dans le brief (« Fiches du chapitre », modifiables dans
l'en-tête du storyboard ; une fiche inconnue est refusée). Claude reçoit les fiches du
chapitre en premier lieu où chercher.

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
en direct, puis en entier. Les **réflexions** de Claude y sont, résumées (les derniers modèles les
omettent si on ne les demande pas : `thinking={"type": "adaptive", "display": "summarized"}`),
et un extrait de chaque **résultat** d'outil (ce qu'une recherche a trouvé, ce qu'une page
disait ; pour un fichier lu, sa taille). En direct, la dernière réflexion est affichée en tête ;
le déroulé complet se filtre (actions, réflexions, résultats), et chaque ligne se déplie. Le travail continue côté serveur si l'on change de vue ; une demande
qui aboutit est signalée. Un redémarrage du serveur (dont le rechargement automatique quand le
code change) interrompt les demandes en cours : elles sont marquées « interrompues ».

Les **références** désignent un morceau du livre par une adresse courte. Le bouton ⧉ la copie :
barre d'une fiche, d'une œuvre, d'un chapitre, d'une partie du plan ; titre d'une section de fiche
(au survol) ; paragraphe, plan, assertion, annotation, note, garde-fou. Collée dans une consigne,
une question, une annotation, elle donne à Claude **la partie visée** (l'extrait exact) et son
fichier pour lire autour (`atelier/refs.py`, section « Les références données par l'auteur » du
contexte). Sous un champ, l'atelier montre ce que Claude lira (✓) ou ce qui ne se résout pas (✗) ;
dans une annotation ou une consigne affichée, une référence est un lien.

```
@fiche/luca   @fiche/luca#section   @oeuvre/coale2024   @partie/p1   @regle/recit/R11
@chapitre/la-mer   @chapitre/la-mer/essai#section   @chapitre/la-mer/essai^b54b   @chapitre/la-mer/recit^c022
@chapitre/la-mer/plan/A   …/assertion/1.9   …/note/<cle>   …/annotation/<id>
```

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
brew install poppler                                  # une fois, hors Poetry : pdftoppm, pour que Claude lise les PDF par pages
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
