# Notes techniques (refactor 13 étapes)

Documentation des adaptations *mécaniques* nécessaires au découpage de
`app.py`, sans changement de comportement. Si un bug est repéré en passant,
il est noté ici et traité séparément — jamais corrigé pendant le refactor.

## Adaptations imposées par le découpage

### 1. Couleurs markup `ACCENT` / `DANGER` (globals mutables)
À l'origine : `app.py` définit `ACCENT` et `DANGER`, rebondus à la volée par
`_apply_theme_globals()` (appel à l'import du module, dans `MatuiApp.__init__`
et à chaque `cycle_theme`). Leurs consommateurs vivaient dans le même module :
une réaffectation `global ACCENT` était donc vue partout.

Après extraction, les consommateurs (ChatScreen, RecoveryDialog, SasDialog,
InviteDialog) sont dans d'autres modules. Un `from ..app import ACCENT` par
module serait *statique* : la réaffectation dans `app.py` ne se propagerait
plus (bug de thème non rafraîchi). La structure interdit les imports
circulaires `screens|dialogs → app`.

⇒ Adaptation : ces call sites lisent désormais la valeur vivante
`themes.accent()` / `themes.danger()` au moment du rendu. C'est strictement
équivalent à l'ancien `ACCENT` : l'invariant `ACCENT == themes.accent()`
(et idem `DANGER`) est maintenu par `_apply_theme_globals()` à l'import et à
chaque bascule de thème → aucune valeur observable ne change.

`ACCENT` / `DANGER` / `_apply_theme_globals()` restent dans `app.py` : ils
n'ont plus de consommateur mais `MatuiApp` continue de les maintenir.

### 2. `_URL_RE` (regex d'URL) — retiré de la liste initiale
`_URL_RE` est utilisé par `ChatScreen._handle_incoming_message`. Il n'est pas
dans la liste des fonctions de `formatting.py`, mais c'est une constante de
formatage de texte et `chat.py` ne peut pas l'importer depuis `app.py`
(circulaire). Il réside donc dans `formatting.py`.

### 3. Sorting `SENDER_COLORS` / `SYNC_LABELS`
- `SENDER_COLORS` : utilisé uniquement par `_sender_color` → `formatting.py`.
- `SYNC_LABELS` : utilisé uniquement par `ChatScreen` → `screens/chat.py`.

### 4. Imports différés pendant la migration (résolus)
Pendant le découpage, `CommandPalette`/`StoreUnlockDialog` appelaient
`ChatScreen`, `JoinRoomDialog`, `RecoveryDialog`, `LoginScreen` encore dans
`app.py` ; ils utilisaient des imports dans le corps de fonction pour éviter
tout retour vers `app.py`. Une fois chaque module extrait (étapes 5, 6, 11,
12), tous ces imports sont repassés en haut de module. `app.py` ne référence
que des modules "aval" (screens/, dialogs/, config/, matrix_client/) —
aucun cycle.

## Structure finale (src/shelltrix/)
- `app.py` : `MatuiApp`, `_apply_theme_globals`, globals `ACCENT`/`DANGER`
  (maintenus mais sans consommateur), `run()`.
- `formatting.py`, `sidebar.py`, `widgets.py` : helpers bas niveau, ne
  dépendent que de `themes` (+ stdlib/rich).
- `screens/{login,chat,splash}.py`, `dialogs/{command_palette,join_room,
  recovery,store_unlock,sas,invite}.py` : écrans et dialogues.

## Bugs repérés pendant le refactor (à traiter séparément)
- (aucun pour l'instant)