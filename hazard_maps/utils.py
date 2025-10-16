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
    OPTIMIZED VERSION with batch processing and caching
    """
    
    OSRM_BASE_URL = "http://router.project-osrm.org"
    OSRM_TABLE_URL = f"{OSRM_BASE_URL}/table/v1/driving"
    OSRM_ROUTE_URL = f"{OSRM_BASE_URL}/route/v1/driving"
    
    # Cache distances for 7 days (rarely change)
    CACHE_TTL = 60 * 60 * 24 * 7  # 7 days in seconds
    
    @classmethod
    def batch_calculate_distances(cls, origin_lat: float, origin_lng: float, 
                                  destinations: list) -> list:
        """
        OPTIMIZED: Calculate road distances to multiple destinations using OSRM Table API
        
        This makes ONE API call instead of N calls, reducing time from 5 minutes to ~2 seconds
        
        Args:
            origin_lat, origin_lng: Origin coordinates
            destinations: List of dicts with 'lat' and 'lng' keys
            
        Returns:
            List of destination dicts with added distance information
        """
        
        if not destinations:
            return []
        
        # OPTIMIZATION 1: Check cache first
        cached_results = cls._get_cached_distances(origin_lat, origin_lng, destinations)
        if cached_results is not None:
            print(f"✅ Using cached distances for {len(destinations)} facilities")
            return cached_results
        
        # OPTIMIZATION 2: Use OSRM Table API for batch processing
        try:
            results = cls._batch_osrm_table(origin_lat, origin_lng, destinations)
            
            # Cache the results
            cls._cache_distances(origin_lat, origin_lng, results)
            
            return results
            
        except Exception as e:
            print(f"⚠️ OSRM Table API failed: {e}, falling back to individual requests")
            # Fallback to original method but with smaller batch
            return cls._fallback_sequential(origin_lat, origin_lng, destinations[:30])  # Limit to 30
    
    @classmethod
    def _batch_osrm_table(cls, origin_lat: float, origin_lng: float, 
                         destinations: list) -> list:
        """
        Use OSRM Table API to get all distances in ONE request
        
        OSRM Table API format:
        http://router.project-osrm.org/table/v1/driving/lng1,lat1;lng2,lat2;lng3,lat3?sources=0&annotations=distance,duration
        """
        
        # OSRM has a limit of ~100 coordinates per request
        # If more destinations, split into chunks
        MAX_DESTINATIONS = 100
        
        if len(destinations) > MAX_DESTINATIONS:
            print(f"⚠️ {len(destinations)} destinations exceed OSRM limit, processing in chunks...")
            return cls._process_in_chunks(origin_lat, origin_lng, destinations, MAX_DESTINATIONS)
        
        # Build coordinate string: origin;dest1;dest2;dest3...
        coords = f"{origin_lng},{origin_lat}"  # Origin (index 0)
        for dest in destinations:
            coords += f";{dest['lng']},{dest['lat']}"
        
        # Build URL with parameters
        url = f"{cls.OSRM_TABLE_URL}/{coords}"
        params = {
            'sources': '0',  # Only calculate from origin (index 0)
            'annotations': 'distance,duration'  # Get both distance and time
        }
        
        # Make request with timeout
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('code') != 'Ok':
            raise Exception(f"OSRM error: {data.get('message', 'Unknown error')}")
        
        # Parse results
        distances = data['distances'][0]  # First row (from origin to all destinations)
        durations = data['durations'][0]  # First row (from origin to all destinations)
        
        # Update destinations with distance data
        results = []
        for i, dest in enumerate(destinations):
            dest_index = i + 1  # +1 because origin is at index 0
            
            distance_meters = distances[dest_index]
            duration_seconds = durations[dest_index]
            
            # Handle null/None values (unreachable destinations)
            if distance_meters is None or duration_seconds is None:
                # Fallback to straight-line
                fallback_data = cls._calculate_straight_line(
                    origin_lat, origin_lng, dest['lat'], dest['lng']
                )
                dest.update(fallback_data)
            else:
                dest.update({
                    'distance_meters': distance_meters,
                    'distance_km': round(distance_meters / 1000, 2),
                    'duration_minutes': round(duration_seconds / 60, 1),
                    'duration_display': cls._format_duration(duration_seconds),
                    'distance_display': cls._format_distance(distance_meters),
                    'method': 'road',
                    'success': True,
                    'is_walkable': distance_meters <= 500
                })
            
            results.append(dest)
        
        print(f"✅ OSRM Table API: Processed {len(results)} destinations in one request")
        return results
    
    @classmethod
    def _process_in_chunks(cls, origin_lat: float, origin_lng: float, 
                          destinations: list, chunk_size: int) -> list:
        """Process destinations in chunks if they exceed OSRM limit"""
        results = []
        
        for i in range(0, len(destinations), chunk_size):
            chunk = destinations[i:i + chunk_size]
            chunk_results = cls._batch_osrm_table(origin_lat, origin_lng, chunk)
            results.extend(chunk_results)
            
            # Small delay between chunks to be nice to OSRM servers
            if i + chunk_size < len(destinations):
                time.sleep(0.2)
        
        return results
    
    @classmethod
    def _fallback_sequential(cls, origin_lat: float, origin_lng: float, 
                            destinations: list) -> list:
        """
        Fallback: Sequential requests (old method) with reduced batch size
        Only use if Table API fails
        """
        results = []
        
        for dest in destinations:
            distance_data = cls.get_road_distance(
                origin_lat, origin_lng,
                dest['lat'], dest['lng']
            )
            dest.update(distance_data)
            results.append(dest)
            
            # Minimal delay
            time.sleep(0.05)
        
        return results
    
    @classmethod
    def get_road_distance(cls, lat1: float, lng1: float, lat2: float, lng2: float) -> Dict:
        """
        Get actual road distance between TWO points (single request)
        Use this only for single calculations, not batch processing
        """
        try:
            url = f"{cls.OSRM_ROUTE_URL}/{lng1},{lat1};{lng2},{lat2}"
            params = {
                'overview': 'false',
                'steps': 'false'
            }
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('code') == 'Ok' and data.get('routes'):
                    route = data['routes'][0]
                    distance_meters = route['distance']
                    duration_seconds = route['duration']
                    
                    return {
                        'distance_meters': distance_meters,
                        'distance_km': round(distance_meters / 1000, 2),
                        'duration_minutes': round(duration_seconds / 60, 1),
                        'duration_display': cls._format_duration(duration_seconds),
                        'distance_display': cls._format_distance(distance_meters),
                        'method': 'road',
                        'success': True,
                        'is_walkable': distance_meters <= 500
                    }
            
            return cls._calculate_straight_line(lat1, lng1, lat2, lng2)
            
        except Exception as e:
            print(f"⚠️ OSRM single request error: {e}")
            return cls._calculate_straight_line(lat1, lng1, lat2, lng2)
    
    @classmethod
    def _calculate_straight_line(cls, lat1: float, lng1: float, 
                                 lat2: float, lng2: float) -> Dict:
        """Fallback to Haversine straight-line distance"""
        lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
        
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * asin(sqrt(a))
        
        r = 6371000  # Earth radius in meters
        distance_meters = c * r
        
        # Estimate duration (assuming 40 km/h average speed)
        duration_minutes = (distance_meters / 1000) / 40 * 60
        
        return {
            'distance_meters': distance_meters,
            'distance_km': round(distance_meters / 1000, 2),
            'duration_minutes': round(duration_minutes, 1),
            'duration_display': cls._format_duration(duration_minutes * 60),
            'distance_display': cls._format_distance(distance_meters),
            'method': 'straight_line',
            'success': True,
            'is_walkable': distance_meters <= 500
        }
    
    @classmethod
    def _format_distance(cls, meters: float) -> str:
        """Format distance for display"""
        if meters < 1000:
            return f"{int(meters)} m"
        else:
            return f"{meters / 1000:.1f} km"
    
    @classmethod
    def _format_duration(cls, seconds: float) -> str:
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
    
    # ================= CACHING METHODS =================
    
    @classmethod
    def _get_cache_key(cls, origin_lat: float, origin_lng: float) -> str:
        """Generate cache key for a location (rounded to 4 decimal places ~11m precision)"""
        lat_rounded = round(origin_lat, 4)
        lng_rounded = round(origin_lng, 4)
        return f"osrm_distances_{lat_rounded}_{lng_rounded}"
    
    @classmethod
    def _get_cached_distances(cls, origin_lat: float, origin_lng: float, 
                             destinations: list) -> list:
        """Try to get cached distances"""
        cache_key = cls._get_cache_key(origin_lat, origin_lng)
        cached_data = cache.get(cache_key)
        
        if cached_data is None:
            return None
        
        # Check if destinations match (same facilities)
        if len(cached_data) != len(destinations):
            return None
        
        return cached_data
    
    @classmethod
    def _cache_distances(cls, origin_lat: float, origin_lng: float, results: list):
        """Cache distance results"""
        cache_key = cls._get_cache_key(origin_lat, origin_lng)
        cache.set(cache_key, results, cls.CACHE_TTL)
        print(f"💾 Cached distances for {len(results)} facilities")

class HybridDistanceCalculator:
    """
    HYBRID APPROACH: Use straight-line for most, OSRM only for critical facilities
    Windows-optimized with aggressive caching
    """
    
    CACHE_TTL = 60 * 60 * 24 * 30  # 30 days
    
    @classmethod
    def batch_calculate_distances(cls, origin_lat: float, origin_lng: float, 
                                  facilities: list) -> list:
        """
        OPTIMIZED FOR WINDOWS: Hybrid approach
        - Use straight-line distance by default (instant)
        - Only use OSRM for TOP 10 critical facilities (hospitals, fire stations)
        - Aggressive caching
        """
        
        if not facilities:
            return []
        
        print(f"🚀 Processing {len(facilities)} facilities with hybrid method...")
        
        # STEP 1: Calculate straight-line distances for ALL facilities (instant)
        for facility in facilities:
            distance_meters = cls._haversine_distance(
                origin_lat, origin_lng,
                facility['lat'], facility['lng']
            )
            
            facility['distance_meters'] = distance_meters
            facility['distance_km'] = round(distance_meters / 1000, 2)
            facility['distance_display'] = cls._format_distance(distance_meters)
            facility['is_walkable'] = distance_meters <= 500
            
            # Estimate duration (40 km/h average)
            duration_minutes = (distance_meters / 1000) / 40 * 60
            facility['duration_minutes'] = round(duration_minutes, 1)
            facility['duration_display'] = cls._format_duration(duration_minutes * 60)
            facility['method'] = 'straight_line'
        
        # STEP 2: Identify TOP 10 CRITICAL facilities for OSRM routing
        critical_facilities = [
            f for f in facilities 
            if f.get('facility_type') in ['hospital', 'clinic', 'fire_station', 'police']
               and f['distance_meters'] <= 10000  # Within 10km only
        ][:10]  # Top 10 only
        
        if critical_facilities:
            print(f"🚗 Getting road distances for {len(critical_facilities)} critical facilities...")
            cls._update_critical_distances(origin_lat, origin_lng, critical_facilities)
        
        # STEP 3: Sort by distance
        facilities.sort(key=lambda x: x['distance_meters'])
        
        road_count = sum(1 for f in facilities if f.get('method') == 'road')
        print(f"✅ Completed: {road_count} road distances, {len(facilities)-road_count} straight-line")
        
        return facilities
    
    @classmethod
    def _update_critical_distances(cls, origin_lat: float, origin_lng: float, 
                                   critical_facilities: list):
        """Get OSRM distances for critical facilities with caching"""
        
        for facility in critical_facilities:
            # Check cache first
            cache_key = cls._get_cache_key(
                origin_lat, origin_lng,
                facility['lat'], facility['lng']
            )
            
            cached_data = cache.get(cache_key)
            if cached_data:
                facility.update(cached_data)
                facility['method'] = 'road_cached'
                continue
            
            # Get fresh OSRM data
            try:
                url = f"http://router.project-osrm.org/route/v1/driving/{origin_lng},{origin_lat};{facility['lng']},{facility['lat']}"
                params = {'overview': 'false', 'steps': 'false'}
                
                response = requests.get(url, params=params, timeout=3)  # SHORT timeout
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get('code') == 'Ok' and data.get('routes'):
                        route = data['routes'][0]
                        distance_meters = route['distance']
                        duration_seconds = route['duration']
                        
                        road_data = {
                            'distance_meters': distance_meters,
                            'distance_km': round(distance_meters / 1000, 2),
                            'duration_minutes': round(duration_seconds / 60, 1),
                            'duration_display': cls._format_duration(duration_seconds),
                            'distance_display': cls._format_distance(distance_meters),
                            'is_walkable': distance_meters <= 500,
                            'method': 'road'
                        }
                        
                        facility.update(road_data)
                        
                        # Cache for 30 days
                        cache.set(cache_key, road_data, cls.CACHE_TTL)
                        
                        # Be nice to OSRM
                        time.sleep(0.1)
                
            except Exception as e:
                # Fallback: keep straight-line distance
                print(f"⚠️ OSRM failed for {facility['name']}: {e}")
                continue
    
    @classmethod
    def _haversine_distance(cls, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate straight-line distance in meters"""
        lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * asin(sqrt(a))
        return 6371000 * c
    
    @classmethod
    def _format_distance(cls, meters: float) -> str:
        """Format distance for display"""
        if meters < 1000:
            return f"{int(meters)} m"
        return f"{meters / 1000:.1f} km"
    
    @classmethod
    def _format_duration(cls, seconds: float) -> str:
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
    
    @classmethod
    def _get_cache_key(cls, lat1: float, lng1: float, lat2: float, lng2: float) -> str:
        """Generate cache key for a route"""
        # Round to 4 decimal places (~11m precision)
        key_string = f"{round(lat1,4)}_{round(lng1,4)}_{round(lat2,4)}_{round(lng2,4)}"
        return f"osrm_route_{hashlib.md5(key_string.encode()).hexdigest()}"