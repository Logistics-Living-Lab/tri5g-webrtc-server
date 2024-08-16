import os


class AppConfig:
    root_path = ""
    damage_detection_model_file: str = ""

    @staticmethod
    def records_directory():
        return os.path.join(AppConfig.root_path, "records")
