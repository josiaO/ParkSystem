from __future__ import annotations

class LocalMediaGateway(_GatewayStateMixin, _GatewayFramesMixin, _GatewayProducersMixin):
    """Stable media gateway facade composed from subsystem mixins."""


gateway = LocalMediaGateway()
