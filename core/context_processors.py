from core.models import Notification, SignalCategory, Organization
from core.services.notifications import ensure_notifications_for_user

def header_context(request):
    user = getattr(request, "user", None)

    if user and user.is_authenticated:
        ensure_notifications_for_user(user)
        unread = Notification.objects.filter(user=user, is_read=False).count()
    else:
        unread = 0

    return {"unread_notifications_count": unread}


def portal_nav(request):
    categories = SignalCategory.objects.all().order_by("name")
    orgs = Organization.objects.all().order_by("organization_type", "name")


    return {
        "nav_signal_categories": categories,
        "nav_orgs": orgs,
    }

