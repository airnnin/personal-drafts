import fiona
import zipfile
import os
import tempfile
import requests
import time
from typing import Dict, Optional, List, Tuple
import time
from django.core.cache import cache
from math import radians, cos, sin, asin, sqrt
import hashlib
from django.contrib.gis.geos import GEOSGeometry, Point
from django.contrib.gis.measure import D
from fiona.io import ZipMemoryFile
from .models import HazardDataset, FloodSusceptibility, LandslideSusceptibility, LiquefactionSusceptibility
import json
import csv
from decimal import Decimal


class ShapefileProcessor:
    """Process and standardize shapefile data"""
    
    FLOOD_MAPPING = {
        'LF': 'LS',
        'MF': 'MS',
        'ML': 'MS',
        'HF': 'HS',
        'VHF': 'VHS'
    }
    
    LANDSLIDE_MAPPING = {
        'LL': 'LS',
        'ML': 'MS',
        'HL': 'HS',
        'VHL': 'VHS',
        'DF': 'DF'
    }
    
    LIQUEFACTION_MAPPING = {
        'Low Susceptibility': 'LS',
        'Moderate Susceptibility': 'MS', 
        'High Susceptibility': 'HS',
        'Low susceptibility': 'LS',
        'Moderate susceptibility': 'MS',
        'High susceptibility': 'HS'
    }
    
    def __init__(self, uploaded_file, dataset_type):
        self.uploaded_file = uploaded_file
        self.dataset_type = dataset_type
        self.temp_dir = None
        
    
    def standardize_code(self, original_code, dataset_type):
        """Standardize susceptibility codes based on dataset type"""
        original_code = str(original_code).strip()
        
        if dataset_type == 'flood':
            return self.FLOOD_MAPPING.get(original_code, original_code)
        elif dataset_type == 'landslide':
            return self.LANDSLIDE_MAPPING.get(original_code, original_code)
        elif dataset_type == 'liquefaction':
            for key, value in self.LIQUEFACTION_MAPPING.items():
                if original_code.lower() == key.lower():
                    return value
            return 'LS'
        
        return original_code
    
    def transform_geometry(self, geom_dict, source_crs):
        """Transform geometry from PRS92/Luzon 1911 to WGS84"""
        try:
            if hasattr(geom_dict, '__geo_interface__'):
                geom_data = geom_dict.__geo_interface__
            else:
                geom_data = geom_dict
            
            geometry = GEOSGeometry(json.dumps(geom_data))
            
            # Check CRS - EPSG:4253 is PRS92 (Philippine Reference System 1992)
            # which is based on Luzon 1911 datum and needs transformation
            crs_string = str(source_crs).upper() if source_crs else ''
            
            # Check if CRS is 4253 or mentions Luzon
            if '4253' in crs_string or 'LUZON' in crs_string or 'PRS92' in crs_string:
                print(f"Transforming from EPSG:4253 (PRS92/Luzon 1911) to WGS84")
                geometry.srid = 4253
                geometry.transform(4326)
            else:
                print(f"Data already in WGS84 or unknown CRS")
                geometry.srid = 4326
            
            if geometry.geom_type == 'Polygon':
                from django.contrib.gis.geos import MultiPolygon
                geometry = MultiPolygon(geometry)
            
            return geometry
            
        except Exception as e:
            print(f"Geometry transformation error: {e}")
            print(f"Source CRS: {source_crs}")
            raise
        
    def process_flood_data(self, shp_file, dataset):
        """Process flood susceptibility shapefile"""
        records_created = 0
        errors = []
        
        try:
            with fiona.open(shp_file) as shapefile:
                print(f"Shapefile CRS: {shapefile.crs}")
                print(f"Total features: {len(shapefile)}")
                
                for idx, feature in enumerate(shapefile):
                    try:
                        props = feature['properties']
                        geom = feature['geometry']
                        
                        if geom is None:
                            continue
                        
                        original_code = props.get('FloodSusc', '')
                        standardized_code = self.standardize_code(original_code, 'flood')
                        geometry = self.transform_geometry(geom, shapefile.crs)
                        
                        FloodSusceptibility.objects.create(
                            dataset=dataset,
                            flood_susc=standardized_code,
                            original_code=original_code,
                            shape_length=props.get('SHAPE_Leng'),
                            shape_area=props.get('SHAPE_Area'),
                            orig_fid=props.get('ORIG_FID'),
                            geometry=geometry
                        )
                        records_created += 1
                        
                        if records_created % 100 == 0:
                            print(f"Processed {records_created} features...")
                        
                    except Exception as feature_error:
                        error_msg = f"Error processing feature {idx}: {feature_error}"
                        print(error_msg)
                        errors.append(error_msg)
                        continue
                        
        except Exception as file_error:
            print(f"Error opening shapefile: {file_error}")
            raise
        
        return records_created
    
    def process_landslide_data(self, shp_file, dataset):
        """Process landslide susceptibility shapefile"""
        records_created = 0
        
        with fiona.open(shp_file) as shapefile:
            print(f"Processing landslide - CRS: {shapefile.crs}")
            
            for idx, feature in enumerate(shapefile):
                try:
                    props = feature['properties']
                    geom = feature['geometry']
                    
                    if geom is None:
                        continue
                    
                    original_code = props.get('LndslideSu') or props.get('LndSu', '')
                    standardized_code = self.standardize_code(original_code, 'landslide')
                    geometry = self.transform_geometry(geom, shapefile.crs)
                    
                    LandslideSusceptibility.objects.create(
                        dataset=dataset,
                        landslide_susc=standardized_code,
                        original_code=original_code,
                        shape_length=props.get('SHAPE_Leng'),
                        shape_area=props.get('SHAPE_Area'),
                        orig_fid=props.get('ORIG_FID'),
                        geometry=geometry
                    )
                    records_created += 1
                    
                except Exception as e:
                    print(f"Error processing landslide feature {idx}: {e}")
                    continue
                
        return records_created
    
    def process_liquefaction_data(self, shp_file, dataset):
        """Process liquefaction susceptibility shapefile"""
        records_created = 0
        
        with fiona.open(shp_file) as shapefile:
            print(f"Processing liquefaction - CRS: {shapefile.crs}")
            
            for idx, feature in enumerate(shapefile):
                try:
                    props = feature['properties']
                    geom = feature['geometry']
                    
                    if geom is None:
                        continue
                    
                    original_code = props.get('Susceptibi', '').strip()
                    standardized_code = self.standardize_code(original_code, 'liquefaction')
                    geometry = self.transform_geometry(geom, shapefile.crs)
                    
                    LiquefactionSusceptibility.objects.create(
                        dataset=dataset,
                        liquefaction_susc=standardized_code,
                        original_code=original_code,
                        geometry=geometry
                    )
                    records_created += 1
                    
                except Exception as e:
                    print(f"Error processing liquefaction feature {idx}: {e}")
                    continue
                
        return records_created


    def process_barangay_gdb(self, gdb_path, dataset):
        """
        Process File Geodatabase (.gdb) containing barangay boundaries
        Filters for Negros Oriental only
        
        Args:
            gdb_path: Path to the .gdb directory
            dataset: HazardDataset instance
        
        Returns:
            Number of records created
        """
        from .models import BarangayBoundaryNew
        from datetime import datetime
        
        records_created = 0
        skipped_records = 0
        
        # CRITICAL: The exact layer name for barangay boundaries (ADM4)
        # If this doesn't work, we'll need to list all layers
        layer_name = "phl_admbnda_adm4_psa_namria_20231106"
        
        print(f"\n{'='*60}")
        print(f"🔍 PROCESSING FILE GEODATABASE")
        print(f"{'='*60}")
        print(f"📂 GDB Path: {gdb_path}")
        
        try:
            # First, list all available layers
            print(f"\n📋 Listing all layers in GDB...")
            import fiona
            layers = fiona.listlayers(gdb_path)
            print(f"✅ Found {len(layers)} layers:")
            for i, layer in enumerate(layers, 1):
                print(f"   {i}. {layer}")
            
            # Find the barangay layer (ADM4)
            target_layer = None
            for layer in layers:
                if 'adm4' in layer.lower():
                    target_layer = layer
                    print(f"\n🎯 Target layer identified: {target_layer}")
                    break
            
            if not target_layer:
                raise ValueError(
                    f"❌ Could not find barangay layer (ADM4) in GDB. "
                    f"Available layers: {', '.join(layers)}"
                )
            
            # Open and process the layer
            print(f"\n📖 Opening layer: {target_layer}")
            
            with fiona.open(gdb_path, layer=target_layer) as shapefile:
                print(f"✅ Successfully opened layer!")
                print(f"📊 CRS: {shapefile.crs}")
                print(f"📈 Total features: {len(shapefile)}")
                
                # Print sample feature to understand structure
                print(f"\n🔍 Inspecting first feature...")
                first_feature = next(iter(shapefile))
                print(f"📝 Sample properties: {list(first_feature['properties'].keys())}")
                
                print(f"\n{'='*60}")
                print(f"🚀 STARTING IMPORT (Filtering for Negros Oriental)")
                print(f"{'='*60}\n")
                
                for idx, feature in enumerate(shapefile):
                    try:
                        props = feature['properties']
                        geom = feature['geometry']
                        
                        if geom is None:
                            print(f"⚠️ Feature {idx}: No geometry, skipping")
                            continue
                        
                        # 🔥 FILTER: Only process Negros Oriental barangays
                        province = str(props.get('ADM2_EN', '')).strip()
                        
                        if province != 'Negros Oriental':
                            skipped_records += 1
                            if skipped_records % 5000 == 0:
                                print(f"⏭️ Skipped {skipped_records} non-Negros Oriental records...")
                            continue
                        
                        # Extract and clean data
                        barangay_name = str(props.get('ADM4_EN', '')).strip()
                        municipality = str(props.get('ADM3_EN', '')).strip()
                        region = str(props.get('ADM1_EN', '')).strip()
                        
                        # Parse dates safely
                        def parse_date(date_field):
                            if not date_field:
                                return None
                            try:
                                if isinstance(date_field, str):
                                    # Remove timezone indicator and parse
                                    date_str = date_field.replace('Z', '').replace('+00:00', '')
                                    return datetime.fromisoformat(date_str).date()
                                return date_field
                            except Exception as date_error:
                                print(f"⚠️ Date parse error: {date_error}")
                                return None
                        
                        # Transform geometry
                        geometry = self.transform_geometry(geom, shapefile.crs)
                        
                        # Create barangay boundary record
                        BarangayBoundaryNew.objects.create(
                            dataset=dataset,
                            objectid=props.get('OBJECTID'),
                            
                            # Barangay (ADM4)
                            adm4_en=barangay_name,
                            adm4_pcode=str(props.get('ADM4_PCODE', '')),
                            
                            # Municipality (ADM3)
                            adm3_en=municipality,
                            adm3_pcode=str(props.get('ADM3_PCODE', '')),
                            
                            # Province (ADM2)
                            adm2_en=province,
                            adm2_pcode=str(props.get('ADM2_PCODE', '')),
                            
                            # Region (ADM1)
                            adm1_en=region,
                            adm1_pcode=str(props.get('ADM1_PCODE', '')),
                            
                            # Country (ADM0)
                            adm0_en=str(props.get('ADM0_EN', 'Philippines')),
                            adm0_pcode=str(props.get('ADM0_PCODE', 'PH')),
                            
                            # Dates
                            date=parse_date(props.get('date')),
                            valid_on=parse_date(props.get('validOn')),
                            valid_to=parse_date(props.get('validTo')),
                            
                            # Area measurements
                            shape_length=props.get('Shape_Length'),
                            shape_area=props.get('Shape_Area'),
                            area_sqkm=props.get('AREA_SQKM'),
                            
                            # Geometry
                            geometry=geometry
                        )
                        
                        records_created += 1
                        
                        # Progress updates
                        if records_created == 1:
                            print(f"✅ First record: {barangay_name}, {municipality}")
                        
                        if records_created % 50 == 0:
                            print(f"✅ Progress: {records_created} Negros Oriental barangays imported...")
                    
                    except Exception as feature_error:
                        print(f"❌ Error processing feature {idx}: {feature_error}")
                        import traceback
                        traceback.print_exc()
                        continue
            
            # Final summary
            print(f"\n{'='*60}")
            print(f"🎉 IMPORT COMPLETE!")
            print(f"{'='*60}")
            print(f"✅ Successfully imported: {records_created} barangays")
            print(f"⏭️ Skipped (other provinces): {skipped_records} barangays")
            print(f"📍 Province: Negros Oriental")
            print(f"{'='*60}\n")
            
            return records_created
            
        except Exception as file_error:
            print(f"\n{'='*60}")
            print(f"❌ ERROR PROCESSING GDB")
            print(f"{'='*60}")
            print(f"Error: {file_error}")
            import traceback
            traceback.print_exc()
            raise    
    
    def process(self):
        """
        UPDATED: Main processing method with GDB support
        Automatically detects file type (Shapefile vs GDB)
        """
        try:
            file_name = self.uploaded_file.name.lower()
            
            print(f"📦 Processing file: {file_name}")
            print(f"📋 Dataset type: {self.dataset_type}")
            
            # Extract the uploaded ZIP file first
            self.temp_dir = tempfile.mkdtemp()
            temp_zip_path = os.path.join(self.temp_dir, 'upload.zip')
            
            # Save uploaded file to temp location
            with open(temp_zip_path, 'wb') as temp_file:
                for chunk in self.uploaded_file.chunks():
                    temp_file.write(chunk)
            
            print(f"💾 Saved to temp: {temp_zip_path}")
            
            # Extract ZIP contents
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.temp_dir)
            
            print(f"📂 Extracted to: {self.temp_dir}")
            
            # 🔍 DETECT FILE TYPE: Look for .gdb directory OR .shp file
            gdb_path = None
            shp_file = None
            
            for root, dirs, files in os.walk(self.temp_dir):
                # Check for .gdb directory (File Geodatabase)
                for dir_name in dirs:
                    if dir_name.endswith('.gdb'):
                        gdb_path = os.path.join(root, dir_name)
                        print(f"✅ Found GDB: {gdb_path}")
                        break
                
                # Check for .shp file (Shapefile)
                if not gdb_path:
                    for file in files:
                        if file.endswith('.shp'):
                            shp_file = os.path.join(root, file)
                            print(f"✅ Found Shapefile: {shp_file}")
                            break
                
                if gdb_path or shp_file:
                    break
            
            # 🚀 PROCESS BASED ON FILE TYPE
            if gdb_path:
                # ==========================================
                # PROCESS FILE GEODATABASE (.gdb)
                # ==========================================
                print(f"🗄️ Processing as File Geodatabase (GDB)")
                
                # Create dataset record
                dataset = HazardDataset.objects.create(
                    name=f"Barangay Boundaries - Negros Oriental (PSA-NAMRIA)",
                    dataset_type='barangay',
                    file_name=self.uploaded_file.name,
                    description="Accurate barangay boundaries from PSA-NAMRIA, filtered for Negros Oriental only"
                )
                
                # Process the GDB
                records_created = self.process_barangay_gdb(gdb_path, dataset)
                
                return {
                    'success': True,
                    'dataset_id': dataset.id,
                    'records_created': records_created,
                    'message': f'✅ Successfully processed {records_created} barangays for Negros Oriental'
                }
            
            elif shp_file:
                # ==========================================
                # PROCESS SHAPEFILE (.shp)
                # ==========================================
                print(f"🗺️ Processing as Shapefile")
                
                # Create dataset record
                dataset = HazardDataset.objects.create(
                    name=f"Uploaded {self.dataset_type.title()} Data",
                    dataset_type=self.dataset_type,
                    file_name=self.uploaded_file.name
                )
                
                # Route to appropriate shapefile processor
                if self.dataset_type == 'flood':
                    records_created = self.process_flood_data(shp_file, dataset)
                elif self.dataset_type == 'landslide':
                    records_created = self.process_landslide_data(shp_file, dataset)
                elif self.dataset_type == 'liquefaction':
                    records_created = self.process_liquefaction_data(shp_file, dataset)
                else:
                    raise ValueError(f"Unsupported dataset type: {self.dataset_type}")
                
                return {
                    'success': True,
                    'dataset_id': dataset.id,
                    'records_created': records_created,
                    'message': f'✅ Successfully processed {records_created} records'
                }
            
            else:
                # ==========================================
                # ERROR: No valid file found
                # ==========================================
                raise ValueError(
                    "❌ No valid geospatial file found in the ZIP archive. "
                    "Please upload a ZIP containing either:\n"
                    "  • A .gdb folder (File Geodatabase), OR\n"
                    "  • Shapefile components (.shp, .shx, .dbf, .prj)"
                )
            
        except Exception as e:
            print(f"❌ Processing error: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'success': False,
                'error': str(e)
            }
            
        finally:
            # Cleanup temp directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                import shutil
                try:
                    shutil.rmtree(self.temp_dir)
                    print(f"🧹 Cleaned up temp directory")
                except Exception as cleanup_error:
                    print(f"⚠️ Could not clean up temp directory: {cleanup_error}")



    
class CSVProcessor:
    """Process CSV files for tabular data"""
    
    def __init__(self, uploaded_file, dataset_type):
        self.uploaded_file = uploaded_file
        self.dataset_type = dataset_type

    def process_municipality_characteristics(self, dataset):
        """
        Process municipality_characteristics.csv with robust error handling
        """
        from .models import MunicipalityCharacteristic
        
        records_created = 0
        errors = []
        
        try:
            # Read CSV file with UTF-8-BOM encoding to handle Excel exports
            decoded_file = self.uploaded_file.read().decode('utf-8-sig').splitlines()
            
            # Try to detect delimiter
            first_line = decoded_file[0] if decoded_file else ''
            delimiter = ';' if ';' in first_line else ','
            
            csv_reader = csv.DictReader(decoded_file, delimiter=delimiter)
            
            print(f"\n{'='*60}")
            print(f"📊 PROCESSING MUNICIPALITY CHARACTERISTICS CSV")
            print(f"{'='*60}")
            print(f"📋 Detected delimiter: '{delimiter}'")
            print(f"📋 Column headers found: {csv_reader.fieldnames}")
            print(f"{'='*60}\n")
            
            # Strip whitespace from column names
            csv_reader.fieldnames = [name.strip() if name else name for name in csv_reader.fieldnames]
            
            for row_num, row in enumerate(csv_reader, start=2):
                try:
                    # DEBUG: Print first row to see what's being read
                    if row_num == 2:
                        print(f"🔍 DEBUG - First row data:")
                        for key, value in row.items():
                            print(f"   '{key}': '{value}'")
                        print()
                    
                    # Extract and clean data - try multiple possible column names
                    lgu_name = (
                        row.get('LGU') or 
                        row.get('lgu') or 
                        row.get('LGU Name') or 
                        ''
                    ).strip()
                    
                    correspondence_code = (
                        row.get('Correspondence_Code') or 
                        row.get('Correspondence Code') or 
                        row.get('correspondence_code') or 
                        row.get('Code') or
                        ''
                    ).strip()
                    
                    category = (
                        row.get('Category') or 
                        row.get('category') or 
                        row.get('Classification') or
                        ''
                    ).strip()
                    
                    # Skip if essential data is missing
                    if not lgu_name or not correspondence_code:
                        print(f"⚠️ Row {row_num}: Skipping - LGU='{lgu_name}', Code='{correspondence_code}'")
                        continue
                    
                    # Parse numeric fields safely
                    def parse_float(field_names, default=None):
                        """Try multiple possible field names"""
                        for name in field_names if isinstance(field_names, list) else [field_names]:
                            value = row.get(name, '')
                            if value and str(value).strip():
                                try:
                                    return float(str(value).replace(',', '').strip())
                                except (ValueError, AttributeError):
                                    continue
                        return default
                    
                    def parse_int(field_names, default=0):
                        """Try multiple possible field names"""
                        for name in field_names if isinstance(field_names, list) else [field_names]:
                            value = row.get(name, '')
                            if value and str(value).strip():
                                try:
                                    return int(str(value).replace(',', '').strip())
                                except (ValueError, AttributeError):
                                    continue
                        return default
                    
                    def parse_decimal(field_names, default=0):
                        """Try multiple possible field names"""
                        from decimal import Decimal
                        for name in field_names if isinstance(field_names, list) else [field_names]:
                            value = row.get(name, '')
                            if value and str(value).strip():
                                try:
                                    return Decimal(str(value).replace(',', '').strip())
                                except (ValueError, AttributeError):
                                    continue
                        return Decimal(default)
                    
                    # Create municipality record
                    MunicipalityCharacteristic.objects.create(
                        dataset=dataset,
                        lgu_name=lgu_name,
                        correspondence_code=correspondence_code,
                        category=category,
                        score=parse_float(['Score', 'score']),
                        population=parse_int(['Population', 'population']),
                        population_weight=parse_float(['Population Weight (50%)', 'Population Weight', 'pop_weight']),
                        revenue=parse_decimal(['Revenue', 'revenue']),
                        revenue_weight=parse_float(['Revenue Weight (50%)', 'Revenue Weight', 'revenue_weight']),
                        total_percentage=parse_float(['Total Percentage', 'Total', 'total_percentage']),
                        provincial_score=parse_float(['Provincial Score', 'provincial_score', 'DTI Score']),
                        poverty_incidence_rate=parse_float(['Poverty Incidence Rate', 'Poverty Rate', 'poverty_incidence'])
                    )
                    
                    records_created += 1
                    
                    if records_created == 1:
                        print(f"✅ First record: {lgu_name} ({category})")
                    
                    if records_created % 5 == 0:
                        print(f"✅ Processed {records_created} municipalities...")
                
                except Exception as row_error:
                    error_msg = f"Row {row_num} ({row.get('LGU', 'Unknown')}): {row_error}"
                    print(f"❌ {error_msg}")
                    errors.append(error_msg)
                    import traceback
                    traceback.print_exc()
                    continue
            
            print(f"\n{'='*60}")
            print(f"🎉 CSV IMPORT COMPLETE!")
            print(f"{'='*60}")
            print(f"✅ Successfully imported: {records_created} municipalities")
            if errors:
                print(f"⚠️ Errors encountered: {len(errors)}")
            print(f"{'='*60}\n")
            
            return records_created
            
        except Exception as e:
            print(f"❌ Error processing CSV: {e}")
            import traceback
            traceback.print_exc()
            raise

    def process_barangay_characteristics(self, dataset):
        """
        Process barangay_characteristics.csv
        
        Expected columns:
        - Barangay
        - Code
        - Population
        - Ecological Landscape
        - Urbanization
        - Cellular Signal
        - Public Street Sweeper
        """
        from .models import BarangayCharacteristic
        
        records_created = 0
        errors = []
        
        try:
            # Read CSV file with UTF-8-BOM encoding
            decoded_file = self.uploaded_file.read().decode('utf-8-sig').splitlines()
            
            # Detect delimiter
            first_line = decoded_file[0] if decoded_file else ''
            delimiter = ';' if ';' in first_line else ','
            
            csv_reader = csv.DictReader(decoded_file, delimiter=delimiter)
            
            print(f"\n{'='*60}")
            print(f"🏘️ PROCESSING BARANGAY CHARACTERISTICS CSV")
            print(f"{'='*60}")
            print(f"📋 Detected delimiter: '{delimiter}'")
            print(f"📋 Column headers: {csv_reader.fieldnames}")
            print(f"{'='*60}\n")
            
            # Strip whitespace from column names
            csv_reader.fieldnames = [name.strip() if name else name for name in csv_reader.fieldnames]
            
            for row_num, row in enumerate(csv_reader, start=2):
                try:
                    # DEBUG: Print first row
                    if row_num == 2:
                        print(f"🔍 DEBUG - First row data:")
                        for key, value in row.items():
                            print(f"   '{key}': '{value}'")
                        print()
                    
                    # Extract and clean data
                    barangay_name = (
                        row.get('Barangay') or 
                        row.get('barangay') or 
                        row.get('Barangay Name') or 
                        ''
                    ).strip()
                    
                    barangay_code = (
                        row.get('Code') or 
                        row.get('code') or 
                        row.get('Barangay Code') or 
                        row.get('barangay_code') or
                        ''
                    ).strip()
                    
                    # Skip if essential data is missing
                    if not barangay_name or not barangay_code:
                        print(f"⚠️ Row {row_num}: Skipping - Name='{barangay_name}', Code='{barangay_code}'")
                        continue
                    
                    # Parse population
                    population_str = (
                        row.get('Population') or 
                        row.get('population') or 
                        ''
                    ).strip()
                    
                    population = None
                    if population_str:
                        try:
                            population = int(str(population_str).replace(',', ''))
                        except (ValueError, AttributeError):
                            pass
                    
                    # Get landscape
                    ecological_landscape = (
                        row.get('Ecological Landscape') or 
                        row.get('ecological_landscape') or 
                        row.get('Landscape') or
                        ''
                    ).strip()
                    
                    # Get urbanization
                    urbanization = (
                        row.get('Urbanization') or 
                        row.get('urbanization') or
                        ''
                    ).strip()
                    
                    # Handle "Not Yet Identified" or empty urbanization
                    if not urbanization or urbanization.lower() in ['', 'none', 'null', 'n/a']:
                        urbanization = 'Not Yet Identified'
                    
                    # Get cellular signal
                    cellular_signal = (
                        row.get('Cellular Signal') or 
                        row.get('cellular_signal') or 
                        row.get('Signal') or
                        ''
                    ).strip()
                    
                    # Get public street sweeper
                    public_street_sweeper = (
                        row.get('Public Street Sweeper') or 
                        row.get('public_street_sweeper') or 
                        row.get('Street Sweeper') or
                        ''
                    ).strip()
                    
                    # Create barangay characteristic record
                    BarangayCharacteristic.objects.create(
                        dataset=dataset,
                        barangay_name=barangay_name,
                        barangay_code=barangay_code,
                        population=population,
                        ecological_landscape=ecological_landscape if ecological_landscape else None,
                        urbanization=urbanization if urbanization else None,
                        cellular_signal=cellular_signal if cellular_signal else None,
                        public_street_sweeper=public_street_sweeper if public_street_sweeper else None
                    )
                    
                    records_created += 1
                    
                    if records_created == 1:
                        print(f"✅ First record: {barangay_name} (Code: {barangay_code})")
                    
                    if records_created % 50 == 0:
                        print(f"✅ Processed {records_created} barangays...")
                
                except Exception as row_error:
                    error_msg = f"Row {row_num} ({row.get('Barangay', 'Unknown')}): {row_error}"
                    print(f"❌ {error_msg}")
                    errors.append(error_msg)
                    import traceback
                    traceback.print_exc()
                    continue
            
            print(f"\n{'='*60}")
            print(f"🎉 CSV IMPORT COMPLETE!")
            print(f"{'='*60}")
            print(f"✅ Successfully imported: {records_created} barangays")
            if errors:
                print(f"⚠️ Errors encountered: {len(errors)}")
            print(f"{'='*60}\n")
            
            return records_created
            
        except Exception as e:
            print(f"❌ Error processing CSV: {e}")
            import traceback
            traceback.print_exc()
            raise    

    def process_zonal_values(self, dataset):
        """
        Process zonal values CSV
        
        Expected columns:
        - Barangay
        - CODE
        - Municipality
        - Street
        - Vicinity
        - Class
        - Price per SQM
        """
        from .models import ZonalValue
        import decimal
        
        records_created = 0
        errors = []
        
        try:
            # Read CSV file with UTF-8-BOM encoding
            decoded_file = self.uploaded_file.read().decode('utf-8-sig').splitlines()
            
            # Detect delimiter
            first_line = decoded_file[0] if decoded_file else ''
            delimiter = ';' if ';' in first_line else ','
            
            csv_reader = csv.DictReader(decoded_file, delimiter=delimiter)
            
            print(f"\n{'='*60}")
            print(f"💰 PROCESSING ZONAL VALUES CSV")
            print(f"{'='*60}")
            print(f"📋 Detected delimiter: '{delimiter}'")
            print(f"📋 Column headers: {csv_reader.fieldnames}")
            print(f"{'='*60}\n")
            
            # Strip whitespace from column names
            csv_reader.fieldnames = [name.strip() if name else name for name in csv_reader.fieldnames]
            
            for row_num, row in enumerate(csv_reader, start=2):
                try:
                    # DEBUG: Print first row
                    if row_num == 2:
                        print(f"🔍 DEBUG - First row data:")
                        for key, value in row.items():
                            print(f"   '{key}': '{value}'")
                        print()
                    
                    # Extract and clean data
                    barangay_name = (
                        row.get('Barangay') or 
                        row.get('barangay') or 
                        row.get('BARANGAY') or 
                        ''
                    ).strip()
                    
                    barangay_code = (
                        row.get('CODE') or 
                        row.get('Code') or 
                        row.get('code') or 
                        row.get('Barangay Code') or
                        ''
                    ).strip()
                    
                    municipality = (
                        row.get('Municipality') or 
                        row.get('municipality') or 
                        row.get('MUNICIPALITY') or
                        ''
                    ).strip()
                    
                    # Skip if essential data is missing
                    if not barangay_name or not barangay_code:
                        print(f"⚠️ Row {row_num}: Skipping - Barangay='{barangay_name}', Code='{barangay_code}'")
                        continue
                    
                    # Extract optional fields
                    street = (
                        row.get('Street') or 
                        row.get('street') or 
                        row.get('STREET') or
                        ''
                    ).strip()
                    
                    vicinity = (
                        row.get('Vicinity') or 
                        row.get('vicinity') or 
                        row.get('VICINITY') or
                        ''
                    ).strip()
                    
                    land_class = (
                        row.get('Class') or 
                        row.get('class') or 
                        row.get('CLASS') or 
                        row.get('Land Class') or
                        ''
                    ).strip()
                    
                    # Parse price per sqm
                    price_str = (
                        row.get('Price per SQM') or 
                        row.get('price per sqm') or 
                        row.get('PRICE PER SQM') or
                        row.get('Price') or
                        ''
                    ).strip()
                    
                    if not price_str:
                        print(f"⚠️ Row {row_num}: Skipping - No price data")
                        continue
                    
                    # Clean and parse price
                    try:
                        # Remove currency symbols, commas, and whitespace
                        price_clean = price_str.replace('₱', '').replace('PHP', '').replace(',', '').strip()
                        price_per_sqm = Decimal(price_clean)
                    except (ValueError, decimal.InvalidOperation):
                        print(f"⚠️ Row {row_num}: Invalid price format: '{price_str}'")
                        continue
                    
                    # Create zonal value record
                    ZonalValue.objects.create(
                        dataset=dataset,
                        barangay_name=barangay_name,
                        barangay_code=barangay_code,
                        municipality=municipality,
                        street=street if street else None,
                        vicinity=vicinity if vicinity else None,
                        land_class=land_class if land_class else None,
                        price_per_sqm=price_per_sqm
                    )
                    
                    records_created += 1
                    
                    if records_created == 1:
                        print(f"✅ First record: {barangay_name} - {street or 'General'} (₱{price_per_sqm}/sqm)")
                    
                    if records_created % 50 == 0:
                        print(f"✅ Processed {records_created} zonal values...")
                
                except Exception as row_error:
                    error_msg = f"Row {row_num} ({row.get('Barangay', 'Unknown')}): {row_error}"
                    print(f"❌ {error_msg}")
                    errors.append(error_msg)
                    import traceback
                    traceback.print_exc()
                    continue
            
            print(f"\n{'='*60}")
            print(f"🎉 CSV IMPORT COMPLETE!")
            print(f"{'='*60}")
            print(f"✅ Successfully imported: {records_created} zonal values")
            if errors:
                print(f"⚠️ Errors encountered: {len(errors)}")
            print(f"{'='*60}\n")
            
            return records_created
            
        except Exception as e:
            print(f"❌ Error processing CSV: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def process(self):
        """Main processing method for CSV files"""
        try:
            # Create dataset record
            if self.dataset_type == 'municipality_characteristics':
                dataset_name = "Municipality Characteristics - Negros Oriental"
                description = "Socioeconomic characteristics of municipalities"
            elif self.dataset_type == 'barangay_characteristics':
                dataset_name = "Barangay Characteristics - Negros Oriental"
                description = "Population and infrastructure data for barangays"
            elif self.dataset_type == 'zonal_values':
                dataset_name = "Zonal Values - Negros Oriental"
                description = "Land prices per square meter by barangay"
            else:
                dataset_name = f"Uploaded {self.dataset_type.title()} Data"
                description = ""
            
            dataset = HazardDataset.objects.create(
                name=dataset_name,
                dataset_type=self.dataset_type,
                file_name=self.uploaded_file.name,
                description=description
            )
            
            # Route to appropriate processor
            if self.dataset_type == 'municipality_characteristics':
                records_created = self.process_municipality_characteristics(dataset)
            elif self.dataset_type == 'barangay_characteristics':
                records_created = self.process_barangay_characteristics(dataset)
            elif self.dataset_type == 'zonal_values':
                records_created = self.process_zonal_values(dataset)
            else:
                raise ValueError(f"Unsupported CSV dataset type: {self.dataset_type}")
            
            return {
                'success': True,
                'dataset_id': dataset.id,
                'records_created': records_created,
                'message': f'✅ Successfully processed {records_created} records'
            }
            
        except Exception as e:
            print(f"❌ Processing error: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'success': False,
                'error': str(e)
            }

def calculate_haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate straight-line distance between two coordinates using Haversine formula
    
    Args:
        lat1, lng1: Origin coordinates
        lat2, lng2: Destination coordinates
    
    Returns:
        Distance in meters
    """
    from math import radians, cos, sin, asin, sqrt
    
    # Convert to radians
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    c = 2 * asin(sqrt(a))
    
    # Earth radius in meters
    r = 6371000
    
    return c * r


def format_duration(seconds: float) -> str:
    """Format duration for display"""
    minutes = seconds / 60
    if minutes < 1:
        return "< 1 min"
    elif minutes < 60:
        return f"{int(minutes)} min"
    else:
        hours = int(minutes / 60)
        mins = int(minutes % 60)
        return f"{hours}h {mins}min"