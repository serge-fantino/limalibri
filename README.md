# LimaLibri

> *… carmen reprehendite quod non*
> *multa dies et multa litura coercuit atque*
> *praesectum deciens non castigavit ad unguem.*
>
> « … blâmez le poème que de longs jours et beaucoup de ratures n'ont pas contenu, et qu'on n'a pas
> repris dix fois, jusqu'à l'ongle. » — Horace, *Art poétique*, v. 292–294

**La lime du livre.** Horace appelle *labor limae*, le travail de la lime, ce qui sépare un texte jeté d'un
texte tenu : le reprendre, le resserrer, le vérifier, jusqu'à ce qu'il tienne. LimaLibri est un atelier
d'écriture de livres, fait pour ce travail-là : un serveur Python et un front web sans build, qui travaillent
sur un dossier de livre — ses versions (un récit, un essai), sa base de connaissance (fiches, sources), son
plan, ses règles — avec Claude comme aide d'atelier : il propose, l'auteur retient.

Né pour deux livres, *Une vie* et *Un monde* ; tout ce qui est propre à un livre vit dans son dossier.

- `docs/cadrage.md` — l'objectif et les pistes d'architecture d'origine
- `docs/audit.md` — l'audit de départ (sur *Une vie*, son ancien dépôt et ses outils)
- `docs/essai-structure.md` — l'essai en texte + métadonnées, et la base de faits

## Stack

- **Serveur** : Python, FastAPI + uvicorn. Toute la chaîne existante (manifeste, cadre, style,
  cycle, appareil) est en Python et doit être réutilisée, pas réécrite.
- **Front** : HTML/CSS/JS en modules ES, servis tels quels. Palette et gestes repris du lecteur
  d'*Une vie*.
- **Données** : fichiers texte versionnés dans git (YAML, Markdown, JSONL). Pas de base.

## Lancer

```bash
./run.sh ~/livres/mon-livre                           # un livre, par son dossier (port 8765)
./run.sh ~/livres/autre 9000 --no-open                # autre livre, autre port, sans navigateur
./limalibri ~/livres/mon-livre                        # la même chose (lien possible dans le PATH)
```

Il faut Python 3.11+, Poetry (installe les dépendances au premier lancement) et, pour les demandes à
Claude, Claude Code connecté (le SDK Claude Agent s'appuie sur lui). Pour publier un site de livre :
Node (`npx wrangler`) et un compte Cloudflare.

Un livre est un dossier avec `structure.yaml` (l'ordre des chapitres) et `livre.yaml` (ce
qui le décrit, et un éventuel dépôt d'« héritage » lu en lecture seule). Un dossier qui ne
les a pas les reçoit, vides, au démarrage ; un dossier inexistant est créé après confirmation.

## Ce que LimaLibri écrit

La **page du livre** (ouverture de l'appli, ou clic sur le titre) modifie `livre.yaml` sur
place : titre, sous-titre, auteur, langue, synopsis, quatrième, couverture (`media/`). Chaque
champ s'enregistre seul ; les commentaires du fichier sont conservés (ruamel.yaml). Si le
fichier a changé ailleurs depuis l'ouverture de la page, l'écriture est refusée (409) et la
page se recharge : LimaLibri n'écrase jamais une modification faite à la main. Rien n'est
commité automatiquement.

La barre de la page a deux modes pour le texte : **annoter** (sélectionner un passage) et
**corriger** (cliquer un paragraphe pour le modifier sur place ; `limalibri/edition.py`). Une
correction garde le ^id du paragraphe, refuse d'écraser un paragraphe changé ailleurs, et est
notée au journal du chapitre (avant, après, motif). L'essai accepte aussi un paragraphe
nouveau et la suppression (refusée si le paragraphe étaie le verrou) ; le récit garde ses
paragraphes, dont le découpage suit le storyboard. **⎇ versions** fait, à la demande, un
commit git des seuls fichiers du livre — jamais automatiquement.

Le **verrou** se modifie dans le détail d'une assertion (`limalibri/verrou.py`) : texte, statut
(obligatoire, supprimable, retirée — avec motif), note ; « ＋ assertion après » crée un
identifiant suffixé (1.8a, 1.8b…) sans renuméroter ; « ＋ assertion » sur une ligne du
storyboard l'ajoute à la fin de la liste du paragraphe (même vide : elle se place après celles
des paragraphes précédents du plan, et le paragraphe cesse d'être un « ajout ») ; les paragraphes du récit qui la portent et
ceux de l'essai qui l'étaient s'attachent et se détachent. L'ancien texte reste dans la note,
chaque changement est au journal (et rend « cadre modifié » les paragraphes qui la portent).

Note technique : les écritures « aller-retour » en YAML (`livre.yaml_rt`) lisent `07e2` ou
`5e56` comme du texte — ce sont des ^id de paragraphe, que YAML 1.2 prendrait pour des nombres —
et les écrivent entre guillemets ; LimaLibri ne crée plus d'identifiant de cette forme.

L'**état de validation** (`limalibri/validation.py`) compare chaque paragraphe à son empreinte
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
insérer ou retirer un intertitre (`limalibri/essai.py`). Le titre choisi se synchronise entre le
plan et le texte ; un double-clic sur un intertitre du texte le renomme. Aucun identifiant ne
change ; chaque opération est au journal.

Les **fiches** (bouton « Fiches » de l'en-tête) : la base de connaissance du livre,
`kb/fiches/`, lue comme un wiki. `#fiches` est l'index (recherche, filtres : utilisées par un
chapitre, sans lien entrant) ; `#fiches/<slug>[/<section>]` ouvre une fiche : sa confiance en
pastilles (établi, débattu, récent…, détail au survol ou déplié), son texte avec les
`[[liens]]` cliquables, son plan à gauche, et à droite ce qui la relie au livre — les
chapitres qui la listent, les fiches qu'elle cite et qui la citent, les œuvres qu'y exploite
l'essai avec un lien vers chaque note qui les cite. Un lien hors fiches (le cadre poétique de
l'ancien dépôt) est marqué, et s'ouvre en lecture seule dans l'éditeur (`limalibri/kb.py`).

Le **graphe** (`#fiches/graphe`, onglet de l'index) : les fiches en cercles, les chapitres
en carrés reliés à leurs fiches, trois sortes de liens — `[[lien]]`, œuvres partagées (la
bibliographie centrale), même chapitre — à afficher ou non. Les couleurs sont des **clusters
thématiques** : communautés de Louvain (networkx) sur ces liens pondérés, calculées par le
serveur (`/api/fiches-graphe`), nommées par leurs mots propres (titres et sujets) et leurs
fiches les plus liées. Curseurs : résolution (nombre de clusters), poids des œuvres et des
chapitres. Glisser, zoomer, survoler (les voisins), cliquer (le détail), double-cliquer
(ouvrir) ; un clic dans la légende isole un cluster. La disposition est gardée d'une visite
à l'autre.

**Créer une fiche** est une demande à Claude, comme une vérification (`limalibri/creation.py`,
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
texte et la ligne de confiance de la fiche (`limalibri/confiance.py`). Le résultat va dans
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
**à compléter** (telle fiche, telle section) ou **déjà couverte** (`limalibri/pistes.py`,
`skills/pistes.md`). Pas de web : c'est une lecture (budget `claude.pistes`, 20 tours). Le
tiroir montre les pistes par statut, avec la section qui les appelle, la priorité et les
chapitres servis ; on coche, on retouche la question, et chaque piste cochée lance une
création de fiche — qui revérifie le doublon avant d'écrire. Les demandes de pistes d'une
fiche sont listées dans sa colonne de droite.

**Créer une fiche** met aussi en file, par défaut, une **vérification de référence** pour chaque source que
Claude n'a pas pu lire (page payante ou bloquée, budget épuisé). Les **liens retour** qu'il propose (depuis les
fiches voisines) s'écrivent à la **validation** de la fiche (« ✓ marquer comme relue », case cochée par
défaut) : une ligne « - [[fiche]] — raison » dans la section « Voir aussi » de chaque voisine, créée au besoin
avant les sources ; le texte de la voisine n'est pas touché. Les paragraphes
sans source [@…] sont signalés en marge ; « 🔎 sourcer les paragraphes signalés » relance la recherche dans
la même session, sur ces paragraphes.

Le **fil des événements** (`limalibri/evenements.py`, `/api/evenements`, Server-Sent Events) : le serveur
prévient les pages ouvertes quand une demande est créée, change d'état ou avance, quand une série avance,
quand une conversation change ; la page redessine ce qui est concerné (le tiroir d'une demande en cours, la
liste des demandes, le bloc des séries, la conversation, les compteurs) — plus de sondage. Le navigateur se
reconnecte seul ; pendant une coupure, un sondage lent prend le relais. Les flux se ferment dès le signal
d'arrêt, pour ne pas retenir le rechargement automatique du serveur.

La **file d'attente** (`limalibri/file.py`) : les fiches retenues depuis « creuser » ne partent
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
brouillon` à `etat: relue`). Les **renvois** (`limalibri/renvois.py`) : pour une fiche, les
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

**Supprimer une fiche** (le ménage, « supprimer… » sur la fiche) : LimaLibri montre d'abord ce
qui en dépend — les fiches qui la citent, les chapitres qui la listent, les œuvres rattachées.
La fiche va à `kb/corbeille/` (récupérable, avec sa confiance), sort des briefs et des
bibliographies ; les liens qui la visaient restent (morts, en rouge, qui proposent de la
recréer) ou sont défaits, le texte gardé, au choix. Tout va à `kb/journal.jsonl`.

Les vues des fiches ont la **barre de vue** du récit et de l'essai : liste · en création · graphe ·
bibliographie, puis, sur une fiche, ses actions (creuser, renvois, supprimer), et les actions sur la
base : nouvelle fiche, **⎙ PDF** et version **imprimable** (`limalibri/export.py`, `/api/kb/pdf`,
`/api/kb/imprimable`). Le document : une couverture (titre, « base de connaissance », synopsis,
date, nombre de fiches), un sommaire par cluster thématique, chaque fiche (confiance, texte, fiches
qui la citent, chapitres, œuvres), la bibliographie des œuvres exploitées en annexe ; tous les liens
(fiche à fiche, vers une section, citation vers son œuvre, sommaire) tiennent dans le document. Le PDF
est imprimé par Chrome sans interface (`LIMALIBRI_CHROME` pour un autre chemin) ; sans Chrome, la
version imprimable s'imprime depuis le navigateur. De quoi faire relire la base par un tiers.

L'**essai** s'exporte de même (**⎙ essai PDF** dans la barre du livre, **⎙ PDF** dans celle de l'essai ;
`/api/essai/pdf`, `/api/essai/imprimable`) : la page de garde du livre (l'idée, le nombre de chapitres
rédigés, de mots, la date), la table des matières — le plan, partie par partie, le statut de chaque
chapitre, et ses sections numérotées quand la numérotation de l'essai est active —, puis chaque partie
(son sens, son arc, sa question, ses chapitres) suivie de ses chapitres. Un chapitre est rendu selon son
avancement : le **texte**, avec son statut (brief, brouillon, en relecture, validé), l'état du harnais
(paragraphes validés) et ses notes ; le **squelette** (les sections « à écrire ») ; ou le **synopsis**
seul, avec sa question. La numérotation (sections, sections + §) suit le réglage du livre. En annexe,
la bibliographie des œuvres citées.

**L'essai et la base de connaissance** (`limalibri/compagnon.py` ; **⎙ essai + base…** dans la barre de
l'essai ; `/api/complet/pdf?portee=…`, `/api/complet/imprimable?portee=…`) : l'essai imprimable, relié à ses
fiches. Chaque chapitre se termine par **« Pour aller plus loin »** : ses fiches (son brief), les fiches qui
partagent ses sources, et une **mini-carte** (le chapitre, ses fiches, leurs voisines). En annexe, **la
carte du livre** — un tableau des clusters thématiques, puis une carte par cluster : les chapitres à
gauche dans l'ordre du livre, les fiches à droite (rangées par le rang moyen de leurs chapitres, pour
croiser le moins de traits), un trait plein chapitre → fiche, un pointillé fiche → fiche —, puis les
fiches par cluster, chacune avec en tête **« Sert : ch. … »** et en pied ses voisines et qui la cite. Une
**bibliographie commune** dit, pour chaque œuvre, les chapitres et les fiches qui la citent. Portée :
`utilisees` (les fiches des briefs ; par défaut) ou `toutes` ; un lien vers une fiche hors de l'édition
devient du texte, marqué. Les cartes sont disposées ici, en mm : traits en SVG, noms en liens HTML posés
dessus — le PDF les garde cliquables (drill-down vers le chapitre ou la fiche). La version imprimable
(HTML) les anime : survoler un nœud allume ses liens et ses voisins. L'essai ne nomme toujours pas ses
fiches (R8) : l'appareil est en encart et en annexe.

Le **récit** s'exporte de la même façon (**⎙ récit PDF** dans la barre du livre, **⎙ PDF** dans celle du
récit ; `/api/recit/pdf`, `/api/recit/imprimable`), avec un niveau d'avancement à lui : entre le synopsis
et le texte, le **storyboard** — les plans du chapitre, chacun avec son cadre (lieu, temps, ambiance) et
ses micro-récits. Pas de numérotation (elle est propre à l'essai) ; la bibliographie n'y paraît que si le
récit cite une œuvre.

La **bibliographie du livre** vit dans `kb/sources/<cle>.yaml`, une œuvre par fichier
(`limalibri/sources.py`) : clé stable, référence, DOI (lu, jamais de mémoire), fiches où l'œuvre est
exploitée, **statut** — importée (venue de la base centrale, jamais vérifiée une à une), à vérifier,
vérifiée, corrigée, introuvable, mal attribuée, doublon —, origine, dernière vérification. Migrée par
`migrer/sources.py` (base centrale de l'ancien dépôt, œuvres citées hors base par l'essai, sources
des fiches). Une fiche créée y fait entrer ses sources, à vérifier. Sur une œuvre : ✎ modifier
(journal), ＋ ajouter à la base (une œuvre hors base), et **🔎 vérifier la référence**
(`limalibri/references.py`) : Claude retrouve l'œuvre (éditeur, PubMed, arXiv…), cherche un doublon
parmi les œuvres proches, et contrôle à chaque endroit qui la cite (notes de l'essai, fiches) ce
qu'on lui fait dire ; verdict confirmée, corrigée, introuvable, mal attribuée ou doublon (budget
`claude.reference` : 14 tours, 3 recherches, 4 pages). Retenir écrit l'œuvre (référence, DOI,
statut, la vérification) et la bibliographie des chapitres qui la citent. La vue bibliographie
filtre par statut ; « vérifier la sélection » met en file une vérification par œuvre affichée.

Le **harnais** (« ✓ harnais » dans la barre d'un chapitre, `limalibri/harnais.py`) : les portes qu'une
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
donne à Claude. La **lecture naïve** (`limalibri/naif.py`) : Claude lit le texte du chapitre et rien
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
candidats, et le serveur télécharge celui qu'on choisit (`limalibri/documents.py` ; les PDF de PMC,
gardés contre les robots, sont remplacés par le texte intégral XML d'Europe PMC) ; ses **citations**,
les passages cités mot pour mot, chacune contrôlée contre les documents (trouvée, page N ; absente ;
pas de document) — une vérification retenue et une fiche créée y ajoutent leurs extraits ; ses
**vérifications** (la dernière, l'historique, celles en cours, chacune liée à sa demande) ; où elle
est citée (notes de l'essai, fiches, bibliographies de chapitre) ; les doublons possibles ; son
historique (journal). Une vérification de référence lit d'abord le texte rangé dans le livre.

Le **plan** (bouton « Plan » de l'en-tête, `limalibri/plan.py`, `limalibri/planif.py`) : le livre
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
Retenir écrit l'essai, la bibliographie du chapitre et le verrou (`limalibri/verification.py`).
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

L'**avancement** de chaque chapitre, par version, s'affiche dans le plan du livre (colonne de gauche,
selon la version lue) et sur les pages du plan : vide, synopsis, brief (squelette ou verrou de l'essai,
storyboard du récit), brouillon, relu, validé (`limalibri/avancement.py`). Un chapitre sans texte dans
la version lue montre ce qu'on sait de lui : synopsis, question, fiches — et de quoi l'écrire.

La **file d'attente** (`limalibri/file.py`) vaut pour toutes les demandes, de la base comme des chapitres :
une seule tourne à la fois (`claude.file.simultanees`, 1 par défaut), les suivantes passent « en attente »
dans l'ordre d'arrivée. Quand une demande finit, la suivante d'une série part toujours ; les autres partent
si l'enchaînement est activé (`claude.file.auto`), sinon elles attendent leur ▶. Le tiroir d'une demande en
attente dit sa place, et « ▶ lancer maintenant » la fait partir en parallèle de ce qui tourne. L'assistant
et la lecture de confiance d'une fiche restent hors de la file.

L'**état réel** : une demande « en cours » dont aucune tâche ne tourne (morte avant d'appeler Claude, ou
perdue) passe en erreur — à l'ouverture et au ⟳ de la liste, à la lecture de la file, et par « ⟳ état
réel » dans son tiroir (2 min de grâce après le départ). Tous les départs passent par
`reecriture.tache()`, qui lance sur la boucle du serveur même depuis une route synchrone ; un départ qui
échoue met la demande en erreur. Sous l'en-tête de chaque demande : son identifiant, « ⧉ réf », « ⧉ fichier ».

La **filiation** (`limalibri/filiation.py`) : une demande née d'une autre porte son `origine` et sa
`generation` ; la mère garde ses `enfants`. Naissent d'une autre : les fiches retenues d'un « creuser »,
la vérification des sources qu'une fiche n'a pas pu lire, les actions lancées depuis l'assistant
(génération 1) ; une relance garde la filiation de la demande remplacée. Deux plafonds
(`claude.file.profondeur`, 2 ; `claude.file.enfants`, 4 ; réglables dans Paramétrage) : au-delà de la
profondeur, une demande n'engendre plus rien ; une demande engendre au plus `enfants` demandes vivantes
(les remplacées et retirées ne comptent pas). « Creuser » propose au plus `enfants` pistes et refuse d'en
retenir davantage ; les sources en surnombre restent à vérifier à la main (`verifications_sautees`). Ce
que l'auteur lance lui-même repart de la génération 0. Le tiroir montre « génération n · issue de … » et
« a engendré … », chaque identifiant ouvrant sa demande.

Les **séries** (`limalibri/serie.py`, `kb/series/`) enchaînent des actions sur plusieurs chapitres :
développer le brief, écrire l'essai, lecture naïve. Depuis le suivi, un groupe d'actions lançable
(« Développer le brief », « Écrire le texte », « Lectures naïves ») a une case par chapitre et « ▶ lancer
pour la sélection… ». Les étapes vont chapitre par chapitre (le brief du premier, son texte, puis le
suivant), chacune partant quand la précédente a fini : chaque chapitre lit le précédent déjà écrit. Le
brief est retenu d'office (fiches — celles déjà choisies restent —, squelette, verrou ; le synopsis et
la question seulement s'ils manquent) ; l'essai est posé d'office ; les relevés de lecture naïve restent
à décider. Une étape sans objet est sautée, une erreur arrête la série (reprendre, ou abandonner) ; un
redémarrage du serveur arrête proprement une série dont l'étape tournait.

Le bouton **⟳** de l'en-tête relit le livre (chapitres et statuts, plan, textes) et redessine la vue
courante à la même place, tiroir ouvert. Il part aussi de lui-même après une décision sur une demande
de la base (poser un essai, retenir un plan, créer une fiche) et quand une demande pose d'office.

**Ce qui manque** à un chapitre (« ◌ manques » dans la barre de l'essai) : les manques signalés par ses
rédactions et révisions, avec de quoi créer ou creuser la fiche, et les phrases du texte et des notes qui
parlent de « la base » ou des « fiches » — le lecteur ne les connaît pas (garde-fou R8 d'Un Monde, que le
harnais contrôle) ; chacune mène à son paragraphe ou à sa note, et « réviser pour retirer ces mentions »
ouvre une révision à la consigne écrite. Les demandes d'écriture et de révision d'un chapitre figurent dans
« Demandes du chapitre ».

**Réviser l'essai** d'un chapitre déjà écrit (« ✎ réviser l'essai… » dans le bandeau ; action `revision` de
l'assistant ; étape « réviser » d'une série) : Claude relit le chapitre en entier et le retravaille selon une
consigne (couper, resserrer, recentrer) et une longueur visée, depuis les fiches, sans web. Il garde l'ancre
^id de chaque paragraphe gardé ou modifié — annotations et appuis du verrou suivent — et dit ce qu'il a
coupé ou fondu, paragraphe par paragraphe. On relit, puis on pose (ou pose d'office). L'**historique**
(« 🕘 historique » dans la barre de l'essai) : chaque pose — écriture, révision, restauration — archive la
version qu'elle remplace dans `chapters/<slug>/historique/` et le note au journal du chapitre, avec la
consigne et les mots avant et après ; on relit une version, on la restaure (la présente est archivée à son
tour). Les corrections à la main restent dans git (⎇ versions).

L'en-tête : **Livre** (onglets présentation — titre, auteur, couverture, synopsis, idée, arc, synopsis
développé, quatrième —, versions et numérotation, garde-fous de chaque version), **Suivi**, **Plan** (la
structure seule : parties et chapitres), Récit, Essai, Fiches, puis Annotations, **Demandes** — la liste (le
tiroir), et deux pages : **Paramétrage des demandes à Claude** (modèle, tours, recherches, pages par sorte de
demande ; la file) et **Consommation** —, ⟳, le thème et l'assistant.

Le **suivi** (en-tête, `#suivi/recit`, `#suivi/essai` ; `limalibri/suivi.py`) : où en est chaque
chapitre, où en est le livre, ce qu'il reste à faire. La note est une progression par étapes pondérées,
lue dans les fichiers — ce qui a été fait, pas ce qui est bon : cadre 10 (synopsis, question),
préparation 15 (essai : fiches et un plan, verrou ou squelette ; récit : storyboard), texte 30 (au
prorata des sections ou des plans), appareil 15 (essai : sources connues, notes complètes, assertions
appuyées ; récit : assertions portées), contrôles 15 (portes bloquantes du harnais), relecture 15
(lecture naïve à jour, annotations traitées, statut relu ou validé). Chaque manque devient une action
qui mène au bon endroit (la vue, et le tiroir : harnais, annotations, demande) ; les actions se
regroupent pour le livre, avec ce que chacune ferait gagner. Le rapport du harnais est gardé en cache
tant que les fichiers du chapitre n'ont pas changé.

Les **objectifs** (en tête du suivi ; `limalibri/objectifs.py`, `objectifs.yaml` à la racine du livre, dans
l'ordre de priorité) : jusqu'où on veut aller. Un objectif a une version, un périmètre (le livre, une
partie, des chapitres) et des critères tenus sur chaque chapitre du périmètre — niveau ≥, score ≥,
manques ouverts ≤, portes du harnais passées, lecture naïve à jour, annotations ouvertes ≤, fiches au
brief ≥, demandes à décider ≤ — et parfois une **intention** en clair, qu'aucune mesure ne capte et que
l'auteur juge (✓ atteinte, pas encore). Facultatifs : une échéance (J-n), un budget en dollars (la
dépense compte les demandes qui servent le périmètre, depuis la création). La progression compte les
couples (chapitre, critère) tenus ; un objectif est atteint quand tous le sont et que son intention est
jugée atteinte. Rien ne s'écrit à la lecture : l'évaluation est recalculée à chaque fois. Déplié, un
objectif montre ses critères (tenus / total) et les chapitres en écart, avec la mesure ; ✎ modifier,
↑ ↓ (priorité), archiver, supprimer. Sur la ligne d'un chapitre, ◎n : l'objectif n n'y est pas tenu.

La **vue d'un objectif** (`#objectif/<id>`, le titre d'un objectif dans le suivi y mène) : sa tête
(progression, chapitres à faire, intention, budget, échéance), son avancement, ses critères, son
intention à juger, puis le **plan d'exécution** (`limalibri/execution.py`), tiré de ses écarts sans Claude,
chapitre par chapitre dans l'ordre du travail : brief, écrire (chapitre sans texte), réviser (portes du
harnais en échec, ou visées par « relu » — la consigne nomme les portes et reprend l'intention), lecture
naïve (après la révision), puis ce qui revient à l'auteur (✋ passer en relu, manques, fiches, annotations,
décisions — « y aller → »). Chaque élément dit pourquoi, son coût estimé (moyennes du journal de
consommation du livre, au moins trois demandes ; sinon une valeur par défaut) et son état : à lancer, en
file, en cours, à décider, dans une série. On coche (tout, rien, les révisions, les lectures naïves, les n
premiers chapitres) ; le pied recalcule nombre, coût, durée et budget restant. **▶ exécuter la sélection** :
une série rattachée à l'objectif (`objectif` dans `kb/series/`), une étape après l'autre, chapitre par
chapitre, chaque révision avec sa consigne ; révisions posées d'office par défaut (sinon, la lecture naïve
d'un chapitre révisé est retirée). Au-delà du budget restant, il faut confirmer. La section **Exécution**
suit les séries de l'objectif (arrêter, reprendre, ouvrir l'étape en cours) ; la vue se redessine quand
une étape ou une demande avance, et la sélection en cours survit au redessin.

**Cadrer un objectif avec Claude** (`limalibri/cadrage.py`, demandes `k-…`, genre `cadrage` : 40 tours, sans
web) : « ✦ cadrer avec Claude… » dans la vue de l'objectif. Claude reçoit l'objectif (titre, critères,
intention, consigne commune, budget), les mesures du suivi par chapitre (niveau, score, portes en échec,
lecture naïve, fiches, manques, à décider), le travail en attente, le plan du livre, l'index des fiches,
les règles d'écriture et le **catalogue des capacités** — puis il lit lui-même le livre (Read, Grep, Glob)
pour se faire son idée. Il rend : sa lecture de l'objectif, ses sous-buts (mesuré, à mesurer, jugé), un
diagnostic par chapitre, des **ajouts au cadre** (une règle d'écriture, un critère, une consigne commune),
un **plan en phases** (avec points d'arrêt), fait d'actions — chacune une capacité, ses paramètres, son
pourquoi, ses dépendances —, les demandes à couper, ses remarques. Le harnais contrôle la réponse :
capacités et paramètres valides (chapitres, fiches, parties existants ; pas de fiche en double),
dépendances connues et sans cycle, coût estimé, et **couverture** (les écarts mesurés qu'aucune action ne
traite). La proposition s'affiche dans la vue de l'objectif : tout se coche ; « Retenir » applique le
cadre coché (une règle déjà présente n'est pas doublée), retire les demandes à couper, et pose le plan.

**Piloter le plan** (`limalibri/pilotage.py`, `kb/plans/<objectif>.json` ; l'ancien est archivé) : ▶ démarrer,
⏸ pause (ce qui tourne finit, rien de neuf ne part), ▶ continuer après un point d'arrêt, arrêter. Une action
part quand ses dépendances sont faites (`capacites.lance`), marquée du plan : ses demandes passent la file
d'elles-mêmes, comme celles d'une série ; les fiches sont créées d'office (à confirmer) et les révisions
posées d'office, pour que la suite s'en serve (options au moment de retenir). Une action est faite quand
sa demande a rendu son résultat (prête, à confirmer, décidée) ; ce qui attend une décision se décide au
point d'arrêt. Une action en erreur bloque le plan (relancer, sauter) ; une tâche de l'auteur attend son
« ✓ fait ». Le pilotage avance à la fin de chaque demande, au démarrage du serveur et à chaque geste.

Les **lots** (`limalibri/file.py`) : une phase d'un plan, une série. Leurs demandes partent d'elles-mêmes tant
que le lot est actif (plan en cours, série en cours) — un plan en pause retient ses demandes en file, un
plan arrêté (ou remplacé) les retire, et leurs actions passent « sautées ». Un lot s'enchaîne d'un bloc : la
place libérée va d'abord au lot de la dernière demande partie. Au démarrage, plans et séries avancent avant
la file (un plan interrompu est bloqué avant que sa suivante puisse partir). La liste des demandes, en vue
« en cours + en attente », groupe la file par lot (titre de la phase, lien vers l'objectif, « attend » si
inactif) ; chaque demande lancée par un plan porte ◫ son action et sa phase, et son tiroir un lien « plan de
l'objectif → ». Dans la vue de l'objectif, une action lancée montre l'état réel de sa demande (en file n° k,
en cours, à décider).

La **relecture critique** (`limalibri/relecture.py`, demandes `q-…`, capacité `relire` ; « ✦ relecture critique… »
dans la barre du suivi) : Claude relit EN ENTIER une partie (ou des chapitres), en connaissant les règles de
la version, le plan du livre et l'index des fiches, et va voir ailleurs (Grep, lecture) ce que le livre dit
déjà. Il **annote lui-même** chaque constat avec l'outil `annoter` (`limalibri/outils_livre.py`, un serveur MCP
en mémoire : `mcp__limalibri__annoter`) — sur le paragraphe (^id), avec un extrait exact ; l'outil refuse une
ancre ou un extrait introuvables, Claude corrige. Sortes : répétition (avec l'autre chapitre et son ^id),
écart à une règle (son numéro), incohérence, fait à vérifier, manque de recherche, clarté, rythme ; gravité
majeur / mineur. L'annotation garde son `origine` (la demande, la sorte, la gravité). Fable 5.1 par défaut
(sauf `claude.relecture.modele`). Le tiroir montre le bilan, la synthèse, les annotations par chapitre ;
« classer » les marque toutes résolues. L'**assistant** a le même outil, mais ne l'utilise qu'à la demande.
La **révision** d'un chapitre reçoit ses annotations ouvertes, les traite, et donne les identifiants de
celles qu'elle règle : à la pose, elles passent résolues.

Le **storyboard d'un chapitre** (`limalibri/storyboard.py`, demandes `b-…`, capacité `storyboard` ; « ✦
storyboard… » dans la barre du récit) : Claude prépare les plans du récit depuis l'**essai** (révisé) et le
**verrou** du chapitre, selon les règles du récit (la voix, le registre), en enchaînant sur le storyboard du
chapitre précédent. Chaque plan : lieu, temps, ambiance, attaque, chute, les **assertions** qu'il met en
scène (le lien avec l'essai), la séquence, les micro-récits, les ajouts permis. Le contrôle dit si chaque
assertion obligatoire est portée et si les identifiants existent. Retenir (ou poser d'office, depuis un
plan) écrit `brief.yaml` — `beats`, `intent`, `tenue` ; synopsis, question et fiches gardés ; l'ancien
storyboard dans `historique/`. Fable 5.1 par défaut.

Le **récit d'un chapitre** s'écrit depuis son storyboard (`limalibri/narration.py`, demandes `t-…`, capacité
`ecrire_recit`, action de série `recit`). La portée est soit le chapitre entier, soit un plan, soit un seul
paragraphe : son rang dans le plan, c'est-à-dire le micro-récit qu'il réalise.

Dans la vue storyboard :
- « ✦ écrire tout le récit » se trouve en tête ;
- « ✦ écrire ce plan » ou « ✦ réécrire ce plan… » se trouve à côté de chaque plan ;
- « ✦ écrire ce paragraphe » apparaît sur chaque rang vide.

On écrit dans l'ordre qu'on veut : un paragraphe porte son rang dans `links.yaml` (« rang », c'est-à-dire
le micro-récit qu'il réalise), et les rangs vides restent ouverts. Sans rang écrit, la place d'un
paragraphe est sa position dans le plan, comme pour un récit écrit d'un trait.

Claude reçoit :
- les règles et l'intention du récit ;
- le storyboard entier ;
- le texte des assertions ;
- le récit déjà écrit autour de la portée ;
- la fin du récit du chapitre précédent.

Il lit l'essai pour les faits. Pour chaque paragraphe, il rend les assertions portées, ou « ajout ».

Retenir réécrit `recit.md` : les paragraphes de la portée sont remplacés, et les autres gardent leurs ancres. `links.yaml` suit (plan, assertions, ajout), et l'ancien récit va dans `historique/`.

Le cadrage peut aussi proposer de **réviser une règle** (`regle_revue` : la cible — `R5`, `la-voix`… —, son
titre et son texte nouveaux), et un plan peut **dépendre d'une action du plan d'un autre objectif**
(`o-xxxx:a8`) : le cadrage reçoit les plans des autres objectifs ; le pilotage attend que l'action visée
soit faite ; chaque geste fait avancer tous les plans.

Les **capacités** (`limalibri/capacites.py`, page `#capacites` sous Demandes) : le catalogue unique de ce
que LimaLibri sait lancer — créer une fiche, creuser, relier, vérifier une référence, lire un texte
original, développer un brief, une partie, revoir la structure du livre, écrire, réviser, lecture naïve,
vérifier des assertions, une tâche de l'auteur — avec ses paramètres, ce qu'il faut à la fin (décision,
pose, rapport), ce qu'elle **produit ou modifie** dans le livre — à la réponse de Claude et à la décision de
l'auteur (fichiers et champs : `kb/fiches/<slug>.md`, `chapters/<slug>/brief.yaml`, `essai.md` et son
historique, `verrou.yaml`, `kb/sources/<cle>.yaml`, `structure.yaml`…) — et son coût moyen dans ce livre ;
et les ajouts au cadre qu'un cadrage peut proposer. Le cadrage reçoit aussi ces artefacts.

**Les demandes, en pleine page** (`#demandes`) : la même liste que le tiroir (filtres, file, commande de
l'enchaînement), qui se redessine quand une demande change ; une demande s'ouvre dans le tiroir. Une seule
navigation pour les demandes — liste · paramétrage · consommation · capacités — dans la barre des pages
Demandes et en tête de la liste du tiroir ; le bouton « Demandes » de l'en-tête ouvre le tiroir.

L'**avancement** d'un objectif : chaque fois que sa mesure change (progression, critères tenus,
atteinte), un point s'ajoute à `objectifs-suivi.jsonl` — seule écriture faite à la lecture du suivi. La
carte montre la courbe, la mesure du premier point et aujourd'hui, et ce qui a bougé critère par critère.

Les **révisions** (vue Livre › **révisions**, `#livre/revisions`) : l'état du dépôt (préfixe des tags, fichiers
du livre non commités), « 🏷 marquer la version actuelle » (nom, une ligne), les versions marquées — leur
date, leur message, les objectifs qui en partent, « ce qui a changé depuis » (fichiers, mots de l'essai par
chapitre) —, et les derniers commits qui touchent le livre (`GET /api/versions/historique`). L'onglet voisin
« récit · essai » (anciennement « versions ») règle les versions du texte et la numérotation de l'essai.

**Marquer une version** (`limalibri/versions.py`, seulement si le livre est dans un dépôt git) : un commit du
seul dossier du livre (ce qui est déjà indexé ailleurs dans le dépôt n'est pas emporté), puis un tag
annoté local — jamais poussé. Livre dans son propre dépôt : `v1`, `v2`… ; dans un dépôt plus grand : le
nom du livre en préfixe (`unmonde/v1`). À la création d'un objectif, « 🏷 marquer d'abord la version
actuelle » (coché par défaut) en fait le **départ** de l'objectif ; sinon, depuis la carte : marquer
maintenant, ou partir d'une version déjà marquée. « Ce qui a changé depuis » : fichiers du livre
modifiés, ajoutés, supprimés (commités ou non), et les mots du texte, chapitre par chapitre. API :
`GET/POST /api/versions`, `GET /api/versions/depuis?tag=…`, `POST /api/objectifs/{id}/depart`.

Le **travail** de chaque chapitre (`limalibri/travail.py`), sur sa ligne du suivi : ⏳ demandes en file ou
en cours, ✋ résultats à décider, ◌ manques de la dernière rédaction — un clic déplie la liste (chaque
demande s'ouvre). Une demande de la base compte pour les chapitres qu'elle sert (rédaction, plan : le
chapitre visé ; fiche : les chapitres de la question ou de la réponse ; creuser : ceux des pistes, sinon
ceux qui utilisent la fiche) ; les autres vont dans « sans chapitre », en fin de liste.

**Écrire l'essai** (✎, `limalibri/redaction.py`) : Claude rédige l'essai d'un chapitre depuis son brief
(synopsis, question, fiches ; squelette et verrou s'il est amorcé), en lisant ses fiches et les chapitres
déjà écrits — sans web. Il suit le squelette, cite en [@cle] les seules sources lues, renvoie en
[chap:slug], met ses notes en [^slug-…] (préfixées au besoin). Ce que les fiches n'établissent pas, il
ne l'écrit pas : il le rend en « manques » (une fiche à créer, une fiche à creuser), qu'on lance d'un
clic. « Poser » écrit l'essai (ancres, intertitres identifiés, squelette remplacé, chapitre en
brouillon) ; un essai déjà rédigé n'est jamais remplacé sans le dire. Depuis le plan du livre ou d'une
partie, **une série** : une demande par chapitre qui n'a qu'un synopsis ou un brief, dans l'ordre du plan,
chacune partant quand la précédente a fini ; « poser d'office » pour que chaque chapitre lise le précédent.
Budget et modèle : `claude.redaction` (40 tours ; un chapitre prend quelques minutes avec Opus).

Les **références** désignent un morceau du livre par une adresse courte. Le bouton ⧉ la copie :
barre d'une fiche, d'une œuvre, d'un chapitre, d'une partie du plan ; titre d'une section de fiche
(au survol) ; paragraphe, plan, assertion, annotation, note, garde-fou. Collée dans une consigne,
une question, une annotation, elle donne à Claude **la partie visée** (l'extrait exact) et son
fichier pour lire autour (`limalibri/refs.py`, section « Les références données par l'auteur » du
contexte). Sous un champ, LimaLibri montre ce que Claude lira (✓) ou ce qui ne se résout pas (✗) ;
dans une annotation ou une consigne affichée, une référence est un lien.

```
@fiche/luca   @fiche/luca#section   @oeuvre/coale2024   @partie/p1   @regle/recit/R11
@chapitre/la-mer   @chapitre/la-mer/essai#section   @chapitre/la-mer/essai^b54b   @chapitre/la-mer/recit^c022
@chapitre/la-mer/plan/A   …/assertion/1.9   …/note/<cle>   …/annotation/<id>
```

**✦ Claude** (en-tête, dans toutes les vues) : **parler du livre**. Claude lit tout — textes, cadres,
verrous, annotations, fiches, bibliographie, garde-fous, l'héritage, le web avec mesure — et répond,
en désignant ce dont il parle par des références cliquables. Il n'écrit rien. Quand la réponse
appelle du travail, il le **propose** : une fiche, creuser une fiche, une vérification, une
réécriture, une lecture naïve, un plan (trois au plus) ; l'auteur relit la consigne et **lance** —
l'action devient une demande ordinaire, qu'on ouvre depuis la conversation. La case « joindre ici »
donne à Claude la référence de ce que l'auteur regarde (le paragraphe choisi, la fiche, l'œuvre…).
Une conversation se poursuit dans la même session : Claude garde ce qu'il a lu. Elles vivent dans
`kb/conversations/<id>.json` (`limalibri/conversation.py`) ; budget et modèle dans les réglages Claude
du livre (`claude.conversation` : 30 tours, 4 recherches, 6 pages par question).

La **consommation** de Claude est journalisée dans `consommation.jsonl`, à la racine du livre : une
ligne JSON par exécution (demande, reprise, « chercher encore », tour de conversation, lecture de
confiance), écrite en fin d'exécution et jamais réécrite, avec ses propres chiffres — date et durée,
type, phase, demande et chapitre, modèle choisi et modèle réel, issue, tours, recherches et pages web,
jetons (neufs, cache créé, cache relu, sortie), coût au tarif API, détail par modèle, session
(`limalibri/consommation.py`). L'onglet « consommation » de la page du livre le résume sur une période
(par jour, type, modèle, chapitre, phase) ; le fichier se lit aussi tel quel (duckdb, pandas).
`migrer/consommation.py` reconstitue le travail d'avant le journal depuis les demandes (lignes
« reconstitue », les reprises y sont cumulées) ; le rejouer ne crée pas de doublon.

Le **storyboard** se recadre dans la vue Récit (mode storyboard). Au survol d'un micro-récit,
des outils apparaissent : ✎ pour le modifier (ou double-clic), ＋ pour en insérer un après, ↑ ↓ pour le
déplacer, × pour le retirer. Un plan vide propose « ＋ premier micro-récit ». Le détail d'un plan donne
ses champs, ses ajouts permis, et deux actions : « insérer un plan après », « retirer ce plan ». Retirer
un plan n'est possible que s'il ne porte aucun paragraphe du récit. « ＋ ajouter un plan à la fin » se
trouve au bas de la vue. Côté serveur, c'est `livre.forme_plan`, sur `POST
/api/chapitres/<slug>/storyboard/<op>`. Les paragraphes du récit suivent leur micro-récit.

Le **texte du récit** a les mêmes outils, en face. Au survol d'un paragraphe : ✎ pour le corriger, ＋ pour
écrire un paragraphe après lui dans le même plan, ↑ ↓ pour le déplacer dans son plan, × pour le retirer.
Chaque rang vide d'un plan propose « ✎ l'écrire à la main », à côté de « ✦ écrire ce paragraphe ».
**Le texte et le storyboard restent alignés ligne à ligne.** Une ligne, c'est un micro-récit et son
paragraphe, et elle bouge d'un bloc des deux côtés :
- **＋** (d'un côté ou de l'autre) insère une ligne : un micro-récit, obligatoire, et son paragraphe,
  facultatif. Les lignes suivantes descendent toutes les deux.
- **↑ ↓** déplace la ligne : depuis le paragraphe, le micro-récit le suit ; depuis le micro-récit, le
  paragraphe le suit.
- **×** côté micro-récit retire la ligne entière, et le texte du paragraphe reste au journal. S'il porte des
  assertions, une confirmation est demandée.
- **×** côté paragraphe retire seulement le texte : le micro-récit reste, à écrire.

Le serveur refuse ce qui désalignerait les deux côtés :
- un paragraphe sur une ligne sans micro-récit ;
- un paragraphe sur une ligne déjà écrite ;
- un déplacement du texte seul.

En mode « corriger », « ＋ paragraphe après » demande le micro-récit de la nouvelle ligne. Claude écrit un
plan entier avec exactement un paragraphe par micro-récit ; s'il ne le fait pas, le tiroir signale l'écart.
Un récit plus ancien peut avoir des paragraphes au-delà des micro-récits : la vue les signale (« sans
micro-récit »), et « ＋ micro-récit pour ce paragraphe » les rattache.
Côté serveur, c'est `narration.paragraphe`, sur `POST /api/chapitres/<slug>/recit/paragraphes/<op>` ;
`recit.md` et `links.yaml` sont réécrits ensemble, avec un groupe par plan séparé par `---`. Sans
modification, la réécriture redonne le même fichier, à l'octet près, pour les 27 récits d'Une Vie.
Retirer un paragraphe qui porte des assertions demande une confirmation. Le mode « corriger » accepte aussi
d'insérer et de supprimer un paragraphe du récit. Chaque opération va au journal du chapitre, avec le
texte complet. Le storyboard, lui, s'écrit dans `brief.yaml` (mise en forme gardée), noté au
journal ; la réécriture suivante lit le nouveau cadre. Une re-migration du chapitre ne
remplace plus brief, textes ni liens sans `--ecraser`. Claude rend des propositions structurées ; le tiroir (↻ dans l'en-tête) les
montre mot à mot. « Retenir » réécrit les paragraphes visés (^id conservés), écrit le
journal, résout les annotations traitées ; « aucune ne convient » garde le motif. Claude ne
touche jamais au texte lui-même. Le serveur le
reçoit par la variable `LIMALIBRI_LIVRE`. Les scripts de `migrer/` restent propres à
l'import d'Une Vie depuis son ancien dépôt.

À la main :

```bash
poetry install                                        # une fois
brew install poppler                                  # une fois, hors Poetry : pdftoppm, pour que Claude lise les PDF par pages
poetry run python3 migrer/structure.py                # ordre.md -> book-atelier/structure.yaml
poetry run python3 migrer/chapitre.py la-mer          # un chapitre -> book-atelier/chapters/la-mer/
poetry run python3 migrer/chapitre.py --texte --tous  # les chapitres sans cadre : leurs deux textes seuls (ni verrou ni storyboard)
poetry run python3 migrer/storyboard.py --tous        # leur storyboard, reconstitué depuis le récit : un plan par groupe entre « --- »,
                                                      # titres, cadre et micro-récits par Claude (un appel par chapitre)
poetry run python3 migrer/liens_essai.py la-mer <analyse.json>   # liens verrou -> essai, écarts
poetry run python3 migrer/bibliographie.py la-mer <analyse.json>  # bibliographie du chapitre
poetry run python3 migrer/fiches.py                   # science/*.md -> book-atelier/kb/fiches/
poetry run python3 migrer/liens_fiches.py             # fiches des chapitres et des œuvres
poetry run uvicorn limalibri.serveur:app --reload --port 8765
```

Puis <http://localhost:8765>. Le récit d'un chapitre migré montre ses plans en marge ; un
clic sur un paragraphe ouvre sa fiche : plan, micro-récit, assertions du verrou.

## La frise du livre

`limalibri/frise.py` et la vue Plan → **frise** (`#plan/frise`) montrent où se place chaque chapitre dans le temps de
l'histoire. On peut aussi y dessiner des frises internes, par exemple les scènes d'un chapitre dans l'histoire des
découvertes.

Tout vient de **`frise.yaml`**, à la racine du livre. Ce fichier s'édite à la main ; LimaLibri le lit et le
dessine. Un bouton « Amorcer » le crée à partir des périodes des chapitres, et ne remplace jamais un fichier
existant.

- **Le temps du livre.** Il n'y a qu'une seule variable : t, en années depuis l'origine de l'histoire.
  - `temps.age` donne le présent.
  - `temps.lecture` dit comment lire une durée seule : `depuis_origine` (Un Monde) ou `avant_present` (Une Vie).
  - Les dates s'écrivent en clair : « 4,5 Ga », « il y a 66 Ma », « 10⁻³⁶ s », « 3 min », « an 1781 »,
    « aujourd'hui », « dans mille ans ».
  - Dans une liste entre crochets ou accolades, une date avec une virgule s'écrit entre guillemets : `"13,8 Ga"`.
- **Les échelles.** Un livre peut en avoir plusieurs, et la vue passe de l'une à l'autre :
  - `lineaire` ;
  - `log`, pour des temps qui s'étendent sur des ordres de grandeur ;
  - `fixe`, des intervalles réguliers entre les dates connues.

  Chaque échelle a sa variable : `depuis_origine`, `avant_present` ou `annee` (le calendrier). Elle a aussi
  son domaine, et des graduations facultatives, éventuellement libellées (`{date, texte}`). C'est ainsi que
  fonctionne le calendrier cosmique d'Un Monde.
- **Les bandes.** Ce sont des échelles superposées :
  - des `segments`, comme les éons et les ères d'Une Vie, ou les époques cosmiques d'Un Monde ;
  - un `gradient`, comme le décalage vers le rouge.
- **Les repères.** Ce sont des dates marquées sur l'axe.
- **Les chapitres.** Chacun a `debut`, `fin` et `approx`. Une borne absente est ouverte : la barre s'estompe.
  `non_date` le liste sous la frise. Le rendu `fleche` relie les chapitres dans l'ordre de lecture, et les
  retours en arrière sont en couleur.
- **Les frises internes.** Ce sont des listes d'événements, liées ou non à un chapitre, avec leur échelle. Le
  rendu `fleche` montre l'ordre du récit, et donc ses voyages dans le temps.

Les avertissements (date illisible, domaine faux) s'affichent sous la frise.

Dans les vues de lecture (le récit, l'essai en mode texte), une **frise réduite** se place sous la progression.
Elle montre tous les chapitres en traits discrets et celui-ci en évidence, avec sa période, sur l'échelle
choisie dans son menu (la première de `frise.yaml`, d'abord), avec toutes ses graduations (une valeur qui
chevaucherait sa voisine est omise, faute de place). Le choix est retenu d'un chapitre à l'autre, et
c'est celui de la grande frise des chapitres. Un clic ouvre la frise du livre, le chapitre mis en avant. Les frises internes du chapitre y ont leur
lien. Un chapitre pas encore daté le dit.

## Le site public d'un livre

`limalibri/public.py` génère un mini-site statique, en lecture seule et lisible sur mobile, pour suivre un livre et le
lire. Le livre y est publié en l'état.

**Ce que le site contient :**
- la progression de chaque version, par étape ;
- les objectifs en cours ;
- les dernières avancées ;
- le sommaire par partie, chaque chapitre avec son statut et sa jauge ;
- le récit et l'essai de chaque chapitre écrit, avec un sélecteur récit / essai et les chapitres précédent et
  suivant ;
- les fiches que les chapitres citent ;
- la bibliographie des œuvres citées.

**Sur le site :**
- un sélecteur de thème (◐ auto, ☀ clair, ☾ sombre) et un bouton **Aa** pour la taille du texte (13 à 26 px) et la
  largeur de la colonne (étroite, moyenne, large). Les choix sont retenus par le navigateur ;
- la carte des fiches par cluster thématique dans `fiches/index.html`, à gauche les chapitres et à droite les fiches.
  C'est le dessin de l'édition « essai + base », avec des liens vers les pages du site ;
- la carte du chapitre sous l'essai de chaque chapitre ;
- **la frise** (`frise.html`, si le livre a un `frise.yaml`), dessinée par le même moteur que LimaLibri,
  extrait de `front/limalibri.js` à la génération. Ses données sont dans `frise-donnees.js`, partagé par toutes
  les pages. Elle a les mêmes réglages : la frise (globale ou interne), l'échelle, les bandes, les repères,
  les flèches. `?ch=<slug>` met un chapitre en avant, `?frise=<id>` ouvre une frise interne ;
- sur chaque page de chapitre, le bandeau **« Dans le temps »** : une mini-frise où le chapitre est en évidence
  parmi les autres, sur la première échelle. Elle donne sa période, un lien vers la frise du livre et vers ses
  frises internes.

**Ce qui ne sort pas :** coûts, consignes, demandes, annotations. Les liens internes, les renvois entre chapitres et
les citations sont réécrits. Un lien vers une fiche non publiée devient du texte.

**Où le site est écrit :** hors du dépôt, dans `~/.cache/limalibri-public/<livre>/site`.

**Depuis la vue Livre, onglet « site public » (`#livre/public`) :**
- « générer l'aperçu » génère le site et l'ouvre sous `/apercu-public/` ;
- « Publier » génère le site, puis le déploie sur Cloudflare Pages avec `wrangler pages deploy`. Le projet est créé
  au premier déploiement. La dernière publication (date, URL, journal en cas d'échec) est affichée.

**Réglages** (`livre.yaml`, facultatif ; ils se modifient aussi dans l'onglet, rubrique « Configuration ») :
```yaml
publication:
  projet: un-monde                       # le projet Cloudflare Pages (par défaut : le titre en slug)
  adresse: un-monde.awen-project.org     # le domaine personnalisé, à rattacher dans Cloudflare
  wrangler: /chemin/vers/wrangler        # sinon : wrangler du PATH, ou npx wrangler@4
```

**Une fois :**
1. Lancer `npx wrangler login`.
2. Après le premier déploiement, dans Cloudflare : Workers & Pages → le projet → Custom domains → le sous-domaine.

## Un exemple : *Une vie*

| | rôle | LimaLibri… |
|---|---|---|
| l'ancien dépôt du livre (héritage, déclaré dans `livre.yaml`) | ses outils et son cycle d'origine | le lit, n'y écrit jamais |
| le dossier du livre (`book-atelier/`) | la représentation du livre | la lit et l'écrit |
| LimaLibri | l'application | — |

Les scripts qui ont importé *Une vie* depuis son ancien dépôt (`migrer/`) sont restés avec le livre.

## Licence

LimaLibri est distribué sous la [licence Apache 2.0](LICENSE). Copyright 2026 Serge Fantino.
