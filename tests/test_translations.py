"""The committed catalogs are complete and the compiled .mo matches the .po.

The dev machine has no GNU gettext, so the .mo files are committed next to the
.po (docker/i18n.sh rebuilds both). A .po edited without recompiling would
silently show English; reading the .po here and asking gettext for every entry
catches that.
"""

import ast
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import translation

LOCALE_DIR = Path(settings.BASE_DIR) / "locale"


def read_po(path):
    """Entries of a .po file as dicts: msgid, msgstr, flags, plural (bool)."""
    entries, entry, field = [], None, None

    def finish():
        if entry is not None and "msgid" in entry:
            entries.append(entry)

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            finish()
            entry, field = None, None
            continue
        if entry is None:
            entry = {"flags": "", "plural": False}
        if line.startswith("#,"):
            entry["flags"] += line[2:]
        elif line.startswith("#"):
            continue
        elif line.startswith("msgid_plural"):
            entry["plural"] = True
            field = None
        elif line.startswith(("msgid ", "msgstr ")):
            field, _, value = line.partition(" ")
            entry[field] = ast.literal_eval(value)
        elif line.startswith("msgstr["):
            entry["plural"] = True
            field = None
        elif line.startswith('"') and field:
            entry[field] += ast.literal_eval(line)
    finish()
    return [e for e in entries if e["msgid"]]  # the header entry has an empty msgid


@pytest.mark.parametrize("language", ["sk", "ru"])
def test_catalog_is_complete_and_compiled(language):
    entries = read_po(LOCALE_DIR / language / "LC_MESSAGES" / "django.po")

    assert entries
    assert not [e["msgid"] for e in entries if "fuzzy" in e["flags"]]
    assert not [e["msgid"] for e in entries if e["plural"]]
    assert not [e["msgid"] for e in entries if not e.get("msgstr")]
    with translation.override(language):
        stale = [e["msgid"] for e in entries if translation.gettext(e["msgid"]) != e["msgstr"]]
    assert not stale, "recompile the catalog: docker/i18n.sh"
