# Changelog

Toutes les modifications notables de shelltrix. Le format suit
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
- **Historique serveur / scrollback** : à l'ouverture d'un salon, shelltrix
  charge les messages les plus récents depuis le serveur, puis remonte dans
  le passé à chaque remontée en haut de la timeline (`PageUp`). Les
  doublons (messages déjà reçus par sync) sont dédupliqués par `event_id`,
  la position de défilement est préservée, et `Ctrl+K` efface le salon.
- **Modèle de message structuré complet** : chaque entrée de timeline porte
  désormais `event_id`, `msgtype` et `has_mention` (détection de `@user`) en
  plus de l'expéditeur/date/heure. C'est la fondation pour la pagination,
  la recherche, les mentions et la persistance.
- **Mentions directes mises en évidence** : un message vous mentionnant
  (`@vous` ou `@vous:serveur`) voit sa mention affichée en gras et en couleur
  d'accent dans la timeline, et le salon affiche un indicateur `@` distinct
  dans la liste des salons tant que la mention n'est pas lue (les
  notifications desktop sont alors préfixées `@Mention ·`). Détection sûre,
  sans faux positifs (`@bob2`, `@bob:autre`).
- **Cache SQLite local** : les messages reçus (sync + scrollback) sont
  persistés par salon et par compte dans `~/.config/shelltrix/cache/` (fichier en
  0600). À la réouverture d'un salon déjà vu, l'historique s'affiche
  instantanément depuis le cache avant même que le serveur ne réponde ; la
  re-déduplication par `event_id` évite les doublons. `Ctrl+K` purge aussi le
  cache du salon.
- **Recherche locale de messages** (`Ctrl+F`, `/search`, palette « Search
  messages ») : un modal de recherche parcourt l'historique en cache des
  salons, insensible à la casse, et affiche les correspondances (salon +
  extrait + heure). Sélectionner un résultat ouvre le salon et positionne la
  timeline sur le message.
- **Rendu d'images 100 % sûr pour Textual** : plus aucune séquence
  d'échappement écrite sur `stdout` (ce qui corrompait l'écran plein écran).
  L'image est décomposée en demi-blocs Unicode colorés (truecolor) écrits
  dans le RichLog ; fonctionne sur tout terminal 24 bits. Fallback simple
  `📷 Image` si Pillow est absent. Pillow devient une dépendance optionnelle
  (`shelltrix[image]`).
- Reconnexion automatique avec backoff exponentiel (1s → 30s) sur panne réseau :
  l'app se re-synchronise toute seule au lieu de rester "off-line". Nouvel état
  `reconnecting…` dans le header et la sidebar.
- Complétion par `Tab` pour les suggestions fuzzy (commandes slash, mentions
  `@user` / `#room`), en plus de `Enter`.
- Barré inline (`~~texte~~`) dans le rendu markdown.
- Tests d'intégration de la couche `ShelltrixClient` (politique de sécurité à
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
