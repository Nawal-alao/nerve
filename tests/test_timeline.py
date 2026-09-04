"""Tests pour le rendu de la timeline conversationnelle (groupage par
expéditeur + séparateurs temporels).

Cible la logique pure `format_timeline_entries` / `interval_time_gap` de
`neurite.formatting`, sans état Textual.
"""

from __future__ import annotations

from neurite.formatting import (
    TIME_GAP_SEPARATOR_MS,
    TimelineContext,
    TimelineEntry,
    body_mentions_user,
    format_timeline_entries,
    highlight_mentions,
    interval_time_gap,
)


def entry(
    sender: str,
    body: str,
    *,
    is_own: bool = False,
    time_ms: int = 0,
    name: str | None = None,
) -> TimelineEntry:
    return TimelineEntry(
        sender=sender,
        display_name=name or sender,
        is_own=is_own,
        time_ms=time_ms,
        body=body,
        timestamp="HH:MM",
    )


def head(e: TimelineEntry) -> str:
    return f"HEAD({'<me>' if e.is_own else e.sender})"


def render(entries, ctx: TimelineContext | None = None) -> tuple[list[str], TimelineContext]:
    lines, new_ctx = format_timeline_entries(
        entries, ctx or TimelineContext(), header_for=head
    )
    return lines, new_ctx


class TestIntervalTimeGap:
    def test_below_threshold_no_separator(self) -> None:
        assert interval_time_gap(0, TIME_GAP_SEPARATOR_MS - 1) is False

    def test_at_threshold_separates(self) -> None:
        assert interval_time_gap(0, TIME_GAP_SEPARATOR_MS) is True

    def test_well_beyond_separates(self) -> None:
        assert interval_time_gap(0, TIME_GAP_SEPARATOR_MS * 10) is True


class TestFormatTimelineEntries:
    def test_single_entry_opens_block(self) -> None:
        lines, ctx = render([entry("@a:hs", "hi")])
        assert lines == ["        HEAD(@a:hs)", "        hi"]
        assert ctx.last_sender == "@a:hs"

    def test_same_sender_continuation(self) -> None:
        """Deux messages consécutifs du même expéditeur → un seul bloc."""
        lines, ctx = render(
            [entry("@a:hs", "one"), entry("@a:hs", "two")]
        )
        assert lines == [
            "        HEAD(@a:hs)",
            "        one",
            "        two",
        ]

    def test_different_sender_new_block(self) -> None:
        lines, _ = render(
            [entry("@a:hs", "one"), entry("@b:hs", "two")]
        )
        # Un header par expéditeur ; aucun nom répété sur les lignes de corps
        assert lines == [
            "        HEAD(@a:hs)",
            "        one",
            "        HEAD(@b:hs)",
            "        two",
        ]

    def test_same_sender_time_gap_separator(self) -> None:
        """Silence > 5 min → séparateur temporel + nouveau bloc."""
        t0 = 1_700_000_000_000
        entries = [
            entry("@a:hs", "before", time_ms=t0),
            entry("@a:hs", "later", time_ms=t0 + TIME_GAP_SEPARATOR_MS + 1),
        ]
        lines, _ = render(entries)
        # Un séparateur temporel apparaît avant le message suivant
        sep_lines = [ln for ln in lines if "─" in ln]
        assert sep_lines, "séparateur temporel manquant"
        # ... puis un nouveau header de bloc pour le même expéditeur
        assert lines[-2] == "        HEAD(@a:hs)"
        assert lines[-1] == "        later"

    def test_sender_returns_after_another_opens_new_block(self) -> None:
        """A, B, A : le retour de A ouvre un nouveau bloc."""
        lines, _ = render(
            [
                entry("@a:hs", "1"),
                entry("@b:hs", "2"),
                entry("@a:hs", "3"),
            ]
        )
        a_headers = [ln for ln in lines if ln.endswith("HEAD(@a:hs)")]
        assert len(a_headers) == 2
        assert lines[-1] == "        3"

    def test_own_message_indicator(self) -> None:
        lines, _ = render([entry("@me:hs", "salut", is_own=True)])
        assert lines[0] == "        HEAD(<me>)"

    def test_continues_existing_context(self) -> None:
        """Le rendu incrémental repart du contexte fourni."""
        ctx = TimelineContext(last_sender="@a:hs", last_time_ms=100)
        lines, new_ctx = render([entry("@a:hs", "more", time_ms=100)], ctx=ctx)
        # Continuation : pas de nouveau header
        assert lines == ["        more"]
        assert new_ctx.last_sender == "@a:hs"

    def test_category_separator_resets_group(self) -> None:
        """Un changement d'expéditeur après un retour crée un header."""
        ctx = TimelineContext(last_sender="@b:hs", last_time_ms=100)
        lines, _ = render([entry("@a:hs", "new", time_ms=100)], ctx=ctx)
        assert lines[0] == "        HEAD(@a:hs)"


class TestBodyMentionsUser:
    """Tests pour body_mentions_user()."""

    def test_matches_full_user_id(self) -> None:
        assert body_mentions_user("regarde @alice:matrix.org stp", "@alice:matrix.org")

    def test_matches_localpart(self) -> None:
        assert body_mentions_user("hé @alice tu peux ?", "@alice:matrix.org")

    def test_no_mention(self) -> None:
        assert not body_mentions_user("salut tout le monde", "@alice:matrix.org")

    def test_empty_body(self) -> None:
        assert not body_mentions_user("", "@alice:matrix.org")

    def test_empty_user_id(self) -> None:
        assert not body_mentions_user("salut @alice", "")

    def test_similar_partial_name_not_mentioned(self) -> None:
        assert not body_mentions_user("parle à Alice en général", "@alice:matrix.org")


class TestHighlightMentions:
    """Tests pour highlight_mentions() : mise en évidence des mentions."""

    @staticmethod
    def _accent() -> str:
        from neurite import themes

        return themes.accent()

    def test_full_user_id_highlighted(self) -> None:
        a = self._accent()
        out = highlight_mentions("bonjour @alice:matrix.org !", "@alice:matrix.org")
        assert f"[bold][{a}]@alice:matrix.org[/{a}][/bold]" in out

    def test_localpart_highlighted(self) -> None:
        a = self._accent()
        out = highlight_mentions("hé @alice tu peux ?", "@alice:matrix.org")
        assert f"[bold][{a}]@alice[/{a}][/bold]" in out

    def test_ignored_when_no_user_id(self) -> None:
        assert highlight_mentions("@alice", "") == "@alice"

    def test_ignored_when_no_mention(self) -> None:
        assert highlight_mentions("juste du texte", "@alice:matrix.org") == "juste du texte"

    def test_partial_name_not_highlighted(self) -> None:
        a = self._accent()
        out = highlight_mentions("@alice2 vient", "@alice:matrix.org")
        assert "@alice2" in out
        assert f"[{a}]@alice2" not in out

    def test_other_server_not_highlighted(self) -> None:
        a = self._accent()
        out = highlight_mentions("@alice:autreserveur ici", "@alice:matrix.org")
        assert f"[{a}]@alice:autreserveur" not in out
        assert "@alice:autreserveur" in out
