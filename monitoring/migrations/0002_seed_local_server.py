from django.db import migrations


def seed_local_server(apps, schema_editor):
    Server = apps.get_model("monitoring", "Server")
    Server.objects.get_or_create(
        is_local=True,
        defaults={
            "name": "本机节点",
            "ip": "127.0.0.1",
            "port": 22,
            "description": "Flink-Agent 本机采集节点",
            "last_status": "online",
        },
    )


class Migration(migrations.Migration):
    dependencies = [("monitoring", "0001_initial")]
    operations = [migrations.RunPython(seed_local_server, migrations.RunPython.noop)]
