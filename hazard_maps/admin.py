from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from .models import HazardDataset, FloodSusceptibility, LandslideSusceptibility, LiquefactionSusceptibility

@admin.register(HazardDataset)
class HazardDatasetAdmin(admin.ModelAdmin):
    list_display = ['name', 'dataset_type', 'upload_date', 'file_name']
    list_filter = ['dataset_type', 'upload_date']
    search_fields = ['name', 'file_name']
    readonly_fields = ['upload_date']

@admin.register(FloodSusceptibility)
class FloodSusceptibilityAdmin(GISModelAdmin):
    list_display = ['flood_susc', 'original_code', 'dataset', 'orig_fid']
    list_filter = ['flood_susc', 'dataset']
    search_fields = ['orig_fid']

@admin.register(LandslideSusceptibility) 
class LandslideSusceptibilityAdmin(GISModelAdmin):
    list_display = ['landslide_susc', 'original_code', 'dataset', 'orig_fid']
    list_filter = ['landslide_susc', 'dataset']
    search_fields = ['orig_fid']

@admin.register(LiquefactionSusceptibility)
class LiquefactionSusceptibilityAdmin(GISModelAdmin):
    list_display = ['liquefaction_susc', 'original_code', 'dataset']
    list_filter = ['liquefaction_susc', 'dataset']

from .models import Facility

@admin.register(Facility)
class FacilityAdmin(GISModelAdmin):
    list_display = ['name', 'facility_type', 'category', 'osm_id']
    list_filter = ['category', 'facility_type']
    search_fields = ['name']