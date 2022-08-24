from django.db import models

from river.models.fields.state import StateField


class DummyWorkFlow(models.Model):
    state = StateField()
