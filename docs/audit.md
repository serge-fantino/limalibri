# Audit — l'existant face au cadrage

*2026-09-26. Confronte `docs/cadrage.md` (écrit sans voir le code) à l'état réel de
`noosphereV2/Books/UneVie-book`. L'ancien dépôt reste en place, en lecture seule pour l'atelier.*

---

## 1. Ce qui existe déjà

| Piste du cadrage | Ce qui existe | Où |
|---|---|---|
| `structure.yaml` | `ordre.md` : parties, ordre, préface ; numéro = position, identité = slug | `ordre.md`, `outils/manifeste.py` |
| `brief.yaml` | le **cadre** : budget chiffré, intention, verrou d'assertions (`!` `~` `✗` + motif daté) | `recit/cadre/<slug>.md` |
| `beats` | le **storyboard** : plans avec lieu, temps, ambiance, attaque, chute, `sequence`, `recits`, quota d'`ajouts` | `recit/cadre/<slug>.storyboard.md` |
| `links.yaml` | les marqueurs `<!--A: 1.1,1.2-->` en fin de paragraphe : bloc → assertions | `recit/cadre/<slug>.habillage.md` |
| `text.md` | chapitre posé depuis l'habillage par `poser.py` (marqueurs retirés) | `recit/chapitres/<slug>.md` |
| harnais mécanique | `cycle.py` (7 portes), `cadre.py` (verrou, budget, séquence), `style.py` (R1–R15), `relecture.py` | `recit/outils/` |
| harnais jugement | la **lecture naïve**, verrouillée par empreinte dans `relecture.json` | `recit/cadre/00-relecture.md` |
| `kb/sources` | `bibliographie.md` : 1 050 entrées, clés `[@cle]`, un seul fichier | `livre/` |
| `kb/concepts` | `glossaire.md` : 338 termes, un seul fichier | `livre/` |
| `kb/facts` | 79 fiches `science/*.md` : des dossiers thématiques, pas un fait par fichier | `science/` |
| `annotations.jsonl` | annotations du lecteur HTML, dans le `localStorage` du navigateur | `outils/lecteur.gabarit.html` |
| `style/voice.md`, `rules.yaml` | `recit/README.md` (15 règles), `00-interdits.md`, `CLAUDE.md` | `recit/` |

Conclusion : **le brief, les beats, la traçabilité et un harnais en partie diagnostique
existent déjà**, sous d'autres noms et dans d'autres formats. L'atelier a moins à inventer
qu'à *réorganiser* : sortir ces données des fichiers Markdown où elles sont mêlées, et leur
donner une UI.

## 2. Ce qui ne colle pas

**2.1 Les exemples du cadrage viennent d'un autre livre.** « La panne », « L'intervalle »,
`pov: passagere`, `ev-2031-03`, ionosphère, satellites : rien de cela n'existe dans Une vie.
La Passagère appartient à une couche antérieure (voir 2.7). Les champs `pov`, `tense`,
`characters` n'ont presque pas de prise ici : le récit n'a quasiment pas de personnage, la
voix est unique et impersonnelle (R8), le temps est fixé par la règle.

**2.2 `span` en dates ne marche pas.** La chronologie va de 4,5 milliards d'années à
l'avenir. Les `periode:` actuelles sont du texte libre (« l'état de départ, et ce qui le
tient »), et plusieurs chapitres sont thématiques plutôt que datés. Il faut un temps
géologique numérique (Ma, avec des bornes floues), et accepter que certains chapitres n'aient
pas de `span`.

**2.3 Deux textes, pas un.** Le cadrage suppose un `text.md` par chapitre. Il y en a deux,
livre et récit, alignés un pour un. Le récit est dérivé du livre (`source:` dans chaque
cadre), et le verrou est extrait du texte. Il faut décider si l'atelier porte les deux
versions ou seulement le récit.

**2.4 `chapters/<nn>-<slug>/` contredit la refonte du 2026-09-20.** Le numéro a été retiré
de tous les noms de fichiers. `book-atelier` reprend la même règle : `chapters/<slug>/`, et le
numéro reste la position dans `structure.yaml`.

**2.5 Les « facts » n'ont pas d'identité globale.** Aujourd'hui, un fait est une assertion
de verrou, numérotée *par chapitre* (`4.13` dans `le-texte`). Le même fait (l'absence
d'ozone, la règle d'Eigen) peut revenir dans deux chapitres sans lien entre eux. Les fiches
`science/` sont des dossiers, pas des faits atomiques. `facts_in_scope` et `facts_forbidden`
supposent un espace de faits partagé, qui n'existe pas encore. C'est le plus gros chantier
de la KB.

**2.6 Le texte ne contient pas « que de la prose ».** Le principe 3a (métadonnées à côté)
est déjà respecté par `recit/chapitres/`, mais **pas par l'habillage**, qui est le fichier
où l'on travaille vraiment. Côté livre, les notes `[^slug-…]` et citations `[@cle]` sont dans
le texte, et c'est légitime : c'est de l'appareil, pas de la métadonnée.

**2.7 Une architecture antérieure dort dans le dépôt.** `vignettes/`, `poetique/`,
`plan/montage.yaml`, `outils/lint.py`, `livre.py`, `compile.py`, `corriger.py`, `qui.py`
viennent d'une itération précédente (quatre voix, la Passagère, passages gelés). Elle
avait déjà le passage comme unité, le montage comme liste et le gel. `CLAUDE.md` ne la
mentionne plus. À classer : morte, ou à récupérer (le gel, en particulier, répond au
problème « je réécris, tu réécris par-dessus »).

**2.8 L'ancrage actuel est celui que le cadrage déconseille.** Les annotations du lecteur
sont ancrées par **décalage de caractères normalisé** et vivent **dans le navigateur**.
Elles ne sont donc ni dans git ni visibles par Claude Code. Le passage à
`annotations.jsonl` + `{block, quote}` règle les deux problèmes à la fois.

**2.9 Le harnais est plus diagnostique qu'annoncé.** `cadre.py` nomme l'assertion
manquante et la ligne où la séquence diverge ; `style.py` cite les phrases fautives. Ce qui
manque, c'est une **sortie structurée** (JSON par bloc et par règle) plutôt que du texte de
terminal. Le travail est une adaptation, pas une réécriture.

**2.10 Le dépôt git est `Awen-Project` entier.** « Un commit atomique par écriture » impose
au serveur de ne jamais faire `git add -A` : il n'indexe que les chemins de
`UneVie/book-atelier/`. Le `.DS_Store` racine est déjà modifié en permanence.

**2.11 Les ids `^b7f3` sont natifs d'Obsidian.** Le livre est ouvert dans un coffre Obsidian
(`.obsidian/`). La syntaxe proposée pour les blocs est exactement celle des références de
bloc d'Obsidian, donc `[[chapitre#^b7f3]]` fonctionnera sans outil. C'est un argument pour
l'adopter telle quelle.

## 3. Réponses proposées aux cinq décisions (§5 du cadrage)

1. **KB** : Markdown + frontmatter, index dérivé. Les sources et le glossaire se migrent
   mécaniquement (une entrée = un fichier). Les faits se construisent en *remontant* les
   assertions de verrou vers des faits globaux, chapitre par chapitre.
2. **Grain du bloc** : le **paragraphe**. C'est déjà l'unité des marqueurs `<!--A:-->`, des
   `recits` et de la relecture. Le « plan » du storyboard (groupe de paragraphes séparés par
   `---`) joue le rôle de la vignette, comme niveau intermédiaire.
3. **`links.yaml`** : **dérivé des marqueurs existants** pour les chapitres qui ont un cadre
   (1 à 5), puis écrit par Claude Code au fil de l'écriture. Pas de passe d'indexation séparée.
4. **Variantes** : un appel qui produit N propositions distinctes, avec en contexte les rejets
   passés du même bloc. Plus cohérent avec R14 (pas de répétition de formules).
5. **Texte existant** : migrer d'abord **un seul chapitre** (le jalon §6), `le-texte` ou
   `la-mer`, qui ont le dispositif complet et une lecture naïve. Pas de migration en masse.

## 4. Décisions prises (2026-09-26)

- L'atelier porte **les deux versions**. La version « livre » est renommée **essai** : elle
  donne le pourquoi et le comment du récit, elle ne raconte pas.
- Premier chapitre migré : **la-mer**.

## 5. Ce que fait déjà l'atelier (v0)

- `migrer/structure.py` : `ordre.md` + en-têtes → `UneVie/book-atelier/structure.yaml`
  (6 parties, 26 chapitres, 1 préface ; statut `revised` quand le cadre est complet).
- Serveur FastAPI : `/api/structure`, `/api/chapitres`, `/api/chapitres/<slug>/<version>`.
  Le texte est encore lu dans l'ancien dépôt.
- `migrer/chapitre.py` : cadre + storyboard + habillage + chapitres -> `brief.yaml`,
  `verrou.yaml`, `links.yaml`, `recit.md`, `essai.md` ancrés. Fait pour `la-mer` ; passe à sec
  sur les quatre autres chapitres qui ont un cadre.
- Front sans build : sommaire, bascule récit/essai, marges de plan, fiche de bloc.
