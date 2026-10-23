from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)
from django.views.generic.detail import SingleObjectMixin

from .forms import ApplyForm, CompanyForm, DismissForm, VacancyForm
from .mixins import OwnerFormMixin, OwnerQuerySetMixin
from .models import Application, Attachment, Company, Vacancy


class DashboardView(LoginRequiredMixin, TemplateView):
    # Placeholder page; the real dashboard context arrives in Task 13.
    template_name = "tracker/dashboard.html"


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


class InboxView(OwnerQuerySetMixin, ListView):
    model = Vacancy
    template_name = "tracker/inbox.html"

    def get_queryset(self):
        # select_related: fetch each vacancy's company in the same query (JOIN),
        # otherwise the template's {{ vacancy.company }} costs one query per row.
        return super().get_queryset().inbox().select_related("company")


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
    success_url = reverse_lazy("tracker:vacancy_list")

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f"{self.object} has an application — its history would be lost.",
            )
            return redirect("tracker:vacancy_list")


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

    def redirect_if_applied(self):
        # One application per vacancy (OneToOne): a second click or a stale
        # tab must land on the existing one, not crash on IntegrityError.
        existing = Application.objects.filter(vacancy=self.object).first()
        return redirect(existing) if existing else None

    def form_valid(self, form):
        data = form.cleaned_data
        with transaction.atomic():
            application = self.object.mark_applied(data["applied_at"], data["notes"])
            if data["file"]:
                Attachment.objects.create(
                    application=application,
                    file=data["file"],
                    label=data["label"] or data["file"].name,
                )
        messages.success(self.request, f"Applied: {self.object}.")
        return redirect(application)


class VacancyDismissView(OwnerQuerySetMixin, UpdateView):
    """The "Dismiss" button. POST only: it changes data (see lesson 1)."""

    model = Vacancy
    form_class = DismissForm
    http_method_names = ["post"]
    success_url = reverse_lazy("tracker:inbox")

    def form_valid(self, form):
        form.instance.state = Vacancy.State.DISMISSED
        messages.info(self.request, f"Dismissed: {form.instance}.")
        return super().form_valid(form)


# --- Applications ---


class ApplicationDetailView(OwnerQuerySetMixin, DetailView):
    # Minimal page so "Applied" has somewhere to land; Task 12 adds the
    # timeline forms, status change and attachment upload.
    model = Application
