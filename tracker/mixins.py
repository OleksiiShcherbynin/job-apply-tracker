from django.contrib.auth.mixins import LoginRequiredMixin


class OwnerQuerySetMixin(LoginRequiredMixin):
    """Restrict a view to the logged-in user's rows.

    Detail/update/delete views look the object up inside get_queryset(),
    so another user's pk simply isn't found: 404, not someone else's data.
    """

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)


class OwnerFormMixin:
    """Hand the logged-in user to an OwnedModelForm as `owner`."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["owner"] = self.request.user
        return kwargs
