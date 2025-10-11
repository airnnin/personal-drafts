import fiona
import zipfile
import os
import tempfile
import requests
from typing import Dict, Optional
import time
from django.contrib.gis.geos import GEOSGeometry
from .models import HazardDataset, FloodSusceptibility, LandslideSusceptibility, LiquefactionSusceptibility
import json


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
        
    def extract_shapefile(self):
        """Extract shapefile from uploaded zip"""
        self.temp_dir = tempfile.mkdtemp()
        
        temp_zip_path = os.path.join(self.temp_dir, 'shapefile.zip')
        with open(temp_zip_path, 'wb') as temp_file:
            for chunk in self.uploaded_file.chunks():
                temp_file.write(chunk)
        
        with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
            zip_ref.extractall(self.temp_dir)
        
        shp_file = None
        for file in os.listdir(self.temp_dir):
            if file.endswith('.shp'):
                shp_file = os.path.join(self.temp_dir, file)
                break
                
        if not shp_file:
            raise ValueError("No .shp file found in the uploaded zip")
            
        return shp_file
    
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

    def process_barangay_data(self, shp_file, dataset):
        """Process barangay boundary shapefile"""
        from .models import BarangayBoundary
        
        records_created = 0
        
        with fiona.open(shp_file) as shapefile:
            print(f"Processing barangay boundaries - CRS: {shapefile.crs}")
            
            for idx, feature in enumerate(shapefile):
                try:
                    props = feature['properties']
                    geom = feature['geometry']
                    
                    if geom is None:
                        continue
                    
                    # Clean up field values (remove newlines and extra spaces)
                    b_name = str(props.get('B_NAME', '')).strip().replace('\n', '')
                    lgu_name = str(props.get('LGU_NAME', '')).strip().replace('\n', '')
                    nsodata = str(props.get('NSODATA', '')).strip().replace('\n', '')
                    brgycode = str(props.get('BRGYCODE', '')).strip().replace('\n', '')
                    
                    # Convert geometry
                    geometry = self.transform_geometry(geom, shapefile.crs)
                    
                    BarangayBoundary.objects.create(
                        dataset=dataset,
                        brgy_id=props.get('BRGY_ID', 0),
                        brgycode=brgycode,
                        b_name=b_name,
                        lgu_name=lgu_name,
                        area_has=props.get('AREA_HAS_'),
                        area=props.get('AREA'),
                        perimeter=props.get('PERIMETER'),
                        hectares=props.get('HECTARES'),
                        area_nso=props.get('AREA_NSO'),
                        district=props.get('DISTRICT'),
                        pop_2020=props.get('POP_2020'),
                        nsodata=nsodata,
                        geometry=geometry
                    )
                    records_created += 1
                    
                    if records_created % 50 == 0:
                        print(f"Processed {records_created} barangay boundaries...")
                    
                except Exception as e:
                    print(f"Error processing barangay feature {idx}: {e}")
                    continue
        
        return records_created

    def process(self):
        """Main processing method"""
        try:
            shp_file = self.extract_shapefile()
            
            # Create dataset record
            dataset = HazardDataset.objects.create(
                name=f"Uploaded {self.dataset_type.title()} Data",
                dataset_type=self.dataset_type,
                file_name=self.uploaded_file.name
            )
            
            # Process based on dataset type
            if self.dataset_type == 'flood':
                records_created = self.process_flood_data(shp_file, dataset)
            elif self.dataset_type == 'landslide':
                records_created = self.process_landslide_data(shp_file, dataset)
            elif self.dataset_type == 'liquefaction':
                records_created = self.process_liquefaction_data(shp_file, dataset)
            elif self.dataset_type == 'barangay':  # NEW: Handle barangay boundaries
                records_created = self.process_barangay_data(shp_file, dataset)
            else:
                raise ValueError(f"Unsupported dataset type: {self.dataset_type}")
            
            return {
                'success': True,
                'dataset_id': dataset.id,
                'records_created': records_created,
                'message': f'Successfully processed {records_created} records'
            }
            
        except Exception as e:
            print(f"Processing error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
            
        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)

class RoadDistanceCalculator:
    """
    Calculate actual road distances using OSRM (Open Source Routing Machine)
    Falls back to straight-line distance if routing fails
    """
    
    OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving"
    
    @classmethod
    def get_road_distance(cls, lat1: float, lng1: float, lat2: float, lng2: float) -> Dict:
        """
        Get actual road distance between two points
        
        Args:
            lat1, lng1: Origin coordinates
            lat2, lng2: Destination coordinates
            
        Returns:
            dict with 'distance_meters', 'distance_km', 'duration_minutes', 'method'
        """
        try:
            # OSRM expects coordinates in lng,lat format
            url = f"{cls.OSRM_BASE_URL}/{lng1},{lat1};{lng2},{lat2}"
            params = {
                'overview': 'false',  # We don't need the full route geometry
                'steps': 'false'      # We don't need turn-by-turn directions
            }
            
            # Make API request with timeout
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('code') == 'Ok' and data.get('routes'):
                    route = data['routes'][0]
                    distance_meters = route['distance']  # Distance in meters
                    duration_seconds = route['duration']  # Duration in seconds
                    
                    return {
                        'distance_meters': distance_meters,
                        'distance_km': round(distance_meters / 1000, 2),
                        'duration_minutes': round(duration_seconds / 60, 1),
                        'method': 'road',
                        'success': True
                    }
            
            # If OSRM fails, fall back to straight-line
            return cls._fallback_straight_line(lat1, lng1, lat2, lng2)
            
        except requests.exceptions.Timeout:
            print(f"⚠️ OSRM timeout - falling back to straight-line distance")
            return cls._fallback_straight_line(lat1, lng1, lat2, lng2)
            
        except Exception as e:
            print(f"⚠️ OSRM error: {e} - falling back to straight-line distance")
            return cls._fallback_straight_line(lat1, lng1, lat2, lng2)
    
    @classmethod
    def _fallback_straight_line(cls, lat1: float, lng1: float, lat2: float, lng2: float) -> Dict:
        """Fallback to Haversine straight-line distance"""
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
        distance_meters = c * r
        
        # Estimate duration (assuming 40 km/h average speed)
        duration_minutes = (distance_meters / 1000) / 40 * 60
        
        return {
            'distance_meters': distance_meters,
            'distance_km': round(distance_meters / 1000, 2),
            'duration_minutes': round(duration_minutes, 1),
            'method': 'straight_line',
            'success': True
        }
    
    @classmethod
    def batch_calculate_distances(cls, origin_lat: float, origin_lng: float, 
                                  destinations: list, delay: float = 0.1) -> list:
        """
        Calculate road distances to multiple destinations
        Includes rate limiting to avoid overwhelming OSRM servers
        
        Args:
            origin_lat, origin_lng: Origin coordinates
            destinations: List of dicts with 'lat' and 'lng' keys
            delay: Delay between requests in seconds (default 0.1s = 100ms)
            
        Returns:
            List of destination dicts with added distance information
        """
        results = []
        
        for i, dest in enumerate(destinations):
            distance_data = cls.get_road_distance(
                origin_lat, origin_lng,
                dest['lat'], dest['lng']
            )
            
            # Merge distance data into destination
            dest.update(distance_data)
            results.append(dest)
            
            # Rate limiting - be nice to OSRM servers
            if i < len(destinations) - 1:  # Don't delay after last request
                time.sleep(delay)
        
        return results