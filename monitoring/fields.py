import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


class EncryptedTextField(models.TextField):
    prefix = "enc::"

    @staticmethod
    def _fernet():
        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value or value.startswith(self.prefix):
            return value
        token = self._fernet().encrypt(value.encode("utf-8")).decode("ascii")
        return f"{self.prefix}{token}"

    def from_db_value(self, value, expression, connection):
        if not value or not value.startswith(self.prefix):
            return value
        try:
            return self._fernet().decrypt(value[len(self.prefix):].encode("ascii")).decode("utf-8")
        except InvalidToken:
            return ""

    def to_python(self, value):
        return value
