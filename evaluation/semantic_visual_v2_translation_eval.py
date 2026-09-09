#!/usr/bin/env python3
"""V2.2: ellipsis, prolonged-mark and wave runs collapse to one mark.
Short point runs retain their original distinction; kana and line semantics stay separate.
"""

from __future__ import annotations

import re

from semantic_visual_v2_eval import normalize_v2_semantic_eval


EVALUATION_POLICY = "v2.2_translation_semantic_lines_eval_20260910"
APPLICATION_CONTRACT = "Visible, idempotent canonical text; ellipsis is U+2026."
_EXCLAMATION_QUESTION_RUN = re.compile(r"[!?]{2,}")
_ELLIPSIS_DOT_RUN = re.compile(r"・+")
_ELLIPSIS_DOT_TOKEN = "\ue000"


def normalize_exclamation_question_runs_from_v2(text: str) -> str:
    """Collapse expressive !/? counts while retaining type and first order."""

    def replace(match: re.Match[str]) -> str:
        value = match.group(0)
        has_exclamation = "!" in value
        has_question = "?" in value
        if has_exclamation and has_question:
            return "!?" if value.index("!") < value.index("?") else "?!"
        return value[0] * 2

    return _EXCLAMATION_QUESTION_RUN.sub(replace, text)


def normalize_ellipsis_runs_from_v2(text: str) -> str:
    """Collapse three or more centered dots to one ellipsis."""
    return re.sub(r"・{3,}", "…", text)


def normalize_v2_translation_eval(text: str) -> str:
    """Return the idempotent canonical scoring key, including inherited v2 rules."""
    normalized = normalize_v2_semantic_eval(text)
    normalized = normalize_exclamation_question_runs_from_v2(normalized)
    return normalize_ellipsis_runs_from_v2(normalized)


def render_translation_normalized(text: str) -> str:
    """Render a canonical scoring key as visible middle-dot punctuation."""

    return text.replace(_ELLIPSIS_DOT_TOKEN, "・")


def normalize_v2_translation_display(text: str) -> str:
    """Return visible normalized text for translation or presentation."""

    return render_translation_normalized(normalize_v2_translation_eval(text))


def normalize_pair(reference: str, prediction: str) -> tuple[str, str]:
    return normalize_v2_translation_eval(reference), normalize_v2_translation_eval(prediction)
