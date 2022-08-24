from .base import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    },
}

INSTALLED_APPS += (
    'river.tests',
)

# if django.get_version() >= '1.9.0':
#     MIGRATION_MODULES = DisableMigrations()

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'EXCEPTION_HANDLER': 'river_admin.views.exception_handler'
}


STATIC_ROOT = "static_root"
STATIC_URL = "static/"
