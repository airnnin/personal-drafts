from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('api/upload-shapefile/', views.upload_shapefile, name='upload_shapefile'),
    path('api/flood-data/', views.get_flood_data, name='flood_data'),
    path('api/landslide-data/', views.get_landslide_data, name='landslide_data'),
    path('api/liquefaction-data/', views.get_liquefaction_data, name='liquefaction_data'),
    path('api/barangay-data/', views.get_barangay_data, name='barangay_data'),  # NEW
    path('api/barangay-from-point/', views.get_barangay_from_point, name='barangay_from_point'),  # NEW
    path('api/municipality-info/', views.get_municipality_info, name='municipality_info'),
    path('api/barangay-characteristics/', views.get_barangay_characteristics, name='barangay_characteristics'),
    path('api/zonal-values/', views.get_zonal_values, name='zonal_values'),
    path('api/datasets/', views.get_datasets, name='datasets'),
    path('api/location-hazards/', views.get_location_hazards, name='location_hazards'),
    path('api/nearby-facilities/', views.get_nearby_facilities, name='nearby_facilities'),
    path('api/location-info/', views.get_location_info, name='location_info'),
]