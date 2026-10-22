from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class DashboardView(LoginRequiredMixin, TemplateView):
    # Placeholder page; the real dashboard context arrives in Task 13.
    template_name = "tracker/dashboard.html"
