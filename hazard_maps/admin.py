from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from .models import HazardDataset, FloodSusceptibility, LandslideSusceptibility, LiquefactionSusceptibility, BarangayBoundaryNew, MunicipalityCharacteristic, BarangayCharacteristic, ZonalValue

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


@admin.register(BarangayBoundaryNew)
class BarangayBoundaryNewAdmin(GISModelAdmin):
    list_display = ['adm4_en', 'adm3_en', 'adm2_en', 'area_sqkm', 'dataset']
    list_filter = ['adm3_en', 'adm2_en', 'dataset']
    search_fields = ['adm4_en', 'adm3_en', 'adm4_pcode']
    
    fieldsets = (
        ('Barangay Information', {
            'fields': ('adm4_en', 'adm4_pcode', 'area_sqkm')
        }),
        ('Administrative Hierarchy', {
            'fields': ('adm3_en', 'adm3_pcode', 'adm2_en', 'adm2_pcode', 'adm1_en', 'adm1_pcode')
        }),
        ('Metadata', {
            'fields': ('dataset', 'date', 'valid_on', 'valid_to', 'objectid')
        }),
        ('Geometry', {
            'fields': ('geometry', 'shape_length', 'shape_area')
        }),
    )


@admin.register(MunicipalityCharacteristic)
class MunicipalityCharacteristicAdmin(admin.ModelAdmin):
    list_display = ['lgu_name', 'category', 'population', 'provincial_score', 'poverty_incidence_rate']
    list_filter = ['category', 'dataset']
    search_fields = ['lgu_name', 'correspondence_code']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('dataset', 'lgu_name', 'correspondence_code', 'category', 'score')
        }),
        ('Population Data', {
            'fields': ('population', 'population_weight')
        }),
        ('Revenue Data', {
            'fields': ('revenue', 'revenue_weight')
        }),
        ('Composite Metrics', {
            'fields': ('total_percentage', 'provincial_score', 'poverty_incidence_rate')
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )

@admin.register(BarangayCharacteristic)
class BarangayCharacteristicAdmin(admin.ModelAdmin):
    list_display = ['barangay_name', 'barangay_code', 'population', 'ecological_landscape', 'urbanization', 'cellular_signal']
    list_filter = ['ecological_landscape', 'urbanization', 'cellular_signal', 'public_street_sweeper', 'dataset']
    search_fields = ['barangay_name', 'barangay_code']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('dataset', 'barangay_name', 'barangay_code', 'population')
        }),
        ('Geographic Characteristics', {
            'fields': ('ecological_landscape', 'urbanization')
        }),
        ('Infrastructure & Services', {
            'fields': ('cellular_signal', 'public_street_sweeper')
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )

@admin.register(ZonalValue)
class ZonalValueAdmin(admin.ModelAdmin):
    list_display = ['barangay_name', 'municipality', 'street', 'land_class', 'price_per_sqm', 'get_price_display']
    list_filter = ['municipality', 'land_class', 'dataset']
    search_fields = ['barangay_name', 'barangay_code', 'street', 'vicinity']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Location Information', {
            'fields': ('dataset', 'barangay_name', 'barangay_code', 'municipality')
        }),
        ('Location Details', {
            'fields': ('street', 'vicinity', 'land_class')
        }),
        ('Price Information', {
            'fields': ('price_per_sqm',)
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )
    
    def get_price_display(self, obj):
        return obj.get_price_display()
    get_price_display.short_description = 'Price Display'