from django.db import models

from .fields import EncryptedTextField


class Server(models.Model):
    name = models.CharField(max_length=100)
    ip = models.GenericIPAddressField(default="127.0.0.1")
    port = models.PositiveIntegerField(default=22)
    username = models.CharField(max_length=100, blank=True)
    password = EncryptedTextField(blank=True)
    is_local = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    description = models.CharField(max_length=255, blank=True)
    last_status = models.CharField(max_length=20, default="unknown")
    last_error = models.CharField(max_length=500, blank=True)
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_local", "name"]
        indexes = [models.Index(fields=["enabled", "is_local"])]

    def __str__(self):
        return self.name


class MetricRecord(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="metrics")
    cpu = models.FloatField()
    memory = models.FloatField()
    disk = models.FloatField()
    network_in = models.FloatField(default=0)
    network_out = models.FloatField(default=0)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["server", "-timestamp"])]


class AIReport(models.Model):
    LEVELS = (("info", "正常"), ("warning", "警告"), ("critical", "严重"))

    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="ai_reports", null=True, blank=True)
    level = models.CharField(max_length=20, choices=LEVELS, default="info")
    problem = models.CharField(max_length=500, blank=True)
    content = models.JSONField(default=dict)
    created_time = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_time"]
