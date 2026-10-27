from django.core.management.commands import makemessages


class Command(makemessages.Command):
    """makemessages without fuzzy matching.

    By default msgmerge pre-fills a new string with the translation of a
    similar old one and marks it fuzzy ("Closed on Profesia" got the text of
    "Closed on Profesia (%(date)s)"). Fuzzy entries are silently skipped when
    compiling, so a new string would show in English. Without the guess a new
    string arrives empty and test_catalog_is_complete_and_compiled flags it.
    """

    msgmerge_options = [*makemessages.Command.msgmerge_options, "--no-fuzzy-matching"]
