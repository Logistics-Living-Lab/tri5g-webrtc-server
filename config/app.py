from middleware.auth import Auth
from services.connection_manager import ConnectionManager
from services.telemetry_service import TelemetryService
from video.detection_service import DetectionService


class App:
    detection_service: DetectionService | None = None
    telemetry_service: TelemetryService | None = None
    connection_manager: ConnectionManager | None = None
    auth_service: Auth | None = None
