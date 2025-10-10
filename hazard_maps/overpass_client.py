import requests
import time
from typing import Dict, List

class OverpassClient:
    """Client for querying OpenStreetMap via Overpass API"""
    
    BASE_URL = "https://overpass-api.de/api/interpreter"

    # Official OSM amenity tags
    AMENITY_MAPPING = {
        # Medical/Health
        'hospital': {'category': 'emergency', 'name': 'Hospital'},
        'clinic': {'category': 'emergency', 'name': 'Clinic'},
        'doctors': {'category': 'emergency', 'name': 'Medical Clinic'},
        'dentist': {'category': 'emergency', 'name': 'Dental Clinic'},
        'pharmacy': {'category': 'emergency', 'name': 'Pharmacy'},
        
        # Emergency Services
        'fire_station': {'category': 'emergency', 'name': 'Fire Station'},
        'police': {'category': 'emergency', 'name': 'Police Station'},
        
        # Education
        'school': {'category': 'everyday', 'name': 'School'},
        'kindergarten': {'category': 'everyday', 'name': 'Kindergarten'},
        'college': {'category': 'everyday', 'name': 'College'},
        'university': {'category': 'everyday', 'name': 'University'},
        
        # Food & Dining
        'restaurant': {'category': 'everyday', 'name': 'Restaurant'},
        'fast_food': {'category': 'everyday', 'name': 'Fast Food'},
        'cafe': {'category': 'everyday', 'name': 'Cafe'},
        
        # Shopping
        'marketplace': {'category': 'everyday', 'name': 'Market'},
        'bank': {'category': 'everyday', 'name': 'Bank'},
        'atm': {'category': 'everyday', 'name': 'ATM'},
        
        # Transportation
        'fuel': {'category': 'everyday', 'name': 'Gas Station'},
        'bus_station': {'category': 'everyday', 'name': 'Bus Station'},
        'ferry_terminal': {'category': 'everyday', 'name': 'Ferry Terminal'},
        
        # Worship
        'place_of_worship': {'category': 'everyday', 'name': 'Place of Worship'},
        
        # Government
        'townhall': {'category': 'government', 'name': 'Municipal/Town Hall'},
        'community_centre': {'category': 'government', 'name': 'Community Center'},
    }

    SHOP_MAPPING = {
        'supermarket': {'category': 'everyday', 'name': 'Supermarket'},
        'convenience': {'category': 'everyday', 'name': 'Convenience Store'},
        'mall': {'category': 'everyday', 'name': 'Shopping Mall'},
    }

    OFFICE_MAPPING = {
        'government': {'category': 'government', 'name': 'Government Office'},
    }
    
    # Map OSM amenity tags to our categories
    FACILITY_MAPPING = {
        # Emergency & Disaster-Related
        'hospital': {'category': 'emergency', 'name': 'Hospital'},
        'clinic': {'category': 'emergency', 'name': 'Clinic'},
        'doctors': {'category': 'emergency', 'name': 'Medical Clinic'},
        'fire_station': {'category': 'emergency', 'name': 'Fire Station'},
        'police': {'category': 'emergency', 'name': 'Police Station'},
        'pharmacy': {'category': 'emergency', 'name': 'Pharmacy'},
        
        # Everyday Life
        'school': {'category': 'everyday', 'name': 'School'},
        'college': {'category': 'everyday', 'name': 'College'},
        'university': {'category': 'everyday', 'name': 'University'},
        'marketplace': {'category': 'everyday', 'name': 'Market'},
        'fuel': {'category': 'everyday', 'name': 'Gas Station'},
        'bank': {'category': 'everyday', 'name': 'Bank'},
        'atm': {'category': 'everyday', 'name': 'ATM'},
        'bus_station': {'category': 'everyday', 'name': 'Bus Station'},
        'ferry_terminal': {'category': 'everyday', 'name': 'Ferry Terminal'},
        
        # Government & Administrative
        'townhall': {'category': 'government', 'name': 'Town/Municipal Hall'},
        'community_centre': {'category': 'government', 'name': 'Community Center'},
        'public_building': {'category': 'government', 'name': 'Public Building'},
    }
    
    # Shop types for everyday facilities
    SHOP_TYPES = ['supermarket', 'convenience', 'mall']
    
    @classmethod
    def query_facilities(cls, lat: float, lng: float, radius: int = 3000) -> List[Dict]:
        """
        Query OSM for facilities around a point
        Simplified query to avoid timeouts
        """
        
        # Simplified query - using regex to group similar tags
        query = f"""
        [out:json][timeout:25];
        (
        nwr["amenity"~"^(hospital|clinic|doctors|pharmacy|fire_station|police)$"](around:{radius},{lat},{lng});
        nwr["amenity"~"^(school|university|college|restaurant|fast_food|cafe)$"](around:{radius},{lat},{lng});
        nwr["amenity"~"^(bank|atm|fuel|marketplace|townhall|community_centre)$"](around:{radius},{lat},{lng});
        nwr["shop"~"^(supermarket|convenience|mall)$"](around:{radius},{lat},{lng});
        nwr["office"="government"](around:{radius},{lat},{lng});
        nwr["healthcare"="hospital"](around:{radius},{lat},{lng});
        );
        out center;
        """
        
        try:
            response = requests.post(
                cls.BASE_URL,
                data={'data': query},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            facilities = []
            seen_ids = set()
            
            for element in data.get('elements', []):
                osm_id = element.get('id')
                if osm_id not in seen_ids:
                    facility = cls._parse_element(element)
                    if facility:
                        facilities.append(facility)
                        seen_ids.add(osm_id)
            
            return facilities
            
        except requests.exceptions.Timeout:
            print(f"Overpass API timeout - query took too long")
            return []
        except requests.exceptions.RequestException as e:
            print(f"Overpass API error: {e}")
            return []
        except Exception as e:
            print(f"Error parsing Overpass response: {e}")
            return []
    
    @classmethod
    def _parse_element(cls, element: Dict) -> Dict:
        """Parse OSM element into facility dict"""
        tags = element.get('tags', {})
        
        # Get coordinates (different for nodes vs ways)
        if element.get('type') == 'node':
            lat = element.get('lat')
            lng = element.get('lon')
        elif element.get('type') == 'way':
            # For ways, use the center coordinates
            center = element.get('center', {})
            lat = center.get('lat')
            lng = center.get('lon')
        else:
            return None
        
        if not lat or not lng:
            return None
        
        # Determine facility type and category
        facility_type = None
        category = None
        type_display = None
        
        # Check amenity tag first (most common)
        if 'amenity' in tags:
            facility_type = tags['amenity']
            facility_info = cls.AMENITY_MAPPING.get(facility_type)
            if facility_info:
                category = facility_info['category']
                type_display = facility_info['name']
        
        # Check healthcare tag
        elif 'healthcare' in tags:
            if tags['healthcare'] == 'hospital':
                facility_type = 'hospital'
                category = 'emergency'
                type_display = 'Hospital'
        
        # Check shop tag
        elif 'shop' in tags:
            facility_type = tags['shop']
            facility_info = cls.SHOP_MAPPING.get(facility_type)
            if facility_info:
                category = facility_info['category']
                type_display = facility_info['name']
        
        # Check office tag
        elif 'office' in tags:
            facility_type = tags['office']
            facility_info = cls.OFFICE_MAPPING.get(facility_type)
            if facility_info:
                category = facility_info['category']
                type_display = facility_info['name']
        
        # If no valid facility type found
        if not category or not type_display:
            # Check if it's a barangay hall by name
            name = tags.get('name', '').lower()
            if 'barangay' in name:
                facility_type = 'barangay_hall'
                category = 'government'
                type_display = 'Barangay Hall'
            else:
                return None
        
        # Get facility name
        name = tags.get('name') or tags.get('name:en') or f"Unnamed {type_display}"
        
        return {
            'osm_id': element.get('id'),
            'osm_type': element.get('type'),
            'name': name,
            'facility_type': facility_type,
            'type_display': type_display,
            'category': category,
            'lat': lat,
            'lng': lng,
        }
    @classmethod
    def get_location_info(cls, lat: float, lng: float) -> Dict:
        """
        Get administrative boundary information for a point using Nominatim reverse geocoding
        
        Args:
            lat: Latitude
            lng: Longitude
            
        Returns:
            Dictionary with location details
        """
        nominatim_url = "https://nominatim.openstreetmap.org/reverse"
        
        params = {
            'lat': lat,
            'lon': lng,
            'format': 'json',
            'addressdetails': 1,
            'zoom': 18,  # Detailed zoom level to get barangay
        }
        
        headers = {
            'User-Agent': 'DisasterRiskAssessmentSystem/1.0'  # Required by Nominatim
        }
        
        try:
            response = requests.get(
                nominatim_url,
                params=params,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            address = data.get('address', {})
            
            # Extract location components
            # Nominatim uses different keys for Philippine barangays
            barangay = (
                address.get('suburb') or  # Sometimes barangay is tagged as suburb
                address.get('neighbourhood') or 
                address.get('village') or
                address.get('hamlet') or
                'Unknown Barangay'
            )
            
            municipality = (
                address.get('city') or
                address.get('town') or
                address.get('municipality') or
                'Unknown Municipality'
            )
            
            province = address.get('state', 'Negros Oriental')
            
            return {
                'barangay': barangay,
                'municipality': municipality,
                'province': province,
                'full_address': data.get('display_name', ''),
                'success': True
            }
            
        except requests.exceptions.RequestException as e:
            print(f"Nominatim reverse geocoding error: {e}")
            return {
                'barangay': 'Unknown',
                'municipality': 'Unknown',
                'province': 'Negros Oriental',
                'full_address': f"Lat: {lat:.6f}, Lng: {lng:.6f}",
                'success': False
            }