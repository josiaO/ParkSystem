from __future__ import annotations

class SetupWizard(_SetupInitMixin, _SetupPagesMixin, _SetupValidationMixin, _SetupNavigationMixin, QWizard):
    """Deployment wizard facade composed from page, validation and navigation subsystems."""
