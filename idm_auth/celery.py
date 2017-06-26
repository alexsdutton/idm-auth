import os

from celery import Celery
from django.apps import apps
from django.conf import settings

app = Celery(__package__, broker=os.environ.get('CELERY_BROKER_URL'))

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings')
app.autodiscover_tasks(lambda: [n.name for n in apps.get_app_configs()])