import calendar

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from .auth import staff_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models import Q, Case, When, Value, IntegerField, Count
from django.core.paginator import Paginator
from django.urls import reverse
from collections import defaultdict
from .models import Person, EmployeeProfile, Location, Organization, Signal, SignalCategory, Notification, SignalNote, StudentProfile, Location, ContactPerson, BenefitType, WorkPackage, Person, Roster, RosterDay, RosterDayWork
from .forms import SignalForm, SignalCreateFromListForm, SignalHistory, StudentCreateForm, EmployeeCreateForm, LocationForm, ContactPersonForm, OrganizationForm, BenefitTypeForm, WorkPackageForm
from django.contrib.auth import get_user_model


def _parse_month(s: str) -> date:
    # verwacht "YYYY-MM"
    if not s:
        now = timezone.localdate()
        return now.replace(day=1)
    try:
        y, m = s.split("-")
        return date(int(y), int(m), 1)
    except Exception:
        now = timezone.localdate()
        return now.replace(day=1)

def _add_month(d: date, delta: int) -> date:
    y = d.year + (d.month - 1 + delta) // 12
    m = (d.month - 1 + delta) % 12 + 1
    return date(y, m, 1)

def _decimal_or_none(v: str):
    v = (v or "").strip().replace(",", ".")
    if v == "":
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        return None

def _roster_overlaps(qs, start_date, end_date, exclude_id=None):
    qs = qs.filter(start_date__lte=end_date, end_date__gte=start_date)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    return qs.exists()


@staff_required
def dashboard(request):
    total_students = Person.objects.filter(person_type="student").count()
    total_employees = Person.objects.filter(person_type="employee").count()

    # Studenten per status
    student_status_qs = (
        Person.objects
        .filter(person_type="student")
        .values("student_profile__status")
        .annotate(c=Count("id"))
    )
    status_map = {row["student_profile__status"] or "unknown": row["c"] for row in student_status_qs}

    # Labels in vaste volgorde
    student_status_labels = ["pending", "active", "dropped", "completed"]
    student_status_values = [status_map.get(k, 0) for k in student_status_labels]

    # Meldingen: open vs done + overdue
    now = timezone.localtime(timezone.now())
    signals_open = Signal.objects.filter(status="open").count()
    signals_done = Signal.objects.filter(status="done").count()
    signals_overdue = Signal.objects.filter(status="open", active_from__lt=now).count()

    return render(request, "core/dashboard.html", {
        "total_students": total_students,
        "total_employees": total_employees,
        "active_nav": "dashboard",

        # chart data
        "student_status_labels": ["Nog beginnen", "Actief", "Afgevallen", "Afgerond"],
        "student_status_values": student_status_values,

        "signals_open": signals_open,
        "signals_done": signals_done,
        "signals_overdue": signals_overdue,
    })

@staff_required
def person_list(request):
    person_type = request.GET.get("type", "student").strip()  # student|employee
    q = request.GET.get("q", "").strip()

    sort = request.GET.get("sort", "last_name")
    direction = request.GET.get("dir", "asc")

    allowed_sorts = {
        "last_name": "last_name",
        "first_name": "first_name",
        "email": "email",
        "city": "city",
        "created": "created_at",
    }

    sort_field = allowed_sorts.get(sort, "last_name")
    if direction == "desc":
        sort_field = f"-{sort_field}"

    qs = Person.objects.all()

    if person_type in ("student", "employee"):
        qs = qs.filter(person_type=person_type)

    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q) |
            Q(city__icontains=q)
        )

    qs = qs.order_by(sort_field, "first_name")

    per_page = int(request.GET.get("per_page", 25) or 25)
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))

    # voor links filters behouden
    params = request.GET.copy()
    params.pop("page", None)
    base_qs = params.urlencode()

    return render(request, "core/person_list.html", {
        "page_obj": page_obj,
        "people": page_obj.object_list,
        "type": person_type,
        "q": q,
        "sort": sort,
        "dir": direction,
        "base_qs": base_qs,
        "active_nav": "people",
    })

def _month_work_stats(cells):
    """
    cells = jouw calendar grid items (dicts) + None's.
    We tellen alleen echte dagen (dict) mee.

    Werkbare dag = status == "work" én planned > 0
    (Je kunt dit aanpassen als je ook 'swapped' wilt meetellen.)
    """
    stats = {
        "workable_days": 0,
        "planned_hours_total": Decimal("0"),
        "actual_hours_total": Decimal("0"),
        "status_counts": defaultdict(int),
    }

    for cell in cells:
        if not cell:
            continue

        status = cell.get("status") or "work"
        planned = cell.get("planned") or Decimal("0")
        actual = cell.get("actual") or Decimal("0")

        stats["status_counts"][status] += 1
        stats["planned_hours_total"] += planned
        stats["actual_hours_total"] += actual

        if status == "work" and planned > 0:
            stats["workable_days"] += 1

    # maak status_counts JSON/template vriendelijk
    stats["status_counts"] = dict(stats["status_counts"])
    return stats

@staff_required
def person_detail(request, person_id):
    person = get_object_or_404(
        Person.objects.select_related(
            "student_profile",
            "student_profile__location",
            "student_profile__organization",
            "student_profile__contact_person",
            "employee_profile",
        ).prefetch_related(
            "signals__category",
            "signals__assigned_to",
            "signals__created_by",
            "signals__notes__author",
            "signals__history__actor",
        ),
        id=person_id
    )


    tab = request.GET.get("tab", "profile")

    User = get_user_model()
    assignees = User.objects.filter(is_staff=True).order_by("username")
    signal_categories = SignalCategory.objects.all().order_by("name")


    open_id = request.GET.get("open", "").strip()


    signal_form = SignalForm()  # popup create

    month_start = _parse_month(request.GET.get("month", "").strip())
    month_end_day = calendar.monthrange(month_start.year, month_start.month)[1]
    month_end = date(month_start.year, month_start.month, month_end_day)

    prev_month = _add_month(month_start, -1)
    next_month = _add_month(month_start, 1)

    # actieve roosters die overlappen met deze maand
    rosters = list(
        Roster.objects.filter(person=person, start_date__lte=month_end, end_date__gte=month_start)
        .order_by("-start_date")
    )
    active_roster = rosters[0] if rosters else None

    # day overrides
    roster_days = RosterDay.objects.filter(person=person, date__gte=month_start, date__lte=month_end)
    day_map = {rd.date: rd for rd in roster_days}

    # work entries (alle werkpakket regels van deze maand)
    works = (RosterDayWork.objects
             .filter(person=person, date__gte=month_start, date__lte=month_end)
             .select_related("work_package")
             .order_by("date", "work_package__sort_order", "work_package__code"))

    # ✅ maandtotalen per werkpakket en per hoofdwerkpakket
    month_totals = {}
    month_parent_totals = {}

    for w in works:
        code = w.work_package.code
        parent_code = (code or "").split(".")[0]

        # totaal per subwerkpakket
        month_totals[code] = month_totals.get(code, Decimal("0")) + (w.hours or Decimal("0"))

        # totaal per hoofdwerkpakket
        month_parent_totals[parent_code] = month_parent_totals.get(parent_code, Decimal("0")) + (w.hours or Decimal("0"))

    
    month_grand_total = Decimal("0")

    for total in month_parent_totals.values():
        month_grand_total += total

    work_map = {}
    for w in works:
        parent_code = (w.work_package.code or "").split(".")[0]  # "1.1" -> "1"
        work_map.setdefault(w.date, []).append({
            "code": w.work_package.code,
            "title": w.work_package.title,
            "hours": w.hours,
            "wp_id": w.work_package_id,
            "parent_code": parent_code,   # ✅ nieuw
        })

    # work packages voor invul-dialog (toon alleen subpakketten, gegroepeerd per hoofd)
    parents = WorkPackage.objects.filter(parent__isnull=True).order_by("sort_order", "code")
    children = WorkPackage.objects.filter(parent__isnull=False).select_related("parent").order_by("parent__sort_order", "sort_order", "code")
    children_by_parent = {}
    for c in children:
        children_by_parent.setdefault(c.parent_id, []).append(c)

    # calendar grid: lege cellen vóór 1e, alleen dagen van de maand
    first_weekday = month_start.weekday()  # maandag=0
    cells = []

    # leading blanks
    for _ in range(first_weekday):
        cells.append(None)

    # days
    for day_num in range(1, month_end_day + 1):
        d = date(month_start.year, month_start.month, day_num)

        # basis planned uit rooster template (laatste rooster dat deze dag dekt)
        planned_base = Decimal("0")
        roster_for_day = None
        for r in rosters:
            if r.start_date <= d <= r.end_date:
                roster_for_day = r
                break

        if roster_for_day:
            wd = d.weekday()  # 0=ma

            cycle_start = roster_for_day.cycle_start_date or roster_for_day.start_date
            delta_days = (d - cycle_start).days
            week_index = ((delta_days // 7) % 2)  # 0=A, 1=B

            week_a = [
                roster_for_day.mon_a_hours,
                roster_for_day.tue_a_hours,
                roster_for_day.wed_a_hours,
                roster_for_day.thu_a_hours,
                roster_for_day.fri_a_hours,
                roster_for_day.sat_a_hours,
                roster_for_day.sun_a_hours,
            ]
            week_b = [
                roster_for_day.mon_b_hours,
                roster_for_day.tue_b_hours,
                roster_for_day.wed_b_hours,
                roster_for_day.thu_b_hours,
                roster_for_day.fri_b_hours,
                roster_for_day.sat_b_hours,
                roster_for_day.sun_b_hours,
            ]

            planned_base = (week_a if week_index == 0 else week_b)[wd]


        override = day_map.get(d)
        status = override.status if override else "work"
        planned = override.planned_hours if (override and override.planned_hours is not None) else planned_base
        actual = override.actual_hours if (override and override.actual_hours is not None) else (Decimal("0") if status in ("sick","vacation","off") else planned)
        note = override.note if override else ""

        entries = work_map.get(d, [])
        totals_by_parent = {}
        for e in entries:
            p = e.get("parent_code") or "-"
            totals_by_parent[p] = totals_by_parent.get(p, Decimal("0")) + (e["hours"] or Decimal("0"))

        cells.append({
            "date": d,
            "day": day_num,
            "status": status,
            "planned": planned,
            "actual": actual,
            "note": note,
            "entries": entries,
            "totals_by_parent": totals_by_parent,
            "rosters": rosters,
        })


    # trailing blanks zodat je grid netjes uitkomt
    while len(cells) % 7 != 0:
        cells.append(None)

    # groepeer subwerkpakketten per parent
    month_totals_by_parent = {}

    for code, total in month_totals.items():
        parent = code.split(".")[0]
        month_totals_by_parent.setdefault(parent, []).append({
            "code": code,
            "total": total,
        })

    # sorteer netjes
    month_totals_by_parent = dict(sorted(month_totals_by_parent.items()))
    for parent in month_totals_by_parent:
        month_totals_by_parent[parent] = sorted(
            month_totals_by_parent[parent],
            key=lambda x: x["code"]
        )
   

    month_stats = _month_work_stats(cells)

    return render(request, "core/person_detail.html", {
        "person": person,
        "month_start": month_start,
        "prev_month": prev_month,
        "next_month": next_month,
        "cells": cells,
        "active_roster": active_roster,
        "parents": parents,
        "children_by_parent": children_by_parent,
        "assignees": assignees,
        "signal_form": signal_form,
        "open_id": open_id,
        "active_nav": "people",
        "rosters": rosters,
        "tab": tab,
        "signal_categories": signal_categories,
        "month_totals": dict(sorted(month_totals.items())),
        "month_parent_totals": dict(sorted(month_parent_totals.items())),
        "month_totals_by_parent": month_totals_by_parent,
         "month_grand_total": month_grand_total,
         "month_stats": month_stats
    })


@staff_required
def student_list(request):
    qs = Person.objects.filter(person_type="student").select_related(
        "student_profile",
        "student_profile__location",
        "student_profile__organization",
    ).prefetch_related(
        "student_profile__documents",
        "signals__category",
    )

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    location_id = request.GET.get("location", "").strip()
    organization_id = request.GET.get("org", "").strip()
    job_guarantee = request.GET.get("job_guarantee", "").strip()
    praktijkroute = request.GET.get("praktijkroute", "").strip()

    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q)
        )

    if status:
        qs = qs.filter(student_profile__status=status)

    if location_id.isdigit():
        qs = qs.filter(student_profile__location_id=int(location_id))

    if organization_id.isdigit():
        qs = qs.filter(student_profile__organization_id=int(organization_id))

    if job_guarantee in ("0", "1"):
        qs = qs.filter(student_profile__job_guarantee=(job_guarantee == "1"))

    if praktijkroute in ("0", "1"):
        qs = qs.filter(student_profile__praktijkroute=(praktijkroute == "1"))

    locations = Location.objects.all().order_by("name")
    orgs = Organization.objects.all().order_by("name", "name")

    return render(request, "core/student_list.html", {
        "students": qs.order_by("last_name", "first_name"),
        "q": q,
        "status": status,
        "location_id": location_id,   # string, zoals je template verwacht
        "organization_id": organization_id,             # string, zoals je template verwacht
        "job_guarantee": job_guarantee,
        "praktijkroute": praktijkroute,
        "locations": locations,
        "orgs": orgs,
        "active_nav": "people",
    })



@staff_required
def student_detail(request, person_id):
    return person_detail(request, person_id)


@staff_required
def signal_create(request, person_id):
    person = get_object_or_404(Person, id=person_id)

    if request.method == "POST":
        form = SignalForm(request.POST)
        if form.is_valid():
            signal = form.save(commit=False)
            signal.person = person
            signal.created_by = request.user
            signal.save()
            messages.success(request, "Melding aangemaakt.")

            return_url = request.POST.get("return_url") or reverse("person_detail", args=[person.id])
            joiner = "&" if "?" in return_url else "?"
            return redirect(f"{return_url}{joiner}open={signal.id}")

    # (optioneel) fallback als iemand toch GET opent:
    return redirect("person_detail", person_id=person.id)



@staff_required
@transaction.atomic
def student_convert_to_employee(request, person_id):
    student = get_object_or_404(Person, id=person_id, person_type="student")

    if not hasattr(student, "student_profile"):
        messages.error(request, "Deze student heeft geen studentprofiel.")
        return redirect("student_detail", person_id=student.id)

    if request.method != "POST":
        return redirect("student_detail", person_id=student.id)

    # mark student as completed + end_date if empty
    sp = student.student_profile
    sp.status = "completed"
    if not sp.end_date:
        sp.end_date = timezone.now().date()
    sp.save()

    # switch type
    student.person_type = "employee"
    student.save()

    # create employee profile if missing
    if not hasattr(student, "employee_profile"):
        EmployeeProfile.objects.create(
            person=student,
            hired_date=timezone.now().date(),
            job_title="",
        )

    messages.success(request, "Student is omgezet naar medewerker (studentdata bewaard).")
    return redirect("dashboard")

@staff_required
def signal_list(request):
    now = timezone.localtime(timezone.now())
    # --- BULK ACTIONS ---
    if request.method == "POST":
        action = request.POST.get("action", "").strip()
        ids = request.POST.getlist("ids")
        return_url = request.POST.get("return_url") or request.get_full_path()

        if not ids:
            messages.warning(request, "Selecteer eerst één of meer meldingen.")
            return redirect(return_url)

        qs_bulk = Signal.objects.filter(id__in=ids)

        if action == "set_open":
            qs_bulk.update(status="open")
            messages.success(request, f"{qs_bulk.count()} melding(en) op 'Open' gezet.")
        elif action == "set_done":
            qs_bulk.update(status="done")
            messages.success(request, f"{qs_bulk.count()} melding(en) op 'Afgerond' gezet.")
        elif action == "set_snoozed":
            qs_bulk.update(status="snoozed")
            messages.success(request, f"{qs_bulk.count()} melding(en) op 'Gepauzeerd' gezet.")
        elif action == "delete":
            qs_bulk.delete()
            messages.success(request, "Meldingen verwijderd.")
        else:
            messages.error(request, "Onbekende bulk actie.")
        return redirect(return_url)

    open_id = request.GET.get("open", "").strip()

    # sorting params (eerst!)
    sort = request.GET.get("sort", "active_from").strip()
    direction = request.GET.get("dir", "asc").strip()

    # behoud alle filters in sort-links, behalve sort/dir zelf
    params = request.GET.copy()
    params.pop("sort", None)
    params.pop("dir", None)
    base_qs = params.urlencode()

    qs = Signal.objects.select_related(
        "person",
        "category",
        "assigned_to",
        "created_by",
    )

    # filters
    status = request.GET.get("status", "").strip()
    scope = request.GET.get("scope", "").strip()
    assigned = request.GET.get("assigned", "").strip()
    category_key = request.GET.get("category", "").strip()
    q = request.GET.get("q", "").strip()

    organization_id = request.GET.get("org", "").strip()
    show_future = request.GET.get("show_future") == "1"
    show_done = request.GET.get("show_done") == "1"

    person_type = request.GET.get("person_type", "").strip()
    


    # DEFAULT: hide future + hide done
    if not show_future:
        qs = qs.filter(active_from__lte=now)

    if not show_done:
        qs = qs.exclude(status="done")

    # explicit status filter
    if status in ("open", "done", "snoozed"):
        qs = qs.filter(status=status)

    if assigned == "me":
        qs = qs.filter(assigned_to=request.user)
    elif assigned.isdigit():
        qs = qs.filter(assigned_to_id=int(assigned))


    if category_key:
        qs = qs.filter(category__key=category_key)

    # Filter by person type (student of employee)
    if person_type in ("student", "employee"):
        qs = qs.filter(person__person_type=person_type)

    # Filter by organization (students)
    if organization_id.isdigit():
        qs = qs.filter(person__student_profile__organization_id=int(organization_id))

    # scope filters
    if scope == "overdue":
        qs = qs.filter(active_from__lt=now).exclude(status="done")
    elif scope == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timezone.timedelta(days=1)
        qs = qs.filter(active_from__gte=start, active_from__lt=end)
    elif scope == "week":
        end = now + timezone.timedelta(days=7)
        qs = qs.filter(active_from__gte=now, active_from__lte=end)

    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(body__icontains=q) |
            Q(person__first_name__icontains=q) |
            Q(person__last_name__icontains=q)
        )

    categories = SignalCategory.objects.all().order_by("name")
    orgs = Organization.objects.all().order_by("organization_type", "name")


    # allowed sorts
    allowed_sorts = {
        "active_from": "active_from",
        "person": "person__last_name",        # 👈 nieuwe naam
        "person_type": "person__person_type",# 👈 nieuwe
        "category": "category__name",
        "title": "title",
        "status": "status",
        "created_by": "created_by__username",
    }

    sort_field = allowed_sorts.get(sort, "active_from")
    if direction == "desc":
        sort_field = f"-{sort_field}"

    # open first, then chosen sort, then tie-breaker
    qs = qs.annotate(
        sort_open=Case(
            When(status="open", then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by("sort_open", sort_field, "-created_at")

    User = get_user_model()
    assignees = User.objects.filter(is_staff=True).order_by("username")
    
    User = get_user_model()
    users = User.objects.filter(is_staff=True).order_by("username")

    qs = qs.prefetch_related("notes__author", "history__actor") 
    
    per_page = int(request.GET.get("per_page", 25) or 25)
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "core/signal_list.html", {
        "signals": qs,
        "categories": categories,
        "orgs": orgs,
        "status": status,
        "scope": scope,
        "assigned": assigned,
        "users": users,
        "category_key": category_key,
        "organization_id": organization_id,
        "show_future": show_future,
        "show_done": show_done,
        "q": q,
        "now": now,
        "sort": sort,
        "dir": direction,
        "base_qs": base_qs,
        "active_nav": "signals",
        "open_id": open_id,
        "assignees": assignees,
        "page_obj": page_obj,
        "signals": page_obj.object_list,
        "paginator": paginator,
        "per_page": per_page,
    })

@staff_required
def signal_create_global(request):
    if request.method == "POST":
        form = SignalCreateFromListForm(request.POST)
        if form.is_valid():
            signal = form.save(commit=False)
            signal.created_by = request.user
            signal.save()
            messages.success(request, "Melding aangemaakt.")
            return redirect("signal_list")
    else:
        form = SignalCreateFromListForm()

    return render(request, "core/signal_form_global.html", {
        "form": form,
        "active_nav": "signals",
    })
@staff_required
def notification_list(request):
    now = timezone.localtime(timezone.now())
    open_id = request.GET.get("open", "").strip()


    # sorting params
    sort = request.GET.get("sort", "active_from").strip()
    direction = request.GET.get("dir", "asc").strip()

    params = request.GET.copy()
    params.pop("sort", None)
    params.pop("dir", None)
    base_qs = params.urlencode()

    show_future = request.GET.get("show_future") == "1"
    show_done = request.GET.get("show_done") == "1"

    qs = Signal.objects.select_related(
        "person",
        "category",
        "assigned_to",
        "created_by",
    ).filter(
        assigned_to=request.user
    ).prefetch_related(
        "notes__author", "history__actor"
    )


    if not show_future:
        qs = qs.filter(active_from__lte=now)

    if not show_done:
        qs = qs.exclude(status="done")

    allowed_sorts = {
        "active_from": "active_from",
        "student": "person__last_name",
        "category": "category__name",
        "title": "title",
        "status": "status",
        "created_by": "created_by__username",
    }

    sort_field = allowed_sorts.get(sort, "active_from")
    if direction == "desc":
        sort_field = f"-{sort_field}"

    qs = qs.annotate(
        sort_open=Case(
            When(status="open", then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by("sort_open", sort_field, "-created_at")

    
    User = get_user_model()
    assignees = User.objects.filter(is_staff=True).order_by("username")

    return render(request, "core/notification_list.html", {
        "signals": qs,              # ✅ template expects signals
        "now": now,
        "open_id": open_id,
        "show_future": show_future,
        "show_done": show_done,
        "sort": sort,
        "dir": direction,
        "base_qs": base_qs,
        "active_nav": "notifications",
        "assignees": assignees,

    })



@staff_required
def notification_mark_read(request, notif_id):
    n = get_object_or_404(Notification, id=notif_id, user=request.user)

    if request.method == "POST":
        n.mark_read()
        # als er een url is: daarheen
        if n.url:
            return redirect(n.url)
        return redirect("notification_list")

    return redirect("notification_list")


@staff_required
def notification_mark_all_read(request):
    if request.method == "POST":
        Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True,
            read_at=timezone.now(),
        )
    return redirect("notification_list")

@staff_required
@transaction.atomic
def notification_quick_update(request, signal_id):
    s = get_object_or_404(Signal, id=signal_id)  # niet alleen assigned_to, want je wil kunnen re-assignen

    # security: alleen staff en alleen als je het mag zien.
    # Jij gebruikt staff_required, dus OK.
    # Extra: je kunt later nog beperken tot "assigned_to == user OR created_by == user".

    if request.method != "POST":
        return redirect("notification_list")

    old = {
        "title": s.title,
        "body": s.body,
        "status": s.status,
        "assigned_to_id": s.assigned_to_id,
    }

    # incoming
    title = request.POST.get("title", "").strip()
    body = request.POST.get("body", "").strip()
    status = request.POST.get("status", "").strip()
    assigned_to_id = request.POST.get("assigned_to", "").strip()
    note = request.POST.get("note", "").strip()

    # validate & apply
    changes = {}

    if title and title != s.title:
        changes["title"] = [s.title, title]
        s.title = title

    if body != s.body:
        changes["body"] = [s.body or "", body]
        s.body = body

    if status in ("open", "done", "snoozed") and status != s.status:
        changes["status"] = [s.status, status]
        s.status = status

    new_assignee = None
    if assigned_to_id.isdigit():
        new_assignee = get_user_model().objects.filter(id=int(assigned_to_id), is_staff=True).first()
    else:
        new_assignee = None

    if new_assignee and new_assignee.id != s.assigned_to_id:
        old_assignee_name = s.assigned_to.username if s.assigned_to else "-"
        new_assignee_name = new_assignee.username if new_assignee else "-"

        changes["assigned_to"] = [old_assignee_name, new_assignee_name]


        s.assigned_to = new_assignee

    s.save()  # save all changed fields

    # history log
    if changes:
        SignalHistory.objects.create(
            signal=s,
            actor=request.user,
            action="updated",
            changes=changes,

        )

    # note (optional)
    if note:
        SignalNote.objects.create(signal=s, author=request.user, body=note)

    # mark current user's notifications for this signal as read
    Notification.objects.filter(user=request.user, signal=s, is_read=False).update(
        is_read=True, read_at=timezone.now()
    )

    # if reassigned -> create a new unread notification for the new assignee
    if "assigned_to" in changes and s.assigned_to:
        Notification.objects.get_or_create(
            user=s.assigned_to,
            signal=s,
            defaults={
                "title": f"Melding: {s.title}",
                "body": s.body or "",
                "url": f"/notifications/?open={s.id}",
                "is_read": False,
            }
        )
        # ook log specifieke reassignment actie (handig)
        SignalHistory.objects.create(
            signal=s,
            actor=request.user,
            action="reassigned",
            changes={"assigned_to": [old_assignee_name, new_assignee_name]},
        )

    # terug naar waar je vandaan kwam (notifications of student detail)
    return_url = request.POST.get("return_url") or ""
    if return_url:
        return redirect(return_url)

    return redirect("notification_list")



@staff_required
def notification_dropdown(request):
    from core.services.notifications import ensure_notifications_for_user
    ensure_notifications_for_user(request.user)

    qs = (
        Notification.objects
        .select_related("signal", "signal__person", "signal__category")
        .filter(user=request.user, is_read=False)
        .order_by("-created_at")[:8]
    )

    return render(request, "core/partials/notification_dropdown.html", {
        "notifications": qs,
    })
@staff_required
def employee_list(request):
    qs = Person.objects.filter(person_type="employee").select_related(
        "employee_profile",
    )

    q = request.GET.get("q", "").strip()
    job_title = request.GET.get("job_title", "").strip()

    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q)
        )

    if job_title:
        qs = qs.filter(employee_profile__job_title__icontains=job_title)

    return render(request, "core/employee_list.html", {
        "employees": qs.order_by("last_name", "first_name"),
        "q": q,
        "job_title": job_title,
        "active_nav": "people",
    })


@staff_required
def employee_detail(request, person_id):
    return person_detail(request, person_id)

@staff_required
@transaction.atomic
def employee_convert_to_student(request, person_id):
    emp = get_object_or_404(Person, id=person_id, person_type="employee")

    if request.method != "POST":
        return redirect("employee_detail", person_id=emp.id)

    # switch type
    emp.person_type = "student"
    emp.save()

    # create student profile if missing (employee data blijft bestaan)
    if not hasattr(emp, "student_profile"):
        StudentProfile.objects.create(
            person=emp,
            status="active",
            start_date=timezone.now().date(),
        )

    messages.success(request, "Medewerker is omgezet naar student (data bewaard).")
    return redirect("student_detail", person_id=emp.id)


@staff_required
def student_create(request):
    if request.method == "POST":
        form = StudentCreateForm(request.POST)
        if form.is_valid():
            person = form.save(commit=False)
            person.person_type = "student"
            person.save()

            StudentProfile.objects.create(
                person=person,
                status=form.cleaned_data["status"],
                start_date=form.cleaned_data.get("start_date") or timezone.now().date(),
            )
            return redirect("student_detail", person_id=person.id)
    else:
        form = StudentCreateForm(initial={"status": "pending"})

    return render(request, "core/student_create.html", {"form": form, "active_nav": "students"})


@staff_required
def employee_create(request):
    if request.method == "POST":
        form = EmployeeCreateForm(request.POST)
        if form.is_valid():
            person = form.save(commit=False)
            person.person_type = "employee"
            person.save()

            EmployeeProfile.objects.create(
                person=person,
                hired_date=form.cleaned_data.get("hired_date") or timezone.now().date(),
                job_title=form.cleaned_data.get("job_title") or "",
            )
            return redirect("employee_detail", person_id=person.id)
    else:
        form = EmployeeCreateForm()

    return render(request, "core/employee_create.html", {"form": form, "active_nav": "employees"})


@staff_required
def signal_notes(request, signal_id):
    sig = get_object_or_404(
        Signal.objects.select_related("person", "category"),
        id=signal_id
    )

    qs = sig.notes.select_related("author").order_by("-created_at")
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "core/signal_notes.html", {
        "sig": sig,
        "page_obj": page_obj,
        "active_nav": "signals",
    })


@staff_required
def location_list(request):
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "name")
    direction = request.GET.get("dir", "asc")

    allowed = {"name": "name", "id": "id"}
    sort_field = allowed.get(sort, "name")
    if direction == "desc":
        sort_field = f"-{sort_field}"

    qs = Location.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)

    qs = qs.order_by(sort_field)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)
    base_qs = params.urlencode()

    return render(request, "core/admin/location_list.html", {
        "page_obj": page_obj,
        "locations": page_obj.object_list,
        "q": q,
        "sort": sort,
        "dir": direction,
        "base_qs": base_qs,
        "active_nav": "admin",
    })

@staff_required
def location_create(request):
    form = LocationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("location_list")
    return render(request, "core/admin/form.html", {"form": form, "active_nav": "admin", "title": "Locatie toevoegen"})

@staff_required
def location_edit(request, pk):
    obj = get_object_or_404(Location, pk=pk)
    form = LocationForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("location_list")
    return render(request, "core/admin/form.html", {"form": form, "active_nav": "admin", "title": "Locatie bewerken"})

@staff_required
def location_delete(request, pk):
    obj = get_object_or_404(Location, pk=pk)
    if request.method == "POST":
        obj.delete()
        return redirect("location_list")
    return render(request, "core/admin/confirm_delete.html", {"object": obj, "active_nav": "admin", "title": "Locatie verwijderen"})

###############


@staff_required
def contactperson_list(request):
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "name")
    direction = request.GET.get("dir", "asc")

    allowed = {"name": "name", "id": "id"}
    sort_field = allowed.get(sort, "name")
    if direction == "desc":
        sort_field = f"-{sort_field}"

    qs = ContactPerson.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)

    qs = qs.order_by(sort_field)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)
    base_qs = params.urlencode()

    return render(request, "core/admin/contactperson_list.html", {
        "page_obj": page_obj,
        "contactpersons": page_obj.object_list,
        "q": q,
        "sort": sort,
        "dir": direction,
        "base_qs": base_qs,
        "active_nav": "admin",
    })

@staff_required
def contactperson_create(request):
    form = ContactPersonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("contactperson_list")
    return render(request, "core/admin/form.html", {"form": form, "active_nav": "admin", "title": "Contactpersoon toevoegen"})

@staff_required
def contactperson_edit(request, pk):
    obj = get_object_or_404(ContactPerson, pk=pk)
    form = ContactPersonForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("contactperson_list")
    return render(request, "core/admin/form.html", {"form": form, "active_nav": "admin", "title": "Contactpersoon bewerken"})

@staff_required
def contactperson_delete(request, pk):
    obj = get_object_or_404(ContactPerson, pk=pk)
    if request.method == "POST":
        obj.delete()
        return redirect("contactperson_list")
    return render(request, "core/admin/confirm_delete.html", {"object": obj, "active_nav": "admin", "title": "Contactpersoon verwijderen"})





###############


@staff_required
def benefittype_list(request):
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "name")
    direction = request.GET.get("dir", "asc")

    allowed = {"name": "name", "id": "id"}
    sort_field = allowed.get(sort, "name")
    if direction == "desc":
        sort_field = f"-{sort_field}"

    qs = BenefitType.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)

    qs = qs.order_by(sort_field)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)
    base_qs = params.urlencode()

    return render(request, "core/admin/benefittype_list.html", {
        "page_obj": page_obj,
        "benefittypes": page_obj.object_list,
        "q": q,
        "sort": sort,
        "dir": direction,
        "base_qs": base_qs,
        "active_nav": "admin",
    })

@staff_required
def benefittype_create(request):
    form = BenefitTypeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("benefittype_list")
    return render(request, "core/admin/form.html", {"form": form, "active_nav": "admin", "title": "Uitkering toevoegen"})

@staff_required
def benefittype_edit(request, pk):
    obj = get_object_or_404(BenefitType, pk=pk)
    form = BenefitTypeForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("benefittype_list")
    return render(request, "core/admin/form.html", {"form": form, "active_nav": "admin", "title": "Uitkering bewerken"})

@staff_required
def benefittype_delete(request, pk):
    obj = get_object_or_404(BenefitType, pk=pk)
    if request.method == "POST":
        obj.delete()
        return redirect("benefittype_list")
    return render(request, "core/admin/confirm_delete.html", {"object": obj, "active_nav": "admin", "title": "Uitkering verwijderen"})




###############


@staff_required
def organization_list(request):
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "name")
    direction = request.GET.get("dir", "asc")

    allowed = {"name": "name", "id": "id"}
    sort_field = allowed.get(sort, "name")
    if direction == "desc":
        sort_field = f"-{sort_field}"

    qs = Organization.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)

    qs = qs.order_by(sort_field)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)
    base_qs = params.urlencode()

    return render(request, "core/admin/organization_list.html", {
        "page_obj": page_obj,
        "organizations": page_obj.object_list,
        "q": q,
        "sort": sort,
        "dir": direction,
        "base_qs": base_qs,
        "active_nav": "admin",
    })

@staff_required
def organization_create(request):
    form = OrganizationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("organization_list")
    return render(request, "core/admin/form.html", {"form": form, "active_nav": "admin", "title": "Organisatie toevoegen"})

@staff_required
def organization_edit(request, pk):
    obj = get_object_or_404(Organization, pk=pk)
    form = OrganizationForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("organization_list")
    return render(request, "core/admin/form.html", {"form": form, "active_nav": "admin", "title": "Organisatie bewerken"})

@staff_required
def organization_delete(request, pk):
    obj = get_object_or_404(Organization, pk=pk)
    if request.method == "POST":
        obj.delete()
        return redirect("organization_list")
    return render(request, "core/admin/confirm_delete.html", {"object": obj, "active_nav": "admin", "title": "Organisatie verwijderen"})
@staff_required
def roster_create(request, person_id):
    person = get_object_or_404(Person, id=person_id)
    return_url = request.POST.get("return_url") or reverse("person_detail", args=[person.id])

    if request.method != "POST":
        return redirect(return_url)

    start_date = request.POST.get("start_date")
    end_date = request.POST.get("end_date")
    cycle_start_date = request.POST.get("cycle_start_date") or start_date

    if not start_date or not end_date:
        messages.error(request, "Start- en einddatum zijn verplicht.")
        return redirect(return_url)

    # overlap check
    if _roster_overlaps(Roster.objects.filter(person=person), start_date, end_date):
        messages.error(request, "Dit rooster overlapt met een bestaand rooster. Pas de periode aan.")
        return redirect(return_url)

    r = Roster.objects.create(
        person=person,
        start_date=start_date,
        end_date=end_date,
        cycle_start_date=cycle_start_date,

        mon_a_hours=_decimal_or_none(request.POST.get("mon_a_hours")) or Decimal("0"),
        tue_a_hours=_decimal_or_none(request.POST.get("tue_a_hours")) or Decimal("0"),
        wed_a_hours=_decimal_or_none(request.POST.get("wed_a_hours")) or Decimal("0"),
        thu_a_hours=_decimal_or_none(request.POST.get("thu_a_hours")) or Decimal("0"),
        fri_a_hours=_decimal_or_none(request.POST.get("fri_a_hours")) or Decimal("0"),
        sat_a_hours=_decimal_or_none(request.POST.get("sat_a_hours")) or Decimal("0"),
        sun_a_hours=_decimal_or_none(request.POST.get("sun_a_hours")) or Decimal("0"),

        mon_b_hours=_decimal_or_none(request.POST.get("mon_b_hours")) or Decimal("0"),
        tue_b_hours=_decimal_or_none(request.POST.get("tue_b_hours")) or Decimal("0"),
        wed_b_hours=_decimal_or_none(request.POST.get("wed_b_hours")) or Decimal("0"),
        thu_b_hours=_decimal_or_none(request.POST.get("thu_b_hours")) or Decimal("0"),
        fri_b_hours=_decimal_or_none(request.POST.get("fri_b_hours")) or Decimal("0"),
        sat_b_hours=_decimal_or_none(request.POST.get("sat_b_hours")) or Decimal("0"),
        sun_b_hours=_decimal_or_none(request.POST.get("sun_b_hours")) or Decimal("0"),
    )

    messages.success(request, "Nieuw rooster toegevoegd.")
    return redirect(return_url)


@staff_required
def roster_edit(request, person_id, roster_id):
    person = get_object_or_404(Person, id=person_id)
    roster = get_object_or_404(Roster, id=roster_id, person=person)
    return_url = request.POST.get("return_url") or reverse("person_detail", args=[person.id])

    if request.method != "POST":
        return redirect(return_url)

    start_date = request.POST.get("start_date")
    end_date = request.POST.get("end_date")
    cycle_start_date = request.POST.get("cycle_start_date") or start_date

    if not start_date or not end_date:
        messages.error(request, "Start- en einddatum zijn verplicht.")
        return redirect(return_url)

    if _roster_overlaps(Roster.objects.filter(person=person), start_date, end_date, exclude_id=roster.id):
        messages.error(request, "Deze periode overlapt met een ander rooster.")
        return redirect(return_url)

    roster.start_date = start_date
    roster.end_date = end_date
    roster.cycle_start_date = cycle_start_date

    for f in [
        "mon_a_hours","tue_a_hours","wed_a_hours","thu_a_hours","fri_a_hours","sat_a_hours","sun_a_hours",
        "mon_b_hours","tue_b_hours","wed_b_hours","thu_b_hours","fri_b_hours","sat_b_hours","sun_b_hours",
    ]:
        setattr(roster, f, _decimal_or_none(request.POST.get(f)) or Decimal("0"))

    roster.save()
    messages.success(request, "Rooster bijgewerkt.")
    return redirect(return_url)


@staff_required
def roster_delete(request, person_id, roster_id):
    person = get_object_or_404(Person, id=person_id)
    roster = get_object_or_404(Roster, id=roster_id, person=person)
    return_url = request.POST.get("return_url") or reverse("person_detail", args=[person.id])

    if request.method == "POST":
        roster.delete()
        messages.success(request, "Rooster verwijderd.")
    return redirect(return_url)
@staff_required
def workpackage_list(request):
    q = request.GET.get("q", "").strip()
    qs = WorkPackage.objects.select_related("parent").all()

    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(title__icontains=q) | Q(parent__title__icontains=q))

    qs = qs.order_by("sort_order", "code")

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)
    base_qs = params.urlencode()

    return render(request, "core/admin/workpackage_list.html", {
        "page_obj": page_obj,
        "workpackages": page_obj.object_list,
        "q": q,
        "base_qs": base_qs,
        "active_nav": "admin",
    })

@staff_required
def workpackage_create(request):
    form = WorkPackageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("workpackage_list")
    return render(request, "core/admin/form.html", {"form": form, "title": "Werkpakket toevoegen", "active_nav": "admin"})

@staff_required
def workpackage_edit(request, pk):
    obj = get_object_or_404(WorkPackage, pk=pk)
    form = WorkPackageForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("workpackage_list")
    return render(request, "core/admin/form.html", {"form": form, "title": "Werkpakket bewerken", "active_nav": "admin"})

@staff_required
def workpackage_delete(request, pk):
    obj = get_object_or_404(WorkPackage, pk=pk)
    if request.method == "POST":
        obj.delete()
        return redirect("workpackage_list")
    return render(request, "core/admin/confirm_delete.html", {"object": obj, "title": "Werkpakket verwijderen", "active_nav": "admin"})


@staff_required
def roster_save(request, person_id):
    person = get_object_or_404(Person, id=person_id)
    if request.method != "POST":
        return redirect("person_detail", person_id=person.id)

    return_url = request.POST.get("return_url") or reverse("person_detail", args=[person.id])

    roster_id = request.POST.get("roster_id", "").strip()
    start_date = request.POST.get("start_date")
    end_date = request.POST.get("end_date")
    cycle_start_date = request.POST.get("cycle_start_date") or start_date

    if not start_date or not end_date:
        messages.error(request, "Start- en einddatum zijn verplicht.")
        return redirect(return_url)

    if roster_id.isdigit():
        r = get_object_or_404(Roster, id=int(roster_id), person=person)
    else:
        r = Roster(person=person)

    r.start_date = start_date
    r.end_date = end_date
    r.cycle_start_date = cycle_start_date

    # Week A
    r.mon_a_hours = _decimal_or_none(request.POST.get("mon_a_hours")) or Decimal("0")
    r.tue_a_hours = _decimal_or_none(request.POST.get("tue_a_hours")) or Decimal("0")
    r.wed_a_hours = _decimal_or_none(request.POST.get("wed_a_hours")) or Decimal("0")
    r.thu_a_hours = _decimal_or_none(request.POST.get("thu_a_hours")) or Decimal("0")
    r.fri_a_hours = _decimal_or_none(request.POST.get("fri_a_hours")) or Decimal("0")
    r.sat_a_hours = _decimal_or_none(request.POST.get("sat_a_hours")) or Decimal("0")
    r.sun_a_hours = _decimal_or_none(request.POST.get("sun_a_hours")) or Decimal("0")

    # Week B
    r.mon_b_hours = _decimal_or_none(request.POST.get("mon_b_hours")) or Decimal("0")
    r.tue_b_hours = _decimal_or_none(request.POST.get("tue_b_hours")) or Decimal("0")
    r.wed_b_hours = _decimal_or_none(request.POST.get("wed_b_hours")) or Decimal("0")
    r.thu_b_hours = _decimal_or_none(request.POST.get("thu_b_hours")) or Decimal("0")
    r.fri_b_hours = _decimal_or_none(request.POST.get("fri_b_hours")) or Decimal("0")
    r.sat_b_hours = _decimal_or_none(request.POST.get("sat_b_hours")) or Decimal("0")
    r.sun_b_hours = _decimal_or_none(request.POST.get("sun_b_hours")) or Decimal("0")

    r.save()
    messages.success(request, "Rooster opgeslagen.")
    return redirect(return_url)

@staff_required
def roster_day_save(request, person_id, day):
    person = get_object_or_404(Person, id=person_id)
    if request.method != "POST":
        return redirect("person_detail", person_id=person.id)

    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        messages.error(request, "Ongeldige datum.")
        return redirect(request.POST.get("return_url") or "person_detail", person_id=person.id)

    status = request.POST.get("status", "work").strip()
    planned_hours = _decimal_or_none(request.POST.get("planned_hours"))
    actual_hours = _decimal_or_none(request.POST.get("actual_hours"))
    note = request.POST.get("note", "")

    rd, _ = RosterDay.objects.get_or_create(person=person, date=d)
    rd.status = status
    rd.planned_hours = planned_hours
    rd.actual_hours = actual_hours
    rd.note = note
    rd.save()

    # werkpakket inputs: name="wp_<id>"
    for key, val in request.POST.items():
        if not key.startswith("wp_"):
            continue
        wp_id = key.replace("wp_", "").strip()
        if not wp_id.isdigit():
            continue

        hours = _decimal_or_none(val)
        wp_id_int = int(wp_id)

        if hours is None or hours == 0:
            RosterDayWork.objects.filter(person=person, date=d, work_package_id=wp_id_int).delete()
        else:
            obj, _ = RosterDayWork.objects.get_or_create(person=person, date=d, work_package_id=wp_id_int)
            obj.hours = hours
            obj.save()

    messages.success(request, "Dag bijgewerkt.")
    return redirect(request.POST.get("return_url") or "person_detail", person_id=person.id)
