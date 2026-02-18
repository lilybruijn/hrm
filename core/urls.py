from django.urls import path
from . import views

urlpatterns = [

    # Dashboard
    path("", views.dashboard, name="dashboard"),

    # =====================================================
    # PERSONEN (centrale detailpagina)
    # =====================================================

    path("people/<int:person_id>/", views.person_detail, name="person_detail"),

    # Studenten (lijst + compatibele detail route)
    path("students/", views.student_list, name="student_list"),
    path("students/<int:person_id>/", views.person_detail, name="student_detail"),
    path("students/new/", views.student_create, name="student_create"),
    path("students/<int:person_id>/convert/", views.student_convert_to_employee, name="student_convert_to_employee"),

    # Medewerkers (lijst + compatibele detail route)
    path("employees/", views.employee_list, name="employee_list"),
    path("employees/<int:person_id>/", views.person_detail, name="employee_detail"),
    path("employees/new/", views.employee_create, name="employee_create"),
    path("employees/<int:person_id>/convert-to-student/", views.employee_convert_to_student, name="employee_convert_to_student"),

    # =====================================================
    # SIGNALS / MELDINGEN
    # =====================================================

    path("signals/", views.signal_list, name="signal_list"),
    path("signals/new/", views.signal_create_global, name="signal_create_global"),
    path("signals/<int:signal_id>/notes/", views.signal_notes, name="signal_notes"),

    # signal create (vanuit person/student/employee)
    path("people/<int:person_id>/signals/new/", views.signal_create, name="signal_create"),
    path("students/<int:person_id>/signals/new/", views.signal_create, name="signal_create"),
    path("employees/<int:person_id>/signals/new/", views.signal_create, name="signal_create"),

    # =====================================================
    # NOTIFICATIONS
    # =====================================================

    path("notifications/", views.notification_list, name="notification_list"),
    path("notifications/<int:notif_id>/read/", views.notification_mark_read, name="notification_mark_read"),
    path("notifications/read-all/", views.notification_mark_all_read, name="notification_mark_all_read"),
    path("notifications/<int:signal_id>/quick/", views.notification_quick_update, name="notification_quick_update"),
    path("notifications/dropdown/", views.notification_dropdown, name="notification_dropdown"),

    # =====================================================
    # ROOSTERS
    # =====================================================

    path("people/<int:person_id>/roster/save/", views.roster_save, name="roster_save"),
    path("people/<int:person_id>/roster/day/<str:day>/save/", views.roster_day_save, name="roster_day_save"),
    
    path("people/<int:person_id>/rosters/new/", views.roster_create, name="roster_create"),
    path("people/<int:person_id>/rosters/<int:roster_id>/edit/", views.roster_edit, name="roster_edit"),
    path("people/<int:person_id>/rosters/<int:roster_id>/delete/", views.roster_delete, name="roster_delete"),

    # =====================================================
    # BEHEER (ADMIN IN PORTAL)
    # =====================================================

    # Organizations
    path("beheer/organizations/", views.organization_list, name="organization_list"),
    path("beheer/organizations/new/", views.organization_create, name="organization_create"),
    path("beheer/organizations/<int:pk>/edit/", views.organization_edit, name="organization_edit"),
    path("beheer/organizations/<int:pk>/delete/", views.organization_delete, name="organization_delete"),

    # Contact persons
    path("beheer/contactpersons/", views.contactperson_list, name="contactperson_list"),
    path("beheer/contactpersons/new/", views.contactperson_create, name="contactperson_create"),
    path("beheer/contactpersons/<int:pk>/edit/", views.contactperson_edit, name="contactperson_edit"),
    path("beheer/contactpersons/<int:pk>/delete/", views.contactperson_delete, name="contactperson_delete"),

    # Benefit types
    path("beheer/benefit-types/", views.benefittype_list, name="benefittype_list"),
    path("beheer/benefit-types/new/", views.benefittype_create, name="benefittype_create"),
    path("beheer/benefit-types/<int:pk>/edit/", views.benefittype_edit, name="benefittype_edit"),
    path("beheer/benefit-types/<int:pk>/delete/", views.benefittype_delete, name="benefittype_delete"),

    # Locations
    path("beheer/locations/", views.location_list, name="location_list"),
    path("beheer/locations/new/", views.location_create, name="location_create"),
    path("beheer/locations/<int:pk>/edit/", views.location_edit, name="location_edit"),
    path("beheer/locations/<int:pk>/delete/", views.location_delete, name="location_delete"),

    # Work packages
    path("beheer/work-packages/", views.workpackage_list, name="workpackage_list"),
    path("beheer/work-packages/new/", views.workpackage_create, name="workpackage_create"),
    path("beheer/work-packages/<int:pk>/edit/", views.workpackage_edit, name="workpackage_edit"),
    path("beheer/work-packages/<int:pk>/delete/", views.workpackage_delete, name="workpackage_delete"),

]
