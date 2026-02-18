from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import Signal, Notification


class Command(BaseCommand):
    help = "Create in-app notifications for signals that should notify and are due."

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.localtime(timezone.now())

        # Eligible signals:
        # - notify=True
        # - assigned_to set
        # - active_from <= now
        # - status not done
        qs = (
            Signal.objects.select_related("person", "assigned_to", "category")
            .filter(notify=True, assigned_to__isnull=False, active_from__lte=now)
            .exclude(status="done")
        )

        created = 0

        for s in qs:
            # prevent duplicates: 1 notification per (signal, user)
            exists = Notification.objects.filter(signal=s, user=s.assigned_to).exists()
            if exists:
                continue

            student_url = f"/students/{s.person_id}/?tab=signals"

            Notification.objects.create(
                user=s.assigned_to,
                signal=s,
                title=f"Melding: {s.title}",
                body=s.body or "",
                url=student_url,
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created} notifications."))
