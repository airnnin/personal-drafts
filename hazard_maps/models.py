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
        ('municipality_characteristics', 'Municipality Characteristics'),
        ('barangay_characteristics', 'Barangay Characteristics'), 
    ]
    
    name = models.CharField(max_length=200)
    dataset_type = models.CharField(max_length=50, choices=DATASET_TYPES)
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


class BarangayBoundaryNew(models.Model):
    """
    NEW: Barangay boundaries from PSA-NAMRIA (HumData)
    Source: https://data.humdata.org/dataset/cod-ab-phl
    Coverage: Entire Philippines (filtered for Negros Oriental)
    """
    dataset = models.ForeignKey(HazardDataset, on_delete=models.CASCADE)
    
    # Administrative hierarchy (from dataset fields)
    objectid = models.IntegerField(null=True, blank=True)
    
    # Barangay (ADM4)
    adm4_en = models.CharField(max_length=100)  # Barangay name (e.g., "Daro")
    adm4_pcode = models.CharField(max_length=50)  # Barangay code (e.g., "PH0102801001")
    
    # Municipality/City (ADM3)
    adm3_en = models.CharField(max_length=100)  # Municipality name (e.g., "Dumaguete City")
    adm3_pcode = models.CharField(max_length=50)  # Municipality code
    
    # Province (ADM2)
    adm2_en = models.CharField(max_length=100)  # Province name (e.g., "Negros Oriental")
    adm2_pcode = models.CharField(max_length=50)  # Province code
    
    # Region (ADM1)
    adm1_en = models.CharField(max_length=100)  # Region name (e.g., "Region VII")
    adm1_pcode = models.CharField(max_length=50)  # Region code
    
    # Country (ADM0)
    adm0_en = models.CharField(max_length=100, default="Philippines")
    adm0_pcode = models.CharField(max_length=10, default="PH")
    
    # Metadata
    date = models.DateField(null=True, blank=True)
    valid_on = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    
    # Area measurements
    shape_length = models.FloatField(null=True, blank=True)
    shape_area = models.FloatField(null=True, blank=True)
    area_sqkm = models.FloatField(null=True, blank=True)  # IMPORTANT: Area in square kilometers
    
    # Geometry
    geometry = models.MultiPolygonField(srid=4326)
    
    class Meta:
        indexes = [
            models.Index(fields=['adm4_en']),  # Barangay name
            models.Index(fields=['adm3_en']),  # Municipality
            models.Index(fields=['adm2_en']),  # Province
            models.Index(fields=['adm4_pcode']),  # Barangay code
        ]
        verbose_name = "Barangay Boundary (PSA-NAMRIA)"
        verbose_name_plural = "Barangay Boundaries (PSA-NAMRIA)"
    
    def __str__(self):
        return f"{self.adm4_en}, {self.adm3_en}, {self.adm2_en}"
    


class MunicipalityCharacteristic(models.Model):
    """Model for municipality socioeconomic characteristics"""
    dataset = models.ForeignKey(HazardDataset, on_delete=models.CASCADE)
    
    # LGU Information
    lgu_name = models.CharField(max_length=100)  # e.g., "Amlan"
    correspondence_code = models.CharField(max_length=50, unique=True)  # e.g., "PH0704601"
    
    # Classification
    category = models.CharField(max_length=100)  # e.g., "Fourth Class Municipality"
    score = models.FloatField(null=True, blank=True)
    
    # Population Data
    population = models.IntegerField()
    population_weight = models.FloatField(null=True, blank=True)  # Percentage
    
    # Revenue Data
    revenue = models.DecimalField(max_digits=15, decimal_places=2)
    revenue_weight = models.FloatField(null=True, blank=True)  # Percentage
    
    # Composite Metrics
    total_percentage = models.FloatField(null=True, blank=True)
    provincial_score = models.FloatField(null=True, blank=True)
    
    # Poverty Data
    poverty_incidence_rate = models.FloatField(null=True, blank=True)  # Percentage
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Municipality Characteristic"
        verbose_name_plural = "Municipality Characteristics"
        indexes = [
            models.Index(fields=['correspondence_code']),
            models.Index(fields=['lgu_name']),
        ]
    
    def __str__(self):
        return f"{self.lgu_name} ({self.category})"
    
    def get_revenue_display(self):
        """Format revenue with PHP symbol and commas"""
        return f"₱{self.revenue:,.2f}"
    
    def get_population_display(self):
        """Format population with commas"""
        return f"{self.population:,}"


class BarangayCharacteristic(models.Model):
    """Model for barangay-level characteristics and infrastructure"""
    dataset = models.ForeignKey(HazardDataset, on_delete=models.CASCADE)
    
    # Barangay Identification
    barangay_name = models.CharField(max_length=100)
    barangay_code = models.CharField(max_length=50, unique=True, db_index=True)
    
    # Population Data
    population = models.IntegerField(null=True, blank=True)
    
    # Geographic & Development Characteristics
    LANDSCAPE_CHOICES = [
        ('Coastal', 'Coastal'),
        ('Lowland', 'Lowland'),
        ('Upland', 'Upland'),
        ('Urban', 'Urban'),
        ('Rural', 'Rural'),
    ]
    ecological_landscape = models.CharField(max_length=50, choices=LANDSCAPE_CHOICES, null=True, blank=True)
    
    URBANIZATION_CHOICES = [
        ('Urban', 'Urban'),
        ('Rural', 'Rural'),
        ('Not Yet Identified', 'Not Yet Identified'),
    ]
    urbanization = models.CharField(max_length=50, choices=URBANIZATION_CHOICES, null=True, blank=True)
    
    # Infrastructure & Services
    YES_NO_CHOICES = [
        ('Yes', 'Yes'),
        ('No', 'No'),
    ]
    cellular_signal = models.CharField(max_length=10, choices=YES_NO_CHOICES, null=True, blank=True)  # CHANGED
    public_street_sweeper = models.CharField(max_length=10, choices=YES_NO_CHOICES, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Barangay Characteristic"
        verbose_name_plural = "Barangay Characteristics"
        indexes = [
            models.Index(fields=['barangay_code']),
            models.Index(fields=['barangay_name']),
        ]
    
    def __str__(self):
        return f"{self.barangay_name} ({self.barangay_code})"
    
    def get_population_display(self):
        """Format population with commas"""
        if self.population:
            return f"{self.population:,}"
        return "N/A"
    
    def get_landscape_icon(self):
        """Return emoji icon for landscape type"""
        icons = {
            'Coastal': '🏖️',
            'Lowland': '🌾',
            'Upland': '⛰️',
            'Urban': '🏙️',
            'Rural': '🌳',
        }
        return icons.get(self.ecological_landscape, '📍')
    
    def get_urbanization_icon(self):
        """Return emoji icon for urbanization level"""
        icons = {
            'Urban': '🏙️',
            'Rural': '🌾',
            'Not Yet Identified': '❓',
        }
        return icons.get(self.urbanization, '📍')


class ZonalValue(models.Model):
    """Model for land zonal values (price per sqm) by barangay"""
    dataset = models.ForeignKey(HazardDataset, on_delete=models.CASCADE)
    
    # Location Information
    barangay_name = models.CharField(max_length=100)
    barangay_code = models.CharField(max_length=50, db_index=True)  # Links to BarangayBoundaryNew.adm4_pcode
    municipality = models.CharField(max_length=100)
    
    # Location Details
    street = models.CharField(max_length=200, blank=True, null=True)
    vicinity = models.CharField(max_length=200, blank=True, null=True)
    
    # Zonal Classification
    CLASS_CHOICES = [
        ('Residential', 'Residential'),
        ('Commercial', 'Commercial'),
        ('Industrial', 'Industrial'),
        ('Agricultural', 'Agricultural'),
        ('Special', 'Special'),
    ]
    land_class = models.CharField(max_length=50, choices=CLASS_CHOICES, blank=True, null=True)
    
    # Price Information
    price_per_sqm = models.DecimalField(max_digits=12, decimal_places=2)  # Price in PHP
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Zonal Value"
        verbose_name_plural = "Zonal Values"
        indexes = [
            models.Index(fields=['barangay_code']),
            models.Index(fields=['barangay_name']),
            models.Index(fields=['municipality']),
        ]
        ordering = ['barangay_name', 'street']
    
    def __str__(self):
        return f"{self.barangay_name} - {self.street or 'General'} (₱{self.price_per_sqm}/sqm)"
    
    def get_price_display(self):
        """Format price with PHP symbol and commas"""
        return f"₱{self.price_per_sqm:,.2f}"
    
    def get_price_per_sqm_formatted(self):
        """Format price per sqm for display"""
        return f"₱{self.price_per_sqm:,.2f}/m²"



