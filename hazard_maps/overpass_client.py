import requests
import time
from typing import Dict, List
from math import radians, cos, sin, asin, sqrt

class OverpassClient:
    """Client for querying OpenStreetMap via Overpass API"""
    
    BASE_URL = "https://overpass-api.de/api/interpreter"

    # Comprehensive facility mapping
    AMENITY_MAPPING = {
        # CRITICAL FACILITIES (Priority 1-2) - GET ALL
        'hospital': {'category': 'emergency', 'name': 'Hospital', 'priority': 1, 'subcat': 'medical'},
        'clinic': {'category': 'emergency', 'name': 'Clinic', 'priority': 1, 'subcat': 'medical'},
        'doctors': {'category': 'emergency', 'name': 'Medical Clinic', 'priority': 1, 'subcat': 'medical'},
        'pharmacy': {'category': 'emergency', 'name': 'Pharmacy', 'priority': 3, 'subcat': 'essential'},
        'fire_station': {'category': 'emergency', 'name': 'Fire Station', 'priority': 1, 'subcat': 'emergency_services'},
        'police': {'category': 'emergency', 'name': 'Police Station', 'priority': 1, 'subcat': 'emergency_services'},
        
        # EVACUATION CENTERS (Priority 1-2) - GET ALL
        'school': {'category': 'everyday', 'name': 'School', 'priority': 1, 'subcat': 'evacuation'},
        'kindergarten': {'category': 'everyday', 'name': 'Kindergarten', 'priority': 2, 'subcat': 'evacuation'},
        'college': {'category': 'everyday', 'name': 'College', 'priority': 1, 'subcat': 'evacuation'},
        'university': {'category': 'everyday', 'name': 'University', 'priority': 1, 'subcat': 'evacuation'},
        'community_centre': {'category': 'government', 'name': 'Community Center', 'priority': 1, 'subcat': 'evacuation'},
        
        # ESSENTIAL SERVICES (Priority 3) - GET NEAREST ONLY
        'marketplace': {'category': 'everyday', 'name': 'Market', 'priority': 3, 'subcat': 'essential'},
        'bank': {'category': 'everyday', 'name': 'Bank', 'priority': 3, 'subcat': 'essential'},
        'atm': {'category': 'everyday', 'name': 'ATM', 'priority': 4, 'subcat': 'essential'},
        'fuel': {'category': 'everyday', 'name': 'Gas Station', 'priority': 3, 'subcat': 'essential'},
        'restaurant': {'category': 'everyday', 'name': 'Restaurant', 'priority': 4, 'subcat': 'essential'},
        'fast_food': {'category': 'everyday', 'name': 'Fast Food', 'priority': 4, 'subcat': 'essential'},
        'cafe': {'category': 'everyday', 'name': 'Cafe', 'priority': 4, 'subcat': 'essential'},
        'post_office': {'category': 'government', 'name': 'Post Office', 'priority': 3, 'subcat': 'essential'},  # NEW
        'ferry_terminal': {'category': 'everyday', 'name': 'Ferry Terminal', 'priority': 3, 'subcat': 'essential'},  # NEW
        
        # GOVERNMENT (Priority 2-3)
        'townhall': {'category': 'government', 'name': 'Town/Municipal Hall', 'priority': 2, 'subcat': 'government'},
        'public_building': {'category': 'government', 'name': 'Public Building', 'priority': 3, 'subcat': 'government'},
    }

    SHOP_MAPPING = {
        'supermarket': {'category': 'everyday', 'name': 'Supermarket', 'priority': 3, 'subcat': 'essential'},
        'convenience': {'category': 'everyday', 'name': 'Convenience Store', 'priority': 3, 'subcat': 'essential'},
        'mall': {'category': 'everyday', 'name': 'Shopping Mall', 'priority': 3, 'subcat': 'essential'},
        'department_store': {'category': 'everyday', 'name': 'Department Store', 'priority': 3, 'subcat': 'essential'},
    }

    OFFICE_MAPPING = {
        'government': {'category': 'government', 'name': 'Government Office', 'priority': 3, 'subcat': 'government'},
    }
    
    @classmethod
    def query_facilities(cls, lat: float, lng: float, radius: int = 3000) -> List[Dict]:
        """
        BALANCED QUERY: All critical facilities + nearest essential services
        Returns ~50-70 facilities total
        """
        
        # COMPREHENSIVE QUERY: Include all facility types
        query = f"""
        [out:json][timeout:20];
        (
        nwr["amenity"~"^(hospital|clinic|doctors|pharmacy|fire_station|police)$"](around:{radius},{lat},{lng});
        nwr["amenity"~"^(school|kindergarten|college|university|community_centre)$"](around:{radius},{lat},{lng});
        nwr["amenity"~"^(marketplace|bank|atm|fuel|townhall|public_building|post_office)$"](around:{radius},{lat},{lng});
        nwr["amenity"~"^(restaurant|fast_food|cafe|ferry_terminal)$"](around:{radius},{lat},{lng});
        nwr["shop"~"^(supermarket|convenience|mall|department_store)$"](around:{radius},{lat},{lng});
        nwr["office"="government"](around:{radius},{lat},{lng});
        nwr["amenity"="ferry_terminal"](around:{radius},{lat},{lng});
        nwr["man_made"="pier"](around:{radius},{lat},{lng});
        nwr["harbour"="yes"](around:{radius},{lat},{lng});
        );
        out center;
        """
        
        try:
            # RETRY LOGIC for rate limits
            max_retries = 2
            retry_delay = 2
            
            for attempt in range(max_retries):
                response = requests.post(
                    cls.BASE_URL,
                    data={'data': query},
                    timeout=25
                )
                
                if response.status_code == 429:  # Too Many Requests
                    if attempt < max_retries - 1:
                        print(f"⚠️ Rate limited, waiting {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    else:
                        print(f"⚠️ Rate limit exceeded after {max_retries} attempts")
                        return []
                
                response.raise_for_status()
                break  # Success
            data = response.json()
            
            facilities = []
            seen_ids = set()
            
            for element in data.get('elements', []):
                osm_id = element.get('id')
                if osm_id not in seen_ids:
                    facility = cls._parse_element(element)
                    if facility:
                        # Calculate straight-line distance
                        facility['straight_distance'] = cls._haversine_distance(
                            lat, lng, facility['lat'], facility['lng']
                        )
                        facilities.append(facility)
                        seen_ids.add(osm_id)
            
            # SMART FILTERING: Keep all critical, limit non-critical
            critical_facilities = []
            essential_facilities = []
            other_facilities = []
            
            for f in facilities:
                priority = f.get('priority', 9)
                subcat = f.get('subcategory', 'other')
                
                if priority <= 2:  # Critical: hospitals, fire stations, schools
                    critical_facilities.append(f)
                elif subcat == 'essential':  # Essential services
                    essential_facilities.append(f)
                else:  # Other
                    other_facilities.append(f)
            
            # Sort each group by distance
            critical_facilities.sort(key=lambda x: x['straight_distance'])
            essential_facilities.sort(key=lambda x: x['straight_distance'])
            other_facilities.sort(key=lambda x: x['straight_distance'])
            
            # BALANCED SELECTION:
            # - ALL critical facilities (hospitals, fire, schools) - usually 30-40
            # - Top 20 essential services (markets, banks, restaurants)
            # - Top 10 other facilities
            final_facilities = (
                critical_facilities[:50] +           # Max 50 critical
                essential_facilities[:20] +          # Max 20 essential
                other_facilities[:10]                # Max 10 other
            )
            
            # Re-sort by priority then distance
            final_facilities.sort(key=lambda x: (x.get('priority', 9), x['straight_distance']))
            
            # Count by subcategory for debugging
            from collections import Counter
            subcats = Counter(f.get('subcategory', 'other') for f in final_facilities)
            
            print(f"✅ Overpass API returned {len(final_facilities)} facilities (from {len(facilities)} total):")
            print(f"   - Medical: {subcats.get('medical', 0)}")
            print(f"   - Emergency Services: {subcats.get('emergency_services', 0)}")
            print(f"   - Evacuation Centers: {subcats.get('evacuation', 0)}")
            print(f"   - Essential Services: {subcats.get('essential', 0)}")
            print(f"   - Government: {subcats.get('government', 0)}")
            print(f"   - Other: {subcats.get('other', 0)}")
            
            return final_facilities
            
        except requests.exceptions.Timeout:
            print(f"⚠️ Overpass API timeout")
            return []
        except Exception as e:
            print(f"⚠️ Overpass API error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    @classmethod
    def _parse_element(cls, element: Dict) -> Dict:
        """Parse OSM element into facility dict with proper subcategorization"""
        tags = element.get('tags', {})
        
        # Get coordinates
        if element.get('type') == 'node':
            lat = element.get('lat')
            lng = element.get('lon')
        elif element.get('type') in ['way', 'relation']:
            center = element.get('center', {})
            lat = center.get('lat')
            lng = center.get('lon')
        else:
            return None
        
        if not lat or not lng:
            return None
        
        # Determine facility type, category, and subcategory
        facility_type = None
        category = None
        type_display = None
        priority = 9
        subcategory = None
        
        # Check amenity tag
        if 'amenity' in tags:
            facility_type = tags['amenity']
            facility_info = cls.AMENITY_MAPPING.get(facility_type)
            if facility_info:
                category = facility_info['category']
                type_display = facility_info['name']
                priority = facility_info['priority']
                subcategory = facility_info.get('subcat', 'other')  # ✅ FIX: Always get subcat
        
        # Check shop tag
        elif 'shop' in tags:
            facility_type = tags['shop']
            facility_info = cls.SHOP_MAPPING.get(facility_type)
            if facility_info:
                category = facility_info['category']
                type_display = facility_info['name']
                priority = facility_info['priority']
                subcategory = facility_info.get('subcat', 'other')  # ✅ FIX: Always get subcat
        
        # Check office tag
        elif 'office' in tags:
            facility_type = tags['office']
            facility_info = cls.OFFICE_MAPPING.get(facility_type)
            if facility_info:
                category = facility_info['category']
                type_display = facility_info['name']
                priority = facility_info['priority']
                subcategory = facility_info.get('subcat', 'other')  # ✅ FIX: Always get subcat
        
        if not category or not type_display:
            return None
        
        # ✅ CRITICAL FIX: Ensure subcategory is NEVER None
        if not subcategory:
            subcategory = 'other'
        
        name = tags.get('name') or tags.get('name:en') or f"Unnamed {type_display}"
        
        return {
            'osm_id': element.get('id'),
            'osm_type': element.get('type'),
            'name': name,
            'facility_type': facility_type,
            'type_display': type_display,
            'category': category,
            'subcategory': subcategory,  # ✅ NOW ALWAYS SET
            'priority': priority,
            'lat': lat,
            'lng': lng,
        }
    
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
    def get_location_info(cls, lat: float, lng: float) -> Dict:
        """Get administrative boundary information"""
        nominatim_url = "https://nominatim.openstreetmap.org/reverse"
        
        params = {
            'lat': lat,
            'lon': lng,
            'format': 'json',
            'addressdetails': 1,
            'zoom': 18,
        }
        
        headers = {
            'User-Agent': 'DisasterRiskAssessmentSystem/1.0'
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
            
            barangay = (
                address.get('suburb') or
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
            
        except Exception as e:
            print(f"Nominatim error: {e}")
            return {
                'barangay': 'Unknown',
                'municipality': 'Unknown',
                'province': 'Negros Oriental',
                'full_address': f"Lat: {lat:.6f}, Lng: {lng:.6f}",
                'success': False
            }