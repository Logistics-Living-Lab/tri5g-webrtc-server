from services.message_service import MessageService
from video.detection_service import DetectionService


class App:
    detection_service: DetectionService | None = None
    message_service: MessageService | None = None
