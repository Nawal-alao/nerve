# Changelog

Toutes les modifications notables de nerve. Le format suit
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), et le versionnage
respecte [SemVer](https://semver.org/).

## [Unreleased]

En préparation de la 1.0.0.

### Added
- **Timeline conversationnelle groupée** : les messages consécutifs du même
  expéditeur sont regroupés en blocs avec un seul indicateur `› Vous` /
  `‹ Nom` (au lieu d'un nom répété à chaque ligne, façon journal système). Un
  séparateur temporel (`HH:MM ────`) apparaît après ~5 min de silence. Le
  rendu est calculé au moment de l'affichage à partir d'entrées structurées,
  ce qui permet un re-rendu cohérent à l'ouverture d'un salon.
- Reconnexion automatique avec backoff exponentiel (1s → 30s) sur panne réseau :
  l'app se re-synchronise toute seule au lieu de rester "off-line". Nouvel état
  `reconnecting…` dans le header et la sidebar.
- Complétion par `Tab` pour les suggestions fuzzy (commandes slash, mentions
  `@user` / `#room`), en plus de `Enter`.
- Barré inline (`~~texte~~`) dans le rendu markdown.
- Tests d'intégration de la couche `NerveClient` (politique de sécurité à
  l'envoi, invites, typing, envoi d'images) en mockant `nio.AsyncClient`.
- Métadonnées PyPI complètes (licence, classifieurs, URLs, keywords) et
  vérification CI du contenu du wheel (`app.tcss` présent).

### Fixed
- `app.tcss` est désormais embarqué dans le paquet (`setuptools.package-data`) :
  le fichier ne disparaît plus après `pip install`.
- L'installateur utilise le gestionnaire de paquets pour `pipx`
  (`sudo apt install -y pipx` sur les distros PEP 668) au lieu de `pip
  install --user` qui casse sur Debian 11+ / Ubuntu 23.04+.
- Les mentions `@user` excluent désormais l'utilisateur courant.
- Le badge de non-lu est plafonné à `99+` au lieu d'un nombre qui déborde.

## [0.2.0] - 2026-09

### Added
- Indicateurs de frappe (`typing…`) dans la timeline.
- Splash animé avec logo ASCII fixe (plus de dépendance `pyfiglet`).
- Command palette repensée (en-têtes de section, badges).
- Suppression du runtime web (migration en cours vers Rust/ratatui).

### Fixed
- `_handle_typing` est désormais async (correspond à `TypingHandler`) : les
  événements de frappe ne lèvent plus de `TypeError`.
- Les timers d'intervalle du statut sont arrêtés au unmount (plus de leak).
- Palette : utilisation du token de couleur pour les en-têtes de section.

## [0.1.0] - 2026

### Added
- Login Matrix + boucle de sync continue.
- Liste de salons, timeline en direct, envoi de messages.
- Chiffrement E2EE (réception/déchiffrement).
- Vérification d'appareil par emoji (SAS) avec confirmation humaine.
- Blocage d'envoi vers des appareils non vérifiés en salon chiffré.
- Confirmation humaine des invitations.
- Token d'accès stocké dans le trousseau système.
- Store E2EE chiffré au repos (Fernet, clé dans le trousseau) + clé de
  récupération de session (`/recovery`).
- Command palette, déconnexion propre (révocation du token).
