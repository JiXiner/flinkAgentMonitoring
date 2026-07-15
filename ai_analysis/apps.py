import os
import sys

from django.apps import AppConfig


class AIAnalysisConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ai_analysis"
    verbose_name = "@Jix 智能分析"

    def ready(self):
        if len(sys.argv) > 1 and sys.argv[1] == "runserver":
            is_server_process = "--noreload" in sys.argv or os.environ.get("RUN_MAIN") == "true"
            if is_server_process:
                from .scheduler import inspection_scheduler

                inspection_scheduler.start()
