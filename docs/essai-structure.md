# L'essai en texte + métadonnées — proposition

*2026-09-26. À discuter avant d'écrire du code. Part de ce qu'on a appris en reliant le
verrou de « la mer » à son essai.*

---

## Ce que la passe de liens a montré

77 assertions : 54 ont un appui direct dans l'essai, 21 un appui partiel, 2 aucun ; **21
écarts**, dont deux de valeur (4.8 marées « une fois et demie » contre « un tiers » ; 3.9
« le vingtième au fond » alors que l'essai met 5 % à sept kilomètres et 20 % à 34) et des
corrections du verrou jamais reportées dans l'essai (2.7, 4.7, 4.8).

Trois leçons :

1. **L'essai et le récit dérivent l'un de l'autre sans lien vivant.** Une correction faite
   d'un côté n'atteint pas l'autre. Le lien assertion → bloc de l'essai (désormais dans le
   verrou) rend l'écart *visible* ; il ne l'empêche pas.
2. **Le rapprochement par les mots plafonne** (66/77, bruité). Il faut une lecture — modèle
   ou humain — et donc un endroit stable où la ranger.
3. **L'essai contient déjà sa propre base de connaissance, en prose** : les notes portent
   les calculs et les sources ; la section « Ce que ce chapitre démontre » classe les faits
   en *solidement établi / discuté / presque inconnu*. C'est de la métadonnée écrite comme
   du texte.

## Principe

Comme pour le verrou : **la prose reste la source, les métadonnées sont extraites du texte
existant** et vivent à côté. L'essai n'est pas regénéré depuis une base ; la base est
tirée de l'essai et reliée à lui. On peut changer d'avis plus tard, mais pas avant d'avoir
vu ce que donne l'extraction sur un chapitre.

## Les fichiers

```
chapters/<slug>/
  essai.md          la prose, ^id par paragraphe, notes [^slug-…] et citations [@cle] dedans
  essai.yaml        par bloc : rôle, confiance, faits énoncés        (nouveau)
  verrou.yaml       par assertion : essai (blocs, appui), ecart       (fait — 2026-09-26)
kb/
  faits/<id>.md     un fait atomique, partagé entre chapitres         (nouveau)
  sources/<cle>.md  une œuvre — migration de bibliographie.md (1 050 entrées)
  concepts/<id>.md  un terme — migration de glossaire.md (338)
```

### `essai.yaml` — ce que fait chaque bloc

```yaml
e82a:
  role: chiffre          # scene | mecanisme | chiffre | methode | debat | bilan | transition
  confiance: etabli      # etabli | discute | inconnu   (repris du bilan de fin de chapitre)
  faits: [echappement-h-taux-actuel]
```

`role: methode` marque ce que le récit n'a pas le droit de reprendre (R11 : « nous le
savons par des zircons » est l'histoire de l'histoire). Le rôle dit donc à la fois ce
qu'est le bloc et ce qui peut passer dans le récit.

### `kb/faits/<id>.md` — le fait, une fois pour tout le livre

```markdown
---
id: echappement-h-taux-actuel
enonce: l'hydrogène quitte la Terre à environ 3 kg/s
valeur: {nombre: 3, unite: kg/s}
epoque: actuel
confiance: etabli
sources: [hunten1973, catling2017]
essai: [la-mer#e82a]
verrou: [la-mer:7.9]
---
Le taux est fixé par l'approvisionnement (diffusion à travers le piège froid), pas par le
mécanisme d'échappement lui-même. …
```

Un fait qui revient dans deux chapitres (le Soleil à 70 %, « repris en 6.5 ») n'existe
qu'une fois. Une valeur structurée rend les écarts de valeur **vérifiables mécaniquement** :
4.8 aurait été attrapé par un contrôle, pas par une lecture.

### À terme, le verrou pointe vers des faits

`assertion -> faits -> blocs de l'essai`. Le lien direct assertion → bloc posé aujourd'hui
devient dérivable ; on le garde tant que les faits n'existent pas.

## Deux lectures du même matériau

- **Mode livre** : `essai.md` assemblé, notes en bas, citations résolues depuis `kb/sources`,
  glossaire en infobulle depuis `kb/concepts` — ce que fait déjà l'ancien assembleur.
- **Mode base** : naviguer par fait (où il est dit, avec quelle confiance, d'après qui,
  quelles assertions du récit en dépendent) ; filtrer par époque ou par confiance.

## Ordre proposé

1. **Sources et concepts** : migration mécanique de `bibliographie.md` et `glossaire.md`.
   Sans risque, et l'essai se rend enfin avec ses citations.
2. **`essai.yaml` pour la mer** : une passe de lecture (rôle, confiance par bloc).
3. **Faits de la mer** : extraction depuis l'essai (on peut s'attendre à 40–60 faits),
   puis on fait pointer le verrou vers eux.
4. **Contrôle de valeur** : écart entre la valeur d'un fait et le texte d'une assertion.
5. Bilan honnête sur la mer avant de toucher un autre chapitre.

## Questions ouvertes

- **Le grain d'un fait.** « La Lune à 90 % de sa distance il y a deux milliards d'années »
  est-il un fait, ou quatre (distance, taille, marées, journée) ? Le verrou 4.8 en groupe
  quatre ; un contrôle de valeur en veut un par nombre.
- **Qui corrige quoi quand un écart est trouvé.** Aujourd'hui l'écart est signalé ; il faut
  décider si la correction part de l'essai (qui source) vers le récit, ou l'inverse selon le
  cas — et le consigner dans le fait, avec sa date.
