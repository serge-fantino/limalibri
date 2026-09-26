#!/usr/bin/env bash
# Lance l'atelier sur un livre : installe les dépendances si besoin, démarre le
# serveur, ouvre le navigateur.
#
#   ./run.sh                                  le livre par défaut (UneVie/book-atelier), port 8765
#   ./run.sh ../../UneVie/book-atelier        un livre, par son dossier (relatif au dossier courant)
#   ./run.sh ~/livres/autre 9000              un autre livre, un autre port
#   ./run.sh --no-open                        sans ouvrir le navigateur
#
# Un livre est un dossier avec livre.yaml et structure.yaml. Un dossier qui ne les a pas
# les reçoit, vides, au démarrage ; un dossier qui n'existe pas est créé après confirmation.
set -euo pipefail

ICI="$(cd "$(dirname "$0")" && pwd)"
LIVRE="$ICI/../../UneVie/book-atelier"
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
LIVRE="$(cd "$LIVRE" && pwd)"
[ -f "$LIVRE/structure.yaml" ] || echo "pas encore un livre : livre.yaml et structure.yaml y seront créés"

cd "$ICI"
command -v poetry >/dev/null || { echo "poetry introuvable — https://python-poetry.org" >&2; exit 1; }
[ -d .venv ] || poetry install --no-interaction

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
