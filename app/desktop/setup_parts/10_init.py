from __future__ import annotations

class _SetupInitMixin:
    def __init__(self, current: DeploymentConfig | None = None, parent=None, role_locked: str | None = None):
        super().__init__(parent)
        self.current = current or DeploymentConfig()
        self.role_locked = str(role_locked or "").upper()
        if self.role_locked not in {SITE_SERVER, EDGE_NODE, OPERATOR_CLIENT}:
            self.role_locked = ""
        self.server_identity: dict = {}
        self.db_result: dict = {}
        self.setWindowTitle(f"{PRODUCT_NAME} Deployment Configuration")
        self.setMinimumSize(760, 560)

        self.welcome_page = self._welcome_page()
        self.role_page = self._role_page()
        self.connection_page = self._connection_page()
        self.requirements_page = self._requirements_page()
        self.network_page = self._network_page()
        self.database_page = self._database_page()
        self.admin_page = self._admin_page()
        self.review_page = self._review_page()
        self.welcome_id = self.addPage(self.welcome_page)
        self.role_id = self.addPage(self.role_page)
        self.connection_id = self.addPage(self.connection_page)
        self.requirements_id = self.addPage(self.requirements_page)
        self.network_id = self.addPage(self.network_page)
        self.database_id = self.addPage(self.database_page)
        self.admin_id = self.addPage(self.admin_page)
        self.review_id = self.addPage(self.review_page)
        if self.role_locked:
            locked_radio = {
                SITE_SERVER: self.server_radio,
                EDGE_NODE: self.node_radio,
                OPERATOR_CLIENT: self.client_radio,
            }[self.role_locked]
            locked_radio.setChecked(True)
            for radio in (self.server_radio, self.node_radio, self.client_radio):
                radio.setEnabled(False)
            self.role_page.setSubTitle(
                f"This installer is locked to {locked_radio.text()}. The role cannot be changed from this package."
            )
            # The normal desktop launch keeps the three-role page. Dedicated
            # installers start directly in their selected role's workflow.
            self.setStartId(self.connection_id if self.role_locked == OPERATOR_CLIENT else self.requirements_id)
