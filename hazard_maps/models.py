from django.contrib.gis.db import models

class HazardDataset(models.Model):
    """Model to track uploaded datasets"""
    DATASET_TYPES = [
        ('flood', 'Flood Susceptibility'),
        ('landslide', 'Landslide Susceptibility'),
        ('liquefaction', 'Liquefaction Susceptibility'),
        ('sea_level_rise', 'Sea Level Rise'),
        ('zonal_values', 'Zonal Values'),
        ('barangay', 'Barangay Boundaries'),  # NEW: Add this line
    ]
    
    name = models.CharField(max_length=200)
    dataset_type = models.CharField(max_length=20, choices=DATASET_TYPES)
    upload_date = models.DateTimeField(auto_now_add=True)
    file_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_dataset_type_display()})"

class FloodSusceptibility(models.Model):
    """Model for flood susceptibility data"""
    SUSCEPTIBILITY_LEVELS = [
        ('LS', 'Low Susceptibility'),
        ('MS', 'Moderate Susceptibility'),
        ('HS', 'High Susceptibility'),
        ('VHS', 'Very High Susceptibility'),
    ]
    
    dataset = models.ForeignKey(HazardDataset, on_delete=models.CASCADE)
    flood_susc = models.CharField(max_length=3, choices=SUSCEPTIBILITY_LEVELS)
    original_code = models.CharField(max_length=10)
    shape_length = models.FloatField(null=True, blank=True)
    shape_area = models.FloatField(null=True, blank=True)
    orig_fid = models.IntegerField(null=True, blank=True)
    geometry = models.MultiPolygonField(srid=4326)
    
    def __str__(self):
        return f"Flood {self.flood_susc} - FID: {self.orig_fid}"

class LandslideSusceptibility(models.Model):
    """Model for landslide susceptibility data"""
    SUSCEPTIBILITY_LEVELS = [
        ('LS', 'Low Susceptibility'),
        ('MS', 'Moderate Susceptibility'),
        ('HS', 'High Susceptibility'),
        ('VHS', 'Very High Susceptibility'),
        ('DF', 'Debris Flow - Critical Risk'),  # FIXED LABEL
    ]
    
    dataset = models.ForeignKey(HazardDataset, on_delete=models.CASCADE)
    landslide_susc = models.CharField(max_length=3, choices=SUSCEPTIBILITY_LEVELS)
    original_code = models.CharField(max_length=10)
    shape_length = models.FloatField(null=True, blank=True)
    shape_area = models.FloatField(null=True, blank=True)
    orig_fid = models.IntegerField(null=True, blank=True)
    geometry = models.MultiPolygonField(srid=4326)
    
    def __str__(self):
        return f"Landslide {self.landslide_susc} - FID: {self.orig_fid}"

class LiquefactionSusceptibility(models.Model):
    """Model for liquefaction susceptibility data"""
    SUSCEPTIBILITY_LEVELS = [
        ('LS', 'Low Susceptibility'),
        ('MS', 'Moderate Susceptibility'),
        ('HS', 'High Susceptibility'),
    ]
    
    dataset = models.ForeignKey(HazardDataset, on_delete=models.CASCADE)
    liquefaction_susc = models.CharField(max_length=3, choices=SUSCEPTIBILITY_LEVELS)
    original_code = models.CharField(max_length=50)
    geometry = models.MultiPolygonField(srid=4326)
    
    def __str__(self):
        return f"Liquefaction {self.liquefaction_susc}"

class Facility(models.Model):
    """Model for storing facility data (optional caching of OSM data)"""
    CATEGORY_CHOICES = [
        ('emergency', 'Emergency & Disaster-Related'),
        ('everyday', 'Everyday Life & Livability'),
        ('government', 'Government & Administrative'),
    ]
    
    name = models.CharField(max_length=200)
    facility_type = models.CharField(max_length=50)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    location = models.PointField(srid=4326)
    osm_id = models.BigIntegerField(unique=True)
    osm_type = models.CharField(max_length=10)  # node, way, relation
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['facility_type']),
            models.Index(fields=['category']),
            models.Index(fields=['osm_id']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.facility_type})"

class BarangayBoundary(models.Model):
    """Model for barangay boundary data"""
    dataset = models.ForeignKey(HazardDataset, on_delete=models.CASCADE)
    
    # Basic identifiers
    brgy_id = models.BigIntegerField()
    brgycode = models.CharField(max_length=20)
    b_name = models.CharField(max_length=100)  # Barangay name
    lgu_name = models.CharField(max_length=100)  # Municipality/City name
    
    # Area measurements
    area_has = models.FloatField(null=True, blank=True)  # Area in hectares
    area = models.FloatField(null=True, blank=True)
    perimeter = models.FloatField(null=True, blank=True)
    hectares = models.FloatField(null=True, blank=True)
    area_nso = models.FloatField(null=True, blank=True)
    
    # Additional data
    district = models.IntegerField(null=True, blank=True)
    pop_2020 = models.IntegerField(null=True, blank=True)  # Population 2020
    nsodata = models.CharField(max_length=100, null=True, blank=True)
    
    # Geometry
    geometry = models.MultiPolygonField(srid=4326)
    
    class Meta:
        indexes = [
            models.Index(fields=['brgy_id']),
            models.Index(fields=['b_name']),
            models.Index(fields=['lgu_name']),
        ]
    
    def __str__(self):
        return f"{self.b_name}, {self.lgu_name}"