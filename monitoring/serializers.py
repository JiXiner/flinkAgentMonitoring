from rest_framework import serializers

from .models import AIReport, Server


class ServerSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Server
        fields = (
            "id", "name", "ip", "port", "username", "password", "is_local",
            "enabled", "description", "last_status", "last_error", "updated_time",
        )
        read_only_fields = ("is_local", "last_status", "last_error", "updated_time")

    def update(self, instance, validated_data):
        if not validated_data.get("password"):
            validated_data.pop("password", None)
        return super().update(instance, validated_data)


class AIReportSerializer(serializers.ModelSerializer):
    server_name = serializers.CharField(source="server.name", read_only=True)

    class Meta:
        model = AIReport
        fields = ("id", "server", "server_name", "level", "problem", "content", "created_time")
