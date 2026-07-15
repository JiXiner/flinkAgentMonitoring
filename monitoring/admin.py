from django.contrib import admin

from .models import AIReport, MetricRecord, Server


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ("name", "ip", "port", "is_local", "enabled", "last_status")
    exclude = ("password",)


admin.site.register(MetricRecord)
admin.site.register(AIReport)
