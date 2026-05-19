#!/usr/bin/env bash
# Papyrus setup — idempotent installer.
# Creates a Python venv, installs deps, downloads epubcheck, and writes .papyrus.env.
# With --persistent, also registers papyrus with Claude Code so it loads in
# every session without --plugin-dir.
# Safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

EPUBCHECK_VERSION="5.1.0"
EPUBCHECK_URL="https://github.com/w3c/epubcheck/releases/download/v${EPUBCHECK_VERSION}/epubcheck-${EPUBCHECK_VERSION}.zip"

PERSISTENT=0
for arg in "$@"; do
  case "$arg" in
    --persistent) PERSISTENT=1 ;;
    -h|--help)
      cat <<EOF
Usage: ./setup.sh [--persistent]

  --persistent   Register papyrus with Claude Code (user scope) so it loads
                 in every session — no more 'claude --plugin-dir' needed.
                 Requires the 'claude' CLI on PATH.
EOF
      exit 0
      ;;
    *)
      echo "setup.sh: unknown argument '$arg' (use --help)" >&2
      exit 2
      ;;
  esac
done

c_red()   { printf '\033[31m%s\033[0m\n' "$*"; }
c_grn()   { printf '\033[32m%s\033[0m\n' "$*"; }
c_yel()   { printf '\033[33m%s\033[0m\n' "$*"; }
c_blue()  { printf '\033[34m%s\033[0m\n' "$*"; }

step() { c_blue "==> $*"; }
ok()   { c_grn "    ok: $*"; }
warn() { c_yel "    warn: $*"; }
fail() { c_red "    fail: $*"; exit 1; }

OS="$(uname -s)"
case "$OS" in
  Darwin) PKG_MGR="brew" ;;
  Linux)  PKG_MGR="apt"  ;;
  *)      PKG_MGR=""     ;;
esac

step "Checking prerequisites"
command -v python3 >/dev/null 2>&1 || fail "python3 not found on PATH"
command -v curl    >/dev/null 2>&1 || fail "curl not found on PATH"
command -v unzip   >/dev/null 2>&1 || fail "unzip not found on PATH"

PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION##*.}"
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  fail "python3 >= 3.10 required (found $PY_VERSION)"
fi
ok "python3 $PY_VERSION"

step "Creating Python venv (.venv/)"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  ok "created .venv"
else
  ok ".venv already exists"
fi

step "Installing Python dependencies"
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt
ok "requirements.txt installed"

install_dep() {
  local name="$1" check="$2" brew_pkg="$3" apt_pkg="$4" brew_kind="${5:-formula}"
  # $check is a shell expression that exits 0 iff the dep is functional.
  if eval "$check" >/dev/null 2>&1; then
    ok "$name present"
    return
  fi
  case "$PKG_MGR" in
    brew)
      if [ "$brew_kind" = "cask" ]; then
        warn "$name not found; installing via brew cask ($brew_pkg)"
        brew install --cask "$brew_pkg" >/dev/null
      else
        warn "$name not found; installing via brew ($brew_pkg)"
        brew install "$brew_pkg" >/dev/null
      fi
      ok "$name installed"
      ;;
    apt)
      warn "$name not found; installing via apt ($apt_pkg)"
      sudo apt-get update -qq
      sudo apt-get install -y -qq "$apt_pkg"
      ok "$name installed"
      ;;
    *)
      fail "$name not found and no supported package manager (install $name manually)"
      ;;
  esac
}

step "Checking system dependencies"
# pandoc: `command -v pandoc` is enough — no stub problem.
install_dep "pandoc" "command -v pandoc" pandoc pandoc
# java: `command -v java` returns true even for the macOS stub that prompts you
# to install a JRE. Use `java -version` to confirm a real runtime is reachable.
install_dep "java"   "java -version"     temurin  default-jre  cask

# cairo (needed by cairosvg). On macOS brew installs libcairo as 'cairo'.
case "$OS" in
  Darwin)
    if ! brew list cairo >/dev/null 2>&1; then
      warn "cairo not found; installing via brew"
      brew install cairo >/dev/null
      ok "cairo installed"
    else
      ok "cairo present"
    fi
    ;;
  Linux)
    if ! dpkg -s libcairo2 >/dev/null 2>&1; then
      warn "libcairo2 not found; installing via apt"
      sudo apt-get install -y -qq libcairo2
      ok "libcairo2 installed"
    else
      ok "libcairo2 present"
    fi
    ;;
esac

# Optional: notifier
step "Checking notification tooling (optional)"
case "$OS" in
  Darwin)
    if command -v terminal-notifier >/dev/null 2>&1; then
      ok "terminal-notifier present"
    elif [ "$PKG_MGR" = "brew" ]; then
      warn "terminal-notifier not found; installing via brew"
      brew install terminal-notifier >/dev/null || warn "terminal-notifier install failed (notifications will no-op)"
    fi
    ;;
  Linux)
    if command -v notify-send >/dev/null 2>&1; then
      ok "notify-send present"
    else
      warn "notify-send not found (notifications will no-op)"
    fi
    ;;
esac

step "Installing epubcheck"
mkdir -p .tools
EPUBCHECK_DIR=".tools/epubcheck-${EPUBCHECK_VERSION}"
EPUBCHECK_JAR_PATH="${HERE}/${EPUBCHECK_DIR}/epubcheck.jar"
if [ -f "$EPUBCHECK_JAR_PATH" ]; then
  ok "epubcheck $EPUBCHECK_VERSION already present"
else
  warn "downloading epubcheck $EPUBCHECK_VERSION"
  TMP_ZIP="$(mktemp -t epubcheck.XXXXXX.zip)"
  curl -sSL "$EPUBCHECK_URL" -o "$TMP_ZIP"
  unzip -q -o "$TMP_ZIP" -d .tools
  rm -f "$TMP_ZIP"
  if [ ! -f "$EPUBCHECK_JAR_PATH" ]; then
    fail "epubcheck.jar not found after extraction"
  fi
  ok "epubcheck installed at $EPUBCHECK_JAR_PATH"
fi

step "Writing .papyrus.env"
cat > .papyrus.env <<EOF
# Generated by setup.sh — re-run setup.sh to refresh.
EPUBCHECK_JAR="${EPUBCHECK_JAR_PATH}"
PAPYRUS_ROOT="${HERE}"
PAPYRUS_PYTHON="${HERE}/.venv/bin/python"
EOF
ok "wrote .papyrus.env"

step "Making scripts executable"
chmod +x bin/papyrus-python setup.sh
find scripts -name '*.py' -exec chmod +x {} \; 2>/dev/null || true
ok "permissions set"

step "Running doctor"
if ./bin/papyrus-python scripts/doctor.py; then
  ok "doctor passed"
else
  warn "doctor reported issues (see above)"
fi

if [ "$PERSISTENT" -eq 1 ]; then
  step "Registering papyrus with Claude Code (--persistent)"
  if ! command -v claude >/dev/null 2>&1; then
    warn "'claude' CLI not on PATH — skipping persistent registration."
    warn "  Install Claude Code first, then re-run: ./setup.sh --persistent"
  else
    # marketplace add and plugin install are both idempotent and exit 0 on no-op.
    if claude plugin marketplace add "$HERE" >/dev/null 2>&1; then
      ok "marketplace 'papyrus' registered (user scope)"
    else
      warn "marketplace add failed; trying to continue"
    fi
    if claude plugin install papyrus@papyrus --scope user >/dev/null 2>&1; then
      ok "plugin papyrus@papyrus installed (user scope)"
    else
      warn "plugin install failed; you may need to run it manually:"
      warn "  claude plugin install papyrus@papyrus --scope user"
    fi
  fi
fi

echo
c_grn "Papyrus setup complete."
echo
if [ "$PERSISTENT" -eq 1 ]; then
  echo "Papyrus is registered persistently — just run 'claude' anywhere."
  echo "To uninstall later:"
  echo "  claude plugin uninstall papyrus@papyrus"
  echo "  claude plugin marketplace remove papyrus"
else
  echo "Next: register the plugin with Claude Code."
  echo "  Ad-hoc (current session only):"
  echo "    claude --plugin-dir \"$HERE\""
  echo "  Persistent (every session):"
  echo "    ./setup.sh --persistent"
fi
echo
echo "Try it out:"
echo "  /papyrus:arxiv-fetch 2401.12345"
echo "  /papyrus:arxiv-to-epub 2401.12345 --name my-first-book"
