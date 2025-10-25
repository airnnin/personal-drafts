from django.apps import AppConfig
from django.core.management import call_command
from django.db.utils import ProgrammingError, OperationalError

class HazardMapsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hazard_maps'

    def ready(self):
        # Automatically create cache table if missing
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT to_regclass('public.osrm_cache_table');
                """)
                exists = cursor.fetchone()[0]
                if not exists:
                    print("⚙️ Creating missing cache table: osrm_cache_table")
                    call_command('createcachetable', 'osrm_cache_table')
        except (ProgrammingError, OperationalError):
            # Database might not be ready during migrations
            pass