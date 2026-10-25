from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = "Create the API token a user's job-ai-assist sends with each push, and print it."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument(
            "--rotate", action="store_true", help="Replace the user's existing token."
        )

    def handle(self, *args, username, rotate, **options):
        try:
            user = get_user_model().objects.get(username=username)
        except get_user_model().DoesNotExist as missing:
            raise CommandError(f"No user named {username!r}.") from missing

        existing = Token.objects.filter(user=user).first()
        if existing and not rotate:
            raise CommandError("A token already exists; pass --rotate to replace it.")
        if existing:
            existing.delete()

        # Printed once: the operator copies it into job-ai-assist's .env.
        self.stdout.write(Token.objects.create(user=user).key)
