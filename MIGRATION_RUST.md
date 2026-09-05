# Migration shelltrix → Rust

Plan complet de migration de l'actuel client Matrix TUI en **Python/Textual**
vers une version **Rust/ratatui**, développée sur la branche `feature/rust`.

Objectif : **parité de fonctionnalités avec le Python actuel**, puis dépassement
grâce aux atouts exploitables par `matrix-sdk` (cross-signing, E2EE natif,
sync robuste). La version Python reste opérationnelle et la référence
fonctionnelle pendant toute la migration (côté à côte sur deux branches).

---

## 1. Rapide panorama — état actuel (Python)

| Composant | Module Python | Rôle |
|---|---|---|
| Bootstrap | `shelltrix/app.py` | MatuiApp, routage splash → login → chat, boucle d'app |
| Config | `shelltrix/config.py` | chemins, clés `config.json`, chiffrement du store (Fernet), clé de récupération |
| Comptes multi | `shelltrix/accounts.py` | `accounts.json` + tokens dans le keyring système |
| Couche Matrix | `shelltrix/matrix_client.py` | wrapper sur `matrix-nio` : login, sync, envoi, SAS, upload |
| Écrans | `screens/{login,splash,chat,account_picker}.py` | UI textuelle |
| Dialogues | `dialogs/{invite,join_room,recovery,store_unlock,sas,command_palette}.py` | dialogs modaux |
| Sidebar | `shelltrix/sidebar.py` | panneau contextuel droit |
| Formatage | `shelltrix/formatting.py` | couleurs par émetteur, markdown inline, regex URL |
| Thèmes | `shelltrix/themes.py` | tokens de couleur (opencode / matrix_green) |
| Images | `shelltrix/image_renderer.py` | Kitty / Sixel / placeholder |
| Notifications | `shelltrix/notifications.py` | `notify-send` |
| Widgets | `shelltrix/widgets.py` | helpers UI (figlet-like banner, …) |

~3 900 lignes de Python / 7 modules de tests.

---

## 2. Stack Rust cible

| Besoin | Crate | Remplace |
|---|---|---|
| Client Matrix + E2EE | `matrix-sdk` (+ feature `e2e-encryption`, events) | `matrix-nio` |
| Store E2EE/meta | `matrix-sdk` + `matrix-sdk-sqlite` (backing store SQLite) | store Python + Fernet |
| TUI | `ratatui` | Textual |
| Backend terminal | `crossterm` | (inclus dans Textual) |
| Async runtime | `tokio` | `asyncio` |
| Effets / animations | `tachyonfx` (optionnel, splash) | animate Textual |
| Sérialisation | `serde` + `serde_json` | JSON stdlib |
| Keyring | `keyring` (crate) | keyring Python |
| Chiffrement store | `chacha20poly1305` + `secrecy` | Fernet (cryptography) |
| Clé de récupération | `argon2` (dérivation) + `zeroize` | scrypt verifier |
| Notifications | `notify-rust` (dbus/libnotify) | sous-process `notify-send` |
| Images | `image` (décodage) + échappements natifs Kitty/Sixel | `requests` + formatage |
| Tests | `cargo test`, `criterion` (perf) | `pytest` |

Consignes Rust globales :
- **Aucune couleur en dur** : tout passe par un module `theme` (tokens), équivalent de `themes.py`.
- Pas de réécriture UI « greenfield » : on **porte composant par composant** avec la **même UX**.
- Toute étape est mergée par petite **PR isolée** (fmt + clippy + tests verts).

---

## 3. Architecture cible

```
crates /
  shelltrix/                       # binaire principal
    src/
      main.rs                  # bootstrap terminal, runtime tokio, App
      app.rs                   # état global de l'app (équivalent app.py)
      config.rs                # config.json, chemins, store chiffré (ex-CLI)
      accounts.rs              # multi-comptes + keyring
      theme.rs                 # tokens de couleur (spec(), accent(), danger()…)
      formatting.rs            # couleurs émetteur, markdown inline, URLs
      notify.rs                # notifications desktop (notify-rust)
      image.rs                 # rendu inline (Kitty / Sixel / placeholder)
      matrix/
        mod.rs
        client.rs              # wrapper matrix-sdk (équivalent matrix_client.py)
        store.rs               # SQLite + chiffrement au repos + clé de récupération
        verification.rs        # SAS/emoji + cross-signing
      ui/
        mod.rs
        app_area.rs            # layout global (header / rooms / timeline / composer / sidebar)
        login.rs                # écran login
        splash.rs              # bannière ASCII animée
        chat.rs                # timeline + composer + suggestions /commandes/@mentions
        room_list.rs           # liste des salons (tri unread, active)
        sidebar.rs             # contexte de la salle (équivalent sidebar.py)
        account_picker.rs      # picker de compte
        dialogs/
          invite.rs
          join_room.rs
          recovery.rs
          store_unlock.rs
          sas.rs
          command_palette.rs
        widgets/
          textarea.rs          # zone de saisie multi-ligne
          autocomplete.rs      # suggestions fzf-like
          statusbar.rs
    tests/
      unit/                    # tests unitaires par module
      integration/             # tests end-to-end (login/sync mockés)
```

Découplage obligatoire : **l'UI ne touche jamais `matrix-sdk`** — uniquement
via le wrapper `matrix::client` (même règle qu'actuellement avec `nio`).
Ça garantit la testabilité (un trait `Client` mockable pour les tests UI).

---

## 4. Phases de migration (ordre = dépendances)

Chaque phase se termine par : cargo fmt + clippy sans warning + tests verts +
une **PR** et une **démo manuelle**. Les phases 1-3 constituent le **POC** qui
débloque la suite.

### Phase 0 — Bootstrap du projet Rust
- `cargo init` (workspace `crates/`), édition 2021+.
- CI GitHub Actions : `cargo fmt --check`, `cargo clippy -D warnings`, `cargo test`.
- Dépôt des crates de base (`ratatui`, `crossterm`, `tokio`), squelette « hello TUI » (fenêtre + texte).
- **Sortie :** `cargo run` affiche une fenêtre vide qui répond au redimensionnement et à `q` pour quitter.

### Phase 1 — POC : login + sync + room list
- `config.rs` (chemins `~/.config/shelltrix`), `accounts.rs` + `keyring`.
- `matrix/client.rs` : login par mot de passe → token + device_id.
- Boucle `sync` (`Client::sync_stream`) + cache SQLite (`matrix-sdk-sqlite`).
- `ui/login.rs` (saisie homeserver/user/password) + `ui/room_list.rs` (noms de salons, badges unread).
- **Sortie :** on se connecte, on voit la liste des salons, triée (unread en premier).

### Phase 2 — Timeline + composer + envoi
- `ui/chat.rs` : timeline (`Paragraph`/liste virtuelle) avec timestamps, couleurs par émetteur (`formatting.rs`), messages persistés localement.
- `ui/widgets/textarea.rs` : zone de saisie multi-ligne (copie du composant Textual).
- Envoi `m.text` ; affichage des erreurs d'envoi (appareils non vérifiés → blocage + avertissement, **même politique que Python**).
- **Sortie :** on écrit dans une salle, on voit le message (le mien + celui des autres en direct via sync).

### Phase 3 — E2EE complet (cœur de la valeur)
- Activer `e2e-encryption` de `matrix-sdk` ; store `matrix-sdk-sqlite`.
- **Chiffrement au repos** : clé du store dérivée puis stockée crypto d'un **keyring** ; sinon **clé de récupération** (`/recovery` = secret de partage, verifier `argon2` stocké seul) — équivalent exact du Python (Fernet + scrypt).
- `ui/dialogs/store_unlock.rs` (déverrouillage à l'ouverture si clé au repo absent).
- **Sortie :** messages chiffrés lisibles, clé de récupération exportable et restaurable sur une **autre machine**/nouveau keyring.

### Phase 4 — Invitations + vérification par emoji (SAS) + cross-signing
- `ui/dialogs/invite.rs` : **jamais** de rejoin auto — dialogue `Accept / Decline`.
- `matrix/verification.rs` : SAS par emoji avec **confirmation humaine explicite** (jamais auto-confirmé), refus distinct, annulation.
- Bonus natif `matrix-sdk` : **cross-signing** des appareils (supérieur au Python).
- **Sortie :** on compare les emojis à l'écran, on valide un appareil ; les salons chiffrés ne bloquent plus l'envoi une fois valide.

### Phase 5 — Commandes slash + palette + autocomplétion
- Commandes complètes : `/help`, `/me`, `/react`, `/join`, `/sendimg`, `/quit`, `/recovery`, `/theme`.
- `ui/dialogs/command_palette.rs` : équivalent `Ctrl+P` (sections non sélectionnables, badge de catégorie, raccourcis).
- Suggestions **fzf-like** au slash `/` + complétion `@mentions` et rooms.
- **Sortie :** 100 % des commandes actuelles fonctionnent, palette et autocomplétion portées.

### Phase 6 — Splash, thèmes, sidebar, confort
- `ui/splash.rs` : bloc ASCII `SHELLTRIX` fixe + révélation colonne par colonne + tagline typée (`tachyonfx` ou timers custom, **mêmes cadeaux**). Skip via `enter`/`esc`, auto after ~3s.
- `theme.rs` : tokens `opencode` / `matrix_green`, bascule `/theme`, persistance `config.json`.
- `ui/sidebar.rs` : nom/alias, topic, compteurs (joined/invited), état E2EE, power level, état de sync + `next_batch`, âge du refresh.
- `ui/widgets/statusbar.rs` : salle active, indicateur sync (offline/syncing…/online), horloge.
- **Sortie :** l'app a l'air et se comporte comme la version Python.

### Phase 7 — Images inline + markdown
- `image.rs` : détection terminal (Kitty/Sixel/aucun), téléchargement `mxc://` cache, rendu.
- Markdown inline (gras, italique, code) en rendu Rich-like (`tui-markdown` si pertinent).
- **Sortie :** rendre les `m.image` et le markdown identique au Python.

### Phase 8 — Notifications, multi-comptes, packaging
- `notify.rs` : notifications desktop quand salle inactive + config `notifications_enabled`.
- Multi-compte : `account_picker.rs` à l'écran d'accueil, commutation propre (un client par compte).
- **Packaging** : single binaire statique ; `Makefile`/scripts build ; tests de non-régression des `config.json`/schema (compat lecture du Python).
- **Sortie :** feature parity complète, install triviale.

### Phase 9 — Durcissement, conformité, bascule
- Runbook : **parité systématique** (voir §5) : chaque écart est un bug ou une amélioration explicitement décidée.
- Fuzz/perf : `criterion` sur sync + rendu ; test long (10k messages) sans fuite.
- Documentation (README), mise à jour du pictogramme install/installer, versioning `0.3.0` Rust.
- **Bascule** : merger `feature/rust` → branche principale, conserver la branche Python en archive (compat migration).

---

## 5. Matrice de parité (cible de fin de Phase 8)

| Fonctionnalité | Python actuel | Rust cible |
|---|---|---|
| Login + sync loop | ✅ | ✅ |
| Room list triée (unread) | ✅ | ✅ |
| Timeline live + envoi | ✅ | ✅ |
| E2EE (déchiffrement/envoi chiffré) | ✅ | ✅ |
| Chiffrement du store au repos | ✅ (Fernet) | ✅ (chacha20poly1305) |
| Clé de récupération `/recovery` | ✅ | ✅ |
| Store unlock au démarrage | ✅ | ✅ |
| Invites à confirmation humaine | ✅ | ✅ |
| Vérif SAS emoji (humain) | ✅ | ✅ |
| Cross-signing | ❌ (impossible via nio) | ✅ (bonus) |
| Commandes slash + help | ✅ | ✅ |
| Palette `Ctrl+P` | ✅ | ✅ |
| Autocomplétion `/` et `@` | ✅ | ✅ |
| Splash animé | ✅ | ✅ |
| Thèmes (2) + bascule | ✅ | ✅ |
| Sidebar contexte | ✅ | ✅ |
| Images inline (Kitty/Sixel) | ✅ | ✅ |
| Notifications desktop | ✅ | ✅ |
| Multi-comptes | ✅ | ✅ |

---

## 6. Risques & mitigations

| Risque | Probabilité | Mitigation |
|---|---|---|
| Scope explosion (« rewrite trap ») | Élevée | POC court (phases 1-3) validé avant toute suite ; chaque phase = PR isolée |
| Difformité UX (ratatui ≠ Textual) | Moyenne | S'appuyer sur mêmes wireframes/écrans ; review visuelle phase par phase |
| Complexité E2EE (état de session) | Moyenne | `matrix-sdk` gère le store natif (SQLite) — pas de re-implantation |
| Dérive de la perf (grosse timeline) | Faible | rendu virtuel + benchmark `criterion` Phase 9 |
| Maintenance de deux codebases | Élevée | **Aucune feature ajoutée au Python pendant la migration** ; le Python est figé (référence) |
| Clé de récupération incompatible | Faible | exporter/importer le secret via la valeur brute ; schéma `recovery.json` versionné |

---

## 7. Marche à suivre git

- Branche de travail : `feature/rust` (créée).
- Règles : `main` = version stable Python **figée** ; worktree Rust isolé.
- Une PR par phase, format rigoriste : `cargo fmt --check` + `cargo clippy -- -D warnings` + `cargo test`.
- Versioning : `shelltrix 0.3.x` (Rust) reprend le numéro après la migration complète.

---

## 8. Première étape immédiate (prochaine action)

1. `cargo init` du workspace dans `/home/nawalalao/shelltrix` (ou sous-dossier `rust/`).
2. Ajouter `ratatui`, `crossterm`, `tokio`.
3. « Hello TUI » : fenêtre + `q` pour quitter → **valide la Phase 0**.

Lancer dès maintenant si tu le confirmes.