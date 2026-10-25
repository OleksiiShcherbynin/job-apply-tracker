from pathlib import Path

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, Prefetch, ProtectedError, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)
from django.views.generic.base import TemplateResponseMixin
from django.views.generic.detail import SingleObjectMixin

from .forms import (
    ApplyForm,
    AttachmentForm,
    CompanyForm,
    DismissForm,
    EventForm,
    StatusChangeForm,
    VacancyDeleteForm,
    VacancyForm,
)
from .mixins import OwnerFormMixin, OwnerQuerySetMixin
from .models import Application, ApplicationEvent, Attachment, Company, Vacancy


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "tracker/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        applications = Application.objects.for_owner(user)

        context["needs_attention"] = (
            Application.objects.needs_attention(user)
            .select_related("vacancy__company")
            .order_by("applied_at")
        )
        counts = dict(applications.values_list("status").annotate(n=Count("id")))
        context["status_counts"] = [
            (label, counts.get(value, 0)) for value, label in Application.Status.choices
        ]
        context["recent_events"] = (
            ApplicationEvent.objects.filter(application__owner=user)
            .select_related("application__vacancy__company")
            .order_by("-happened_at")[:10]
        )
        context["inbox_count"] = Vacancy.objects.for_inbox_view(user).count()
        return context


# --- Companies ---


class CompanyListView(OwnerQuerySetMixin, ListView):
    model = Company


class CompanyCreateView(LoginRequiredMixin, OwnerFormMixin, CreateView):
    model = Company
    form_class = CompanyForm
    success_url = reverse_lazy("tracker:company_list")


class CompanyUpdateView(OwnerQuerySetMixin, OwnerFormMixin, UpdateView):
    model = Company
    form_class = CompanyForm
    success_url = reverse_lazy("tracker:company_list")


class CompanyDeleteView(OwnerQuerySetMixin, DeleteView):
    model = Company
    success_url = reverse_lazy("tracker:company_list")

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f"{self.object} has vacancies — delete or move them first.",
            )
            return redirect("tracker:company_list")


# --- Vacancies ---


def inbox_return_url(request):
    """Where an inbox action returns: the same toggled view it came from.

    Only same-site paths are trusted; anything else falls back to the plain
    inbox, so the parameter can't bounce the user to another site.
    """
    target = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return reverse("tracker:inbox")


class InboxView(OwnerQuerySetMixin, ListView):
    model = Vacancy
    template_name = "tracker/inbox.html"

    def get_queryset(self):
        # for_inbox_view also select_related()s the company: one JOIN instead of
        # a query per card for {{ vacancy.company }}.
        return Vacancy.objects.for_inbox_view(
            self.request.user,
            unprocessed=self.show_unprocessed,
            below_threshold=self.show_low,
        )

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.show_unprocessed = request.GET.get("unprocessed") == "1"
        self.show_low = request.GET.get("low") == "1"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_unprocessed"] = self.show_unprocessed
        context["show_low"] = self.show_low
        return context


class VacancyListView(OwnerQuerySetMixin, ListView):
    model = Vacancy

    def get_queryset(self):
        queryset = super().get_queryset().select_related("company").order_by("-created_at")
        state = self.request.GET.get("state")
        if state in Vacancy.State.values:
            queryset = queryset.filter(state=state)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["states"] = Vacancy.State.choices
        context["current_state"] = self.request.GET.get("state", "")
        return context


class VacancyCreateView(LoginRequiredMixin, OwnerFormMixin, CreateView):
    model = Vacancy
    form_class = VacancyForm
    success_url = reverse_lazy("tracker:inbox")


class VacancyUpdateView(OwnerQuerySetMixin, OwnerFormMixin, UpdateView):
    model = Vacancy
    form_class = VacancyForm
    success_url = reverse_lazy("tracker:vacancy_list")


class VacancyDeleteView(OwnerQuerySetMixin, DeleteView):
    model = Vacancy
    form_class = VacancyDeleteForm
    success_url = reverse_lazy("tracker:vacancy_list")

    @cached_property
    def application(self):
        return Application.objects.filter(vacancy=self.object).first()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["has_application"] = self.application is not None
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.application is not None:
            context["application"] = self.application
            context["event_count"] = self.application.events.count()
            context["attachment_count"] = self.application.attachments.count()
        return context

    def form_valid(self, form):
        # Reaching here with an application means the user ticked the box.
        stored_files = []
        with transaction.atomic():
            if self.application is not None:
                stored_files = [a.file for a in self.application.attachments.all()]
                self.application.delete()
            response = super().form_valid(form)
        # Uploaded CVs are personal data: don't leave them orphaned on disk.
        for stored in stored_files:
            stored.storage.delete(stored.name)
        messages.info(self.request, f"Deleted: {self.object}.")
        return response


class VacancyApplyView(OwnerQuerySetMixin, SingleObjectMixin, FormView):
    """The "I applied" button: turns an inbox vacancy into an Application."""

    model = Vacancy
    form_class = ApplyForm
    template_name = "tracker/apply_form.html"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.redirect_if_applied() or super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.redirect_if_applied() or super().post(request, *args, **kwargs)

    @cached_property
    def previous_attempts(self):
        return list(self.object.previous_applications())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["previous_attempts"] = self.previous_attempts
        return kwargs

    def get_context_data(self, **kwargs):
        kwargs.setdefault("previous_attempts", self.previous_attempts)
        return super().get_context_data(**kwargs)

    def redirect_if_applied(self):
        # One application per vacancy (OneToOne): a second click or a stale
        # tab must land on the existing one, not crash on IntegrityError.
        existing = Application.objects.filter(vacancy=self.object).first()
        return redirect(existing) if existing else None

    def form_valid(self, form):
        data = form.cleaned_data
        with transaction.atomic():
            application = self.object.mark_applied(
                data["applied_at"],
                data["notes"],
                previous_attempt=self.previous_attempts[0] if self.previous_attempts else None,
            )
            if data["file"]:
                Attachment.objects.create(
                    application=application,
                    file=data["file"],
                    label=data["label"],
                )
        messages.success(self.request, f"Applied: {self.object}.")
        return redirect(application)


class VacancyDismissView(OwnerQuerySetMixin, UpdateView):
    """The "Dismiss" button. POST only: it changes data (see lesson 1)."""

    model = Vacancy
    form_class = DismissForm
    http_method_names = ["post"]
    success_url = reverse_lazy("tracker:inbox")

    def get_queryset(self):
        # Only undecided vacancies; a stale tab must not dismiss an applied one.
        return super().get_queryset().filter(state=Vacancy.State.INBOX)

    def get_success_url(self):
        return inbox_return_url(self.request)

    def form_valid(self, form):
        form.instance.state = Vacancy.State.DISMISSED
        messages.info(self.request, f"Dismissed: {form.instance}.")
        return super().form_valid(form)


class VacancyRestoreView(OwnerQuerySetMixin, SingleObjectMixin, View):
    """ "Back to inbox" for a dismissed vacancy. Clears the dismissal, nothing else."""

    model = Vacancy
    http_method_names = ["post"]

    def get_queryset(self):
        return super().get_queryset().filter(state=Vacancy.State.DISMISSED)

    def post(self, request, *args, **kwargs):
        vacancy = self.get_object()
        vacancy.state = Vacancy.State.INBOX
        vacancy.dismiss_reason = ""
        vacancy.save(update_fields=["state", "dismiss_reason", "updated_at"])
        messages.info(request, f"Back in the inbox: {vacancy}.")
        return redirect(inbox_return_url(request))


# --- Applications ---


class ApplicationListView(OwnerQuerySetMixin, ListView):
    model = Application

    def get_queryset(self):
        queryset = super().get_queryset().select_related("vacancy__company").order_by("-applied_at")
        status = self.request.GET.get("status")
        if status in Application.Status.values:
            queryset = queryset.filter(status=status)
        elif self.request.GET.get("archive") != "1":
            queryset = queryset.exclude(status__in=Application.CLOSED_STATUSES)
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(vacancy__title__icontains=query) | Q(vacancy__company__name__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statuses"] = Application.Status.choices
        context["current_status"] = self.request.GET.get("status", "")
        context["query"] = self.request.GET.get("q", "")
        context["show_archive"] = self.request.GET.get("archive") == "1"
        return context


class ApplicationPageMixin(OwnerQuerySetMixin):
    """What the application page needs, shared by the page and its small forms."""

    model = Application
    template_name = "tracker/application_detail.html"

    def get_queryset(self):
        # select_related: the "one" side — vacancy, company, earlier attempt (JOIN).
        # prefetch_related: the "many" side — events, attachments, later attempts
        # (one extra query each).
        return (
            super()
            .get_queryset()
            .select_related("vacancy__company", "previous_attempt__vacancy")
            .prefetch_related(
                "events",
                "attachments",
                Prefetch("later_attempts", queryset=Application.objects.select_related("vacancy")),
            )
        )

    def get_context_data(self, **kwargs):
        # An invalid form arrives in kwargs and keeps its errors; the rest start empty.
        kwargs.setdefault("event_form", EventForm())
        kwargs.setdefault("status_form", StatusChangeForm(initial={"status": self.object.status}))
        kwargs.setdefault("attachment_form", AttachmentForm())
        return super().get_context_data(**kwargs)


class ApplicationDetailView(ApplicationPageMixin, DetailView):
    pass


class ApplicationActionView(ApplicationPageMixin, SingleObjectMixin, TemplateResponseMixin, View):
    """Base for the small POST-only forms on the application page.

    Valid form: do the action and redirect back (POST/redirect/GET).
    Invalid form: show the page again with that form's errors.
    """

    http_method_names = ["post"]
    form_class = None
    context_name = None

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.form_class(request.POST, request.FILES, **self.get_form_kwargs())
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(**{self.context_name: form}))
        self.act(form)
        return redirect(self.object)

    def get_form_kwargs(self):
        return {}

    def act(self, form):
        raise NotImplementedError


class ApplicationAddEventView(ApplicationActionView):
    form_class = EventForm
    context_name = "event_form"

    def act(self, form):
        event = form.save(commit=False)
        event.application = self.object
        event.save()


class ApplicationChangeStatusView(ApplicationActionView):
    form_class = StatusChangeForm
    context_name = "status_form"

    def get_form_kwargs(self):
        return {"current_status": self.object.status}

    def act(self, form):
        self.object.change_status(form.cleaned_data["status"], form.cleaned_data["comment"])


class ApplicationAddAttachmentView(ApplicationActionView):
    form_class = AttachmentForm
    context_name = "attachment_form"

    def act(self, form):
        attachment = form.save(commit=False)
        attachment.application = self.object
        attachment.save()


class AttachmentDownloadView(LoginRequiredMixin, View):
    """Serve an attachment only to its owner; a foreign or unknown pk is 404."""

    def get(self, request, pk):
        attachment = get_object_or_404(Attachment, pk=pk, application__owner=request.user)
        return FileResponse(attachment.file.open("rb"), filename=Path(attachment.file.name).name)
