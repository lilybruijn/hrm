from django.utils import timezone
from django.db import transaction

from core.models import Signal, Notification


@transaction.atomic
def ensure_notifications_for_user(user):
    if not user or not user.is_authenticated:
        return

    now = timezone.localtime(timezone.now())

    eligible = (
        Signal.objects
        .filter(
            notify=True,
            assigned_to=user,
            active_from__lte=now,
        )
        .exclude(status="done")
    )

    # signals zonder notification voor deze user
    missing = eligible.exclude(notifications__user=user)

    if not missing.exists():
        return

    to_create = []
    for s in missing:
        to_create.append(Notification(
            user=user,
            signal=s,
            title=f"Melding: {s.title}",
            body=s.body or "",
            url=f"/notifications/?open={s.id}",
        ))

    Notification.objects.bulk_create(to_create, ignore_conflicts=True)
