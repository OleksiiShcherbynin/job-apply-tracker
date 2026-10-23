from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from .forms import CompanyForm
from .mixins import OwnerFormMixin, OwnerQuerySetMixin
from .models import Company


class DashboardView(LoginRequiredMixin, TemplateView):
    # Placeholder page; the real dashboard context arrives in Task 13.
    template_name = "tracker/dashboard.html"


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
