#!/usr/bin/env bash
# Lance l'atelier sur un livre : installe les dépendances si besoin, démarre le
# serveur, ouvre le navigateur.
#
#   ./run.sh ~/livres/mon-livre               un livre, par son dossier, port 8765
#   ./run.sh ~/livres/autre 9000              un autre livre, un autre port
#   LIMALIBRI_LIVRE=~/livres/mon-livre ./run.sh   le livre par une variable d'environnement
#   ./run.sh --no-open                        sans ouvrir le navigateur
#
# Un livre est un dossier avec livre.yaml et structure.yaml. Un dossier qui ne les a pas
# les reçoit, vides, au démarrage ; un dossier qui n'existe pas est créé après confirmation.
set -euo pipefail

ICI="$(cd "$(dirname "$0")" && pwd)"
LIVRE="${LIMALIBRI_LIVRE:-}"
PORT=8765
OUVRIR=1
for a in "$@"; do
  case "$a" in
    --no-open) OUVRIR=0 ;;
    ''|*[!0-9]*)
      if [ ! -d "$a" ]; then
        printf "le dossier %s n'existe pas — en faire un nouveau livre ? [o/N] " "$a"
        read -r rep
        case "$rep" in o|O|oui) mkdir -p "$a" ;; *) echo "abandon" >&2; exit 2 ;; esac
      fi
      LIVRE="$a" ;;                              # résolu depuis le dossier courant, avant tout cd
    *) PORT="$a" ;;
  esac
done
if [ -z "$LIVRE" ]; then
  echo "LimaLibri — quel livre ? ./run.sh <dossier du livre> [port] [--no-open]" >&2
  exit 2
fi
LIVRE="$(cd "$LIVRE" && pwd)"
[ -f "$LIVRE/structure.yaml" ] || echo "pas encore un livre : livre.yaml et structure.yaml y seront créés"

cd "$ICI"
command -v poetry >/dev/null || { echo "poetry introuvable — https://python-poetry.org" >&2; exit 1; }
[ -d .venv ] || poetry install --no-interaction
# poppler (pdftoppm) : un outil du système, pas un paquet Python. Claude Code s'en sert pour lire
# un PDF par pages ; sans lui, les demandes à Claude se rabattent sur les pages HTML.
command -v pdftoppm >/dev/null || echo "note : pdftoppm introuvable — les PDF ne seront pas lus par Claude (brew install poppler)" >&2

if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "le port $PORT est déjà pris — ./run.sh <livre> <autre port>" >&2; exit 1
fi

URL="http://localhost:$PORT"
TITRE="$(sed -n 's/^titre: *//p' "$LIVRE/livre.yaml" 2>/dev/null | head -1 || true)"   # pas de livre.yaml : pas de titre
echo "Atelier — ${TITRE:-$(basename "$LIVRE")}"
echo "  livre   $LIVRE"
echo "  adresse $URL   (ctrl-C pour arrêter)"
if [ "$OUVRIR" = 1 ]; then
  ( for _ in $(seq 20); do curl -s "$URL/api/chapitres" >/dev/null && break; sleep 0.5; done
    open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true ) &
fi
export ATELIER_LIVRE="$LIVRE"
exec poetry run uvicorn atelier.serveur:app --reload --port "$PORT"
