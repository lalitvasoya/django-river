from django.db import models

from river.models.fields.state import StateField
from river.models.workflow import Workflow


class DummyWorkFlow(models.Model):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, default=Workflow.objects.first().id)
    state = StateField()
