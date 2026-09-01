#!/bin/sh
#
# nerve — installateur cross-platform (Linux + macOS; Windows via WSL2).
#
# Usage :
#   curl -fsSL https://raw.githubusercontent.com/Nawal-alao/nerve/main/install.sh | sh
#
# Le script est idempotent : relancer sur une machine déjà configurée ne
# casse rien (il ne réinstalle que ce qui manque). Il ne pipe jamais de
# commande sudo sans l'annoncer explicitement à l'écran avant.
#
# NOTE publication PyPI : une fois nerve publié sur PyPI, remplacer
# l'installation ci-dessous par `pipx install nerve` (et le curl du README
# par le chemin PyPI). Le `git+https://...` reste valable en attendant.

set -e

# ---------------------------------------------------------------------------
# Couleurs/utilitaires d'affichage (POSIX — pas de bash-ismes)
# ---------------------------------------------------------------------------
if [ -t 1 ]; then
    _BOLD='\033[1m'
    _DIM='\033[2m'
    _RED='\033[31m'
    _GREEN='\033[32m'
    _YELLOW='\033[33m'
    _RESET='\033[0m'
else
    _BOLD=''
    _DIM=''
    _RED=''
    _GREEN=''
    _YELLOW=''
    _RESET=''
fi

# ---------------------------------------------------------------------------
# Bannière ASCII "NERVE" (bloc fixe, pas de police générée). La couleur est
# gérée par les variables ci-dessus (déjà "éteintes" hors tty) ; seule la
# locale indique si les caractères de dessin de boîte sont sûrs à imprimer.
# ---------------------------------------------------------------------------
banner() {
    case "${LANG:-}${LC_ALL:-}" in
        *UTF-8*|*utf8*) banner_ok=1 ;;
        *) banner_ok=0 ;;
    esac
    if [ "$banner_ok" = 1 ]; then
        printf '%b' "$_BOLD"
        cat <<'LOGO'

███╗   ██╗███████╗██████╗ ██╗   ██╗███████╗
████╗  ██║██╔════╝██╔══██╗██║   ██║██╔════╝
██╔██╗ ██║█████╗  ██████╔╝██║   ██║█████╗  
██║╚██╗██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██╔══╝  
██║ ╚████║███████╗██║  ██║ ╚████╔╝ ███████╗
╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝  ╚═╝  ╚══════╝

LOGO
        printf '%b\n' "$_RESET"
    else
        printf '%b\n' "${_BOLD}NERVE${_RESET}"
    fi
}
banner

info()  { printf '%b%b%s%b\n' "$_GREEN" "  • " "$1" "$_RESET"; }
step()  { printf '%b%b%s%b\n' "$_BOLD" "==> " "$1" "$_RESET"; }
warn()  { printf '%b%b%s%b\n' "$_YELLOW" "WARN " "$1" "$_RESET"; }
die()   { printf '%b%b%s%b\n' "$_RED" "ERROR " "$1" "$_RESET" >&2; exit 1; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# 1. Détection de l'OS
# ---------------------------------------------------------------------------
OS="$(uname -s 2>/dev/null || echo Unknown)"
case "$OS" in
    Darwin) OS_FAMILY="macos" ;;
    Linux)  OS_FAMILY="linux" ;;
    *)
        cat <<EOF

${_RED}Nerve nécessite Linux ou macOS.${_RESET}

Sur Windows, installe via WSL2 puis relance ce script depuis ton terminal
WSL (Ubuntu de préférence) :
  https://learn.microsoft.com/windows/wsl/install

EOF
        exit 1
        ;;
esac

# ---------------------------------------------------------------------------
# 2. Vérification Python >= 3.10
# ---------------------------------------------------------------------------
step "Vérification de Python (>= 3.10)"

if ! command_exists python3; then
    if [ "$OS_FAMILY" = "macos" ]; then
        cat <<EOF
${_RED}python3 est introuvable.${_RESET}
Installe Python 3.10+ :
  https://www.python.org/downloads/macos/
  (ou via Homebrew : brew install python)
Puis relance ce script.
EOF
    else
        cat <<EOF
${_RED}python3 est introuvable.${_RESET}
Installe Python 3.10+ via le gestionnaire de paquets de ta distro
(par ex. 'sudo apt install python3' sur Debian/Ubuntu), puis relance ce
script.
EOF
    fi
    exit 1
fi

PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0)"
PY_MAJOR="$(printf '%s' "$PY_VERSION" | cut -d. -f1)"
PY_MINOR="$(printf '%s' "$PY_VERSION" | cut -d. -f2)"

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    cat <<EOF
${_RED}Python $PY_VERSION est trop ancien : nerve requiert Python >= 3.10.${_RESET}
Met à niveau Python puis relance ce script.
EOF
    exit 1
fi
info "Python $PY_VERSION détecté (>= 3.10) : OK"

# ---------------------------------------------------------------------------
# 3. libolm — la dépendance critique (E2EE)
# ---------------------------------------------------------------------------
step "Vérification de libolm"

if [ "$OS_FAMILY" = "macos" ]; then
    if ! command_exists brew; then
        cat <<EOF
${_RED}Homebrew est introuvable (requis pour installer libolm).${_RESET}
Installe Homebrew :  https://brew.sh
Puis relance ce script.
EOF
        exit 1
    fi
    if brew list libolm >/dev/null 2>&1; then
        info "libolm déjà installé : OK"
    else
        echo "  ${_YELLOW}Installation de libolm via Homebrew (aucun sudo requis)…${_RESET}"
        brew install libolm
        info "libolm installé"
    fi
else
    # Linux : identifier la distro via /etc/os-release
    . /etc/os-release 2>/dev/null || { . /usr/lib/os-release 2>/dev/null || DISTRO_ID="unknown"; }
    DISTRO_ID="${ID:-unknown}"

    case "$DISTRO_ID" in
        debian|ubuntu|pop|linuxmint|elementary)
            if dpkg -s libolm-dev >/dev/null 2>&1; then
                info "libolm-dev déjà installé : OK"
            else
                echo "  ${_YELLOW}Installation de libolm-dev via apt (sudo requis)…${_RESET}"
                sudo apt-get update
                sudo apt-get install -y libolm-dev
                info "libolm-dev installé"
            fi
            ;;
        fedora|rhel|centos|rocky|almalinux)
            if rpm -q libolm-devel >/dev/null 2>&1; then
                info "libolm-devel déjà installé : OK"
            else
                echo "  ${_YELLOW}Installation de libolm-devel via dnf (sudo requis)…${_RESET}"
                sudo dnf install -y libolm-devel
                info "libolm-devel installé"
            fi
            ;;
        arch|manjaro|endeavouros)
            if pacman -Q libolm >/dev/null 2>&1; then
                info "libolm déjà installé : OK"
            else
                echo "  ${_YELLOW}Installation de libolm via pacman (sudo requis)…${_RESET}"
                sudo pacman -S --noconfirm libolm
                info "libolm installé"
            fi
            ;;
        *)
            cat <<EOF
${_RED}Distro Linux non reconnue : installe libolm manuellement.${_RESET}
Nerve (E2EE) a besoin de libolm. Réfère-toi aux instructions de la matrice
de build de matrix-org/olm :
  https://github.com/matrix-org/olm
Puis relance ce script (ou installe nerve par une autre méthode).
EOF
            exit 1
            ;;
    esac
fi

# ---------------------------------------------------------------------------
# 4. pipx (ou uv si déjà présent)
# ---------------------------------------------------------------------------
step "Vérification de pipx / uv"

# pipx installe les scripts dans ~/.local/bin (ajouté au PATH via ensurepath).
# On le préfixe dès maintenant pour trouver nerve juste après l'installation.
LOCAL_BIN="$HOME/.local/bin"
PATH="$LOCAL_BIN:$PATH"
export PATH

INSTALLER=""
if command_exists uv; then
    INSTALLER="uv"
    info "uv détecté : utilisation de 'uv tool install' (plus rapide)"
elif command_exists pipx; then
    INSTALLER="pipx"
    info "pipx déjà présent : OK"
else
    INSTALLER="pipx"
    echo "  ${_YELLOW}Installation de pipx (python3 -m pip install --user pipx)…${_RESET}"
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath
    info "pipx installé"
fi

# ---------------------------------------------------------------------------
# 5. Installation de nerve
# ---------------------------------------------------------------------------
step "Installation de nerve"

install_nerve() {
    # NOTE publication PyPI : remplacer le git+https par `pipx install nerve`
    # (ou `uv tool install nerve`) une fois le paquet publié.
    if [ "$INSTALLER" = "uv" ]; then
        uv tool install "git+https://github.com/Nawal-alao/nerve.git"
    else
        pipx install "git+https://github.com/Nawal-alao/nerve.git"
    fi
}

if command_exists nerve; then
    info "nerve déjà installé : OK"
    NERVE_VERSION="$(nerve --version 2>/dev/null || echo unknown)"
    warn "nerve présent (version actuelle : $NERVE_VERSION) — pour le mettre à jour : pipx upgrade nerve (ou uv tool upgrade nerve)."
else
    install_nerve
    info "nerve installé"
fi

# ---------------------------------------------------------------------------
# 6. Message final
# ---------------------------------------------------------------------------
cat <<EOF

${_BOLD}Installation terminée.${_RESET}
  • Lance nerve avec :        ${_BOLD}nerve${_RESET}
  • Vérifie la version :      ${_BOLD}nerve --version${_RESET}
  • Config :                  ~/.config/nerve/
  • Si 'nerve' n'est pas trouvé, rouvre ton terminal (pipx a ajouté
    ~/.local/bin à ton PATH).

EOF
