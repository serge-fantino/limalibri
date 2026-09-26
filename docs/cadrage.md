# Une vie — objectif du projet et pistes d'architecture

> Document de cadrage destiné à être lu par Claude Code au démarrage d'une session.
> Il décrit **ce qu'on veut construire** et **des pistes de structure de données** à challenger,
> pas une spécification arrêtée.
>
> *Reçu le 2026-09-26. Quelques passages étaient tronqués au collage ; ils sont marqués
> `[…]`. Les exemples (« La panne », la passagère, 2031) ne viennent pas d'Une vie : voir
> `audit.md` §2.1.*

---

## 1. Ce qu'est le projet

« Une vie » est un récit multimédia en vignettes : de LECA à la fin du monde, avec un clin d'œil
au paradoxe de Fermi. Six parties, vingt-six chapitres, adossés à des faits scientifiques et
historiques, avec une bibliographie qui sert au fact-checking.

Le projet a deux faces indissociables :

1. **Le livre** — le texte, sa structure, sa voix, ses sources.
2. **L'atelier** — l'outillage qui permet de l'écrire avec un vrai contrôle : base de
   connaissances, briefs de chapitre, révision fine, traçabilité vers les faits.

On garde **un seul repo**. L'atelier n'est pas un produit générique : c'est l'outillage de ce
livre-là, au même titre que CodeDistillery est l'outillage […] généralisable plus tard, tant
mieux, mais ce n'est pas l'objectif.

## 2. Le problème à résoudre

L'approche actuelle — Claude Code écrit, un harnais évalue, une UX affiche — produit un résultat
en dessous des objectifs et laborieux. Trois causes probables :

- **Le brief est implicite.** Claude reçoit un contexte large et reconstruit à chaque fois ce que
  le chapitre doit être. Les intentions ne sont pas matérialisées quelque part de stable.
- **La granularité de correction est trop grossière.** On révise le chapitre en bloc ; on ne peut
  pas dire « cette phrase-là, autrement, pour cette raison » et obtenir trois propositions.
- **Le harnais diagnostique mal.** Il dit qu'un texte échoue, il ne dit pas *où* ni *contre quelle
  contrainte*. Un score global n'est pas actionnable.

L'objectif de l'atelier est donc : **rendre les intentions explicites, adressables et
révisables au bon grain.**

## 3. Deux principes structurants

**a. Le texte reste du Markdown.**
Ne pas fragment[…] Le texte doit rester lisible, diffable, éditable à la main, et écrivable
naturellement par Claude Code. Tout ce qui est métadonnée vit à côté, pas dedans. C'est la
condition pour que l'écriture ne devienne pas de la saisie de formulaire.

**b. Séparation des responsabilités d'écriture.**
Pour éviter les conflits UX ↔ Claude Code, on attribue chaque fichier à un seul écrivain :

| Fichier | Écrit par | Lu par |
| --- | --- | --- |
| `structure.yaml` | UX et Claude Code | les deux |
| `brief.yaml` (par chapitre) | UX surtout | Claude Code |
| `text.md` (par chapitre) | Claude Code | les deux |
| `annotations.jsonl` | UX (append-only) | Claude Code |
| `variants/` | Claude Code | UX |
| base de connaissances | les deux | les deux |

Git est le substrat de fusion. Chaque écriture est un commit atomique avec un message
conventionnel (`text(ch08): révision §4-7 sur annotation a-31`), ce qui donne gratuitement un
historique lisible du travail d'écriture.

## 4. Pistes de structure de donnée proposée

```
/structure.yaml              # colonne vertébrale : parties, chapitres, ordre, statut
/kb/
  facts/<id>.md              # un fait = un fichier, frontmatter + développement
  characters/<id>.md
  events/<id>.md             # chronologie
  sources/<id>.md            # bibliographie
  concepts/<id>.md           # notions scientifiques mobilisées
/style/
  voice.md                   # le protocole d'écriture : la voix qui raconte
  rules.yaml                 # règles vérifiables mécaniquement
/chapters/<nn>-<slug>/
  brief.yaml                 # l'atelier : intentions et contraintes du chapitre
  text.md                    # la prose, avec ancres de bloc
  links.yaml                 # bloc -> entités de la KB
  annotations.jsonl          # tes annotations, ancrées
  variants/<block-id>.yaml   # propositions alternatives
  reports/<date>.json        # sorties du harnais
```

### 4.2 La colonne vertébrale

`structure.yaml` est le seul endroit qui décrit l'ordre et le découpage. Il est […]eux
côtés, ce qui impose qu'il reste **petit et déclaratif** — pas de contenu dedans, uniquement des
références.

```yaml
parts:
  - id: p2
    title: "L'intervalle"
    chapters:
      - id: ch08
        slug: la-panne
        title: "La panne"
        status: draft          # outline | draft | revised | locked
        pov: passagere
        span: [ev-2031-03, ev-2031-11]   # bornes chronologiques
```

Le `span` est important : il permet de dériver automatiquement quels événements et quels faits
sont *dans le champ* d'un chapitre, au lieu de les lister à la main.

### 4.3 L'ancrage — la vraie décision

C'est le point qui conditionne tout le reste : annotations, traçabilité, variantes, réordonnancement.

**Proposition : identité au niveau du bloc, adressage par citation à l'intérieur du bloc.**

Un bloc = un paragraphe ou une vignette. Il porte un identifiant stable, invisible au rendu :

```markdown
Elle n'avait pas compris tout de suite. Le silence de la radio,
d'abord, puis l'absence ciel. ^b7f3
```

- Le bloc survit à la réécriture de son contenu → annotations et liens restent valides.
- Le bloc peut être déplacé → le réordonnancement ne casse rien.
- La **phrase** n'a pas d'identité propre : elle est trop volatile. On l'adresse par
  `{block: b7f3, quote: "puis l'absence de traînées"}`, résolu par recherche exacte puis
  approchée. Si la citation ne se retrouve plus, l'annotation est marquée *orpheline* et
  remontée dans l'UX plutôt que silencieusement perdue.

L'alternative — offsets de caractères — est plus simple à implémenter et se casse à la première
révision. À éviter.

### 4.4 Le brief de chapitre

C'est l'objet central de l'atelier : ce que tu remplis avant d'écrire, et le **seul** contrat
passé à Claude Code.

```yaml
chapter: ch08
intent: >
  Faire basculer le lecteur de la routine à l'irréversible, sans que
  la narratrice le nomme. Elle constate, elle ne comprend pas encore.
pov: passagere
tense: passe-compose
register: sec, phrases cou[…]
beats:
  - id: b1
    summary: "Le silence radio, perçu comme une panne locale"
    requires_facts: [f-ionosphere-blackout]
    characters: [passagere]
  - id: b2
    summary: "La tentative d'appel, l'absence de réponse"
    tension: monte

facts_in_scope: [f-ionosphere-blackout, f-satellite-decay-2031]
facts_forbidden: [f-origine-signal]     # pas encore révélé au lecteur
continuity:
  from: ch07                            # état narratif entrant
  establishes: [la-passagere-seule]

constraints:
  - no_explanation        # la voix raconte l'histoire, pas comment on la connaît
  - no_anachronism_after: 2031
```

Deux choses à noter :

- `facts_forbidden` et `continuity` sont aussi importants que ce qu'on autorise. La cohérence d'un
  récit tient autant à ce qu'on ne dit pas encore qu'à ce qu'on dit.
- Les `beats` donnent le grain de génération et de révision : on peut régénérer un beat seul.

Le brief est **compilé** en prompt par un module explicite et versionné (`compile_brief.py` ou
équ[…]ser cette compilation implicite : quand le texte déçoit, il faut pouvoir
lire exactement ce que Claude a reçu.

### 4.5 La traçabilité

`links.yaml` par chapitre, maintenu par Claude Code, éditable dans l'UX :

```yaml
b7f3:
  facts: [f-ionosphere-blackout]
  characters: [passagere]
  beat: b1
  confidence: asserted   # asserted | implied | decorative
```

Le champ `confidence` évite le piège du tout-ou-rien : un bloc qui *affirme* un fait doit être
fact-checké, un bloc qui l'*évoque* ne doit pas déclencher d'alerte. Sans cette distinction, le
harnais crie trop et on l'ignore.

C'est cette table qui rend possible la navigation multi-plans : passer du récit à la science, c'est
suivre `links.yaml` en sens inverse.

### 4.6 Les variantes

Le mode « auto-complete pour la prose ». Pour un bloc ou une citation à l'intérieur d'un bloc :

```yaml
block: b7f3
selection: "puis l'absence de traînées"
request: "plus sec, supprimer l'effet d'annonce"
proposals:
  - id: v1
    text: "puis le ciel vide[…]
    respects: [reg]ister-sec, no_explanation]
    tension: [beat-b1]
    status: proposed        # proposed | accepted | rejected
  - id: v2
    text: "puis rien dans le ciel"
    respects: [register-sec]
    status: rejected
    reason: "trop plat"
```

Conserver les rejets avec leur motif : au bout de trente chapitres, c'est un corpus qui apprend à
l'atelier ce que tu ne veux pas. C'est probablement la donnée la plus précieuse du système, et
elle est habituellement jetée.

### 4.7 Le harnais, reformulé

Le harnais actuel évalue globalement. Il doit devenir **diagnostique** : toute violation pointe un
bloc et une contrainte nommée.

```json
{
  "block": "b7f3",
  "rule": "no_explanation",
  "severity": "warn",
  "evidence": "ce que les instruments montreraient plus tard",
  "suggestion": null
}
```

Deux familles de règles, à ne pas mélanger :

- **Mécaniques** (déterministes, rapides, lancées à chaque écriture) : anachronismes, noms de
  personnages hors scope, faits interdits cités, longueur de phrase, mar[…]annis.
- **Jugement** (par modèle, lancées à la demande) : voix, tension, accessibilité, cohérence de POV.

Ne faire tourner les secondes qu'à la demande : elles sont lentes, coûteuses et bruyantes. Les
premières doivent être assez rapides pour tourner en pre-commit.

## 5. Ce qu'il faut décider avant de coder

1. **Format de la base de connaissances** — fichiers Markdown + frontmatter (git-friendly,
   lisible, éditable par Claude Code) ou base structurée (requêtable, mais opaque en diff) ?
   Recommandation : Markdown, avec un index dérivé reconstructible.
2. **Granularité du bloc** — paragraphe ou vignette ? Le récit étant « en vignettes », la vignette
   est peut-être l'unité naturelle, avec des paragraphes dedans. À trancher sur un chapitre réel.
3. **Qui écrit `links.yaml`** — Claude Code au fil de l'écriture, ou une passe d'indexation après
   coup ? La première option est plus juste, la seconde plus simple.
4. **Mode de génération des variantes** — appel unique […] indépendants ? Le second donne plus de
   diversité, le premier est plus cohérent avec la contrainte de non-répétition.
5. **Statut du texte existant** — migration des chapitres déjà écrits vers le format ancré, ou
   repartir chapitre par chapitre au fil des révisions ?

## 6. Premier jalon proposé

Ne pas construire tout l'atelier. Prendre **un chapitre existant** et le faire passer entièrement
par la chaîne cible :

1. Écrire son `brief.yaml` à la main.
2. Ancrer son `text.md` en blocs.
3. Remplir `links.yaml` pour ce chapitre seul.
4. Écrire le compilateur de brief et régénérer un beat.
5. Implémenter la demande de variantes sur une phrase.
6. Comparer honnêtement au résultat obtenu avec l'approche actuelle.

Si le résultat n'est pas nettement meilleur sur ce chapitre-là, le problème n'est pas l'outillage
et il faut chercher ailleurs avant d'industrialiser.

---

## Première tâche pour Claude Code

Auditer le repo existant : arborescence, format actuel de la structure et […], ce que fait le
harnais. Puis confronter l'état réel aux pistes ci-dessus et signaler ce qui ne colle pas — les
pistes sont écrites sans connaissance du code existant.
